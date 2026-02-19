"""Orderblock Detection & Backtest API Endpoints"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.orderblock_config_service import resolve_orderblock_config
from app.services.orderblock_data_service import (
    ALLOWED_INTERVALS,
    INTERVAL_MS,
    serialize_candle_for_chart,
    serialize_config,
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

from app.symbol_registry import KNOWN_PAIRS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orderblock", tags=["orderblock"])

ALLOWED_SYMBOLS = set(KNOWN_PAIRS.keys())

# Timeouts fuer async Operationen (Sekunden)
_ANALYZE_TIMEOUT = 120
_CANDLE_FETCH_TIMEOUT = 60


# ─── Request Models ───


class OBConfigRequest(BaseModel):
    atr_length: int = Field(default=20, ge=5, le=100)
    atr_multiplier: str = Field(default="2.0")
    fvg_window: int = Field(default=3, ge=1, le=10)
    swing_fractal_n: int = Field(default=2, ge=1, le=5)
    target_rr: str = Field(default="2.0")
    zscore_lookback: int = Field(default=50, ge=10, le=200)
    zscore_threshold: str = Field(default="2.0")
    max_holding_candles: int = Field(default=200, ge=0, le=2000)
    impulse_window: int = Field(default=5, ge=2, le=20)
    sweep_lookback: int = Field(default=10, ge=1, le=50)
    sweep_conviction_boost: str = Field(default="10.0")

    @field_validator(
        "atr_multiplier", "target_rr", "zscore_threshold", "sweep_conviction_boost",
        mode="before",
    )
    @classmethod
    def coerce_to_string(cls, v) -> str:
        """Akzeptiert float/int/str, konvertiert zu String (Decimal-String-Transport)."""
        if isinstance(v, (int, float)):
            return str(v)
        return v

    @field_validator(
        "atr_multiplier", "target_rr", "zscore_threshold", "sweep_conviction_boost",
        mode="after",
    )
    @classmethod
    def validate_decimal_string(cls, v: str) -> str:
        try:
            d = Decimal(v)
        except Exception:
            raise ValueError(f"Wert '{v}' ist keine gueltige Dezimalzahl")
        if d.is_nan() or d.is_infinite():
            raise ValueError("Wert muss eine endliche Zahl sein (kein NaN/Infinity)")
        return v

    @field_validator("atr_multiplier", mode="after")
    @classmethod
    def validate_atr_range(cls, v: str) -> str:
        d = Decimal(v)
        if not (Decimal("0.5") <= d <= Decimal("10.0")):
            raise ValueError("atr_multiplier muss zwischen 0.5 und 10.0 liegen")
        return v

    @field_validator("target_rr", mode="after")
    @classmethod
    def validate_rr_range(cls, v: str) -> str:
        d = Decimal(v)
        if not (Decimal("0.5") <= d <= Decimal("10.0")):
            raise ValueError("target_rr muss zwischen 0.5 und 10.0 liegen")
        return v

    @field_validator("zscore_threshold", mode="after")
    @classmethod
    def validate_zscore_range(cls, v: str) -> str:
        d = Decimal(v)
        if not (Decimal("0.5") <= d <= Decimal("5.0")):
            raise ValueError("zscore_threshold muss zwischen 0.5 und 5.0 liegen")
        return v

    @field_validator("sweep_conviction_boost", mode="after")
    @classmethod
    def validate_sweep_range(cls, v: str) -> str:
        d = Decimal(v)
        if not (Decimal("0") <= d <= Decimal("30.0")):
            raise ValueError("sweep_conviction_boost muss zwischen 0.0 und 30.0 liegen")
        return v


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

    config, interval = resolve_orderblock_config(
        db, user_id, request.config, request.interval,
    )
    _validate_interval(interval)

    service = get_orderblock_data_service()

    try:
        result_data = await asyncio.wait_for(
            asyncio.to_thread(
                service.analyze,
                symbol=request.symbol,
                interval=interval,
                months=request.months,
                config=config,
            ),
            timeout=_ANALYZE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("Orderblock Analyse Timeout (%ds) fuer user=%s, symbol=%s", _ANALYZE_TIMEOUT, user_id, request.symbol)
        raise HTTPException(
            status_code=504,
            detail=f"Analyse-Timeout ({_ANALYZE_TIMEOUT}s). Kuerzeren Lookback oder groesseres Intervall waehlen.",
        )
    except Exception:
        logger.exception("Orderblock Analyse fehlgeschlagen fuer user=%s, symbol=%s", user_id, request.symbol)
        raise HTTPException(
            status_code=502,
            detail="Analyse fehlgeschlagen. Bitte Parameter pruefen.",
        )

    # Zonen persistieren
    raw_zones = result_data.pop("raw_zones", [])
    if raw_zones:
        config_json = serialize_config(config)
        save_detection_result(
            db, user_id, raw_zones, request.symbol, interval, config_json
        )

    # Backtest-Run persistieren
    run_id = None
    result = result_data.pop("result", None)
    if result:
        run_id = save_backtest_result(
            db,
            user_id,
            result,
            config_json=result_data["config"],
            metrics_json=result_data["metrics"],
            trades_json=result_data["trades"],
        )
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

    try:
        zones = get_zones(db, user_id, symbol, interval, state)
        return {"zones": zones, "count": len(zones)}
    except Exception:
        logger.exception("Orderblock zones failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/zones/{zone_id}")
def get_orderblock_zone_detail(
    user_id: str,
    zone_id: str,
    db: Session = Depends(get_db),
):
    """Einzelne Zone mit vollstaendigen Details laden."""
    try:
        zone = get_zone_detail(db, zone_id, user_id=user_id)
        if zone is None:
            raise HTTPException(status_code=404, detail="Zone nicht gefunden.")
        return zone
    except HTTPException:
        raise
    except Exception:
        logger.exception("Orderblock zone detail failed for zone=%s", zone_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


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

    try:
        deleted = delete_all_zones(db, user_id, symbol, interval)
        return {"deleted": deleted}
    except Exception:
        logger.exception("Orderblock zone delete failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/backtest/runs")
def get_orderblock_backtest_runs(
    user_id: str,
    symbol: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Alle Backtest-Runs fuer einen User laden (optional nach Symbol filtern)."""
    if symbol:
        _validate_symbol(symbol)

    try:
        runs = get_backtest_runs(db, user_id, symbol)
        return {"runs": runs, "count": len(runs)}
    except Exception:
        logger.exception("Orderblock backtest runs failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/backtest/runs/{run_id}")
