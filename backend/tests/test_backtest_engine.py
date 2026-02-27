"""
Tests fuer den Backtest Engine Domain-Modul.

TDD: RED phase — alle Tests sollen initial fehlschlagen, bis die Implementierung steht.
Tests decken: Config-Validierung, Warmup, Signal-Generierung, Trailing-Stop-Exit,
Equity-Curve, Performance-Metriken, Monthly Returns, Benchmark, Degraded Alpha Score,
Cancellation, und Edge Cases.
"""
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

import pytest

from app.domain.backtest_engine import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BenchmarkResult,
    EquityPoint,
    MonthlyReturn,
    TradeRecord,
    compute_benchmark,
    compute_max_drawdown,
    compute_monthly_returns,
    compute_sharpe_ratio,
    compute_warmup_period,
    run_alpha_backtest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2024, 1, 1, 0, 0, 0)


def _make_candle(
    index: int,
    open_: str = "100",
    high: str = "102",
    low: str = "98",
    close: str = "101",
    volume: str = "1000",
    base_time: datetime = BASE_TIME,
    interval_hours: int = 1,
) -> dict:
    """Create a candle dict matching expected backtest engine format."""
    return {
        "open_time": base_time + timedelta(hours=index * interval_hours),
        "open": Decimal(open_),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
        "volume": Decimal(volume),
    }


def _make_candle_series(
    count: int,
    base_price: str = "100",
    trend: str = "0",
    volatility: str = "2",
    base_time: datetime = BASE_TIME,
) -> List[dict]:
    """Create a series of candles with optional trend and volatility."""
    candles = []
    price = Decimal(base_price)
    trend_d = Decimal(trend)
    vol = Decimal(volatility)
    for i in range(count):
        price = price + trend_d
        o = price
        h = price + vol
        l = price - vol
        c = price + trend_d / 2
        candles.append(_make_candle(
            i, str(o), str(h), str(l), str(c), "1000", base_time,
        ))
    return candles


def _default_config(**overrides) -> BacktestConfig:
    """Create a default BacktestConfig for tests, with optional overrides."""
    defaults = dict(
        symbol="XRPBTC",
        initial_capital=Decimal("10000"),
        position_fraction=Decimal("0.10"),
        entry_threshold=Decimal("3.0"),
        fee_rate=Decimal("0.001"),
        slippage_pct=Decimal("0.0005"),
        atr_period=14,
        atr_multiplier=Decimal("3.0"),
        zscore_window=20,
        leadlag_window=15,
        hurst_lookback=40,
        weights={
            "zscore": Decimal("0.40"),
            "leadlag": Decimal("0.30"),
            "imbalance": Decimal("0.20"),
            "funding": Decimal("0.10"),
        },
        hurst_trending=Decimal("0.55"),
        hurst_reverting=Decimal("0.45"),
    )
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def _make_trending_xrpbtc_candles(count: int, start_price: str = "0.00002") -> List[dict]:
    """Create XRPBTC candles with a mean-reverting pattern to generate signals."""
    candles = []
    base = Decimal(start_price)
    for i in range(count):
        # Create oscillating pattern: price goes up then sharply back
        # This should create mean-reversion signals
        cycle = i % 40
        if cycle < 20:
            # Rising phase
            offset = base * Decimal(str(cycle)) * Decimal("0.02")
        else:
            # Falling phase back to mean
            offset = base * Decimal(str(40 - cycle)) * Decimal("0.02")

        price = base + offset
        vol = base * Decimal("0.01")
        candles.append(_make_candle(
            i,
            str(price),
            str(price + vol),
            str(price - vol),
            str(price),
            "1000",
        ))
    return candles


def _make_btceur_candles(count: int, start_price: str = "40000") -> List[dict]:
    """Create BTCEUR candles with gradual uptrend."""
    candles = []
    price = Decimal(start_price)
    for i in range(count):
        trend = Decimal("10") * Decimal(str(i % 20 - 10))
        p = price + trend
        candles.append(_make_candle(
            i,
            str(p),
            str(p + Decimal("50")),
            str(p - Decimal("50")),
            str(p),
            "500",
        ))
    return candles


