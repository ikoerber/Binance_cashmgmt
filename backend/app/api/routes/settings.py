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


VALID_STRATEGIES = {"FIFO", "LIFO", "HIGHEST_COST"}
VALID_OB_INTERVALS = {"1h", "4h", "1d"}


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
