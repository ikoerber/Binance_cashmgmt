"""Alpha Score API Endpoints (Multi-Factor Scoring Engine)"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserSettingsDB
from app.services.alpha_score_data_service import get_alpha_score_data_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alpha-score", tags=["alpha-score"])


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
async def get_alpha_score(
    user_id: str,
    symbol: str = Query(
        default="XRPBTC",
        description="Trading-Paar fuer Alpha Score Berechnung",
    ),
    db: Session = Depends(get_db),
):
    """
    Liefert den Alpha Score (-5 bis +5) mit Faktor-Breakdown und Regime-Info.

    Kombiniert 4 Faktoren (Z-Score, Lead-Lag, Orderbook, Funding) mit
    Hurst-basierter Regime-Erkennung zu einem gewichteten Alpha Score.
    Graceful Degradation bei fehlenden Datenquellen, Warmup-Status bei
    ungenuegender Datenhistorie.
    """
    try:
        settings = _get_user_settings(user_id, db)
    except Exception:
        logger.exception("Settings laden fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")

    try:
        service = get_alpha_score_data_service()
        result = await asyncio.wait_for(
            asyncio.to_thread(
                service.get_alpha_score,
                user_id=user_id,
                settings=settings,
            ),
            timeout=30,
        )
        return result
    except asyncio.TimeoutError:
        logger.error("Alpha Score Timeout fuer user=%s, symbol=%s", user_id, symbol)
        raise HTTPException(status_code=504, detail="Alpha Score Timeout")
    except Exception:
        logger.exception("Alpha Score Berechnung fehlgeschlagen")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/trailing-stops")
async def get_trailing_stops(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Liefert Trailing-Stop-Level pro Symbol (BTCEUR, XRPEUR).

    Stop-Level werden als Nebeneffekt von get_alpha_score() berechnet.
    Bei Erstaufruf ohne vorherigen Score-Abruf: leere Stops.
    Frozen-State zeigt Datenpausen an (frozen_since, data_points_needed).
    """
    try:
        settings = _get_user_settings(user_id, db)
    except Exception:
        logger.exception("Settings laden fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")

    try:
        service = get_alpha_score_data_service()
        result = await asyncio.wait_for(
            asyncio.to_thread(
                service.get_trailing_stops,
                user_id=user_id,
                settings=settings,
            ),
            timeout=10,
        )
        return result
    except asyncio.TimeoutError:
        logger.error("Trailing Stops Timeout fuer user=%s", user_id)
        raise HTTPException(status_code=504, detail="Trailing Stops Timeout")
    except Exception:
        logger.exception("Trailing Stops Abfrage fehlgeschlagen")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
