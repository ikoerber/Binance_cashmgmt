"""Backtest API Endpoints (Alpha Score Backtesting Engine)"""

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserSettingsDB
from app.services.backtest_data_service import (
    BACKTEST_SYMBOLS,
    MAX_MONTHS,
    get_backtest_data_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


# --- Request Models ---


class BacktestRunRequest(BaseModel):
    symbol: str = Field(default="BTCEUR", description="Trading-Symbol")
    months: int = Field(
        default=12, ge=1, le=MAX_MONTHS, description="Datenlookback in Monaten"
    )
    initial_capital: str = Field(default="10000", description="Startkapital in EUR")
    # Optional config overrides
    interval: Optional[str] = Field(
        default=None, description="Kerzen-Intervall (5m/15m/1h)"
    )
    fee_rate: Optional[str] = Field(default=None, description="Fee Rate (z.B. 0.001)")
    slippage_pct: Optional[str] = Field(
        default=None, description="Slippage (z.B. 0.0005)"
    )
    position_fraction: Optional[str] = Field(
        default=None, description="Positionsgroesse (0-1)"
    )
    entry_threshold: Optional[str] = Field(
        default=None, description="Alpha Score Schwelle"
    )
    atr_period: Optional[int] = Field(default=None, description="ATR Perioden")
    atr_multiplier: Optional[str] = Field(default=None, description="ATR Multiplikator")
    zscore_window: Optional[int] = Field(default=None, description="Z-Score Fenster")
    leadlag_window: Optional[int] = Field(default=None, description="Lead-Lag Fenster")
    hurst_lookback: Optional[int] = Field(default=None, description="Hurst Lookback")
    hurst_trending: Optional[str] = Field(
        default=None, description="Hurst Trending Schwelle"
    )
    hurst_reverting: Optional[str] = Field(
        default=None, description="Hurst Reverting Schwelle"
    )
    weight_zscore: Optional[str] = Field(default=None, description="Z-Score Gewicht")
    weight_leadlag: Optional[str] = Field(default=None, description="Lead-Lag Gewicht")
    weight_imbalance: Optional[str] = Field(
        default=None, description="Imbalance Gewicht"
    )
    weight_funding: Optional[str] = Field(default=None, description="Funding Gewicht")


# --- Helpers ---


def _get_user_settings(user_id: str, db: Session) -> dict:
    """Laedt User-Settings oder gibt Defaults zurueck."""
    from app.api.routes.settings import _settings_to_dict, DEFAULTS

    settings = (
        db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
    )
    if settings:
        return _settings_to_dict(settings)
    return {"user_id": user_id, **DEFAULTS}


def _build_overrides(request: BacktestRunRequest) -> dict:
    """Extrahiert non-None Overrides aus dem Request."""
    overrides = {}
    for field_name in [
        "interval",
        "fee_rate",
        "slippage_pct",
        "position_fraction",
        "entry_threshold",
        "atr_period",
        "atr_multiplier",
        "zscore_window",
        "leadlag_window",
        "hurst_lookback",
        "hurst_trending",
        "hurst_reverting",
        "weight_zscore",
        "weight_leadlag",
        "weight_imbalance",
        "weight_funding",
    ]:
        val = getattr(request, field_name, None)
        if val is not None:
            overrides[field_name] = val
    return overrides


# --- Endpoints ---


@router.post("/{user_id}/run")
async def run_backtest(
    user_id: str,
    request: BacktestRunRequest,
    db: Session = Depends(get_db),
):
    """
    Startet einen Alpha Score Backtest.

    Fuehrt eine vollstaendige historische Simulation durch und gibt
    Metriken, Trades, Equity Curve und Benchmark zurueck.
    """
    # Validate symbol
    if request.symbol not in BACKTEST_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol nicht unterstuetzt. Erlaubt: {', '.join(sorted(BACKTEST_SYMBOLS))}",
        )

    # Validate initial_capital
    try:
        initial_capital = Decimal(request.initial_capital)
        if initial_capital <= 0:
            raise ValueError("must be positive")
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=400,
            detail="initial_capital muss eine positive Zahl sein",
        )

    # Validate optional numeric overrides
    for field_name in ["fee_rate", "slippage_pct", "position_fraction"]:
        val = getattr(request, field_name, None)
        if val is not None:
            try:
                d = Decimal(val)
                if d < 0:
                    raise ValueError("negative")
            except (InvalidOperation, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail=f"{field_name} muss eine nicht-negative Zahl sein",
                )

    try:
        settings = _get_user_settings(user_id, db)
    except Exception:
        logger.exception("Settings laden fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")

    overrides = _build_overrides(request)

    # Optional: Get WS manager for progress updates
    ws_manager = None
    try:
        from app.services.websocket_manager import get_stream_manager

        ws_manager = get_stream_manager()
    except Exception:
        pass  # Non-critical

    try:
        service = get_backtest_data_service()
        result = await asyncio.wait_for(
            service.run_backtest(
                user_id=user_id,
                symbol=request.symbol,
                months=request.months,
                initial_capital=initial_capital,
                config_overrides=overrides,
                db=db,
                settings=settings,
                ws_manager=ws_manager,
            ),
            timeout=300,  # 5 min timeout fuer Backtest
        )
        return result
    except asyncio.TimeoutError:
        logger.error(
            "Backtest Timeout fuer user=%s, symbol=%s", user_id, request.symbol
        )
        raise HTTPException(status_code=504, detail="Backtest Timeout (5 Minuten)")
    except Exception:
        logger.exception("Backtest fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/runs")
async def list_backtest_runs(
    user_id: str,
    symbol: Optional[str] = Query(default=None, description="Filter nach Symbol"),
    db: Session = Depends(get_db),
):
    """
    Listet vergangene Backtest-Runs mit Zusammenfassungs-Metriken.

    Ohne grosse JSON-Blobs (Trades, Equity Curve). Sortiert nach created_at desc.
    """
    try:
        service = get_backtest_data_service()
        runs = service.get_runs(db, user_id, symbol)
        return {"runs": runs, "count": len(runs)}
    except Exception:
        logger.exception("Backtest Runs laden fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/runs/{run_id}")
async def get_backtest_run_detail(
    user_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Gibt vollstaendige Backtest-Run-Details inkl. Trades, Equity Curve und Monthly Returns.
    """
    try:
        service = get_backtest_data_service()
        detail = service.get_run_detail(db, user_id, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Backtest Run nicht gefunden")
        return detail
    except HTTPException:
        raise
    except Exception:
        logger.exception("Backtest Run Detail laden fehlgeschlagen fuer run=%s", run_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/cancel/{run_id}")
async def cancel_backtest_run(
    user_id: str,
    run_id: str,
):
    """
    Bricht einen laufenden Backtest ab.

    Bereits berechnete Ergebnisse bis zum Abbruchpunkt werden gespeichert.
    """
    try:
        service = get_backtest_data_service()
        cancelled = service.cancel_run(run_id)
        if not cancelled:
            raise HTTPException(
                status_code=404,
                detail="Kein laufender Backtest mit dieser ID gefunden",
            )
        return {"cancelled": True, "run_id": run_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Backtest Cancel fehlgeschlagen fuer run=%s", run_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
