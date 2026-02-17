"""Combined Score API Endpoint (MacroSignal + Sentiment)"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.combined_score_service import get_combined_score_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/combined", tags=["combined"])

ALLOWED_SYMBOLS = {"BTCEUR"}


@router.get("/{user_id}/score")
async def get_combined_score(
    user_id: str,
    interval: str = Query(
        default="15",
        pattern="^(1|5|15)$",
        description="MacroSignal-Intervall in Minuten (1, 5, 15)",
    ),
    symbol: str = Query(
        default="BTCEUR",
        description="Trading-Paar fuer Sentiment-Daten",
    ),
):
    """
    Liefert den Combined Score: MacroSignal (Richtung) x Sentiment (Sizing).

    Kombiniert kurzfristiges Richtungssignal (1-15min) mit mittelfristigem
    Sentiment-Sizing zu einer einheitlichen Handlungsempfehlung.
    """
    if symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol nicht unterstuetzt. Erlaubt: {', '.join(sorted(ALLOWED_SYMBOLS))}",
        )

    try:
        service = get_combined_score_service()
        return await asyncio.wait_for(
            asyncio.to_thread(
                service.get_combined_score,
                interval_minutes=int(interval),
                symbol=symbol,
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.error("Combined Score Timeout fuer symbol=%s", symbol)
        raise HTTPException(status_code=504, detail="Combined Score Timeout")
    except Exception:
        logger.exception("Combined Score Berechnung fehlgeschlagen")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
