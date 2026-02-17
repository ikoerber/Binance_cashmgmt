"""
Makro-Daten-Service - Fetcht und cached Makro-Indikatoren

Datenquellen:
- Binance REST API (oeffentlich, kein Key): BTC/USDT, BTC/EUR, EUR/USDT
- Twelve Data API (Free Tier, 800 req/Tag): DXY, US02Y, DE02Y

Haelt eine In-Memory Rolling History fuer konfigurierbare Intervall-Vergleiche (1m/5m/15m).
"""

import os
import logging
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests

from app.domain.macro_signal import (
    MacroIndicator,
    MacroSignalResult,
    compute_change_pct,
    compute_derived_eur_usd,
    compute_macro_signal,
    compute_yield_spread,
)
from app.services.binance_public_client import CachedValue, get_binance_public_client

logger = logging.getLogger(__name__)

# ─── Konfiguration ───

TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
ECB_URL = "https://data-api.ecb.europa.eu/service/data"

# Cache-TTLs
BINANCE_CACHE_TTL = timedelta(seconds=30)
TWELVE_DATA_CACHE_TTL = timedelta(minutes=5)
FRED_CACHE_TTL = timedelta(hours=1)  # Yield-Daten aendern sich nur taeglich
ECB_CACHE_TTL = timedelta(hours=1)

# History: 1 Eintrag pro ~30s = 120 Eintraege = ~60 Min
HISTORY_MAX_LEN = 120

# Binance Kline Intervall-Mapping
BINANCE_INTERVAL_MAP = {1: "1m", 5: "5m", 15: "15m"}

# Twelve Data Intervall-Mapping
TWELVE_DATA_INTERVAL_MAP = {1: "1min", 5: "5min", 15: "15min"}

# Request-Timeout
REQUEST_TIMEOUT = 10  # Sekunden


