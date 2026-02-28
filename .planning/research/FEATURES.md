# Feature Research

**Domain:** Trading App Hardening + Monitoring (Health-Check System, Status Dashboard, Telegram Notifications, WebSocket Recovery)
**Researched:** 2026-02-28
**Confidence:** HIGH

---

## Context: Existing System (v3.1 Milestone)

This is a SUBSEQUENT MILESTONE — not greenfield. The existing app already ships:
- Alert system: `AlertEventDB`, `AlertBanner` with 30s polling, dismiss/bulk-dismiss
- WebSocket: `WebSocketContext.jsx` with `scheduleReconnect()` using exponential backoff (1s → 30s), heartbeat every 30s, `pong` handling, auth-error guard (code 4001 = no reconnect)
- Health stub: `GET /health` returns `{"status": "healthy"}` — no dependency checks whatsoever
- WebSocket stats: `GET /api/websocket/stats` — returns stream manager connection stats

The WebSocket reconnect logic already EXISTS in `WebSocketContext.jsx` and works correctly. The missing piece is UI visibility of the reconnect state (attempt count, reconnecting indicator). The health check endpoint is a stub — it passes all dependency failures silently. The Telegram notification system does not exist yet.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features required for the "app can run unattended" goal stated in PROJECT.md v3.1.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Health endpoint with dependency checks** | `/health` stub returns healthy even when DB or Binance is down — meaningless in production; any monitoring system expects real dependency validation | LOW | Parallel `asyncio.gather()` checks for DB, Binance REST, WebSocket stream state, Dry-Run loop, Alpha Score, Sentiment, Macro; 5s timeout per check; return HTTP 200 (all healthy) or 503 (any degraded) |
| **Per-service status response payload** | Status Dashboard and Telegram need to know WHICH service failed, not just "something is wrong" | LOW | `{"status": "degraded", "services": {"db": {"status": "healthy"}, "binance_rest": {"status": "timeout", "error": "..."}}, "checked_at": "..."}` — structured, parseable, no stack traces |
| **Status Dashboard in Admin area** | Trading app running unattended must surface service health at a glance without SSH access | MEDIUM | React component in existing Admin nav group; polls `GET /api/health` every 30s via TanStack Query; color-coded service cards (green/yellow/red); shows service name, status badge, last-check time |
| **Freshness indicators per service** | "Connected" is insufficient — data could be stale even with a live connection (Binance stops sending tickers but socket stays open) | MEDIUM | Backend tracks `last_successful_at` per service in health response; frontend shows relative timestamps ("3m ago"); stale thresholds: 90s for price stream, 10min for Alpha/Sentiment, 30min for Macro |
| **Telegram: service DOWN notification** | Service down at 3am — silent failure means missed signals and data gaps; operator cannot monitor dashboard while sleeping | MEDIUM | `httpx.AsyncClient.post()` to `api.telegram.org/bot{token}/sendMessage`; configured via `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars; triggered by health status transition healthy → degraded |
| **Telegram: service RECOVERY notification** | Without recovery notification, operator doesn't know when the incident resolved and keeps investigating | LOW | Triggered by health status transition degraded → healthy per service; one message per recovery event |
| **Alert deduplication / cooldown** | Without cooldown, a flapping DB connection sends one Telegram message per 30s health poll = 120 messages/hour; Telegram rate-limits at 30 msg/min burst, 20 msg/min sustained per chat | MEDIUM | In-memory `dict[service_name, datetime]` on `TelegramNotifier` singleton; 10-minute cooldown between repeat DOWN alerts for the same service; cooldown does NOT apply to RECOVERY alerts |
| **WebSocket reconnect state visible in UI** | Current implementation reconnects silently — user sees a broken connection indicator but has no way to know if recovery is in progress or stuck | LOW | The reconnect logic already works in `WebSocketContext.jsx`. Add `reconnecting` boolean state + `reconnectAttempts` count to context value; display in the existing connection status indicator in nav |

### Differentiators (Competitive Advantage)

Features that go beyond minimum viable monitoring.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Liveness vs. readiness distinction** | Process managers and uptime checkers need a fast "is the process alive" check without dependency overhead; Status Dashboard needs the full readiness check | LOW | `GET /health/live` — returns 200 immediately, no deps (liveness); `GET /health/ready` — full dependency check (readiness); rename existing `GET /health` to `GET /health/ready`, add `/health/live`; both unauthenticated |
| **WebSocket price stream last-message age** | Price stream could be connected (socket open) but Binance stopped sending ticker data — alive-looking but data-dead | MEDIUM | Backend: add `_last_price_message_at` dict per symbol to `BinanceStreamManager`; update on every price broadcast; expose in health response; stale = age > 90s (Binance sends tickers every ~1s in normal operation) |
| **Dry-Run loop health with timestamp** | Dry-run service runs an asyncio evaluation loop — if it hangs or crashes mid-iteration, it fails silently with no error logged | MEDIUM | `DryRunService` exposes `last_loop_completed_at` timestamp; health check computes expected next loop time from interval (`last_loop + interval_seconds`); stale = `now > expected_next + grace_period` |
| **Exponential backoff with jitter** | Existing reconnect has no jitter — if two browser tabs are open, they both retry at identical intervals and hit the backend simultaneously | LOW | Add `Math.random() * 500` to `scheduleReconnect()` delay; already structured for this one-liner addition in `WebSocketContext.jsx` |
| **Telegram Markdown formatting** | Plain text alerts are harder to scan; Telegram supports MarkdownV2 for bold, code blocks, and structured layout | LOW | `parse_mode=MarkdownV2` with escaped special chars; bold service names, code-formatted timestamps; skip if formatting adds significant escaping complexity |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Full `python-telegram-bot` library** | Richer bot API, incoming command handling, polling/webhook | 100+ MB dependency, async threading overhead, webhook infrastructure needed — all for one-way push notifications | Plain `httpx.AsyncClient.post()` to Telegram Bot API; httpx is already a project dependency (used in `binance_public_client.py`); one-way notification = 10 lines of code, zero new dependencies |
| **Public status page** | "Transparency" for users | This is a single-user personal trading app — there are no other users to communicate status to; public status pages add auth bypass complexity for public access | Private Status Dashboard inside the existing authenticated Admin nav group |
| **Persistent health history in DB** | Trend analysis, uptime percentage over time | DB writes every 30s = 2880 writes/day for a personal SQLite app; SQLite is not a time-series DB; no consumer for historical health data in current scope | In-memory last-N-checks ring buffer (last 10 results per service) on backend singleton; expose via response if needed; zero DB writes |
| **Per-user health checks** | Follows existing `/{user_id}/` routing pattern | Health is system-wide — DB connectivity and Binance REST reachability are identical regardless of user; per-user routing implies per-user health state which does not exist | Single `/api/health` (or `/health`) without user scoping; existing `/api/websocket/stats` already follows this unauthenticated pattern |
| **WebSocket-pushed health status** | Real-time health status without polling | WebSocket is one of the services being monitored — if the WS connection is down (the very thing the health check should detect), the push also fails; circular failure mode | HTTP polling from Frontend every 30s — same pattern as `AlertBanner`; simple, reliable, not dependent on the monitored service |
| **Email notifications** | Traditional ops alerting channel | Requires SMTP server configuration, TLS certificates, email templating; Telegram is instant, free, reliable, and already the stated requirement in PROJECT.md | Telegram only for this milestone; email can be added later as a secondary channel if needed |
| **Kubernetes-style probe behavior** | Standard DevOps practice — readiness/liveness probes with specific response formats | App runs as a single uvicorn process on a local/VPS machine, not in Kubernetes; K8s-specific behavior adds complexity (probe annotations, rollout behavior) with no infrastructure benefit | Same endpoints with same HTTP semantics; just don't enforce K8s-specific probe labels or response format expectations |

---

## Feature Dependencies

```
[Health endpoint with dependency checks]
    └──requires──> [Per-service status response payload]
    │
