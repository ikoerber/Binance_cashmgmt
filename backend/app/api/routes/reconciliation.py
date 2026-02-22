"""Reconciliation API Endpoints"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db

logger = logging.getLogger(__name__)
from app.services.reconciliation_service import ReconciliationService
from app.services.binance import BinanceService
from app.api.dependencies import get_binance_service
from app.symbol_registry import is_known_symbol, KNOWN_PAIRS

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


def _validate_symbol(symbol: str) -> None:
    if not is_known_symbol(symbol):
        raise HTTPException(
            status_code=400,
            detail=f"Unbekanntes Symbol: {symbol}. Bekannt: {list(KNOWN_PAIRS.keys())}",
        )


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
    - Persists run as ReconciliationRunDB with trigger='manual'

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Reconciliation report mit Diskrepanzen + run_id
    """
    try:
        _validate_symbol(symbol)
        report = reconciliation_service.full_reconciliation(db, user_id, symbol)
        return {
            "status": "completed",
            "user_id": user_id,
            "symbol": symbol,
            "run_id": report.get("run_id"),
            "report": {
                "orders": report.get("orders", {}),
                "balances": report.get("balances", {}),
                "fills": report.get("fills", {}),
            },
        }
    except Exception:
        logger.exception("Reconciliation endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/history")
def get_reconciliation_history(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service),
):
    """
    Gibt vergangene Reconciliation-Runs zurueck (paginiert).

    Args:
        user_id: User ID
        limit: Max Ergebnisse (1-100, Default: 20)
        offset: Pagination Offset
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Liste von Run-Summaries mit Gesamtzahl
    """
    try:
        return reconciliation_service.get_reconciliation_history(
            db, user_id, limit, offset
        )
    except Exception:
        logger.exception("Reconciliation history failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/history/{run_id}")
def get_reconciliation_run_detail(
    user_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service),
):
    """
    Gibt Details eines einzelnen Reconciliation-Runs zurueck.

    Inkl. vollem report_json und zugehoerigen Alert-Events.
    IDOR-geschuetzt via user_id.

    Args:
        user_id: User ID
        run_id: Reconciliation Run ID
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Run-Detail oder 404
    """
    try:
        result = reconciliation_service.get_reconciliation_run(db, user_id, run_id)
        if result is None:
            raise HTTPException(
                status_code=404, detail="Reconciliation-Run nicht gefunden"
            )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Reconciliation run detail failed for user=%s, run=%s", user_id, run_id
        )
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


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
        _validate_symbol(symbol)
        report = reconciliation_service.reconcile_orders(db, user_id, symbol)
        return {
            "status": "completed",
            "type": "orders",
            "user_id": user_id,
            "symbol": symbol,
            "report": report
        }
    except Exception as e:
        logger.exception("Reconciliation endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/balances")
def reconcile_balances_only(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db),
    reconciliation_service: ReconciliationService = Depends(get_reconciliation_service)
):
    """
    Vergleicht Balances (Binance vs. Ledger)

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        reconciliation_service: Reconciliation Service (injected)

    Returns:
        Balance reconciliation report
    """
    try:
        _validate_symbol(symbol)
        report = reconciliation_service.reconcile_balances(db, user_id, symbol)
        return {
            "status": "completed",
            "type": "balances",
            "user_id": user_id,
            "symbol": symbol,
            "report": report
        }
    except Exception as e:
        logger.exception("Reconciliation endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


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
        _validate_symbol(symbol)
        report = reconciliation_service.reconcile_fills(db, user_id, symbol, start_time)
        return {
            "status": "completed",
            "type": "fills",
            "user_id": user_id,
            "symbol": symbol,
            "report": report
        }
    except Exception as e:
        logger.exception("Reconciliation endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
