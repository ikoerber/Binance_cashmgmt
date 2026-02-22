"""Sync API Endpoints"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from app.db.database import get_db

logger = logging.getLogger(__name__)
from app.services.binance import BinanceService
from app.services.sync_service import SyncService
from app.services.csv_import_service import import_trading_bots_csv
from app.api.dependencies import get_binance_service
from app.symbol_registry import is_known_symbol, KNOWN_PAIRS

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _validate_symbol(symbol: str) -> None:
    if not is_known_symbol(symbol):
        raise HTTPException(
            status_code=400,
            detail=f"Unbekanntes Symbol: {symbol}. Bekannt: {list(KNOWN_PAIRS.keys())}",
        )


@router.post("/{user_id}/fills")
def sync_fills(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    start_time: Optional[str] = Query(None, description="Optional start time (ISO format)"),
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
        _validate_symbol(symbol)
        sync_service = SyncService(binance_service)

        start_dt = None
        if start_time:
            start_dt = datetime.fromisoformat(start_time)

        return sync_service.sync_fills(db, user_id, symbol, start_dt)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Sync endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/fills/full")
def sync_all_fills(
    user_id: str,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
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
        _validate_symbol(symbol)
        sync_service = SyncService(binance_service)

        start_dt = datetime.now() - timedelta(days=365)

        total_new_fills = 0
        total_new_lots = 0
        total_allocations = 0
        total_fills_processed = 0
        total_fills_failed = 0
        total_fills_skipped_fifo = 0
        last_synced_source_id = None
        all_fill_details = []
        all_errors = []

        for _ in range(10):  # Max 10 Batches = 10,000 Trades
            result = sync_service.sync_fills(db, user_id, symbol, start_dt)

            total_new_fills += result["new_fills"]
            total_new_lots += result["new_lots"]
            total_allocations += result["allocations"]
            total_fills_processed += result.get("fills_processed", 0)
            total_fills_failed += result.get("fills_failed", 0)
            total_fills_skipped_fifo += result.get("fills_skipped_fifo", 0)
            all_fill_details.extend(result.get("fill_details", []))
            all_errors.extend(result.get("errors", []))

            batch_watermark = result.get("last_synced_source_id")
            if batch_watermark is not None:
                if last_synced_source_id is None:
                    last_synced_source_id = batch_watermark
                else:
                    last_synced_source_id = max(
                        last_synced_source_id, batch_watermark,
                        key=lambda sid: int(sid)
                    )

            if result.get("status") == "fifo_error":
                return {
                    "status": "fifo_error",
                    "message": f"FIFO allocation error after {total_new_fills} fills. Remaining batches skipped.",
                    "new_fills": total_new_fills,
                    "new_lots": total_new_lots,
                    "allocations": total_allocations,
                    "fills_processed": total_fills_processed,
                    "fills_failed": total_fills_failed,
                    "fills_skipped_fifo": total_fills_skipped_fifo,
                    "last_synced_source_id": last_synced_source_id,
                    "fifo_aborted": True,
                    "fill_details": all_fill_details,
                    "errors": all_errors,
                }

            if result["new_fills"] == 0:
                break

            start_dt = start_dt - timedelta(days=30)

        status = "success"
        if total_fills_failed > 0:
            status = "partial_success"

        return {
            "status": status,
            "message": f"Full sync completed: {total_new_fills} fills imported",
            "new_fills": total_new_fills,
            "new_lots": total_new_lots,
            "allocations": total_allocations,
            "fills_processed": total_fills_processed,
            "fills_failed": total_fills_failed,
            "fills_skipped_fifo": total_fills_skipped_fifo,
            "last_synced_source_id": last_synced_source_id,
            "fifo_aborted": False,
            "fill_details": all_fill_details,
            "errors": all_errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Sync endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


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
    MAX_CSV_SIZE = 10 * 1024 * 1024  # 10 MB
    try:
        content = await file.read(MAX_CSV_SIZE + 1)
        if len(content) > MAX_CSV_SIZE:
            raise HTTPException(status_code=413, detail="CSV ueberschreitet 10 MB Limit")
        csv_content = content.decode("utf-8-sig")

        return import_trading_bots_csv(db, user_id, csv_content)

    except ValueError as e:
        logger.warning("CSV parse error for user=%s: %s", user_id, e)
        raise HTTPException(status_code=400, detail="CSV-Format ungueltig")
    except Exception as e:
        logger.exception("Sync endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
