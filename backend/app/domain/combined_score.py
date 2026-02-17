"""
Combined Score Domain-Logik (pure, kein I/O).

Fuehrt MacroSignal (Richtung) und Sentiment (Sizing) zu einer
einheitlichen Handlungsempfehlung zusammen:
  - MacroSignal (60%): Kurzfristige Richtung (-2 bis +2)
  - Sentiment (40%): Mittelfristiges Position-Sizing (0-100)

Unified Score: -100 bis +100 (negativ = Sell-Seite, positiv = Buy-Seite)
Action: 7 Stufen von "Aggressiv kaufen" bis "Aggressiv verkaufen"
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIRECTION_WEIGHT = Decimal("0.60")
SIZING_WEIGHT = Decimal("0.40")

# MacroSignal raw score range
MACRO_RAW_MAX = Decimal("8")

# Sentiment score midpoint (contrarian)
SENTIMENT_MID = Decimal("50")

# Conflict detection threshold
CONFLICT_THRESHOLD = Decimal("0.25")


class CombinedAction(Enum):
    """7-stufige Handlungsempfehlung."""

    STRONG_BUY = "Aggressiv kaufen"
    BUY = "Kaufen"
    LEAN_BUY = "Leicht akkumulieren"
    HOLD = "Abwarten"
    LEAN_SELL = "Leicht reduzieren"
    SELL = "Verkaufen"
    STRONG_SELL = "Aggressiv verkaufen"


ACTION_THRESHOLDS = [
    (Decimal("60"), CombinedAction.STRONG_BUY),
    (Decimal("30"), CombinedAction.BUY),
    (Decimal("10"), CombinedAction.LEAN_BUY),
    (Decimal("-10"), CombinedAction.HOLD),
    (Decimal("-30"), CombinedAction.LEAN_SELL),
    (Decimal("-60"), CombinedAction.SELL),
    # Below -60: STRONG_SELL
]

ACTION_COLORS = {
    CombinedAction.STRONG_BUY: "#16a34a",
    CombinedAction.BUY: "#22c55e",
    CombinedAction.LEAN_BUY: "#4ade80",
    CombinedAction.HOLD: "#64748b",
    CombinedAction.LEAN_SELL: "#fb923c",
    CombinedAction.SELL: "#f97316",
    CombinedAction.STRONG_SELL: "#dc2626",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DirectionInput:
    """Normalisierter MacroSignal-Input fuer Combined Scoring."""

    composite_score: int  # -2 bis +2 (gemapped)
    composite_raw: int  # -8 bis +8
    recommendation: str  # z.B. "STARK LONG"
    active_factors: int
    total_factors: int
    interval_minutes: int


@dataclass
class SizingInput:
    """Normalisierter Sentiment-Input fuer Combined Scoring."""

    composite_score: Decimal  # 0-100
    label: str  # z.B. "Fear", "Neutral", "Greed"
    buy_size_multiplier: Decimal  # 0.85 - 1.50 (final, nach Dispersion + Vol)
    raw_multiplier: Decimal  # Vor Adjustierungen
    confidence: Decimal  # Dispersion Confidence 0-1
    active_pillars: int
    total_pillars: int


@dataclass
class CombinedScoreResult:
    """Vollstaendiges Combined Score Ergebnis."""

    # Primaere Ausgabe
    action: CombinedAction
    action_label: str  # Deutscher Text aus CombinedAction.value
    action_color: str
    intensity: Decimal  # 0.0 bis 1.0 (Signalstaerke)
    size_multiplier: Decimal  # Finaler Kaufgroessen-Multiplikator

    # Unified Score: -100 bis +100
    unified_score: Decimal

    # Direction-Komponente
    direction: DirectionInput
    direction_weight: Decimal

    # Sizing-Komponente
    sizing: SizingInput
    sizing_weight: Decimal

    # Qualitaet
    overall_quality: str  # "full", "partial", "degraded"
    quality_reason: Optional[str]
    confidence: Decimal  # 0-1, zusammengesetzte Confidence

    # Konflikterkennung
    signals_aligned: bool
    conflict_description: Optional[str]

    timestamp: datetime


# ---------------------------------------------------------------------------
# Pure Scoring Functions
# ---------------------------------------------------------------------------


def _normalize_direction(composite_raw: int) -> Decimal:
    """
    Normalisiert MacroSignal Raw Score (-8..+8) auf -1.0..+1.0.

    >>> _normalize_direction(8)
    Decimal('1.0')
    >>> _normalize_direction(-8)
    Decimal('-1.0')
    >>> _normalize_direction(0)
    Decimal('0.0')
    """
    normalized = Decimal(str(composite_raw)) / MACRO_RAW_MAX
    return max(Decimal("-1"), min(Decimal("1"), normalized))


def _normalize_sentiment_direction(composite_score: Decimal) -> Decimal:
    """
    Konvertiert Sentiment Score (0-100) zu kontrarerer Richtung (-1.0..+1.0).

    Fear (0) -> +1.0 (Kaufsignal)
    Neutral (50) -> 0.0
    Greed (100) -> -1.0 (Verkaufssignal)
    """
    direction = (SENTIMENT_MID - composite_score) / SENTIMENT_MID
    return max(Decimal("-1"), min(Decimal("1"), direction))


def _map_score_to_action(score: Decimal) -> CombinedAction:
    """Mappt Unified Score auf 7-stufige Action."""
    for threshold, action in ACTION_THRESHOLDS:
        if score >= threshold:
            return action
    return CombinedAction.STRONG_SELL


def _compute_final_multiplier(
    sentiment_multiplier: Decimal,
    direction_normalized: Decimal,
    composite_confidence: Decimal,
) -> Decimal:
    """
    Moduliert den Sentiment-Multiplikator durch Macro-Direction.

    Bullish Macro amplifiziert Kauf-Multiplikatoren, komprimiert Verkauf-Multiplikatoren.
    Bearish Macro komprimiert Kauf-Multiplikatoren, amplifiziert Verkauf-Multiplikatoren.
    Neutrale Macro laesst den Sentiment-Multiplikator unveraendert.

    Direction-Adjustment: max ±20%.
    Clamped auf 0.50 - 2.00.
    """
    # Abweichung vom Neutral-Multiplikator 1.0
    base_deviation = sentiment_multiplier - Decimal("1")

    # Richtungs-Adjustment: ±20% max
    direction_adjustment = direction_normalized * Decimal("0.20")
    adjusted = base_deviation * (Decimal("1") + direction_adjustment)

    # Confidence-Daempfung
    adjusted = adjusted * composite_confidence

    final = (Decimal("1") + adjusted).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(Decimal("0.50"), min(Decimal("2.00"), final))


def _detect_conflict(
    direction_normalized: Decimal,
    sentiment_direction: Decimal,
) -> tuple:
    """
    Erkennt Divergenz zwischen MacroSignal und Sentiment.

    Konflikt = ein Signal sagt Kauf, das andere Verkauf (beide ueber Schwelle).

    Returns:
        (signals_aligned: bool, conflict_description: Optional[str])
    """
    dir_bullish = direction_normalized > CONFLICT_THRESHOLD
    dir_bearish = direction_normalized < -CONFLICT_THRESHOLD
    sent_bullish = sentiment_direction > CONFLICT_THRESHOLD
    sent_bearish = sentiment_direction < -CONFLICT_THRESHOLD

    if dir_bullish and sent_bearish:
        return False, "Makro bullish, aber Sentiment im Greed-Bereich (Vorsicht)"
    if dir_bearish and sent_bullish:
        return (
            False,
            "Makro bearish, aber Sentiment im Fear-Bereich (Akkumulation moeglich)",
        )

    return True, None


def _assess_quality(
    direction: DirectionInput,
    sizing: SizingInput,
) -> tuple:
    """
    Bewertet die Gesamtqualitaet des Combined Score.

    Returns:
        (quality: str, quality_reason: Optional[str])
        - "full": >= 75% Makro-Faktoren UND >= 60% Sentiment-Pillars
        - "partial": >= 50% Makro ODER >= 40% Sentiment
        - "degraded": Unterhalb beider Schwellen
    """
    dir_ratio = direction.active_factors / max(1, direction.total_factors)
    siz_ratio = sizing.active_pillars / max(1, sizing.total_pillars)

    if dir_ratio >= 0.75 and siz_ratio >= 0.6:
        return "full", None

    reason_parts = []
    if dir_ratio < 0.75:
        reason_parts.append(
            f"Makro: {direction.active_factors}/{direction.total_factors} Faktoren"
        )
    if siz_ratio < 0.6:
        reason_parts.append(
            f"Sentiment: {sizing.active_pillars}/{sizing.total_pillars} Pillars"
        )

    if dir_ratio >= 0.5 or siz_ratio >= 0.4:
        return "partial", ", ".join(reason_parts)

    return "degraded", "Zu wenige aktive Datenquellen fuer zuverlaessiges Signal"


def compute_combined_score(
    direction: DirectionInput,
    sizing: SizingInput,
) -> CombinedScoreResult:
    """
    Hauptfunktion: Kombiniert MacroSignal (Richtung) mit Sentiment (Sizing).

    Pure function — kein I/O, deterministisch, verwendet nur Decimal.

    Args:
        direction: Normalisierter MacroSignal-Input
        sizing: Normalisierter Sentiment-Input

    Returns:
        CombinedScoreResult mit allen Feldern.
    """
    from app.domain.models import utcnow

    # 1. Normalisierung
    direction_normalized = _normalize_direction(direction.composite_raw)
    sentiment_direction = _normalize_sentiment_direction(sizing.composite_score)

    # 2. Unified Score
    unified_raw = (
        direction_normalized * DIRECTION_WEIGHT + sentiment_direction * SIZING_WEIGHT
    )
    unified_score = (unified_raw * Decimal("100")).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )

    # 3. Confidence Dampening
    direction_confidence = Decimal(str(direction.active_factors)) / Decimal(
        str(max(1, direction.total_factors))
    )
    sizing_pillar_ratio = Decimal(str(sizing.active_pillars)) / Decimal(
        str(max(1, sizing.total_pillars))
    )
    sizing_confidence = sizing_pillar_ratio * sizing.confidence
    composite_confidence = (
        direction_confidence * DIRECTION_WEIGHT + sizing_confidence * SIZING_WEIGHT
    )

    unified_dampened = (unified_score * composite_confidence).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )

    # 4. Action
    action = _map_score_to_action(unified_dampened)

    # 5. Finaler Multiplikator
    final_multiplier = _compute_final_multiplier(
        sizing.buy_size_multiplier, direction_normalized, composite_confidence
    )

    # 6. Konflikterkennung
    aligned, conflict_desc = _detect_conflict(direction_normalized, sentiment_direction)

    # 7. Qualitaet
    quality, quality_reason = _assess_quality(direction, sizing)

    # 8. Intensity: |unified_dampened| / 100
    intensity = abs(unified_dampened) / Decimal("100")
    intensity = min(Decimal("1"), intensity).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return CombinedScoreResult(
        action=action,
        action_label=action.value,
        action_color=ACTION_COLORS[action],
        intensity=intensity,
        size_multiplier=final_multiplier,
        unified_score=unified_dampened,
        direction=direction,
        direction_weight=DIRECTION_WEIGHT,
        sizing=sizing,
        sizing_weight=SIZING_WEIGHT,
        overall_quality=quality,
        quality_reason=quality_reason,
        confidence=composite_confidence.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        signals_aligned=aligned,
        conflict_description=conflict_desc,
        timestamp=utcnow(),
    )
