"""Backtest API Endpoints (Alpha Score Backtesting Engine)"""

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserSettingsDB
from app.services.backtest_data_service import (
    BACKTEST_SYMBOLS,
    MAX_MONTHS,
    MAX_SWEEP_COMBINATIONS,
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


class SweepRangeConfig(BaseModel):
    """Range definition for a single sweep parameter."""

    min: float = Field(description="Minimum value")
    max: float = Field(description="Maximum value")
    step: float = Field(gt=0, description="Step size (must be > 0)")


class SweepRequest(BaseModel):
    """Request model for parameter sweep."""

    symbol: str = Field(default="BTCEUR", description="Trading-Symbol")
    months: int = Field(
        default=12, ge=1, le=MAX_MONTHS, description="Datenlookback in Monaten"
    )
    initial_capital: str = Field(default="10000", description="Startkapital in EUR")
    # Base config overrides (non-sweep parameters)
    fee_rate: Optional[str] = Field(default=None, description="Fee Rate")
    slippage_pct: Optional[str] = Field(default=None, description="Slippage")
    position_fraction: Optional[str] = Field(
        default=None, description="Positionsgroesse"
    )
    # Sweep parameter ranges
    sweep: Dict[str, SweepRangeConfig] = Field(
        description="Parameter ranges for sweep (z.B. zscore_window, entry_threshold)"
    )


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


# --- Sweep Endpoints ---


@router.post("/{user_id}/sweep")
async def run_sweep(
    user_id: str,
    request: SweepRequest,
    db: Session = Depends(get_db),
):
    """
    Startet einen Parameter-Sweep ueber mehrere Backtest-Konfigurationen.

    Fuehrt Backtests fuer alle Kombinationen der Sweep-Parameter durch.
    Candle-Daten werden einmalig gefetcht und wiederverwendet.
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

    # Validate sweep config and compute combination count upfront
    sweep_dict = {
        k: {"min": v.min, "max": v.max, "step": v.step}
        for k, v in request.sweep.items()
    }

    try:
        service = get_backtest_data_service()
        service._generate_sweep_combinations(sweep_dict)
    except ValueError as e:
        combo_count = 1
        for v in sweep_dict.values():
            steps = int((v["max"] - v["min"]) / v["step"]) + 1
            combo_count *= max(1, steps)
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(e),
                "combination_count": combo_count,
                "max_allowed": MAX_SWEEP_COMBINATIONS,
            },
        )

    # Build base config (non-sweep overrides)
    base_config = {}
    if request.fee_rate is not None:
        base_config["fee_rate"] = request.fee_rate
    if request.slippage_pct is not None:
        base_config["slippage_pct"] = request.slippage_pct
    if request.position_fraction is not None:
        base_config["position_fraction"] = request.position_fraction

    try:
        settings = _get_user_settings(user_id, db)
    except Exception:
        logger.exception("Settings laden fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")

    # Optional WS manager
    ws_manager = None
    try:
        from app.services.websocket_manager import get_stream_manager

        ws_manager = get_stream_manager()
    except Exception:
        pass

    try:
        result = await asyncio.wait_for(
            service.run_sweep(
                user_id=user_id,
                symbol=request.symbol,
                months=request.months,
                initial_capital=initial_capital,
                base_config=base_config,
                sweep_config=sweep_dict,
                db=db,
                settings=settings,
                ws_manager=ws_manager,
            ),
            timeout=600,  # 10 min timeout fuer Sweep
        )
        return result
    except asyncio.TimeoutError:
        logger.error("Sweep Timeout fuer user=%s, symbol=%s", user_id, request.symbol)
        raise HTTPException(status_code=504, detail="Sweep Timeout (10 Minuten)")
    except Exception:
        logger.exception("Sweep fehlgeschlagen fuer user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/sweep/{sweep_id}")
async def get_sweep_detail(
    user_id: str,
    sweep_id: str,
    db: Session = Depends(get_db),
):
    """
    Gibt alle Runs eines Sweeps zurueck (Summary-Metriken, ohne Equity Curves).
    """
    try:
        service = get_backtest_data_service()
        result = service.get_sweep_runs(db, user_id, sweep_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Sweep nicht gefunden")
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Sweep Detail laden fehlgeschlagen fuer sweep=%s", sweep_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/sweep/{sweep_id}/csv")
async def get_sweep_csv(
    user_id: str,
    sweep_id: str,
    db: Session = Depends(get_db),
):
    """
    Exportiert Sweep-Ergebnisse als CSV-Datei.
    """
    try:
        service = get_backtest_data_service()
        csv_content = service.generate_sweep_csv(db, user_id, sweep_id)
        if csv_content is None:
            raise HTTPException(status_code=404, detail="Sweep nicht gefunden")
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="sweep_{sweep_id}.csv"'
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Sweep CSV Export fehlgeschlagen fuer sweep=%s", sweep_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
