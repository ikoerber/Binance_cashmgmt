"""Settings API Endpoints"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from pydantic import BaseModel, Field
import uuid

from app.db.database import get_db
from app.db.models import UserSettingsDB
from app.domain.models import utcnow

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    max_order_value_eur: float
    macro_signal_interval: str = "15"
    sell_allocation_strategy: str = "FIFO"
    # Orderblock Detection
    ob_interval: Optional[str] = Field(default="4h")
    ob_atr_multiplier: Optional[float] = Field(default=2.0, ge=0.5, le=10.0)
    ob_target_rr: Optional[float] = Field(default=2.0, ge=0.5, le=10.0)
    ob_impulse_window: Optional[int] = Field(default=5, ge=2, le=20)


VALID_STRATEGIES = {"FIFO", "LIFO", "HIGHEST_COST"}
VALID_OB_INTERVALS = {"1h", "4h", "1d"}


def _settings_to_dict(settings: UserSettingsDB) -> dict:
    return {
        "user_id": settings.user_id,
        "max_order_value_eur": float(settings.max_order_value_eur),
        "macro_signal_interval": settings.macro_signal_interval,
        "sell_allocation_strategy": settings.sell_allocation_strategy,
        "ob_interval": settings.ob_interval or "4h",
        "ob_atr_multiplier": float(settings.ob_atr_multiplier) if settings.ob_atr_multiplier is not None else 2.0,
        "ob_target_rr": float(settings.ob_target_rr) if settings.ob_target_rr is not None else 2.0,
        "ob_impulse_window": int(settings.ob_impulse_window) if settings.ob_impulse_window is not None else 5,
    }


DEFAULTS = {
    "max_order_value_eur": 1000.0,
    "macro_signal_interval": "15",
    "sell_allocation_strategy": "FIFO",
    "ob_interval": "4h",
    "ob_atr_multiplier": 2.0,
    "ob_target_rr": 2.0,
    "ob_impulse_window": 5,
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
    settings = db.query(UserSettingsDB).filter(
        UserSettingsDB.user_id == user_id
    ).first()

    if settings:
        return _settings_to_dict(settings)

    return {
        "user_id": user_id,
        **DEFAULTS,
    }


@router.put("/{user_id}")
def update_settings(
    user_id: str,
    body: SettingsUpdate,
    db: Session = Depends(get_db),
):
    """
    Settings fuer User speichern (upsert).
    """
    if body.max_order_value_eur <= 0:
        raise HTTPException(status_code=400, detail="max_order_value_eur muss > 0 sein")
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

    settings = db.query(UserSettingsDB).filter(
        UserSettingsDB.user_id == user_id
    ).first()

    if settings:
        settings.max_order_value_eur = Decimal(str(body.max_order_value_eur))
        settings.macro_signal_interval = body.macro_signal_interval
        settings.sell_allocation_strategy = body.sell_allocation_strategy
        settings.ob_interval = body.ob_interval
        settings.ob_atr_multiplier = Decimal(str(body.ob_atr_multiplier)) if body.ob_atr_multiplier is not None else None
        settings.ob_target_rr = Decimal(str(body.ob_target_rr)) if body.ob_target_rr is not None else None
        settings.ob_impulse_window = body.ob_impulse_window
        settings.updated_at = utcnow()
    else:
        settings = UserSettingsDB(
            id=str(uuid.uuid4()),
            user_id=user_id,
            max_order_value_eur=Decimal(str(body.max_order_value_eur)),
            macro_signal_interval=body.macro_signal_interval,
            sell_allocation_strategy=body.sell_allocation_strategy,
            ob_interval=body.ob_interval,
            ob_atr_multiplier=Decimal(str(body.ob_atr_multiplier)) if body.ob_atr_multiplier is not None else None,
            ob_target_rr=Decimal(str(body.ob_target_rr)) if body.ob_target_rr is not None else None,
            ob_impulse_window=body.ob_impulse_window,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(settings)

    db.commit()
    db.refresh(settings)

    return _settings_to_dict(settings)
