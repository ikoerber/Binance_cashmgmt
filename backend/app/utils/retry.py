"""
Retry-Decorator mit Exponential Backoff fuer transiente Fehler.

Verwendet fuer Binance API Calls (429 Rate Limit, 5xx Server Errors, Timeouts).

Features:
- Strukturierte Error Classification (transient vs. permanent)
- Retry-After Header Respektierung fuer 429 Responses
- BinanceAPIError Exception mit Klassifikations-Metadaten
- Exponential Backoff mit Jitter
"""

import functools
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Optionaler Import: python-binance Exception
try:
    from binance.exceptions import BinanceAPIException
except ImportError:
    BinanceAPIException = None


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class ErrorClassification:
    """Strukturierte Fehler-Klassifikation.

    Attributes:
        is_transient: True wenn der Fehler transient ist (Retry sinnvoll)
        category: Fehler-Kategorie ("rate_limit", "server_error", "timeout",
                  "connection_error", "client_error", "unknown")
        status_code: HTTP Status Code (falls verfuegbar)
        retry_after: Wartezeit in Sekunden aus Retry-After Header (falls verfuegbar)
    """

    is_transient: bool
    category: str
    status_code: Optional[int] = None
    retry_after: Optional[float] = None


class BinanceAPIError(Exception):
    """Strukturierter Fehler-Wrapper fuer Binance API Fehler.

    Wird vom retry-Decorator geworfen wenn:
    - Alle Retries erschoepft sind (transient error)
    - Ein permanenter Fehler auftritt (sofort, kein Retry)

    Attributes:
        message: Fehlermeldung
        original_exception: Die urspruengliche Exception
        classification: ErrorClassification mit Kategorie und Metadaten
        attempts: Anzahl der durchgefuehrten Versuche
    """

    def __init__(
        self,
        message: str,
        original_exception: Exception,
        classification: ErrorClassification,
        attempts: int,
    ):
        self.message = message
        self.original_exception = original_exception
        self.classification = classification
        self.attempts = attempts
        super().__init__(str(self))

    def __str__(self):
        return (
            f"{self.classification.category}: {self.message} "
            f"(attempts={self.attempts}, status={self.classification.status_code})"
        )


# ============================================================
# Error Classification
# ============================================================


def _extract_retry_after(response) -> Optional[float]:
    """Extrahiert Retry-After Header als float (Sekunden).

    Args:
        response: HTTP Response Objekt mit .headers Dict

    Returns:
        Wartezeit in Sekunden oder None wenn Header nicht vorhanden/ungueltig
    """
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    retry_after = headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return float(retry_after)
    except (ValueError, TypeError):
        return None


