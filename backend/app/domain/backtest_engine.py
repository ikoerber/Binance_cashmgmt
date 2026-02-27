"""
Backtest Engine Domain-Logik (pure, kein I/O).

Simuliert Alpha Score Signal-Trading auf historischen Kerzen-Daten und berechnet
Performance-Metriken. Reines Domain-Modul ohne DB, API oder Netzwerk-Aufrufe.

Alle finanziellen Berechnungen verwenden Decimal (kein float, Ausnahme: math.sqrt
fuer Sharpe-Annualisierung).
"""

import math
import threading
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Dict, List, Optional, Tuple

from app.domain.alpha_score import (
    AlphaFactorScore,
    AlphaScoreResult as _AlphaScoreResult,
    RegimeInfo,
    TrailingStopState,
    compute_alpha_score,
    compute_atr_standalone,
    compute_hurst_rs,
    compute_leadlag_momentum,
    compute_regime_adjusted_weights,
    compute_zscore_mean_reversion,
    update_trailing_stop,
)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""

    symbol: str
    initial_capital: Decimal
    position_fraction: Decimal
    entry_threshold: Decimal
    fee_rate: Decimal
    slippage_pct: Decimal
    atr_period: int
    atr_multiplier: Decimal
    zscore_window: int
    leadlag_window: int
    hurst_lookback: int
    weights: Dict[str, Decimal]
    hurst_trending: Decimal
    hurst_reverting: Decimal

    def __post_init__(self) -> None:
        if self.fee_rate < Decimal("0"):
            raise ValueError("fee_rate must be >= 0")
        if self.position_fraction <= Decimal("0") or self.position_fraction > Decimal(
            "1"
        ):
            raise ValueError("position_fraction must be > 0 and <= 1")


@dataclass
class TradeRecord:
    """Record of a single trade."""

    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: Decimal
    exit_price: Optional[Decimal]
    qty: Decimal
    pnl_eur: Optional[Decimal]
    pnl_pct: Optional[Decimal]
    duration_candles: Optional[int]
    alpha_score_at_entry: Decimal
    fees_paid: Decimal
    slippage_cost: Decimal
    is_open: bool


@dataclass
class EquityPoint:
    """A single point on the equity curve."""

    timestamp: datetime
    equity: Decimal
    benchmark_equity: Decimal
    drawdown_pct: Decimal


@dataclass
class MonthlyReturn:
    """Monthly return for a given year/month."""

    year: int
    month: int
    return_pct: Decimal


@dataclass
class BenchmarkResult:
    """Result of the benchmark computation."""

    return_pct: Decimal
    final_equity: Decimal
    sharpe_ratio: Optional[Decimal]


@dataclass
class BacktestMetrics:
    """Aggregated performance metrics."""

    net_return_pct: Decimal
    sharpe_ratio: Optional[Decimal]
    max_drawdown_pct: Decimal
    trade_count: int
    win_rate: Optional[Decimal]
    total_fees: Decimal
    total_slippage: Decimal
    avg_trade_duration: Optional[Decimal]


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""

    config: BacktestConfig
    metrics: BacktestMetrics
    trades: List[TradeRecord]
    equity_curve: List[EquityPoint]
    monthly_returns: List[MonthlyReturn]
    warmup_end_index: int
    data_start: datetime
    data_end: datetime
    candle_count: int
    benchmark: BenchmarkResult
    open_trade: Optional[TradeRecord]
    cancelled: bool


# ---------------------------------------------------------------------------
# Pure computation functions
# ---------------------------------------------------------------------------


def compute_warmup_period(config: BacktestConfig) -> int:
    """
    Compute the number of candles needed for indicator warmup.

    Returns max(zscore_window, leadlag_window, hurst_lookback, atr_period+1) + 10.
    """
    return (
        max(
            config.zscore_window,
            config.leadlag_window,
            config.hurst_lookback,
            config.atr_period + 1,
        )
        + 10
    )


