"""Makro-Signal API Endpoint"""
import logging
import math

from fastapi import APIRouter, HTTPException, Query

from app.services.macro_data_service import get_macro_data_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/macro", tags=["macro"])


def _safe_float(value) -> float | None:
    """Konvertiert Decimal/float sicher zu float. Gibt None bei NaN/Inf/None zurueck."""
    if value is None:
        return None
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


@router.get("/signals")
def get_macro_signals(
    interval: str = Query(
        default="15",
        pattern="^(1|5|15)$",
        description="Signal-Intervall in Minuten (1, 5, 15)",
    ),
):
    """
    Liefert aktuelle Makro-Indikatoren, Signal-Scores und Richtungsempfehlung.

    Query-Parameter:
    - interval: "1", "5" oder "15" (Minuten, Default: 15)

    Indikatoren:
    - BTC/USD (Binance)
    - EUR/USD (Twelve Data, Fallback: Binance)
    - DXY (Twelve Data)
    - US 2Y Yield (FRED)
    - DE 2Y Yield (ECB)
    - Spread US02Y-DE02Y (berechnet)
    - BTC/EUR (Binance, zur Anzeige)

    Scores: 4 Faktoren je -2 bis +2, mit direction ("direct"/"inverse")
    Empfehlung: STARK SHORT / SHORT / NEUTRAL / LONG / STARK LONG
    """
    try:
        service = get_macro_data_service()
        interval_minutes = int(interval)
        result = service.get_signal(interval_minutes=interval_minutes)

        return {
            "indicators": result.indicators,
            "scores": [
                {
                    "factor": s.factor,
                    "score": s.score,
                    "reason": s.reason,
                    "change_value": _safe_float(s.change_value),
                    "direction": s.direction,
                }
                for s in result.scores
            ],
            "composite_score": result.composite_score,
            "composite_raw": result.composite_raw,
            "recommendation": result.recommendation,
            "recommendation_color": result.recommendation_color,
            "timestamp": result.timestamp.isoformat(),
            "next_update": result.next_update.isoformat() if result.next_update else None,
            "active_factors": result.active_factors,
            "total_factors": result.total_factors,
            "interval_minutes": result.interval_minutes,
        }
    except Exception:
        logger.exception("Macro signal endpoint failed: interval=%s", interval)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
