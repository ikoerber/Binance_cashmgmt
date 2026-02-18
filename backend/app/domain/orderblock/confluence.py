"""
Orderblock Confluence – Sentiment-OB Cross-Referenz.

Berechnet Confluence zwischen Sentiment-Score und Orderblock-Richtung.
Kontraere Konstellationen (Fear + Bullish bzw. Greed + Bearish) erhalten
einen Score-Boost, gleichgerichtete einen Abschlag.
"""

from decimal import Decimal
from typing import List, Optional

from app.domain.orderblock.models import (
    ConfluenceLabel,
    OBDirection,
    Orderblock,
    SentimentConfluence,
)
from app.domain.orderblock.scoring import _clamp


def compute_sentiment_confluence(
    sentiment_score: Decimal,
    ob_direction: OBDirection,
    conviction_score: Decimal,
) -> SentimentConfluence:
    """
    Berechnet Sentiment-OB Confluence.

    Kontraere Konstellationen (Fear + Bullish bzw. Greed + Bearish) erhalten
    einen Score-Boost, gleichgerichtete Konstellationen einen Abschlag.

    BULLISH OB + Sentiment < 30:  STRONG_CONTRARIAN  (×1.3)
    BULLISH OB + Sentiment 30-45: MODERATE_CONTRARIAN (×1.15)
    BULLISH OB + Sentiment > 70:  ADVERSE            (×0.85)
    BEARISH OB + Sentiment > 70:  STRONG_CONTRARIAN  (×1.3)
    BEARISH OB + Sentiment 55-70: MODERATE_CONTRARIAN (×1.15)
    BEARISH OB + Sentiment < 30:  ADVERSE            (×0.85)
    Sonst:                        NEUTRAL             (×1.0)

    Pure Funktion. Alle Werte Decimal, niemals float.
    """
    _30 = Decimal("30")
    _45 = Decimal("45")
    _55 = Decimal("55")
    _70 = Decimal("70")
    _hundred = Decimal("100")

    if ob_direction == OBDirection.BULLISH:
        if sentiment_score < _30:
            label = ConfluenceLabel.STRONG_CONTRARIAN
            mult = Decimal("1.3")
        elif sentiment_score < _45:
            label = ConfluenceLabel.MODERATE_CONTRARIAN
            mult = Decimal("1.15")
        elif sentiment_score > _70:
            label = ConfluenceLabel.ADVERSE
            mult = Decimal("0.85")
        else:
            label = ConfluenceLabel.NEUTRAL
            mult = Decimal("1")
    else:  # BEARISH
        if sentiment_score > _70:
            label = ConfluenceLabel.STRONG_CONTRARIAN
            mult = Decimal("1.3")
        elif sentiment_score > _55:
            label = ConfluenceLabel.MODERATE_CONTRARIAN
            mult = Decimal("1.15")
        elif sentiment_score < _30:
            label = ConfluenceLabel.ADVERSE
            mult = Decimal("0.85")
        else:
            label = ConfluenceLabel.NEUTRAL
            mult = Decimal("1")

    conf_score = _clamp(conviction_score * mult, Decimal("0"), _hundred)

    return SentimentConfluence(
        confluence_score=conf_score,
        confluence_label=label,
        sentiment_at_detection=sentiment_score,
    )


def annotate_zones_with_confluence(
    zones: List["Orderblock"],
    sentiment_score: Optional[Decimal],
) -> None:
    """
    Annotiert Orderblock-Zonen mit Sentiment-Confluence (in-place).

    Fuer jede Zone wird compute_sentiment_confluence() aufgerufen und
    die Confluence-Felder gesetzt.

    Args:
        zones: Liste von Orderblock-Zonen (werden in-place modifiziert)
        sentiment_score: Aktueller Sentiment Composite Score (0-100), oder None
    """
    if sentiment_score is None:
        return

    for zone in zones:
        confluence = compute_sentiment_confluence(
            sentiment_score, zone.direction, zone.conviction_score
        )
        zone.sentiment_at_detection = confluence.sentiment_at_detection
        zone.confluence_label = confluence.confluence_label.value
        zone.confluence_score = confluence.confluence_score
