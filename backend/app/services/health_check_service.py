"""
HealthCheckService — Parallel health checks for 8 core services.

In-memory only (HLTH-04): No SQLite writes, no get_db() usage.
5-second TTL cache (HLTH-05): CachedValue from binance_public_client.
"""

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from app.db.database import engine
from app.services.binance_public_client import CachedValue, get_binance_public_client
from app.services.websocket_manager import get_stream_manager
from app.services.dry_run_service import get_dry_run_service
from app.services.alpha_score_data_service import get_alpha_score_data_service
from app.services.sentiment_data_service import get_sentiment_data_service
from app.services.macro_data_service import get_macro_data_service
from app.services.telegram_notifier import get_telegram_notifier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class ServiceStatus:
    """Status of a single service."""

    name: str
    status: str  # ok | stale | degraded | stopped | unavailable | error
    last_checked: str  # ISO 8601 timestamp
    detail: str = ""


# ---------------------------------------------------------------------------
# Pure function — overall status aggregation (HLTH-03)
# ---------------------------------------------------------------------------


def compute_overall_status(statuses: dict[str, ServiceStatus]) -> str:
    """
    Aggregate individual service statuses to three-tier overall.

    Returns: "healthy" | "degraded" | "critical"
    """
    status_values = [s.status for s in statuses.values()]

    # Critical: any service in error or unavailable state
    if any(s in ("error", "unavailable") for s in status_values):
        return "critical"

    # Degraded: any service not fully healthy
    if any(s in ("degraded", "stale", "stopped") for s in status_values):
        return "degraded"

    # Healthy: all services ok
    return "healthy"


# ---------------------------------------------------------------------------
# HealthCheckService
# ---------------------------------------------------------------------------


