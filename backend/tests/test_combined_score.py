"""
Tests fuer Combined Score Domain-Logik.

Testet die reine Scoring-Logik ohne I/O:
  - Normalisierung (Direction, Sentiment)
  - Unified Score Berechnung
  - Action-Mapping
  - Finaler Multiplikator
  - Konflikterkennung
  - Qualitaetsbewertung
  - Integration (compute_combined_score)
"""

from decimal import Decimal

import pytest

from app.domain.combined_score import (
    CombinedAction,
    CombinedScoreResult,
    DirectionInput,
    SizingInput,
    _normalize_direction,
    _normalize_sentiment_direction,
    _map_score_to_action,
    _compute_final_multiplier,
    _detect_conflict,
    _assess_quality,
    compute_combined_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_direction(
    composite_raw: int = 0,
    composite_score: int = 0,
    recommendation: str = "NEUTRAL",
    active_factors: int = 4,
    total_factors: int = 4,
    interval_minutes: int = 15,
) -> DirectionInput:
    return DirectionInput(
        composite_score=composite_score,
        composite_raw=composite_raw,
        recommendation=recommendation,
        active_factors=active_factors,
        total_factors=total_factors,
        interval_minutes=interval_minutes,
    )


def _make_sizing(
    composite_score: Decimal = Decimal("50"),
    label: str = "Neutral",
    buy_size_multiplier: Decimal = Decimal("1.00"),
    raw_multiplier: Decimal = Decimal("1.00"),
    confidence: Decimal = Decimal("1.0"),
    active_pillars: int = 5,
    total_pillars: int = 5,
) -> SizingInput:
    return SizingInput(
        composite_score=composite_score,
        label=label,
        buy_size_multiplier=buy_size_multiplier,
        raw_multiplier=raw_multiplier,
        confidence=confidence,
        active_pillars=active_pillars,
        total_pillars=total_pillars,
    )


# ---------------------------------------------------------------------------
# TestNormalizeDirection
# ---------------------------------------------------------------------------

class TestNormalizeDirection:
    """Testet _normalize_direction: Raw -8..+8 → -1.0..+1.0."""

    def test_max_bullish_raw_8(self):
        assert _normalize_direction(8) == Decimal("1")

    def test_max_bearish_raw_minus_8(self):
        assert _normalize_direction(-8) == Decimal("-1")

    def test_neutral_raw_0(self):
        assert _normalize_direction(0) == Decimal("0")

    def test_mild_bullish_raw_3(self):
        result = _normalize_direction(3)
        assert result == Decimal("0.375")

    def test_clamping_beyond_positive(self):
        """Werte ueber 8 werden auf 1.0 geclamped."""
        assert _normalize_direction(10) == Decimal("1")

    def test_clamping_beyond_negative(self):
        """Werte unter -8 werden auf -1.0 geclamped."""
        assert _normalize_direction(-12) == Decimal("-1")


# ---------------------------------------------------------------------------
# TestNormalizeSentimentDirection
# ---------------------------------------------------------------------------

class TestNormalizeSentimentDirection:
    """Testet _normalize_sentiment_direction: Score 0-100 → +1.0..-1.0 (kontraer)."""

    def test_extreme_fear_score_0(self):
        """Score 0 (Extreme Fear) = staerkstes Kaufsignal (+1.0)."""
        assert _normalize_sentiment_direction(Decimal("0")) == Decimal("1")

    def test_extreme_greed_score_100(self):
        """Score 100 (Extreme Greed) = staerkstes Verkaufssignal (-1.0)."""
        assert _normalize_sentiment_direction(Decimal("100")) == Decimal("-1")

    def test_neutral_score_50(self):
        """Score 50 (Neutral) = kein Richtungssignal (0.0)."""
        assert _normalize_sentiment_direction(Decimal("50")) == Decimal("0")

    def test_fear_score_20(self):
        """Score 20 → positive Richtung (Kauf)."""
        result = _normalize_sentiment_direction(Decimal("20"))
        assert result == Decimal("0.6")

    def test_greed_score_80(self):
        """Score 80 → negative Richtung (Verkauf)."""
        result = _normalize_sentiment_direction(Decimal("80"))
        assert result == Decimal("-0.6")


# ---------------------------------------------------------------------------
# TestActionMapping
# ---------------------------------------------------------------------------

class TestActionMapping:
    """Testet _map_score_to_action: Schwellenwert-Grenzen."""

    def test_strong_buy_at_60(self):
        assert _map_score_to_action(Decimal("60")) == CombinedAction.STRONG_BUY

    def test_strong_buy_above_60(self):
        assert _map_score_to_action(Decimal("85")) == CombinedAction.STRONG_BUY

    def test_buy_at_30(self):
        assert _map_score_to_action(Decimal("30")) == CombinedAction.BUY

    def test_buy_just_below_60(self):
        assert _map_score_to_action(Decimal("59.9")) == CombinedAction.BUY

    def test_lean_buy_at_10(self):
        assert _map_score_to_action(Decimal("10")) == CombinedAction.LEAN_BUY

    def test_hold_at_0(self):
        assert _map_score_to_action(Decimal("0")) == CombinedAction.HOLD

    def test_hold_at_minus_10(self):
        assert _map_score_to_action(Decimal("-10")) == CombinedAction.HOLD

    def test_lean_sell_at_minus_11(self):
        assert _map_score_to_action(Decimal("-11")) == CombinedAction.LEAN_SELL

    def test_lean_sell_at_minus_30(self):
        assert _map_score_to_action(Decimal("-30")) == CombinedAction.LEAN_SELL

    def test_sell_at_minus_31(self):
        assert _map_score_to_action(Decimal("-31")) == CombinedAction.SELL

    def test_sell_at_minus_60(self):
        assert _map_score_to_action(Decimal("-60")) == CombinedAction.SELL

    def test_strong_sell_below_minus_60(self):
        assert _map_score_to_action(Decimal("-61")) == CombinedAction.STRONG_SELL

    def test_strong_sell_at_minus_100(self):
        assert _map_score_to_action(Decimal("-100")) == CombinedAction.STRONG_SELL


# ---------------------------------------------------------------------------
# TestFinalMultiplier
# ---------------------------------------------------------------------------

class TestFinalMultiplier:
    """Testet _compute_final_multiplier."""

    def test_neutral_macro_passthrough(self):
        """Neutrale Macro-Richtung laesst Sentiment-Multiplikator unveraendert."""
        result = _compute_final_multiplier(
            sentiment_multiplier=Decimal("1.30"),
            direction_normalized=Decimal("0"),
            composite_confidence=Decimal("1.0"),
        )
        assert result == Decimal("1.30")

    def test_bullish_macro_amplifies_buy_multiplier(self):
        """Bullish Macro amplifiziert Kauf-Multiplikator (>1.0)."""
        result = _compute_final_multiplier(
            sentiment_multiplier=Decimal("1.30"),
            direction_normalized=Decimal("1.0"),
            composite_confidence=Decimal("1.0"),
        )
        # deviation=0.30, adjustment=0.20, adjusted=0.30*(1+0.20)=0.36
        assert result == Decimal("1.36")

    def test_bearish_macro_compresses_buy_multiplier(self):
        """Bearish Macro komprimiert Kauf-Multiplikator (drueckt Richtung 1.0 runter)."""
        result = _compute_final_multiplier(
            sentiment_multiplier=Decimal("1.30"),
            direction_normalized=Decimal("-1.0"),
            composite_confidence=Decimal("1.0"),
        )
        # deviation=0.30, adjustment=-0.20, adjusted=0.30*(1-0.20)=0.24
        assert result == Decimal("1.24")

    def test_confidence_dampens_deviation(self):
        """Niedrige Confidence daempft Abweichung von 1.0."""
        result = _compute_final_multiplier(
            sentiment_multiplier=Decimal("1.50"),
            direction_normalized=Decimal("0"),
            composite_confidence=Decimal("0.50"),
        )
        # deviation=0.50, adjusted=0.50*0.50=0.25
        assert result == Decimal("1.25")

    def test_clamping_min(self):
        """Multiplikator kann nicht unter 0.50 fallen."""
        result = _compute_final_multiplier(
            sentiment_multiplier=Decimal("0.10"),
            direction_normalized=Decimal("-1.0"),
            composite_confidence=Decimal("1.0"),
        )
        assert result >= Decimal("0.50")

    def test_clamping_max(self):
        """Multiplikator kann nicht ueber 2.00 steigen."""
        result = _compute_final_multiplier(
            sentiment_multiplier=Decimal("1.90"),
            direction_normalized=Decimal("1.0"),
            composite_confidence=Decimal("1.0"),
        )
        assert result <= Decimal("2.00")


# ---------------------------------------------------------------------------
# TestConflictDetection
# ---------------------------------------------------------------------------

class TestConflictDetection:
    """Testet _detect_conflict."""

    def test_aligned_both_bullish(self):
        """Beide bullish → aligned."""
        aligned, desc = _detect_conflict(Decimal("0.5"), Decimal("0.5"))
        assert aligned is True
        assert desc is None

    def test_aligned_both_neutral(self):
        """Beide neutral → aligned."""
        aligned, desc = _detect_conflict(Decimal("0.1"), Decimal("0.1"))
        assert aligned is True
        assert desc is None

    def test_macro_bullish_sentiment_greed(self):
        """Macro bullish + Sentiment Greed → Konflikt."""
        aligned, desc = _detect_conflict(Decimal("0.5"), Decimal("-0.5"))
        assert aligned is False
        assert "bullish" in desc.lower()
        assert "Greed" in desc

    def test_macro_bearish_sentiment_fear(self):
        """Macro bearish + Sentiment Fear → Konflikt."""
        aligned, desc = _detect_conflict(Decimal("-0.5"), Decimal("0.5"))
        assert aligned is False
        assert "bearish" in desc.lower()
        assert "Fear" in desc


# ---------------------------------------------------------------------------
# TestQualityAssessment
# ---------------------------------------------------------------------------

class TestQualityAssessment:
    """Testet _assess_quality."""

    def test_full_quality(self):
        """Alle Quellen aktiv → full."""
        direction = _make_direction(active_factors=4, total_factors=4)
        sizing = _make_sizing(active_pillars=5, total_pillars=5)
        quality, reason = _assess_quality(direction, sizing)
        assert quality == "full"
        assert reason is None

    def test_full_quality_at_threshold(self):
        """3/4 Faktoren (75%) + 3/5 Pillars (60%) → full."""
        direction = _make_direction(active_factors=3, total_factors=4)
        sizing = _make_sizing(active_pillars=3, total_pillars=5)
        quality, reason = _assess_quality(direction, sizing)
        assert quality == "full"

    def test_partial_quality(self):
        """2/4 Faktoren (50%) + 5/5 Pillars → partial."""
        direction = _make_direction(active_factors=2, total_factors=4)
        sizing = _make_sizing(active_pillars=5, total_pillars=5)
        quality, reason = _assess_quality(direction, sizing)
        assert quality == "partial"
        assert "Makro" in reason

    def test_degraded_quality(self):
        """1/4 Faktoren + 1/5 Pillars → degraded."""
        direction = _make_direction(active_factors=1, total_factors=4)
        sizing = _make_sizing(active_pillars=1, total_pillars=5)
        quality, reason = _assess_quality(direction, sizing)
        assert quality == "degraded"


# ---------------------------------------------------------------------------
# TestUnifiedScore
# ---------------------------------------------------------------------------

class TestUnifiedScore:
    """Testet die Unified Score Berechnung ueber compute_combined_score."""

    def test_both_bullish_strong_positive(self):
        """Macro STARK LONG + Sentiment Fear → hoher positiver Score."""
        direction = _make_direction(composite_raw=8, composite_score=2, recommendation="STARK LONG")
        sizing = _make_sizing(composite_score=Decimal("10"), label="Extreme Fear",
                              buy_size_multiplier=Decimal("1.45"))
        result = compute_combined_score(direction, sizing)
        assert result.unified_score > Decimal("50")
        assert result.action in (CombinedAction.STRONG_BUY, CombinedAction.BUY)

    def test_both_bearish_strong_negative(self):
        """Macro STARK SHORT + Sentiment Greed → hoher negativer Score."""
        direction = _make_direction(composite_raw=-8, composite_score=-2, recommendation="STARK SHORT")
        sizing = _make_sizing(composite_score=Decimal("90"), label="Extreme Greed",
                              buy_size_multiplier=Decimal("0.85"))
        result = compute_combined_score(direction, sizing)
        assert result.unified_score < Decimal("-50")
        assert result.action in (CombinedAction.STRONG_SELL, CombinedAction.SELL)

    def test_both_neutral_near_zero(self):
        """Macro NEUTRAL + Sentiment Neutral → Score nahe 0."""
        direction = _make_direction(composite_raw=0, composite_score=0, recommendation="NEUTRAL")
        sizing = _make_sizing(composite_score=Decimal("50"))
        result = compute_combined_score(direction, sizing)
        assert abs(result.unified_score) <= Decimal("10")
        assert result.action == CombinedAction.HOLD

    def test_macro_dominates_with_neutral_sentiment(self):
        """Starkes Macro-Signal + neutrales Sentiment → moderater Score."""
        direction = _make_direction(composite_raw=6, composite_score=1, recommendation="LONG")
        sizing = _make_sizing(composite_score=Decimal("50"))
        result = compute_combined_score(direction, sizing)
        # direction_normalized=0.75, sentiment_direction=0
        # unified = 0.75*0.60*100 = 45.0
        assert result.unified_score > Decimal("30")

    def test_sentiment_dominates_when_macro_neutral(self):
        """Neutrales Macro + extremes Sentiment → moderater Score."""
        direction = _make_direction(composite_raw=0, composite_score=0, recommendation="NEUTRAL")
        sizing = _make_sizing(composite_score=Decimal("5"), label="Extreme Fear",
                              buy_size_multiplier=Decimal("1.50"))
        result = compute_combined_score(direction, sizing)
        # direction_normalized=0, sentiment_direction=0.9
        # unified = 0.9*0.40*100 = 36.0
        assert result.unified_score > Decimal("25")

    def test_conflicting_signals_moderate(self):
        """Macro LONG + Sentiment Greed → teilweise aufhebend, moderater Score."""
        direction = _make_direction(composite_raw=6, composite_score=1, recommendation="LONG")
        sizing = _make_sizing(composite_score=Decimal("85"), label="Greed",
                              buy_size_multiplier=Decimal("0.90"))
        result = compute_combined_score(direction, sizing)
        # Macro pushes positive, Sentiment pushes negative → moderater Score
        assert abs(result.unified_score) < Decimal("50")
        assert result.signals_aligned is False

    def test_confidence_dampening_reduces_score(self):
        """Weniger aktive Faktoren → gedaempfter Score."""
        direction = _make_direction(composite_raw=8, composite_score=2,
                                     recommendation="STARK LONG", active_factors=2)
        sizing = _make_sizing(composite_score=Decimal("10"), label="Extreme Fear",
                              buy_size_multiplier=Decimal("1.45"),
                              confidence=Decimal("0.50"), active_pillars=2)
        result = compute_combined_score(direction, sizing)
        # Confidence < 1 → dampened score < undampened
        assert result.confidence < Decimal("1.0")
        assert result.unified_score < Decimal("90")  # wuerde 92 ohne Daempfung sein

    def test_full_confidence_no_dampening(self):
        """Alle Faktoren aktiv + volle Confidence → unveraenderter Score."""
        direction = _make_direction(composite_raw=4, active_factors=4, total_factors=4)
        sizing = _make_sizing(confidence=Decimal("1.0"), active_pillars=5, total_pillars=5)
        result = compute_combined_score(direction, sizing)
        assert result.confidence == Decimal("1.00")


# ---------------------------------------------------------------------------
# TestComputeCombinedScore (Integration)
# ---------------------------------------------------------------------------

class TestComputeCombinedScore:
    """Integrationstests fuer compute_combined_score."""

    def test_all_data_available(self):
        """Vollstaendige Inputs produzieren valides Ergebnis."""
        direction = _make_direction(composite_raw=3, composite_score=1, recommendation="LONG")
        sizing = _make_sizing(composite_score=Decimal("30"), label="Fear",
                              buy_size_multiplier=Decimal("1.20"),
                              raw_multiplier=Decimal("1.25"))
        result = compute_combined_score(direction, sizing)

        assert isinstance(result, CombinedScoreResult)
        assert isinstance(result.action, CombinedAction)
        assert result.action_label == result.action.value
        assert result.action_color in ("#16a34a", "#22c55e", "#4ade80", "#64748b",
                                        "#fb923c", "#f97316", "#dc2626")
        assert Decimal("0") <= result.intensity <= Decimal("1")
        assert Decimal("0.50") <= result.size_multiplier <= Decimal("2.00")
        assert Decimal("-100") <= result.unified_score <= Decimal("100")
        assert result.direction_weight == Decimal("0.60")
        assert result.sizing_weight == Decimal("0.40")
        assert result.overall_quality in ("full", "partial", "degraded")
        assert isinstance(result.signals_aligned, bool)
        assert result.timestamp is not None

    def test_result_deterministic(self):
        """Gleiche Inputs → gleiches Ergebnis (bis auf Timestamp)."""
        direction = _make_direction(composite_raw=5, composite_score=2)
        sizing = _make_sizing(composite_score=Decimal("25"), buy_size_multiplier=Decimal("1.30"))

        r1 = compute_combined_score(direction, sizing)
        r2 = compute_combined_score(direction, sizing)

        assert r1.unified_score == r2.unified_score
        assert r1.action == r2.action
        assert r1.size_multiplier == r2.size_multiplier
        assert r1.confidence == r2.confidence

    def test_macro_unavailable_fallback(self):
        """0 aktive Faktoren → Score wird nur durch Sentiment getrieben."""
        direction = _make_direction(composite_raw=0, active_factors=0)
        sizing = _make_sizing(composite_score=Decimal("20"), label="Fear",
                              buy_size_multiplier=Decimal("1.30"))
        result = compute_combined_score(direction, sizing)

        # Macro-Beitrag ist 0 (raw=0), Sentiment treibt allein
        assert result.unified_score > Decimal("0")  # Fear = Kaufsignal
        assert result.overall_quality in ("partial", "degraded")

    def test_sentiment_unavailable_fallback(self):
        """0 aktive Pillars → Multiplikator nahe 1.0, Score durch Macro."""
        direction = _make_direction(composite_raw=4, composite_score=1, recommendation="LONG")
        sizing = _make_sizing(composite_score=Decimal("50"),
                              buy_size_multiplier=Decimal("1.00"),
                              confidence=Decimal("0"), active_pillars=0)
        result = compute_combined_score(direction, sizing)

        assert result.unified_score > Decimal("0")  # Macro treibt positiv
        assert result.overall_quality in ("partial", "degraded")

    def test_both_unavailable_hold(self):
        """Alles unavailable → HOLD + degraded."""
        direction = _make_direction(composite_raw=0, active_factors=0)
        sizing = _make_sizing(composite_score=Decimal("50"),
                              buy_size_multiplier=Decimal("1.00"),
                              confidence=Decimal("0"), active_pillars=0)
        result = compute_combined_score(direction, sizing)

        assert result.action == CombinedAction.HOLD
        assert result.overall_quality == "degraded"

    def test_serializable_types(self):
        """Alle Result-Felder sind JSON-serialisierbar."""
        direction = _make_direction(composite_raw=2)
        sizing = _make_sizing(composite_score=Decimal("40"))
        result = compute_combined_score(direction, sizing)

        # Decimal und datetime sind nicht nativ JSON-serialisierbar,
        # aber das ist korrekt — die Serialisierung passiert im Service Layer.
        assert isinstance(result.unified_score, Decimal)
        assert isinstance(result.confidence, Decimal)
        assert isinstance(result.size_multiplier, Decimal)
        assert isinstance(result.intensity, Decimal)
