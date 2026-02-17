"""
Orderblock Data Service - Fetcht Klines, cached, orchestriert Detection + Backtest.

Datenquelle: Binance REST API (oeffentliche Klines, kein API Key noetig).
Pattern: Singleton mit threading.Lock und CachedValue (analog sentiment_data_service.py).

Paginierung: Binance liefert max 1000 Klines/Request (Weight 2).
6 Monate 1h ≈ 4.380 Kerzen → ~5 API-Calls.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from app.domain.orderblock import (
    Candle,
    OBConfig,
    Orderblock,
    compute_sentiment_confluence,
    detect_orderblocks,
    update_zone_states,
)
from app.domain.orderblock_backtest import run_backtest
from app.services.binance_public_client import CachedValue, get_binance_public_client

logger = logging.getLogger(__name__)

# ─── Konfiguration ───

KLINE_CACHE_TTL = timedelta(hours=1)
REQUEST_TIMEOUT = 15  # Sekunden
MAX_KLINES_PER_REQUEST = 1000

# Interval → Millisekunden Mapping
INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

ALLOWED_INTERVALS = set(INTERVAL_MS.keys())


class OrderblockDataService:
    """
    Singleton-Service fuer Orderblock Detection + Backtest.

    Thread-safe via Lock. Haelt In-Memory Cache fuer Klines.
    """

    def __init__(self):
        self._cache: dict[str, CachedValue] = {}
        self._lock = threading.Lock()

    def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        months: int = 6,
    ) -> List[Candle]:
        """
        Fetcht OHLCV Klines von Binance REST API (paginiert).

        Verwendet Cache fuer identische (symbol, interval, months) Anfragen.
        """
        now = datetime.now(timezone.utc)

        if end_time is None:
            end_time = now
        if start_time is None:
            start_time = end_time - timedelta(days=months * 30)

        cache_key = f"klines_{symbol}_{interval}_{months}"

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and not cached.is_expired(now):
                logger.info(
                    "Klines Cache-Hit: %s %s %d Monate (%d Kerzen)",
                    symbol,
                    interval,
                    months,
                    len(cached.value),
                )
                return cached.value

        # Fetch ausserhalb Lock
        candles = self._fetch_klines_paginated(symbol, interval, start_time, end_time)

        with self._lock:
            self._cache[cache_key] = CachedValue(candles, now, KLINE_CACHE_TTL)

        logger.info(
            "Klines gefetcht: %s %s %d Monate → %d Kerzen",
            symbol,
            interval,
            months,
            len(candles),
        )
        return candles

    def analyze(
        self,
        symbol: str,
        interval: str,
        months: int = 6,
        config: Optional[OBConfig] = None,
    ) -> dict:
        """
        Combined Detection + Backtest: Fetch → detect → state update → simulate → metrics.

        Ein einziger Aufruf auf denselben Kerzen garantiert konsistente Ergebnisse
        zwischen Zonen-Liste und Backtest-Metriken.

        Returns: Dict mit zones, raw_zones, metrics, trades, config, meta.
        """
        if config is None:
            config = OBConfig()

        candles = self.fetch_candles(symbol, interval, months=months)

        empty = {
            "zones": [],
            "raw_zones": [],
            "metrics": {},
            "trades": [],
            "config": serialize_config(config),
            "meta": {
                "symbol": symbol,
                "interval": interval,
                "months": months,
                "candle_count": 0,
            },
        }

        if not candles:
            return empty

        # Combined: Detection + Simulation (pure Domain-Logik, gleiche Kerzen)
        result = run_backtest(candles, config, timeframe=interval, symbol=symbol)

        # Sentiment Confluence: Snapshot holen und Zonen annotieren
        sentiment_score = self._fetch_sentiment_snapshot(symbol)
        if sentiment_score is not None:
            for zone in result.zones:
                confluence = compute_sentiment_confluence(
                    sentiment_score, zone.direction, zone.conviction_score
                )
                zone.sentiment_at_detection = confluence.sentiment_at_detection
                zone.confluence_label = confluence.confluence_label.value
                zone.confluence_score = confluence.confluence_score

        return {
            "result": result,
            "zones": [serialize_zone(z) for z in result.zones],
            "raw_zones": result.zones,
            "metrics": serialize_metrics(result),
            "trades": [serialize_trade(t) for t in result.trades],
            "config": serialize_config(config),
            "meta": {
                "symbol": symbol,
                "interval": interval,
                "months": months,
                "candle_count": result.candle_count,
                "data_start": utc_iso(result.data_start),
                "data_end": utc_iso(result.data_end),
                "sentiment_score": (
                    float(sentiment_score) if sentiment_score is not None else None
                ),
            },
        }

    # ─── Sentiment Snapshot (Graceful Degradation) ───

    def _fetch_sentiment_snapshot(self, symbol: str) -> Optional[Decimal]:
        """
        Holt aktuellen Sentiment Composite Score fuer Confluence-Annotation.

        Graceful Degradation: Gibt None zurueck wenn Sentiment-Service nicht verfuegbar.
        Sentiment wird im Service-Layer gefetcht (Domain bleibt pure).
        """
        try:
            from app.services.sentiment_data_service import get_sentiment_data_service

            sentiment_service = get_sentiment_data_service()
            sentiment_data = sentiment_service.get_sentiment(symbol=symbol)
            score = sentiment_data.get("composite_score")
            if score is not None:
                return Decimal(str(score))
        except Exception as e:
            logger.warning("Sentiment-Fetch fuer OB Confluence fehlgeschlagen: %s", e)
        return None

    # ─── Public: Window-basierter Fetch (fuer Chart-Endpoint) ───

    def fetch_candles_for_window(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Candle]:
        """Fetcht Klines fuer ein explizites Zeitfenster (kein Month-Cache)."""
        return self._fetch_klines_paginated(symbol, interval, start_time, end_time)

    # ─── Private: Kline Fetch ───

    def _fetch_klines_paginated(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Candle]:
        """Paginiertes Kline-Fetching (max 1000 pro Request)."""
        client = get_binance_public_client()
        candles: List[Candle] = []
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        interval_ms = INTERVAL_MS.get(interval, 3_600_000)

        current_start = start_ms
        page = 0

        while current_start < end_ms:
            page += 1
            try:
                data = client.get_klines(
                    symbol,
                    interval,
                    limit=MAX_KLINES_PER_REQUEST,
                    start_time=current_start,
                    end_time=end_ms,
                )
            except Exception as e:
                logger.error("Binance Kline Fetch Fehler (Page %d): %s", page, e)
                break

            if not data:
                break

            for raw in data:
                candles.append(
                    Candle(
                        timestamp=datetime.fromtimestamp(
                            raw[0] / 1000, tz=timezone.utc
                        ).replace(tzinfo=None),
                        open=Decimal(str(raw[1])),
                        high=Decimal(str(raw[2])),
                        low=Decimal(str(raw[3])),
                        close=Decimal(str(raw[4])),
                        volume=Decimal(str(raw[5])),
                    )
                )

            # Naechste Seite: letzter Timestamp + 1 Interval
            last_ts = data[-1][0]
            current_start = last_ts + interval_ms

            if len(data) < MAX_KLINES_PER_REQUEST:
                break

            logger.debug(
                "Kline Page %d: %d Kerzen, naechster Start: %s",
                page,
                len(data),
                datetime.fromtimestamp(current_start / 1000, tz=timezone.utc),
            )

        return candles


# ─── Serialisierung ───


def serialize_candle_for_chart(candle: Candle) -> dict:
    """Candle → lightweight-charts Format (time als Unix-Sekunden, Werte als float)."""
    # Naive datetime ist intern UTC → explizit markieren, damit .timestamp() korrekt rechnet
    utc_dt = candle.timestamp.replace(tzinfo=timezone.utc)
    return {
        "time": int(utc_dt.timestamp()),
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": float(candle.volume),
    }


def utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Naive datetime (intern UTC) → ISO-String mit Z-Suffix fuer Frontend."""
    if dt is None:
        return None
    return dt.isoformat() + "Z"