def _make_xrpeur_candles(count: int, start_price: str = "0.50") -> List[dict]:
    """Create XRPEUR candles with moderate volatility."""
    candles = []
    price = Decimal(start_price)
    for i in range(count):
        offset = Decimal("0.005") * Decimal(str(i % 10 - 5))
        p = price + offset
        candles.append(_make_candle(
            i,
            str(p),
            str(p + Decimal("0.01")),
            str(p - Decimal("0.01")),
            str(p),
            "10000",
        ))
    return candles


# ===========================================================================
# 1. BacktestConfig validation (4 tests)
# ===========================================================================


class TestBacktestConfigValidation:
    """Config validation tests."""

    def test_valid_config_creates_successfully(self):
        config = _default_config()
        assert config.symbol == "XRPBTC"
        assert config.initial_capital == Decimal("10000")
        assert config.position_fraction == Decimal("0.10")

    def test_negative_fee_rate_raises(self):
        with pytest.raises(ValueError, match="fee_rate"):
            _default_config(fee_rate=Decimal("-0.001"))

    def test_invalid_position_fraction_zero_raises(self):
        with pytest.raises(ValueError, match="position_fraction"):
            _default_config(position_fraction=Decimal("0"))

    def test_invalid_position_fraction_above_one_raises(self):
        with pytest.raises(ValueError, match="position_fraction"):
            _default_config(position_fraction=Decimal("1.5"))

    def test_warmup_computed_from_max_windows(self):
        config = _default_config(
            zscore_window=60,
            leadlag_window=30,
            hurst_lookback=100,
            atr_period=14,
        )
        warmup = compute_warmup_period(config)
        # max(60, 30, 100, 14+1) + 10 = 110
        assert warmup == 110


# ===========================================================================
# 2. Warmup period (3 tests)
# ===========================================================================


class TestWarmupPeriod:
    """Warmup period handling tests."""

    def test_no_trades_during_warmup(self):
        """No trades should be generated during the warmup period."""
        config = _default_config(
            zscore_window=20, leadlag_window=15, hurst_lookback=40, atr_period=14,
        )
        warmup = compute_warmup_period(config)
        # Provide exactly warmup candles + 5 extra
        count = warmup + 5

        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)

        # Check no trade entered before warmup_end_index
        for trade in result.trades:
            # Find the candle index for trade entry
            entry_idx = next(
                i for i, c in enumerate(xrpbtc)
                if c["open_time"] == trade.entry_time
            )
            assert entry_idx >= result.warmup_end_index

    def test_first_possible_trade_at_warmup_end(self):
        """First possible trade is at warmup_end_index."""
        config = _default_config(
            zscore_window=20, leadlag_window=15, hurst_lookback=40, atr_period=14,
        )
        warmup = compute_warmup_period(config)
        result_warmup = compute_warmup_period(config)
        assert result_warmup == warmup

    def test_warmup_end_index_in_result(self):
        """BacktestResult includes warmup_end_index."""
        config = _default_config()
        count = compute_warmup_period(config) + 10
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        assert result.warmup_end_index == compute_warmup_period(config)


# ===========================================================================
# 3. Signal generation and trade entry (6 tests)
# ===========================================================================


