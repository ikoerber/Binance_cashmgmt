# Architecture Research: v3.1 Hardening + Monitoring

**Domain:** Health-Check System, Status Dashboard, Telegram Notifications, WebSocket Recovery for existing BTC/EUR Cashflow-Management trading app
**Researched:** 2026-02-28
**Confidence:** HIGH (based on direct codebase analysis of 15+ source files, supplemented with web research on integration patterns)

---

## 1. Existing Architecture (Relevant Parts)

The codebase follows a strict 3-layer architecture. New code for v3.1 must fit within it without breaking existing invariants.

```
API Routes (thin)  -->  Services (DB + External APIs)  -->  Domain (pure, no I/O)
     |                         |                                |
  FastAPI                SQLAlchemy ORM                  Dataclasses + Decimal
  Pydantic               Singletons + TTL Cache          Pure functions only
  Auth deps              asyncio background tasks        No imports from services
```

### Existing singletons to monitor (all in `backend/app/services/`)

| Singleton | Constructor Pattern | Has Status/Health Info |
|-----------|--------------------|-----------------------|
| `BinanceStreamManager` | `get_stream_manager()` | `get_stats()` already returns running, subscriber counts, current_prices |
| `DryRunService` | `get_dry_run_service()` | `_running`, `_task` attributes expose loop state |
| `AlphaScoreDataService` | `get_alpha_score_data_service()` | `_cache` dict with `CachedValue` TTL; `_initialized` flag |
| `SentimentDataService` | `get_sentiment_data_service()` | `_history_initialized` flag; `_cache` dict |
| `MacroDataService` | (imported in routes) | Cache dict |
| `BinancePublicClient` | `get_binance_public_client()` | Wraps requests; no explicit health |
| `BinanceService` | (instantiated per route call) | Auth client; connectivity = call success |

### Existing lifespan hook in `main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_config()
    init_db(database_url)
    create_tables()
    # sentiment init
    # stream_manager.start() + start_user_data_stream()
    # dry_run_svc.start()
    yield
    # dry_run_svc.stop()
    # stream_manager.stop()
