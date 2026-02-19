"""API Key Authentication"""
import hmac
import logging
import os

from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Log auth status once at import time (not per request)
_auth_warned = False


async def require_api_key(api_key: str = Security(api_key_header)):
    """
    Validiert X-API-Key Header gegen API_SECRET_KEY aus Environment.

    In Production (APP_ENV=production) ist API_SECRET_KEY pflicht.
    In Development wird Auth deaktiviert wenn kein Key gesetzt ist.
    Verwendet hmac.compare_digest() fuer timing-safe Vergleich.
    """
    global _auth_warned
    expected = os.getenv("API_SECRET_KEY")
    if not expected:
        if os.getenv("APP_ENV") == "production":
            logger.error("API_SECRET_KEY not set in production — rejecting request")
            raise HTTPException(status_code=500, detail="Server misconfigured")
        if not _auth_warned:
            logger.warning("API_SECRET_KEY not set — auth disabled (dev mode)")
            _auth_warned = True
        return
    if not api_key or not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
