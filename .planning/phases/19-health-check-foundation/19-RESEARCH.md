# Phase 19: Health Check Foundation - Research

**Researched:** 2026-02-28
**Domain:** FastAPI Health Check Endpoint + In-Memory Service Status Aggregation
**Confidence:** HIGH

## Summary

Phase 19 implements a structured health endpoint that checks 8 core services in parallel and returns per-service status with an aggregated overall status. The entire implementation uses existing stack components -- FastAPI async routes, `asyncio.gather()` for parallel execution, and the `CachedValue` TTL pattern already established across `SentimentDataService`, `MacroDataService`, and `AlphaScoreDataService`. No new dependencies are required.

The 8 services to check are: Backend (FastAPI process), DB (SQLite connectivity), WebSocket (`BinanceStreamManager`), Dry-Run (`DryRunService`), Alpha Score (`AlphaScoreDataService`), Sentiment (`SentimentDataService`), Macro (`MacroDataService`), and Binance REST (`BinancePublicClient`). Each service already exposes state that can be read non-destructively -- singleton instances with `_running` flags, cache dicts with `CachedValue.is_expired()`/`is_stale()`, and `get_stats()` methods. The health check service reads these existing states without modification.

The critical architectural constraint is HLTH-04: health state lives entirely in memory with zero SQLite writes. This means the `HealthCheckService` singleton holds a `dict[str, ServiceStatus]` in memory, cached for 5 seconds (HLTH-05). The `CachedValue` class from `binance_public_client.py` is reused for the TTL cache mechanism. The 5-second cache prevents excessive polling from triggering repeated service checks while still providing reasonably fresh data.

**Primary recommendation:** Build a single `HealthCheckService` singleton in `services/health_check_service.py` with 8 parallel async check functions, a `_cached_result` using `CachedValue` with 5s TTL, and a thin `api/routes/health.py` endpoint at `GET /api/health/{user_id}`. Use `asyncio.gather()` with per-check 2s timeouts. The overall status aggregation logic (healthy/degraded/critical) is a pure function that maps the worst individual service status to the three-tier overall.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HLTH-01 | Health Endpoint prueft 8 Kern-Services parallel (Backend, DB, WebSocket, Dry-Run, Alpha Score, Sentiment, Macro, Binance REST) | `asyncio.gather()` with per-check 2s timeout; each check reads existing singleton state (see Architecture Patterns for all 8 check implementations) |
| HLTH-02 | Jeder Service liefert strukturierten Status (ok/stale/degraded/stopped/unavailable/error) mit Timestamps | `ServiceStatus` dataclass with `status: str`, `last_checked: str` (ISO timestamp); status values derived from existing quality badge pattern (`CachedValue.is_expired()`/`is_stale()`) |
| HLTH-03 | Overall-Status aggregiert als healthy/degraded/critical (3-Tier) | Pure function `compute_overall_status(statuses)`: all ok = healthy; any degraded/stale = degraded; any error/unavailable = critical (see Code Examples for exact mapping) |
| HLTH-04 | Health-State lebt ausschliesslich in-memory (kein SQLite-Write, kein Lock-Contention) | `HealthCheckService._cached_result` stored in singleton memory; no `get_db()` dependency in health route; DB check uses a read-only `SELECT 1` via raw connection (never through `get_db()` yield-pattern that auto-commits) |
| HLTH-05 | Health-Response wird 5s gecacht (verhindert excessive Polling-Last) | `CachedValue` from `binance_public_client.py` reused with `timedelta(seconds=5)` TTL; check `is_expired(now)` before re-executing checks |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.128.7 | Async route handler | Already in stack; `async def` + `asyncio.gather()` for parallel checks |
| asyncio (stdlib) | Python 3.x | Parallel execution of 8 checks | `asyncio.gather(*checks, return_exceptions=True)` for non-blocking parallel execution |
| threading (stdlib) | Python 3.x | Thread-safe cache access | `threading.Lock` for `_cached_result` access; matches existing singleton pattern |
| datetime (stdlib) | Python 3.x | Timestamps | `datetime.now(timezone.utc).isoformat()` for `last_checked` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `CachedValue` (existing) | In `binance_public_client.py` | TTL cache for 5s response caching | Reuse for `_cached_result` field on `HealthCheckService` |
| SQLAlchemy | 2.0.46 | DB connectivity check | `SELECT 1` via `engine.connect()` -- read-only, no session/transaction |
| aiohttp | 3.13.3 | (indirect) WebSocket manager dependency | Already imported in `websocket_manager.py` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom health service | `fastapi-health` or `fastapi-healthchecks` | Adds abstraction without benefit for custom singleton state checks; custom is simpler for 8 specific checks that read existing singletons |
| `CachedValue` reuse | `cachetools.TTLCache` | Would add a new dependency; existing `CachedValue` already has `is_expired()` and `is_stale()` methods |
| `SELECT 1` via raw connection | `get_db()` dependency | `get_db()` auto-commits on yield exit, which violates HLTH-04 (zero writes). Raw `engine.connect()` is read-only. |

