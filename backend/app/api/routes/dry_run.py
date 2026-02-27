"""Dry-Run API Endpoints"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.dry_run_service import get_dry_run_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dry-run", tags=["dry-run"])

VALID_ACTIONS = {"BUY", "SELL", "HOLD", "NO_SIGNAL"}


@router.get("/{user_id}/status")
def get_status(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Dry-Run Status fuer einen User abrufen.

    Gibt is_active, Positionen, virtuelle P&L, Trade-Statistiken,
    Initial-Kapital, Cash und Total Equity zurueck.
    """
    try:
        service = get_dry_run_service()
        return service.get_status(user_id, db)
    except Exception:
        logger.exception("Dry-Run Status fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/toggle")
async def toggle_dry_run(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Dry-Run Modus ein-/ausschalten.

    Gibt den neuen Status zurueck (is_active, message).
    Erstellt bei Erstaktivierung ein virtuelles Portfolio mit Initial-Kapital
    aus den User-Settings.
    """
    try:
        service = get_dry_run_service()
        return await service.toggle_dry_run(user_id, db)
    except Exception:
        logger.exception("Dry-Run Toggle fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/decisions")
def get_decisions(
    user_id: str,
    from_date: Optional[str] = Query(
        default=None, description="Start-Datum (ISO 8601)"
    ),
    to_date: Optional[str] = Query(default=None, description="End-Datum (ISO 8601)"),
    action: Optional[str] = Query(
        default=None, description="Action-Filter (BUY/SELL/HOLD/NO_SIGNAL)"
    ),
    symbol: Optional[str] = Query(
        default=None, description="Symbol-Filter (z.B. BTCEUR)"
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Filterbares Decision Log abrufen.

    Unterstuetzt Filter nach Datum, Action-Typ und Symbol.
    Paginierung ueber limit/offset.
    """
    if action and action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action muss einer von {sorted(VALID_ACTIONS)} sein",
        )

    try:
        service = get_dry_run_service()
        return service.get_decisions(
            user_id=user_id,
            db=db,
            from_date=from_date,
            to_date=to_date,
            action=action,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )
    except Exception:
        logger.exception("Dry-Run Decisions fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/decisions/{decision_id}")
def get_decision_detail(
    user_id: str,
    decision_id: str,
    db: Session = Depends(get_db),
):
    """
    Einzelne Decision mit vollem Faktor-Breakdown abrufen.
    """
    try:
        service = get_dry_run_service()
        result = service.get_decision(user_id, decision_id, db)
        if result is None:
            raise HTTPException(status_code=404, detail="Decision nicht gefunden")
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Dry-Run Decision Detail fehlgeschlagen fuer user=%s, decision=%s",
            user_id,
            decision_id,
        )
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/reset")
async def reset_portfolio(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Virtuelles Portfolio zuruecksetzen.

    Loescht virtuelle Positionen und setzt P&L/Cash zurueck.
    Decision Log bleibt erhalten (separate Tabelle).
    is_active Status bleibt unveraendert.
    """
    try:
        service = get_dry_run_service()
        return await service.reset_portfolio(user_id, db)
    except Exception:
        logger.exception("Dry-Run Reset fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/portfolio")
def get_portfolio(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Aktuelles virtuelles Portfolio abrufen.

    Gibt Initial-Kapital, Cash, Equity, P&L, Positionen,
    Trade-Statistiken und Aktivierungszeitpunkt zurueck.
    """
    try:
        service = get_dry_run_service()
        return service.get_portfolio(user_id, db)
    except Exception:
        logger.exception("Dry-Run Portfolio fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
