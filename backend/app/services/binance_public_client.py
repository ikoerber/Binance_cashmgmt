"""
Binance Public Client - Zentraler Client fuer oeffentliche Binance REST API Endpunkte.

Kein API-Key erforderlich. Verwendet fuer Marktdaten (Klines, Ticker) in:
- MacroDataService
- SentimentDataService
- OrderblockDataService
- BinanceService.get_historical_price()
"""

import logging
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import requests

from app.utils.retry import retry_on_transient_error

logger = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com"
TIMEOUT = 10  # Sekunden


class CachedValue:
    """Einfacher Cache-Eintrag mit TTL."""

    def __init__(self, value, fetched_at: datetime, ttl: timedelta):
        self.value = value
        self.fetched_at = fetched_at
        self.ttl = ttl

    def is_expired(self, now: datetime) -> bool:
        return (now - self.fetched_at) > self.ttl

    def is_stale(self, now: datetime, stale_factor: int = 6) -> bool:
        """Stale = deutlich aelter als TTL (z.B. 6x)."""
        return (now - self.fetched_at) > (self.ttl * stale_factor)


class BinancePublicClient:
    """
    Leichtgewichtiger Client fuer oeffentliche Binance REST API Endpunkte.

    - Kein API-Key, kein Testnet-Switch (oeffentliche Daten sind identisch)
    - Retry mit Exponential Backoff bei 429/5xx
    - Zentralisiert URL, Timeout und Error-Handling
    - Timeout konfigurierbar (Default: TIMEOUT Modul-Konstante)
    """

    def __init__(self, timeout: int = TIMEOUT):
        """
        Args:
            timeout: Request Timeout in Sekunden (Default: 10)
        """
        self.timeout = timeout
        self._exchange_info_cache: dict[str, CachedValue] = {}
        self._exchange_info_lock = threading.Lock()

    @retry_on_transient_error()
    def get_ticker_price(self, symbol: str) -> Decimal:
        """
        Holt aktuellen Ticker-Preis.

        GET /api/v3/ticker/price

        Args:
            symbol: Trading Pair (z.B. "BTCEUR")

        Returns:
            Aktueller Preis als Decimal
        """
        resp = requests.get(
            f"{BASE_URL}/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return Decimal(resp.json()["price"])

    @retry_on_transient_error()
    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list:
        """
        Holt OHLCV Klines.

        GET /api/v3/klines

        Args:
            symbol: Trading Pair (z.B. "BTCEUR")
            interval: Kline-Intervall (z.B. "1m", "1h", "1d")
            limit: Max Kerzen pro Request (max 1000)
            start_time: Start-Timestamp in Millisekunden (optional)
            end_time: End-Timestamp in Millisekunden (optional)

        Returns:
            Liste von Kline-Arrays (Binance Raw Format)
        """
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        resp = requests.get(
            f"{BASE_URL}/api/v3/klines",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    @retry_on_transient_error()
    def _fetch_exchange_info(self, symbol: str) -> dict:
        """
        Holt Exchange Info fuer ein Symbol von Binance.

        GET /api/v3/exchangeInfo?symbol=...

        Returns:
            Symbol-Info Dict mit 'filters' Array
        """
        resp = requests.get(
            f"{BASE_URL}/api/v3/exchangeInfo",
            params={"symbol": symbol},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        symbols = data.get("symbols", [])
        if not symbols:
            raise ValueError(f"Keine Exchange Info fuer {symbol}")
        return symbols[0]

    def get_symbol_filters(self, symbol: str) -> "SymbolFilters":
        """
        Gibt gecachte SymbolFilters zurueck (24h TTL).

        Returns:
            SymbolFilters Dataclass mit LOT_SIZE, PRICE_FILTER, NOTIONAL
        """
        from app.domain.orders import parse_symbol_filters

        now = datetime.now()
        cache_key = f"filters_{symbol}"

        with self._exchange_info_lock:
            cached = self._exchange_info_cache.get(cache_key)
            if cached and not cached.is_expired(now):
                return cached.value

        # Fetch ausserhalb des Locks (I/O)
        raw = self._fetch_exchange_info(symbol)
        filters = parse_symbol_filters(raw.get("filters", []))

        with self._exchange_info_lock:
            self._exchange_info_cache[cache_key] = CachedValue(
                value=filters,
                fetched_at=now,
                ttl=timedelta(hours=24),
            )
        return filters


# ─── Singleton ───

_instance: Optional[BinancePublicClient] = None
_instance_lock = threading.Lock()


def get_binance_public_client(timeout: Optional[int] = None) -> BinancePublicClient:
    """Liefert Singleton-Instanz des BinancePublicClient.

    Args:
        timeout: Optional timeout override (nur bei Erstinitialisierung wirksam)
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = BinancePublicClient(timeout=timeout or TIMEOUT)
    return _instance
