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

import requests

from app.domain.orderblock import (
    Candle,
    OBConfig,
    Orderblock,
    detect_orderblocks,
    update_zone_states,
)
from app.domain.orderblock_backtest import run_backtest

logger = logging.getLogger(__name__)

# ─── Konfiguration ───

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
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


class CachedValue:
    """Einfacher Cache-Eintrag mit TTL."""

    def __init__(self, value, fetched_at: datetime, ttl: timedelta):
        self.value = value
        self.fetched_at = fetched_at
        self.ttl = ttl

    def is_expired(self, now: datetime) -> bool:
        return (now - self.fetched_at) > self.ttl


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

    def detect_zones(
        self,
        symbol: str,
        interval: str,
        months: int = 6,
        config: Optional[OBConfig] = None,
    ) -> dict:
        """
        Detection ausfuehren: Fetch → detect → state update → serialize.

        Returns: Dict mit zones, config, meta.
        """
        if config is None:
            config = OBConfig()

        candles = self.fetch_candles(symbol, interval, months=months)

        if not candles:
            return {
                "zones": [],
                "config": _serialize_config(config),
                "meta": {
                    "symbol": symbol,
                    "interval": interval,
                    "months": months,
                    "candle_count": 0,
                },
            }

        # Detection (pure Domain-Logik)
        zones = detect_orderblocks(candles, config)
        zones = update_zone_states(zones, candles)

        return {
            "zones": [_serialize_zone(z) for z in zones],
            "raw_zones": zones,
            "config": _serialize_config(config),
            "meta": {
                "symbol": symbol,
                "interval": interval,
                "months": months,
                "candle_count": len(candles),
                "data_start": candles[0].timestamp.isoformat(),
                "data_end": candles[-1].timestamp.isoformat(),
            },
        }

    def run_backtest(
        self,
        symbol: str,
        interval: str,
        months: int = 6,
        config: Optional[OBConfig] = None,
    ) -> dict:
        """
        Backtest ausfuehren: Fetch → detect → simulate → metrics → serialize.

        Returns: Dict mit metrics, trades, zones, config, meta.
        """
        if config is None:
            config = OBConfig()

        candles = self.fetch_candles(symbol, interval, months=months)

        if not candles:
            return {
                "metrics": {},
                "trades": [],
                "zones": [],
                "config": _serialize_config(config),
                "meta": {
                    "symbol": symbol,
                    "interval": interval,
                    "months": months,
                    "candle_count": 0,
                },
            }

        # Backtest (pure Domain-Logik)
        result = run_backtest(candles, config, timeframe=interval, symbol=symbol)

        return {
            "result": result,
            "metrics": _serialize_metrics(result),
            "trades": [_serialize_trade(t) for t in result.trades],
            "zones": [_serialize_zone(z) for z in result.zones],
            "config": _serialize_config(config),
            "meta": {
                "symbol": symbol,
                "interval": interval,
                "months": months,
                "candle_count": result.candle_count,
                "data_start": result.data_start.isoformat(),
                "data_end": result.data_end.isoformat(),
            },
        }

    # ─── Private: Kline Fetch ───

    def _fetch_klines_paginated(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Candle]:
        """Paginiertes Kline-Fetching (max 1000 pro Request)."""
        candles: List[Candle] = []
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        interval_ms = INTERVAL_MS.get(interval, 3_600_000)

        current_start = start_ms
        page = 0

        while current_start < end_ms:
            page += 1
            try:
                resp = requests.get(
                    BINANCE_KLINES_URL,
                    params={
                        "symbol": symbol,
                        "interval": interval,
                        "startTime": current_start,
                        "endTime": end_ms,
                        "limit": MAX_KLINES_PER_REQUEST,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
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


def _serialize_zone(zone: Orderblock) -> dict:
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
        "formed_at": zone.formed_at.isoformat(),
        "confirmed_at": zone.confirmed_at.isoformat(),
        "mitigated_at": zone.mitigated_at.isoformat() if zone.mitigated_at else None,
        "invalidated_at": (
            zone.invalidated_at.isoformat() if zone.invalidated_at else None
        ),
        "volume_zscore": str(zone.volume_zscore),
        "volume_weight": str(zone.volume_weight),
        "volume_percentile": str(zone.volume_percentile),
        "ofi_divergence": str(zone.ofi_divergence),
        "impact_efficiency_ratio": str(zone.impact_efficiency_ratio),
        "conviction_score": str(zone.conviction_score),
        "is_high_conviction_zscore": zone.is_high_conviction_zscore,
        "atr_at_formation": str(zone.atr_at_formation),
        "displacement_range": str(zone.displacement_range),
        "bos_swing_price": str(zone.bos_swing_price),
    }


def _serialize_config(config: OBConfig) -> dict:
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
    }


def _serialize_metrics(result) -> dict:
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


def _serialize_trade(trade) -> dict:
    """Serialisiert einen BacktestTrade fuer API-Response."""
    return {
        "ob_id": trade.ob_id,
        "direction": trade.direction.value,
        "entry_edge": str(trade.entry_edge),
        "stop_edge": str(trade.stop_edge),
        "target": str(trade.target),
        "entry_price": str(trade.entry_price),
        "entry_timestamp": trade.entry_timestamp.isoformat(),
        "exit_timestamp": (
            trade.exit_timestamp.isoformat() if trade.exit_timestamp else None
        ),
        "outcome": trade.outcome.value,
        "penetration_depth_pct": str(trade.penetration_depth_pct),
        "holding_duration_candles": trade.holding_duration_candles,
        "min_adverse_price": str(trade.min_adverse_price),
        "conviction": trade.conviction.value,
        "volume_zscore": str(trade.volume_zscore),
        "conviction_score": str(trade.conviction_score),
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