**Installation:**
```bash
# No new packages required -- all libraries already in requirements.txt
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
├── services/
│   └── health_check_service.py    # NEW: HealthCheckService singleton
├── api/routes/
│   └── health.py                  # NEW: GET /api/health/{user_id}
└── main.py                        # MODIFIED: register health router
```

### Pattern 1: Singleton Service with In-Memory TTL Cache

**What:** `HealthCheckService` follows the identical singleton pattern used by `SentimentDataService`, `MacroDataService`, `AlphaScoreDataService`, `DryRunService`, and `CombinedScoreService`.

**When to use:** When a service needs shared mutable state (the cached health result) accessible from route handlers.

**Implementation pattern (from codebase):**

```python
# Pattern from sentiment_data_service.py (line 479-499), macro_data_service.py (line 628-640)
_service_instance: Optional[HealthCheckService] = None
_service_lock = threading.Lock()

def get_health_check_service() -> HealthCheckService:
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = HealthCheckService()
    return _service_instance
```

### Pattern 2: Parallel Async Checks with asyncio.gather

**What:** Execute all 8 service checks simultaneously with individual timeouts. If any single check hangs, it fails independently without blocking other checks.

**When to use:** When multiple independent I/O-bound operations must complete within a bounded time.

**Implementation:**

```python
async def check_all_services(self) -> dict:
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
    # Map exceptions to error status
    service_names = ["backend", "db", "websocket", "dry_run", "alpha_score", "sentiment", "macro", "binance_rest"]
    statuses = {}
    for name, result in zip(service_names, results):
        if isinstance(result, Exception):
            statuses[name] = ServiceStatus(status="error", last_checked=now_iso)
        else:
            statuses[name] = result
    return statuses
```

### Pattern 3: Read-Only Singleton State Inspection

**What:** Health checks read existing singleton state without modifying it. No API calls, no DB writes, no cache invalidation.

**When to use:** When you need to assess service health without introducing side effects.

**8 service check implementations:**

| Service | What to Check | How to Read | Status Mapping |
|---------|--------------|-------------|----------------|
| **Backend** | FastAPI process alive | Always `ok` (if this code runs, backend is alive) | ok |
| **DB** | SQLite connectivity | `engine.connect()` + `SELECT 1` (raw, no session) | ok = success; error = exception |
| **WebSocket** | `BinanceStreamManager` running + has prices | `get_stream_manager().get_stats()` -- read `running`, `current_prices` | ok = running + has prices; degraded = running but no prices; stopped = not running |
| **Dry-Run** | `DryRunService` loop running | `get_dry_run_service()._running` | ok = running; stopped = not running |
| **Alpha Score** | Cache freshness | `get_alpha_score_data_service()._kline_cache` -- check any `CachedValue.is_expired(now)` | ok = any live cache; stale = all expired but exist; unavailable = empty cache |
| **Sentiment** | Cache freshness + init | `get_sentiment_data_service()._cache` + `_history_initialized` | ok = initialized + live cache; stale = initialized + expired cache; unavailable = not initialized |
| **Macro** | Cache freshness | `get_macro_data_service()._cache` -- check Binance cache entries | ok = live; stale = expired; unavailable = empty |
| **Binance REST** | Public API reachable | `get_binance_public_client().get_ticker_price("BTCEUR")` with 2s timeout | ok = price returned; error = exception |

