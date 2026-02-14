"""API Key Authentication"""
import os

from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(api_key_header)):
    """
    Validiert X-API-Key Header gegen API_SECRET_KEY aus Environment.

    Wenn API_SECRET_KEY nicht gesetzt ist, wird Auth deaktiviert (Development).
    """
    expected = os.getenv("API_SECRET_KEY")
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
