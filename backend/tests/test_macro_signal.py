"""Tests fuer die Makro-Signal Domain-Logik"""
from decimal import Decimal

import pytest

from app.domain.macro_signal import (
    MacroIndicator,
    IntervalThresholds,
    get_thresholds,
    score_btc_momentum,
    score_eur_usd,
    score_dxy,
    score_yield_spread,
    compute_macro_signal,
    _map_composite_to_recommendation,
    _score_momentum,
    RECOMMENDATIONS,
    VALID_INTERVALS,
)


# ─── Hilfsfunktion ───

def _make_indicator(name, current, previous, source="test", quality="live"):
    """Erstellt einen MacroIndicator mit berechneter change_pct."""
    change_pct = None
    if current is not None and previous is not None and previous != 0:
        change_pct = ((current - previous) / previous) * Decimal("100")
    return MacroIndicator(
        name=name,
        current=current,
        previous_15m=previous,
        change_pct=change_pct,
        timestamp=None,
        source=source,
        quality=quality,
    )


# ─── BTC/USD Momentum ───

class TestBtcMomentum:
    def test_strong_uptrend(self):
        """BTC steigt >1% in 15 Min -> Score +2"""
        result = score_btc_momentum(Decimal("96000"), Decimal("95000"))
        assert result.score == 2

    def test_mild_uptrend(self):
        """BTC steigt 0.3-1% -> Score +1"""
        result = score_btc_momentum(Decimal("95500"), Decimal("95000"))
        assert result.score == 1

    def test_sideways(self):
        """BTC bewegt sich <0.3% -> Score 0"""
        result = score_btc_momentum(Decimal("95100"), Decimal("95000"))
        assert result.score == 0

    def test_mild_downtrend(self):
        """BTC faellt 0.3-1% -> Score -1"""
        result = score_btc_momentum(Decimal("94500"), Decimal("95000"))
        assert result.score == -1

    def test_strong_downtrend(self):
        """BTC faellt >1% -> Score -2"""
        result = score_btc_momentum(Decimal("93900"), Decimal("95000"))
        assert result.score == -2

    def test_zero_previous(self):
        """Vorheriger Wert 0 -> Score 0 (keine Division durch 0)"""
        result = score_btc_momentum(Decimal("95000"), Decimal("0"))
        assert result.score == 0

    def test_exact_threshold_positive(self):
        """Exakt an der Schwelle +0.3% -> Score +1 (>= mild)"""
        prev = Decimal("100000")
        curr = prev * (Decimal("1") + Decimal("0.003001"))
        result = score_btc_momentum(curr, prev)
        assert result.score == 1


# ─── EUR/USD Richtung (invers) ───

class TestEurUsd:
    def test_eur_strong_up_bearish(self):
        """EUR steigt >0.5% -> bearish fuer BTC/EUR -> Score -2"""
        result = score_eur_usd(Decimal("1.0960"), Decimal("1.0900"))
        assert result.score == -2

    def test_eur_mild_up(self):
        """EUR steigt 0.2-0.5% -> Score -1"""
        result = score_eur_usd(Decimal("1.0930"), Decimal("1.0900"))
        assert result.score == -1

    def test_eur_stable(self):
        """EUR stabil -> Score 0"""
        result = score_eur_usd(Decimal("1.0901"), Decimal("1.0900"))
        assert result.score == 0

    def test_eur_mild_down_bullish(self):
        """EUR faellt 0.2-0.5% -> bullish fuer BTC/EUR -> Score +1"""
        result = score_eur_usd(Decimal("1.0870"), Decimal("1.0900"))
        assert result.score == 1

    def test_eur_strong_down(self):
        """EUR faellt >0.5% -> Score +2"""
        result = score_eur_usd(Decimal("1.0840"), Decimal("1.0900"))
        assert result.score == 2


# ─── DXY Richtung (invers) ───

