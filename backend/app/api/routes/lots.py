"""TradeLot API Endpoints"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional, List

from app.db.database import get_db

logger = logging.getLogger(__name__)
from app.services.lot_service import (
    get_lots_for_user,
    get_lot_detail,
    update_auto_order,
    sync_and_refresh_lots,
    get_mergeable_groups,
    merge_lots,
)
from app.services.binance import BinanceService
from app.api.dependencies import get_binance_service

router = APIRouter(prefix="/api/lots", tags=["lots"])


@router.get("/{user_id}")
def list_lots(
    user_id: str,
    status: Optional[str] = Query(
        None, description="Filter by status: OPEN, PARTIAL_CLOSED, CLOSED"
    ),
    from_date: Optional[str] = Query(
        None,
        description="Filter von Datum (ISO format: YYYY-MM-DD oder YYYY-MM-DDTHH:MM:SS)",
    ),
    to_date: Optional[str] = Query(
        None,
        description="Filter bis Datum (ISO format: YYYY-MM-DD oder YYYY-MM-DDTHH:MM:SS)",
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Liste TradeLots für einen User

    Args:
        user_id: User ID
        status: Optional - Filter nach Status
        from_date: Optional - Nur Lots ab diesem Datum (ISO format)
        to_date: Optional - Nur Lots bis zu diesem Datum (ISO format)
        limit: Max Anzahl Lots (1-1000)
        offset: Offset für Pagination
        db: Database Session (injected)

    Returns:
        Liste von TradeLots
    """
    try:
        parsed_from = None
        parsed_to = None
        if from_date:
            parsed_from = datetime.fromisoformat(from_date)
        if to_date:
            parsed_to = datetime.fromisoformat(to_date)

        lots = get_lots_for_user(
            db, user_id, status, parsed_from, parsed_to, limit, offset
        )
        return {
            "lots": lots,
            "count": len(lots),
            "limit": limit,
            "offset": offset,
        }
    except Exception:
        logger.exception("list_lots failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/sync")
def sync_lots_from_binance(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    start_time: Optional[str] = Query(
        None, description="ISO timestamp - nur Fills danach"
    ),
    db: Session = Depends(get_db),
    binance_service: BinanceService = Depends(get_binance_service),
):
    """
    Synchronisiert Trades von Binance und gibt aktualisierte TradeLots zurück.

    Holt neue Fills, erstellt TradeLots (Buy) und FIFO-Allocations (Sell),
    und gibt danach alle Lots zurück.

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        start_time: Optional - ISO timestamp, nur Fills danach
        db: Database Session (injected)
        binance_service: BinanceService (injected)

    Returns:
        Sync-Report + aktualisierte Lots
    """
    try:
        start_dt = None
        if start_time:
            start_dt = datetime.fromisoformat(start_time)

        return sync_and_refresh_lots(db, user_id, binance_service, symbol, start_dt)

    except HTTPException:
        raise
    except Exception:
        logger.exception("sync_lots failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/merge-groups")
def get_merge_groups(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Gibt Gruppen von OPEN Lots zurueck, die zusammengefasst werden koennen
    (gleiche binance_order_id, keine Orders/Allocations/Pairings).
    """
    try:
        groups = get_mergeable_groups(db, user_id)
        return {
            "groups": groups,
            "count": len(groups),
        }
    except Exception:
        logger.exception("get_merge_groups failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/merge")
def merge_lots_endpoint(
    user_id: str,
    lot_ids: List[str] = Body(..., description="Liste der Lot-IDs zum Zusammenfassen"),
    db: Session = Depends(get_db),
):
    """
    Fasst die angegebenen Lots zu einem Keeper-Lot zusammen.

    Der Keeper ist das aelteste Lot (nach created_at).
    Alle anderen Lots erhalten Status MERGED mit merged_into_lot_id-Referenz.

    Validierung:
    - Alle Lots muessen OPEN sein
    - Alle Lots muessen die gleiche binance_order_id haben
    - Keine Lots mit Sell Allocations, Orders oder aktiven Pairings
    """
    try:
        result = merge_lots(db, user_id, lot_ids)
        return {
            "message": f"{result['merged_count']} Lots zusammengefasst -> {result['keeper']['id']}",
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("merge_lots failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/{lot_id}")
def get_lot(user_id: str, lot_id: str, db: Session = Depends(get_db)):
    """
    Holt Lot-Details inkl. Allocations

    Args:
        user_id: User ID
        lot_id: Lot ID
        db: Database Session (injected)

    Returns:
        Lot-Details
    """
    try:
        lot = get_lot_detail(db, user_id, lot_id)
        if not lot:
            raise HTTPException(status_code=404, detail="Lot not found")
        return lot
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_lot failed for user=%s lot=%s", user_id, lot_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.patch("/{user_id}/{lot_id}/auto-order")
def toggle_auto_order(
    user_id: str,
    lot_id: str,
    enabled: bool = Body(
        ..., description="Enable (true) or disable (false) auto-order"
    ),
    db: Session = Depends(get_db),
):
    """
    Aktiviert/Deaktiviert Auto-Order für ein Lot

    Args:
        user_id: User ID
        lot_id: Lot ID
        enabled: True = aktivieren, False = deaktivieren
        db: Database Session (injected)

    Returns:
        Updated Lot
    """
    try:
        lot = update_auto_order(db, user_id, lot_id, enabled)
        return {
            "message": f"Auto-order {'enabled' if enabled else 'disabled'} for lot {lot_id}",
            "lot": lot,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("toggle_auto_order failed for user=%s lot=%s", user_id, lot_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
