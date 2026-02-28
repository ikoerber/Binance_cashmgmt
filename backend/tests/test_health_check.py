"""Tests for HealthCheckService — covers HLTH-01 through HLTH-05.

All service singletons are mocked — no real Binance/DB calls.
"""

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.health_check_service import (
    ServiceStatus,
    HealthCheckService,
    compute_overall_status,
    get_health_check_service,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_STATUSES = {"ok", "stale", "degraded", "stopped", "unavailable", "error"}

EXPECTED_SERVICE_KEYS = {
    "backend",
    "db",
    "websocket",
    "dry_run",
    "alpha_score",
    "sentiment",
    "macro",
    "binance_rest",
}


def _make_mock_engine():
    """Return a mock engine whose .connect() context manager supports execute()."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return mock_engine, mock_conn


def _make_mock_stream_manager(running=True, has_prices=True):
    mgr = MagicMock()
    mgr.get_stats.return_value = {
        "running": running,
        "current_prices": {"BTCEUR": "50000"} if has_prices else {},
        "price_subscribers": 1,
        "user_data_streams": 0,
        "active_tasks": 1,
        "has_async_client": True,
    }
    return mgr


def _make_mock_dry_run_service(running=True):
    svc = MagicMock()
    svc._running = running
    return svc


def _make_cached_value(expired=False, stale=False):
    cv = MagicMock()
    cv.is_expired.return_value = expired
    cv.is_stale.return_value = stale
    return cv


def _make_mock_alpha_score_service(empty=False, any_live=True, all_stale=False):
    svc = MagicMock()
    svc._lock = MagicMock()
    svc._lock.__enter__ = MagicMock(return_value=None)
    svc._lock.__exit__ = MagicMock(return_value=False)
    if empty:
        svc._kline_cache = {}
    else:
        cv = _make_cached_value(expired=not any_live, stale=all_stale)
        svc._kline_cache = {"BTCEUR_4h": cv}
    return svc


def _make_mock_sentiment_service(initialized=True, has_live_cache=True):
    svc = MagicMock()
    svc._lock = MagicMock()
    svc._lock.__enter__ = MagicMock(return_value=None)
    svc._lock.__exit__ = MagicMock(return_value=False)
    svc._history_initialized = initialized
    if initialized and has_live_cache:
        cv = _make_cached_value(expired=False)
        svc._cache = {"fng": cv}
    elif initialized:
        cv = _make_cached_value(expired=True)
        svc._cache = {"fng": cv}
    else:
        svc._cache = {}
    return svc


def _make_mock_macro_service(empty=False, any_live=True):
    svc = MagicMock()
    svc._lock = MagicMock()
    svc._lock.__enter__ = MagicMock(return_value=None)
    svc._lock.__exit__ = MagicMock(return_value=False)
    if empty:
        svc._cache = {}
    else:
        cv = _make_cached_value(expired=not any_live)
        svc._cache = {"binance_BTCEUR_1m": cv}
    return svc


def _make_mock_binance_public_client():
    client = MagicMock()
    from decimal import Decimal
    client.get_ticker_price.return_value = Decimal("50000.00")
    return client


def _patch_all_services(
    engine=None,
    stream_manager=None,
    dry_run=None,
    alpha_score=None,
    sentiment=None,
    macro=None,
    binance_client=None,
):
    """Context manager that patches all 6 singleton getters + engine."""
    if engine is None:
        engine, _ = _make_mock_engine()
    if stream_manager is None:
        stream_manager = _make_mock_stream_manager()
    if dry_run is None:
        dry_run = _make_mock_dry_run_service()
    if alpha_score is None:
        alpha_score = _make_mock_alpha_score_service()
    if sentiment is None:
        sentiment = _make_mock_sentiment_service()
    if macro is None:
        macro = _make_mock_macro_service()
    if binance_client is None:
        binance_client = _make_mock_binance_public_client()

    patches = [
        patch("app.services.health_check_service.engine", engine),
        patch(
            "app.services.health_check_service.get_stream_manager",
            return_value=stream_manager,
        ),
        patch(
            "app.services.health_check_service.get_dry_run_service",
            return_value=dry_run,
        ),
        patch(
            "app.services.health_check_service.get_alpha_score_data_service",
            return_value=alpha_score,
        ),
        patch(
            "app.services.health_check_service.get_sentiment_data_service",
            return_value=sentiment,
        ),
        patch(
            "app.services.health_check_service.get_macro_data_service",
            return_value=macro,
        ),
        patch(
            "app.services.health_check_service.get_binance_public_client",
            return_value=binance_client,
        ),
    ]

    class CombinedPatch:
        def __enter__(self_inner):
            for p in patches:
                p.__enter__()
            return self_inner

        def __exit__(self_inner, *args):
            for p in reversed(patches):
                p.__exit__(*args)

    return CombinedPatch()


# ---------------------------------------------------------------------------
# Tests — HLTH-01
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_all_8_services():
    """HLTH-01: check_all_services() returns dict with exactly 8 service keys."""
    service = HealthCheckService()
    with _patch_all_services():
        result = await service.get_health()

    assert "services" in result
    assert set(result["services"].keys()) == EXPECTED_SERVICE_KEYS


@pytest.mark.asyncio
async def test_each_service_returns_status():
    """HLTH-01: Each service returns a ServiceStatus with name, status, last_checked."""
    service = HealthCheckService()
    with _patch_all_services():
        result = await service.get_health()

    for key, svc_data in result["services"].items():
        assert "name" in svc_data, f"Missing 'name' for {key}"
        assert "status" in svc_data, f"Missing 'status' for {key}"
        assert "last_checked" in svc_data, f"Missing 'last_checked' for {key}"


# ---------------------------------------------------------------------------
# Tests — HLTH-02
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_values_valid():
    """HLTH-02: All status values are from the valid set."""
    service = HealthCheckService()
    with _patch_all_services():
        result = await service.get_health()

    for key, svc_data in result["services"].items():
        assert svc_data["status"] in VALID_STATUSES, (
            f"Invalid status '{svc_data['status']}' for {key}"
        )


@pytest.mark.asyncio
async def test_last_checked_timestamp():
    """HLTH-02: last_checked is a valid ISO 8601 timestamp."""
    service = HealthCheckService()
    with _patch_all_services():
        result = await service.get_health()

    for key, svc_data in result["services"].items():
        ts = svc_data["last_checked"]
        # Should parse without error
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None, f"Timestamp for {key} lacks timezone info"


# ---------------------------------------------------------------------------
# Tests — HLTH-03
# ---------------------------------------------------------------------------


def test_overall_healthy():
    """HLTH-03: compute_overall_status returns 'healthy' when all services are 'ok'."""
    statuses = {
        name: ServiceStatus(name=name, status="ok", last_checked="2026-01-01T00:00:00+00:00")
        for name in EXPECTED_SERVICE_KEYS
    }
    assert compute_overall_status(statuses) == "healthy"


def test_overall_degraded():
    """HLTH-03: Returns 'degraded' when any service is stale/degraded/stopped but none error/unavailable."""
    for degraded_status in ("stale", "degraded", "stopped"):
        statuses = {
            name: ServiceStatus(name=name, status="ok", last_checked="2026-01-01T00:00:00+00:00")
            for name in EXPECTED_SERVICE_KEYS
        }
        # Set one service to a degraded state
        statuses["macro"] = ServiceStatus(
            name="macro", status=degraded_status, last_checked="2026-01-01T00:00:00+00:00"
        )
        assert compute_overall_status(statuses) == "degraded", (
            f"Expected 'degraded' when macro is '{degraded_status}'"
        )


def test_overall_critical():
    """HLTH-03: Returns 'critical' when any service is error or unavailable."""
    for critical_status in ("error", "unavailable"):
        statuses = {
            name: ServiceStatus(name=name, status="ok", last_checked="2026-01-01T00:00:00+00:00")
            for name in EXPECTED_SERVICE_KEYS
        }
        statuses["db"] = ServiceStatus(
            name="db", status=critical_status, last_checked="2026-01-01T00:00:00+00:00"
        )
        assert compute_overall_status(statuses) == "critical", (
            f"Expected 'critical' when db is '{critical_status}'"
        )


# ---------------------------------------------------------------------------
# Tests — HLTH-04
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_db_writes():
    """HLTH-04: DB check uses engine.connect() + SELECT 1, not get_db()."""
    mock_engine, mock_conn = _make_mock_engine()
    service = HealthCheckService()

    with _patch_all_services(engine=mock_engine):
        await service.get_health()

    # engine.connect() must have been called
    mock_engine.connect.assert_called()
    # The connection must have had execute() called (for SELECT 1)
    mock_conn.execute.assert_called()
    # Verify the execute call used text("SELECT 1")
    call_args = mock_conn.execute.call_args
    assert "SELECT 1" in str(call_args), "Expected SELECT 1 query"


# ---------------------------------------------------------------------------
# Tests — HLTH-05
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_5s_cache():
    """HLTH-05: Two rapid calls return same result without re-running checks."""
    service = HealthCheckService()
    call_count = 0

    original_run = service._run_all_checks

    async def counting_run():
        nonlocal call_count
        call_count += 1
        return await original_run()

    with _patch_all_services():
        service._run_all_checks = counting_run

        result1 = await service.get_health()
        result2 = await service.get_health()

    assert call_count == 1, f"Expected 1 check run, got {call_count}"
    assert result1 == result2


@pytest.mark.asyncio
async def test_cache_expiry():
    """HLTH-05: After 5s, get_health() re-runs checks."""
    service = HealthCheckService()
    call_count = 0

    original_run = service._run_all_checks

    async def counting_run():
        nonlocal call_count
        call_count += 1
        return await original_run()

    with _patch_all_services():
        service._run_all_checks = counting_run

        await service.get_health()
        assert call_count == 1

        # Manually expire the cache by shifting its fetched_at back
        if service._cached_result:
            service._cached_result.fetched_at = (
                datetime.now(timezone.utc) - timedelta(seconds=10)
            )

        await service.get_health()
        assert call_count == 2, f"Expected 2 check runs after cache expiry, got {call_count}"