class MacroDataService:
    """
    Singleton-Service fuer Makro-Indikatoren.

    Thread-safe via Lock. Haelt in-Memory Cache und Rolling History.
    """

    def __init__(self):
        self._cache: dict[str, CachedValue] = {}
        self._history: deque = deque(maxlen=HISTORY_MAX_LEN)
        self._lock = threading.Lock()
        self._twelve_data_api_key = os.getenv("TWELVE_DATA_API_KEY", "")
        self._fred_api_key = os.getenv("FRED_API_KEY", "")

    def get_signal(self, interval_minutes: int = 15) -> MacroSignalResult:
        """
        Holt aktuelle Indikatoren, berechnet Signal.

        Args:
            interval_minutes: Signal-Intervall (1, 5 oder 15 Minuten).

        Returns:
            MacroSignalResult mit Indikatoren, Scores und Empfehlung.
        """
        if interval_minutes not in (1, 5, 15):
            interval_minutes = 15

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        with self._lock:
            # 1. Daten holen/refreshen (Intervall-spezifische Klines)
            binance_data = self._get_binance_prices(now, interval_minutes)
            twelve_data = self._get_twelve_data(now, interval_minutes)
            fred_data = self._get_fred_yields(now)
            ecb_data = self._get_ecb_yields(now)

            # 2. Indikatoren zusammenbauen
            indicators = self._build_indicators(
                binance_data, twelve_data, fred_data, ecb_data, now
            )

            # 3. History aktualisieren
            current_snapshot = {
                k: ind.current
                for k, ind in indicators.items()
                if ind.current is not None
            }
            if current_snapshot:
                self._history.append((now, current_snapshot))

            # 4. Vergleichswerte einsetzen (Lookback = Intervall)
            self._fill_previous_values(
                indicators, now, lookback_minutes=interval_minutes
            )

        # 5. Signal berechnen (pure Funktion, ausserhalb Lock)
        return compute_macro_signal(indicators, interval_minutes=interval_minutes)

    # ─── Binance ───

    def _get_binance_prices(self, now: datetime, interval_minutes: int = 15) -> dict:
        """Fetcht oder liefert gecachte Binance-Preise (Intervall-spezifisch)."""
        cache_key = f"binance_prices_{interval_minutes}"
        cached = self._cache.get(cache_key)

        if cached and not cached.is_expired(now):
            return cached.value

        try:
            data = self._fetch_binance_prices(interval_minutes)
            self._cache[cache_key] = CachedValue(data, now, BINANCE_CACHE_TTL)
            return data
        except Exception as e:
            logger.warning(f"Binance API Fehler: {e}")
            if cached:
                return cached.value
            return {}

    def _fetch_binance_prices(self, interval_minutes: int = 15) -> dict:
        """Holt BTCUSDT, BTCEUR, EURUSDT von Binance Public API mit konfigurierbaren Klines."""
        client = get_binance_public_client()
        symbols = ["BTCUSDT", "BTCEUR", "EURUSDT"]
        kline_interval = BINANCE_INTERVAL_MAP.get(interval_minutes, "15m")
        result = {}

        for symbol in symbols:
            try:
                # Aktueller Preis
                price = client.get_ticker_price(symbol)
                result[symbol] = {"current": price}

                # Klines fuer Vergleichswert (limit=2: vorherige + aktuelle Kerze)
                klines = client.get_klines(symbol, kline_interval, limit=2)
                if len(klines) >= 2:
                    # klines[0] = vorherige abgeschlossene Kerze, close = index 4
                    result[symbol]["previous"] = Decimal(klines[0][4])
            except Exception as e:
                logger.warning(f"Binance {symbol} Fehler: {e}")

        return result

    # ─── Twelve Data ───

    def _get_twelve_data(self, now: datetime, interval_minutes: int = 15) -> dict:
        """Fetcht oder liefert gecachte Twelve Data Indikatoren (Intervall-spezifisch)."""
        if not self._twelve_data_api_key:
            return {}

        cache_key = f"twelve_data_{interval_minutes}"
        cached = self._cache.get(cache_key)

        if cached and not cached.is_expired(now):
            return cached.value

        try:
            data = self._fetch_twelve_data(interval_minutes)
            self._cache[cache_key] = CachedValue(data, now, TWELVE_DATA_CACHE_TTL)
            return data
        except Exception as e:
            logger.warning(f"Twelve Data API Fehler: {e}")
            if cached:
                return cached.value
            return {}

    def _fetch_twelve_data(self, interval_minutes: int = 15) -> dict:
        """
        Holt EUR/USD und UUP (DXY-Proxy) von Twelve Data.

        UUP = Invesco DB US Dollar Index Bullish Fund (korreliert eng mit DXY).
        Yield-Daten kommen separat von FRED (Free Tier hat keine Yield-Ticker).
        """
        symbols = {
            "EUR/USD": "eur_usd_td",
            "UUP": "dxy",  # UUP ETF als DXY-Proxy
        }
        td_interval = TWELVE_DATA_INTERVAL_MAP.get(interval_minutes, "15min")

        result = {}
        for symbol, key in symbols.items():
            try:
                resp = requests.get(
                    TWELVE_DATA_URL,
                    params={
                        "symbol": symbol,
                        "interval": td_interval,
                        "outputsize": 2,
                        "apikey": self._twelve_data_api_key,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()

                if "values" in data and len(data["values"]) > 0:
                    current_close = Decimal(data["values"][0]["close"])
                    result[key] = {
                        "current": current_close,
                    }
                    if len(data["values"]) > 1:
                        prev_close = Decimal(data["values"][1]["close"])
                        result[key]["previous"] = prev_close
                elif "code" in data:
                    logger.warning(
                        f"Twelve Data {symbol}: {data.get('message', 'API Error')}"
                    )

            except (requests.RequestException, InvalidOperation, KeyError) as e:
                logger.warning(f"Twelve Data {symbol} Fehler: {e}")

        return result

    # ─── FRED (Federal Reserve Economic Data) ───

    def _get_fred_yields(self, now: datetime) -> dict:
        """Fetcht oder liefert gecachte FRED Yield-Daten."""
        if not self._fred_api_key:
            return {}

        cache_key = "fred_yields"
        cached = self._cache.get(cache_key)

        if cached and not cached.is_expired(now):
            return cached.value

        try:
            data = self._fetch_fred_yields()
            self._cache[cache_key] = CachedValue(data, now, FRED_CACHE_TTL)
            return data
        except Exception as e:
            logger.warning(f"FRED API Fehler: {e}")
            if cached:
                return cached.value
            return {}

    def _fetch_fred_yields(self) -> dict:
        """
        Holt US 2Y und DE 2Y Yields von FRED.

        FRED Series:
        - DGS2: 2-Year Treasury Constant Maturity Rate
        - Fuer DE 2Y gibt es keine direkte FRED-Serie, daher nutzen wir
          DFII5 (5Y TIPS) oder eine manuelle Quelle als Fallback.

        Hinweis: FRED liefert nur Tageswerte (kein Intraday).
        Wir holen die letzten 5 Beobachtungen und nehmen die neueste + vorherige.
        """
        result = {}

        # US 2Y Yield
        series_map = {
            "DGS2": "us02y",  # US 2-Year Treasury
            "DGS10": "us10y",  # US 10-Year (zusaetzlich)
        }

        for series_id, key in series_map.items():
            try:
                resp = requests.get(
                    FRED_URL,
                    params={
                        "series_id": series_id,
                        "api_key": self._fred_api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 5,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()

                observations = [
                    obs
                    for obs in data.get("observations", [])
                    if obs.get("value") != "."
                ]

                if len(observations) >= 1:
                    result[key] = {"current": Decimal(observations[0]["value"])}
                    if len(observations) >= 2:
                        result[key]["previous"] = Decimal(observations[1]["value"])

            except (requests.RequestException, InvalidOperation, KeyError) as e:
                logger.warning(f"FRED {series_id} Fehler: {e}")

        return result

    # ─── ECB (Europaeische Zentralbank) ───

    def _get_ecb_yields(self, now: datetime) -> dict:
        """Fetcht oder liefert gecachte ECB Yield-Daten (DE 2Y Bund)."""
        cache_key = "ecb_yields"
        cached = self._cache.get(cache_key)

        if cached and not cached.is_expired(now):
            return cached.value

        try:
            data = self._fetch_ecb_yields()
            self._cache[cache_key] = CachedValue(data, now, ECB_CACHE_TTL)
            return data
        except Exception as e:
            logger.warning(f"ECB API Fehler: {e}")
            if cached:
                return cached.value
            return {}

    def _fetch_ecb_yields(self) -> dict:
        """
        Holt DE 2Y Government Bond Yield von der ECB.

        ECB Yield Curve Serie:
        YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y = Euro area 2Y government bond yield
        Kein API-Key noetig. Tageswerte.
        """
        result = {}

        try:
            resp = requests.get(
                f"{ECB_URL}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",
                params={
                    "lastNObservations": 3,
                    "format": "jsondata",
                    "detail": "dataonly",
                },
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # Observations extrahieren
            series = data["dataSets"][0]["series"]
            for _key, s in series.items():
                obs = s["observations"]
                # Observations sind nach Index sortiert, hoechster Index = neuester
                sorted_obs = sorted(obs.items(), key=lambda x: int(x[0]), reverse=True)

                if len(sorted_obs) >= 1:
                    result["de02y"] = {"current": Decimal(str(sorted_obs[0][1][0]))}
                    if len(sorted_obs) >= 2:
                        result["de02y"]["previous"] = Decimal(str(sorted_obs[1][1][0]))

        except (requests.RequestException, InvalidOperation, KeyError, IndexError) as e:
            logger.warning(f"ECB DE02Y Fehler: {e}")

        return result

    # ─── Indikator-Zusammenbau ───

    def _build_indicators(
        self, binance: dict, twelve: dict, fred: dict, ecb: dict, now: datetime
    ) -> dict:
        """Baut MacroIndicator-Objekte aus Rohdaten."""
        indicators = {}

        binance_quality = self._get_quality_prefix("binance_prices", now)
        td_quality = self._get_quality_prefix("twelve_data", now)

        # BTC/USD (von Binance BTCUSDT mit Kline-Vergleich)
        btc_usdt_data = binance.get("BTCUSDT", {})
        btc_usdt = (
            btc_usdt_data.get("current") if isinstance(btc_usdt_data, dict) else None
        )
        btc_usdt_prev = (
            btc_usdt_data.get("previous") if isinstance(btc_usdt_data, dict) else None
        )
        indicators["btc_usd"] = self._make_indicator(
            "BTC/USD",
            btc_usdt,
            btc_usdt_prev,
            now,
            "binance",
            binance_quality,
        )

        # EUR/USD: Primaer von Twelve Data, Fallback aus Binance (BTCEUR/BTCUSDT)
        eur_usd_td = twelve.get("eur_usd_td", {})
        btc_eur_data = binance.get("BTCEUR", {})
        btc_eur = (
            btc_eur_data.get("current") if isinstance(btc_eur_data, dict) else None
        )
        btc_eur_prev = (
            btc_eur_data.get("previous") if isinstance(btc_eur_data, dict) else None
        )

        if eur_usd_td.get("current"):
            indicators["eur_usd"] = self._make_indicator(
                "EUR/USD",
                eur_usd_td["current"],
                eur_usd_td.get("previous"),
                now,
                "twelvedata",
                td_quality,
            )
        elif btc_eur and btc_usdt and btc_usdt > 0:
            eur_usd_curr, eur_usd_prev = compute_derived_eur_usd(
                btc_eur, btc_usdt, btc_eur_prev, btc_usdt_prev
            )
            indicators["eur_usd"] = self._make_indicator(
                "EUR/USD",
                eur_usd_curr,
                eur_usd_prev,
                now,
                "binance",
                binance_quality,
            )
        else:
            indicators["eur_usd"] = self._make_indicator(
                "EUR/USD",
                None,
                None,
                now,
                "unavailable",
                "unavailable",
            )

        # DXY (via UUP ETF als Proxy)
        dxy_data = twelve.get("dxy", {})
        indicators["dxy"] = self._make_indicator(
            "DXY (UUP)",
            dxy_data.get("current"),
            dxy_data.get("previous"),
            now,
            "twelvedata",
            td_quality if dxy_data.get("current") else "unavailable",
        )

        # US 2Y Yield (von FRED, Tageswerte)
        fred_quality = self._get_quality("fred_yields", now)
        us02y_data = fred.get("us02y", {})
        indicators["us02y"] = self._make_indicator(
            "US 2Y Yield",
            us02y_data.get("current"),
            us02y_data.get("previous"),
            now,
            "fred",
            fred_quality if us02y_data.get("current") else "unavailable",
        )

        # DE 2Y Yield (von ECB, Tageswerte, kein API Key noetig)
        ecb_quality = self._get_quality("ecb_yields", now)
        de02y_data = ecb.get("de02y", {})
        indicators["de02y"] = self._make_indicator(
            "DE 2Y Yield",
            de02y_data.get("current"),
            de02y_data.get("previous"),
            now,
            "ecb",
            ecb_quality if de02y_data.get("current") else "unavailable",
        )

        # Spread (berechnet aus FRED US02Y + ECB DE02Y)
        us02y_curr = us02y_data.get("current")
        de02y_curr = de02y_data.get("current")
        us02y_prev = us02y_data.get("previous")
        de02y_prev = de02y_data.get("previous")

        spread_curr = compute_yield_spread(us02y_curr, de02y_curr)
        spread_prev = compute_yield_spread(us02y_prev, de02y_prev)

        spread_quality = (
            "live"
            if (us02y_curr is not None and de02y_curr is not None)
            else "unavailable"
        )
        indicators["spread"] = self._make_indicator(
            "Spread US02Y-DE02Y",
            spread_curr,
            spread_prev,
            now,
            "calculated",
            spread_quality,
        )

        # BTC/EUR (nur zur Anzeige)
        indicators["btc_eur"] = self._make_indicator(
            "BTC/EUR",
            btc_eur,
            btc_eur_prev,
            now,
            "binance",
            binance_quality if btc_eur else "unavailable",
        )

        return indicators

    @staticmethod
    def _make_indicator(name, current, previous, now, source, quality):
        """Erstellt einen MacroIndicator mit berechneter change_pct."""
        return MacroIndicator(
            name=name,
            current=current,
            previous_15m=previous,
            change_pct=compute_change_pct(current, previous),
            timestamp=now if current is not None else None,
            source=source,
            quality=quality,
        )

    def _fill_previous_values(
        self, indicators: dict, now: datetime, lookback_minutes: int = 15
    ):
        """Fuellt previous_15m aus History als Fallback (nur wenn API keinen Wert lieferte)."""
        target_time = now - timedelta(minutes=lookback_minutes)

        # Finde den Eintrag der am naechsten am Lookback-Zeitpunkt liegt
        best_entry = None
        best_diff = None
        for ts, snapshot in self._history:
            diff = abs((ts - target_time).total_seconds())
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_entry = snapshot

        if not best_entry:
            return

        # Toleranz: max 1/3 des Intervalls oder mindestens 30 Sekunden
        max_tolerance = max(lookback_minutes * 20, 30)  # Sekunden
        if best_diff and best_diff > max_tolerance:
            return

        for key, indicator in indicators.items():
            # Nur als Fallback: nicht ueberschreiben wenn API schon previous lieferte
            if indicator.previous_15m is not None:
                continue
            if key in best_entry and indicator.current is not None:
                prev = best_entry[key]
                if prev is not None and prev != 0:
                    indicator.previous_15m = prev
                    indicator.change_pct = compute_change_pct(indicator.current, prev)

    def _get_quality(self, cache_key: str, now: datetime) -> str:
        """Bestimmt Datenqualitaet basierend auf Cache-Alter."""
        cached = self._cache.get(cache_key)
        if not cached:
            return "unavailable"
        if cached.is_stale(now):
            return "stale"
        if cached.is_expired(now):
            return "cached"
        return "live"

    def _get_quality_prefix(self, prefix: str, now: datetime) -> str:
        """Bestimmt Datenqualitaet fuer Intervall-spezifische Cache-Keys (bester Match)."""
        best_quality = "unavailable"
        for key, cached in self._cache.items():
            if key.startswith(prefix):
                if cached.is_stale(now):
                    q = "stale"
                elif cached.is_expired(now):
                    q = "cached"
                else:
                    return "live"
                if best_quality == "unavailable":
                    best_quality = q
        return best_quality


# ─── Singleton ───

_service_instance: Optional[MacroDataService] = None
_service_lock = threading.Lock()


def get_macro_data_service() -> MacroDataService:
    """Liefert die Singleton-Instanz des MacroDataService."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = MacroDataService()
    return _service_instance