def classify_error(exc: Exception) -> ErrorClassification:
    """Klassifiziert eine Exception als transient oder permanent.

    Klassifikationsregeln:
    - BinanceAPIException 429 -> transient, rate_limit (mit Retry-After)
    - BinanceAPIException >= 500 -> transient, server_error
    - BinanceAPIException 4xx (nicht 429) -> permanent, client_error
    - requests.Timeout -> transient, timeout
    - requests.ConnectionError -> transient, connection_error
    - requests.HTTPError 429 -> transient, rate_limit (mit Retry-After)
    - requests.HTTPError >= 500 -> transient, server_error
    - requests.HTTPError 4xx (nicht 429) -> permanent, client_error
    - Alle anderen -> permanent, unknown

    Args:
        exc: Die zu klassifizierende Exception

    Returns:
        ErrorClassification mit is_transient, category, status_code, retry_after
    """
    # Timeouts und Verbindungsfehler (vor HTTPError pruefen, da ConnectionError
    # auch von requests kommt und spezifischer ist)
    if isinstance(exc, requests.exceptions.Timeout):
        return ErrorClassification(
            is_transient=True,
            category="timeout",
        )

    if isinstance(exc, requests.exceptions.ConnectionError):
        return ErrorClassification(
            is_transient=True,
            category="connection_error",
        )

    # Binance API: 429 (Rate Limit) und 5xx (Server Error)
    if BinanceAPIException and isinstance(exc, BinanceAPIException):
        status = exc.status_code
        if status == 429:
            retry_after = _extract_retry_after(exc.response)
            return ErrorClassification(
                is_transient=True,
                category="rate_limit",
                status_code=429,
                retry_after=retry_after,
            )
        if status >= 500:
            return ErrorClassification(
                is_transient=True,
                category="server_error",
                status_code=status,
            )
        # 4xx Client-Fehler (ausser 429): permanent
        return ErrorClassification(
            is_transient=False,
            category="client_error",
            status_code=status,
        )

    # requests HTTP-Fehler (fuer direkten requests.get()-Aufruf)
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is not None:
            status = response.status_code
            if status == 429:
                retry_after = _extract_retry_after(response)
                return ErrorClassification(
                    is_transient=True,
                    category="rate_limit",
                    status_code=429,
                    retry_after=retry_after,
                )
            if status >= 500:
                return ErrorClassification(
                    is_transient=True,
                    category="server_error",
                    status_code=status,
                )
            return ErrorClassification(
                is_transient=False,
                category="client_error",
                status_code=status,
            )
        return ErrorClassification(
            is_transient=False,
            category="unknown",
        )

    # Alle anderen: permanent, unknown
    return ErrorClassification(
        is_transient=False,
        category="unknown",
    )


def _is_retryable(exc: Exception) -> bool:
    """Prueft ob der Fehler transient ist und ein Retry sinnvoll waere.

    Backward-Compatibility Wrapper fuer classify_error().
    """
    return classify_error(exc).is_transient


# ============================================================
# Retry Decorator
# ============================================================


def retry_on_transient_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
):
    """
    Decorator: Wiederholt Funktionsaufrufe bei transienten Fehlern.

    Exponential Backoff mit Jitter:
        delay = min(base_delay * 2^attempt + jitter, max_delay)

    Bei 429 Rate-Limit mit Retry-After Header:
        delay = max(computed_delay, retry_after)

    Permanente Fehler (4xx ausser 429, unbekannte) werden sofort als
    BinanceAPIError propagiert (kein Retry).

    Nach Erschoepfung aller Retries wird BinanceAPIError mit der
    Anzahl der Versuche geworfen.

    Args:
        max_retries: Maximale Anzahl Wiederholungen (Default: 3)
        base_delay: Basis-Wartezeit in Sekunden (Default: 1.0)
        max_delay: Maximale Wartezeit in Sekunden (Default: 30.0)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    classification = classify_error(exc)
                    total_attempts = attempt + 1

                    # Permanenter Fehler: sofort als BinanceAPIError propagieren
                    if not classification.is_transient:
                        raise BinanceAPIError(
                            message=str(exc),
                            original_exception=exc,
                            classification=classification,
                            attempts=total_attempts,
                        ) from exc

                    # Letzter Versuch erschoepft: BinanceAPIError werfen
                    if attempt >= max_retries:
                        raise BinanceAPIError(
                            message=str(exc),
                            original_exception=exc,
                            classification=classification,
                            attempts=total_attempts,
                        ) from exc

                    # Backoff berechnen
                    delay = min(base_delay * (2**attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.25)
                    total_delay = delay + jitter

                    # Retry-After Header respektieren (Minimum-Wartezeit)
                    if classification.retry_after is not None:
                        if total_delay < classification.retry_after:
                            logger.info(
                                "Using Retry-After header value %.1fs "
                                "(computed backoff: %.1fs) for %s",
                                classification.retry_after,
                                total_delay,
                                func.__name__,
                            )
                            total_delay = classification.retry_after

                    logger.warning(
                        "Retry %d/%d for %s after %.1fs "
                        "(category: %s, status: %s, error: %s)",
                        attempt + 1,
                        max_retries,
                        func.__name__,
                        total_delay,
                        classification.category,
                        classification.status_code,
                        exc,
                    )
                    time.sleep(total_delay)

        return wrapper

    return decorator