def get_orderblock_backtest_run_detail(
    user_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    """Einzelnen Backtest-Run mit Metriken und Trades laden."""
    try:
        run = get_backtest_run(db, run_id, user_id=user_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Backtest-Run nicht gefunden.")
        return run
    except HTTPException:
        raise
    except Exception:
        logger.exception("Orderblock backtest run detail failed for run=%s", run_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


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

    from datetime import timezone as _tz

    def _parse_iso_to_naive_utc(iso_str: str) -> datetime:
        """Parsed ISO-String zu naive-UTC datetime (konsistente Konvertierung)."""
        return datetime.fromisoformat(
            iso_str.replace("Z", "+00:00")
        ).astimezone(_tz.utc).replace(tzinfo=None)

    if start_time and end_time:
        # Modus 2: Explizites Zeitfenster mit Kontext-Padding
        try:
            start_dt = _parse_iso_to_naive_utc(start_time)
            end_dt = _parse_iso_to_naive_utc(end_time)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Ungueltiges Datumsformat. ISO-Format erwartet.",
            )
        padding_ms = 20 * interval_ms
        start_dt = start_dt - timedelta(milliseconds=padding_ms)
        end_dt = end_dt + timedelta(milliseconds=padding_ms)
    elif zone_id:
        # Modus 1: Zone-basiertes Fenster
        zone = get_zone_detail(db, zone_id, user_id=user_id)
        if zone is None:
            raise HTTPException(status_code=404, detail="Zone nicht gefunden.")
        formed_at_str = zone.get("formed_at", "")
        formed_dt = _parse_iso_to_naive_utc(formed_at_str)
        window_ms = context_candles * interval_ms
        start_dt = formed_dt - timedelta(milliseconds=window_ms)
        end_dt = formed_dt + timedelta(milliseconds=window_ms)
    else:
        raise HTTPException(
            status_code=400,
            detail="zone_id oder start_time+end_time erforderlich.",
        )

    service = get_orderblock_data_service()
    try:
        candles = await asyncio.wait_for(
            asyncio.to_thread(
                service.fetch_candles_for_window,
                symbol=symbol,
                interval=interval,
                start_time=start_dt,
                end_time=end_dt,
            ),
            timeout=_CANDLE_FETCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("Candle-Fetch Timeout (%ds) fuer user=%s, symbol=%s", _CANDLE_FETCH_TIMEOUT, user_id, symbol)
        raise HTTPException(
            status_code=504,
            detail=f"Candle-Fetch Timeout ({_CANDLE_FETCH_TIMEOUT}s). Kleineres Zeitfenster waehlen.",
        )
    except Exception:
        logger.exception("Candle-Fetch fehlgeschlagen fuer user=%s, symbol=%s", user_id, symbol)
        raise HTTPException(
            status_code=502,
            detail="Candle-Daten konnten nicht geladen werden.",
        )

    return {
        "candles": [serialize_candle_for_chart(c) for c in candles],
        "count": len(candles),
        "symbol": symbol,
        "interval": interval,
    }
