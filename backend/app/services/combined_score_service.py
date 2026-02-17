"""
Combined Score Service — Orchestriert MacroSignal + Sentiment.

Kein eigener Cache: nutzt Sub-Service-Caches (MacroDataService 30s,
SentimentDataService 5-30min). Jeder Aufruf holt frische Daten von
beiden Sub-Services und kombiniert sie via pure Domain-Logik.
"""

import logging
import threading
from decimal import Decimal
from typing import Optional

from app.domain.combined_score import (
    CombinedScoreResult,
    DirectionInput,
    SizingInput,
    compute_combined_score,
)
from app.services.macro_data_service import get_macro_data_service
from app.services.sentiment_data_service import get_sentiment_data_service

logger = logging.getLogger(__name__)


class CombinedScoreService:
    """Orchestriert MacroSignal + Sentiment zu Combined Score."""

    def get_combined_score(
        self,
        interval_minutes: int = 15,
        symbol: str = "BTCEUR",
    ) -> dict:
        """
        Holt beide Signale und berechnet den Combined Score.

        Args:
            interval_minutes: MacroSignal-Intervall (1, 5, 15)
            symbol: Trading-Paar fuer Sentiment-Daten

        Returns:
            Serialisiertes dict mit Combined Score + Sub-Signal-Details.
        """
        # 1. MacroSignal abrufen
        macro_service = get_macro_data_service()
        macro_result = macro_service.get_signal(interval_minutes=interval_minutes)

        # 2. Sentiment abrufen
        sentiment_service = get_sentiment_data_service()
        sentiment_data = sentiment_service.get_sentiment(symbol=symbol)

        # 3. Domain-Inputs bauen
        direction = DirectionInput(
            composite_score=macro_result.composite_score,
            composite_raw=macro_result.composite_raw,
            recommendation=macro_result.recommendation,
            active_factors=macro_result.active_factors,
            total_factors=macro_result.total_factors,
            interval_minutes=macro_result.interval_minutes,
        )

        sizing = SizingInput(
            composite_score=Decimal(str(sentiment_data["composite_score"])),
            label=sentiment_data["composite_label"],
            buy_size_multiplier=Decimal(
                str(sentiment_data["recommendation"]["buy_size_multiplier"])
            ),
            raw_multiplier=Decimal(
                str(sentiment_data["recommendation"]["raw_multiplier"])
            ),
            confidence=Decimal(str(sentiment_data["dispersion"]["confidence_factor"])),
            active_pillars=sentiment_data["active_pillars"],
            total_pillars=sentiment_data["total_pillars"],
        )

        # 4. Combined Score berechnen (pure Domain-Logik)
        result = compute_combined_score(direction, sizing)

        # 5. Serialisieren inkl. Sub-Signal-Details
        return self._serialize(result, macro_result, sentiment_data)

    @staticmethod
    def _serialize(
        result: CombinedScoreResult,
        macro_result,
        sentiment_data: dict,
    ) -> dict:
        """Serialisiert CombinedScoreResult fuer JSON-Response."""
        return {
            # Primaere Ausgabe
            "action": result.action_label,
            "action_color": result.action_color,
            "intensity": float(result.intensity),
            "size_multiplier": float(result.size_multiplier),
            "unified_score": float(result.unified_score),
            # Qualitaet
            "overall_quality": result.overall_quality,
            "quality_reason": result.quality_reason,
            "confidence": float(result.confidence),
            "signals_aligned": result.signals_aligned,
            "conflict_description": result.conflict_description,
            # Direction Sub-Signal (MacroSignal Zusammenfassung)
            "direction": {
                "composite_score": result.direction.composite_score,
                "composite_raw": result.direction.composite_raw,
                "recommendation": result.direction.recommendation,
                "active_factors": result.direction.active_factors,
                "total_factors": result.direction.total_factors,
                "interval_minutes": result.direction.interval_minutes,
                "weight": float(result.direction_weight),
            },
            # Sizing Sub-Signal (Sentiment Zusammenfassung)
            "sizing": {
                "composite_score": float(result.sizing.composite_score),
                "label": result.sizing.label,
                "buy_size_multiplier": float(result.sizing.buy_size_multiplier),
                "raw_multiplier": float(result.sizing.raw_multiplier),
                "confidence": float(result.sizing.confidence),
                "active_pillars": result.sizing.active_pillars,
                "total_pillars": result.sizing.total_pillars,
                "weight": float(result.sizing_weight),
            },
            # Detail-Daten fuer Transparenz
            "macro_detail": {
                "scores": [
                    {
                        "factor": s.factor,
                        "score": s.score,
                        "reason": s.reason,
                        "direction": s.direction,
                    }
                    for s in macro_result.scores
                ],
                "recommendation_color": macro_result.recommendation_color,
            },
            "sentiment_detail": {
                "pillars": sentiment_data.get("pillars", []),
                "dispersion": sentiment_data.get("dispersion"),
                "volatility": sentiment_data.get("volatility"),
            },
            "timestamp": result.timestamp.isoformat(),
        }


# ─── Singleton ───

_service_instance: Optional[CombinedScoreService] = None
_service_lock = threading.Lock()


def get_combined_score_service() -> CombinedScoreService:
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = CombinedScoreService()
    return _service_instance