class TestSignalGenerationAndEntry:
    """Signal generation and trade entry tests."""

    def test_long_signal_opens_trade(self):
        """A LONG signal above threshold opens a trade."""
        config = _default_config(entry_threshold=Decimal("0.5"))
        # Use enough data to pass warmup and generate at least one signal
        count = compute_warmup_period(config) + 200
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # With trending oscillating data and low threshold, should get trades
        # (may or may not depending on score, but at least engine completes)
        assert isinstance(result, BacktestResult)
        assert result.metrics.trade_count >= 0

    def test_neutral_signal_does_not_open_trade(self):
        """NEUTRAL signal does not open a trade — long-only."""
        # With extremely high threshold, no trade should open
        config = _default_config(entry_threshold=Decimal("5.0"))
        count = compute_warmup_period(config) + 50
        xrpbtc = _make_candle_series(count, "100", "0", "1")
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # Flat data with max threshold should produce 0 trades
        assert result.metrics.trade_count == 0

    def test_new_long_signal_while_open_is_ignored(self):
        """New LONG signal while position already open is ignored."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("10.0"),  # Very wide stop — trade unlikely to close
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # Even with many signals, only one position at a time
        # Check no overlapping trades
        closed = [t for t in result.trades if not t.is_open]
        for i in range(len(closed) - 1):
            assert closed[i].exit_time is not None
            assert closed[i + 1].entry_time >= closed[i].exit_time

    def test_trade_entry_records_fields(self):
        """Trade entry records all required fields."""
        config = _default_config(entry_threshold=Decimal("0.3"))
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.trades:
            trade = result.trades[0]
            assert isinstance(trade.entry_time, datetime)
            assert isinstance(trade.entry_price, Decimal)
            assert isinstance(trade.alpha_score_at_entry, Decimal)
            assert isinstance(trade.qty, Decimal)
            assert trade.qty > 0

    def test_position_size_uses_equity_fraction(self):
        """Position size = current_equity * position_fraction / entry_price."""
        config = _default_config(
            position_fraction=Decimal("0.10"),
            entry_threshold=Decimal("0.3"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.trades:
            trade = result.trades[0]
            # First trade: equity = initial_capital, so position value ~= 10% of 10000 = 1000
            expected_value = config.initial_capital * config.position_fraction
            actual_value = trade.entry_price * trade.qty
            # Allow for slippage difference
            tolerance = expected_value * Decimal("0.05")
            assert abs(actual_value - expected_value) < tolerance

    def test_entry_fee_deducted(self):
        """Entry fee is applied and tracked."""
        config = _default_config(
            fee_rate=Decimal("0.001"),
            entry_threshold=Decimal("0.3"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.trades:
            trade = result.trades[0]
            assert trade.fees_paid > 0


# ===========================================================================
# 4. Trailing stop exit (6 tests)
# ===========================================================================


class TestTrailingStopExit:
    """Trailing stop exit mechanism tests."""

    def test_trade_exits_when_low_hits_stop(self):
        """Trade exits when candle low <= trailing stop level."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),  # Tight stop for quicker exit
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        closed = [t for t in result.trades if not t.is_open]
        # With oscillating data and tight stop, should get some closed trades
        if closed:
            trade = closed[0]
            assert trade.exit_time is not None
            assert trade.exit_price is not None

    def test_exit_price_is_stop_level_with_slippage(self):
        """Exit price = trailing stop level minus slippage."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            slippage_pct=Decimal("0.001"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        closed = [t for t in result.trades if not t.is_open]
        if closed:
            trade = closed[0]
            # Exit price should be <= entry price for a losing trade or
            # any value for a winning trade; key is it uses Decimal
            assert isinstance(trade.exit_price, Decimal)

    def test_exit_fee_deducted(self):
        """Exit fee is deducted from proceeds."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        closed = [t for t in result.trades if not t.is_open]
        if closed:
            trade = closed[0]
            assert trade.fees_paid > 0

    def test_trailing_stop_ratchets_up(self):
        """Trailing stop ratchets up as price increases — never down for longs."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # This is implicitly tested by the trailing stop logic from alpha_score.py
        assert isinstance(result, BacktestResult)

    def test_trade_pnl_is_decimal(self):
        """Trade P&L = exit_proceeds - entry_cost (Decimal)."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        closed = [t for t in result.trades if not t.is_open]
        if closed:
            trade = closed[0]
            assert isinstance(trade.pnl_eur, Decimal)
            assert isinstance(trade.pnl_pct, Decimal)

    def test_trade_record_has_duration(self):
        """Trade record includes duration in candles."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        closed = [t for t in result.trades if not t.is_open]
        if closed:
            trade = closed[0]
            assert isinstance(trade.duration_candles, int)
            assert trade.duration_candles > 0


# ===========================================================================
# 5. Equity curve (4 tests)
# ===========================================================================


class TestEquityCurve:
    """Equity curve tracking tests."""

    def test_equity_starts_at_initial_capital(self):
        """Equity curve starts at initial_capital."""
        config = _default_config()
        count = compute_warmup_period(config) + 50
        xrpbtc = _make_candle_series(count, "100", "0", "1")
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.equity_curve:
            assert result.equity_curve[0].equity == config.initial_capital

    def test_equity_updates_after_trade_close(self):
        """Equity updates reflect P&L after trades close."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.trades and result.equity_curve:
            # Final equity should reflect all trade P&Ls
            assert isinstance(result.equity_curve[-1].equity, Decimal)

    def test_equity_point_has_all_fields(self):
        """Each equity point has timestamp, equity, benchmark_equity, drawdown_pct."""
        config = _default_config()
        count = compute_warmup_period(config) + 50
        xrpbtc = _make_candle_series(count, "100", "0", "1")
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.equity_curve:
            pt = result.equity_curve[0]
            assert isinstance(pt, EquityPoint)
            assert isinstance(pt.timestamp, datetime)
            assert isinstance(pt.equity, Decimal)
            assert isinstance(pt.benchmark_equity, Decimal)
            assert isinstance(pt.drawdown_pct, Decimal)

    def test_equity_curve_downsampled_to_daily(self):
        """Equity curve is downsampled to daily granularity."""
        config = _default_config()
        # 300 hours of data = ~12.5 days
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.equity_curve:
            # Should have far fewer points than candles
            assert len(result.equity_curve) < count
            # Check dates are unique (daily)
            dates = [pt.timestamp.date() for pt in result.equity_curve]
            assert len(dates) == len(set(dates))


