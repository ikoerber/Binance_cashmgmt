"""Shared FastAPI Dependencies - Zentrale BinanceService-Initialisierung"""
import os
import logging
import threading

from fastapi import HTTPException
from app.services.binance import BinanceService

logger = logging.getLogger(__name__)

# Singleton BinanceService — wird einmal pro Credential-Kombination erstellt.
# Vermeidet: neue HTTPS-Session pro Request, Rate-Limit-State-Verlust.
_binance_service: BinanceService | None = None
_binance_lock = threading.Lock()


def _get_or_create_binance_service() -> BinanceService:
    """
    Thread-safe Singleton fuer BinanceService.

    Erstellt den Client einmalig und cached ihn fuer alle nachfolgenden Requests.
    Connection-Pooling und Rate-Limit-State bleiben so erhalten.
    """
    global _binance_service

    if _binance_service is not None:
        return _binance_service

    with _binance_lock:
        # Double-checked locking
        if _binance_service is not None:
            return _binance_service

        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

        if not api_key or not api_secret:
            raise HTTPException(
                status_code=400,
                detail="Binance API credentials not configured"
            )

        _binance_service = BinanceService(api_key, api_secret, testnet)
        logger.info("BinanceService initialized (testnet=%s)", testnet)
        return _binance_service


def get_binance_service() -> BinanceService:
    """
    Zentrale Dependency fuer BinanceService.

    Singleton: Client wird einmalig erstellt und wiederverwendet.
    Connection-Pooling und Rate-Limit-State bleiben erhalten.

    Raises:
        HTTPException 400 wenn Credentials fehlen
    """
    return _get_or_create_binance_service()


def get_binance_service_optional() -> BinanceService | None:
    """
    Optionale Dependency fuer BinanceService.

    Gibt None zurueck wenn Credentials fehlen (statt Exception).
    Verwendet fuer Portfolio-Endpoint wo Live-Balances optional sind.
    """
    try:
        return _get_or_create_binance_service()
    except HTTPException:
        return None
    except Exception as e:
        logger.warning("Could not initialize BinanceService: %s", e)
        return None


def reset_binance_service():
    """
    Setzt den Singleton zurueck (fuer Tests).
    """
    global _binance_service
    with _binance_lock:
        _binance_service = None