```

New services (Telegram notifier) start/stop here following the same pattern.

### Existing WebSocket frontend reconnection (in `WebSocketContext.jsx`)

Already has exponential backoff: `Math.min(1000 * Math.pow(2, attempts), 30000)`. The current implementation is missing:
- Jitter to prevent thundering-herd on server restart
- Maximum retry cap (attempts are unbounded)
- Visibility-based reconnect (reconnect faster when tab regains focus)
- `connected` state is exposed but not surfaced in the Admin UI

### Existing alert system (already in place)

- `AlertEventDB` table + `alerts.py` route (CRUD: list, acknowledge, bulk-acknowledge)
- `AlertBanner.jsx` polls every 30s, displays severity-colored banners with dismiss
- `reconciliation_service.py` creates `AlertEventDB` records on threshold breach

Health-check failures will reuse this same `AlertEventDB` table — no new notification table needed.

---

## 2. New vs. Modified Components

### New Components

| Component | Layer | File | Purpose |
|-----------|-------|------|---------|
| `HealthCheckService` | Service | `services/health_check_service.py` | Orchestrates all 8 service checks; returns structured health dict |
| `TelegramNotifier` | Service | `services/telegram_notifier.py` | Sends Telegram messages via `python-telegram-bot` Bot API; async-compatible |
| `health.py` (route) | API Route | `api/routes/health.py` | `GET /api/health/{user_id}` — returns full health status |
| `StatusDashboard.jsx` | Frontend | `components/StatusDashboard.jsx` | Admin-area status page; polls `/api/health/{user_id}` every 15s |
| `StatusDashboard.css` | Frontend | `components/StatusDashboard.css` | Plain CSS, dark theme, status badge colors |

### Modified Components

| Component | File | Change |
|-----------|------|--------|
| `main.py` | `backend/app/main.py` | Register `health.py` router; start/stop `TelegramNotifier` in lifespan |
| `SymbolLayout.jsx` | `frontend/src/components/SymbolLayout.jsx` | Add "Status" link in Admin subnav group |
| `App.jsx` | `frontend/src/App.jsx` | Add `/status` route pointing to `StatusDashboard` |
| `WebSocketContext.jsx` | `frontend/src/contexts/WebSocketContext.jsx` | Add jitter to backoff, cap retry attempts, expose `reconnectCount` in context value |
| `reconciliation_service.py` | `backend/app/services/reconciliation_service.py` | (optional) Call `TelegramNotifier` on critical reconciliation alerts — or handled in `HealthCheckService` on next poll |

---

## 3. System Overview: v3.1 Additions

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Frontend (React 19)                           │
│                                                                       │
│  GlobalNav → SymbolLayout → AdminGroup → [StatusDashboard (NEW)]     │
│                                                                       │
│  WebSocketContext.jsx (MODIFIED: jitter + retry cap)                 │
│  AlertBanner.jsx (unchanged — reuses existing alert system)          │
└────────────────────┬─────────────────────────────────────────────────┘
                     │ REST polling (15s refetchInterval)
                     │ GET /api/health/{user_id}
┌────────────────────▼─────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                               │
│                                                                       │
│  health.py router (NEW) ← api_auth_with_user dependency              │
│  alerts.py router (unchanged)                                        │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────────┐
│                   Service Layer                                        │
│                                                                       │
│  HealthCheckService (NEW, singleton)                                 │
│    ├── check_db()          → SELECT 1 via SessionLocal               │
│    ├── check_websocket()   → get_stream_manager().get_stats()        │
│    ├── check_dry_run()     → get_dry_run_service()._running          │
│    ├── check_alpha_score() → get_alpha_score_data_service()._cache   │
│    ├── check_sentiment()   → get_sentiment_data_service()._history.. │
│    ├── check_macro()       → get_macro_data_service()._cache         │
│    ├── check_binance_rest()→ BinancePublicClient ping (cache hit ok) │
│    └── check_fastapi()     → always OK if we got here                │
│                                                                       │
│  TelegramNotifier (NEW, singleton)                                   │
│    ├── send_alert(title, body, severity)                             │
│    ├── _bot: telegram.Bot (python-telegram-bot v22)                  │
│    └── _chat_id: str (from .env TELEGRAM_CHAT_ID)                   │
│                                                                       │
│  [Existing singletons unchanged — health checks read their state]    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Flow

### Health Check Request Flow

```
GET /api/health/{user_id}
         |
   health.py route (thin)
         |
   HealthCheckService.get_health_status()
         |  (asyncio.gather for parallel checks)
         |
   ├── check_db()           → try: SessionLocal().execute("SELECT 1") → "ok" / "error"
   ├── check_websocket()    → get_stream_manager().get_stats()["running"] → "ok" / "degraded"
   ├── check_dry_run()      → get_dry_run_service()._running → "ok" / "stopped"
   ├── check_alpha_score()  → cache age check → "ok" / "stale" / "unavailable"
   ├── check_sentiment()    → _history_initialized flag + cache age → "ok" / "stale"
   ├── check_macro()        → cache age check → "ok" / "stale" / "unavailable"
   ├── check_binance_rest() → BinancePublicClient.get_ticker_price("BTCEUR") cached → "ok" / "error"
   └── check_fastapi()      → always "ok"
         |
   Aggregate: "healthy" / "degraded" / "critical"
         |
   If status changed from last check → TelegramNotifier.send_alert()
   If status critical → AlertEventDB.create() [reuses existing alert table]
         |
   Return JSON response to frontend
