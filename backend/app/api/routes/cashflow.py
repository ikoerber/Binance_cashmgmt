"""External Cashflow API Endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel

from app.db.database import get_db
from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum
from app.domain.models import utcnow
import uuid

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
    """
    Erstellt External Cashflow Event (z.B. Bank-Transfer)

    Args:
        user_id: User ID
        request: Cashflow details
        db: Database Session (injected)

    Returns:
        Created cashflow event
    """
    try:
        # Parse amount
        amount = Decimal(request.amount)

        # Parse timestamp
        if request.timestamp:
            timestamp = datetime.fromisoformat(request.timestamp)
        else:
            timestamp = utcnow()

        # Create event
        event_id = str(uuid.uuid4())
        event_db = LedgerEventDB(
            id=event_id,
            user_id=user_id,
            type=EventTypeEnum.EXTERNAL_CASHFLOW,
            timestamp=timestamp,
            asset=request.asset,
            amount=amount,
            source=EventSourceEnum.EXTERNAL,
            note=f"{request.category}: {request.note}" if request.category and request.note else (request.category or request.note),
            created_at=utcnow()
        )

        db.add(event_db)
        db.commit()
        db.refresh(event_db)

        return {
            "id": event_db.id,
            "user_id": event_db.user_id,
            "type": event_db.type.value,
            "timestamp": event_db.timestamp.isoformat(),
            "asset": event_db.asset,
            "amount": str(event_db.amount),
            "note": event_db.note,
            "created_at": event_db.created_at.isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid amount: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/list")
def list_external_cashflows(
    user_id: str,
    asset: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Liste aller External Cashflow Events für einen User

    Args:
        user_id: User ID
        asset: Optional - Filter nach Asset (EUR/BTC)
        limit: Max Anzahl Events (1-1000)
        offset: Offset für Pagination
        db: Database Session (injected)

    Returns:
        Liste von Cashflow Events
    """
    try:
        query = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW
        )

        if asset:
            query = query.filter(LedgerEventDB.asset == asset)

        events_db = (
            query
            .order_by(LedgerEventDB.timestamp.desc())
            .limit(min(limit, 1000))
            .offset(offset)
            .all()
        )

        events = [
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "asset": event.asset,
                "amount": str(event.amount),
                "note": event.note,
                "created_at": event.created_at.isoformat()
            }
            for event in events_db
        ]

        # Calculate cumulative sums
        eur_total = Decimal("0")
        btc_total = Decimal("0")

        for event in reversed(events):
            if event["asset"] == "EUR":
                eur_total += Decimal(event["amount"])
            elif event["asset"] == "BTC":
                btc_total += Decimal(event["amount"])

        return {
            "events": events,
            "count": len(events),
            "limit": limit,
            "offset": offset,
            "totals": {
                "eur": str(eur_total),
                "btc": str(btc_total)
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/{event_id}")
def get_cashflow_detail(
    user_id: str,
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Holt Details eines External Cashflow Events

    Args:
        user_id: User ID
        event_id: Event ID
        db: Database Session (injected)

    Returns:
        Cashflow event details
    """
    try:
        event_db = db.query(LedgerEventDB).filter(
            LedgerEventDB.id == event_id,
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW
        ).first()

        if not event_db:
            raise HTTPException(status_code=404, detail="Cashflow event not found")

        return {
            "id": event_db.id,
            "user_id": event_db.user_id,
            "type": event_db.type.value,
            "timestamp": event_db.timestamp.isoformat(),
            "asset": event_db.asset,
            "amount": str(event_db.amount),
            "note": event_db.note,
            "source": event_db.source.value,
            "created_at": event_db.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{user_id}/{event_id}")
def update_cashflow_note(
    user_id: str,
    event_id: str,
    request: CashflowUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Updated Note/Kategorie eines Cashflow Events

    WICHTIG: Ledger ist append-only, daher nur Note/Kategorie änderbar.
    Für Betrags-/Datum-Änderungen: Event löschen + neues erstellen.

    Args:
        user_id: User ID
        event_id: Event ID
        request: Update data
        db: Database Session (injected)

    Returns:
        Updated cashflow event
    """
    try:
        event_db = db.query(LedgerEventDB).filter(
            LedgerEventDB.id == event_id,
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW
        ).first()

        if not event_db:
            raise HTTPException(status_code=404, detail="Cashflow event not found")

        # Update note (preserve category if provided)
        if request.category or request.note:
            if request.category and request.note:
                event_db.note = f"{request.category}: {request.note}"
            elif request.category:
                # Extract existing note if present
                existing_note = event_db.note.split(": ", 1)[1] if event_db.note and ": " in event_db.note else ""
                event_db.note = f"{request.category}: {existing_note}" if existing_note else request.category
            elif request.note:
                # Preserve category if present
                if event_db.note and ": " in event_db.note:
                    category = event_db.note.split(": ", 1)[0]
                    event_db.note = f"{category}: {request.note}"
                else:
                    event_db.note = request.note

        db.commit()
        db.refresh(event_db)

        return {
            "id": event_db.id,
            "timestamp": event_db.timestamp.isoformat(),
            "asset": event_db.asset,
            "amount": str(event_db.amount),
            "note": event_db.note,
            "updated": True
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}/{event_id}")
def reverse_cashflow(
    user_id: str,
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Storniert External Cashflow Event via ADJUSTMENT (append-only)

    Erstellt ein Gegen-Event (ADJUSTMENT) das den Betrag des
    ursprünglichen Events aufhebt. Das Original bleibt erhalten.

    Args:
        user_id: User ID
        event_id: Event ID
        db: Database Session (injected)

    Returns:
        Reversal confirmation mit ADJUSTMENT Event
    """
    try:
        event_db = db.query(LedgerEventDB).filter(
            LedgerEventDB.id == event_id,
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW
        ).first()

        if not event_db:
            raise HTTPException(status_code=404, detail="Cashflow event not found")

        # Gegen-Event erstellen (Ledger append-only!)
        reversal_id = f"adj_{event_id}"
        reversal = LedgerEventDB(
            id=reversal_id,
            user_id=user_id,
            type=EventTypeEnum.ADJUSTMENT,
            timestamp=utcnow(),
            asset=event_db.asset,
            amount=-event_db.amount,
            source=EventSourceEnum.ADJUSTMENT,
            note=f"Reversal of cashflow event {event_id}",
            created_at=utcnow()
        )

        db.add(reversal)
        db.commit()

        return {
            "message": "Cashflow event reversed via ADJUSTMENT",
            "original_event_id": event_id,
            "reversal_event_id": reversal_id,
            "reversed_amount": str(-event_db.amount),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