**Critical: Binance REST is the only check that makes an external API call.** All other checks read in-memory singleton state. The Binance REST check is justified because the Binance Public Client has no internal state to read -- it is a stateless HTTP wrapper. The 2s timeout prevents this single check from blocking the response.

### Pattern 4: Three-Tier Overall Status Aggregation

**What:** Pure function maps individual service statuses to one of three overall tiers.

**Mapping logic:**

```
Status priority (worst-first): error > unavailable > degraded > stale > stopped > ok

Overall mapping:
- critical: ANY service is "error" or "unavailable"
- degraded: ANY service is "degraded", "stale", or "stopped" (but none error/unavailable)
- healthy: ALL services are "ok"
```

### Pattern 5: Route Registration (existing pattern)

**What:** Thin route module with router prefix, registered in `main.py`.

**Matches existing pattern from `macro.py`, `alerts.py`, etc.:**

```python
# api/routes/health.py
router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("/{user_id}")
async def get_health(user_id: str):
    ...

# main.py -- register with api_auth_with_user (same as all {user_id} routes)
app.include_router(health.router, dependencies=api_auth_with_user)
```

### Anti-Patterns to Avoid

- **DB writes in health checks:** Never use `get_db()` yield-pattern which auto-commits. Use `engine.connect()` for read-only `SELECT 1`. Violating this causes SQLite lock contention (single-writer model with NullPool).
- **Calling service compute methods:** Do NOT call `sentiment_service.get_sentiment()` or `macro_service.get_signal()` from health checks. These trigger HTTP requests to external APIs (Binance, OKX, FRED, ECB). Health checks must only READ existing cached state.
- **Using float for timestamps:** All timestamps in this codebase use `datetime` objects or ISO strings. Follow this convention.
- **Adding health events to AlertEventDB:** AlertEventDB is for reconciliation/business alerts (STATE.md: "AlertEventDB is for reconciliation/business alerts -- health events must NOT go there"). Health state is in-memory only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TTL cache | Custom expiry logic | `CachedValue` from `binance_public_client.py` | Already has `is_expired()`, `is_stale()`, used by 4+ services |
| Parallel execution | Sequential check loop | `asyncio.gather(*checks, return_exceptions=True)` | 8 sequential 2s-timeout checks = 16s worst case; parallel = 2s |
| Singleton pattern | Global dict/variable | Double-checked locking pattern (see Pattern 1) | Matches 6+ existing services in this codebase |
| Thread-safe access | `asyncio.Lock` | `threading.Lock` | Service uses `threading.Lock` pattern (see AlphaScoreDataService, SentimentDataService) for compatibility with sync callers from `asyncio.to_thread()` |

**Key insight:** Every pattern needed for the health check service already exists in the codebase. The implementation is a composition of proven patterns, not a novel architecture.

## Common Pitfalls

### Pitfall 1: DB Check Triggers Auto-Commit via get_db()

**What goes wrong:** Using `get_db()` for the `SELECT 1` DB check. The `get_db()` generator in `database.py` (line 51-71) yields a session that auto-commits on normal exit and auto-rollbacks on exception. Even a `SELECT 1` through this pattern would hold a connection and potentially interfere with the session lifecycle.

**Why it happens:** All other routes use `Depends(get_db)`. Natural instinct is to follow the same pattern.

**How to avoid:** Use `engine.connect()` directly for the read-only check. Import `engine` from `app.db.database`, execute `text("SELECT 1")`, close the connection immediately. No session, no transaction, no commit.

**Warning signs:** Health endpoint appearing in SQLite write-ahead log; `SQLITE_BUSY` errors during health polling.

### Pitfall 2: Health Check Calling External APIs

**What goes wrong:** Health checks for Sentiment, Macro, or Alpha Score calling their `get_signal()`/`get_sentiment()`/`get_alpha_score()` methods, which trigger HTTP requests to Binance, OKX, FRED, ECB, etc.

**Why it happens:** Seems logical to "check if the service works" by calling its main method.

**How to avoid:** Health checks must ONLY read existing in-memory state (cache dicts, `_running` flags, `_history_initialized` booleans). The only permitted external call is the Binance REST ticker check (because `BinancePublicClient` is stateless and has no internal state to read).

**Warning signs:** Health endpoint taking >5s to respond; rate limit errors from external APIs; health polling consuming API quota.

### Pitfall 3: Cache Race on First Request