class HealthCheckService:
    """
    Checks 8 core services in parallel via asyncio.gather.

    - Backend, DB, WebSocket, Dry-Run, Alpha Score, Sentiment, Macro, Binance REST
    - Results cached for 5 seconds (CachedValue TTL)
    - All state in-memory (no DB writes)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cached_result: Optional[CachedValue] = None

    async def get_health(self) -> dict:
        """Return cached or fresh health check results."""
        now = datetime.now(timezone.utc)

        # Check cache (thread-safe)
        with self._lock:
            if self._cached_result and not self._cached_result.is_expired(now):
                return self._cached_result.value

        # Cache expired or missing — run checks
        result = await self._run_all_checks()

        # Store in cache
        now = datetime.now(timezone.utc)
        with self._lock:
            self._cached_result = CachedValue(result, now, timedelta(seconds=5))

        return result

    async def _run_all_checks(self) -> dict:
        """Execute all 8 service checks in parallel."""
        checks = [
            self._check_backend(),
            self._check_db(),
            self._check_websocket(),
            self._check_dry_run(),
            self._check_alpha_score(),
            self._check_sentiment(),
            self._check_macro(),
            self._check_binance_rest(),
        ]

        results = await asyncio.gather(*checks, return_exceptions=True)

        service_names = [
            "backend",
            "db",
            "websocket",
            "dry_run",
            "alpha_score",
            "sentiment",
            "macro",
            "binance_rest",
        ]

        now_iso = datetime.now(timezone.utc).isoformat()
        statuses: dict[str, ServiceStatus] = {}

        for name, result in zip(service_names, results):
            if isinstance(result, Exception):
                statuses[name] = ServiceStatus(
                    name=name,
                    status="error",
                    last_checked=now_iso,
                    detail=str(result),
                )
            else:
                statuses[name] = result

        overall = compute_overall_status(statuses)

        result = {
            "overall_status": overall,
            "services": {name: asdict(s) for name, s in statuses.items()},
            "checked_at": now_iso,
        }

        # Notify on state transitions (TELE-01)
        try:
            notifier = get_telegram_notifier()
            await notifier.check_transitions(result)
        except Exception:
            logger.exception("TelegramNotifier.check_transitions() failed")

        return result

    # -------------------------------------------------------------------
    # Individual service checks
    # -------------------------------------------------------------------

    async def _check_backend(self) -> ServiceStatus:
        """Backend is alive if this code runs."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return ServiceStatus(name="backend", status="ok", last_checked=now_iso)

    async def _check_db(self) -> ServiceStatus:
        """Check SQLite connectivity via read-only SELECT 1."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            if engine is None:
                return ServiceStatus(
                    name="db",
                    status="unavailable",
                    last_checked=now_iso,
                    detail="Engine not initialized",
                )

            # Use raw connection — NOT get_db() which auto-commits
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            return ServiceStatus(name="db", status="ok", last_checked=now_iso)
        except Exception as e:
            return ServiceStatus(
                name="db",
                status="error",
                last_checked=now_iso,
                detail=str(e),
            )

    async def _check_websocket(self) -> ServiceStatus:
        """Check BinanceStreamManager state."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            manager = get_stream_manager()
            stats = manager.get_stats()

            if not stats.get("running"):
                return ServiceStatus(
                    name="websocket",
                    status="stopped",
                    last_checked=now_iso,
                    detail="Stream manager not running",
                )

            if not stats.get("current_prices"):
                return ServiceStatus(
                    name="websocket",
                    status="degraded",
                    last_checked=now_iso,
                    detail="Running but no prices received",
                )

            return ServiceStatus(name="websocket", status="ok", last_checked=now_iso)
        except Exception as e:
            return ServiceStatus(
                name="websocket",
                status="error",
                last_checked=now_iso,
                detail=str(e),
            )

    async def _check_dry_run(self) -> ServiceStatus:
        """Check DryRunService running state."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            svc = get_dry_run_service()
            if svc._running:
                return ServiceStatus(
                    name="dry_run", status="ok", last_checked=now_iso
                )
            return ServiceStatus(
                name="dry_run",
                status="stopped",
                last_checked=now_iso,
                detail="Dry run service not running",
            )
        except Exception as e:
            return ServiceStatus(
                name="dry_run",
                status="error",
                last_checked=now_iso,
                detail=str(e),
            )

    async def _check_alpha_score(self) -> ServiceStatus:
        """Check AlphaScoreDataService cache freshness."""
        now_iso = datetime.now(timezone.utc).isoformat()
        now = datetime.now(timezone.utc)
        try:
            service = get_alpha_score_data_service()

            # Read cache dict under service's lock for thread safety
            with service._lock:
                kline_entries = dict(service._kline_cache)

            if not kline_entries:
                return ServiceStatus(
                    name="alpha_score",
                    status="unavailable",
                    last_checked=now_iso,
                    detail="No cached data",
                )

            # Check if any entry is still fresh
            any_live = any(
                not cv.is_expired(now) for cv in kline_entries.values()
            )
            all_stale = all(cv.is_stale(now) for cv in kline_entries.values())

            if any_live:
                return ServiceStatus(
                    name="alpha_score", status="ok", last_checked=now_iso
                )
            elif all_stale:
                return ServiceStatus(
                    name="alpha_score",
                    status="stale",
                    last_checked=now_iso,
                    detail="All cache entries stale",
                )
            else:
                return ServiceStatus(
                    name="alpha_score",
                    status="degraded",
                    last_checked=now_iso,
                    detail="Cache expired but not stale",
                )
        except Exception as e:
            return ServiceStatus(
                name="alpha_score",
                status="error",
                last_checked=now_iso,
                detail=str(e),
            )

    async def _check_sentiment(self) -> ServiceStatus:
        """Check SentimentDataService cache freshness + initialization."""
        now_iso = datetime.now(timezone.utc).isoformat()
        now = datetime.now(timezone.utc)
        try:
            service = get_sentiment_data_service()

            with service._lock:
                initialized = service._history_initialized
                cache_entries = dict(service._cache)

            if not initialized:
                return ServiceStatus(
                    name="sentiment",
                    status="unavailable",
                    last_checked=now_iso,
                    detail="History not initialized",
                )

            if cache_entries and any(
                not cv.is_expired(now) for cv in cache_entries.values()
            ):
                return ServiceStatus(
                    name="sentiment", status="ok", last_checked=now_iso
                )

            return ServiceStatus(
                name="sentiment",
                status="stale",
                last_checked=now_iso,
                detail="Initialized but all cache expired",
            )
        except Exception as e:
            return ServiceStatus(
                name="sentiment",
                status="error",
                last_checked=now_iso,
                detail=str(e),
            )

    async def _check_macro(self) -> ServiceStatus:
        """Check MacroDataService cache freshness."""
        now_iso = datetime.now(timezone.utc).isoformat()
        now = datetime.now(timezone.utc)
        try:
            service = get_macro_data_service()

            with service._lock:
                cache_entries = dict(service._cache)

            if not cache_entries:
                return ServiceStatus(
                    name="macro",
                    status="unavailable",
                    last_checked=now_iso,
                    detail="No cached data",
                )

            any_live = any(
                not cv.is_expired(now) for cv in cache_entries.values()
            )

            if any_live:
                return ServiceStatus(
                    name="macro", status="ok", last_checked=now_iso
                )

            return ServiceStatus(
                name="macro",
                status="stale",
                last_checked=now_iso,
                detail="All cache entries expired",
            )
        except Exception as e:
            return ServiceStatus(
                name="macro",
                status="error",
                last_checked=now_iso,
                detail=str(e),
            )

    async def _check_binance_rest(self) -> ServiceStatus:
        """Check Binance public REST API reachability with 2s timeout."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            client = get_binance_public_client()
            await asyncio.wait_for(
                asyncio.to_thread(client.get_ticker_price, "BTCEUR"),
                timeout=2.0,
            )
            return ServiceStatus(
                name="binance_rest", status="ok", last_checked=now_iso
            )
        except (asyncio.TimeoutError, Exception) as e:
            return ServiceStatus(
                name="binance_rest",
                status="error",
                last_checked=now_iso,
                detail=str(e),
            )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service_instance: Optional[HealthCheckService] = None
_service_lock = threading.Lock()


def get_health_check_service() -> HealthCheckService:
    """Liefert die Singleton-Instanz des HealthCheckService."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = HealthCheckService()
    return _service_instance