[Telegram: service DOWN]
    └──requires──> [Health endpoint with dependency checks]
    └──requires──> [Alert deduplication / cooldown]
    │
[Telegram: service RECOVERY]
    └──requires──> [Health endpoint with dependency checks]
    └──shares-state-with──> [Alert deduplication / cooldown]
    │
[Status Dashboard (Admin)]
    └──requires──> [Health endpoint with dependency checks]
    └──enhances-with──> [Freshness indicators per service]
    │
[WebSocket reconnect state in UI]
    └──enhances──> [WebSocket reconnect (already exists in WebSocketContext.jsx)]
    │
[WebSocket price stream last-message age]
    └──enhances──> [Health endpoint with dependency checks]
    └──requires──> [BinanceStreamManager: add last_price_message_at tracking]
    │
[Dry-Run loop health]
    └──enhances──> [Health endpoint with dependency checks]
    └──requires──> [DryRunService: expose last_loop_completed_at]
    │
[Liveness vs. readiness distinction]
    └──enhances──> [Health endpoint with dependency checks]
    └──refactors──> [existing GET /health stub]
```

### Dependency Notes

- **Health endpoint is the foundation:** Everything else — Telegram notifications, Status Dashboard, freshness checks — depends on the structured health response. Build this first.
- **Telegram requires alert deduplication:** Ship these together. A Telegram notifier without cooldown will create alert storms the first time any service has instability.
- **WebSocket reconnect UI is independent:** Does not require health endpoint or Telegram. It only reads state from the existing `WebSocketContext.jsx`. Can be done in any phase.
- **Freshness indicators depend on backend tracking timestamps:** The `BinanceStreamManager` must expose `last_price_message_at` before the Status Dashboard can show stream freshness. Backend change first.
- **Dry-Run loop health is additive:** Requires `DryRunService.last_loop_completed_at` which does not exist yet. Add after basic health checks are working.

---

## MVP Definition

### Launch With (v3.1 Milestone)

Minimum viable scope for "app can run unattended without babysitting."

- [ ] **Health endpoint with dependency checks** — Foundation for everything else; 8 services, parallel checks, structured JSON response
- [ ] **Per-service status response payload** — Required for granular dashboard and meaningful Telegram messages
- [ ] **Status Dashboard (Admin area)** — Primary deliverable; makes health visible at a glance
- [ ] **Telegram: service DOWN notification** — Core out-of-band alerting; prevents silent failures overnight
- [ ] **Telegram: service RECOVERY notification** — Without this, operator keeps investigating resolved incidents
- [ ] **Alert deduplication / cooldown** — Must ship with Telegram; prevents alert storms and Telegram rate-limit errors
- [ ] **WebSocket reconnect state visible in UI** — Minimal change to existing context; high user value, low effort

### Add After Validation (v3.1.x)

- [ ] **Liveness vs. readiness distinction** — Add `/health/live` once `/health/ready` is stable and operators have a use case for the cheap liveness check
- [ ] **WebSocket price stream last-message age** — Catches silent stream staleness; add once basic health checks are solid
- [ ] **Dry-Run loop health** — Requires `DryRunService` modification; add after baseline health infrastructure is proven

### Future Consideration (v3.2+)

- [ ] **Exponential backoff jitter** — Low urgency; existing reconnect is functionally correct; jitter only matters with multiple simultaneous browser tabs
- [ ] **Telegram Markdown formatting** — Quality-of-life improvement to alerts; functional plain text works in v3.1

---

## What Each Service Actually Needs Checked

The 8 services listed in PROJECT.md require different health-check strategies:

| Service | Check Method | Healthy Signal | Stale/Degraded Threshold |
|---------|--------------|----------------|--------------------------|
| **Backend (FastAPI process)** | Liveness only — endpoint responds | HTTP 200 from `/health/live` | N/A — binary up/down |
| **Database (SQLite)** | `db.execute(text("SELECT 1"))` via SQLAlchemy, 3s timeout | Query succeeds without exception | N/A — transactional, not time-based |
| **Binance REST API** | `GET /api/v3/ping` or `GET /api/v3/time` via `BinancePublicClient`, 5s timeout | HTTP 200 within timeout | N/A — live ping |
| **WebSocket stream (Binance price)** | `BinanceStreamManager._running` flag + `last_price_message_at` age | `_running == True` AND age < 90s | Age > 90s = stale (Binance sends tickers every ~1s normally) |
| **WebSocket (Frontend connections)** | `len(price_subscribers) > 0` from stream manager | At least one subscriber connected; `_running == True` | N/A — informational, not blocking |
| **Dry-Run service** | `DryRunService.last_loop_completed_at` timestamp | Age < `interval_seconds * 2` | Depends on configured interval (300s → stale at 600s) |
| **Alpha Score service** | `AlphaScoreDataService` — cache freshness or `initialized` flag | Cache populated and not stale | 10 minutes (configurable) |
| **Sentiment service** | `SentimentDataService.initialized` flag + deque population | `initialized == True` + history populated | 30 minutes (F&G TTL) |
| **Macro service** | Last klines fetch timestamp (macro data service cache) | Klines fetched within macro_signal_interval | 60 minutes |

---

## Implementation Notes (Opinionated Guidance)

### Backend: Health Check Endpoint

Use `asyncio.gather(*checks, return_exceptions=True)` — do NOT check services sequentially. Eight sequential 5s timeouts = 40s health check. Parallel = 5s maximum.

The `/health` and `/health/live` routes must NOT use `api_auth_with_user` dependency — they need to be reachable by external uptime monitors. The existing `/api/websocket/stats` already uses only `api_auth` (no user scoping). Use the same pattern for `/api/health/ready` with `api_auth` (or no auth for liveness).

Response structure (example):
```json
{
  "status": "degraded",
  "services": {
    "database": {"status": "healthy", "last_checked": "2026-02-28T03:00:00Z"},
    "binance_rest": {"status": "timeout", "last_checked": "2026-02-28T03:00:00Z", "error": "Connection timeout"},
    "price_stream": {"status": "stale", "last_price_age_seconds": 120}
  },
  "checked_at": "2026-02-28T03:00:00Z"
}
```

Never include stack traces, exception messages with internal paths, or database error strings in the health response — follow the existing error sanitization convention.

### Backend: Telegram Notification

Use `httpx.AsyncClient` (already a project dependency via `binance_public_client.py`) — zero new dependencies.

```python
async def send_telegram(message: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"chat_id": CHAT_ID, "text": message})
    return resp.status_code == 200