def serialize_zone(zone: Orderblock) -> dict:
    """Serialisiert einen Orderblock fuer API-Response."""
    return {
        "id": zone.id,
        "direction": zone.direction.value,
        "state": zone.state.value,
        "conviction": zone.conviction.value,
        "zone_top": str(zone.zone_top),
        "zone_bottom": str(zone.zone_bottom),
        "equilibrium": str(zone.equilibrium),
        "entry_edge": str(zone.entry_edge),
        "stop_edge": str(zone.stop_edge),
        "formed_at": utc_iso(zone.formed_at),
        "confirmed_at": utc_iso(zone.confirmed_at),
        "mitigated_at": utc_iso(zone.mitigated_at),
        "invalidated_at": utc_iso(zone.invalidated_at),
        "volume_zscore": str(zone.volume_zscore),
        "volume_weight": str(zone.volume_weight),
        "volume_percentile": str(zone.volume_percentile),
        "ofi_divergence": str(zone.ofi_divergence),
        "impact_efficiency_ratio": str(zone.impact_efficiency_ratio),
        "conviction_score": str(zone.conviction_score),
        "is_high_conviction_zscore": zone.is_high_conviction_zscore,
        "category": (
            zone.category.value if hasattr(zone.category, "value") else "UNCLASSIFIED"
        ),
        "atr_at_formation": str(zone.atr_at_formation),
        "displacement_range": str(zone.displacement_range),
        "bos_swing_price": str(zone.bos_swing_price),
        # Liquidity Sweep
        "has_liquidity_sweep": zone.has_liquidity_sweep,
        "liquidity_sweep_level": (
            str(zone.liquidity_sweep_level)
            if zone.liquidity_sweep_level is not None
            else None
        ),
        # Sentiment Confluence
        "sentiment_at_detection": (
            str(zone.sentiment_at_detection)
            if zone.sentiment_at_detection is not None
            else None
        ),
        "confluence_label": zone.confluence_label,
        "confluence_score": (
            str(zone.confluence_score) if zone.confluence_score is not None else None
        ),
    }


