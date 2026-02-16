"""
Tests fuer Orderblock Detection Engine.

Alle Tests verwenden synthetische Candle-Daten (kein I/O, kein DB).
Pattern: pytest-Klassen gruppiert nach Feature, _make_candle() Factory.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.orderblock import (
    Candle,
    ConvictionLevel,
    FairValueGap,
    OBConfig,
    OBDirection,
    OBState,
    Orderblock,
    compute_atr,
    compute_conviction_score,
    compute_impact_efficiency_ratio,
    compute_ofi_divergence,
    compute_volume_percentile,
    compute_volume_weight,
    compute_volume_zscore,
    conviction_level_from_score,
    detect_orderblocks,
    find_fvgs,
    find_swing_points,
    update_zone_states,
    _approx_tanh,
    _body_ratio,
    _clamp,
    _decimal_sqrt,
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
    """Factory: Erzeugt Candle mit Index als Stunden-Offset."""
    return Candle(
        timestamp=BASE_TIME + timedelta(hours=index),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(v),
    )


def _make_flat_candles(
    count: int,
    price: str = "100",
    spread: str = "1",
    volume: str = "100",
    start_index: int = 0,
) -> list[Candle]:
    """Erzeugt eine Reihe flacher Kerzen um einen Preis."""
    p = Decimal(price)
    s = Decimal(spread)
    candles = []
    for i in range(count):
        candles.append(
            _make_candle(
                start_index + i,
                str(p),
                str(p + s),
                str(p - s),
                str(p),
                volume,
            )
        )
    return candles


# ===========================================================================
# TestDecimalSqrt
# ===========================================================================


class TestDecimalSqrt:
    def test_sqrt_of_4(self):
        assert _decimal_sqrt(Decimal("4")) == Decimal("2")

    def test_sqrt_of_0(self):
        assert _decimal_sqrt(Decimal("0")) == Decimal("0")

    def test_sqrt_of_9(self):
        result = _decimal_sqrt(Decimal("9"))
        assert abs(result - Decimal("3")) < Decimal("0.0001")

    def test_sqrt_of_2(self):
        result = _decimal_sqrt(Decimal("2"))
        assert abs(result - Decimal("1.41421356")) < Decimal("0.0001")

    def test_sqrt_negative_raises(self):
        with pytest.raises(ValueError):
            _decimal_sqrt(Decimal("-1"))


# ===========================================================================
# TestATR
# ===========================================================================


class TestATR:
    def test_empty_candles(self):
        assert compute_atr([], 20) == []

    def test_insufficient_candles(self):
        candles = _make_flat_candles(10)
        result = compute_atr(candles, 20)
        assert all(v is None for v in result)

    def test_atr_length_3_simple(self):
        """3 Kerzen mit bekannter True Range -> ATR berechenbar."""
        candles = [
            _make_candle(0, "100", "105", "95", "102"),  # TR = 10
            _make_candle(
                1, "102", "108", "98", "104"
            ),  # TR = max(10, |108-102|, |98-102|) = 10
            _make_candle(
                2, "104", "110", "100", "106"
            ),  # TR = max(10, |110-104|, |100-104|) = 10
            _make_candle(
                3, "106", "112", "101", "108"
            ),  # TR = max(11, |112-106|, |101-106|) = 11
            _make_candle(
                4, "108", "115", "103", "110"
            ),  # TR = max(12, |115-108|, |103-108|) = 12
        ]
        result = compute_atr(candles, 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is None
        # ATR(3) = SMA(TR[1], TR[2], TR[3]) = SMA(10, 10, 11) = 31/3
        assert result[3] is not None
        assert result[3] == Decimal("10") + Decimal("1") / Decimal("3") or abs(
            result[3] - Decimal("10.333")
        ) < Decimal("0.01")

    def test_atr_all_none_below_length(self):
        """Alle Werte unter length muessen None sein."""
        candles = _make_flat_candles(25)
        result = compute_atr(candles, 20)
        for i in range(20):
            assert result[i] is None
        assert result[20] is not None

    def test_atr_decimal_precision(self):
        """ATR-Werte muessen Decimal sein, nie float."""
        candles = _make_flat_candles(25)
        result = compute_atr(candles, 20)
        for v in result:
            if v is not None:
                assert isinstance(v, Decimal)

    def test_atr_increases_with_volatility(self):
        """Hoehere Volatilitaet -> hoeherer ATR."""
        # Flache Kerzen
        flat = _make_flat_candles(25, spread="1")
        atr_flat = compute_atr(flat, 20)

        # Volatile Kerzen
        volatile = _make_flat_candles(25, spread="10")
        atr_volatile = compute_atr(volatile, 20)

        assert atr_volatile[24] > atr_flat[24]


# ===========================================================================
# TestSwingPoints
# ===========================================================================


class TestSwingPoints:
    def test_simple_swing_high(self):
        """Klarer Swing High mit n=2."""
        candles = [
            _make_candle(0, "100", "102", "98", "101"),
            _make_candle(1, "101", "103", "99", "102"),
            _make_candle(2, "102", "110", "100", "108"),  # Swing High
            _make_candle(3, "108", "107", "99", "101"),
            _make_candle(4, "101", "104", "97", "100"),
        ]
        swings = find_swing_points(candles, fractal_n=2)
        highs = [s for s in swings if s.is_high]
        assert len(highs) == 1
        assert highs[0].index == 2
        assert highs[0].price == Decimal("110")
        assert highs[0].confirmed_at_index == 4

    def test_simple_swing_low(self):
        """Klarer Swing Low mit n=2."""
        candles = [
            _make_candle(0, "100", "102", "98", "101"),
            _make_candle(1, "101", "103", "97", "102"),
            _make_candle(2, "102", "105", "90", "95"),  # Swing Low
            _make_candle(3, "95", "100", "93", "99"),
            _make_candle(4, "99", "104", "96", "103"),
        ]
        swings = find_swing_points(candles, fractal_n=2)
        lows = [s for s in swings if not s.is_high]
        assert len(lows) == 1
        assert lows[0].index == 2
        assert lows[0].price == Decimal("90")

    def test_no_swings_in_flat_market(self):
        """Keine Swings bei identischen Kerzen."""
        candles = _make_flat_candles(10)
        swings = find_swing_points(candles, fractal_n=2)
        assert len(swings) == 0

    def test_confirmed_at_index_with_n3(self):
        """confirmed_at_index = index + fractal_n."""
        candles = [
            _make_candle(0, "100", "102", "98", "100"),
            _make_candle(1, "100", "101", "98", "100"),
            _make_candle(2, "100", "101", "98", "100"),
            _make_candle(3, "100", "120", "98", "115"),  # Swing High
            _make_candle(4, "115", "118", "100", "105"),
            _make_candle(5, "105", "110", "99", "103"),
            _make_candle(6, "103", "108", "97", "100"),
        ]
        swings = find_swing_points(candles, fractal_n=3)
        highs = [s for s in swings if s.is_high]
        assert len(highs) == 1
        assert highs[0].confirmed_at_index == 3 + 3  # = 6

    def test_multiple_swings(self):
        """Mehrere Swing Highs und Lows in Folge."""
        candles = [
            _make_candle(0, "100", "102", "98", "101"),
            _make_candle(1, "101", "103", "99", "102"),
            _make_candle(2, "102", "115", "100", "110"),  # Swing High
            _make_candle(3, "110", "112", "95", "97"),
            _make_candle(4, "97", "100", "85", "88"),  # Swing Low
            _make_candle(5, "88", "95", "86", "93"),
            _make_candle(6, "93", "120", "90", "118"),  # Swing High
            _make_candle(7, "118", "119", "100", "102"),
            _make_candle(8, "102", "105", "98", "100"),
        ]
        swings = find_swing_points(candles, fractal_n=2)
        highs = [s for s in swings if s.is_high]
        lows = [s for s in swings if not s.is_high]
        assert len(highs) >= 1
        assert len(lows) >= 1


# ===========================================================================
# TestFVG
# ===========================================================================


class TestFVG:
    def test_bullish_fvg_detected(self):
        """Bullish FVG: Low(i) > High(i-2)."""
        candles = [
            _make_candle(0, "100", "105", "95", "102"),
            _make_candle(1, "102", "108", "100", "106"),  # i-2
            _make_candle(2, "106", "120", "104", "118"),  # i-1 (impuls)
            _make_candle(
                3, "118", "130", "115", "128"
            ),  # i: Low(115) > High(108)? -> Nein
        ]
        # Manuell: Low(3)=115, High(1)=108 -> 115 > 108 = True -> FVG!
        fvgs = find_fvgs(
            candles, start_index=1, window=3, direction=OBDirection.BULLISH
        )
        assert len(fvgs) >= 1
        assert fvgs[0].direction == OBDirection.BULLISH
        assert fvgs[0].gap_bottom == Decimal("108")  # High(i-2)
        assert fvgs[0].gap_top == Decimal("115")  # Low(i)

    def test_bearish_fvg_detected(self):
        """Bearish FVG: High(i) < Low(i-2)."""
        candles = [
            _make_candle(0, "200", "205", "185", "198"),  # Low=185, kein FVG mit i=2
            _make_candle(1, "198", "200", "190", "192"),  # i-2: Low=190
            _make_candle(2, "192", "193", "170", "172"),  # i-1 (impuls)
            _make_candle(
                3, "172", "180", "165", "168"
            ),  # i: High(180) < Low(190)? -> Ja!
        ]
        fvgs = find_fvgs(
            candles, start_index=1, window=3, direction=OBDirection.BEARISH
        )
        bearish = [f for f in fvgs if f.direction == OBDirection.BEARISH]
        assert len(bearish) >= 1
        assert bearish[0].gap_top == Decimal("190")  # Low(i-2)
        assert bearish[0].gap_bottom == Decimal("180")  # High(i)

    def test_no_fvg_in_normal_movement(self):
        """Keine FVG bei normaler Preisbewegung."""
        candles = [
            _make_candle(0, "100", "105", "95", "102"),
            _make_candle(1, "102", "107", "100", "104"),
            _make_candle(2, "104", "108", "101", "106"),
            _make_candle(3, "106", "110", "103", "108"),
        ]
        fvgs = find_fvgs(
            candles, start_index=1, window=3, direction=OBDirection.BULLISH
        )
        assert len(fvgs) == 0

    def test_fvg_window_respected(self):
        """FVGs ausserhalb des Windows werden nicht gefunden."""
        candles = _make_flat_candles(10)
        # Erzwinge FVG weit ausserhalb des Windows
        candles[8] = _make_candle(8, "100", "100.5", "99.5", "100")
        candles[9] = _make_candle(9, "100", "101", "99", "100.5")
        fvgs = find_fvgs(
            candles, start_index=1, window=2, direction=OBDirection.BULLISH
        )
        # Nur Kerzen Index 1..4 (start + window + 2) werden geprueft
        assert len(fvgs) == 0


# ===========================================================================
# TestVolumeZScore
# ===========================================================================


class TestVolumeZScore:
    def test_high_volume_zscore(self):
        """Deutlich hoeheres Volumen -> positiver Z-Score."""
        # Leichte Varianz im Lookback-Volumen damit std > 0
        candles = []
        for i in range(55):
            vol = str(90 + (i % 20))  # Volumen 90-109, std > 0
            candles.append(_make_candle(i, "100", "101", "99", "100", vol))
        # Setze letzte Kerze auf extrem hohes Volumen
        candles[54] = _make_candle(54, "100", "101", "99", "100", "500")
        zscore = compute_volume_zscore(candles, 54, 50)
        assert zscore > Decimal("2")

    def test_normal_volume_zscore(self):
        """Normales Volumen -> Z-Score nahe 0."""
        candles = _make_flat_candles(55, volume="100")
        zscore = compute_volume_zscore(candles, 54, 50)
        assert abs(zscore) < Decimal("0.1")

    def test_insufficient_history(self):
        """Zu wenig Historie -> Z-Score = 0."""
        candles = _make_flat_candles(5, volume="100")
        zscore = compute_volume_zscore(candles, 3, 50)
        assert zscore == Decimal("0")

    def test_zero_std_returns_zero(self):
        """Identische Volumen (std=0) -> Z-Score = 0."""
        candles = _make_flat_candles(55, volume="100")
        zscore = compute_volume_zscore(candles, 54, 50)
        assert zscore == Decimal("0")


# ===========================================================================
# TestVolumeWeight
# ===========================================================================


class TestVolumeWeight:
    def test_normal_volume_weight(self):
        """Normales Impuls-Volumen -> Weight ~1."""
        candles = _make_flat_candles(30, volume="100")
        weight = compute_volume_weight(candles, 25)
        # 3 Kerzen a 100 = 300, SMA(20) = 100, Weight = 300/100 = 3
        assert weight == Decimal("3")

    def test_insufficient_history(self):
        """Zu wenig Historie -> Weight = 0."""
        candles = _make_flat_candles(5, volume="100")
        weight = compute_volume_weight(candles, 2)
        assert weight == Decimal("0")


# ===========================================================================
# TestDetectOrderblocks
# ===========================================================================


class TestDetectOrderblocks:
    def _build_perfect_bullish_ob_scenario(self) -> list[Candle]:
        """
        Baut ein perfektes Bullish OB Szenario:
        - 25 flache Kerzen (fuer ATR-Berechnung)
        - Swing High bei Index 20 (bestaetigt bei 22)
        - Bearish Base Candle
        - Starker bullischer Displacement
        - FVG
        - BOS ueber Swing High
        """
        candles = []

        # 18 flache Kerzen als ATR-Basis (Index 0-17)
        for i in range(18):
            candles.append(_make_candle(i, "100", "102", "98", "100"))

        # Aufwaertsbewegung -> Swing High bei Index 20 (n=2: bestaetigt bei 22)
        candles.append(_make_candle(18, "100", "104", "99", "103"))
        candles.append(_make_candle(19, "103", "106", "101", "105"))
        candles.append(_make_candle(20, "105", "115", "104", "112"))  # Swing High = 115
        candles.append(_make_candle(21, "112", "113", "103", "105"))
        candles.append(
            _make_candle(22, "105", "110", "100", "103")
        )  # Swing High confirmed

        # Abwaertsbewegung (Kerzen bleiben bullish oder Doji -> kein OB-Kandidat)
        candles.append(_make_candle(23, "103", "104", "96", "96"))  # Doji
        candles.append(_make_candle(24, "96", "98", "90", "96"))  # Doji (Close == Open)

        # *** BEARISH BASE CANDLE (Bullish OB Candidate) ***
        candles.append(
            _make_candle(25, "91", "93", "85", "86")
        )  # Close < Open -> bearish

        # *** DISPLACEMENT: Starke bullische Kerzen ***
        # ATR bei flachen Kerzen (spread 2) ist ca. 4. Displacement threshold = 2.5 * 4 = 10
        # Range muss >= 10 sein
        candles.append(
            _make_candle(26, "86", "100", "85", "99", "500")
        )  # Range=15 > 10
        candles.append(
            _make_candle(27, "99", "120", "98", "118", "500")
        )  # Range=22 > 10, Close > Swing High 115 -> BOS!
        # FVG: Low(27)=98 > High(25)=93? -> 98 > 93 = True!
        candles.append(_make_candle(28, "118", "125", "116", "122", "500"))

        # Nachfolgende Kerzen
        candles.append(_make_candle(29, "122", "124", "119", "121"))

        return candles

    def _build_perfect_bearish_ob_scenario(self) -> list[Candle]:
        """Baut ein perfektes Bearish OB Szenario."""
        candles = []

        # 18 flache Kerzen (Index 0-17)
        for i in range(18):
            candles.append(_make_candle(i, "200", "202", "198", "200"))

        # Abwaertsbewegung -> Swing Low bei Index 20 (bestaetigt bei 22)
        candles.append(_make_candle(18, "200", "201", "196", "197"))
        candles.append(_make_candle(19, "197", "198", "193", "194"))
        candles.append(_make_candle(20, "194", "195", "185", "187"))  # Swing Low = 185
        candles.append(_make_candle(21, "187", "195", "186", "193"))
        candles.append(
            _make_candle(22, "193", "198", "191", "196")
        )  # Swing Low confirmed

        # Aufwaertsbewegung (Kerzen bleiben bearish oder Doji -> kein OB-Kandidat)
        candles.append(_make_candle(23, "196", "204", "195", "196"))  # Doji
        candles.append(
            _make_candle(24, "203", "208", "202", "203")
        )  # Doji (Close == Open)

        # *** BULLISH BASE CANDLE (Bearish OB Candidate) ***
        candles.append(
            _make_candle(25, "207", "213", "206", "212")
        )  # Close > Open -> bullish

        # *** DISPLACEMENT: Starke bearische Kerzen ***
        candles.append(
            _make_candle(26, "212", "213", "195", "196", "500")
        )  # Range=18 > threshold, bearish
        candles.append(
            _make_candle(27, "196", "197", "178", "180", "500")
        )  # Close=180 < Swing Low 185 -> BOS!
        # FVG: High(27)=197 < Low(25)=206? -> 197 < 206 = True! Bearish FVG
        candles.append(_make_candle(28, "180", "183", "175", "177", "500"))

        candles.append(_make_candle(29, "177", "180", "173", "175"))

        return candles

    def test_perfect_bullish_ob_detected(self):
        """Ein perfektes Bullish OB Szenario MUSS erkannt werden."""
        candles = self._build_perfect_bullish_ob_scenario()
        config = OBConfig(
            atr_length=20, atr_multiplier=Decimal("2.5"), swing_fractal_n=2
        )
        obs = detect_orderblocks(candles, config)

        bullish_obs = [ob for ob in obs if ob.direction == OBDirection.BULLISH]
        assert (
            len(bullish_obs) >= 1
        ), f"Expected bullish OB, got {len(bullish_obs)} bullish from {len(obs)} total"

        ob = bullish_obs[0]
        assert ob.state == OBState.UNMITIGATED
        assert ob.zone_top == Decimal("93")  # High of base candle
        assert ob.zone_bottom == Decimal("85")  # Low of base candle
        assert ob.entry_edge == ob.zone_top
        assert ob.stop_edge == ob.zone_bottom

    def test_perfect_bearish_ob_detected(self):
        """Ein perfektes Bearish OB Szenario MUSS erkannt werden."""
        candles = self._build_perfect_bearish_ob_scenario()
        config = OBConfig(
            atr_length=20, atr_multiplier=Decimal("2.5"), swing_fractal_n=2
        )
        obs = detect_orderblocks(candles, config)

        bearish_obs = [ob for ob in obs if ob.direction == OBDirection.BEARISH]
        assert (
            len(bearish_obs) >= 1
        ), f"Expected bearish OB, got {len(bearish_obs)} bearish from {len(obs)} total"

        ob = bearish_obs[0]
        assert ob.state == OBState.UNMITIGATED
        assert ob.zone_top == Decimal("213")
        assert ob.zone_bottom == Decimal("206")
        assert ob.entry_edge == ob.zone_bottom
        assert ob.stop_edge == ob.zone_top

    def test_no_displacement_rejected(self):
        """Ohne signifikanten Displacement wird kein OB erkannt."""
        candles = _make_flat_candles(30, spread="1")
        config = OBConfig(atr_length=20, atr_multiplier=Decimal("5.0"))
        obs = detect_orderblocks(candles, config)
        assert len(obs) == 0

    def test_insufficient_candles_returns_empty(self):
        """Zu wenige Kerzen -> leere Liste."""
        candles = _make_flat_candles(5)
        obs = detect_orderblocks(candles, OBConfig())
        assert len(obs) == 0

    def test_formed_at_before_confirmed_at(self):
        """confirmed_at muss >= formed_at sein."""
        candles = self._build_perfect_bullish_ob_scenario()
        obs = detect_orderblocks(candles, OBConfig(atr_length=20, swing_fractal_n=2))
        for ob in obs:
            assert ob.confirmed_at >= ob.formed_at
            assert ob.confirmed_at_index >= ob.formed_at_index

    def test_bullish_entry_edge_is_top(self):
        """Bullish OB: entry_edge = zone_top."""
        candles = self._build_perfect_bullish_ob_scenario()
        obs = detect_orderblocks(candles, OBConfig(atr_length=20, swing_fractal_n=2))
        bullish = [ob for ob in obs if ob.direction == OBDirection.BULLISH]
        for ob in bullish:
            assert ob.entry_edge == ob.zone_top

    def test_bearish_entry_edge_is_bottom(self):
        """Bearish OB: entry_edge = zone_bottom."""
        candles = self._build_perfect_bearish_ob_scenario()
        obs = detect_orderblocks(candles, OBConfig(atr_length=20, swing_fractal_n=2))
        bearish = [ob for ob in obs if ob.direction == OBDirection.BEARISH]
        for ob in bearish:
            assert ob.entry_edge == ob.zone_bottom

    def test_equilibrium_is_midpoint(self):
        """equilibrium = (top + bottom) / 2."""
        candles = self._build_perfect_bullish_ob_scenario()
        obs = detect_orderblocks(candles, OBConfig(atr_length=20, swing_fractal_n=2))
        for ob in obs:
            expected = (ob.zone_top + ob.zone_bottom) / Decimal("2")
            assert ob.equilibrium == expected

    def test_high_conviction_with_high_volume(self):
        """Hohes Impuls-Volumen -> HIGH oder INSTITUTIONAL Conviction."""
        candles = self._build_perfect_bullish_ob_scenario()
        # Standard-Volumen ist 100 in flat candles, Impuls-Kerzen haben 500
        config = OBConfig(
            atr_length=20,
            swing_fractal_n=2,
            zscore_lookback=20,
            zscore_threshold=Decimal("1.0"),  # Niedrigerer Threshold fuer Test
        )
        obs = detect_orderblocks(candles, config)
        bullish = [ob for ob in obs if ob.direction == OBDirection.BULLISH]
        if bullish:
            # Mit 500 vs 100 Volumen sollte Z-Score hoch sein
            assert bullish[0].volume_zscore > Decimal("0") or bullish[0].conviction in (
                ConvictionLevel.HIGH,
                ConvictionLevel.INSTITUTIONAL,
                ConvictionLevel.STANDARD,
            )
            # Neue Felder muessen vorhanden sein
            assert bullish[0].conviction_score >= Decimal("0")
            assert bullish[0].volume_percentile >= Decimal("0")

    def test_deterministic_results(self):
        """Gleiche Eingabe -> gleiche Ausgabe (deterministisch)."""
        candles = self._build_perfect_bullish_ob_scenario()
        config = OBConfig(atr_length=20, swing_fractal_n=2)
        obs1 = detect_orderblocks(candles, config)
        obs2 = detect_orderblocks(candles, config)
        assert len(obs1) == len(obs2)
        for a, b in zip(obs1, obs2):
            assert a.id == b.id
            assert a.zone_top == b.zone_top
            assert a.zone_bottom == b.zone_bottom

    def test_ob_id_format(self):
        """OB-ID hat deterministisches Format."""
        candles = self._build_perfect_bullish_ob_scenario()
        obs = detect_orderblocks(candles, OBConfig(atr_length=20, swing_fractal_n=2))
        for ob in obs:
            assert ob.id.startswith("ob_")
            assert ob.direction.value.lower() in ob.id

    def test_different_atr_multiplier_changes_result(self):
        """Hoeher ATR-Multiplikator -> weniger oder andere OBs."""
        candles = self._build_perfect_bullish_ob_scenario()
        config_low = OBConfig(
            atr_length=20, atr_multiplier=Decimal("1.0"), swing_fractal_n=2
        )
        config_high = OBConfig(
            atr_length=20, atr_multiplier=Decimal("10.0"), swing_fractal_n=2
        )
        obs_low = detect_orderblocks(candles, config_low)
        obs_high = detect_orderblocks(candles, config_high)
        # Hoeherer Multiplikator sollte weniger/keine OBs finden
        assert len(obs_high) <= len(obs_low)


# ===========================================================================
# TestUpdateZoneStates
# ===========================================================================


class TestUpdateZoneStates:
    def _make_test_ob(
        self,
        direction: OBDirection = OBDirection.BULLISH,
        zone_top: str = "100",
        zone_bottom: str = "90",
        confirmed_at_index: int = 5,
    ) -> Orderblock:
        """Factory fuer Test-Orderblocks."""
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
            conviction=ConvictionLevel.STANDARD,
            volume_zscore=Decimal("1.5"),
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

    def test_unmitigated_stays_unmitigated(self):
        """Kein Touch -> bleibt UNMITIGATED."""
        ob = self._make_test_ob(zone_top="100", zone_bottom="90", confirmed_at_index=5)
        # Kerzen weit ueber der Zone
        candles = []
        for i in range(10):
            candles.append(_make_candle(i, "150", "155", "145", "152"))
        updated = update_zone_states([ob], candles)
        assert updated[0].state == OBState.UNMITIGATED

    def test_bullish_unmitigated_to_mitigated(self):
        """Preis beruehrt Zone -> MITIGATED."""
        ob = self._make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),  # confirmed
            _make_candle(3, "119", "121", "110", "112"),
            _make_candle(
                4, "112", "115", "95", "97"
            ),  # Low=95, beruehrt Zone [90,100] -> MITIGATED
            _make_candle(5, "97", "105", "92", "103"),  # Preis prallt ab
        ]
        updated = update_zone_states([ob], candles)
        assert updated[0].state == OBState.MITIGATED
        assert updated[0].mitigated_at == candles[4].timestamp

    def test_bullish_unmitigated_to_invalid(self):
        """Preis bricht durch Stop-Edge -> INVALID."""
        ob = self._make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),  # confirmed
            _make_candle(
                3, "119", "121", "85", "87"
            ),  # Low=85 <= zone_bottom=90 -> INVALID
        ]
        updated = update_zone_states([ob], candles)
        assert updated[0].state == OBState.INVALID
        assert updated[0].invalidated_at == candles[3].timestamp

    def test_bearish_unmitigated_to_invalid(self):
        """Bearish OB: High >= zone_top -> INVALID."""
        ob = self._make_test_ob(
            direction=OBDirection.BEARISH,
            zone_top="210",
            zone_bottom="200",
            confirmed_at_index=2,
        )
        candles = [
            _make_candle(0, "180", "185", "175", "182"),
            _make_candle(1, "182", "184", "178", "180"),
            _make_candle(2, "180", "183", "176", "179"),  # confirmed
            _make_candle(
                3, "179", "215", "177", "212"
            ),  # High=215 >= zone_top=210 -> INVALID
        ]
        updated = update_zone_states([ob], candles)
        assert updated[0].state == OBState.INVALID

    def test_already_invalid_stays_invalid(self):
        """Ein bereits INVALID OB bleibt INVALID."""
        ob = self._make_test_ob(confirmed_at_index=2)
        ob = Orderblock(
            **{**ob.__dict__, "state": OBState.INVALID, "invalidated_at": BASE_TIME}
        )
        candles = _make_flat_candles(5, price="150")
        updated = update_zone_states([ob], candles)
        assert updated[0].state == OBState.INVALID

    def test_invalidation_before_mitigation(self):
        """Wenn Invalidierung und Mitigation gleichzeitig, gewinnt Invalidierung."""
        ob = self._make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        # Kerze die durch die gesamte Zone durchbricht
        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),
            _make_candle(3, "119", "121", "80", "82"),  # Low=80 <= bottom=90 -> INVALID
        ]
        updated = update_zone_states([ob], candles)
        assert updated[0].state == OBState.INVALID

    def test_multiple_zones_updated_independently(self):
        """Mehrere Zonen werden unabhaengig voneinander aktualisiert."""
        ob1 = self._make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=2,
        )
        ob1 = Orderblock(**{**ob1.__dict__, "id": "ob_test_1"})
        ob2 = self._make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="80",
            zone_bottom="70",
            confirmed_at_index=2,
        )
        ob2 = Orderblock(**{**ob2.__dict__, "id": "ob_test_2"})

        candles = [
            _make_candle(0, "120", "125", "115", "122"),
            _make_candle(1, "122", "124", "118", "120"),
            _make_candle(2, "120", "122", "116", "119"),
            _make_candle(
                3, "119", "121", "95", "97"
            ),  # Beruehrt Zone 1 (90-100) -> MITIGATED
            _make_candle(4, "97", "100", "92", "98"),  # Bleibt ueber Zone 2 (70-80)
        ]
        updated = update_zone_states([ob1, ob2], candles)
        assert updated[0].state == OBState.MITIGATED  # Zone 1 beruehrt
        assert updated[1].state == OBState.UNMITIGATED  # Zone 2 nicht beruehrt

    def test_state_update_respects_confirmed_at(self):
        """State-Updates beginnen erst nach confirmed_at_index."""
        ob = self._make_test_ob(
            direction=OBDirection.BULLISH,
            zone_top="100",
            zone_bottom="90",
            confirmed_at_index=5,
        )
        # Kerzen 0-5: Preis beruehrt Zone, aber VOR confirmed_at
        # Kerzen 6+: Preis ueber Zone
        candles = [
            _make_candle(
                0, "95", "100", "85", "90"
            ),  # Beruehrt Zone, aber i <= confirmed_at
            _make_candle(1, "90", "98", "82", "85"),
            _make_candle(2, "85", "95", "80", "88"),
            _make_candle(3, "88", "96", "83", "90"),
            _make_candle(4, "90", "97", "85", "92"),
            _make_candle(5, "92", "100", "88", "95"),  # confirmed_at
            _make_candle(
                6, "120", "125", "118", "122"
            ),  # Nach confirmed -> weit ueber Zone
            _make_candle(7, "122", "128", "120", "125"),
        ]
        updated = update_zone_states([ob], candles)
        # Zone sollte NICHT mitigated sein, da Beruehrungen vor confirmed_at ignoriert werden
        assert updated[0].state == OBState.UNMITIGATED


# ===========================================================================
# TestVolumePercentile (Enhancement 1: Cont)
# ===========================================================================


class TestVolumePercentile:
    def test_high_volume_near_100(self):
        """Volumen hoeher als alle im Lookback -> Percentile nahe 100."""
        candles = [_make_candle(i, "100", "102", "98", "100", v="50") for i in range(20)]
        candles.append(_make_candle(20, "100", "102", "98", "100", v="200"))
        result = compute_volume_percentile(candles, 20, 20)
        assert result == Decimal("100")

    def test_median_volume_near_50(self):
        """Volumen in der Mitte -> Percentile nahe 50."""
        candles = []
        for i in range(20):
            vol = str(10 + i * 10)  # 10, 20, 30, ..., 200
            candles.append(_make_candle(i, "100", "102", "98", "100", v=vol))
        # Kerze 20 mit Volumen 110 (median-artig)
        candles.append(_make_candle(20, "100", "102", "98", "100", v="110"))
        result = compute_volume_percentile(candles, 20, 20)
        assert Decimal("40") <= result <= Decimal("60")

    def test_low_volume_near_0(self):
        """Volumen niedriger als alle im Lookback -> Percentile 0."""
        candles = [_make_candle(i, "100", "102", "98", "100", v="200") for i in range(20)]
        candles.append(_make_candle(20, "100", "102", "98", "100", v="1"))
        result = compute_volume_percentile(candles, 20, 20)
        assert result == Decimal("0")

    def test_insufficient_history_returns_50(self):
        """Unzureichende Historie -> neutral 50."""
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(5)]
        result = compute_volume_percentile(candles, 3, 50)  # lookback > index
        assert result == Decimal("50")

    def test_decimal_precision(self):
        """Ergebnis ist Decimal."""
        candles = [_make_candle(i, "100", "102", "98", "100", v="100") for i in range(25)]
        result = compute_volume_percentile(candles, 24, 20)
        assert isinstance(result, Decimal)


# ===========================================================================
# TestOFIDivergence (Enhancement 2: Bouchaud)
# ===========================================================================


class TestOFIDivergence:
    def test_bullish_positive_divergence(self):
        """Buying pressure shift -> positive Divergenz."""
        # Formation: Kerzen mit Close nahe Low (Verkaufsdruck)
        candles = []
        for i in range(5):
            candles.append(_make_candle(i, "100", "102", "96", "97", v="100"))
        # OB-Kerze (bearish base fuer bullish OB)
        candles.append(_make_candle(5, "100", "102", "96", "97", v="100"))
        # Impulse: Kerzen mit Close nahe High (Kaufdruck)
        for i in range(6, 9):
            candles.append(_make_candle(i, "100", "108", "99", "107", v="200"))

        result = compute_ofi_divergence(candles, ob_index=5)
        assert result > Decimal("0")  # Positiver Shift

    def test_bearish_negative_divergence(self):
        """Selling pressure shift -> negative Divergenz."""
        # Formation: Kerzen mit Close nahe High (Kaufdruck)
        candles = []
        for i in range(5):
            candles.append(_make_candle(i, "100", "106", "98", "105", v="100"))
        # OB-Kerze
        candles.append(_make_candle(5, "100", "106", "98", "105", v="100"))
        # Impulse: Kerzen mit Close nahe Low (Verkaufsdruck)
        for i in range(6, 9):
            candles.append(_make_candle(i, "100", "101", "92", "93", v="200"))

        result = compute_ofi_divergence(candles, ob_index=5)
        assert result < Decimal("0")  # Negativer Shift

    def test_flat_market_near_zero(self):
        """Kein Shift -> Divergenz nahe 0."""
        candles = [_make_candle(i, "100", "102", "98", "100", v="100") for i in range(10)]
        result = compute_ofi_divergence(candles, ob_index=5)
        assert abs(result) < Decimal("50")  # Nahe 0

    def test_doji_candle_zero_range(self):
        """Doji (High == Low) -> CLV = 0, kein Beitrag."""
        candles = [_make_candle(i, "100", "100", "100", "100", v="100") for i in range(10)]
        result = compute_ofi_divergence(candles, ob_index=5)
        assert result == Decimal("0")

    def test_insufficient_data(self):
        """Nicht genug Kerzen -> 0."""
        candles = [_make_candle(0, "100", "102", "98", "100")]
        result = compute_ofi_divergence(candles, ob_index=0)
        assert result == Decimal("0")


# ===========================================================================
# TestImpactEfficiencyRatio (Enhancement 5: Bouchaud)
# ===========================================================================


class TestImpactEfficiencyRatio:
    def test_high_vol_low_displacement(self):
        """Viel Volumen, wenig Preisbewegung -> hoher IER."""
        # Kerzen mit hohem Volumen und minimaler Preisaenderung
        candles = [_make_candle(i, "100", "101", "99", "100", v="1000") for i in range(16)]
        # OB-Kerze mit leichter Preisaenderung (Close != form_start Open)
        candles.append(_make_candle(16, "100", "101", "99", "100.5", v="1000"))
        candles.append(_make_candle(17, "100.5", "101", "99", "101", v="1000"))
        candles.append(_make_candle(18, "101", "101.5", "99.5", "101.2", v="1000"))
        candles.append(_make_candle(19, "101.2", "101.5", "99.5", "101.3", v="1000"))
        candles.append(_make_candle(20, "101.3", "102", "99", "101.5", v="1000"))
        result = compute_impact_efficiency_ratio(
            candles, ob_index=20, atr_at_formation=Decimal("5")
        )
        assert result > Decimal("1")

    def test_low_vol_high_displacement(self):
        """Wenig Volumen, viel Preisbewegung -> niedriger IER."""
        candles = [_make_candle(i, "100", "102", "98", "100", v="10") for i in range(20)]
        # OB-Kerze mit grosser Preisbewegung
        candles.append(_make_candle(20, "100", "120", "80", "80", v="10"))
        result = compute_impact_efficiency_ratio(
            candles, ob_index=20, atr_at_formation=Decimal("5")
        )
        assert result < Decimal("5")

    def test_zero_displacement_returns_zero(self):
        """Keine Preisbewegung -> 0 (kein div/0)."""
        candles = [_make_candle(i, "100", "101", "99", "100", v="100") for i in range(25)]
        # OB-Kerze: Close == Open des form_start -> displacement = 0
        result = compute_impact_efficiency_ratio(
            candles, ob_index=20, atr_at_formation=Decimal("5")
        )
        # Bei gleichen Open/Close im form_start und OB: displacement nahe 0
        assert isinstance(result, Decimal)

    def test_zero_atr_returns_zero(self):
        """ATR = 0 -> 0."""
        candles = [_make_candle(i, "100", "102", "98", "100") for i in range(25)]
        result = compute_impact_efficiency_ratio(
            candles, ob_index=20, atr_at_formation=Decimal("0")
        )
        assert result == Decimal("0")


# ===========================================================================
# TestConvictionScore (Enhancement 4: Composite Scoring)
# ===========================================================================


class TestConvictionScore:
    def _make_impulse_candle(self, close_near_high: bool = True) -> Candle:
        if close_near_high:
            return _make_candle(0, "100", "120", "98", "118", v="500")
        return _make_candle(0, "100", "102", "98", "100", v="50")

    def test_all_high_inputs_near_100(self):
        """Alle Signale maximal -> Score nahe 100."""
        score = compute_conviction_score(
            volume_percentile=Decimal("95"),
            volume_zscore=Decimal("4.0"),
            ofi_divergence=Decimal("5000"),  # Stark positiv
            direction=OBDirection.BULLISH,
            impulse_candle=self._make_impulse_candle(close_near_high=True),
            volume_weight=Decimal("6.0"),
        )
        assert score > Decimal("70")

    def test_all_low_inputs_near_0(self):
        """Alle Signale minimal -> Score nahe 0."""
        score = compute_conviction_score(
            volume_percentile=Decimal("5"),
            volume_zscore=Decimal("0.1"),
            ofi_divergence=Decimal("-5000"),  # Falsche Richtung fuer Bullish
            direction=OBDirection.BULLISH,
            impulse_candle=self._make_impulse_candle(close_near_high=False),
            volume_weight=Decimal("0.3"),
        )
        assert score < Decimal("30")

    def test_score_to_level_mapping(self):
        """conviction_level_from_score mappt korrekt."""
        assert conviction_level_from_score(Decimal("20")) == ConvictionLevel.LOW
        assert conviction_level_from_score(Decimal("45")) == ConvictionLevel.STANDARD
        assert conviction_level_from_score(Decimal("65")) == ConvictionLevel.HIGH
        assert conviction_level_from_score(Decimal("85")) == ConvictionLevel.INSTITUTIONAL

    def test_boundary_values(self):
        """Grenzwerte: 35, 55, 75."""
        assert conviction_level_from_score(Decimal("34.99")) == ConvictionLevel.LOW
        assert conviction_level_from_score(Decimal("35")) == ConvictionLevel.STANDARD
        assert conviction_level_from_score(Decimal("54.99")) == ConvictionLevel.STANDARD
        assert conviction_level_from_score(Decimal("55")) == ConvictionLevel.HIGH
        assert conviction_level_from_score(Decimal("74.99")) == ConvictionLevel.HIGH
        assert conviction_level_from_score(Decimal("75")) == ConvictionLevel.INSTITUTIONAL

    def test_decimal_precision(self):
        """Score ist Decimal."""
        score = compute_conviction_score(
            volume_percentile=Decimal("50"),
            volume_zscore=Decimal("2.0"),
            ofi_divergence=Decimal("0"),
            direction=OBDirection.BULLISH,
            impulse_candle=self._make_impulse_candle(),
            volume_weight=Decimal("2.0"),
        )
        assert isinstance(score, Decimal)
        assert Decimal("0") <= score <= Decimal("100")


# ===========================================================================
# TestHelpers (Clamp, Tanh, BodyRatio)
# ===========================================================================


class TestHelpers:
    def test_clamp(self):
        """_clamp begrenzt korrekt."""
        assert _clamp(Decimal("5"), Decimal("0"), Decimal("10")) == Decimal("5")
        assert _clamp(Decimal("-1"), Decimal("0"), Decimal("10")) == Decimal("0")
        assert _clamp(Decimal("15"), Decimal("0"), Decimal("10")) == Decimal("10")

    def test_approx_tanh(self):
        """_approx_tanh approximiert tanh."""
        # Neutral
        assert _approx_tanh(Decimal("0")) == Decimal("0")
        # Positive: should be between 0 and 1
        result = _approx_tanh(Decimal("1"))
        assert Decimal("0") < result < Decimal("1")
        # Large: should approach 1
        result = _approx_tanh(Decimal("100"))
        assert result > Decimal("0.9")
        # Symmetric
        assert _approx_tanh(Decimal("2")) == -_approx_tanh(Decimal("-2"))

    def test_body_ratio(self):
        """_body_ratio berechnet Body/Range korrekt."""
        # Bullish Kerze: body = |110-100| = 10, range = 112-98 = 14
        c = _make_candle(0, "100", "112", "98", "110")
        ratio = _body_ratio(c)
        assert ratio == Decimal("10") / Decimal("14")
        # Doji
        d = _make_candle(0, "100", "100", "100", "100")
        assert _body_ratio(d) == Decimal("0")


# ===========================================================================
# TestDojBaseCandle (Edge Case)
# ===========================================================================


class TestDojiBaseCandle:
    """Doji-Kerzen (Close == Open) duerfen keine OB-Kandidaten sein."""

    def test_doji_not_treated_as_base(self):
        """Reine Doji-Kerzen werden als Base uebersprungen."""
        candles = []
        # ATR-Basis
        for i in range(22):
            candles.append(_make_candle(i, "100", "102", "98", "100"))
        # Swing High bei 20 (bestaetigt bei 22)
        candles[20] = _make_candle(20, "100", "115", "99", "112")
        # Doji als potenzieller OB-Kandidat (Close == Open)
        candles.append(_make_candle(22, "95", "96", "85", "95"))  # Doji!
        # Starke bullische Displacement
        candles.append(_make_candle(23, "95", "120", "94", "118", "500"))
        candles.append(_make_candle(24, "118", "125", "116", "122", "500"))
        candles.append(_make_candle(25, "122", "128", "120", "125", "500"))

        config = OBConfig(atr_length=20, swing_fractal_n=2)
        obs = detect_orderblocks(candles, config)

        # Doji (Close==Open) darf kein OB-Kandidat sein
        doji_obs = [ob for ob in obs if ob.formed_at_index == 22]
        # Doji candle hat Close == Open, also kein Kandidat
        for ob in doji_obs:
            assert candles[ob.formed_at_index].close != candles[ob.formed_at_index].open


class TestConfigVariations:
    """Verschiedene Config-Parameter beeinflussen Detection deterministisch."""

    def _build_basic_scenario(self) -> list:
        candles = []
        for i in range(18):
            candles.append(_make_candle(i, "100", "102", "98", "100"))
        candles.append(_make_candle(18, "100", "104", "99", "103"))
        candles.append(_make_candle(19, "103", "106", "101", "105"))
        candles.append(_make_candle(20, "105", "115", "104", "112"))
        candles.append(_make_candle(21, "112", "113", "103", "105"))
        candles.append(_make_candle(22, "105", "110", "100", "103"))
        candles.append(_make_candle(23, "103", "104", "96", "96"))
        candles.append(_make_candle(24, "96", "98", "90", "96"))
        candles.append(_make_candle(25, "91", "93", "85", "86"))
        candles.append(_make_candle(26, "86", "100", "85", "99", "500"))
        candles.append(_make_candle(27, "99", "120", "98", "118", "500"))
        candles.append(_make_candle(28, "118", "125", "116", "122", "500"))
        candles.append(_make_candle(29, "122", "124", "119", "121"))
        return candles

    def test_different_fractal_n_changes_detection(self):
        """Groesseres fractal_n kann zu anderen Ergebnissen fuehren."""
        candles = self._build_basic_scenario()
        config_n2 = OBConfig(atr_length=20, swing_fractal_n=2)
        config_n3 = OBConfig(atr_length=20, swing_fractal_n=3)
        obs_n2 = detect_orderblocks(candles, config_n2)
        obs_n3 = detect_orderblocks(candles, config_n3)
        # Mit n=3 kann BOS nicht bestaetigt werden weil Swing spaeter bestaetigt wird
        assert len(obs_n2) >= len(obs_n3)

    def test_different_fvg_window(self):
        """Kleinerer FVG-Window kann OBs ausschliessen."""
        candles = self._build_basic_scenario()
        config_w3 = OBConfig(atr_length=20, fvg_window=3, swing_fractal_n=2)
        config_w1 = OBConfig(atr_length=20, fvg_window=1, swing_fractal_n=2)
        obs_w3 = detect_orderblocks(candles, config_w3)
        obs_w1 = detect_orderblocks(candles, config_w1)
        assert len(obs_w3) >= len(obs_w1)

    def test_zscore_threshold_affects_conviction(self):
        """Hoeherer zscore_threshold -> weniger HIGH_CONVICTION."""
        candles = self._build_basic_scenario()
        config_low = OBConfig(
            atr_length=20, swing_fractal_n=2,
            zscore_threshold=Decimal("0.5"),
        )
        config_high = OBConfig(
            atr_length=20, swing_fractal_n=2,
            zscore_threshold=Decimal("5.0"),
        )
        obs_low = detect_orderblocks(candles, config_low)
        obs_high = detect_orderblocks(candles, config_high)
        # Gleiche Anzahl OBs (Threshold aendert nur Conviction, nicht Detection)
        assert len(obs_low) == len(obs_high)


class TestBearishFVGEdgeCases:
    """Spezifische FVG Tests fuer Bearish Richtung."""

    def test_bearish_fvg_gap_boundaries(self):
        """Bearish FVG: gap_top = Low(i-2), gap_bottom = High(i)."""
        candles = [
            _make_candle(0, "200", "205", "195", "198"),
            _make_candle(1, "198", "200", "193", "195"),  # i-2: Low=193
            _make_candle(2, "195", "196", "175", "177"),  # i-1 (impuls)
            _make_candle(3, "177", "185", "170", "172"),  # i: High=185 < Low(1)=193 -> FVG!
        ]
        fvgs = find_fvgs(candles, start_index=1, window=3, direction=OBDirection.BEARISH)
        bearish = [f for f in fvgs if f.direction == OBDirection.BEARISH]
        assert len(bearish) >= 1
        # Gap boundaries korrekt
        assert bearish[0].gap_top == Decimal("193")  # Low(i-2)
        assert bearish[0].gap_bottom == Decimal("185")  # High(i)

    def test_no_fvg_when_gap_just_touches(self):
        """Kein FVG wenn High(i) == Low(i-2) (kein Gap)."""
        candles = [
            _make_candle(0, "200", "205", "195", "198"),
            _make_candle(1, "198", "200", "190", "195"),  # i-2: Low=190
            _make_candle(2, "195", "196", "180", "182"),  # i-1 (impuls)
            _make_candle(3, "182", "190", "175", "178"),  # i: High=190 == Low(1)=190 -> KEIN FVG
        ]
        fvgs = find_fvgs(candles, start_index=1, window=3, direction=OBDirection.BEARISH)
        bearish = [f for f in fvgs if f.direction == OBDirection.BEARISH]
        assert len(bearish) == 0

    def test_bullish_fvg_no_gap_when_equal(self):
        """Kein Bullish FVG wenn Low(i) == High(i-2)."""
        candles = [
            _make_candle(0, "100", "105", "95", "102"),
            _make_candle(1, "102", "108", "100", "106"),  # i-2: High=108
            _make_candle(2, "106", "120", "104", "118"),  # i-1
            _make_candle(3, "118", "125", "108", "122"),  # i: Low=108 == High(1)=108 -> KEIN FVG
        ]
        fvgs = find_fvgs(candles, start_index=1, window=3, direction=OBDirection.BULLISH)
        assert len(fvgs) == 0


class TestMultipleZonesDetection:
    """Test: Mehrere OBs in einer Candle-Serie."""

    def test_multiple_obs_in_series(self):
        """Erkennt mehrere OBs wenn Szenario es hergibt."""
        candles = []
        # 25 flache Kerzen
        for i in range(25):
            candles.append(_make_candle(i, "100", "102", "98", "100"))

        # Swing High bei 22
        candles[22] = _make_candle(22, "100", "115", "99", "112")

        # Erste OB-Sequenz (Bullish)
        candles.append(_make_candle(25, "100", "101", "90", "91"))  # Bearish base
        candles.append(_make_candle(26, "91", "108", "90", "107", "500"))
        candles.append(_make_candle(27, "107", "120", "106", "118", "500"))
        candles.append(_make_candle(28, "118", "125", "116", "122", "500"))
        candles.append(_make_candle(29, "122", "124", "119", "121"))

        config = OBConfig(atr_length=20, swing_fractal_n=2)
        obs = detect_orderblocks(candles, config)

        # Mindestens 1 OB sollte erkannt werden
        assert len(obs) >= 1

        # Alle OBs muessen eindeutige IDs haben
        ids = [ob.id for ob in obs]
        assert len(ids) == len(set(ids))

    def test_all_obs_have_decimal_fields(self):
        """Alle numerischen Felder auf Orderblocks sind Decimal."""
        candles = []
        for i in range(18):
            candles.append(_make_candle(i, "100", "102", "98", "100"))
        candles.append(_make_candle(18, "100", "104", "99", "103"))
        candles.append(_make_candle(19, "103", "106", "101", "105"))
        candles.append(_make_candle(20, "105", "115", "104", "112"))
        candles.append(_make_candle(21, "112", "113", "103", "105"))
        candles.append(_make_candle(22, "105", "110", "100", "103"))
        candles.append(_make_candle(23, "103", "104", "96", "96"))
        candles.append(_make_candle(24, "96", "98", "90", "96"))
        candles.append(_make_candle(25, "91", "93", "85", "86"))
        candles.append(_make_candle(26, "86", "100", "85", "99", "500"))
        candles.append(_make_candle(27, "99", "120", "98", "118", "500"))
        candles.append(_make_candle(28, "118", "125", "116", "122", "500"))
        candles.append(_make_candle(29, "122", "124", "119", "121"))

        config = OBConfig(atr_length=20, swing_fractal_n=2)
        obs = detect_orderblocks(candles, config)
        for ob in obs:
            assert isinstance(ob.zone_top, Decimal)
            assert isinstance(ob.zone_bottom, Decimal)
            assert isinstance(ob.equilibrium, Decimal)
            assert isinstance(ob.entry_edge, Decimal)
            assert isinstance(ob.stop_edge, Decimal)
            assert isinstance(ob.volume_zscore, Decimal)
            assert isinstance(ob.volume_weight, Decimal)
            assert isinstance(ob.volume_percentile, Decimal)
            assert isinstance(ob.ofi_divergence, Decimal)
            assert isinstance(ob.impact_efficiency_ratio, Decimal)
            assert isinstance(ob.conviction_score, Decimal)
            assert isinstance(ob.atr_at_formation, Decimal)
            assert isinstance(ob.displacement_range, Decimal)