class TestDxy:
    def test_dxy_strong_up_bearish(self):
        """DXY steigt >0.3% -> USD staerker -> bearish BTC -> Score -2"""
        result = score_dxy(Decimal("104.50"), Decimal("104.18"))
        assert result.score == -2

    def test_dxy_mild_up(self):
        """DXY steigt 0.1-0.3% -> Score -1"""
        result = score_dxy(Decimal("104.30"), Decimal("104.18"))
        assert result.score == -1

    def test_dxy_stable(self):
        """DXY stabil -> Score 0"""
        result = score_dxy(Decimal("104.20"), Decimal("104.18"))
        assert result.score == 0

    def test_dxy_mild_down_bullish(self):
        """DXY faellt 0.1-0.3% -> Score +1"""
        result = score_dxy(Decimal("104.05"), Decimal("104.18"))
        assert result.score == 1

    def test_dxy_strong_down(self):
        """DXY faellt >0.3% -> Score +2"""
        result = score_dxy(Decimal("103.85"), Decimal("104.18"))
        assert result.score == 2


# ─── Yield Spread ───

class TestYieldSpread:
    def test_spread_widening_strong(self):
        """Spread weitet sich >10bps -> bearish -> Score -2"""
        # spread von 1.50% auf 1.62% = +12 bps
        result = score_yield_spread(Decimal("1.62"), Decimal("1.50"))
        assert result.score == -2

    def test_spread_widening_mild(self):
        """Spread weitet sich 5-10bps -> Score -1"""
        # spread von 1.50% auf 1.57% = +7 bps
        result = score_yield_spread(Decimal("1.57"), Decimal("1.50"))
        assert result.score == -1

    def test_spread_stable(self):
        """Spread stabil +/-5bps -> Score 0"""
        result = score_yield_spread(Decimal("1.52"), Decimal("1.50"))
        assert result.score == 0

    def test_spread_narrowing_mild(self):
        """Spread engt sich 5-10bps ein -> bullish -> Score +1"""
        result = score_yield_spread(Decimal("1.43"), Decimal("1.50"))
        assert result.score == 1

    def test_spread_narrowing_strong(self):
        """Spread engt sich >10bps ein -> Score +2"""
        result = score_yield_spread(Decimal("1.38"), Decimal("1.50"))
        assert result.score == 2


# ─── Composite Score Mapping ───

class TestCompositeMapping:
    def test_stark_long(self):
        """Summe >= 4 -> STARK LONG (+2)"""
        assert _map_composite_to_recommendation(4) == 2
        assert _map_composite_to_recommendation(8) == 2

    def test_long(self):
        """Summe 2-3 -> LONG (+1)"""
        assert _map_composite_to_recommendation(2) == 1
        assert _map_composite_to_recommendation(3) == 1

    def test_neutral(self):
        """Summe -1 bis 1 -> NEUTRAL (0)"""
        assert _map_composite_to_recommendation(-1) == 0
        assert _map_composite_to_recommendation(0) == 0
        assert _map_composite_to_recommendation(1) == 0

    def test_short(self):
        """Summe -3 bis -2 -> SHORT (-1)"""
        assert _map_composite_to_recommendation(-2) == -1
        assert _map_composite_to_recommendation(-3) == -1

    def test_stark_short(self):
        """Summe < -3 -> STARK SHORT (-2)"""
        assert _map_composite_to_recommendation(-4) == -2
        assert _map_composite_to_recommendation(-8) == -2


# ─── Compute Macro Signal (Integration) ───

