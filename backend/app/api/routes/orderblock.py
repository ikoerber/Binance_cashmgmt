"""Orderblock Detection & Backtest API Endpoints"""

import asyncio
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserSettingsDB
from app.domain.orderblock import OBConfig
from app.services.orderblock_data_service import (
    ALLOWED_INTERVALS,
    _serialize_config,
    get_orderblock_data_service,
)
from app.services.orderblock_persistence_service import (
    get_backtest_run,
    get_backtest_runs,
    get_zone_detail,
    get_zones,
    save_backtest_result,
    save_detection_result,
)

router = APIRouter(prefix="/api/orderblock", tags=["orderblock"])

ALLOWED_SYMBOLS = {"BTCEUR", "BTCUSDT"}


# ─── Request Models ───


class OBConfigRequest(BaseModel):
    atr_length: int = Field(default=20, ge=5, le=100)
    atr_multiplier: float = Field(default=2.0, ge=0.5, le=10.0)
    fvg_window: int = Field(default=3, ge=1, le=10)
    swing_fractal_n: int = Field(default=2, ge=1, le=5)
    target_rr: float = Field(default=2.0, ge=0.5, le=10.0)
    zscore_lookback: int = Field(default=50, ge=10, le=200)
    zscore_threshold: float = Field(default=2.0, ge=0.5, le=5.0)
    max_holding_candles: int = Field(default=200, ge=0, le=2000)


class DetectionRequest(BaseModel):
    symbol: str = Field(default="BTCEUR")
    interval: Optional[str] = Field(default=None)
    months: int = Field(default=6, ge=1, le=24)
    config: Optional[OBConfigRequest] = None


class BacktestRequest(BaseModel):
    symbol: str = Field(default="BTCEUR")
    interval: Optional[str] = Field(default=None)
    months: int = Field(default=6, ge=1, le=24)
    config: Optional[OBConfigRequest] = None


# ─── Helpers ───


def _validate_symbol(symbol: str) -> None:
    if symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol nicht unterstuetzt. Erlaubt: {', '.join(sorted(ALLOWED_SYMBOLS))}",
        )


def _validate_interval(interval: str) -> None:
    if interval not in ALLOWED_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"Interval nicht unterstuetzt. Erlaubt: {', '.join(sorted(ALLOWED_INTERVALS))}",
        )


def _load_user_ob_settings(db: Session, user_id: str) -> dict:
    """Laedt Orderblock-Settings des Users (oder leeres Dict)."""
    settings = db.query(UserSettingsDB).filter(
        UserSettingsDB.user_id == user_id
    ).first()
    if settings is None:
        return {}
    result = {}
    if settings.ob_interval is not None:
        result["interval"] = settings.ob_interval
    if settings.ob_atr_multiplier is not None:
        result["atr_multiplier"] = settings.ob_atr_multiplier
    if settings.ob_target_rr is not None:
        result["target_rr"] = settings.ob_target_rr
    return result


def _build_config(
    req_config: Optional[OBConfigRequest],
    user_settings: dict,
) -> OBConfig:
    """
    3-Tier Config: Request > User-Settings > OBConfig-Defaults.

    Request-Config ueberschreibt alles. Ohne Request werden User-Settings
    als Fallback fuer atr_multiplier und target_rr verwendet.
    """
    if req_config is not None:
        return OBConfig(
            atr_length=req_config.atr_length,
            atr_multiplier=Decimal(str(req_config.atr_multiplier)),
            fvg_window=req_config.fvg_window,
            swing_fractal_n=req_config.swing_fractal_n,
            target_rr=Decimal(str(req_config.target_rr)),
            zscore_lookback=req_config.zscore_lookback,
            zscore_threshold=Decimal(str(req_config.zscore_threshold)),
            max_holding_candles=req_config.max_holding_candles,
        )

    # Kein expliziter Config -> User-Settings als Fallback
    defaults = OBConfig()
    atr_mult = user_settings.get("atr_multiplier", defaults.atr_multiplier)
    target_rr = user_settings.get("target_rr", defaults.target_rr)

    return OBConfig(
        atr_multiplier=Decimal(str(atr_mult)),
        target_rr=Decimal(str(target_rr)),
    )


