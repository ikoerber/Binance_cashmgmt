"""Makro-Signal API Endpoint"""
from fastapi import APIRouter, Query

from app.services.macro_data_service import get_macro_data_service

router = APIRouter(prefix="/api/macro", tags=["macro"])


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
                "change_value": float(s.change_value) if s.change_value is not None else None,
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
