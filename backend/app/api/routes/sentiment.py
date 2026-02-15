"""Sentiment API Endpoint (v3)"""
import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.services.sentiment_data_service import get_sentiment_data_service

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])

ALLOWED_SYMBOLS = {"BTCEUR", "BTCUSDT"}


@router.get("/{user_id}/current")
async def get_sentiment_current(
    user_id: str,
    symbol: str = Query(
        default="BTCEUR",
        description="Trading-Paar fuer Kline-Daten",
    ),
):
    """
    Liefert den aktuellen Sentiment Score (v3).

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
    if symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol nicht unterstuetzt. Erlaubt: {', '.join(sorted(ALLOWED_SYMBOLS))}",
        )
    service = get_sentiment_data_service()
    return await asyncio.to_thread(service.get_sentiment, symbol=symbol)