class TestComputeMacroSignal:
    def test_all_bullish(self):
        """Alle Faktoren bullish -> STARK LONG"""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("97000"), Decimal("95000")),
            "eur_usd": _make_indicator("EUR/USD", Decimal("1.0840"), Decimal("1.0900")),
            "dxy": _make_indicator("DXY", Decimal("103.50"), Decimal("104.00")),
            "spread": _make_indicator("Spread", Decimal("1.38"), Decimal("1.50")),
        }
        result = compute_macro_signal(indicators)
        assert result.recommendation == "STARK LONG"
        assert result.composite_score == 2
        assert result.active_factors == 4

    def test_all_bearish(self):
        """Alle Faktoren bearish -> STARK SHORT"""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("93000"), Decimal("95000")),
            "eur_usd": _make_indicator("EUR/USD", Decimal("1.0960"), Decimal("1.0900")),
            "dxy": _make_indicator("DXY", Decimal("104.50"), Decimal("104.00")),
            "spread": _make_indicator("Spread", Decimal("1.62"), Decimal("1.50")),
        }
        result = compute_macro_signal(indicators)
        assert result.recommendation == "STARK SHORT"
        assert result.composite_score == -2
        assert result.active_factors == 4

    def test_mixed_neutral(self):
        """Gemischte Signale -> NEUTRAL"""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("95500"), Decimal("95000")),  # +1
            "eur_usd": _make_indicator("EUR/USD", Decimal("1.0930"), Decimal("1.0900")),  # -1
            "dxy": _make_indicator("DXY", Decimal("104.20"), Decimal("104.18")),  # 0
            "spread": _make_indicator("Spread", Decimal("1.52"), Decimal("1.50")),  # 0
        }
        result = compute_macro_signal(indicators)
        assert result.recommendation == "NEUTRAL"
        assert result.composite_raw == 0

    def test_missing_indicators(self):
        """Fehlende Indikatoren werden als Score 0 gewertet."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("96000"), Decimal("95000")),  # +2
        }
        result = compute_macro_signal(indicators)
        assert result.active_factors == 1
        assert result.total_factors == 4
        assert result.composite_raw == 2  # nur BTC zaehlt

    def test_unavailable_data(self):
        """Indikatoren mit None-Werten -> Score 0."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", None, None),
            "eur_usd": _make_indicator("EUR/USD", None, None),
            "dxy": _make_indicator("DXY", None, None),
            "spread": _make_indicator("Spread", None, None),
        }
        result = compute_macro_signal(indicators)
        assert result.recommendation == "NEUTRAL"
        assert result.active_factors == 0
        assert result.composite_raw == 0

    def test_result_has_all_fields(self):
        """Ergebnis enthaelt alle erwarteten Felder."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("95000"), Decimal("95000")),
            "eur_usd": _make_indicator("EUR/USD", Decimal("1.09"), Decimal("1.09")),
            "dxy": _make_indicator("DXY", Decimal("104"), Decimal("104")),
            "spread": _make_indicator("Spread", Decimal("1.5"), Decimal("1.5")),
        }
        result = compute_macro_signal(indicators)
        assert result.recommendation in RECOMMENDATIONS.values()
        assert result.recommendation_color is not None
        assert result.timestamp is not None
        assert result.next_update is not None
        assert len(result.scores) == 4
        assert result.indicators is not None

    def test_scores_are_serializable(self):
        """Indicator-Dicts enthalten nur serialisierbare Typen."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("95000"), Decimal("94000")),
        }
        result = compute_macro_signal(indicators)
        btc_dict = result.indicators["btc_usd"]
        assert isinstance(btc_dict["current"], float)
        assert isinstance(btc_dict["previous_15m"], float)
        assert isinstance(btc_dict["change_pct"], float)


# ─── Intervall-Schwellenwerte ───

class TestIntervalThresholds:
    def test_15m_baseline(self):
        """15m Schwellenwerte entsprechen den Basis-Konstanten."""
        t = get_thresholds(15)
        assert t.btc_strong == Decimal("1.0")
        assert t.btc_mild == Decimal("0.3")
        assert t.eur_strong == Decimal("0.5")
        assert t.dxy_strong == Decimal("0.3")
        assert t.spread_strong == Decimal("10")
        assert t.interval_minutes == 15

    def test_5m_scaled_down(self):
        """5m Schwellenwerte sind kleiner als 15m (sqrt(5/15) Skalierung)."""
        t5 = get_thresholds(5)
        t15 = get_thresholds(15)
        assert t5.btc_strong < t15.btc_strong
        assert t5.btc_strong > Decimal("0.5")  # ~0.577
        assert t5.interval_minutes == 5

    def test_1m_smallest(self):
        """1m Schwellenwerte sind die kleinsten."""
        t1 = get_thresholds(1)
        t5 = get_thresholds(5)
        t15 = get_thresholds(15)
        assert t1.btc_strong < t5.btc_strong < t15.btc_strong
        assert t1.eur_strong < t5.eur_strong < t15.eur_strong
        assert t1.dxy_strong < t5.dxy_strong < t15.dxy_strong
        assert t1.spread_strong < t5.spread_strong < t15.spread_strong

    def test_invalid_interval_defaults_to_15(self):
        """Unbekanntes Intervall faellt auf 15m zurueck."""
        t = get_thresholds(7)
        assert t.interval_minutes == 15
        assert t.btc_strong == Decimal("1.0")

    def test_scoring_same_move_higher_on_short_interval(self):
        """0.3% Bewegung ist stark fuer 1m aber mild fuer 15m."""
        t1 = get_thresholds(1)
        t15 = get_thresholds(15)
        score_1m = _score_momentum(Decimal("0.3"), t1.btc_strong, t1.btc_mild)
        score_15m = _score_momentum(Decimal("0.3"), t15.btc_strong, t15.btc_mild)
        assert score_1m > score_15m

    def test_all_valid_intervals(self):
        """Alle gueltigen Intervalle liefern korrekte Thresholds."""
        for iv in VALID_INTERVALS:
            t = get_thresholds(iv)
            assert t.interval_minutes == iv
            assert t.btc_strong > 0
            assert t.btc_mild > 0
            assert t.btc_mild < t.btc_strong


