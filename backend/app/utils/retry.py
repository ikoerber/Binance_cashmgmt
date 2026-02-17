"""
Retry-Decorator mit Exponential Backoff fuer transiente Fehler.

Verwendet fuer Binance API Calls (429 Rate Limit, 5xx Server Errors, Timeouts).
"""
import functools
import logging
import random
import time

import requests

logger = logging.getLogger(__name__)

# Optionaler Import: python-binance Exception
try:
    from binance.exceptions import BinanceAPIException
except ImportError:
    BinanceAPIException = None


def _is_retryable(exc: Exception) -> bool:
    """Prueft ob der Fehler transient ist und ein Retry sinnvoll waere."""
    # Timeouts und Verbindungsfehler
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True

    # Binance API: 429 (Rate Limit) und 5xx (Server Error)
    if BinanceAPIException and isinstance(exc, BinanceAPIException):
        if exc.status_code == 429:
            return True
        if exc.status_code >= 500:
            return True
        # 4xx Client-Fehler (ausser 429): kein Retry
        return False

    # requests HTTP-Fehler (fuer direkten requests.get()-Aufruf)
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is not None:
            if response.status_code == 429 or response.status_code >= 500:
                return True
        return False

    return False


def retry_on_transient_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
):
    """
    Decorator: Wiederholt Funktionsaufrufe bei transienten Fehlern.

    Exponential Backoff mit Jitter:
        delay = min(base_delay * 2^attempt + jitter, max_delay)

    Args:
        max_retries: Maximale Anzahl Wiederholungen (Default: 3)
        base_delay: Basis-Wartezeit in Sekunden (Default: 1.0)
        max_delay: Maximale Wartezeit in Sekunden (Default: 30.0)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt >= max_retries or not _is_retryable(exc):
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.25)
                    total_delay = delay + jitter
                    logger.warning(
                        "Retry %d/%d for %s after %.1fs (error: %s)",
                        attempt + 1, max_retries, func.__name__,
                        total_delay, exc,
                    )
                    time.sleep(total_delay)
            raise last_exception  # Sollte nie erreicht werden
        return wrapper
    return decorator