**What goes wrong:** First health request arrives before any service has populated its cache. All cache-based checks return "unavailable" even though services are starting up normally.

**Why it happens:** Lifespan hook initializes services, but cache population happens lazily on first user request (except Sentiment which pre-initializes in lifespan).

**How to avoid:** For the initial state, distinguish "not yet checked" from "checked and found unavailable". A service with empty cache shortly after startup is "starting" not "unavailable". Use a startup grace period (e.g., first 60 seconds after app start, services default to "ok" if their singleton exists and is not explicitly errored).

**Warning signs:** Dashboard shows all services as unavailable immediately after restart, then flips to healthy after first user interaction.

### Pitfall 4: 5-Second Cache Stale During Extended Error

**What goes wrong:** A service goes down. The first check detects "error". Subsequent requests within 5s return the cached "error" result. After 5s, a new check runs and detects "error" again. This is correct behavior but could confuse consumers expecting real-time status.

**Why it happens:** 5-second cache is by design (HLTH-05).

**How to avoid:** Document that the health endpoint reflects state with up to 5s latency. The `last_checked` timestamp on each service status makes the age transparent to consumers.

**Warning signs:** Dashboard showing stale timestamps. This is expected behavior, not a bug.

### Pitfall 5: Thread Safety of Singleton Cache Access

**What goes wrong:** Race condition when multiple concurrent requests read/write `_cached_result` on the `HealthCheckService` singleton.

**Why it happens:** FastAPI runs async handlers concurrently. Multiple requests can trigger cache expiry check + re-check simultaneously.

**How to avoid:** Use `threading.Lock` for `_cached_result` access. Although the route handler is `async def`, the health check reads singleton state from services that use `threading.Lock` (all data services use `threading.Lock`, not `asyncio.Lock`). The pattern is: acquire lock, check if cached result is fresh, release lock, if stale then run checks (outside lock), acquire lock again, store result.

**Warning signs:** Occasionally seeing duplicate check executions within the same 5s window. Minor performance issue, not a correctness issue -- `asyncio.gather` results are idempotent.

## Code Examples

### Service Status Dataclass

```python
from dataclasses import dataclass

@dataclass
class ServiceStatus:
    """Status of a single service."""
    name: str
    status: str  # ok | stale | degraded | stopped | unavailable | error
    last_checked: str  # ISO 8601 timestamp
    detail: str = ""  # Optional human-readable detail
```

### DB Check (Read-Only, No Session)

```python
async def _check_db(self) -> ServiceStatus:
    """Check SQLite connectivity via read-only SELECT 1."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        from app.db.database import engine
        from sqlalchemy import text

        if engine is None:
            return ServiceStatus(
                name="db", status="unavailable",
                last_checked=now_iso, detail="Engine not initialized"
            )

        # Use raw connection -- NOT get_db() which auto-commits
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return ServiceStatus(name="db", status="ok", last_checked=now_iso)
    except Exception as e:
        return ServiceStatus(
            name="db", status="error",
            last_checked=now_iso, detail=str(e)
        )
```

### Cache-Based Service Check (Alpha Score Example)

```python
async def _check_alpha_score(self) -> ServiceStatus:
    """Check AlphaScoreDataService cache freshness."""
    now_iso = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)
    try:
        service = get_alpha_score_data_service()

        # Read cache dict (under service's lock for thread safety)
        with service._lock:
            kline_entries = dict(service._kline_cache)

        if not kline_entries:
            return ServiceStatus(
                name="alpha_score", status="unavailable",
                last_checked=now_iso, detail="No cached data"
            )

        # Check if any entry is still fresh
        any_live = any(not cv.is_expired(now) for cv in kline_entries.values())
        all_stale = all(cv.is_stale(now) for cv in kline_entries.values())

        if any_live:
            return ServiceStatus(name="alpha_score", status="ok", last_checked=now_iso)
        elif all_stale:
            return ServiceStatus(
                name="alpha_score", status="stale",
                last_checked=now_iso, detail="All cache entries stale"
            )
        else:
            return ServiceStatus(
                name="alpha_score", status="degraded",
                last_checked=now_iso, detail="Cache expired but not stale"
            )
    except Exception as e:
        return ServiceStatus(
            name="alpha_score", status="error",
            last_checked=now_iso, detail=str(e)
        )
```

