"""Combined Score API Endpoint (MacroSignal + Sentiment + Alpha Score)"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserSettingsDB
from app.services.combined_score_service import get_combined_score_service
from app.symbol_registry import KNOWN_PAIRS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/combined", tags=["combined"])


def _get_user_settings(user_id: str, db: Session) -> dict:
    """Laedt User-Settings oder gibt Defaults zurueck."""
    from app.api.routes.settings import _settings_to_dict, DEFAULTS

    settings = (
        db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
    )
    if settings:
        return _settings_to_dict(settings)
    return {"user_id": user_id, **DEFAULTS}


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
    db: Session = Depends(get_db),
):
    """
    Liefert den Combined Score: MacroSignal (Richtung) x Sentiment (Sizing) x Alpha Score.

    Kombiniert kurzfristiges Richtungssignal (1-15min) mit mittelfristigem
    Sentiment-Sizing und optionalem Alpha Score zu einer einheitlichen
    Handlungsempfehlung. Wenn Alpha Score nicht verfuegbar, Fallback auf 60/40.
    """
    if symbol not in KNOWN_PAIRS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol nicht unterstuetzt. Erlaubt: {', '.join(sorted(KNOWN_PAIRS))}",
        )

    try:
        settings = _get_user_settings(user_id, db)
    except Exception:
        logger.exception("Settings laden fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")

    try:
        service = get_combined_score_service()
        return await asyncio.wait_for(
            asyncio.to_thread(
                service.get_combined_score,
                interval_minutes=int(interval),
                symbol=symbol,
                user_id=user_id,
                settings=settings,
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.error("Combined Score Timeout fuer symbol=%s", symbol)
        raise HTTPException(status_code=504, detail="Combined Score Timeout")
    except Exception:
        logger.exception("Combined Score Berechnung fehlgeschlagen")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