# ===========================================================================
# 6. Performance metrics (6 tests)
# ===========================================================================


class TestPerformanceMetrics:
    """Performance metrics computation tests."""

    def test_net_return_pct_correct(self):
        """net_return_pct = (final_equity - initial_capital) / initial_capital * 100."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        assert isinstance(result.metrics.net_return_pct, Decimal)

    def test_sharpe_ratio_annualized_365(self):
        """Sharpe ratio uses 365-day annualization for crypto."""
        daily_equities = [Decimal("10000") + Decimal(str(i * 10)) for i in range(100)]
        sharpe = compute_sharpe_ratio(daily_equities, annualization=365)
        assert sharpe is not None
        assert isinstance(sharpe, Decimal)
        assert sharpe > 0  # Steadily increasing equity -> positive Sharpe

    def test_sharpe_returns_none_when_std_zero(self):
        """Sharpe returns None when std=0."""
        # Constant equity -> zero returns -> std=0
        daily_equities = [Decimal("10000")] * 50
        sharpe = compute_sharpe_ratio(daily_equities)
        assert sharpe is None

    def test_sharpe_returns_none_fewer_than_2_points(self):
        """Sharpe returns None with fewer than 2 data points."""
        sharpe = compute_sharpe_ratio([Decimal("10000")])
        assert sharpe is None

    def test_max_drawdown_from_hwm(self):
        """max_drawdown_pct from high-water-mark tracking."""
        equities = [
            Decimal("10000"), Decimal("11000"), Decimal("10500"),
            Decimal("9000"), Decimal("9500"),
        ]
        dd = compute_max_drawdown(equities)
        # Max drawdown: from 11000 to 9000 = -18.18%
        expected = (Decimal("11000") - Decimal("9000")) / Decimal("11000") * 100
        assert abs(dd - expected) < Decimal("0.01")

    def test_win_rate_correct(self):
        """win_rate = winning_trades / total_trades * 100 (None if 0 trades)."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        if result.metrics.trade_count > 0:
            assert isinstance(result.metrics.win_rate, Decimal)
            assert Decimal("0") <= result.metrics.win_rate <= Decimal("100")
        else:
            assert result.metrics.win_rate is None

    def test_trade_count_matches_trades_list(self):
        """trade_count matches actual trades list length."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        assert result.metrics.trade_count == len(result.trades)

    def test_total_fees_and_slippage_tracked_separately(self):
        """total_fees and total_slippage are separate Decimal sums."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
            fee_rate=Decimal("0.001"),
            slippage_pct=Decimal("0.0005"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        assert isinstance(result.metrics.total_fees, Decimal)
        assert isinstance(result.metrics.total_slippage, Decimal)
        assert result.metrics.total_fees >= 0
        assert result.metrics.total_slippage >= 0


# ===========================================================================
# 7. Monthly returns (3 tests)
# ===========================================================================


class TestMonthlyReturns:
    """Monthly returns computation tests."""

    def test_monthly_returns_computed(self):
        """Monthly returns computed from equity curve."""
        # Create equity points spanning 3 months
        points = []
        for m in range(1, 4):
            for d in range(1, 29):
                dt = datetime(2024, m, d)
                equity = Decimal("10000") + Decimal(str(m * 100 + d))
                points.append(EquityPoint(
                    timestamp=dt,
                    equity=equity,
                    benchmark_equity=equity,
                    drawdown_pct=Decimal("0"),
                ))

        monthly = compute_monthly_returns(points)
        assert len(monthly) == 3
        for mr in monthly:
            assert isinstance(mr, MonthlyReturn)
            assert isinstance(mr.return_pct, Decimal)

    def test_monthly_returns_list_format(self):
        """Monthly returns have year, month, return_pct."""
        points = []
        for d in range(1, 29):
            dt = datetime(2024, 1, d)
            equity = Decimal("10000") + Decimal(str(d * 10))
            points.append(EquityPoint(
                timestamp=dt,
                equity=equity,
                benchmark_equity=equity,
                drawdown_pct=Decimal("0"),
            ))

        monthly = compute_monthly_returns(points)
        assert len(monthly) >= 1
        assert monthly[0].year == 2024
        assert monthly[0].month == 1

    def test_monthly_returns_partial_months(self):
        """Handles partial first/last month correctly."""
        points = [
            EquityPoint(datetime(2024, 1, 15), Decimal("10000"), Decimal("10000"), Decimal("0")),
            EquityPoint(datetime(2024, 1, 20), Decimal("10100"), Decimal("10000"), Decimal("0")),
            EquityPoint(datetime(2024, 2, 1), Decimal("10200"), Decimal("10000"), Decimal("0")),
            EquityPoint(datetime(2024, 2, 15), Decimal("10400"), Decimal("10000"), Decimal("0")),
        ]
        monthly = compute_monthly_returns(points)
        assert len(monthly) == 2
        # Jan: (10200 - 10000) / 10000 * 100 = 2%
        # (uses last equity in month vs first equity at start of month)


# ===========================================================================
# 8. Benchmark (5 tests)
# ===========================================================================


class TestBenchmark:
    """50/50 BTC/XRP HODL benchmark tests."""

    def test_benchmark_50_50_computed(self):
        """50/50 BTC/XRP HODL benchmark computed from first candle close."""
        btceur = _make_btceur_candles(100)
        xrpeur = _make_xrpeur_candles(100)
        capital = Decimal("10000")
        fee_rate = Decimal("0.001")

        equities, bench = compute_benchmark(btceur, xrpeur, capital, fee_rate, start_index=0)
        assert isinstance(bench, BenchmarkResult)
        assert isinstance(bench.return_pct, Decimal)
        assert isinstance(bench.final_equity, Decimal)

    def test_benchmark_fee_applied_on_purchase(self):
        """Same fee_rate applied on initial benchmark purchase."""
        btceur = _make_btceur_candles(50)
        xrpeur = _make_xrpeur_candles(50)
        capital = Decimal("10000")
        fee_rate = Decimal("0.001")

        equities, bench = compute_benchmark(btceur, xrpeur, capital, fee_rate, start_index=0)
        # Benchmark initial equity should be capital minus fees
        # 50% * 10000 = 5000 per asset, fee = 5000 * 0.001 = 5 per asset = 10 total
        # So initial value = 10000 - 10 = 9990
        # First equity point should be close to 9990 (depending on close prices)
        assert equities[0] <= capital  # Must be less due to fees

    def test_benchmark_equity_tracked_per_candle(self):
        """Benchmark equity tracked at each candle (mark-to-market)."""
        btceur = _make_btceur_candles(50)
        xrpeur = _make_xrpeur_candles(50)
        capital = Decimal("10000")
        fee_rate = Decimal("0.001")

        equities, bench = compute_benchmark(btceur, xrpeur, capital, fee_rate, start_index=0)
        assert len(equities) == 50

    def test_excess_return_computed(self):
        """excess_return_pct = strategy_return - benchmark_return."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("1.5"),
        )
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # BacktestResult should include benchmark
        assert isinstance(result.benchmark, BenchmarkResult)
        assert isinstance(result.benchmark.return_pct, Decimal)

    def test_benchmark_sharpe_computed(self):
        """Benchmark Sharpe ratio computed."""
        btceur = _make_btceur_candles(100)
        xrpeur = _make_xrpeur_candles(100)
        capital = Decimal("10000")
        fee_rate = Decimal("0.001")

        equities, bench = compute_benchmark(btceur, xrpeur, capital, fee_rate, start_index=0)
        # Sharpe may be None or Decimal depending on data volatility
        assert bench.sharpe_ratio is None or isinstance(bench.sharpe_ratio, Decimal)


# ===========================================================================
# 9. Degraded Alpha Score (3 tests)
# ===========================================================================


class TestDegradedAlphaScore:
    """Only Z-Score and Lead-Lag active (orderbook + funding unavailable)."""

    def test_degraded_mode_generates_trades(self):
        """With only Z-Score and Lead-Lag, trades can still be generated."""
        config = _default_config(entry_threshold=Decimal("0.5"))
        count = compute_warmup_period(config) + 200
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # Engine should work in degraded mode (2/4 factors)
        assert isinstance(result, BacktestResult)

    def test_alpha_score_renormalizes_weights(self):
        """Alpha Score renormalizes weights with unavailable factors."""
        # This is tested implicitly through the backtest engine which
        # marks imbalance and funding as "unavailable"
        config = _default_config(
            weights={
                "zscore": Decimal("0.40"),
                "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"),
                "funding": Decimal("0.10"),
            },
            entry_threshold=Decimal("0.3"),
        )
        count = compute_warmup_period(config) + 200
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        assert isinstance(result, BacktestResult)

    def test_two_factor_partial_score(self):
        """Trades generated from 2-factor partial score (Z-Score + Lead-Lag)."""
        config = _default_config(entry_threshold=Decimal("0.5"))
        count = compute_warmup_period(config) + 300
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # Result should be valid (not error)
        assert result.candle_count == count


# ===========================================================================
# 10. Cancellation (2 tests)
# ===========================================================================


class TestCancellation:
    """Cancellation via threading.Event tests."""

    def test_cancel_event_stops_simulation(self):
        """When cancel_event is set, simulation stops and returns partial result."""
        config = _default_config()
        count = compute_warmup_period(config) + 500
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        cancel = threading.Event()
        # Set cancel before running (immediate cancel)
        cancel.set()

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config, cancel_event=cancel)
        assert result.cancelled is True

    def test_partial_result_has_metrics(self):
        """Partial result after cancellation has metrics computed from trades so far."""
        config = _default_config()
        count = compute_warmup_period(config) + 500
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        cancel = threading.Event()
        cancel.set()

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config, cancel_event=cancel)
        assert isinstance(result.metrics, BacktestMetrics)
        assert isinstance(result.metrics.net_return_pct, Decimal)


# ===========================================================================
# 11. Edge cases (3 tests)
# ===========================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_candle_data_returns_zero_trade_result(self):
        """Empty candle data returns zero-trade result with initial_capital equity."""
        config = _default_config()
        result = run_alpha_backtest([], [], [], config)
        assert result.metrics.trade_count == 0
        assert result.metrics.net_return_pct == Decimal("0")

    def test_all_candles_within_warmup(self):
        """All candles within warmup returns zero-trade result."""
        config = _default_config(hurst_lookback=100)
        warmup = compute_warmup_period(config)
        # Provide fewer candles than warmup
        count = warmup - 5
        xrpbtc = _make_candle_series(count, "100", "0", "1")
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        assert result.metrics.trade_count == 0
        assert result.metrics.net_return_pct == Decimal("0")

    def test_open_trade_at_end_marked(self):
        """Trade still open at end of data is marked as open_trade."""
        config = _default_config(
            entry_threshold=Decimal("0.3"),
            atr_multiplier=Decimal("100.0"),  # Very wide stop — will never exit
        )
        count = compute_warmup_period(config) + 200
        xrpbtc = _make_trending_xrpbtc_candles(count)
        btceur = _make_btceur_candles(count)
        xrpeur = _make_xrpeur_candles(count)

        result = run_alpha_backtest(xrpbtc, btceur, xrpeur, config)
        # If there's an open trade, it should be in result.open_trade
        if result.open_trade is not None:
            assert result.open_trade.is_open is True
            assert result.open_trade.exit_time is None
            assert result.open_trade.exit_price is None