### WebSocket Check

```python
async def _check_websocket(self) -> ServiceStatus:
    """Check BinanceStreamManager state."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        manager = get_stream_manager()
        stats = manager.get_stats()

        if not stats.get("running"):
            return ServiceStatus(
                name="websocket", status="stopped",
                last_checked=now_iso, detail="Stream manager not running"
            )

        if not stats.get("current_prices"):
            return ServiceStatus(
                name="websocket", status="degraded",
                last_checked=now_iso, detail="Running but no prices received"
            )

        return ServiceStatus(name="websocket", status="ok", last_checked=now_iso)
    except Exception as e:
        return ServiceStatus(
            name="websocket", status="error",
            last_checked=now_iso, detail=str(e)
        )
```

### Overall Status Aggregation (Pure Function)

```python
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
```

### 5-Second Response Cache

```python
class HealthCheckService:
    def __init__(self):
        self._lock = threading.Lock()
        self._cached_result: Optional[CachedValue] = None

    async def get_health(self) -> dict:
        now = datetime.now(timezone.utc)

        # Check cache (thread-safe)
        with self._lock:
            if self._cached_result and not self._cached_result.is_expired(now):
                return self._cached_result.value

        # Cache expired or missing -- run checks
        result = await self._run_all_checks()

        # Store in cache
        with self._lock:
            self._cached_result = CachedValue(
                result, now, timedelta(seconds=5)
            )

        return result
```

### Health Route (Thin HTTP Layer)

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("/{user_id}")
async def get_health(user_id: str):
    """
    Health Check: Returns structured status for all 8 core services.

    Response cached for 5 seconds to prevent excessive polling.
    """
    service = get_health_check_service()
    result = await service.get_health()

    response = JSONResponse(content=result)
    response.headers["Cache-Control"] = "no-store"
    return response
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Always-healthy stub (`/health`) | Per-service structured checks | Phase 19 (now) | Enables meaningful monitoring; existing `/health` returns `{"status": "healthy"}` unconditionally |
| Health libraries (fastapi-health) | Custom singleton with `asyncio.gather` | 2024-2025 pattern shift | Libraries add abstraction for simple checks; custom is cleaner for singleton state reading |
| Sequential health checks | `asyncio.gather` parallel | Standard since Python 3.7+ | 8 checks in 2s instead of 16s |