def compute_sharpe_ratio(
    daily_equities: List[Decimal],
    annualization: int = 365,
) -> Optional[Decimal]:
    """
    Compute annualized Sharpe ratio from daily equity values.

    Returns None if std=0 or fewer than 2 data points.
    Risk-free rate = 0 (standard for crypto).
    """
    if len(daily_equities) < 2:
        return None

    daily_returns: List[Decimal] = []
    for i in range(1, len(daily_equities)):
        if daily_equities[i - 1] != 0:
            daily_returns.append(
                (daily_equities[i] - daily_equities[i - 1]) / daily_equities[i - 1]
            )

    if len(daily_returns) < 1:
        return None

    n = Decimal(str(len(daily_returns)))
    mean_r = sum(daily_returns) / n
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / n
    std_r = variance.sqrt() if variance > 0 else Decimal("0")

    if std_r == 0:
        return None

    # math.sqrt for annualization factor, immediately converted to Decimal
    ann_factor = Decimal(str(math.sqrt(annualization)))
    return (mean_r / std_r * ann_factor).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def compute_max_drawdown(equity_curve: List[Decimal]) -> Decimal:
    """
    Compute maximum drawdown percentage from equity curve using high-water-mark.

    Returns the maximum percentage decline from peak to trough.
    """
    if not equity_curve:
        return Decimal("0")

    hwm = equity_curve[0]
    max_dd = Decimal("0")

    for equity in equity_curve:
        if equity > hwm:
            hwm = equity
        if hwm > 0:
            dd = (hwm - equity) / hwm * Decimal("100")
            if dd > max_dd:
                max_dd = dd

    return max_dd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_monthly_returns(
    equity_curve: List[EquityPoint],
) -> List[MonthlyReturn]:
    """
    Compute monthly returns from equity curve points.

    Groups equity points by (year, month), computes return per month as
    (last_equity - first_equity) / first_equity * 100.
    """
    if not equity_curve:
        return []

    # Group by (year, month)
    months: Dict[Tuple[int, int], List[EquityPoint]] = {}
    for pt in equity_curve:
        key = (pt.timestamp.year, pt.timestamp.month)
        if key not in months:
            months[key] = []
        months[key].append(pt)

    result: List[MonthlyReturn] = []
    sorted_keys = sorted(months.keys())

    # Track the equity at the start of each month
    prev_end_equity: Optional[Decimal] = None

    for year, month in sorted_keys:
        points = months[(year, month)]
        first_equity = (
            prev_end_equity if prev_end_equity is not None else points[0].equity
        )
        last_equity = points[-1].equity

        if first_equity != 0:
            ret = (last_equity - first_equity) / first_equity * Decimal("100")
        else:
            ret = Decimal("0")

        result.append(
            MonthlyReturn(
                year=year,
                month=month,
                return_pct=ret.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
        )
        prev_end_equity = last_equity

    return result


def compute_benchmark(
    btceur_candles: List[dict],
    xrpeur_candles: List[dict],
    initial_capital: Decimal,
    fee_rate: Decimal,
    start_index: int,
) -> Tuple[List[Decimal], BenchmarkResult]:
    """
    Compute 50/50 BTC/XRP HODL benchmark.

    Buys 50% BTC and 50% XRP at start_index close prices (with fee).
    Tracks mark-to-market at each candle from start_index onward.

    Returns:
        Tuple of (equity_list, BenchmarkResult)
    """
    if not btceur_candles or not xrpeur_candles:
        return [initial_capital], BenchmarkResult(
            return_pct=Decimal("0"),
            final_equity=initial_capital,
            sharpe_ratio=None,
        )

    # Ensure start_index is valid
    max_start = min(len(btceur_candles), len(xrpeur_candles)) - 1
    if start_index > max_start:
        return [initial_capital], BenchmarkResult(
            return_pct=Decimal("0"),
            final_equity=initial_capital,
            sharpe_ratio=None,
        )

    # Buy 50/50 at start_index close prices
    half_capital = initial_capital / Decimal("2")

    btc_price = btceur_candles[start_index]["close"]
    xrp_price = xrpeur_candles[start_index]["close"]

    if btc_price <= 0 or xrp_price <= 0:
        return [initial_capital], BenchmarkResult(
            return_pct=Decimal("0"),
            final_equity=initial_capital,
            sharpe_ratio=None,
        )

    # Buy with half_capital; fees are additional cost (not deducted from qty)
    btc_qty = half_capital / btc_price
    xrp_qty = half_capital / xrp_price

    # Track equity: value of holdings at each candle
    equities: List[Decimal] = []

    end_index = min(len(btceur_candles), len(xrpeur_candles))
    for i in range(start_index, end_index):
        btc_val = btc_qty * btceur_candles[i]["close"]
        xrp_val = xrp_qty * xrpeur_candles[i]["close"]
        equities.append(btc_val + xrp_val)

    if not equities:
        return [initial_capital], BenchmarkResult(
            return_pct=Decimal("0"),
            final_equity=initial_capital,
            sharpe_ratio=None,
        )

    final_equity = equities[-1]
    # Return is computed on initial capital (including fee drag)
    if initial_capital > 0:
        return_pct = (
            (final_equity - initial_capital) / initial_capital * Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    else:
        return_pct = Decimal("0")

    # Compute benchmark Sharpe from daily equity (using all equity points)
    sharpe = compute_sharpe_ratio(equities)

    return equities, BenchmarkResult(
        return_pct=return_pct,
        final_equity=final_equity.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        sharpe_ratio=sharpe,
    )


# ---------------------------------------------------------------------------
# Helper: compute returns from closes
# ---------------------------------------------------------------------------


def _compute_returns(closes: List[Decimal]) -> List[Decimal]:
    """Compute simple returns from a list of close prices."""
    returns: List[Decimal] = []
    for i in range(1, len(closes)):
        if closes[i - 1] != 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
        else:
            returns.append(Decimal("0"))
    return returns


# ---------------------------------------------------------------------------
# Helper: determine trading candle set by symbol
# ---------------------------------------------------------------------------


def _get_trading_candles(
    symbol: str,
    xrpbtc_candles: List[dict],
    btceur_candles: List[dict],
    xrpeur_candles: List[dict],
) -> List[dict]:
    """
    Determine which candle set to trade on based on symbol.

    BTCEUR trades on btceur_candles, XRPEUR on xrpeur_candles.
    XRPBTC and other symbols default to xrpbtc_candles.
    """
    symbol_upper = symbol.upper()
    if symbol_upper == "BTCEUR":
        return btceur_candles
    elif symbol_upper == "XRPEUR":
        return xrpeur_candles
    else:
        return xrpbtc_candles


# ---------------------------------------------------------------------------
# Helper: downsample equity curve to daily
# ---------------------------------------------------------------------------


def _downsample_to_daily(
    raw_points: List[EquityPoint],
) -> List[EquityPoint]:
    """
    Downsample equity curve to daily granularity.

    Takes the last equity point per day.
    """
    if not raw_points:
        return []

    daily: Dict[datetime, EquityPoint] = {}
    for pt in raw_points:
        day_key = datetime(pt.timestamp.year, pt.timestamp.month, pt.timestamp.day)
        daily[day_key] = EquityPoint(
            timestamp=day_key,
            equity=pt.equity,
            benchmark_equity=pt.benchmark_equity,
            drawdown_pct=pt.drawdown_pct,
        )

    return [daily[k] for k in sorted(daily.keys())]


# ---------------------------------------------------------------------------
# Main backtest simulation
# ---------------------------------------------------------------------------


def run_alpha_backtest(
    xrpbtc_candles: List[dict],
    btceur_candles: List[dict],
    xrpeur_candles: List[dict],
    config: BacktestConfig,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
) -> BacktestResult:
    """
    Run Alpha Score backtest simulation on historical candle data.

    Simulates long-only trading based on Alpha Score signals with trailing stop exits.
    Only Z-Score and Lead-Lag factors are used (orderbook + funding unavailable historically).

    Args:
        xrpbtc_candles: XRPBTC OHLCV candle dicts (for Z-Score computation)
        btceur_candles: BTCEUR OHLCV candle dicts (for Lead-Lag + benchmark)
        xrpeur_candles: XRPEUR OHLCV candle dicts (for benchmark)
        config: Backtest configuration
        progress_callback: Optional callback(candles_processed, candles_total, trades_found)
        cancel_event: Optional threading.Event for cancellation

    Returns:
        BacktestResult with trades, metrics, equity curve, benchmark
    """
    # Determine trading candle set
    trading_candles = _get_trading_candles(
        config.symbol,
        xrpbtc_candles,
        btceur_candles,
        xrpeur_candles,
    )

    candle_count = len(trading_candles)

    # Edge case: no data
    if candle_count == 0:
        return _empty_result(config, candle_count)

    warmup = compute_warmup_period(config)

    # Edge case: all candles within warmup
    if candle_count <= warmup:
        return _empty_result(
            config, candle_count, warmup=warmup, candles=trading_candles
        )

    # Timestamps
    data_start = trading_candles[0]["open_time"]
    data_end = trading_candles[-1]["open_time"]

    # Initialize state
    equity = config.initial_capital
    position: Optional[dict] = (
        None  # {entry_price, qty, entry_time, entry_idx, alpha_score, entry_fee, entry_slippage, stop_state}
    )
    trades: List[TradeRecord] = []
    raw_equity_points: List[EquityPoint] = []
    cancelled = False

    # Compute benchmark
    benchmark_equities, benchmark_result = compute_benchmark(
        btceur_candles,
        xrpeur_candles,
        config.initial_capital,
        config.fee_rate,
        start_index=warmup,
    )

    # High-water mark for drawdown
    hwm = equity

    # Progress throttle
    last_progress_idx = 0
    progress_interval = max(100, candle_count // 100)

    for i in range(warmup, candle_count):
        # Check cancellation
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break

        candle = trading_candles[i]

        # ---- Compute Alpha Score (degraded: Z-Score + Lead-Lag only) ----
        alpha_result = _compute_alpha_at_index(
            i,
            xrpbtc_candles,
            btceur_candles,
            config,
        )

        # ---- Compute ATR ----
        atr = compute_atr_standalone(trading_candles[: i + 1], period=config.atr_period)

        # ---- Position management ----
        if position is not None:
            # Update trailing stop
            if atr is not None:
                position["stop_state"] = update_trailing_stop(
                    position["stop_state"],
                    current_price=candle["close"],
                    current_atr=atr,
                    multiplier=config.atr_multiplier,
                    data_is_fresh=True,
                    now=candle["open_time"],
                )

            # Check stop hit
            stop_level = position["stop_state"].stop_level
            if stop_level is not None and candle["low"] <= stop_level:
                # Exit at stop level with slippage
                exit_price = stop_level * (Decimal("1") - config.slippage_pct)
                exit_slippage = stop_level * config.slippage_pct * position["qty"]
                exit_fee = exit_price * position["qty"] * config.fee_rate
                exit_proceeds = (
                    exit_price * position["qty"] * (Decimal("1") - config.fee_rate)
                )
                entry_cost = (
                    position["entry_price"]
                    * position["qty"]
                    * (Decimal("1") + config.fee_rate)
                )
                pnl = exit_proceeds - entry_cost

                total_fees = position["entry_fee"] + exit_fee
                total_slippage = position["entry_slippage"] + exit_slippage

                pnl_pct = (
                    (pnl / entry_cost * Decimal("100")).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                    if entry_cost > 0
                    else Decimal("0")
                )

                duration = i - position["entry_idx"]

                trade = TradeRecord(
                    entry_time=position["entry_time"],
                    exit_time=candle["open_time"],
                    entry_price=position["entry_price"],
                    exit_price=exit_price.quantize(
                        Decimal("0.00000001"), rounding=ROUND_HALF_UP
                    ),
                    qty=position["qty"],
                    pnl_eur=pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    pnl_pct=pnl_pct,
                    duration_candles=duration,
                    alpha_score_at_entry=position["alpha_score"],
                    fees_paid=total_fees.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                    slippage_cost=total_slippage.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                    is_open=False,
                )
                trades.append(trade)
                equity += pnl
                position = None

        elif alpha_result is not None and alpha_result.trade_signal == "LONG":
            # Open new position (long-only)
            if atr is not None:
                entry_price = candle["close"] * (Decimal("1") + config.slippage_pct)
                entry_slippage = candle["close"] * config.slippage_pct
                position_value = equity * config.position_fraction
                qty = position_value / entry_price
                entry_fee = entry_price * qty * config.fee_rate
                entry_slippage_total = entry_slippage * qty

                # Initialize trailing stop state
                initial_stop = TrailingStopState(
                    symbol=config.symbol,
                    stop_level=None,
                    atr_value=atr,
                    atr_distance=atr * config.atr_multiplier,
                    direction="long",
                    frozen=False,
                    frozen_since=None,
                    fresh_data_count=0,
                    resume_threshold=3,
                    last_price=entry_price,
                    last_updated=candle["open_time"],
                )
                # Update trailing stop to set initial level
                initial_stop = update_trailing_stop(
                    initial_stop,
                    current_price=entry_price,
                    current_atr=atr,
                    multiplier=config.atr_multiplier,
                    data_is_fresh=True,
                    now=candle["open_time"],
                )

                position = {
                    "entry_price": entry_price,
                    "qty": qty,
                    "entry_time": candle["open_time"],
                    "entry_idx": i,
                    "alpha_score": alpha_result.score,
                    "entry_fee": entry_fee,
                    "entry_slippage": entry_slippage_total,
                    "stop_state": initial_stop,
                }

        # ---- Record equity point ----
        if hwm < equity:
            hwm = equity
        dd_pct = (
            ((hwm - equity) / hwm * Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if hwm > 0
            else Decimal("0")
        )

        bench_idx = i - warmup
        bench_eq = (
            benchmark_equities[bench_idx]
            if bench_idx < len(benchmark_equities)
            else (
                benchmark_equities[-1] if benchmark_equities else config.initial_capital
            )
        )

        raw_equity_points.append(
            EquityPoint(
                timestamp=candle["open_time"],
                equity=equity.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                benchmark_equity=(
                    bench_eq.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if isinstance(bench_eq, Decimal)
                    else Decimal(str(bench_eq))
                ),
                drawdown_pct=dd_pct,
            )
        )

        # ---- Progress callback ----
        if progress_callback and (i - last_progress_idx) >= progress_interval:
            progress_callback(i - warmup, candle_count - warmup, len(trades))
            last_progress_idx = i

    # ---- Handle open trade at end ----
    open_trade: Optional[TradeRecord] = None
    if position is not None:
        open_trade = TradeRecord(
            entry_time=position["entry_time"],
            exit_time=None,
            entry_price=position["entry_price"],
            exit_price=None,
            qty=position["qty"],
            pnl_eur=None,
            pnl_pct=None,
            duration_candles=None,
            alpha_score_at_entry=position["alpha_score"],
            fees_paid=position["entry_fee"].quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            slippage_cost=position["entry_slippage"].quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            is_open=True,
        )
        trades.append(open_trade)

    # ---- Downsample equity curve to daily ----
    equity_curve = _downsample_to_daily(raw_equity_points)

    # ---- Compute metrics ----
    metrics = _compute_metrics(trades, equity, config.initial_capital, equity_curve)

    # ---- Monthly returns ----
    monthly = compute_monthly_returns(equity_curve)

    return BacktestResult(
        config=config,
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
        monthly_returns=monthly,
        warmup_end_index=warmup,
        data_start=data_start,
        data_end=data_end,
        candle_count=candle_count,
        benchmark=benchmark_result,
        open_trade=open_trade,
        cancelled=cancelled,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_result(
    config: BacktestConfig,
    candle_count: int,
    warmup: int = 0,
    candles: Optional[List[dict]] = None,
) -> BacktestResult:
    """Create an empty result for edge cases (no data or all warmup)."""
    data_start = candles[0]["open_time"] if candles else datetime(2000, 1, 1)
    data_end = candles[-1]["open_time"] if candles else datetime(2000, 1, 1)

    return BacktestResult(
        config=config,
        metrics=BacktestMetrics(
            net_return_pct=Decimal("0"),
            sharpe_ratio=None,
            max_drawdown_pct=Decimal("0"),
            trade_count=0,
            win_rate=None,
            total_fees=Decimal("0"),
            total_slippage=Decimal("0"),
            avg_trade_duration=None,
        ),
        trades=[],
        equity_curve=[],
        monthly_returns=[],
        warmup_end_index=warmup,
        data_start=data_start,
        data_end=data_end,
        candle_count=candle_count,
        benchmark=BenchmarkResult(
            return_pct=Decimal("0"),
            final_equity=config.initial_capital,
            sharpe_ratio=None,
        ),
        open_trade=None,
        cancelled=False,
    )


def _compute_alpha_at_index(
    i: int,
    xrpbtc_candles: List[dict],
    btceur_candles: List[dict],
    config: BacktestConfig,
) -> Optional[_AlphaScoreResult]:
    """
    Compute Alpha Score at candle index i using only Z-Score and Lead-Lag.

    Orderbook and Funding are marked as "unavailable" for graceful degradation.
    """
    # Extract close prices up to index i
    xrpbtc_closes = (
        [c["close"] for c in xrpbtc_candles[: i + 1]] if i < len(xrpbtc_candles) else []
    )
    btceur_closes = (
        [c["close"] for c in btceur_candles[: i + 1]] if i < len(btceur_candles) else []
    )

    if not xrpbtc_closes or not btceur_closes:
        return None

    # Compute Z-Score
    zscore_result = compute_zscore_mean_reversion(
        xrpbtc_closes,
        window=config.zscore_window,
    )

    # Compute Lead-Lag
    btc_returns = _compute_returns(btceur_closes)
    xrp_returns = _compute_returns(xrpbtc_closes)
    leadlag_result = compute_leadlag_momentum(
        btc_returns,
        xrp_returns,
        window=config.leadlag_window,
    )

    # Compute Hurst for regime detection
    hurst_result = compute_hurst_rs(
        xrpbtc_closes,
        trending_threshold=config.hurst_trending,
        reverting_threshold=config.hurst_reverting,
    )

    regime = RegimeInfo(
        hurst=hurst_result.hurst,
        regime=hurst_result.regime,
        confidence=hurst_result.confidence,
        zscore_weight_pct=config.weights.get("zscore", Decimal("0.40"))
        * Decimal("100"),
    )

    # Regime-adjusted weights
    adjusted_weights = compute_regime_adjusted_weights(
        config.weights,
        hurst_result.hurst,
        trending_threshold=config.hurst_trending,
        reverting_threshold=config.hurst_reverting,
    )

    # Build factors (orderbook + funding unavailable in backtest)
    factors = [
        AlphaFactorScore(
            name="zscore",
            sub_score=zscore_result.sub_score,
            raw_value=zscore_result.zscore,
            weight=adjusted_weights.get("zscore", Decimal("0.40")),
            base_weight=config.weights.get("zscore", Decimal("0.40")),
            quality=zscore_result.quality,
            description="Z-Score Mean Reversion",
        ),
        AlphaFactorScore(
            name="leadlag",
            sub_score=leadlag_result.sub_score,
            raw_value=leadlag_result.best_correlation,
            weight=adjusted_weights.get("leadlag", Decimal("0.30")),
            base_weight=config.weights.get("leadlag", Decimal("0.30")),
            quality=leadlag_result.quality,
            description="Lead-Lag Momentum",
        ),
        AlphaFactorScore(
            name="imbalance",
            sub_score=Decimal("0"),
            raw_value=None,
            weight=adjusted_weights.get("imbalance", Decimal("0.20")),
            base_weight=config.weights.get("imbalance", Decimal("0.20")),
            quality="unavailable",
            description="Orderbook Imbalance (unavailable in backtest)",
        ),
        AlphaFactorScore(
            name="funding",
            sub_score=Decimal("0"),
            raw_value=None,
            weight=adjusted_weights.get("funding", Decimal("0.10")),
            base_weight=config.weights.get("funding", Decimal("0.10")),
            quality="unavailable",
            description="Funding Rate (unavailable in backtest)",
        ),
    ]

    return compute_alpha_score(
        factors=factors,
        regime=regime,
        threshold=config.entry_threshold,
    )


def _compute_metrics(
    trades: List[TradeRecord],
    final_equity: Decimal,
    initial_capital: Decimal,
    equity_curve: List[EquityPoint],
) -> BacktestMetrics:
    """Compute aggregated performance metrics from trade list and equity curve."""
    closed_trades = [t for t in trades if not t.is_open]

    # Net return
    if initial_capital > 0:
        net_return_pct = (
            (final_equity - initial_capital) / initial_capital * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        net_return_pct = Decimal("0")

    # Sharpe from daily equities
    daily_equities = [pt.equity for pt in equity_curve]
    sharpe = compute_sharpe_ratio(daily_equities) if len(daily_equities) >= 2 else None

    # Max drawdown
    max_dd = compute_max_drawdown(daily_equities)

    # Trade count
    trade_count = len(trades)

    # Win rate
    if closed_trades:
        winners = sum(
            1 for t in closed_trades if t.pnl_eur is not None and t.pnl_eur > 0
        )
        win_rate = (
            Decimal(str(winners)) / Decimal(str(len(closed_trades))) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        win_rate = None

    # Total fees and slippage
    total_fees = sum((t.fees_paid for t in trades), Decimal("0"))
    total_slippage = sum((t.slippage_cost for t in trades), Decimal("0"))

    # Average trade duration
    durations = [
        t.duration_candles for t in closed_trades if t.duration_candles is not None
    ]
    if durations:
        avg_dur = Decimal(str(sum(durations))) / Decimal(str(len(durations)))
        avg_dur = avg_dur.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    else:
        avg_dur = None

    return BacktestMetrics(
        net_return_pct=net_return_pct,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd,
        trade_count=trade_count,
        win_rate=win_rate,
        total_fees=total_fees.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        total_slippage=total_slippage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        avg_trade_duration=avg_dur,
    )