```

Cooldown state lives on a `TelegramNotifier` singleton as `dict[str, datetime]` (service_name → last_alert_sent_at). Thread-safe enough for asyncio single-event-loop use (no threading needed).

The health check loop runs every N seconds (configurable, default 60s — faster than the 30s Frontend poll to catch issues before the user notices). State transitions: `last_known_state: dict[str, str]` compares previous vs current status per service and fires Telegram only on change.

### Frontend: Status Dashboard

React component in the `Admin` nav group. TanStack Query with:
- `queryKey: ['health']`
- `refetchInterval: 30_000`
- `staleTime: 25_000`
- `retry: 1` (health endpoint should respond quickly; excessive retries mask real failures)

Service cards with color coding: green = `status == "healthy"`, yellow = `status == "stale"`, red = `status == "unhealthy"` or `status == "timeout"`. Show service name, status badge, timestamp ("3m ago" via relative formatting using existing `formatters.js`).

No global state needed — this is an isolated admin feature with its own polling.

### Frontend: WebSocket Reconnect State

The reconnect logic in `WebSocketContext.jsx` already works correctly. The change is additive:

```javascript
// In WebSocketContext.jsx — new state
const [reconnecting, setReconnecting] = useState(false);

// In scheduleReconnect():
setReconnecting(true);   // add this line