def _resolve_interval(
    request_interval: Optional[str],
    user_settings: dict,
) -> str:
    """Interval: Request > User-Setting > Default '4h'."""
    if request_interval is not None:
        return request_interval
    return user_settings.get("interval", "4h")


# ─── Endpoints ───


@router.post("/{user_id}/detect")
async def detect_orderblocks(
    user_id: str,
    request: DetectionRequest,
    db: Session = Depends(get_db),
):
    """
    Detection ausfuehren: Fetcht Klines, erkennt Orderblocks, persistiert Zonen.

    Returns: Erkannte Zonen mit State und Meta-Informationen.
    """
    _validate_symbol(request.symbol)

    user_settings = _load_user_ob_settings(db, user_id)
    interval = _resolve_interval(request.interval, user_settings)
    _validate_interval(interval)

    config = _build_config(request.config, user_settings)
    service = get_orderblock_data_service()

    result = await asyncio.to_thread(
        service.detect_zones,
        symbol=request.symbol,
        interval=interval,
        months=request.months,
        config=config,
    )

    # Persistieren
    raw_zones = result.pop("raw_zones", [])
    if raw_zones:
        config_json = _serialize_config(config)
        saved = save_detection_result(
            db, user_id, raw_zones, request.symbol, interval, config_json
        )
        result["saved_count"] = saved

    return result


@router.get("/{user_id}/zones")
def get_orderblock_zones(
    user_id: str,
    symbol: str = Query(default="BTCEUR"),
    interval: str = Query(default="1h"),
    state: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Persistierte Zonen laden (mit optionalem State-Filter).

    State-Filter: UNMITIGATED, MITIGATED, INVALID
    """
    _validate_symbol(symbol)
    _validate_interval(interval)

    if state and state not in ("UNMITIGATED", "MITIGATED", "INVALID"):
        raise HTTPException(
            status_code=400,
            detail="State muss UNMITIGATED, MITIGATED oder INVALID sein.",
        )

    zones = get_zones(db, user_id, symbol, interval, state)
    return {"zones": zones, "count": len(zones)}


@router.get("/{user_id}/zones/{zone_id}")
def get_orderblock_zone_detail(
    user_id: str,
    zone_id: str,
    db: Session = Depends(get_db),
):
    """Einzelne Zone mit vollstaendigen Details laden."""
    zone = get_zone_detail(db, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone nicht gefunden.")
    return zone


@router.post("/{user_id}/backtest")
async def run_orderblock_backtest(
    user_id: str,
    request: BacktestRequest,
    db: Session = Depends(get_db),
):
    """
    Backtest ausfuehren: Detection + Simulation + Metriken.

    Persistiert den Run und liefert vollstaendiges Ergebnis.
    """
    _validate_symbol(request.symbol)

    user_settings = _load_user_ob_settings(db, user_id)
    interval = _resolve_interval(request.interval, user_settings)
    _validate_interval(interval)

    config = _build_config(request.config, user_settings)
    service = get_orderblock_data_service()

    result_data = await asyncio.to_thread(
        service.run_backtest,
        symbol=request.symbol,
        interval=interval,
        months=request.months,
        config=config,
    )

    # Persistieren (nur wenn Ergebnis vorhanden)
    run_id = None
    if result_data.get("result"):
        run_id = save_backtest_result(db, user_id, result_data)

    # result-Objekt nicht im API-Response zurueckgeben
    result_data.pop("result", None)
    result_data["run_id"] = run_id

    return result_data


@router.get("/{user_id}/backtest/runs")
def get_orderblock_backtest_runs(
    user_id: str,
    symbol: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Alle Backtest-Runs fuer einen User laden (optional nach Symbol filtern)."""
    if symbol:
        _validate_symbol(symbol)

    runs = get_backtest_runs(db, user_id, symbol)
    return {"runs": runs, "count": len(runs)}


@router.get("/{user_id}/backtest/runs/{run_id}")
def get_orderblock_backtest_run_detail(
    user_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    """Einzelnen Backtest-Run mit Metriken und Trades laden."""
    run = get_backtest_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest-Run nicht gefunden.")
    return run
