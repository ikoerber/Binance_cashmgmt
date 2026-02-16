"""Orderblock Detection & Backtest API Endpoints"""

import asyncio
from datetime import datetime, timedelta
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
    INTERVAL_MS,
    _serialize_candle_for_chart,
    _serialize_config,
    get_orderblock_data_service,
)
from app.services.orderblock_persistence_service import (
    delete_all_zones,
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
    impulse_window: int = Field(default=5, ge=2, le=20)


class AnalyzeRequest(BaseModel):
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
    if settings.ob_impulse_window is not None:
        result["impulse_window"] = int(settings.ob_impulse_window)
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
            impulse_window=req_config.impulse_window,
        )

    # Kein expliziter Config -> User-Settings als Fallback
    defaults = OBConfig()
    atr_mult = user_settings.get("atr_multiplier", defaults.atr_multiplier)
    target_rr = user_settings.get("target_rr", defaults.target_rr)
    impulse_window = user_settings.get("impulse_window", defaults.impulse_window)

    return OBConfig(
        atr_multiplier=Decimal(str(atr_mult)),
        target_rr=Decimal(str(target_rr)),
        impulse_window=int(impulse_window),
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


@router.post("/{user_id}/analyze")
async def analyze_orderblocks(
    user_id: str,
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
):
    """
    Combined Detection + Backtest: ein Aufruf, gleiche Kerzen, konsistente Ergebnisse.

    1. Fetcht Klines
    2. Erkennt Orderblocks (5-Phasen-Validierung)
    3. Aktualisiert Zone-States (UNMITIGATED/MITIGATED/INVALID)
    4. Simuliert Trades (Entry/Stop/Target)
    5. Berechnet Backtest-Metriken
    6. Persistiert Zonen + Backtest-Run

    Returns: Zonen, Metriken, Trades, Config, Meta.
    """
    _validate_symbol(request.symbol)

    user_settings = _load_user_ob_settings(db, user_id)
    interval = _resolve_interval(request.interval, user_settings)
    _validate_interval(interval)

    config = _build_config(request.config, user_settings)
    service = get_orderblock_data_service()

    result_data = await asyncio.to_thread(
        service.analyze,
        symbol=request.symbol,
        interval=interval,
        months=request.months,
        config=config,
    )

    # Zonen persistieren
    raw_zones = result_data.pop("raw_zones", [])
    if raw_zones:
        config_json = _serialize_config(config)
        save_detection_result(
            db, user_id, raw_zones, request.symbol, interval, config_json
        )

    # Backtest-Run persistieren
    run_id = None
    if result_data.get("result"):
        run_id = save_backtest_result(db, user_id, result_data)

    result_data.pop("result", None)
    result_data["run_id"] = run_id

    return result_data


@router.get("/{user_id}/zones")
def get_orderblock_zones(
    user_id: str,
    symbol: str = Query(default="BTCEUR"),
    interval: str = Query(default="4h"),
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


@router.delete("/{user_id}/zones")
def delete_orderblock_zones(
    user_id: str,
    symbol: str = Query(default="BTCEUR"),
    interval: str = Query(default="4h"),
    db: Session = Depends(get_db),
):
    """Alle Zonen fuer User/Symbol/Interval loeschen."""
    _validate_symbol(symbol)
    _validate_interval(interval)

    deleted = delete_all_zones(db, user_id, symbol, interval)
    return {"deleted": deleted}


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


@router.get("/{user_id}/candles")
async def get_orderblock_candles(
    user_id: str,
    symbol: str = Query(default="BTCEUR"),
    interval: str = Query(default="4h"),
    zone_id: Optional[str] = Query(default=None),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    context_candles: int = Query(default=80, ge=20, le=300),
    db: Session = Depends(get_db),
):
    """
    OHLCV Candles fuer Candlestick-Chart.

    Zwei Modi:
    1. zone_id → Auto-Fenster um Zone (formed_at ± context_candles × interval)
    2. start_time + end_time → Explizites Zeitfenster (± context_candles Padding)

    Returns: candles[] mit {time, open, high, low, close, volume}.
    """
    _validate_symbol(symbol)
    _validate_interval(interval)

    interval_ms = INTERVAL_MS[interval]

    if start_time and end_time:
        # Modus 2: Explizites Zeitfenster mit Kontext-Padding
        start_dt = datetime.fromisoformat(
            start_time.replace("Z", "+00:00")
        ).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(
            end_time.replace("Z", "+00:00")
        ).replace(tzinfo=None)
        padding_ms = 20 * interval_ms
        start_dt = start_dt - timedelta(milliseconds=padding_ms)
        end_dt = end_dt + timedelta(milliseconds=padding_ms)
    elif zone_id:
        # Modus 1: Zone-basiertes Fenster
        zone = get_zone_detail(db, zone_id)
        if zone is None:
            raise HTTPException(status_code=404, detail="Zone nicht gefunden.")
        formed_at_str = zone.get("formed_at", "")
        formed_dt = datetime.fromisoformat(
            formed_at_str.replace("Z", "+00:00")
        ).replace(tzinfo=None)
        window_ms = context_candles * interval_ms
        start_dt = formed_dt - timedelta(milliseconds=window_ms)
        end_dt = formed_dt + timedelta(milliseconds=window_ms)
    else:
        raise HTTPException(
            status_code=400,
            detail="zone_id oder start_time+end_time erforderlich.",
        )

    service = get_orderblock_data_service()
    candles = await asyncio.to_thread(
        service.fetch_candles_for_window,
        symbol=symbol,
        interval=interval,
        start_time=start_dt,
        end_time=end_dt,
    )

    return {
        "candles": [_serialize_candle_for_chart(c) for c in candles],
        "count": len(candles),
        "symbol": symbol,
        "interval": interval,
    }
