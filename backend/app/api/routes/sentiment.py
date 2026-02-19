"""Sentiment API Endpoint (v3)"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.sentiment_data_service import get_sentiment_data_service
from app.symbol_registry import KNOWN_PAIRS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])


@router.get("/{user_id}/current")
async def get_sentiment_current(
    user_id: str,  # noqa: ARG001 — Path-Param fuer API-Konsistenz + Logging (reserviert fuer Sentiment-History)
    symbol: str = Query(
        default="BTCEUR",
        description="Trading-Paar fuer Kline-Daten",
    ),
):
    """
    Liefert den aktuellen Sentiment Score (v3).

    user_id ist im Pfad fuer API-Konsistenz mit anderen Endpoints und Logging.
    Sentiment-Daten sind aktuell nicht user-spezifisch (reserviert fuer Sentiment-History).

    Berechnet aus 5 Pillars (Correlation-gewichtet):
    - Fear & Greed Index (28%) - Alternative.me
    - Funding Rate (20%) - OKX
    - Taker Buy/Sell Ratio (18%) - Binance
    - Trend-Deviation / DMA-Composite (42%) - Binance
    - Volume-Momentum (12%) - Binance

    Features:
    - Piecewise-Linear Multiplier (keine Bucket-Spruenge)
    - Pillar-Dispersion als Konfidenz-Faktor
    - Volatility-Scaling (20d vs 120d Vol)
    """
    if symbol not in KNOWN_PAIRS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol nicht unterstuetzt. Erlaubt: {', '.join(sorted(KNOWN_PAIRS))}",
        )
    try:
        service = get_sentiment_data_service()
        return await asyncio.wait_for(
            asyncio.to_thread(service.get_sentiment, symbol=symbol),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.error("Sentiment Timeout fuer user=%s, symbol=%s", user_id, symbol)
        raise HTTPException(status_code=504, detail="Sentiment-Berechnung Timeout")
    except Exception:
        logger.exception("Sentiment endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
