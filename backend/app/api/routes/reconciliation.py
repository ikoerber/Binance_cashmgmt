"""Reconciliation API Endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.reconciliation_service import ReconciliationService
from app.services.binance import BinanceService
from app.api.dependencies import get_binance_service

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


def get_reconciliation_service(binance: BinanceService = Depends(get_binance_service)) -> ReconciliationService:
    """Dependency: Reconciliation Service"""
    return ReconciliationService(binance)


@router.post("/{user_id}/run")
def run_full_reconciliation(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service)
):
    """
    Führt vollständige Reconciliation durch (Orders + Balances + Fills)

    Synct:
    - Order Status von Binance
    - Balance-Vergleich (Binance vs. Ledger)
    - Neue Fills (mit FIFO Allocation)

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Reconciliation report mit Diskrepanzen
    """
    try:
        report = reconciliation_service.full_reconciliation(db, user_id, symbol)
        return {
            "status": "completed",
            "user_id": user_id,
            "symbol": symbol,
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/orders")
def reconcile_orders_only(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service)
):
    """
    Synct nur Order Status von Binance

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Order reconciliation report
    """
    try:
        report = reconciliation_service.reconcile_orders(db, user_id, symbol)
        return {
            "status": "completed",
            "type": "orders",
            "user_id": user_id,
            "symbol": symbol,
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/balances")
def reconcile_balances_only(
    user_id: str,
    db: Session = Depends(get_db),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service)
):
    """
    Vergleicht Balances (Binance vs. Ledger)

    Args:
        user_id: User ID
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Balance reconciliation report
    """
    try:
        report = reconciliation_service.reconcile_balances(db, user_id)
        return {
            "status": "completed",
            "type": "balances",
            "user_id": user_id,
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/fills")
def reconcile_fills_only(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    start_time: str = Query(None, description="Optional start time (ISO format)"),
    db: Session = Depends(get_db),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service)
):
    """
    Synct Fills von Binance (mit FIFO Allocation)

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        start_time: Optional - Start time for sync
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Fill reconciliation report
    """
    try:
        report = reconciliation_service.reconcile_fills(db, user_id, symbol, start_time)
        return {
            "status": "completed",
            "type": "fills",
            "user_id": user_id,
            "symbol": symbol,
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