**Deprecated/outdated:**
- The existing `/health` endpoint at `main.py` line 148-151 always returns `{"status": "healthy"}`. This must be kept for backward compatibility (any monitoring that pings it) but the new `GET /api/health/{user_id}` is the structured replacement.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | None (defaults, `conftest.py` for Binance test keys) |
| Quick run command | `cd backend && python -m pytest tests/test_health_check.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -x` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HLTH-01 | 8 services checked in parallel | unit | `pytest tests/test_health_check.py::test_check_all_8_services -x` | Wave 0 |
| HLTH-01 | Each of 8 services returns a status | unit | `pytest tests/test_health_check.py::test_each_service_returns_status -x` | Wave 0 |
| HLTH-02 | Status values from {ok,stale,degraded,stopped,unavailable,error} | unit | `pytest tests/test_health_check.py::test_status_values_valid -x` | Wave 0 |
| HLTH-02 | Each service includes last_checked timestamp | unit | `pytest tests/test_health_check.py::test_last_checked_timestamp -x` | Wave 0 |
| HLTH-03 | Overall status: all ok -> healthy | unit | `pytest tests/test_health_check.py::test_overall_healthy -x` | Wave 0 |
| HLTH-03 | Overall status: degraded service -> degraded | unit | `pytest tests/test_health_check.py::test_overall_degraded -x` | Wave 0 |
| HLTH-03 | Overall status: error service -> critical | unit | `pytest tests/test_health_check.py::test_overall_critical -x` | Wave 0 |
| HLTH-04 | No DB writes during health check | unit | `pytest tests/test_health_check.py::test_no_db_writes -x` | Wave 0 |
| HLTH-05 | Cached result returned within 5s | unit | `pytest tests/test_health_check.py::test_5s_cache -x` | Wave 0 |
| HLTH-05 | Cache expires after 5s | unit | `pytest tests/test_health_check.py::test_cache_expiry -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_health_check.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_health_check.py` -- covers HLTH-01 through HLTH-05 (10 tests)
- No new framework install needed (pytest + pytest-asyncio already in requirements.txt)
- No new conftest fixtures needed (tests mock service singletons, don't need Binance keys)

## Open Questions

1. **Binance REST check frequency under 5s cache**
   - What we know: The Binance REST check (`get_ticker_price`) is the only check making an external API call. With 5s cache, it runs at most once every 5 seconds.
   - What's unclear: Whether this adds meaningful load to the Binance API quota (public endpoints have generous limits: 1200 weight/minute, ticker/price costs 2 weight).
   - Recommendation: Proceed as designed. 12 weight/minute (at maximum polling rate of 1 request per 5s) is negligible compared to the 1200 weight/minute limit.

2. **Startup grace period duration**
   - What we know: After app restart, services populate caches lazily. Sentiment pre-initializes in lifespan (takes ~5-10s), others populate on first user request.
   - What's unclear: Exact time between lifespan start and first cache population for non-Sentiment services. Could be seconds or minutes depending on user activity.
   - Recommendation: No grace period in v3.1. Report actual state honestly. "Unavailable" on first check after restart is accurate and informative. Phase 22 (Status Dashboard) can show a "just restarted" notice based on the Backend uptime field.

3. **Per-check timeout vs. overall timeout**
   - What we know: `asyncio.gather` runs checks in parallel. Individual check timeout (2s) vs. overall timeout (none) are independent.
   - What's unclear: Whether a single hung check (e.g., Binance REST during network outage) could cause `asyncio.gather` to wait indefinitely.
   - Recommendation: Wrap the Binance REST check (the only network-bound check) with `asyncio.wait_for(check, timeout=2.0)` and catch `asyncio.TimeoutError` as "error" status. All other checks are in-memory reads and complete near-instantly.

## Sources

### Primary (HIGH confidence)
- `backend/app/services/sentiment_data_service.py` -- Singleton + `CachedValue` + `_cache` dict + `_history_initialized` flag + quality badges pattern
- `backend/app/services/alpha_score_data_service.py` -- Singleton + `_lock` + `_kline_cache` / `_depth_cache` / `_funding_cache` with `CachedValue` entries
- `backend/app/services/macro_data_service.py` -- Singleton + `_cache` dict + `_get_quality()` / `_get_quality_prefix()` methods
- `backend/app/services/websocket_manager.py` -- `BinanceStreamManager` singleton + `get_stats()` method (returns `running`, `current_prices`, etc.)
- `backend/app/services/dry_run_service.py` -- `DryRunService` singleton + `_running` flag + `_task` field
- `backend/app/services/binance_public_client.py` -- `CachedValue` class (reusable), `BinancePublicClient` singleton (stateless)
- `backend/app/services/binance.py` -- `BinanceService` (not a singleton; instantiated per-request scope)
- `backend/app/db/database.py` -- `engine` global, `get_db()` yield-pattern (auto-commit), `NullPool` for SQLite
- `backend/app/main.py` -- Lifespan hook, router registration pattern, existing `/health` stub (line 148-151)
- `backend/app/api/auth.py` -- `api_auth_with_user` dependency pattern
- `backend/app/api/routes/alerts.py` -- `AlertEventDB` structure (health events must NOT use this)
- `backend/app/api/routes/macro.py` -- Thin route pattern (singleton access, serialize, return)
- `.planning/STATE.md` -- Key context: current `/health` stub always returns healthy; AlertEventDB for business alerts only; SQLite single-writer model

### Secondary (MEDIUM confidence)
- FastAPI async route handling with `asyncio.gather` -- standard Python async pattern, well-documented
- SQLite NullPool behavior under concurrent read access -- based on SQLAlchemy docs + codebase NullPool configuration

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies; all patterns already in codebase
- Architecture: HIGH -- direct inspection of all 8 service singletons confirmed readable state; `CachedValue` pattern verified
- Pitfalls: HIGH -- DB auto-commit pattern (get_db yield), AlertEventDB separation, and singleton threading model all verified from source code
- Test mapping: HIGH -- pytest + pytest-asyncio already in requirements; test structure follows existing convention

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable domain; no external dependencies to drift)
