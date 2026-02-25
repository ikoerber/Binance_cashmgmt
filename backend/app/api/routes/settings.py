"""Settings API Endpoints"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from pydantic import BaseModel, Field
import uuid

from app.db.database import get_db
from app.db.models import UserSettingsDB
from app.domain.models import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    max_order_value_eur: str
    macro_signal_interval: str = "15"
    sell_allocation_strategy: str = "FIFO"
    # Orderblock Detection
    ob_interval: Optional[str] = Field(default="4h")
    ob_atr_multiplier: Optional[str] = Field(default="2.0")
    ob_target_rr: Optional[str] = Field(default="2.0")
    ob_impulse_window: Optional[int] = Field(default=5, ge=2, le=20)
    # Reconciliation Thresholds
    recon_tolerance_base: Optional[str] = Field(default=None)
    recon_tolerance_quote: Optional[str] = Field(default=None)
    # Alpha Score Settings
    alpha_score_interval: Optional[str] = Field(default="15m")
    alpha_score_weight_zscore: Optional[str] = Field(default="40")
    alpha_score_weight_leadlag: Optional[str] = Field(default="30")
    alpha_score_weight_imbalance: Optional[str] = Field(default="20")
    alpha_score_weight_funding: Optional[str] = Field(default="10")
    alpha_score_threshold: Optional[str] = Field(default="3.0")
    alpha_score_zscore_window: Optional[int] = Field(default=60)
    alpha_score_leadlag_window: Optional[int] = Field(default=30)
    alpha_score_hurst_lookback: Optional[int] = Field(default=100)
    alpha_score_hurst_trending: Optional[str] = Field(default="0.55")
    alpha_score_hurst_reverting: Optional[str] = Field(default="0.45")
    alpha_score_atr_mult_btc: Optional[str] = Field(default="2.0")
    alpha_score_atr_mult_xrp: Optional[str] = Field(default="3.0")
    alpha_score_stop_resume_n: Optional[int] = Field(default=5)


VALID_STRATEGIES = {"FIFO", "LIFO", "HIGHEST_COST"}
VALID_OB_INTERVALS = {"1h", "4h", "1d"}
VALID_ALPHA_INTERVALS = {"5m", "15m", "1h"}


def _settings_to_dict(settings: UserSettingsDB) -> dict:
    return {
        "user_id": settings.user_id,
        "max_order_value_eur": str(settings.max_order_value_eur),
        "macro_signal_interval": settings.macro_signal_interval,
        "sell_allocation_strategy": settings.sell_allocation_strategy,
        "ob_interval": settings.ob_interval or "4h",
        "ob_atr_multiplier": str(settings.ob_atr_multiplier) if settings.ob_atr_multiplier is not None else "2.0",
        "ob_target_rr": str(settings.ob_target_rr) if settings.ob_target_rr is not None else "2.0",
        "ob_impulse_window": int(settings.ob_impulse_window) if settings.ob_impulse_window is not None else 5,
        "recon_tolerance_base": str(settings.recon_tolerance_base) if settings.recon_tolerance_base is not None else "0.0001",
        "recon_tolerance_quote": str(settings.recon_tolerance_quote) if settings.recon_tolerance_quote is not None else "1.00",
        # Alpha Score Settings
        "alpha_score_interval": settings.alpha_score_interval or "15m",
        "alpha_score_weight_zscore": str(settings.alpha_score_weight_zscore) if settings.alpha_score_weight_zscore is not None else "40",
        "alpha_score_weight_leadlag": str(settings.alpha_score_weight_leadlag) if settings.alpha_score_weight_leadlag is not None else "30",
        "alpha_score_weight_imbalance": str(settings.alpha_score_weight_imbalance) if settings.alpha_score_weight_imbalance is not None else "20",
        "alpha_score_weight_funding": str(settings.alpha_score_weight_funding) if settings.alpha_score_weight_funding is not None else "10",
        "alpha_score_threshold": str(settings.alpha_score_threshold) if settings.alpha_score_threshold is not None else "3.0",
        "alpha_score_zscore_window": int(settings.alpha_score_zscore_window) if settings.alpha_score_zscore_window is not None else 60,
        "alpha_score_leadlag_window": int(settings.alpha_score_leadlag_window) if settings.alpha_score_leadlag_window is not None else 30,
        "alpha_score_hurst_lookback": int(settings.alpha_score_hurst_lookback) if settings.alpha_score_hurst_lookback is not None else 100,
        "alpha_score_hurst_trending": str(settings.alpha_score_hurst_trending) if settings.alpha_score_hurst_trending is not None else "0.55",
        "alpha_score_hurst_reverting": str(settings.alpha_score_hurst_reverting) if settings.alpha_score_hurst_reverting is not None else "0.45",
        "alpha_score_atr_mult_btc": str(settings.alpha_score_atr_mult_btc) if settings.alpha_score_atr_mult_btc is not None else "2.0",
        "alpha_score_atr_mult_xrp": str(settings.alpha_score_atr_mult_xrp) if settings.alpha_score_atr_mult_xrp is not None else "3.0",
        "alpha_score_stop_resume_n": int(settings.alpha_score_stop_resume_n) if settings.alpha_score_stop_resume_n is not None else 5,
    }


DEFAULTS = {
    "max_order_value_eur": "1000",
    "macro_signal_interval": "15",
    "sell_allocation_strategy": "FIFO",
    "ob_interval": "4h",
    "ob_atr_multiplier": "2.0",
    "ob_target_rr": "2.0",
    "ob_impulse_window": 5,
    "recon_tolerance_base": "0.0001",
    "recon_tolerance_quote": "1.00",
    # Alpha Score
    "alpha_score_interval": "15m",
    "alpha_score_weight_zscore": "40",
    "alpha_score_weight_leadlag": "30",
    "alpha_score_weight_imbalance": "20",
    "alpha_score_weight_funding": "10",
    "alpha_score_threshold": "3.0",
    "alpha_score_zscore_window": 60,
    "alpha_score_leadlag_window": 30,
    "alpha_score_hurst_lookback": 100,
    "alpha_score_hurst_trending": "0.55",
    "alpha_score_hurst_reverting": "0.45",
    "alpha_score_atr_mult_btc": "2.0",
    "alpha_score_atr_mult_xrp": "3.0",
    "alpha_score_stop_resume_n": 5,
}


@router.get("/{user_id}")
def get_settings(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Settings fuer User laden.

    Gibt gespeicherte Settings oder Defaults zurueck.
    """
    try:
        settings = db.query(UserSettingsDB).filter(
            UserSettingsDB.user_id == user_id
        ).first()

        if settings:
            return _settings_to_dict(settings)

        return {
            "user_id": user_id,
            **DEFAULTS,
        }
    except Exception:
        logger.exception("Settings GET failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.put("/{user_id}")
def update_settings(
    user_id: str,
    body: SettingsUpdate,
    db: Session = Depends(get_db),
):
    """
    Settings fuer User speichern (upsert).
    """
    # Decimal-Validierung fuer String-Felder
    try:
        max_val = Decimal(body.max_order_value_eur)
    except Exception:
        raise HTTPException(status_code=400, detail="max_order_value_eur muss eine gueltige Zahl sein")
    if max_val.is_nan() or max_val.is_infinite():
        raise HTTPException(status_code=400, detail="max_order_value_eur darf nicht NaN oder Infinity sein")
    if not (Decimal("1") <= max_val <= Decimal("1000000")):
        raise HTTPException(status_code=400, detail="max_order_value_eur muss zwischen 1 und 1000000 liegen")

    ob_atr_mult = None
    if body.ob_atr_multiplier is not None:
        try:
            ob_atr_mult = Decimal(body.ob_atr_multiplier)
        except Exception:
            raise HTTPException(status_code=400, detail="ob_atr_multiplier muss eine gueltige Zahl sein")
        if ob_atr_mult.is_nan() or ob_atr_mult.is_infinite():
            raise HTTPException(status_code=400, detail="ob_atr_multiplier darf nicht NaN oder Infinity sein")
        if not (Decimal("0.5") <= ob_atr_mult <= Decimal("10.0")):
            raise HTTPException(status_code=400, detail="ob_atr_multiplier muss zwischen 0.5 und 10.0 liegen")

    ob_rr = None
    if body.ob_target_rr is not None:
        try:
            ob_rr = Decimal(body.ob_target_rr)
        except Exception:
            raise HTTPException(status_code=400, detail="ob_target_rr muss eine gueltige Zahl sein")
        if ob_rr.is_nan() or ob_rr.is_infinite():
            raise HTTPException(status_code=400, detail="ob_target_rr darf nicht NaN oder Infinity sein")
        if not (Decimal("0.5") <= ob_rr <= Decimal("10.0")):
            raise HTTPException(status_code=400, detail="ob_target_rr muss zwischen 0.5 und 10.0 liegen")

    if body.macro_signal_interval not in ("1", "5", "15"):
        raise HTTPException(status_code=400, detail="macro_signal_interval muss '1', '5' oder '15' sein")
    if body.sell_allocation_strategy not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"sell_allocation_strategy muss einer von {sorted(VALID_STRATEGIES)} sein"
        )
    if body.ob_interval and body.ob_interval not in VALID_OB_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"ob_interval muss einer von {sorted(VALID_OB_INTERVALS)} sein"
        )

    # Reconciliation Threshold Validation
    recon_base = None
    if body.recon_tolerance_base is not None:
        try:
            recon_base = Decimal(body.recon_tolerance_base)
        except Exception:
            raise HTTPException(status_code=400, detail="recon_tolerance_base muss eine gueltige Zahl sein")
        if recon_base.is_nan() or recon_base.is_infinite():
            raise HTTPException(status_code=400, detail="recon_tolerance_base darf nicht NaN oder Infinity sein")
        if recon_base < Decimal("0"):
            raise HTTPException(status_code=400, detail="recon_tolerance_base muss >= 0 sein")

    recon_quote = None
    if body.recon_tolerance_quote is not None:
        try:
            recon_quote = Decimal(body.recon_tolerance_quote)
        except Exception:
            raise HTTPException(status_code=400, detail="recon_tolerance_quote muss eine gueltige Zahl sein")
        if recon_quote.is_nan() or recon_quote.is_infinite():
            raise HTTPException(status_code=400, detail="recon_tolerance_quote darf nicht NaN oder Infinity sein")
        if recon_quote < Decimal("0"):
            raise HTTPException(status_code=400, detail="recon_tolerance_quote muss >= 0 sein")

    # Alpha Score Validation
    if body.alpha_score_interval and body.alpha_score_interval not in VALID_ALPHA_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"alpha_score_interval muss einer von {sorted(VALID_ALPHA_INTERVALS)} sein"
        )

    # Validate and parse alpha score weights
    alpha_weights = {}
    for wname in ("zscore", "leadlag", "imbalance", "funding"):
        field_name = f"alpha_score_weight_{wname}"
        raw_val = getattr(body, field_name)
        if raw_val is not None:
            try:
                wval = Decimal(raw_val)
            except Exception:
                raise HTTPException(status_code=400, detail=f"{field_name} muss eine gueltige Zahl sein")
            if wval.is_nan() or wval.is_infinite():
                raise HTTPException(status_code=400, detail=f"{field_name} darf nicht NaN oder Infinity sein")
            if not (Decimal("0") <= wval <= Decimal("100")):
                raise HTTPException(status_code=400, detail=f"{field_name} muss zwischen 0 und 100 liegen")
            alpha_weights[wname] = wval

    # Auto-normalize weights to sum to 100%
    if alpha_weights:
        weight_sum = sum(alpha_weights.values())
        if weight_sum > Decimal("0"):
            for wname in alpha_weights:
                alpha_weights[wname] = (alpha_weights[wname] / weight_sum * Decimal("100")).quantize(Decimal("0.01"))

    alpha_threshold = None
    if body.alpha_score_threshold is not None:
        try:
            alpha_threshold = Decimal(body.alpha_score_threshold)
        except Exception:
            raise HTTPException(status_code=400, detail="alpha_score_threshold muss eine gueltige Zahl sein")
        if alpha_threshold.is_nan() or alpha_threshold.is_infinite():
            raise HTTPException(status_code=400, detail="alpha_score_threshold darf nicht NaN oder Infinity sein")
        if not (Decimal("0.1") <= alpha_threshold <= Decimal("5.0")):
            raise HTTPException(status_code=400, detail="alpha_score_threshold muss zwischen 0.1 und 5.0 liegen")

    # Validate integer windows
    if body.alpha_score_zscore_window is not None:
        if not (10 <= body.alpha_score_zscore_window <= 500):
            raise HTTPException(status_code=400, detail="alpha_score_zscore_window muss zwischen 10 und 500 liegen")
    if body.alpha_score_leadlag_window is not None:
        if not (10 <= body.alpha_score_leadlag_window <= 500):
            raise HTTPException(status_code=400, detail="alpha_score_leadlag_window muss zwischen 10 und 500 liegen")
    if body.alpha_score_hurst_lookback is not None:
        if not (10 <= body.alpha_score_hurst_lookback <= 500):
            raise HTTPException(status_code=400, detail="alpha_score_hurst_lookback muss zwischen 10 und 500 liegen")

    # Validate Hurst thresholds (0.0-1.0)
    alpha_hurst_trending = None
    if body.alpha_score_hurst_trending is not None:
        try:
            alpha_hurst_trending = Decimal(body.alpha_score_hurst_trending)
        except Exception:
            raise HTTPException(status_code=400, detail="alpha_score_hurst_trending muss eine gueltige Zahl sein")
        if alpha_hurst_trending.is_nan() or alpha_hurst_trending.is_infinite():
            raise HTTPException(status_code=400, detail="alpha_score_hurst_trending darf nicht NaN oder Infinity sein")
        if not (Decimal("0") <= alpha_hurst_trending <= Decimal("1")):
            raise HTTPException(status_code=400, detail="alpha_score_hurst_trending muss zwischen 0.0 und 1.0 liegen")

    alpha_hurst_reverting = None
    if body.alpha_score_hurst_reverting is not None:
        try:
            alpha_hurst_reverting = Decimal(body.alpha_score_hurst_reverting)
        except Exception:
            raise HTTPException(status_code=400, detail="alpha_score_hurst_reverting muss eine gueltige Zahl sein")
        if alpha_hurst_reverting.is_nan() or alpha_hurst_reverting.is_infinite():
            raise HTTPException(status_code=400, detail="alpha_score_hurst_reverting darf nicht NaN oder Infinity sein")
        if not (Decimal("0") <= alpha_hurst_reverting <= Decimal("1")):
            raise HTTPException(status_code=400, detail="alpha_score_hurst_reverting muss zwischen 0.0 und 1.0 liegen")

    # Validate ATR multipliers (0.5-10.0)
    alpha_atr_btc = None
    if body.alpha_score_atr_mult_btc is not None:
        try:
            alpha_atr_btc = Decimal(body.alpha_score_atr_mult_btc)
        except Exception:
            raise HTTPException(status_code=400, detail="alpha_score_atr_mult_btc muss eine gueltige Zahl sein")
        if alpha_atr_btc.is_nan() or alpha_atr_btc.is_infinite():
            raise HTTPException(status_code=400, detail="alpha_score_atr_mult_btc darf nicht NaN oder Infinity sein")
        if not (Decimal("0.5") <= alpha_atr_btc <= Decimal("10.0")):
            raise HTTPException(status_code=400, detail="alpha_score_atr_mult_btc muss zwischen 0.5 und 10.0 liegen")

    alpha_atr_xrp = None
    if body.alpha_score_atr_mult_xrp is not None:
        try:
            alpha_atr_xrp = Decimal(body.alpha_score_atr_mult_xrp)
        except Exception:
            raise HTTPException(status_code=400, detail="alpha_score_atr_mult_xrp muss eine gueltige Zahl sein")
        if alpha_atr_xrp.is_nan() or alpha_atr_xrp.is_infinite():
            raise HTTPException(status_code=400, detail="alpha_score_atr_mult_xrp darf nicht NaN oder Infinity sein")
        if not (Decimal("0.5") <= alpha_atr_xrp <= Decimal("10.0")):
            raise HTTPException(status_code=400, detail="alpha_score_atr_mult_xrp muss zwischen 0.5 und 10.0 liegen")

    # Validate stop resume N (1-50)
    if body.alpha_score_stop_resume_n is not None:
        if not (1 <= body.alpha_score_stop_resume_n <= 50):
            raise HTTPException(status_code=400, detail="alpha_score_stop_resume_n muss zwischen 1 und 50 liegen")

    try:
        # Row-Level Lock: verhindert Lost Updates bei konkurrierenden Requests
        settings = db.query(UserSettingsDB).filter(
            UserSettingsDB.user_id == user_id
        ).with_for_update().first()

        if settings:
            settings.max_order_value_eur = max_val
            settings.macro_signal_interval = body.macro_signal_interval
            settings.sell_allocation_strategy = body.sell_allocation_strategy
            settings.ob_interval = body.ob_interval
            settings.ob_atr_multiplier = ob_atr_mult
            settings.ob_target_rr = ob_rr
            settings.ob_impulse_window = body.ob_impulse_window
            if recon_base is not None:
                settings.recon_tolerance_base = recon_base
            if recon_quote is not None:
                settings.recon_tolerance_quote = recon_quote
            # Alpha Score Settings
            settings.alpha_score_interval = body.alpha_score_interval
            settings.alpha_score_weight_zscore = alpha_weights.get("zscore")
            settings.alpha_score_weight_leadlag = alpha_weights.get("leadlag")
            settings.alpha_score_weight_imbalance = alpha_weights.get("imbalance")
            settings.alpha_score_weight_funding = alpha_weights.get("funding")
            settings.alpha_score_threshold = alpha_threshold
            settings.alpha_score_zscore_window = body.alpha_score_zscore_window
            settings.alpha_score_leadlag_window = body.alpha_score_leadlag_window
            settings.alpha_score_hurst_lookback = body.alpha_score_hurst_lookback
            settings.alpha_score_hurst_trending = alpha_hurst_trending
            settings.alpha_score_hurst_reverting = alpha_hurst_reverting
            settings.alpha_score_atr_mult_btc = alpha_atr_btc
            settings.alpha_score_atr_mult_xrp = alpha_atr_xrp
            settings.alpha_score_stop_resume_n = body.alpha_score_stop_resume_n
            settings.updated_at = utcnow()
        else:
            settings = UserSettingsDB(
                id=str(uuid.uuid4()),
                user_id=user_id,
                max_order_value_eur=max_val,
                macro_signal_interval=body.macro_signal_interval,
                sell_allocation_strategy=body.sell_allocation_strategy,
                ob_interval=body.ob_interval,
                ob_atr_multiplier=ob_atr_mult,
                ob_target_rr=ob_rr,
                ob_impulse_window=body.ob_impulse_window,
                recon_tolerance_base=recon_base,
                recon_tolerance_quote=recon_quote,
                # Alpha Score Settings
                alpha_score_interval=body.alpha_score_interval,
                alpha_score_weight_zscore=alpha_weights.get("zscore"),
                alpha_score_weight_leadlag=alpha_weights.get("leadlag"),
                alpha_score_weight_imbalance=alpha_weights.get("imbalance"),
                alpha_score_weight_funding=alpha_weights.get("funding"),
                alpha_score_threshold=alpha_threshold,
                alpha_score_zscore_window=body.alpha_score_zscore_window,
                alpha_score_leadlag_window=body.alpha_score_leadlag_window,
                alpha_score_hurst_lookback=body.alpha_score_hurst_lookback,
                alpha_score_hurst_trending=alpha_hurst_trending,
                alpha_score_hurst_reverting=alpha_hurst_reverting,
                alpha_score_atr_mult_btc=alpha_atr_btc,
                alpha_score_atr_mult_xrp=alpha_atr_xrp,
                alpha_score_stop_resume_n=body.alpha_score_stop_resume_n,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            db.add(settings)

        db.flush()

        return _settings_to_dict(settings)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Settings PUT failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
