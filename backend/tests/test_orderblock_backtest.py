"""
Tests fuer Orderblock Backtest Engine.

Alle Tests verwenden synthetische Daten (kein I/O, kein DB).
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.orderblock import (
    Candle,
    ConvictionLevel,
    FairValueGap,
    OBConfig,
    OBDirection,
    OBState,
    Orderblock,
)
from app.domain.orderblock_backtest import (
    BacktestResult,
    BacktestTrade,
    TradeOutcome,
    _compute_zscore_clusters,
    _mean_decimal,
    _median_decimal,
    compute_backtest_metrics,
    run_backtest,
    simulate_zone_approach,
)

BASE_TIME = datetime(2024, 1, 1, 0, 0, 0)


def _make_candle(
    index: int,
    o: str,
    h: str,
    low: str,
    c: str,
    v: str = "100",
) -> Candle:
    return Candle(
        timestamp=BASE_TIME + timedelta(hours=index),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(v),
    )


def _make_test_ob(
    direction: OBDirection = OBDirection.BULLISH,
    zone_top: str = "100",
    zone_bottom: str = "90",
    confirmed_at_index: int = 5,
    conviction: ConvictionLevel = ConvictionLevel.STANDARD,
    volume_zscore: str = "1.5",
) -> Orderblock:
    zt = Decimal(zone_top)
    zb = Decimal(zone_bottom)
    return Orderblock(
        id="ob_test_1",
        direction=direction,
        zone_top=zt,
        zone_bottom=zb,
        equilibrium=(zt + zb) / Decimal("2"),
        entry_edge=zt if direction == OBDirection.BULLISH else zb,
        stop_edge=zb if direction == OBDirection.BULLISH else zt,
        formed_at=BASE_TIME + timedelta(hours=3),
        confirmed_at=BASE_TIME + timedelta(hours=confirmed_at_index),
        formed_at_index=3,
        confirmed_at_index=confirmed_at_index,
        state=OBState.UNMITIGATED,
        conviction=conviction,
        volume_zscore=Decimal(volume_zscore),
        volume_weight=Decimal("2.0"),
        fvg=FairValueGap(
            index=4,
            timestamp=BASE_TIME + timedelta(hours=4),
            gap_top=Decimal("95"),
            gap_bottom=Decimal("92"),
            direction=direction,
        ),
        atr_at_formation=Decimal("5"),
        displacement_range=Decimal("15"),
        bos_swing_price=Decimal("105"),
        config=OBConfig(),
    )


# ===========================================================================
# TestMedianMean
# ===========================================================================


class TestMedianMean:
    def test_mean_empty(self):
        assert _mean_decimal([]) == Decimal("0")

    def test_mean_single(self):
        assert _mean_decimal([Decimal("10")]) == Decimal("10")

    def test_mean_multiple(self):
        result = _mean_decimal([Decimal("10"), Decimal("20"), Decimal("30")])
        assert result == Decimal("20")

    def test_median_empty(self):
        assert _median_decimal([]) == Decimal("0")

    def test_median_odd(self):
        result = _median_decimal([Decimal("3"), Decimal("1"), Decimal("2")])
        assert result == Decimal("2")

    def test_median_even(self):
        result = _median_decimal(
            [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        )
        assert result == Decimal("2.5")

    def test_median_single(self):
        assert _median_decimal([Decimal("42")]) == Decimal("42")


# ===========================================================================
# TestSimulateZoneApproach
# ===========================================================================


class TestSimulateZoneApproach:
    def test_hit_before_stop(self):
        """Preis beruehrt Zone, prallt ab und trifft Target -> HIT."""
        ob = _make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        # Target = 100 + 2.0 * (100-90) = 120
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),  # confirmed
            _make_candle(
                3, "119", "121", "98", "99"
            ),  # Low=98 <= entry_edge=100 -> ENTRY
            _make_candle(
                4, "99", "105", "95", "103"
            ),  # Low=95 > stop=90, High=105 < 120
            _make_candle(
                5, "103", "125", "101", "122"
            ),  # High=125 >= target=120 -> HIT
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.HIT
        assert trade.entry_timestamp == candles[3].timestamp
        assert trade.exit_timestamp == candles[5].timestamp

    def test_stop_before_hit(self):
        """Preis beruehrt Zone, bricht durch Stop -> MISS."""
        ob = _make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),  # confirmed
            _make_candle(3, "119", "121", "98", "99"),  # ENTRY (Low=98 <= 100)
            _make_candle(4, "99", "102", "85", "87"),  # Low=85 <= stop=90 -> MISS
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.MISS

    def test_never_touched(self):
        """Zone wird nie beruehrt -> None."""
        ob = _make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        config = OBConfig()
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),
            _make_candle(3, "119", "121", "110", "115"),  # Low=110 > entry_edge=100
            _make_candle(4, "115", "118", "112", "116"),
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is None

    def test_same_candle_stop_and_target_is_miss(self):
        """Bei gleichzeitigem Stop und Target in gleicher Kerze -> MISS (konservativ)."""
        ob = _make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        # Target = 100 + 2.0 * 10 = 120
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),
            _make_candle(3, "119", "121", "98", "99"),  # ENTRY
            _make_candle(
                4, "99", "130", "80", "110"
            ),  # Low=80<=90 (STOP) AND High=130>=120 (TARGET) -> MISS
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.MISS

    def test_bearish_hit(self):
        """Bearish OB: Preis steigt zur Zone, prallt ab und faellt -> HIT."""
        ob = _make_test_ob(
            direction=OBDirection.BEARISH,
            zone_top="210",
            zone_bottom="200",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        # entry_edge = 200 (bottom fuer bearish), stop_edge = 210 (top)
        # Target = 200 - 2.0 * (210-200) = 180
        candles = [
            _make_candle(0, "180", "185", "175", "182"),
            _make_candle(1, "182", "184", "178", "180"),
            _make_candle(2, "180", "183", "176", "179"),  # confirmed
            _make_candle(
                3, "179", "202", "177", "198"
            ),  # High=202 >= entry=200 -> ENTRY
            _make_candle(4, "198", "205", "190", "192"),  # High=205 < stop=210
            _make_candle(5, "192", "195", "175", "178"),  # Low=175 <= target=180 -> HIT
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.HIT

    def test_bearish_miss(self):
        """Bearish OB: Preis bricht ueber Stop -> MISS."""
        ob = _make_test_ob(
            direction=OBDirection.BEARISH,
            zone_top="210",
            zone_bottom="200",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        candles = [
            _make_candle(0, "180", "185", "175", "182"),
            _make_candle(1, "182", "184", "178", "180"),
            _make_candle(2, "180", "183", "176", "179"),
            _make_candle(3, "179", "202", "177", "198"),  # ENTRY
            _make_candle(4, "198", "215", "195", "212"),  # High=215 >= stop=210 -> MISS
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.MISS

    def test_open_trade_at_end_of_data(self):
        """Ende der Daten ohne Ergebnis -> OPEN."""
        ob = _make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),
            _make_candle(3, "119", "121", "98", "99"),  # ENTRY
            _make_candle(4, "99", "105", "95", "103"),  # Weder Stop noch Target
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.OPEN
        assert trade.exit_timestamp is None

    def test_penetration_depth_calculation(self):
        """Penetration Depth korrekt berechnet."""
        ob = _make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),
            _make_candle(3, "119", "121", "98", "99"),  # ENTRY at 100
            _make_candle(4, "99", "105", "95", "103"),  # Min low = 95
            _make_candle(5, "103", "125", "101", "122"),  # HIT
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        # pen_depth = (entry=100 - min_low=95) / (entry=100 - stop=90) * 100 = 5/10*100 = 50%
        assert trade.penetration_depth_pct == Decimal("50")

    def test_holding_duration(self):
        """Holding Duration in Kerzen korrekt."""
        ob = _make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),
            _make_candle(3, "119", "121", "98", "99"),  # ENTRY (idx 3)
            _make_candle(4, "99", "105", "95", "103"),
            _make_candle(5, "103", "110", "101", "108"),
            _make_candle(6, "108", "125", "106", "122"),  # HIT (idx 6), holding = 3
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.holding_duration_candles == 3

    def test_confirmed_at_out_of_bounds(self):
        """confirmed_at_index >= len(candles) -> None."""
        ob = _make_test_ob(confirmed_at_index=100)
        candles = [_make_candle(i, "100", "101", "99", "100") for i in range(5)]
        config = OBConfig()
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is None


# ===========================================================================
# TestComputeBacktestMetrics
# ===========================================================================


class TestComputeBacktestMetrics:
    def _make_trade(
        self,
        outcome: TradeOutcome,
        pen_depth: str = "50",
        holding: int = 5,
        conviction: ConvictionLevel = ConvictionLevel.STANDARD,
        zscore: str = "1.0",
    ) -> BacktestTrade:
        return BacktestTrade(
            ob_id="ob_test",
            direction=OBDirection.BULLISH,
            entry_edge=Decimal("100"),
            stop_edge=Decimal("90"),
            target=Decimal("120"),
            entry_price=Decimal("100"),
            entry_timestamp=BASE_TIME,
            exit_timestamp=(
                BASE_TIME + timedelta(hours=holding)
                if outcome != TradeOutcome.OPEN
                else None
            ),
            outcome=outcome,
            penetration_depth_pct=Decimal(pen_depth),
            holding_duration_candles=holding,
            min_adverse_price=Decimal("95"),
            conviction=conviction,
            volume_zscore=Decimal(zscore),
            conviction_score=Decimal("50"),
        )

    def test_hit_rate_calculation(self):
        trades = [
            self._make_trade(TradeOutcome.HIT),
            self._make_trade(TradeOutcome.HIT),
            self._make_trade(TradeOutcome.MISS),
        ]
        zones = [_make_test_ob() for _ in range(3)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert metrics.hit_rate == Decimal("2") / Decimal("3")
        assert metrics.hits == 2
        assert metrics.misses == 1

    def test_no_trades_hit_rate_none(self):
        metrics = compute_backtest_metrics(
            [], [], 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert metrics.hit_rate is None
        assert metrics.total_trades == 0

    def test_open_trades_excluded_from_hit_rate(self):
        trades = [
            self._make_trade(TradeOutcome.HIT),
            self._make_trade(TradeOutcome.OPEN),
            self._make_trade(TradeOutcome.OPEN),
        ]
        zones = [_make_test_ob() for _ in range(3)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        # Hit Rate: 1 / 1 (nur abgeschlossene)
        assert metrics.hit_rate == Decimal("1")
        assert metrics.open_trades == 2

    def test_avg_penetration(self):
        trades = [
            self._make_trade(TradeOutcome.HIT, pen_depth="30"),
            self._make_trade(TradeOutcome.MISS, pen_depth="70"),
        ]
        zones = [_make_test_ob() for _ in range(2)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert metrics.avg_penetration_depth_pct == Decimal("50")

    def test_median_penetration(self):
        trades = [
            self._make_trade(TradeOutcome.HIT, pen_depth="10"),
            self._make_trade(TradeOutcome.HIT, pen_depth="50"),
            self._make_trade(TradeOutcome.MISS, pen_depth="90"),
        ]
        zones = [_make_test_ob() for _ in range(3)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert metrics.median_penetration_depth_pct == Decimal("50")

    def test_conviction_breakdown(self):
        trades = [
            self._make_trade(
                TradeOutcome.HIT, conviction=ConvictionLevel.HIGH
            ),
            self._make_trade(
                TradeOutcome.MISS, conviction=ConvictionLevel.HIGH
            ),
            self._make_trade(TradeOutcome.HIT, conviction=ConvictionLevel.STANDARD),
        ]
        zones = [_make_test_ob() for _ in range(3)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        # Backward-compat: HIGH maps to high_conviction
        assert metrics.high_conviction_count == 2
        assert metrics.high_conviction_hit_rate == Decimal("1") / Decimal("2")
        # STANDARD + LOW -> standard_conviction
        assert metrics.standard_conviction_hit_rate == Decimal("1")
        # 4-Level Breakdown
        assert len(metrics.conviction_breakdown) == 4
        high_bd = next(b for b in metrics.conviction_breakdown if b.level == "HIGH")
        assert high_bd.count == 2
        assert high_bd.hits == 1
        assert high_bd.misses == 1

    def test_zones_per_month(self):
        zones = [_make_test_ob() for _ in range(6)]
        metrics = compute_backtest_metrics(
            [], zones, 100, BASE_TIME, BASE_TIME + timedelta(days=90)
        )
        # 6 Zones / 3 Monate = 2
        assert metrics.zones_per_month == Decimal("2")

    def test_state_distribution(self):
        zones = [
            _make_test_ob(),  # UNMITIGATED
            Orderblock(
                **{**_make_test_ob().__dict__, "id": "ob2", "state": OBState.MITIGATED}
            ),
            Orderblock(
                **{**_make_test_ob().__dict__, "id": "ob3", "state": OBState.INVALID}
            ),
            Orderblock(
                **{**_make_test_ob().__dict__, "id": "ob4", "state": OBState.INVALID}
            ),
        ]
        metrics = compute_backtest_metrics(
            [], zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert metrics.unmitigated_count == 1
        assert metrics.mitigated_count == 1
        assert metrics.invalid_count == 2


# ===========================================================================
# TestZScoreClusters
# ===========================================================================


class TestZScoreClusters:
    def _make_trade(self, outcome: TradeOutcome, zscore: str) -> BacktestTrade:
        return BacktestTrade(
            ob_id="ob_test",
            direction=OBDirection.BULLISH,
            entry_edge=Decimal("100"),
            stop_edge=Decimal("90"),
            target=Decimal("120"),
            entry_price=Decimal("100"),
            entry_timestamp=BASE_TIME,
            exit_timestamp=BASE_TIME + timedelta(hours=1),
            outcome=outcome,
            penetration_depth_pct=Decimal("50"),
            holding_duration_candles=5,
            min_adverse_price=Decimal("95"),
            conviction=ConvictionLevel.STANDARD,
            volume_zscore=Decimal(zscore),
            conviction_score=Decimal("50"),
        )

    def test_empty_trades(self):
        clusters = _compute_zscore_clusters([])
        assert clusters == []

    def test_single_cluster(self):
        trades = [
            self._make_trade(TradeOutcome.HIT, "1.2"),
            self._make_trade(TradeOutcome.MISS, "1.3"),
        ]
        clusters = _compute_zscore_clusters(trades, bucket_width=Decimal("0.5"))
        assert len(clusters) >= 1
        # Beide Trades im selben Bucket [1.0, 1.5)
        bucket = [c for c in clusters if c.range_low <= Decimal("1.2") < c.range_high]
        assert len(bucket) == 1
        assert bucket[0].count == 2
        assert bucket[0].hits == 1
        assert bucket[0].misses == 1

    def test_multiple_clusters(self):
        trades = [
            self._make_trade(TradeOutcome.HIT, "1.0"),
            self._make_trade(TradeOutcome.HIT, "2.5"),
            self._make_trade(TradeOutcome.MISS, "3.0"),
        ]
        clusters = _compute_zscore_clusters(trades, bucket_width=Decimal("1.0"))
        assert len(clusters) >= 2  # Mindestens 2 verschiedene Buckets


# ===========================================================================
# TestRunBacktest (Integration)
# ===========================================================================


class TestRunBacktest:
    def test_end_to_end_with_flat_data(self):
        """Flache Daten -> keine OBs, leere Ergebnisse."""
        candles = []
        for i in range(50):
            candles.append(_make_candle(i, "100", "102", "98", "100"))
        config = OBConfig(atr_length=20, swing_fractal_n=2)
        result = run_backtest(candles, config)
        assert isinstance(result, BacktestResult)
        assert result.metrics.total_zones == 0
        assert result.metrics.total_trades == 0
        assert result.candle_count == 50

    def test_result_structure(self):
        """BacktestResult hat alle erwarteten Felder."""
        candles = []
        for i in range(50):
            candles.append(_make_candle(i, "100", "102", "98", "100"))
        result = run_backtest(candles, OBConfig(atr_length=20))
        assert hasattr(result, "metrics")
        assert hasattr(result, "trades")
        assert hasattr(result, "zones")
        assert hasattr(result, "config")
        assert result.symbol == "BTCEUR"
        assert result.timeframe == "1h"

    def test_data_start_end(self):
        """data_start und data_end korrekt gesetzt."""
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(50)]
        result = run_backtest(candles, OBConfig(atr_length=20))
        assert result.data_start == candles[0].timestamp
        assert result.data_end == candles[-1].timestamp

    def test_empty_candles(self):
        """Leere Candles -> leeres Ergebnis."""
        result = run_backtest([], OBConfig())
        assert result.metrics.total_zones == 0
        assert result.candle_count == 0

    def test_deterministic(self):
        """Gleiche Eingabe -> gleiche Ausgabe."""
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(50)]
        config = OBConfig(atr_length=20)
        r1 = run_backtest(candles, config)
        r2 = run_backtest(candles, config)
        assert r1.metrics.total_zones == r2.metrics.total_zones
        assert r1.metrics.total_trades == r2.metrics.total_trades
        assert len(r1.trades) == len(r2.trades)


# ===========================================================================
# TestTripleBarrier (Enhancement 3: Lopez de Prado)
# ===========================================================================


class TestTripleBarrier:
    """Tests fuer Triple Barrier / max_holding_candles Zeitlimit."""

    def test_expired_before_hit_or_stop(self):
        """Trade ueberschreitet max_holding -> EXPIRED."""
        ob = _make_test_ob(confirmed_at_index=5)
        # Kerzen: 0-5 Flat, 6=Entry (Low=100 beruehrt entry_edge=100),
        # dann nur Kerzen die weder Stop noch Target beruehren
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(6)]
        # Kerze 6: Entry (low=99 <= entry_edge=100)
        candles.append(_make_candle(6, "101", "102", "99", "101"))
        # 15 Kerzen: Preis bleibt im Bereich (kein Stop=90, kein Target)
        for i in range(7, 22):
            candles.append(_make_candle(i, "101", "102", "99", "101"))

        config = OBConfig(max_holding_candles=10, target_rr=Decimal("2.0"))
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.EXPIRED

    def test_hit_before_expiry(self):
        """Target erreicht vor max_holding -> HIT, nicht EXPIRED."""
        ob = _make_test_ob(confirmed_at_index=5)
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(6)]
        # Kerze 6: Entry
        candles.append(_make_candle(6, "101", "102", "99", "101"))
        # Kerze 7: Target (zone_width=10, target_rr=2 -> target=120)
        candles.append(_make_candle(7, "110", "125", "109", "120"))

        config = OBConfig(max_holding_candles=100, target_rr=Decimal("2.0"))
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.HIT

    def test_stop_before_expiry(self):
        """Stop erreicht vor max_holding -> MISS, nicht EXPIRED."""
        ob = _make_test_ob(confirmed_at_index=5)
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(6)]
        # Kerze 6: Entry
        candles.append(_make_candle(6, "101", "102", "99", "101"))
        # Kerze 7: Stop (low=89 <= stop_edge=90)
        candles.append(_make_candle(7, "95", "96", "89", "91"))

        config = OBConfig(max_holding_candles=100, target_rr=Decimal("2.0"))
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.MISS

    def test_max_holding_zero_disables_barrier(self):
        """max_holding_candles=0 -> kein Zeitlimit, Trade bleibt OPEN."""
        ob = _make_test_ob(confirmed_at_index=5)
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(6)]
        # Kerze 6: Entry
        candles.append(_make_candle(6, "101", "102", "99", "101"))
        # 5 Kerzen: kein Stop, kein Target
        for i in range(7, 12):
            candles.append(_make_candle(i, "101", "102", "99", "101"))

        config = OBConfig(max_holding_candles=0, target_rr=Decimal("2.0"))
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.OPEN

    def test_expired_excluded_from_hit_rate(self):
        """EXPIRED-Trades zaehlen nicht in der Hit-Rate."""
        trades = [
            BacktestTrade(
                ob_id="ob1", direction=OBDirection.BULLISH,
                entry_edge=Decimal("100"), stop_edge=Decimal("90"),
                target=Decimal("120"), entry_price=Decimal("100"),
                entry_timestamp=BASE_TIME,
                exit_timestamp=BASE_TIME + timedelta(hours=5),
                outcome=TradeOutcome.HIT,
                penetration_depth_pct=Decimal("30"),
                holding_duration_candles=5,
                min_adverse_price=Decimal("95"),
                conviction=ConvictionLevel.STANDARD,
                volume_zscore=Decimal("1.0"),
                conviction_score=Decimal("40"),
            ),
            BacktestTrade(
                ob_id="ob2", direction=OBDirection.BULLISH,
                entry_edge=Decimal("100"), stop_edge=Decimal("90"),
                target=Decimal("120"), entry_price=Decimal("100"),
                entry_timestamp=BASE_TIME,
                exit_timestamp=BASE_TIME + timedelta(hours=200),
                outcome=TradeOutcome.EXPIRED,
                penetration_depth_pct=Decimal("50"),
                holding_duration_candles=200,
                min_adverse_price=Decimal("95"),
                conviction=ConvictionLevel.STANDARD,
                volume_zscore=Decimal("1.0"),
                conviction_score=Decimal("40"),
            ),
        ]
        zones = [_make_test_ob(), _make_test_ob()]
        metrics = compute_backtest_metrics(
            trades, zones, 300, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert metrics.hit_rate == Decimal("1")  # 1/1 (EXPIRED ausgeschlossen)
        assert metrics.expired_trades == 1

    def test_holding_duration_on_expiry(self):
        """Holding-Duration korrekt bei EXPIRED Trade."""
        ob = _make_test_ob(confirmed_at_index=5)
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(6)]
        candles.append(_make_candle(6, "101", "102", "99", "101"))
        for i in range(7, 30):
            candles.append(_make_candle(i, "101", "102", "99", "101"))

        config = OBConfig(max_holding_candles=10, target_rr=Decimal("2.0"))
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.EXPIRED
        assert trade.holding_duration_candles == 11  # 1 ueber Limit


# ===========================================================================
# TestConvictionBreakdown4Level
# ===========================================================================


class TestConvictionBreakdown4Level:
    """Tests fuer 4-Level Conviction Breakdown."""

    def _make_trade(
        self,
        outcome: TradeOutcome,
        conviction: ConvictionLevel = ConvictionLevel.STANDARD,
    ) -> BacktestTrade:
        return BacktestTrade(
            ob_id="ob_test",
            direction=OBDirection.BULLISH,
            entry_edge=Decimal("100"),
            stop_edge=Decimal("90"),
            target=Decimal("120"),
            entry_price=Decimal("100"),
            entry_timestamp=BASE_TIME,
            exit_timestamp=(
                BASE_TIME + timedelta(hours=5)
                if outcome != TradeOutcome.OPEN
                else None
            ),
            outcome=outcome,
            penetration_depth_pct=Decimal("50"),
            holding_duration_candles=5,
            min_adverse_price=Decimal("95"),
            conviction=conviction,
            volume_zscore=Decimal("1.0"),
            conviction_score=Decimal("50"),
        )

    def test_four_level_breakdown_all_present(self):
        """Alle 4 Levels korrekt gezaehlt."""
        trades = [
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.LOW),
            self._make_trade(TradeOutcome.MISS, ConvictionLevel.STANDARD),
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.HIGH),
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.INSTITUTIONAL),
        ]
        zones = [_make_test_ob() for _ in range(4)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert len(metrics.conviction_breakdown) == 4
        levels = {b.level: b for b in metrics.conviction_breakdown}
        assert levels["LOW"].count == 1
        assert levels["LOW"].hits == 1
        assert levels["STANDARD"].count == 1
        assert levels["STANDARD"].misses == 1
        assert levels["HIGH"].count == 1
        assert levels["INSTITUTIONAL"].count == 1

    def test_empty_level_shows_zeros(self):
        """Level ohne Trades -> count=0, hit_rate=None."""
        trades = [
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.HIGH),
        ]
        zones = [_make_test_ob()]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        levels = {b.level: b for b in metrics.conviction_breakdown}
        assert levels["LOW"].count == 0
        assert levels["LOW"].hit_rate is None
        assert levels["INSTITUTIONAL"].count == 0

    def test_backward_compat_high_conviction_fields(self):
        """high_conviction_count/hit_rate = HIGH + INSTITUTIONAL kombiniert."""
        trades = [
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.HIGH),
            self._make_trade(TradeOutcome.MISS, ConvictionLevel.HIGH),
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.INSTITUTIONAL),
        ]
        zones = [_make_test_ob() for _ in range(3)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        # HIGH(2) + INSTITUTIONAL(1) = 3
        assert metrics.high_conviction_count == 3
        # Hits: HIGH=1 + INST=1 = 2, Closed: 3
        assert metrics.high_conviction_hit_rate == Decimal("2") / Decimal("3")


# ===========================================================================
# TestBearishPenetrationDepth
# ===========================================================================


class TestBearishPenetrationDepth:
    """Penetration Depth Berechnung fuer Bearish OBs."""

    def test_bearish_penetration_depth(self):
        """Bearish: pen = (max_high - entry) / (stop - entry) * 100."""
        ob = _make_test_ob(
            direction=OBDirection.BEARISH,
            zone_top="210",
            zone_bottom="200",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        # entry=200, stop=210, target=200 - 2*10 = 180
        candles = [
            _make_candle(0, "180", "185", "175", "182"),
            _make_candle(1, "182", "184", "178", "180"),
            _make_candle(2, "180", "183", "176", "179"),  # confirmed
            _make_candle(3, "179", "202", "177", "198"),  # ENTRY at 200
            _make_candle(4, "198", "205", "190", "192"),  # max high = 205
            _make_candle(5, "192", "195", "175", "178"),  # HIT (Low <= 180)
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        assert trade.outcome == TradeOutcome.HIT
        # pen = (205 - 200) / (210 - 200) * 100 = 50%
        assert trade.penetration_depth_pct == Decimal("50")

    def test_bearish_no_penetration(self):
        """Bearish Trade ohne Adverse-Bewegung -> pen_depth = 0."""
        ob = _make_test_ob(
            direction=OBDirection.BEARISH,
            zone_top="210",
            zone_bottom="200",
            confirmed_at_index=2,
        )
        config = OBConfig(target_rr=Decimal("2.0"))
        candles = [
            _make_candle(0, "180", "185", "175", "182"),
            _make_candle(1, "182", "184", "178", "180"),
            _make_candle(2, "180", "183", "176", "179"),
            _make_candle(3, "179", "200", "177", "198"),  # ENTRY exactly at 200
            _make_candle(4, "198", "199", "175", "178"),  # HIT, max_high=199 < entry=200
        ]
        trade = simulate_zone_approach(ob, candles, config)
        assert trade is not None
        # max_high=199, entry=200 -> penetration = (199-200)/(210-200) -> negative, clamped to 0
        assert trade.penetration_depth_pct == Decimal("0")


# ===========================================================================
# TestIntegrationDetectAndSimulate
# ===========================================================================


class TestIntegrationDetectAndSimulate:
    """End-to-end: Detection + Backtest mit synthetischem OB-Szenario."""

    def _build_scenario_with_hit(self) -> list:
        """
        Szenario: Bullish OB, Preis entfernt sich, kommt zurueck, Hit.
        ~60 Kerzen fuer realistischere Sequenz.
        """
        candles = []

        # 0-17: Flache Kerzen (ATR-Basis, Spread 2)
        for i in range(18):
            candles.append(_make_candle(i, "100", "102", "98", "100"))

        # 18-22: Aufwaertsbewegung -> Swing High bei 20 (bestaetigt bei 22 mit n=2)
        candles.append(_make_candle(18, "100", "104", "99", "103"))
        candles.append(_make_candle(19, "103", "106", "101", "105"))
        candles.append(_make_candle(20, "105", "115", "104", "112"))  # Swing High = 115
        candles.append(_make_candle(21, "112", "113", "103", "105"))
        candles.append(_make_candle(22, "105", "110", "100", "103"))  # Swing confirmed

        # 23-24: Abwaertsbewegung
        candles.append(_make_candle(23, "103", "104", "96", "97"))
        candles.append(_make_candle(24, "97", "98", "90", "91"))

        # 25: BEARISH BASE (Bullish OB Candidate)
        candles.append(_make_candle(25, "91", "93", "85", "86"))

        # 26-28: DISPLACEMENT + BOS + FVG
        candles.append(_make_candle(26, "86", "100", "85", "99", "500"))
        candles.append(_make_candle(27, "99", "120", "98", "118", "500"))
        candles.append(_make_candle(28, "118", "125", "116", "122", "500"))

        # 29-40: Preis bleibt hoch (ueber OB Zone)
        for i in range(29, 41):
            candles.append(_make_candle(i, "120", "125", "118", "122"))

        # 41-45: Preis faellt zurueck zur Zone (Entry bei ~93 = zone_top)
        candles.append(_make_candle(41, "122", "123", "110", "112"))
        candles.append(_make_candle(42, "112", "114", "100", "102"))
        candles.append(_make_candle(43, "102", "104", "92", "94"))  # Low=92 <= zone_top=93 -> ENTRY

        # 44-48: Bounce -> Target Hit
        candles.append(_make_candle(44, "94", "105", "91", "103"))
        candles.append(_make_candle(45, "103", "115", "101", "112"))
        # Target = 93 + 2*(93-85) = 93+16 = 109. High=115 >= 109 -> already hit at 45
        candles.append(_make_candle(46, "112", "120", "110", "118"))

        return candles

    def test_full_cycle_detect_and_simulate(self):
        """Vollstaendiger Zyklus: detect -> state update -> simulate -> metrics."""
        candles = self._build_scenario_with_hit()
        config = OBConfig(atr_length=20, swing_fractal_n=2, target_rr=Decimal("2.0"))
        result = run_backtest(candles, config)

        assert result.candle_count == len(candles)
        assert result.metrics.total_zones >= 1
        # Mindestens ein Trade mit HIT oder MISS
        if result.metrics.total_trades > 0:
            assert result.metrics.hits + result.metrics.misses + result.metrics.open_trades + result.metrics.expired_trades == result.metrics.total_trades

    def test_full_cycle_deterministic(self):
        """Gleiche Candles -> identische Ergebnisse (Determinismus)."""
        candles = self._build_scenario_with_hit()
        config = OBConfig(atr_length=20, swing_fractal_n=2)
        r1 = run_backtest(candles, config)
        r2 = run_backtest(candles, config)

        assert r1.metrics.total_zones == r2.metrics.total_zones
        assert r1.metrics.total_trades == r2.metrics.total_trades
        assert r1.metrics.hits == r2.metrics.hits
        assert r1.metrics.misses == r2.metrics.misses
        assert len(r1.trades) == len(r2.trades)
        for t1, t2 in zip(r1.trades, r2.trades):
            assert t1.ob_id == t2.ob_id
            assert t1.outcome == t2.outcome
            assert t1.penetration_depth_pct == t2.penetration_depth_pct

    def test_zones_have_correct_states_after_backtest(self):
        """Nach Backtest: Zonen-States korrekt aktualisiert."""
        candles = self._build_scenario_with_hit()
        config = OBConfig(atr_length=20, swing_fractal_n=2)
        result = run_backtest(candles, config)

        for zone in result.zones:
            # Jede Zone muss einen gueltigen State haben
            assert zone.state in (OBState.UNMITIGATED, OBState.MITIGATED, OBState.INVALID)
            # confirmed_at >= formed_at
            assert zone.confirmed_at >= zone.formed_at

    def test_no_look_ahead_bias(self):
        """OBs duerfen nur ab confirmed_at als Zone gelten."""
        candles = self._build_scenario_with_hit()
        config = OBConfig(atr_length=20, swing_fractal_n=2)
        result = run_backtest(candles, config)

        for trade in result.trades:
            # Entry darf nicht vor confirmed_at passieren
            zone = next(z for z in result.zones if z.id == trade.ob_id)
            assert trade.entry_timestamp >= zone.confirmed_at


# ===========================================================================
# TestMetricsWithExpiredAndAllConvictions
# ===========================================================================


class TestMetricsWithExpiredAndAllConvictions:
    """Metriken korrekt bei Mix aus HIT, MISS, OPEN, EXPIRED ueber alle Conviction Levels."""

    def _make_trade(
        self,
        outcome: TradeOutcome,
        conviction: ConvictionLevel = ConvictionLevel.STANDARD,
        pen_depth: str = "30",
        holding: int = 5,
    ) -> BacktestTrade:
        return BacktestTrade(
            ob_id="ob_test",
            direction=OBDirection.BULLISH,
            entry_edge=Decimal("100"),
            stop_edge=Decimal("90"),
            target=Decimal("120"),
            entry_price=Decimal("100"),
            entry_timestamp=BASE_TIME,
            exit_timestamp=(
                BASE_TIME + timedelta(hours=holding)
                if outcome not in (TradeOutcome.OPEN,)
                else None
            ),
            outcome=outcome,
            penetration_depth_pct=Decimal(pen_depth),
            holding_duration_candles=holding,
            min_adverse_price=Decimal("95"),
            conviction=conviction,
            volume_zscore=Decimal("1.0"),
            conviction_score=Decimal("50"),
        )

    def test_all_outcomes_all_convictions(self):
        """Mix aller Outcome/Conviction Kombinationen."""
        trades = [
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.LOW),
            self._make_trade(TradeOutcome.MISS, ConvictionLevel.LOW),
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.STANDARD),
            self._make_trade(TradeOutcome.EXPIRED, ConvictionLevel.STANDARD),
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.HIGH),
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.HIGH),
            self._make_trade(TradeOutcome.MISS, ConvictionLevel.HIGH),
            self._make_trade(TradeOutcome.OPEN, ConvictionLevel.INSTITUTIONAL),
            self._make_trade(TradeOutcome.HIT, ConvictionLevel.INSTITUTIONAL),
        ]
        zones = [_make_test_ob() for _ in range(9)]
        metrics = compute_backtest_metrics(
            trades, zones, 500, BASE_TIME, BASE_TIME + timedelta(days=90)
        )

        assert metrics.total_trades == 9
        assert metrics.hits == 5  # LOW:1, STD:1, HIGH:2, INST:1
        assert metrics.misses == 2  # LOW:1, HIGH:1
        assert metrics.open_trades == 1
        assert metrics.expired_trades == 1

        # Hit Rate: 5 / (5+2) = 5/7 (OPEN + EXPIRED ausgeschlossen)
        assert metrics.hit_rate == Decimal("5") / Decimal("7")

        # Conviction Breakdown: Alle 4 Levels vorhanden
        assert len(metrics.conviction_breakdown) == 4
        levels = {b.level: b for b in metrics.conviction_breakdown}
        assert levels["LOW"].count == 2
        assert levels["LOW"].hits == 1
        assert levels["LOW"].misses == 1
        assert levels["STANDARD"].count == 2
        assert levels["STANDARD"].hits == 1
        assert levels["STANDARD"].expired == 1
        assert levels["HIGH"].count == 3
        assert levels["HIGH"].hits == 2
        assert levels["HIGH"].misses == 1
        assert levels["INSTITUTIONAL"].count == 2
        assert levels["INSTITUTIONAL"].hits == 1

    def test_only_expired_trades(self):
        """Nur EXPIRED -> hit_rate None, expired_trades korrekt."""
        trades = [
            self._make_trade(TradeOutcome.EXPIRED, ConvictionLevel.STANDARD),
            self._make_trade(TradeOutcome.EXPIRED, ConvictionLevel.HIGH),
        ]
        zones = [_make_test_ob() for _ in range(2)]
        metrics = compute_backtest_metrics(
            trades, zones, 100, BASE_TIME, BASE_TIME + timedelta(days=30)
        )
        assert metrics.hit_rate is None  # Keine abgeschlossenen Trades
        assert metrics.expired_trades == 2
        assert metrics.total_trades == 2
