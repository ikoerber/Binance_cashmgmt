"""Sync API Endpoints"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from app.db.database import get_db
from app.services.binance import BinanceService
from app.services.sync_service import SyncService
from app.services.csv_import_service import import_trading_bots_csv
from app.api.dependencies import get_binance_service

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/{user_id}/fills")
def sync_fills(
    user_id: str,
    symbol: str = "BTCEUR",
    start_time: Optional[str] = None,
    db: Session = Depends(get_db),
    binance_service: BinanceService = Depends(get_binance_service)
):
    """
    Synchronisiert Fills von Binance

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        start_time: Optional - ISO timestamp, nur Fills danach
        db: Database Session (injected)
        binance_service: BinanceService (injected)

    Returns:
        Sync-Report
    """
    try:
        sync_service = SyncService(binance_service)

        start_dt = None
        if start_time:
            start_dt = datetime.fromisoformat(start_time)

        return sync_service.sync_fills(db, user_id, symbol, start_dt)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/fills/full")
def sync_all_fills(
    user_id: str,
    symbol: str = "BTCEUR",
    db: Session = Depends(get_db),
    binance_service: BinanceService = Depends(get_binance_service)
):
    """
    Synchronisiert ALLE historischen Fills von Binance

    Holt alle verfügbaren Fills in mehreren Batches.

    Args:
        user_id: User ID
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        binance_service: BinanceService (injected)

    Returns:
        Sync-Report mit allen importierten Fills
    """
    try:
        sync_service = SyncService(binance_service)

        start_dt = datetime.now() - timedelta(days=365)

        total_new_fills = 0
        total_new_lots = 0
        total_allocations = 0

        for _ in range(10):  # Max 10 Batches = 10,000 Trades
            result = sync_service.sync_fills(db, user_id, symbol, start_dt)

            total_new_fills += result["new_fills"]
            total_new_lots += result["new_lots"]
            total_allocations += result["allocations"]

            if result["new_fills"] == 0:
                break

            start_dt = start_dt - timedelta(days=30)

        return {
            "status": "success",
            "message": f"Full sync completed: {total_new_fills} fills imported",
            "new_fills": total_new_fills,
            "new_lots": total_new_lots,
            "allocations": total_allocations
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/import/trading-bots-csv")
async def import_trading_bots_from_csv(
    user_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Importiert Trading Bot Trades aus Binance CSV-Export.

    Der Import ist idempotent: Doppelte Trades werden automatisch erkannt
    und übersprungen.

    Args:
        user_id: User ID
        file: CSV-Datei (Binance Trading Bots Export)
        db: Database Session (injected)

    Returns:
        Import-Report
    """
    try:
        content = await file.read()
        csv_content = content.decode("utf-8-sig")

        return import_trading_bots_csv(db, user_id, csv_content)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
