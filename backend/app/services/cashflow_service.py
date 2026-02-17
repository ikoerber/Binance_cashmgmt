"""
Cashflow Service - External Cashflow Management

Erstellt, listet und storniert External Cashflow Events (Bank-Transfers etc.).
Extrahiert aus cashflow.py Route fuer saubere Schichtentrennung.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum
from app.domain.models import utcnow

ALLOWED_CASHFLOW_ASSETS = {"EUR", "BTC"}


def _validate_asset(asset: str) -> None:
    """Validiert dass das Asset erlaubt ist."""
    if asset not in ALLOWED_CASHFLOW_ASSETS:
        raise ValueError(
            f"Asset '{asset}' nicht unterstuetzt. Erlaubt: {', '.join(sorted(ALLOWED_CASHFLOW_ASSETS))}"
        )


def create_cashflow_event(
    db: Session,
    user_id: str,
    asset: str,
    amount: Decimal,
    timestamp: Optional[datetime] = None,
    note: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """
    Erstellt ein External Cashflow Event.

    Args:
        db: Database Session
        user_id: User ID
        asset: Asset ("EUR" oder "BTC")
        amount: Betrag als Decimal
        timestamp: Zeitpunkt (Default: jetzt)
        note: Optionale Notiz
        category: Optionale Kategorie

    Returns:
        Event als Dict

    Raises:
        ValueError: Bei ungueltigem Asset
    """
    _validate_asset(asset)
    event_id = str(uuid.uuid4())
    combined_note = (
        f"{category}: {note}" if category and note
        else (category or note)
    )

    event_db = LedgerEventDB(
        id=event_id,
        user_id=user_id,
        type=EventTypeEnum.EXTERNAL_CASHFLOW,
        timestamp=timestamp or utcnow(),
        asset=asset,
        amount=amount,
        source=EventSourceEnum.EXTERNAL,
        note=combined_note,
        created_at=utcnow(),
    )

    db.add(event_db)
    db.flush()
    db.refresh(event_db)

    return _event_to_dict(event_db, include_type=True)


def list_cashflow_events(
    db: Session,
    user_id: str,
    asset: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Listet External Cashflow Events mit optionalem Asset-Filter.

    Returns:
        Dict mit events, count, totals
    """
    query = db.query(LedgerEventDB).filter(
        LedgerEventDB.user_id == user_id,
        LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW,
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

    events = [_event_to_dict(e) for e in events_db]
    totals = compute_cashflow_totals(events)

    return {
        "events": events,
        "count": len(events),
        "limit": limit,
        "offset": offset,
        "totals": totals,
    }


def get_cashflow_event(
    db: Session, user_id: str, event_id: str
) -> Optional[dict]:
    """Einzelnes Event laden. Gibt None zurueck wenn nicht gefunden."""
    event_db = db.query(LedgerEventDB).filter(
        LedgerEventDB.id == event_id,
        LedgerEventDB.user_id == user_id,
        LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW,
    ).first()

    if not event_db:
        return None

    return _event_to_dict(event_db, include_type=True, include_source=True)


def update_cashflow_note(
    db: Session,
    user_id: str,
    event_id: str,
    note: Optional[str] = None,
    category: Optional[str] = None,
) -> Optional[dict]:
    """
    Updated Note/Kategorie eines Cashflow Events.

    Returns:
        Updated Event als Dict, oder None wenn nicht gefunden.
    """
    event_db = db.query(LedgerEventDB).filter(
        LedgerEventDB.id == event_id,
        LedgerEventDB.user_id == user_id,
        LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW,
    ).first()

    if not event_db:
        return None

    if category or note:
        if category and note:
            event_db.note = f"{category}: {note}"
        elif category:
            existing_note = ""
            if event_db.note and ": " in event_db.note:
                parts = event_db.note.split(": ", 1)
                existing_note = parts[1] if len(parts) > 1 else ""
            event_db.note = f"{category}: {existing_note}" if existing_note else category
        elif note:
            if event_db.note and ": " in event_db.note:
                cat = event_db.note.split(": ", 1)[0]
                event_db.note = f"{cat}: {note}"
            else:
                event_db.note = note

    db.flush()
    db.refresh(event_db)

    result = _event_to_dict(event_db)
    result["updated"] = True
    return result


def reverse_cashflow_event(
    db: Session, user_id: str, event_id: str
) -> Optional[dict]:
    """
    Storniert ein Cashflow Event via ADJUSTMENT (append-only).

    Returns:
        Reversal-Ergebnis als Dict, oder None wenn Event nicht gefunden.
    """
    event_db = db.query(LedgerEventDB).filter(
        LedgerEventDB.id == event_id,
        LedgerEventDB.user_id == user_id,
        LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW,
    ).first()

    if not event_db:
        return None

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
        created_at=utcnow(),
    )

    db.add(reversal)
    db.flush()

    return {
        "message": "Cashflow event reversed via ADJUSTMENT",
        "original_event_id": event_id,
        "reversal_event_id": reversal_id,
        "reversed_amount": str(-event_db.amount),
    }


def compute_cashflow_totals(events: list[dict]) -> dict[str, str]:
    """Berechnet kumulative EUR/BTC Summen aus Cashflow-Events."""
    eur_total = Decimal("0")
    btc_total = Decimal("0")
    for event in events:
        if event["asset"] == "EUR":
            eur_total += Decimal(event["amount"])
        elif event["asset"] == "BTC":
            btc_total += Decimal(event["amount"])
    return {"eur": str(eur_total), "btc": str(btc_total)}


def _event_to_dict(
    event_db: LedgerEventDB,
    include_type: bool = False,
    include_source: bool = False,
) -> dict:
    """Konvertiert LedgerEventDB zu Dict."""
    result = {
        "id": event_db.id,
        "timestamp": event_db.timestamp.isoformat(),
        "asset": event_db.asset,
        "amount": str(event_db.amount),
        "note": event_db.note,
        "created_at": event_db.created_at.isoformat(),
    }
    if include_type:
        result["user_id"] = event_db.user_id
        result["type"] = event_db.type.value
    if include_source:
        result["source"] = event_db.source.value
    return result