// In connect() onopen (after setConnected(true)):
setReconnecting(false);  // add this line

// In context value:
{ connected, reconnecting, ...existing }
```

Then in the connection status indicator (wherever `connected` is displayed — likely `GlobalNav.jsx`): show "Reconnecting... (attempt 3)" when `reconnecting === true` using the existing connection dot indicator.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Health endpoint with dependency checks | HIGH | LOW | P1 |
| Per-service status response payload | HIGH | LOW | P1 |
| Status Dashboard (Admin area) | HIGH | MEDIUM | P1 |
| Telegram: service DOWN | HIGH | MEDIUM | P1 |
| Telegram: service RECOVERY | HIGH | LOW | P1 |
| Alert deduplication / cooldown | HIGH | LOW | P1 |
| WebSocket reconnect state in UI | MEDIUM | LOW | P1 |
| Liveness vs. readiness distinction | MEDIUM | LOW | P2 |
| WebSocket price stream last-message age | MEDIUM | MEDIUM | P2 |
| Dry-Run loop health tracking | MEDIUM | MEDIUM | P2 |
| Exponential backoff jitter | LOW | LOW | P3 |
| Telegram Markdown formatting | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for "unattended operation" milestone goal
- P2: Should have; add once P1 features are proven stable
- P3: Nice to have; defer to v3.2+

---

## Sources

- [FastAPI Health Check Best Practices](https://www.index.dev/blog/how-to-implement-health-check-in-python) — MEDIUM confidence (current, verified patterns)
- [Building a Health-Check Microservice with FastAPI](https://dev.to/lisan_al_gaib/building-a-health-check-microservice-with-fastapi-26jo) — MEDIUM confidence
- [fastapi-health PyPI](https://pypi.org/project/fastapi-health/) — HIGH confidence (official PyPI, considered but not recommended — overhead for simple inline checks)
- [WebSocket Reconnect with Exponential Backoff](https://dev.to/hexshift/robust-websocket-reconnection-strategies-in-javascript-with-exponential-backoff-40n1) — HIGH confidence (matches existing implementation pattern)
- [WebSocket Reconnection Logic 2026](https://oneuptime.com/blog/post/2026-01-24-websocket-reconnection-logic/view) — MEDIUM confidence (current year)
- [Telegram Bot for Service Uptime Monitoring (HackerNoon)](https://hackernoon.com/how-to-create-a-telegram-bot-for-monitoring-your-service-uptime-in-python-part-23-alerting) — MEDIUM confidence (current pattern)
- [python-telegram-bot Flood Limits (official wiki)](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Avoiding-flood-limits) — HIGH confidence (authoritative source on Telegram rate limits)
- [Alert Deduplication Patterns](https://oneuptime.com/blog/post/2026-01-30-alert-deduplication/view) — MEDIUM confidence (current)
- [WebSocket Heartbeat / Keepalive (websockets official docs)](https://websockets.readthedocs.io/en/stable/topics/keepalive.html) — HIGH confidence (official)
- Existing codebase `/Users/ikoerber/AIProjects/cashmgnt/frontend/src/contexts/WebSocketContext.jsx` — HIGH confidence (direct inspection)
- Existing codebase `/Users/ikoerber/AIProjects/cashmgnt/backend/app/main.py` — HIGH confidence (direct inspection, current `/health` stub confirmed)
- Existing codebase `/Users/ikoerber/AIProjects/cashmgnt/backend/app/api/routes/alerts.py` — HIGH confidence (direct inspection, alert pattern reference)
- Existing codebase `/Users/ikoerber/AIProjects/cashmgnt/backend/app/services/websocket_manager.py` — HIGH confidence (direct inspection, `BinanceStreamManager` structure confirmed)

---
*Feature research for: BTC/EUR Trading App — Hardening + Monitoring (v3.1)*
*Researched: 2026-02-28*