# ─── Direction-Feld ───

class TestDirectionField:
    def test_btc_momentum_direct(self):
        """BTC Momentum hat direkte Richtung."""
        result = score_btc_momentum(Decimal("96000"), Decimal("95000"))
        assert result.direction == "direct"

    def test_eur_usd_inverse(self):
        """EUR/USD hat inverse Richtung."""
        result = score_eur_usd(Decimal("1.0960"), Decimal("1.0900"))
        assert result.direction == "inverse"

    def test_dxy_inverse(self):
        """DXY hat inverse Richtung."""
        result = score_dxy(Decimal("104.50"), Decimal("104.18"))
        assert result.direction == "inverse"

    def test_yield_spread_inverse(self):
        """Zinsspread hat inverse Richtung."""
        result = score_yield_spread(Decimal("1.62"), Decimal("1.50"))
        assert result.direction == "inverse"

    def test_direction_in_compute_result(self):
        """compute_macro_signal liefert Direction in allen Scores."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("96000"), Decimal("95000")),
            "eur_usd": _make_indicator("EUR/USD", Decimal("1.0930"), Decimal("1.0900")),
            "dxy": _make_indicator("DXY", Decimal("104.30"), Decimal("104.18")),
            "spread": _make_indicator("Spread", Decimal("1.57"), Decimal("1.50")),
        }
        result = compute_macro_signal(indicators)
        directions = [s.direction for s in result.scores]
        assert directions == ["direct", "inverse", "inverse", "inverse"]

    def test_unavailable_data_still_has_direction(self):
        """Auch bei fehlenden Daten wird Direction gesetzt."""
        result = compute_macro_signal({})
        for s in result.scores:
            assert s.direction in ("direct", "inverse")


# ─── Intervall-basierte Berechnung ───

class TestIntervalComputation:
    def test_compute_with_1m_interval(self):
        """Signal mit 1m Intervall liefert interval_minutes=1."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("95500"), Decimal("95000")),
        }
        result = compute_macro_signal(indicators, interval_minutes=1)
        assert result.interval_minutes == 1

    def test_compute_with_5m_interval(self):
        """Signal mit 5m Intervall liefert interval_minutes=5."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("95500"), Decimal("95000")),
        }
        result = compute_macro_signal(indicators, interval_minutes=5)
        assert result.interval_minutes == 5

    def test_default_interval_is_15(self):
        """Standard-Intervall ist 15 Minuten."""
        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("95000"), Decimal("95000")),
        }
        result = compute_macro_signal(indicators)
        assert result.interval_minutes == 15

    def test_next_update_within_interval(self):
        """next_update liegt maximal ein Intervall in der Zukunft."""
        from datetime import timedelta
        from app.domain.models import utcnow

        indicators = {
            "btc_usd": _make_indicator("BTC/USD", Decimal("95000"), Decimal("95000")),
        }
        for iv in [1, 5, 15]:
            result = compute_macro_signal(indicators, interval_minutes=iv)
            diff = result.next_update - utcnow()
            assert diff <= timedelta(minutes=iv)
            assert diff >= timedelta(seconds=0)

    def test_1m_scores_higher_for_small_move(self):
        """Kleine Bewegung (0.3%) erzeugt hoeheren Score bei 1m als 15m."""
        # 0.3% Aenderung
        prev = Decimal("95000")
        curr = prev * (Decimal("1") + Decimal("0.003"))
        indicators_1m = {"btc_usd": _make_indicator("BTC/USD", curr, prev)}
        indicators_15m = {"btc_usd": _make_indicator("BTC/USD", curr, prev)}
        result_1m = compute_macro_signal(indicators_1m, interval_minutes=1)
        result_15m = compute_macro_signal(indicators_15m, interval_minutes=15)
        btc_score_1m = result_1m.scores[0].score
        btc_score_15m = result_15m.scores[0].score
        assert btc_score_1m >= btc_score_15m
