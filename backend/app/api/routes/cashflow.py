"""External Cashflow API Endpoints"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel

from app.db.database import get_db
from app.services.cashflow_service import (
    create_cashflow_event,
    list_cashflow_events,
    get_cashflow_event,
    update_cashflow_note as svc_update_note,
    reverse_cashflow_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cashflow", tags=["cashflow"])


# Request/Response Models
class CashflowCreateRequest(BaseModel):
    """Request body für External Cashflow Event"""
    asset: str  # "EUR" or "BTC"
    amount: str  # Decimal as string
    timestamp: Optional[str] = None  # ISO format, defaults to now
    note: Optional[str] = None
    category: Optional[str] = None  # z.B. "BANK_DEPOSIT", "WITHDRAWAL", etc.


class CashflowUpdateRequest(BaseModel):
    """Request body für Cashflow Update"""
    note: Optional[str] = None
    category: Optional[str] = None


@router.post("/{user_id}/create")
def create_external_cashflow(
    user_id: str,
    request: CashflowCreateRequest,
    db: Session = Depends(get_db)
):
    """Erstellt External Cashflow Event (z.B. Bank-Transfer)"""
    try:
        try:
            amount = Decimal(request.amount)
        except Exception:
            raise HTTPException(status_code=400, detail="amount muss eine gueltige Dezimalzahl sein")
        if amount.is_nan() or amount.is_infinite():
            raise HTTPException(status_code=400, detail="amount darf nicht NaN oder Infinity sein")

        try:
            timestamp = datetime.fromisoformat(request.timestamp) if request.timestamp else None
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="timestamp muss im ISO-Format sein (z.B. 2026-01-15T12:00:00)")

        if request.asset not in ("EUR", "BTC"):
            raise HTTPException(status_code=400, detail="asset muss 'EUR' oder 'BTC' sein")

        return create_cashflow_event(
            db, user_id, request.asset, amount,
            timestamp=timestamp, note=request.note, category=request.category,
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungueltige Eingabedaten")
    except Exception:
        logger.exception("Cashflow create failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/list")
def list_external_cashflows(
    user_id: str,
    asset: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Liste aller External Cashflow Events für einen User"""
    try:
        return list_cashflow_events(db, user_id, asset, limit, offset)
    except Exception:
        logger.exception("Cashflow endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/{event_id}")
def get_cashflow_detail(
    user_id: str,
    event_id: str,
    db: Session = Depends(get_db)
):
    """Holt Details eines External Cashflow Events"""
    try:
        event = get_cashflow_event(db, user_id, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Cashflow event not found")
        return event
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cashflow endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.patch("/{user_id}/{event_id}")
def update_cashflow_note(
    user_id: str,
    event_id: str,
    request: CashflowUpdateRequest,
    db: Session = Depends(get_db)
):
    """Updated Note/Kategorie eines Cashflow Events"""
    try:
        result = svc_update_note(db, user_id, event_id, request.note, request.category)
        if not result:
            raise HTTPException(status_code=404, detail="Cashflow event not found")
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cashflow endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.delete("/{user_id}/{event_id}")
def reverse_cashflow(
    user_id: str,
    event_id: str,
    db: Session = Depends(get_db)
):
    """Storniert External Cashflow Event via ADJUSTMENT (append-only)"""
    try:
        result = reverse_cashflow_event(db, user_id, event_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cashflow event not found")
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cashflow endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
