"""Orders API Endpoints"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from decimal import Decimal
from typing import Optional

from app.db.database import get_db

logger = logging.getLogger(__name__)
from app.services.order_service import OrderService
from app.services.order_tracking_service import OrderTrackingService
from app.services.binance import BinanceService
from app.api.dependencies import get_binance_service

router = APIRouter(prefix="/api/orders", tags=["orders"])


def get_order_service(binance: BinanceService = Depends(get_binance_service)) -> OrderService:
    """Dependency: Order Service"""
    return OrderService(binance)


def get_order_tracking_service(binance: BinanceService = Depends(get_binance_service)) -> OrderTrackingService:
    """Dependency: Order Tracking Service"""
    return OrderTrackingService(binance)


@router.post("/{user_id}/lot/{lot_id}/create")
def create_order_for_lot(
    user_id: str,
    lot_id: str,
    target_margin_pct: str = Query("0.05", description="Zielmarge (z.B. '0.05' fuer 5%)"),
    fee_buffer_pct: str = Query("0.002", description="Fee-Puffer (z.B. '0.002' fuer 0.2%)"),
    db: Session = Depends(get_db),
    order_service: OrderService = Depends(get_order_service)
):
    """
    Erstellt Limit-Sell-Order für ein TradeLot

    Args:
        user_id: User ID
        lot_id: TradeLot ID
        target_margin_pct: Zielmarge als String (Default: '0.05' fuer 5%)
        fee_buffer_pct: Fee-Puffer als String (Default: '0.002' fuer 0.2%)
        db: Database Session (injected)
        order_service: Order Service (injected)

    Returns:
        Order-Details
    """
    try:
        try:
            target_margin = Decimal(target_margin_pct)
            fee_buffer = Decimal(fee_buffer_pct)
        except Exception:
            raise ValueError("target_margin_pct und fee_buffer_pct muessen gueltige Dezimalzahlen sein")

        result = order_service.create_limit_sell_for_lot(
            db,
            user_id,
            lot_id,
            target_margin,
            fee_buffer
        )

        return result
    except ValueError as e:
        logger.warning("Order creation validation error for user=%s, lot=%s: %s", user_id, lot_id, e)
        raise HTTPException(status_code=400, detail="Order-Erstellung fehlgeschlagen. Bitte Parameter pruefen.")
    except Exception as e:
        logger.exception("Orders endpoint failed")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/open")
def get_open_orders(
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    order_service: OrderService = Depends(get_order_service)
):
    """
    Holt alle offenen Orders

    Args:
        symbol: Trading Pair (Default: BTCEUR)
        order_service: Order Service (injected)

    Returns:
        Liste offener Orders
    """
    try:
        orders = order_service.get_open_orders(symbol)
        return {
            "orders": orders,
            "count": len(orders),
            "symbol": symbol
        }
    except Exception as e:
        logger.exception("Orders endpoint failed")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.delete("/{user_id}/{order_id}")
def cancel_order(
    user_id: str,
    order_id: int,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db),
    order_service: OrderService = Depends(get_order_service),
    tracking_service: OrderTrackingService = Depends(get_order_tracking_service)
):
    """
    Cancelt eine Order auf Binance und aktualisiert lokale DB

    Args:
        user_id: User ID
        order_id: Binance Order ID
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        order_service: Order Service (injected)
        tracking_service: Order Tracking Service (injected)

    Returns:
        Cancel-Result
    """
    try:
        # Autorisierung: Order muss dem User gehoeren
        from app.db.models import OrderDB
        order_db = db.query(OrderDB).filter(
            OrderDB.binance_order_id == str(order_id),
            OrderDB.user_id == user_id,
        ).first()
        if not order_db:
            raise HTTPException(status_code=404, detail="Order nicht gefunden")

        result = order_service.cancel_order(db, symbol, order_id)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Order-Stornierung fehlgeschlagen")
    except Exception:
        logger.exception("Orders cancel failed for user=%s, order=%s", user_id, order_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/list")
def list_orders(
    user_id: str,
    status: Optional[str] = Query(None, description="Filter by status: PENDING, OPEN, FILLED, CANCELLED, etc."),
    symbol: Optional[str] = Query(None, description="Filter by symbol (z.B. BTCEUR)"),
    lot_id: Optional[str] = Query(None, description="Filter by linked lot ID"),
    pairing_id: Optional[str] = Query(None, description="Filter by linked pairing ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    tracking_service: OrderTrackingService = Depends(get_order_tracking_service)
):
    """
    Liste aller Orders für einen User mit Filtern

    Args:
        user_id: User ID
        status: Optional - Filter nach Status
        symbol: Optional - Filter nach Symbol
        lot_id: Optional - Filter nach Lot ID
        pairing_id: Optional - Filter nach Pairing ID
        limit: Max Anzahl Orders (1-1000)
        offset: Offset für Pagination
        db: Database Session (injected)
        tracking_service: Order Tracking Service (injected)

    Returns:
        Liste von Orders
    """
    try:
        orders = tracking_service.get_orders_for_user(
            db,
            user_id,
            status=status,
            symbol=symbol,
            lot_id=lot_id,
            pairing_id=pairing_id,
            limit=limit,
            offset=offset
        )
        return {
            "orders": orders,
            "count": len(orders),
            "limit": limit,
            "offset": offset,
            "filters": {
                "status": status,
                "symbol": symbol,
                "lot_id": lot_id,
                "pairing_id": pairing_id
            }
        }
    except Exception as e:
        logger.exception("Orders endpoint failed")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/sync-status")
def sync_order_statuses(
    user_id: str,
    db: Session = Depends(get_db),
    tracking_service: OrderTrackingService = Depends(get_order_tracking_service)
):
    """
    Synchronisiert offene Order-Status mit Binance.

    Expliziter POST-Endpoint (statt implizitem Sync im GET).
    """
    try:
        tracking_service.sync_open_order_statuses(db, user_id)
        return {"status": "synced", "user_id": user_id}
    except Exception:
        logger.exception("Order status sync failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/{order_id}")
def get_order_detail(
    user_id: str,
    order_id: str,
    db: Session = Depends(get_db),
    tracking_service: OrderTrackingService = Depends(get_order_tracking_service)
):
    """
    Holt Order-Details

    Args:
        user_id: User ID
        order_id: Order ID (internal)
        db: Database Session (injected)
        tracking_service: Order Tracking Service (injected)

    Returns:
        Order-Details
    """
    try:
        order = tracking_service.get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Verify user_id matches
        if order["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Orders endpoint failed")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/import")
def import_external_orders(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db),
    tracking_service: OrderTrackingService = Depends(get_order_tracking_service)
):
    """
    Importiert externe Orders von Binance in lokale DB

    Nützlich für Orders, die nicht von der App erstellt wurden
    (z.B. manuell in Binance UI oder via anderer Software)

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        tracking_service: Order Tracking Service (injected)

    Returns:
        Import report
    """
    try:
        report = tracking_service.import_external_orders(db, user_id, symbol)
        return {
            "status": "completed",
            "user_id": user_id,
            "symbol": symbol,
            "report": report
        }
    except Exception as e:
        logger.exception("Orders endpoint failed")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
