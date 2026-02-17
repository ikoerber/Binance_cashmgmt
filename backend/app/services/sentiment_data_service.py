"""
Sentiment-Daten-Service - Fetcht, cached und berechnet Live Sentiment Score (v3).

Datenquellen:
- Alternative.me: Fear & Greed Index (kein API Key)
- Binance REST API: Klines (OHLCV + Taker Volume) fuer DMA, Volume, Taker Ratio
- OKX REST API: Funding Rate (kein API Key, EU-zugaenglich)

Haelt Rolling-Historien fuer Percentile-Scoring (90 Tage).
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

import requests

from app.domain.sentiment import (
    SentimentResultV3,
    compute_sentiment_v3,
)
from app.services.binance_public_client import CachedValue, get_binance_public_client

logger = logging.getLogger(__name__)

# ─── Konfiguration ───

FNG_URL = "https://api.alternative.me/fng/"
OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
# OKX bietet nur USD-denominierte Perpetuals. Funding Rate ist ein prozentualer
# Indikator und damit waehrungsneutral (identisch fuer EUR- und USD-Paare).
OKX_FUNDING_INST_ID = "BTC-USDT-SWAP"

# Cache-TTLs
FNG_CACHE_TTL = timedelta(minutes=30)  # F&G aendert sich nur taeglich
KLINE_CACHE_TTL = timedelta(minutes=5)  # Klines fuer DMA/Volume
FUNDING_CACHE_TTL = timedelta(
    minutes=15
)  # OKX Funding Rate (alle 8h, aber wir pollen oefter)

# Percentile-Fenster
PERCENTILE_WINDOW = 90  # Tage

# Request-Timeout
REQUEST_TIMEOUT = 10  # Sekunden


class SentimentDataService:
    """
    Singleton-Service fuer Sentiment-Daten.

    Thread-safe via Lock. Haelt In-Memory Cache und Rolling-Historien
    fuer Percentile-basiertes Scoring (v3).
    """

    def __init__(self):
        self._cache: dict[str, CachedValue] = {}
        self._lock = threading.Lock()

        # Rolling-Historien fuer Percentile (90 Tage, 1 Eintrag/Tag)
        self._hist_fng: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)
        self._hist_taker: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)
        self._hist_dma: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)
        self._hist_vol: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)

        # Daily-Returns fuer Volatility-Scaling (120 Tage)
        self._daily_returns: deque[Decimal] = deque(maxlen=120)

        # Letzter Tag an dem Historien aktualisiert wurden
        self._last_history_date: Optional[str] = None

        # Flag: Historien initial befuellt
        self._history_initialized = False

    def initialize(self, symbol: str = "BTCEUR") -> None:
        """Initialisiert Percentile-Historien (aufzurufen beim App-Start via Lifespan)."""
        with self._lock:
            if not self._history_initialized:
                self._initialize_history(symbol)
                self._history_initialized = True

    def get_sentiment(self, symbol: str = "BTCEUR") -> dict:
        """
        Berechnet aktuellen Sentiment Score (v3).

        Returns:
            Dict mit Score, Label, Multiplier, Pillar-Details, Dispersion, Vol-Regime.
        """
        now = datetime.now(timezone.utc)

        with self._lock:
            # 1. Historien initialisieren (Fallback falls nicht via Lifespan geschehen)
            if not self._history_initialized:
                self._initialize_history(symbol)
                self._history_initialized = True

            # 2. Daten holen/refreshen (Cache-Zugriff unter Lock)
            fng_value, fng_quality = self._get_fng(now)
            kline_data, kline_quality = self._get_klines(now, symbol)
            funding_rate, funding_quality = self._get_funding_rate(now)

            # 3. Snapshot Historien unter Lock (thread-safe)
            hist_fng = list(self._hist_fng)
            hist_taker = list(self._hist_taker)
            hist_dma = list(self._hist_dma)
            hist_vol = list(self._hist_vol)
            daily_returns = (
                list(self._daily_returns) if len(self._daily_returns) >= 120 else None
            )

        # 4. Rohwerte berechnen (ausserhalb Lock - kein Shared-State-Zugriff)
        taker_ratio_7d = kline_data.get("taker_ratio_7d")
        dist_50dma_pct = kline_data.get("dist_50dma_pct")
        vol_ratio = kline_data.get("vol_ratio")
        price_change_pct = kline_data.get("price_change_pct")
        sma50 = kline_data.get("sma50")
        sma200 = kline_data.get("sma200")
        current_price = kline_data.get("current_price")

        # 5. Sentiment berechnen (pure Funktion)
        result = compute_sentiment_v3(
            fng_value=fng_value,
            taker_ratio_7d=taker_ratio_7d,
            dist_50dma_pct=dist_50dma_pct,
            vol_ratio=vol_ratio,
            price_change_pct=price_change_pct,
            history_fng=hist_fng,
            history_taker=hist_taker,
            history_dma=hist_dma,
            history_vol=hist_vol,
            sma50=sma50,
            sma200=sma200,
            daily_returns=daily_returns,
            funding_rate=funding_rate,
        )

        # 6. Quality Badges basierend auf Cache-Status setzen
        quality_map = {
            "alternative.me": fng_quality,
            "okx": funding_quality,
            "binance": kline_quality,
        }
        for pillar in result.pillars:
            if pillar.quality != "unavailable":
                source_quality = quality_map.get(pillar.source)
                if source_quality:
                    pillar.quality = source_quality

        # 7. Historien taeglich aktualisieren (unter Lock)
        today = now.strftime("%Y-%m-%d")
        with self._lock:
            if today != self._last_history_date:
                self._update_daily_history(
                    fng_value, taker_ratio_7d, dist_50dma_pct, vol_ratio, kline_data
                )
                self._last_history_date = today

        return self._serialize_result(result, current_price, fng_value, funding_rate)

    # ─── Fear & Greed Index ───

    def _get_fng(self, now: datetime) -> tuple[Optional[Decimal], str]:
        cached = self._cache.get("fng")
        if cached and not cached.is_expired(now):
            return cached.value, "live"

        try:
            resp = requests.get(FNG_URL, params={"limit": 1}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                value = Decimal(data[0]["value"])
                self._cache["fng"] = CachedValue(value, now, FNG_CACHE_TTL)
                return value, "live"
        except Exception as e:
            logger.warning("Fear & Greed API Fehler: %s", e)

        if cached:
            if cached.is_stale(now):
                return cached.value, "stale"
            return cached.value, "cached"
        return None, "unavailable"

    # ─── Binance Klines (50+200 DMA, Volume, Taker Ratio) ───

    def _get_klines(self, now: datetime, symbol: str) -> tuple[dict, str]:
        cached = self._cache.get("klines")
        if cached and not cached.is_expired(now):
            return cached.value, "live"

        try:
            data = self._fetch_and_compute_klines(symbol)
            self._cache["klines"] = CachedValue(data, now, KLINE_CACHE_TTL)
            return data, "live"
        except Exception as e:
            logger.warning("Binance Klines Fehler: %s", e)
            if cached:
                if cached.is_stale(now):
                    return cached.value, "stale"
                return cached.value, "cached"
            return {}, "unavailable"

    def _fetch_and_compute_klines(self, symbol: str) -> dict:
        """Holt 200 Tages-Klines und berechnet alle technischen Indikatoren."""
        client = get_binance_public_client()
        klines = client.get_klines(symbol, "1d", limit=201)

        if len(klines) < 50:
            return {}

        closes = [Decimal(str(k[4])) for k in klines]
        volumes = [Decimal(str(k[5])) for k in klines]
        taker_buy_vols = [Decimal(str(k[9])) for k in klines]

        current_price = closes[-1]

        # SMAs
        sma50 = sum(closes[-50:]) / Decimal("50")
        sma200 = sum(closes[-200:]) / Decimal("200") if len(closes) >= 200 else None

        # Distance to 50-DMA
        dist_50dma_pct = (
            ((current_price - sma50) / sma50) * Decimal("100") if sma50 > 0 else None
        )

        # Volume Ratio (heute vs 20-Tage-Durchschnitt)
        vol_ratio = None
        if len(volumes) >= 21:
            vol_20d = sum(volumes[-21:-1]) / Decimal("20")
            if vol_20d > 0:
                vol_ratio = volumes[-1] / vol_20d

        # Price Change (heute vs gestern)
        price_change_pct = None
        if len(closes) >= 2 and closes[-2] > 0:
            price_change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * Decimal("100")

        # Taker Ratio (7d Durchschnitt)
        taker_ratios = []
        for i in range(max(0, len(klines) - 7), len(klines)):
            sell_vol = volumes[i] - taker_buy_vols[i]
            if sell_vol > 0:
                taker_ratios.append(taker_buy_vols[i] / sell_vol)
        taker_ratio_7d = (
            sum(taker_ratios) / Decimal(str(len(taker_ratios)))
            if len(taker_ratios) >= 3
            else None
        )

        # Aktuellen Ticker-Preis holen (genauer als Kline-Close)
        try:
            current_price = client.get_ticker_price(symbol)
        except Exception:
            logger.debug("Ticker-Fallback auf Kline-Close fuer %s", symbol)

        return {
            "current_price": current_price,
            "sma50": sma50,
            "sma200": sma200,
            "dist_50dma_pct": dist_50dma_pct,
            "vol_ratio": vol_ratio,
            "price_change_pct": price_change_pct,
            "taker_ratio_7d": taker_ratio_7d,
            "closes": closes,
        }

    # ─── OKX Funding Rate ───

    def _get_funding_rate(self, now: datetime) -> tuple[Optional[Decimal], str]:
        cached = self._cache.get("funding")
        if cached and not cached.is_expired(now):
            return cached.value, "live"

        try:
            resp = requests.get(
                OKX_FUNDING_URL,
                params={"instId": OKX_FUNDING_INST_ID},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                rate = Decimal(data[0].get("fundingRate", "0"))
                self._cache["funding"] = CachedValue(rate, now, FUNDING_CACHE_TTL)
                return rate, "live"
        except Exception as e:
            logger.warning("OKX Funding Rate Fehler: %s", e)

        if cached:
            if cached.is_stale(now):
                return cached.value, "stale"
            return cached.value, "cached"
        return None, "unavailable"

    # ─── Historien-Initialisierung (einmalig) ───

    def _initialize_history(self, symbol: str) -> None:
        """Befuellt Percentile-Historien mit 90 Tagen echter Daten."""
        logger.info("Sentiment: Initialisiere Percentile-Historien (90 Tage)...")

        try:
            # F&G Historisch
            resp = requests.get(
                FNG_URL, params={"limit": PERCENTILE_WINDOW}, timeout=30
            )
            resp.raise_for_status()
            fng_data = resp.json().get("data", [])
            for entry in reversed(fng_data):
                self._hist_fng.append(Decimal(entry["value"]))
            logger.info("  F&G Historie: %d Tage", len(self._hist_fng))
        except Exception as e:
            logger.warning("  F&G Historie Fehler: %s", e)

        try:
            # Klines (200+90 Tage fuer Warmup + Percentile)
            client = get_binance_public_client()
            klines = client.get_klines(symbol, "1d", limit=300)

            closes = [Decimal(str(k[4])) for k in klines]
            volumes = [Decimal(str(k[5])) for k in klines]
            taker_buy_vols = [Decimal(str(k[9])) for k in klines]

            # Ab Tag 200 (nach Warmup) die letzten 90 Tage in Historien fuellen
            start = max(200, len(closes) - PERCENTILE_WINDOW)
            for i in range(start, len(closes)):
                # DMA Distance
                if i >= 50:
                    sma50 = sum(closes[i - 49 : i + 1]) / Decimal("50")
                    if sma50 > 0:
                        self._hist_dma.append(
                            ((closes[i] - sma50) / sma50) * Decimal("100")
                        )

                # Volume Ratio
                if i >= 21:
                    vol_20d = sum(volumes[i - 20 : i]) / Decimal("20")
                    if vol_20d > 0:
                        self._hist_vol.append(volumes[i] / vol_20d)

                # Taker Ratio
                taker_ratios = []
                for j in range(max(0, i - 6), i + 1):
                    sell = volumes[j] - taker_buy_vols[j]
                    if sell > 0:
                        taker_ratios.append(taker_buy_vols[j] / sell)
                if len(taker_ratios) >= 3:
                    avg = sum(taker_ratios) / Decimal(str(len(taker_ratios)))
                    self._hist_taker.append(avg)

                # Daily Returns
                if i >= 1 and closes[i - 1] > 0:
                    self._daily_returns.append(
                        (closes[i] - closes[i - 1]) / closes[i - 1]
                    )

            logger.info(
                "  Kline Historie: DMA=%d, Vol=%d, Taker=%d, Returns=%d",
                len(self._hist_dma),
                len(self._hist_vol),
                len(self._hist_taker),
                len(self._daily_returns),
            )
        except Exception as e:
            logger.warning("  Kline Historie Fehler: %s", e)

    def _update_daily_history(
        self,
        fng_value: Optional[Decimal],
        taker_ratio_7d: Optional[Decimal],
        dist_50dma_pct: Optional[Decimal],
        vol_ratio: Optional[Decimal],
        kline_data: dict,
    ) -> None:
        """Fuegt aktuelle Tageswerte zur Percentile-Historie hinzu."""
        if fng_value is not None:
            self._hist_fng.append(fng_value)
        if taker_ratio_7d is not None:
            self._hist_taker.append(taker_ratio_7d)
        if dist_50dma_pct is not None:
            self._hist_dma.append(dist_50dma_pct)
        if vol_ratio is not None:
            self._hist_vol.append(vol_ratio)

        # Daily Return
        closes = kline_data.get("closes", [])
        if len(closes) >= 2 and closes[-2] > 0:
            self._daily_returns.append((closes[-1] - closes[-2]) / closes[-2])

    # ─── Serialisierung ───

    @staticmethod
    def _serialize_result(
        result: SentimentResultV3,
        current_price: Optional[Decimal],
        fng_value: Optional[Decimal],
        funding_rate: Optional[Decimal],
    ) -> dict:
        """Serialisiert SentimentResultV3 fuer JSON-Response."""
        rec = result.recommendation
        disp = rec.dispersion
        vol = rec.volatility

        return {
            "composite_score": float(result.composite_score),
            "composite_label": result.composite_label.value,
            "composite_color": result.composite_color,
            "active_pillars": result.active_pillars,
            "total_pillars": result.total_pillars,
            "recommendation": {
                "action": rec.action,
                "buy_size_multiplier": float(rec.buy_size_multiplier),
                "raw_multiplier": float(rec.raw_multiplier),
            },
            "dispersion": {
                "pillar_std": float(disp.pillar_std),
                "confidence_factor": float(disp.confidence_factor),
                "high_dispersion": disp.high_dispersion,
            },
            "volatility": (
                {
                    "realized_vol_20d": float(vol.realized_vol_20d),
                    "avg_vol_120d": float(vol.avg_vol_120d),
                    "vol_ratio": float(vol.vol_ratio),
                    "regime": vol.regime,
                    "scaling_factor": float(vol.scaling_factor),
                }
                if vol
                else None
            ),
            "pillars": [
                {
                    "name": p.name,
                    "score": float(p.score),
                    "raw_value": (
                        float(p.raw_value) if p.raw_value is not None else None
                    ),
                    "source": p.source,
                    "quality": p.quality,
                }
                for p in result.pillars
            ],
            "market_data": {
                "btc_price": float(current_price) if current_price else None,
                "fng_raw": int(fng_value) if fng_value is not None else None,
                "funding_rate": (
                    float(funding_rate) if funding_rate is not None else None
                ),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ─── Singleton ───

_service_instance: Optional[SentimentDataService] = None
_service_lock = threading.Lock()


def get_sentiment_data_service() -> SentimentDataService:
    """Liefert die Singleton-Instanz des SentimentDataService."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = SentimentDataService()
    return _service_instance


def reset_sentiment_data_service() -> None:
    """Setzt die Singleton-Instanz zurueck (fuer Tests)."""
    global _service_instance
    with _service_lock:
        _service_instance = None
