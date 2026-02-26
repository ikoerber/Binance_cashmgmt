"""
Alpha Score Data Service - Fetcht, cached und berechnet den Alpha Score.

Singleton-Service mit gemischten Refresh-Kadenzen:
- Candle-getriebene Faktoren (Z-Score, Lead-Lag, Hurst): TTL = Intervall-Dauer
- Echtzeit-Faktoren (Orderbook, Funding): kuerzere TTL (30s bzw. 15min)

Datenquellen:
- Binance REST API: Klines (XRPBTC, BTCEUR), Orderbook Depth (XRPBTC)
- OKX REST API: Funding Rate (XRP-USDT-SWAP, BTC-USDT-SWAP)
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

import requests

from app.domain.alpha_score import (
    AlphaFactorScore,
    AlphaScoreResult,
    HurstResult,
    RegimeInfo,
    TrailingStopState,
    compute_alpha_score,
    compute_atr_standalone,
    compute_funding_rate_score,
    compute_hurst_rs,
    compute_leadlag_momentum,
    compute_orderbook_imbalance,
    compute_regime_adjusted_weights,
    compute_zscore_mean_reversion,
    update_trailing_stop,
    _decimal_pearson_correlation,
)
from app.services.binance_public_client import CachedValue, get_binance_public_client

logger = logging.getLogger(__name__)

# --- Konfiguration ---

OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
REQUEST_TIMEOUT = 10  # Sekunden

# TTLs
DEPTH_CACHE_TTL = timedelta(seconds=30)
FUNDING_CACHE_TTL = timedelta(minutes=15)

# Interval-Dauer-Mapping fuer Kline TTL
INTERVAL_DURATION: Dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
}

# Orderbook EMA
EMA_ALPHA = Decimal("0.4")
EMA_HISTORY_SIZE = 5

# Warmup
MIN_CANDLES_BUFFER = 10  # Extra Kerzen ueber Window-Groesse hinaus


def _parse_interval_minutes(interval: str) -> int:
    """Konvertiert Intervall-String in Minuten."""
    mapping = {"5m": 5, "15m": 15, "1h": 60}
    return mapping.get(interval, 15)


class AlphaScoreDataService:
    """
    Singleton-Service fuer Alpha Score Daten.

    Thread-safe via Lock. Haelt In-Memory Cache fuer Klines, Orderbook,
    Funding Rate und Trailing Stop State.
    """

    def __init__(self):
        self._lock = threading.Lock()

        # Caches
        self._kline_cache: Dict[str, CachedValue] = {}  # "{symbol}_{interval}"
        self._depth_cache: Dict[str, CachedValue] = {}   # symbol
        self._funding_cache: Dict[str, CachedValue] = {}  # inst_id

        # Orderbook EMA history (last N imbalance ratios per symbol)
        self._depth_history: Dict[str, deque] = {}

        # Trailing stop state per symbol
        self._trailing_stops: Dict[str, TrailingStopState] = {}

        # Warmup tracking
        self._warmup_checked: Dict[str, bool] = {}

    # --- Main Method: get_alpha_score ---

    def get_alpha_score(self, user_id: str, settings: dict) -> dict:
        """
        Berechnet den Alpha Score mit allen 4 Faktoren.

        Args:
            user_id: User ID
            settings: User-Settings Dict (von Settings API)

        Returns:
            Serialisiertes Dict mit Score, Faktoren, Regime, Trailing Stops
        """
        now = datetime.now(timezone.utc)

        # 1. Parse settings
        interval = settings.get("alpha_score_interval", "15m")
        threshold = Decimal(str(settings.get("alpha_score_threshold", "3.0")))
        zscore_window = int(settings.get("alpha_score_zscore_window", 60))
        leadlag_window = int(settings.get("alpha_score_leadlag_window", 30))
        hurst_lookback = int(settings.get("alpha_score_hurst_lookback", 100))
        hurst_trending = Decimal(str(settings.get("alpha_score_hurst_trending", "0.55")))
        hurst_reverting = Decimal(str(settings.get("alpha_score_hurst_reverting", "0.45")))
        atr_mult_btc = Decimal(str(settings.get("alpha_score_atr_mult_btc", "2.0")))
        atr_mult_xrp = Decimal(str(settings.get("alpha_score_atr_mult_xrp", "3.0")))
        resume_n = int(settings.get("alpha_score_stop_resume_n", 5))

        # Parse base weights (from settings, already normalized to 100%)
        w_zscore = Decimal(str(settings.get("alpha_score_weight_zscore", "40")))
        w_leadlag = Decimal(str(settings.get("alpha_score_weight_leadlag", "30")))
        w_imbalance = Decimal(str(settings.get("alpha_score_weight_imbalance", "20")))
        w_funding = Decimal(str(settings.get("alpha_score_weight_funding", "10")))

        # Normalize to sum = 1.0
        w_sum = w_zscore + w_leadlag + w_imbalance + w_funding
        if w_sum > 0:
            base_weights = {
                "zscore": (w_zscore / w_sum).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                "leadlag": (w_leadlag / w_sum).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                "imbalance": (w_imbalance / w_sum).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                "funding": (w_funding / w_sum).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            }
        else:
            base_weights = {
                "zscore": Decimal("0.40"),
                "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"),
                "funding": Decimal("0.10"),
            }

        # Ensure exact sum = 1.0
        total = sum(base_weights.values())
        diff = Decimal("1.0") - total
        if diff != 0:
            largest_key = max(base_weights, key=lambda k: base_weights[k])
            base_weights[largest_key] += diff

        # Minimum window for warmup check
        min_window_size = max(zscore_window, hurst_lookback)

        # 2. Fetch candle-driven data
        xrpbtc_klines = None
        xrpbtc_quality = "unavailable"
        btceur_klines = None
        btceur_quality = "unavailable"

        # Fetch XRPBTC klines (for Z-Score + Hurst)
        needed_candles = min_window_size + MIN_CANDLES_BUFFER
        try:
            xrpbtc_klines, xrpbtc_quality = self._get_klines(
                now, "XRPBTC", interval, limit=needed_candles
            )
        except Exception as e:
            logger.warning("XRPBTC Klines Fehler: %s", e)

        # Fetch BTCEUR klines (for Lead-Lag)
        try:
            btceur_klines, btceur_quality = self._get_klines(
                now, "BTCEUR", interval, limit=needed_candles
            )
        except Exception as e:
            logger.warning("BTCEUR Klines Fehler: %s", e)

        # 3. Warmup check (SCORE-08)
        xrpbtc_candle_count = len(xrpbtc_klines) if xrpbtc_klines else 0
        if xrpbtc_candle_count < min_window_size:
            return {
                "status": "warmup",
                "candles_available": xrpbtc_candle_count,
                "candles_needed": min_window_size,
                "message": (
                    f"Insufficient data for Alpha Score computation. "
                    f"Need {min_window_size} candles, have {xrpbtc_candle_count}."
                ),
            }

        # Extract close prices
        xrpbtc_closes = [Decimal(str(k[4])) for k in xrpbtc_klines]
        btceur_closes = [Decimal(str(k[4])) for k in btceur_klines] if btceur_klines else []

        # 4. Compute Z-Score
        zscore_quality = "unavailable"
        zscore_result = None
        try:
            zscore_result = compute_zscore_mean_reversion(
                prices=xrpbtc_closes, window=zscore_window
            )
            zscore_quality = zscore_result.quality
        except Exception as e:
            logger.warning("Z-Score Berechnung Fehler: %s", e)

        # 5. Compute Lead-Lag
        leadlag_quality = "unavailable"
        leadlag_result = None
        try:
            if btceur_closes and xrpbtc_closes:
                # Compute returns
                btc_returns = [
                    (btceur_closes[i] - btceur_closes[i - 1]) / btceur_closes[i - 1]
                    if btceur_closes[i - 1] != 0 else Decimal("0")
                    for i in range(1, len(btceur_closes))
                ]
                xrp_returns = [
                    (xrpbtc_closes[i] - xrpbtc_closes[i - 1]) / xrpbtc_closes[i - 1]
                    if xrpbtc_closes[i - 1] != 0 else Decimal("0")
                    for i in range(1, len(xrpbtc_closes))
                ]
                leadlag_result = compute_leadlag_momentum(
                    btc_returns=btc_returns,
                    xrp_returns=xrp_returns,
                    window=leadlag_window,
                )
                leadlag_quality = leadlag_result.quality
        except Exception as e:
            logger.warning("Lead-Lag Berechnung Fehler: %s", e)

        # 6. Compute Hurst
        hurst_result = None
        try:
            hurst_result = compute_hurst_rs(
                prices=xrpbtc_closes,
                min_window=10,
                trending_threshold=hurst_trending,
                reverting_threshold=hurst_reverting,
            )
        except Exception as e:
            logger.warning("Hurst R/S Fehler: %s", e)

        if hurst_result is None:
            hurst_result = HurstResult(
                hurst=Decimal("0.5"),
                regime="transitional",
                confidence=Decimal("0"),
                data_points=0,
            )

        # 7. Fetch real-time data: Orderbook
        orderbook_quality = "unavailable"
        orderbook_result = None
        try:
            orderbook_result, orderbook_quality = self._get_orderbook_with_ema(
                now, "XRPBTC"
            )
        except Exception as e:
            logger.warning("Orderbook Imbalance Fehler: %s", e)

        # 8. Fetch real-time data: Funding
        funding_quality = "unavailable"
        funding_result = None
        try:
            xrp_funding, xrp_funding_quality = self._get_funding_rate(
                now, "XRP-USDT-SWAP"
            )
            btc_funding, _ = self._get_funding_rate(now, "BTC-USDT-SWAP")
            funding_result = compute_funding_rate_score(
                funding_rate=xrp_funding,
                btc_funding=btc_funding,
            )
            funding_quality = xrp_funding_quality if xrp_funding is not None else "unavailable"
        except Exception as e:
            logger.warning("Funding Rate Fehler: %s", e)

        # 9. Regime-adjusted weights
        adjusted_weights = compute_regime_adjusted_weights(
            base_weights=base_weights,
            hurst=hurst_result.hurst,
            trending_threshold=hurst_trending,
            reverting_threshold=hurst_reverting,
        )

        # Build regime info
        zscore_weight_pct = (adjusted_weights.get("zscore", Decimal("0")) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        regime_info = RegimeInfo(
            hurst=hurst_result.hurst,
            regime=hurst_result.regime,
            confidence=hurst_result.confidence,
            zscore_weight_pct=zscore_weight_pct,
        )

        # 10. Build factor scores
        factors: List[AlphaFactorScore] = []

        # Z-Score
        factors.append(AlphaFactorScore(
            name="zscore",
            sub_score=zscore_result.sub_score if zscore_result else Decimal("0"),
            raw_value=zscore_result.zscore if zscore_result else None,
            weight=adjusted_weights.get("zscore", Decimal("0")),
            base_weight=base_weights.get("zscore", Decimal("0")),
            quality=zscore_quality,
            description="Z-Score Mean Reversion on XRP/BTC ratio",
        ))

        # Lead-Lag
        factors.append(AlphaFactorScore(
            name="leadlag",
            sub_score=leadlag_result.sub_score if leadlag_result else Decimal("0"),
            raw_value=leadlag_result.best_correlation if leadlag_result else None,
            weight=adjusted_weights.get("leadlag", Decimal("0")),
            base_weight=base_weights.get("leadlag", Decimal("0")),
            quality=leadlag_quality,
            description="Lead-Lag Momentum (BTC leads XRP)",
        ))

        # Orderbook Imbalance
        factors.append(AlphaFactorScore(
            name="imbalance",
            sub_score=orderbook_result.sub_score if orderbook_result else Decimal("0"),
            raw_value=orderbook_result.imbalance_ratio if orderbook_result else None,
            weight=adjusted_weights.get("imbalance", Decimal("0")),
            base_weight=base_weights.get("imbalance", Decimal("0")),
            quality=orderbook_quality,
            description="Orderbook Imbalance (bid/ask volume)",
        ))

        # Funding Rate
        factors.append(AlphaFactorScore(
            name="funding",
            sub_score=funding_result.sub_score if funding_result else Decimal("0"),
            raw_value=funding_result.raw_rate if funding_result else None,
            weight=adjusted_weights.get("funding", Decimal("0")),
            base_weight=base_weights.get("funding", Decimal("0")),
            quality=funding_quality,
            description="Funding Rate Score (OKX, contrarian)",
        ))

        # 11. Compute composite Alpha Score
        alpha_result = compute_alpha_score(
            factors=factors,
            regime=regime_info,
            threshold=threshold,
            timestamp=now,
        )

        # 12. Update trailing stops
        self._update_trailing_stops_from_klines(
            now=now,
            interval=interval,
            xrpbtc_klines=xrpbtc_klines,
            btceur_klines=btceur_klines,
            xrpbtc_closes=xrpbtc_closes,
            btceur_closes=btceur_closes,
            atr_mult_btc=atr_mult_btc,
            atr_mult_xrp=atr_mult_xrp,
            resume_n=resume_n,
            leadlag_window=leadlag_window,
        )

        # 13. Serialize response
        return self._serialize_alpha_score(alpha_result)

    # --- Second Method: get_trailing_stops ---

    def get_trailing_stops(self, user_id: str, settings: dict) -> dict:
        """
        Gibt den aktuellen Trailing-Stop-Status zurueck.

        Args:
            user_id: User ID
            settings: User-Settings Dict

        Returns:
            Dict mit Trailing Stop Levels pro Symbol
        """
        with self._lock:
            stops_copy = dict(self._trailing_stops)

        if not stops_copy:
            return {"stops": {}}

        result: Dict[str, dict] = {}
        for symbol, state in stops_copy.items():
            result[symbol] = {
                "stop_level": str(state.stop_level) if state.stop_level is not None else None,
                "atr_value": str(state.atr_value) if state.atr_value is not None else None,
                "atr_distance": str(state.atr_distance) if state.atr_distance is not None else None,
                "direction": state.direction,
                "frozen": state.frozen,
                "frozen_since": state.frozen_since.isoformat() if state.frozen_since else None,
                "data_points_needed": max(0, state.resume_threshold - state.fresh_data_count),
                "last_price": str(state.last_price) if state.last_price is not None else None,
                "last_updated": state.last_updated.isoformat() if state.last_updated else None,
            }

        return {"stops": result}

    # --- Klines fetch with TTL ---

    def _get_klines(
        self, now: datetime, symbol: str, interval: str, limit: int = 200
    ) -> tuple:
        """
        Holt Klines mit Intervall-basiertem TTL.

        Returns:
            (klines_list, quality_string)
        """
        cache_key = f"{symbol}_{interval}"
        ttl = INTERVAL_DURATION.get(interval, timedelta(minutes=15))

        with self._lock:
            cached = self._kline_cache.get(cache_key)
            if cached and not cached.is_expired(now):
                return cached.value, "live"

        try:
            client = get_binance_public_client()
            klines = client.get_klines(symbol, interval, limit=limit)

            with self._lock:
                self._kline_cache[cache_key] = CachedValue(klines, now, ttl)

            return klines, "live"
        except Exception as e:
            logger.warning("Klines Fetch Fehler (%s, %s): %s", symbol, interval, e)

            with self._lock:
                cached = self._kline_cache.get(cache_key)
                if cached:
                    if cached.is_stale(now):
                        return cached.value, "stale"
                    return cached.value, "cached"

            return [], "unavailable"

    # --- Orderbook with EMA smoothing ---

    def _get_orderbook_with_ema(self, now: datetime, symbol: str) -> tuple:
        """
        Holt Orderbook und berechnet EMA-geglaettete Imbalance.

        Returns:
            (OrderbookImbalanceResult, quality_string)
        """
        # Check cache first
        with self._lock:
            cached = self._depth_cache.get(symbol)
            if cached and not cached.is_expired(now):
                return cached.value, "live"

        try:
            client = get_binance_public_client()
            depth = client.get_order_book(symbol, limit=100)

            if not depth or "bids" not in depth or "asks" not in depth:
                return None, "unavailable"

            bids_raw = depth.get("bids", [])
            asks_raw = depth.get("asks", [])

            if not bids_raw or not asks_raw:
                return None, "unavailable"

            # Parse bids/asks
            bids = [(Decimal(p), Decimal(q)) for p, q in bids_raw]
            asks = [(Decimal(p), Decimal(q)) for p, q in asks_raw]

            mid_price = (bids[0][0] + asks[0][0]) / Decimal("2")

            # Compute raw imbalance ratio (1% band)
            band_pct = Decimal("0.01")
            band_low = mid_price * (Decimal("1") - band_pct)
            band_high = mid_price * (Decimal("1") + band_pct)

            bid_vol = sum(q for p, q in bids if band_low <= p <= band_high)
            ask_vol = sum(q for p, q in asks if band_low <= p <= band_high)
            total_vol = bid_vol + ask_vol

            if total_vol == 0:
                raw_ratio = Decimal("0")
            else:
                raw_ratio = (bid_vol - ask_vol) / total_vol

            # EMA smoothing
            with self._lock:
                if symbol not in self._depth_history:
                    self._depth_history[symbol] = deque(maxlen=EMA_HISTORY_SIZE)

                self._depth_history[symbol].append(raw_ratio)
                history = list(self._depth_history[symbol])

            # Compute EMA from history
            if len(history) == 1:
                ema_ratio = history[0]
            else:
                ema_ratio = history[0]
                for val in history[1:]:
                    ema_ratio = EMA_ALPHA * val + (Decimal("1") - EMA_ALPHA) * ema_ratio

            # Use domain function with synthetic bid/ask that produce the EMA ratio
            # Instead: compute sub_score directly from EMA ratio
            # imbalance_ratio linearly maps [-1, +1] -> [-5, +5]
            result = compute_orderbook_imbalance(
                bids=bids,
                asks=asks,
                mid_price=mid_price,
                band_pct=band_pct,
            )

            # Override the sub_score with EMA-smoothed value
            from dataclasses import replace as dc_replace
            from app.domain.alpha_score import _clamp_subscore, _SUBSCORE_MAX

            ema_sub_score = (ema_ratio * _SUBSCORE_MAX).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            ema_sub_score = _clamp_subscore(ema_sub_score)

            smoothed_result = dc_replace(
                result,
                sub_score=ema_sub_score,
                imbalance_ratio=ema_ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            )

            with self._lock:
                self._depth_cache[symbol] = CachedValue(smoothed_result, now, DEPTH_CACHE_TTL)

            return smoothed_result, "live"

        except Exception as e:
            logger.warning("Orderbook Fetch Fehler (%s): %s", symbol, e)

            with self._lock:
                cached = self._depth_cache.get(symbol)
                if cached:
                    if cached.is_stale(now):
                        return cached.value, "stale"
                    return cached.value, "cached"

            return None, "unavailable"

    # --- OKX Funding Rate (own cache, NOT SentimentDataService) ---

    def _get_funding_rate(
        self, now: datetime, inst_id: str
    ) -> tuple:
        """
        Holt OKX Funding Rate mit eigenem Cache.

        Returns:
            (Decimal_rate_or_None, quality_string)
        """
        with self._lock:
            cached = self._funding_cache.get(inst_id)
            if cached and not cached.is_expired(now):
                return cached.value, "live"

        try:
            resp = requests.get(
                OKX_FUNDING_URL,
                params={"instId": inst_id},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                rate = Decimal(data[0].get("fundingRate", "0"))
                with self._lock:
                    self._funding_cache[inst_id] = CachedValue(
                        rate, now, FUNDING_CACHE_TTL
                    )
                return rate, "live"
        except Exception as e:
            logger.warning("OKX Funding Rate Fehler (%s): %s", inst_id, e)

        with self._lock:
            cached = self._funding_cache.get(inst_id)
            if cached:
                if cached.is_stale(now):
                    return cached.value, "stale"
                return cached.value, "cached"

        return None, "unavailable"

    # --- Trailing Stop Updates ---

    def _update_trailing_stops_from_klines(
        self,
        now: datetime,
        interval: str,
        xrpbtc_klines: Optional[list],
        btceur_klines: Optional[list],
        xrpbtc_closes: List[Decimal],
        btceur_closes: List[Decimal],
        atr_mult_btc: Decimal,
        atr_mult_xrp: Decimal,
        resume_n: int,
        leadlag_window: int,
    ) -> None:
        """
        Aktualisiert Trailing Stops fuer BTCEUR und XRPEUR.

        Berechnet ATR aus Klines und aktualisiert die Stop-Level.
        Portfolio-aware: korrelationsbasierte Stop-Verschaerfung.
        """
        interval_td = INTERVAL_DURATION.get(interval, timedelta(minutes=15))
        stale_threshold = interval_td * 2

        # Compute portfolio correlation for stop tightening
        correlation_factor = Decimal("1")  # Default: no tightening
        if btceur_closes and xrpbtc_closes and len(btceur_closes) > leadlag_window and len(xrpbtc_closes) > leadlag_window:
            try:
                btc_rets = [
                    (btceur_closes[i] - btceur_closes[i - 1]) / btceur_closes[i - 1]
                    if btceur_closes[i - 1] != 0 else Decimal("0")
                    for i in range(1, len(btceur_closes))
                ]
                # For XRP/EUR correlation, we need XRP movement in EUR terms
                # Use XRPBTC returns as proxy (correlated with XRPEUR)
                xrp_rets = [
                    (xrpbtc_closes[i] - xrpbtc_closes[i - 1]) / xrpbtc_closes[i - 1]
                    if xrpbtc_closes[i - 1] != 0 else Decimal("0")
                    for i in range(1, len(xrpbtc_closes))
                ]
                # Use last leadlag_window returns for rolling correlation
                min_len = min(len(btc_rets), len(xrp_rets), leadlag_window)
                if min_len >= 10:
                    corr = _decimal_pearson_correlation(
                        btc_rets[-min_len:],
                        xrp_rets[-min_len:],
                    )
                    # When correlation > 0.7, tighten stops
                    # Max 15% tightening at correlation 1.0
                    if corr > Decimal("0.7"):
                        tightening = (corr - Decimal("0.7")) * Decimal("0.5")
                        correlation_factor = Decimal("1") - tightening
            except Exception as e:
                logger.debug("Portfolio correlation Fehler: %s", e)

        # --- BTCEUR trailing stop ---
        if btceur_klines and len(btceur_klines) > 14:
            try:
                btceur_candles = [
                    {
                        "high": Decimal(str(k[2])),
                        "low": Decimal(str(k[3])),
                        "close": Decimal(str(k[4])),
                    }
                    for k in btceur_klines
                ]
                btceur_atr = compute_atr_standalone(btceur_candles, period=14)
                if btceur_atr is not None:
                    last_kline_time = int(btceur_klines[-1][6])  # Close time ms
                    last_kline_dt = datetime.fromtimestamp(
                        last_kline_time / 1000, tz=timezone.utc
                    )
                    data_fresh = (now - last_kline_dt) < stale_threshold
                    current_price = Decimal(str(btceur_klines[-1][4]))

                    # Apply portfolio correlation tightening
                    effective_mult = atr_mult_btc * correlation_factor

                    with self._lock:
                        if "BTCEUR" not in self._trailing_stops:
                            self._trailing_stops["BTCEUR"] = TrailingStopState(
                                symbol="BTCEUR",
                                stop_level=None,
                                atr_value=None,
                                atr_distance=None,
                                direction="long",
                                frozen=False,
                                frozen_since=None,
                                fresh_data_count=0,
                                resume_threshold=resume_n,
                                last_price=None,
                                last_updated=None,
                            )
                        current_state = self._trailing_stops["BTCEUR"]

                    new_state = update_trailing_stop(
                        state=current_state,
                        current_price=current_price,
                        current_atr=btceur_atr,
                        multiplier=effective_mult,
                        data_is_fresh=data_fresh,
                        now=now,
                    )

                    with self._lock:
                        self._trailing_stops["BTCEUR"] = new_state
            except Exception as e:
                logger.warning("BTCEUR Trailing Stop Fehler: %s", e)

        # --- XRPEUR trailing stop ---
        # Use XRPBTC klines for ATR (we don't have XRPEUR klines directly),
        # convert via BTCEUR price for stop level
        if xrpbtc_klines and len(xrpbtc_klines) > 14 and btceur_closes:
            try:
                # Compute ATR on XRPBTC klines
                xrpbtc_candles = [
                    {
                        "high": Decimal(str(k[2])),
                        "low": Decimal(str(k[3])),
                        "close": Decimal(str(k[4])),
                    }
                    for k in xrpbtc_klines
                ]
                xrpbtc_atr = compute_atr_standalone(xrpbtc_candles, period=14)
                if xrpbtc_atr is not None:
                    # Convert to EUR: ATR_EUR = ATR_BTC * BTCEUR_price
                    btceur_price = btceur_closes[-1] if btceur_closes else Decimal("0")
                    if btceur_price > 0:
                        xrpeur_atr = xrpbtc_atr * btceur_price
                        xrpeur_price = xrpbtc_closes[-1] * btceur_price

                        last_kline_time = int(xrpbtc_klines[-1][6])
                        last_kline_dt = datetime.fromtimestamp(
                            last_kline_time / 1000, tz=timezone.utc
                        )
                        data_fresh = (now - last_kline_dt) < stale_threshold

                        # Apply portfolio correlation tightening
                        effective_mult = atr_mult_xrp * correlation_factor

                        with self._lock:
                            if "XRPEUR" not in self._trailing_stops:
                                self._trailing_stops["XRPEUR"] = TrailingStopState(
                                    symbol="XRPEUR",
                                    stop_level=None,
                                    atr_value=None,
                                    atr_distance=None,
                                    direction="long",
                                    frozen=False,
                                    frozen_since=None,
                                    fresh_data_count=0,
                                    resume_threshold=resume_n,
                                    last_price=None,
                                    last_updated=None,
                                )
                            current_state = self._trailing_stops["XRPEUR"]

                        new_state = update_trailing_stop(
                            state=current_state,
                            current_price=xrpeur_price,
                            current_atr=xrpeur_atr,
                            multiplier=effective_mult,
                            data_is_fresh=data_fresh,
                            now=now,
                        )

                        with self._lock:
                            self._trailing_stops["XRPEUR"] = new_state
            except Exception as e:
                logger.warning("XRPEUR Trailing Stop Fehler: %s", e)

    # --- Serialization ---

    @staticmethod
    def _serialize_alpha_score(result: AlphaScoreResult) -> dict:
        """Serialisiert AlphaScoreResult fuer JSON-Response."""
        return {
            "status": "ok",
            "score": str(result.score),
            "trade_signal": result.trade_signal,
            "threshold": str(result.threshold),
            "quality": result.quality,
            "active_factors": result.active_factors,
            "total_factors": result.total_factors,
            "regime": {
                "hurst": str(result.regime.hurst),
                "label": result.regime.regime,
                "confidence": str(result.regime.confidence),
                "zscore_weight_pct": str(result.regime.zscore_weight_pct),
            },
            "factors": [
                {
                    "name": f.name,
                    "sub_score": str(f.sub_score),
                    "raw_value": str(f.raw_value) if f.raw_value is not None else None,
                    "weight": str(f.weight),
                    "base_weight": str(f.base_weight),
                    "quality": f.quality,
                    "description": f.description,
                }
                for f in result.factors
            ],
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
        }


# --- Singleton ---

_instance: Optional[AlphaScoreDataService] = None
_lock = threading.Lock()


def get_alpha_score_data_service() -> AlphaScoreDataService:
    """Liefert die Singleton-Instanz des AlphaScoreDataService."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AlphaScoreDataService()
    return _instance


def reset_alpha_score_data_service() -> None:
    """Setzt die Singleton-Instanz zurueck (fuer Tests)."""
    global _instance
    with _lock:
        _instance = None
