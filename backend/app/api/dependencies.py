"""Shared FastAPI Dependencies - Zentrale BinanceService-Initialisierung"""
import os
import logging

from fastapi import HTTPException
from app.services.binance import BinanceService

logger = logging.getLogger(__name__)


def get_binance_service() -> BinanceService:
    """
    Zentrale Dependency für BinanceService.

    Liest Credentials aus Environment Variables.
    Konsistent: testnet=false als Default.

    Raises:
        HTTPException 400 wenn Credentials fehlen
    """
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=400,
            detail="Binance API credentials not configured"
        )

    return BinanceService(api_key, api_secret, testnet)


def get_binance_service_optional() -> BinanceService | None:
    """
    Optionale Dependency für BinanceService.

    Gibt None zurück wenn Credentials fehlen (statt Exception).
    Verwendet für Portfolio-Endpoint wo Live-Balances optional sind.
    """
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    if not api_key or not api_secret:
        return None

    try:
        return BinanceService(api_key, api_secret, testnet)
    except Exception as e:
        logger.warning("Could not initialize BinanceService: %s", e)
        return None
