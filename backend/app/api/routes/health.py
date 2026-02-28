"""Health Check API Endpoint"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.health_check_service import get_health_check_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/{user_id}")
async def get_health(user_id: str):
    """
    Health Check: Returns structured status for all 8 core services.

    Response cached for 5 seconds to prevent excessive polling.
    Each service includes status (ok/stale/degraded/stopped/unavailable/error)
    and last_checked timestamp.
    """
    try:
        service = get_health_check_service()
        result = await service.get_health()

        response = JSONResponse(content=result)
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        logger.exception("Health check failed")
        return JSONResponse(
            content={
                "overall_status": "critical",
                "services": {},
                "checked_at": None,
                "error": "Health check service unavailable",
            },
            status_code=503,
        )
