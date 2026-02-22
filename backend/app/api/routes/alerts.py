"""Alert API Endpoints"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.db.models import AlertEventDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _serialize_alert(alert: AlertEventDB) -> dict:
    """Serialize AlertEventDB to API response dict."""
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title,
        "details": alert.details_json,
        "acknowledged": alert.acknowledged,
        "acknowledged_at": (
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
        ),
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "reconciliation_run_id": alert.reconciliation_run_id,
    }


@router.get("/{user_id}")
def list_alerts(
    user_id: str,
    include_acknowledged: bool = Query(False, description="Include acknowledged alerts"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    List alerts for user.

    Returns unacknowledged alerts by default. Set include_acknowledged=true
    to include all alerts.

    Args:
        user_id: User ID
        include_acknowledged: Include acknowledged alerts (default: false)
        limit: Max results (1-200, default: 50)
        offset: Pagination offset
        db: Database Session (injected)

    Returns:
        Alerts list with total and unacknowledged_count
    """
    try:
        base_query = db.query(AlertEventDB).filter(
            AlertEventDB.user_id == user_id
        )

        # Always compute unacknowledged count (regardless of filter)
        unacknowledged_count = (
            db.query(func.count(AlertEventDB.id))
            .filter(
                AlertEventDB.user_id == user_id,
                AlertEventDB.acknowledged == False,  # noqa: E712
            )
            .scalar()
        ) or 0

        # Apply filter
        if not include_acknowledged:
            base_query = base_query.filter(
                AlertEventDB.acknowledged == False  # noqa: E712
            )

        total = base_query.count()

        alerts_db = (
            base_query.order_by(AlertEventDB.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        return {
            "alerts": [_serialize_alert(a) for a in alerts_db],
            "total": total,
            "unacknowledged_count": unacknowledged_count,
        }
    except Exception:
        logger.exception("Failed to list alerts for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.patch("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    user_id: str = Query(..., description="User ID (IDOR protection)"),
    db: Session = Depends(get_db),
):
    """
    Acknowledge/dismiss a single alert.

    IDOR-protected: user_id must match the alert's user_id.

    Args:
        alert_id: Alert ID
        user_id: User ID (query param for IDOR protection)
        db: Database Session (injected)

    Returns:
        Updated alert dict
    """
    try:
        alert_db = (
            db.query(AlertEventDB)
            .filter(
                AlertEventDB.id == alert_id,
                AlertEventDB.user_id == user_id,
            )
            .first()
        )

        if not alert_db:
            raise HTTPException(
                status_code=404, detail="Alert nicht gefunden"
            )

        alert_db.acknowledged = True
        alert_db.acknowledged_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.flush()

        return _serialize_alert(alert_db)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to acknowledge alert=%s for user=%s", alert_id, user_id
        )
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/acknowledge-all")
def acknowledge_all_alerts(
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Bulk acknowledge all unacknowledged alerts for user.

    Args:
        user_id: User ID
        db: Database Session (injected)

    Returns:
        Count of acknowledged alerts
    """
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        acknowledged_count = (
            db.query(AlertEventDB)
            .filter(
                AlertEventDB.user_id == user_id,
                AlertEventDB.acknowledged == False,  # noqa: E712
            )
            .update(
                {"acknowledged": True, "acknowledged_at": now},
                synchronize_session="fetch",
            )
        )

        db.flush()

        return {"acknowledged_count": acknowledged_count}
    except Exception:
        logger.exception(
            "Failed to bulk acknowledge alerts for user=%s", user_id
        )
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
