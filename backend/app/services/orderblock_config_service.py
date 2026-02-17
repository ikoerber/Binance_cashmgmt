"""
Orderblock Config Resolution Service

3-Tier Config-Hierarchie: Request > User-Settings > OBConfig-Defaults.
Extrahiert aus orderblock.py Route um Business-Logik von HTTP-Layer zu trennen.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.db.models import UserSettingsDB
from app.domain.orderblock import OBConfig


def load_user_ob_settings(db: Session, user_id: str) -> dict:
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


def build_ob_config(
    req_config,
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
            atr_multiplier=Decimal(req_config.atr_multiplier),
            fvg_window=req_config.fvg_window,
            swing_fractal_n=req_config.swing_fractal_n,
            target_rr=Decimal(req_config.target_rr),
            zscore_lookback=req_config.zscore_lookback,
            zscore_threshold=Decimal(req_config.zscore_threshold),
            max_holding_candles=req_config.max_holding_candles,
            impulse_window=req_config.impulse_window,
            sweep_lookback=req_config.sweep_lookback,
            sweep_conviction_boost=Decimal(req_config.sweep_conviction_boost),
        )

    # Kein expliziter Config -> User-Settings als Fallback
    defaults = OBConfig()

    atr_mult = _safe_decimal(
        user_settings.get("atr_multiplier"), defaults.atr_multiplier, "atr_multiplier"
    )
    target_rr = _safe_decimal(
        user_settings.get("target_rr"), defaults.target_rr, "target_rr"
    )
    zscore_threshold = _safe_decimal(
        user_settings.get("zscore_threshold"), defaults.zscore_threshold, "zscore_threshold"
    )
    sweep_conviction_boost = _safe_decimal(
        user_settings.get("sweep_conviction_boost"), defaults.sweep_conviction_boost, "sweep_conviction_boost"
    )

    impulse_window = _safe_int(
        user_settings.get("impulse_window"), defaults.impulse_window, "impulse_window"
    )
    atr_length = _safe_int(
        user_settings.get("atr_length"), defaults.atr_length, "atr_length"
    )
    fvg_window = _safe_int(
        user_settings.get("fvg_window"), defaults.fvg_window, "fvg_window"
    )
    swing_fractal_n = _safe_int(
        user_settings.get("swing_fractal_n"), defaults.swing_fractal_n, "swing_fractal_n"
    )
    zscore_lookback = _safe_int(
        user_settings.get("zscore_lookback"), defaults.zscore_lookback, "zscore_lookback"
    )
    max_holding_candles = _safe_int(
        user_settings.get("max_holding_candles"), defaults.max_holding_candles, "max_holding_candles"
    )
    sweep_lookback = _safe_int(
        user_settings.get("sweep_lookback"), defaults.sweep_lookback, "sweep_lookback"
    )

    return OBConfig(
        atr_length=atr_length,
        atr_multiplier=atr_mult,
        fvg_window=fvg_window,
        swing_fractal_n=swing_fractal_n,
        target_rr=target_rr,
        zscore_lookback=zscore_lookback,
        zscore_threshold=zscore_threshold,
        max_holding_candles=max_holding_candles,
        impulse_window=impulse_window,
        sweep_lookback=sweep_lookback,
        sweep_conviction_boost=sweep_conviction_boost,
    )


def _safe_int(value, default: int, name: str) -> int:
    """Konvertiert einen Wert sicher zu int mit Fallback auf Default."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning("Ungueltiger %s Wert '%s', verwende Default: %s", name, value, default)
        return default


def _safe_decimal(value, default: Decimal, name: str) -> Decimal:
    """Konvertiert einen Wert sicher zu Decimal mit Fallback auf Default."""
    if value is None:
        return default
    try:
        result = Decimal(str(value))
        if result.is_nan() or result.is_infinite():
            logger.warning("Ungueltiger %s Wert (NaN/Inf), verwende Default: %s", name, default)
            return default
        return result
    except (InvalidOperation, ValueError, TypeError):
        logger.warning("Ungueltiger %s Wert '%s', verwende Default: %s", name, value, default)
        return default


def resolve_interval(
    request_interval: Optional[str],
    user_settings: dict,
) -> str:
    """Interval: Request > User-Setting > Default '4h'."""
    if request_interval is not None:
        return request_interval
    return user_settings.get("interval", "4h")


def resolve_orderblock_config(
    db: Session,
    user_id: str,
    req_config=None,
    request_interval: Optional[str] = None,
) -> tuple[OBConfig, str]:
    """
    Einheitliche Config-Resolution: Laedt User-Settings und loest 3-Tier-Hierarchie auf.

    Returns:
        Tuple[OBConfig, interval_str]
    """
    user_settings = load_user_ob_settings(db, user_id)
    config = build_ob_config(req_config, user_settings)
    interval = resolve_interval(request_interval, user_settings)
    return config, interval