def serialize_config(config: OBConfig) -> dict:
    """Serialisiert OBConfig fuer API-Response / DB-Persistenz."""
    return {
        "atr_length": config.atr_length,
        "atr_multiplier": str(config.atr_multiplier),
        "fvg_window": config.fvg_window,
        "swing_fractal_n": config.swing_fractal_n,
        "target_rr": str(config.target_rr),
        "entry_policy": config.entry_policy.value,
        "stop_policy": config.stop_policy.value,
        "mitigation_policy": config.mitigation_policy.value,
        "zscore_lookback": config.zscore_lookback,
        "zscore_threshold": str(config.zscore_threshold),
        "max_holding_candles": config.max_holding_candles,
        "impulse_window": config.impulse_window,
        "sweep_lookback": config.sweep_lookback,
        "sweep_conviction_boost": str(config.sweep_conviction_boost),
    }


def serialize_metrics(result) -> dict:
    """Serialisiert BacktestMetrics fuer API-Response."""
    m = result.metrics
    return {
        "total_zones": m.total_zones,
        "total_trades": m.total_trades,
        "hits": m.hits,
        "misses": m.misses,
        "open_trades": m.open_trades,
        "expired_trades": m.expired_trades,
        "hit_rate": str(m.hit_rate) if m.hit_rate is not None else None,
        "avg_penetration_depth_pct": str(m.avg_penetration_depth_pct),
        "median_penetration_depth_pct": str(m.median_penetration_depth_pct),
        "avg_holding_duration_candles": str(m.avg_holding_duration_candles),
        "median_holding_duration_candles": str(m.median_holding_duration_candles),
        "high_conviction_count": m.high_conviction_count,
        "high_conviction_hit_rate": (
            str(m.high_conviction_hit_rate)
            if m.high_conviction_hit_rate is not None
            else None
        ),
        "standard_conviction_hit_rate": (
            str(m.standard_conviction_hit_rate)
            if m.standard_conviction_hit_rate is not None
            else None
        ),
        "conviction_breakdown": [
            {
                "level": b.level,
                "count": b.count,
                "hits": b.hits,
                "misses": b.misses,
                "expired": b.expired,
                "hit_rate": str(b.hit_rate) if b.hit_rate is not None else None,
            }
            for b in m.conviction_breakdown
        ],
        "zscore_clusters": [
            {
                "range_label": c.range_label,
                "range_low": str(c.range_low),
                "range_high": str(c.range_high),
                "count": c.count,
                "hits": c.hits,
                "misses": c.misses,
                "hit_rate": str(c.hit_rate) if c.hit_rate is not None else None,
            }
            for c in m.zscore_clusters
        ],
        "high_conviction_zscore_count": m.high_conviction_zscore_count,
        "high_conviction_zscore_hit_rate": (
            str(m.high_conviction_zscore_hit_rate)
            if m.high_conviction_zscore_hit_rate is not None
            else None
        ),
        "unmitigated_count": m.unmitigated_count,
        "mitigated_count": m.mitigated_count,
        "invalid_count": m.invalid_count,
        "zones_per_month": str(m.zones_per_month),
    }


def serialize_trade(trade) -> dict:
    """Serialisiert einen BacktestTrade fuer API-Response."""
    return {
        "ob_id": trade.ob_id,
        "direction": trade.direction.value,
        "entry_edge": str(trade.entry_edge),
        "stop_edge": str(trade.stop_edge),
        "target": str(trade.target),
        "entry_price": str(trade.entry_price),
        "entry_timestamp": utc_iso(trade.entry_timestamp),
        "exit_timestamp": utc_iso(trade.exit_timestamp),
        "outcome": trade.outcome.value,
        "penetration_depth_pct": str(trade.penetration_depth_pct),
        "holding_duration_candles": trade.holding_duration_candles,
        "min_adverse_price": str(trade.min_adverse_price),
        "conviction": trade.conviction.value,
        "volume_zscore": str(trade.volume_zscore),
        "conviction_score": str(trade.conviction_score),
        "has_liquidity_sweep": trade.has_liquidity_sweep,
    }


# ─── Singleton ───

_instance: Optional[OrderblockDataService] = None
_instance_lock = threading.Lock()


def get_orderblock_data_service() -> OrderblockDataService:
    """Liefert Singleton-Instanz des OrderblockDataService."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = OrderblockDataService()
    return _instance