```

### Telegram Notification Flow

```
HealthCheckService detects service failure
         |
   TelegramNotifier.send_alert(title, body, severity)
         |  (async — does not block health check response)
   asyncio.create_task(bot.send_message(chat_id, text))
         |
   Telegram Bot API (https://api.telegram.org)
         |
   User's Telegram client receives notification
```

Notification conditions (fire once on transition, not every poll):
- Any service transitions from "ok" to "error" / "critical"
- Any service transitions back to "ok" (recovery notification)
- Reconciliation critical alert (existing `reconciliation_service.py` calls notifier)

### WebSocket Recovery (Frontend Enhancement)

```
Current: scheduleReconnect() → Math.min(1000 * 2^attempts, 30000)

Enhanced:
  onclose (not 4001) → scheduleReconnect()
      delay = Math.min(BASE_DELAY * 2^attempts, MAX_DELAY)
      delay += Math.random() * JITTER_MS   // NEW: prevents thundering herd
      attempts = Math.min(attempts + 1, MAX_ATTEMPTS)  // NEW: cap at 10
      if (attempts >= MAX_ATTEMPTS) → stop reconnecting, show persistent error

  document.addEventListener('visibilitychange')  // NEW: fast reconnect on tab focus
      if (document.visibilityState === 'visible' && !connected)
          → reset attempts to 0, connect()

  Context value additions:
      reconnectCount: reconnectAttempts.current  // NEW: for StatusDashboard display
      wsError: string | null  // NEW: "Max reconnect attempts reached"
```

---

## 5. Component Boundaries

### HealthCheckService

**Responsibility:** Read-only introspection of all existing singletons. Returns a structured dict. Does NOT modify any service state. Does NOT call Telegram directly — it delegates to `TelegramNotifier`.

**Critical design rule:** Health checks must be non-blocking and fast. Each check has a 2-second timeout. Failures do not propagate exceptions — they return `{"status": "error", "detail": "..."}`.

**State tracking:** The service maintains `_last_status: dict[str, str]` to detect transitions (ok → error) and avoid duplicate Telegram notifications.

```python
class HealthCheckService:
    def __init__(self):
        self._last_status: dict[str, str] = {}
        self._lock = threading.Lock()

    async def get_health_status(self) -> dict:
        checks = await asyncio.gather(
            self._check_db(),
            self._check_websocket(),
            self._check_dry_run(),
            self._check_alpha_score(),
            self._check_sentiment(),
            self._check_macro(),
            self._check_binance_rest(),
            return_exceptions=True,
        )
        # assemble, detect transitions, fire notifications
        ...
```

### TelegramNotifier

**Responsibility:** Fire-and-forget async Telegram messages. No retry loop (Telegram's Bot API is reliable; failed notifications are logged, not re-queued).

**Isolation:** Never imported by domain modules. Never imported by route modules directly — only by `HealthCheckService` and (optionally) `reconciliation_service.py`.

**Config:** `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` from `.env`. If either is missing, `TelegramNotifier` is a no-op (graceful degradation — no exception raised).

```python
class TelegramNotifier:
    def __init__(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._enabled = bool(token and chat_id)
        if self._enabled:
            from telegram import Bot
            self._bot = Bot(token=token)
            self._chat_id = chat_id

    async def send_alert(self, title: str, body: str, severity: str = "warning"):
        if not self._enabled:
            return
        text = f"[{severity.upper()}] {title}\n{body}"
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
        except Exception:
            logger.exception("Telegram notification failed")
```

### health.py Route

**Responsibility:** Thin HTTP layer. Calls `HealthCheckService.get_health_status()`. Returns structured JSON. Uses `api_auth_with_user` dependency (same as all other routes with `{user_id}`).

**No-cache header:** Health responses should not be cached by browsers (`Cache-Control: no-store`).

**Route:** `GET /api/health/{user_id}` — user-scoped to follow existing IDOR protection pattern, even though health data is not user-specific. This avoids creating a new auth pattern.

### StatusDashboard.jsx

**Responsibility:** Display-only admin panel. Polls `/api/health/{user_id}` every 15 seconds via TanStack Query. Shows per-service status badges, last-check timestamp, and WebSocket connection state from `useWebSocket()`.

**Navigation integration:** Added to the Admin subnav group in `SymbolLayout.jsx`:
```
Admin
├── Status (NEW)         →  /status  (global, not symbol-scoped)
├── Reconciliation
├── Settings
└── API Docs
```

`/status` is NOT symbol-scoped (placed at `/status`, not `/s/:symbol/status`) because health is a global concern. It maps to the global `App.jsx` routing.

---

## 6. Architectural Patterns to Follow

### Pattern: Non-Blocking Health Probe with asyncio.gather

All 8 service checks run in parallel to keep the health endpoint fast (under 2s total response time).

```python
async def _check_db(self) -> dict:
    try:
        await asyncio.wait_for(
            asyncio.to_thread(self._sync_check_db),
            timeout=2.0
        )
        return {"status": "ok"}
    except asyncio.TimeoutError:
        return {"status": "error", "detail": "DB query timeout"}
    except Exception as e:
        return {"status": "error", "detail": "DB unavailable"}

def _sync_check_db(self):
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
```

**Why asyncio.to_thread:** `SessionLocal()` is synchronous (SQLAlchemy with NullPool). Wrapping in `to_thread` prevents blocking the async event loop during the health check.

### Pattern: State-Transition-Only Notifications

Telegram messages fire only on state change, not on every poll. Prevents notification spam during sustained outages.

```python
def _detect_transitions(self, new_statuses: dict) -> list[dict]:
    transitions = []
    with self._lock:
        for service, new_status in new_statuses.items():
            old_status = self._last_status.get(service, "unknown")
            if old_status != new_status:
                transitions.append({
                    "service": service,
                    "from": old_status,
                    "to": new_status,
                })
        self._last_status = new_statuses
    return transitions
```

### Pattern: Graceful Degradation for Optional Config

`TelegramNotifier` checks for config at construction time and becomes a no-op if unconfigured. This means the health system works without Telegram credentials — no test failures, no startup errors.

Same pattern as existing `SentimentDataService` graceful degradation for missing pillars.

### Pattern: Status Check via Existing Singleton State

Health checks do NOT make new external API calls for services that have internal caches. They inspect the cache state instead.

```python
async def _check_alpha_score(self) -> dict:
    svc = get_alpha_score_data_service()
    with svc._lock:
        if not svc._cache:
            return {"status": "unavailable", "detail": "Cache empty (warmup)"}
        # Check freshness of most recently updated cache entry
        ...
        return {"status": "ok", "cache_entries": len(svc._cache)}
```

**Why this approach:** Making a real API call from the health endpoint would add load and could fail for reasons unrelated to service health. Cache inspection is instant and reflects the actual service state from the perspective of consumers.

Exception: `check_binance_rest()` uses `BinancePublicClient.get_ticker_price("BTCEUR")` which itself is cached — so the health check hits the cache first and only makes a real call if the cache has expired. This naturally measures whether Binance REST is reachable.

### Pattern: Frontend Polling with TanStack Query

StatusDashboard uses TanStack Query (matching all other pages) rather than a custom `useEffect` fetch.

```javascript
const { data: health, isLoading } = useQuery({
  queryKey: ['health', userId],
  queryFn: () => getHealth(userId),
  refetchInterval: 15000,
  staleTime: 10000,
  retry: false,  // Don't retry on error — show stale data with error badge
});
```

`retry: false` is intentional: if the backend itself is down, retrying floods a dead server.

---

## 7. Anti-Patterns to Avoid

### Anti-Pattern: Health Check That Makes External API Calls

**What people do:** `GET /health` calls Binance REST, OKX, alternative.me directly to verify connectivity.

**Why it's wrong:** Health endpoint becomes slow (10s+ timeout per external call), adds unnecessary API load, and creates false failures when rate-limited.

**Do this instead:** Inspect the existing TTL-cache state. If the cache has fresh data, the external API was reachable recently. If cache is stale/empty, report degraded — the service will show this naturally without a new call.

### Anti-Pattern: Telegram Notification on Every Poll

**What people do:** Send Telegram message every time a service is detected as unhealthy during a health poll.

**Why it's wrong:** A 15-second poll interval with a 1-hour outage produces 240 Telegram messages. Notification spam causes users to ignore or mute the bot.

**Do this instead:** Track last known state per service in `HealthCheckService._last_status`. Only notify on state transition (ok → error, error → ok).

### Anti-Pattern: Blocking Health Check

**What people do:** `def health():` (sync) with blocking DB calls.

**Why it's wrong:** A slow health check blocks the FastAPI event loop during the request, degrading all concurrent requests. SQLite with NullPool creates a new connection per call, which can be slow.

**Do this instead:** `async def health():` + `asyncio.gather()` for parallel checks, each wrapped in `asyncio.wait_for(..., timeout=2.0)`.

### Anti-Pattern: New Route Auth Pattern for Health

**What people do:** Create an unauthenticated `/health` endpoint that returns detailed service status.

**Why it's wrong:** Detailed service internals (cache state, service versions, DB path) are sensitive. The existing unauthenticated `/health` in `main.py` only returns `{"status": "healthy"}` — sufficient for external monitoring. The new detailed health endpoint must use `api_auth_with_user` like all admin routes.

**Do this instead:** Keep the existing `GET /health` (unauthenticated, returns `{"status": "healthy"}`) for external uptime monitors. Add new `GET /api/health/{user_id}` (authenticated) for detailed status.

### Anti-Pattern: Symbol-Scoped Status Dashboard

**What people do:** Add Status to `/s/:symbol/status` like all other admin pages.

**Why it's wrong:** Health status is global, not symbol-specific. Placing it under SymbolLayout forces the user to select a symbol to see global health — confusing UX.

**Do this instead:** Route `/status` at the App.jsx level (not under SymbolLayout), same as `/settings` and `/backtest`.

### Anti-Pattern: WebSocket Recovery Without Jitter

**What people do:** Simple exponential backoff: `delay = Math.min(BASE * 2^n, MAX)`.

**Why it's wrong:** On server restart, all connected clients reconnect simultaneously at the same backoff intervals, creating a thundering herd that overwhelms the freshly started server.

**Do this instead:** Add random jitter: `delay += Math.random() * 2000` (up to 2s additional randomness). This spreads reconnections across time.

---

## 8. New vs. Modified: Build Order

Build order is driven by dependency direction. Later phases depend on earlier ones.

| Order | Component | Type | Depends On |
|-------|-----------|------|-----------|
| 1 | `TelegramNotifier` (service) | NEW | `.env` config only; no other services |
| 2 | `HealthCheckService` (service) | NEW | All existing singletons (read-only); `TelegramNotifier` |
| 3 | `health.py` (route) | NEW | `HealthCheckService` |
| 4 | `main.py` (lifespan) | MODIFIED | Register health route; start/stop `TelegramNotifier` |
| 5 | Backend `.env.example` | MODIFIED | Add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| 6 | `WebSocketContext.jsx` (jitter + cap) | MODIFIED | No backend deps; pure frontend change |
| 7 | `StatusDashboard.jsx` + `.css` | NEW | `GET /api/health/{user_id}` (Phase 3); `useWebSocket()` |
| 8 | `App.jsx` (add `/status` route) | MODIFIED | `StatusDashboard.jsx` |
| 9 | `SymbolLayout.jsx` (add "Status" nav link) | MODIFIED | `/status` route |
| 10 | `api/client.js` (add `getHealth`) | MODIFIED | `GET /api/health/{user_id}` endpoint |

**Rationale for order:**
- `TelegramNotifier` has no dependencies → build first; safe to ship without wiring
- `HealthCheckService` depends on `TelegramNotifier` but not the other way around
- Health route depends on service → backend completes before frontend
- `WebSocketContext.jsx` changes are pure frontend with no backend dependency → can be parallelized with backend work
- `StatusDashboard` requires the health endpoint to be live; wiring into routing last

---

## 9. Integration Points

### Backend: New Route Integration

`health.py` registers with `api_auth_with_user` dependency (same pattern as `dry_run.py`, `backtest.py`, etc.):

```python
# main.py — add to existing imports and include_router calls
from app.api.routes import health

app.include_router(health.router, dependencies=api_auth_with_user)
```

`TelegramNotifier` starts in lifespan (same pattern as `DryRunService`):

```python
# main.py lifespan — add after dry_run_svc.start()
from app.services.telegram_notifier import get_telegram_notifier
telegram = get_telegram_notifier()
await telegram.start()  # validates config, logs status

yield

await telegram.stop()  # no-op if not enabled
```

### Backend: `.env` + `.env.example` additions

```
# Telegram Bot Notifications (optional — health alerts disabled if not set)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### Frontend: Route addition in `App.jsx`

```jsx
import StatusDashboard from './components/StatusDashboard';

// Inside <Routes>:
<Route path="/status" element={<StatusDashboard />} />
```

### Frontend: Nav link in `SymbolLayout.jsx` Admin group

```jsx
<div className="subnav-group">
  <span className="subnav-group-label">Admin</span>
  <NavLink to="/status">Status</NavLink>   {/* NEW */}
  <NavLink to={`/s/${symbol}/reconciliation`}>Reconciliation</NavLink>
  <NavLink to="/settings">Settings</NavLink>
  <a href="/docs" target="_blank" rel="noopener noreferrer">API Docs</a>
</div>
```

### Frontend: `api/client.js` addition

```javascript
export const getHealth = (userId) =>
  apiClient.get(`/api/health/${userId}`).then(r => r.data);
```

### Frontend: WebSocket context additions

```javascript
// Expose in context value:
const value = {
  // existing...
  connected,
  prices,
  // NEW:
  reconnectCount: reconnectAttempts.current,
  wsError,  // null | "Max attempts reached"
};
```

`StatusDashboard` consumes `reconnectCount` and `wsError` from `useWebSocket()` to show WebSocket connection health without needing a separate API call.

---

## 10. Health Response Schema

The `GET /api/health/{user_id}` endpoint returns:

```json
{
  "overall": "healthy | degraded | critical",
  "checked_at": "2026-02-28T12:00:00Z",
  "services": {
    "fastapi": {
      "status": "ok",
      "detail": null
    },
    "database": {
      "status": "ok | error",
      "detail": null
    },
    "websocket_binance": {
      "status": "ok | degraded | stopped",
      "detail": "running=true, price_subscribers=1, active_tasks=2",
      "current_prices": {"BTCEUR": "85000.00"}
    },
    "dry_run_loop": {
      "status": "ok | stopped",
      "detail": null
    },
    "alpha_score_cache": {
      "status": "ok | stale | unavailable",
      "detail": "cache_entries=3, oldest_age_seconds=42"
    },
    "sentiment_cache": {
      "status": "ok | stale | unavailable",
      "detail": "history_initialized=true, cache_entries=5"
    },
    "macro_cache": {
      "status": "ok | stale | unavailable",
      "detail": null
    },
    "binance_rest": {
      "status": "ok | error",
      "detail": "cached=true, age_seconds=18"
    }
  }
}
```

**Status tiers:**
- `ok` — working normally
- `stale` — cache exists but exceeds TTL (data is old but service ran recently)
- `degraded` — partial function (e.g., WebSocket connected but no price subscribers)
- `stopped` — background task not running (dry_run loop)
- `unavailable` — cache is empty / service never successfully fetched data
- `error` — hard failure (DB unreachable, exception thrown)

**Overall aggregation:**
- `healthy` — all services "ok"
- `degraded` — any service "stale" or "degraded" or "stopped"
- `critical` — any service "error" or "unavailable" for a critical service (DB, FastAPI)

---

## 11. Scalability Considerations

This is a single-user system (one `userId = 'user_123'`). Scaling is not a current concern. However, two design choices future-proof the implementation:

| Decision | Rationale |
|----------|-----------|
| User-scoped health route (`/api/health/{user_id}`) | Consistent with all other routes; trivially extensible to multi-user |
| `HealthCheckService` as singleton with `_last_status` | State isolation per service name; works for N services without redesign |
| `TelegramNotifier` with configurable `TELEGRAM_CHAT_ID` | One chat_id per deployment; multi-user would need per-user mapping (future concern) |

---

## Sources

- FastAPI health check patterns: [fastapi-health on PyPI](https://pypi.org/project/fastapi-health/), [Index.dev health check guide](https://www.index.dev/blog/how-to-implement-health-check-in-python)
- python-telegram-bot v22 Bot API: [Official docs](https://docs.python-telegram-bot.org/en/stable/telegram.bot.html)
- WebSocket reconnection with jitter: [DEV Community — Exponential Backoff](https://dev.to/hexshift/robust-websocket-reconnection-strategies-in-javascript-with-exponential-backoff-40n1), [oneuptime.com reconnection logic](https://oneuptime.com/blog/post/2026-01-24-websocket-reconnection-logic/view)
- Codebase analysis: `backend/app/main.py`, `services/websocket_manager.py`, `services/dry_run_service.py`, `services/alpha_score_data_service.py`, `services/sentiment_data_service.py`, `services/websocket_event_handler.py`, `api/routes/alerts.py`, `frontend/src/contexts/WebSocketContext.jsx`, `frontend/src/components/AlertBanner.jsx`, `frontend/src/components/SymbolLayout.jsx`, `frontend/src/App.jsx`

---

*Architecture research for: v3.1 Hardening + Monitoring (Health-Check, Status Dashboard, Telegram Notifications, WebSocket Recovery)*
*Researched: 2026-02-28*
