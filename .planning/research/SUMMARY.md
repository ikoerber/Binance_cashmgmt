# Project Research Summary

**Project:** v3.1 Hardening + Monitoring (BTC/EUR Cashflow-Management App)
**Domain:** Trading App Observability — Health-Check Infrastructure, Telegram Alerting, WebSocket Recovery, Status Dashboard
**Researched:** 2026-02-28
**Confidence:** HIGH

## Executive Summary

This is a subsequent milestone on a mature, single-user BTC/EUR Binance Spot trading application. The goal is to make the system safe for unattended overnight operation by adding real observability: a structured health endpoint, a visual status dashboard, out-of-band Telegram notifications, and hardened WebSocket recovery. The existing codebase already ships 80% of the infrastructure needed — the gaps are freshness-aware health checks (the current `/health` stub always returns 200 healthy even when DB or Binance is down), alert deduplication logic for Telegram, and UI visibility of the WebSocket reconnect state.

The recommended approach is additive and surgical. One new dependency (`python-telegram-bot==22.6`) covers Telegram; all other features are pure FastAPI, SQLAlchemy, TanStack Query, and plain CSS already in the stack. Health state must live exclusively in memory — writing health check results to the production SQLite database risks write lock contention that would delay trading writes. Build order is strictly dependency-driven: `TelegramNotifier` first (no deps), then `HealthCheckService` (needs notifier), then the health route (needs service), then the frontend dashboard (needs the route).

The two highest-risk areas are alert design and WebSocket gap recovery. Telegram without an alert state machine produces notification spam during any sustained outage, causing alert fatigue within hours. WebSocket reconnect without a post-reconnect reconciliation trigger means fills that arrive during a disconnect window are silently lost — the Lot stays open in the DB while Binance has closed the order. Both risks have clear mitigations and must be addressed in their respective phases, not deferred.

## Key Findings

### Recommended Stack

The existing stack requires only one addition. `python-telegram-bot==22.6` is the correct choice: it is fully async, requires only `httpx>=0.27,<0.29` (the project already has `httpx==0.28.1`), and its standalone `Bot` class provides exactly what is needed for push-only notifications without the overhead of a full bot framework. All other features — health endpoints, status dashboard, WebSocket recovery — are implemented with libraries already in use.

**Core technologies:**
- `python-telegram-bot==22.6`: Telegram push notifications — only async library with zero dependency conflicts; standalone `Bot` mode, no webhook/polling infrastructure needed; httpx dependency already installed
- FastAPI + `asyncio.gather` (existing): Health endpoint — parallel service checks (8 simultaneous, 2s timeout each = 2s total max); pure FastAPI, no health library needed
- TanStack Query 5.90.20 (existing): Status dashboard polling — `refetchInterval: 30000`, `retry: false`; matches existing AlertBanner pattern, no new frontend dependencies
- plain CSS (existing): Status dashboard UI — color-coded service cards using existing CSS custom property patterns

**What NOT to add:**
- `aiogram`: full bot framework, over-engineered for one-way push notifications
- Prometheus + Grafana: production monitoring stack for a single-machine single-user app
- `fastapi-health` / `fastapi-healthchecks`: adds abstraction without benefit for custom singleton state checks
- Persistent health history in production SQLite: write contention risk, no consumer for the data

### Expected Features

**Must have (table stakes) — v3.1 launch scope:**
- Health endpoint with real dependency checks — current `/health` stub returns healthy even when DB or Binance is unreachable; meaningless for unattended operation
- Per-service structured JSON response — Telegram and dashboard both need to know WHICH service failed, not just "something is wrong"
- Status Dashboard in Admin area — primary deliverable; makes service health visible at a glance without SSH access
- Telegram: service DOWN notification — core out-of-band alerting; prevents silent failures overnight
- Telegram: service RECOVERY notification — without recovery alerts, operator keeps investigating resolved incidents
- Alert deduplication / cooldown — must ship with Telegram; 10-minute cooldown per service for repeat DOWN alerts; prevents alert storms and Telegram rate-limit violations
- WebSocket reconnect state visible in UI — existing reconnect works silently; add `reconnecting` boolean and `reconnectAttempts` count to `WebSocketContext` context value

**Should have — add after v3.1 is stable:**
- Liveness vs. readiness distinction (`/health/live` for process alive check, `/health/ready` for full dependency check)
- WebSocket price stream last-message age (catches silent stream staleness where socket is open but Binance stopped sending tickers)
- Dry-Run loop health with `last_loop_completed_at` timestamp (DryRunService modification required)

**Defer to v3.2+:**
- Exponential backoff jitter (low urgency; only matters with multiple simultaneous browser tabs)
- Telegram Markdown formatting (plain text works; formatting is quality-of-life only)
- Email notifications (Telegram covers the requirement; email adds SMTP configuration overhead)
- Public status page (single-user app; unnecessary complexity)

### Architecture Approach

The v3.1 additions slot cleanly into the existing 3-layer architecture without structural changes. Two new singletons (`HealthCheckService`, `TelegramNotifier`) live in the service layer; a new `health.py` route is a thin HTTP wrapper following the established pattern; `StatusDashboard.jsx` is a standard TanStack Query read-only component added to the Admin nav group. The critical architectural rule is that health state lives entirely in memory — `HealthCheckService._last_status: dict[str, str]` tracks per-service state for transition detection, and no health data is written to the production SQLite database. The health endpoint uses `asyncio.gather()` for parallel checks (8 sequential 5s timeouts = 40s; parallel = 2s maximum with per-check timeouts).

**Major components:**
1. `TelegramNotifier` (NEW, `services/telegram_notifier.py`) — fire-and-forget async Telegram push; no-op if env vars not set; started in FastAPI lifespan hook
2. `HealthCheckService` (NEW, `services/health_check_service.py`) — orchestrates 8 parallel service checks; reads existing singleton state (never modifies); detects state transitions; calls `TelegramNotifier` on change; caches result in memory for 5s
3. `health.py` route (NEW, `api/routes/health.py`) — `GET /api/health/{user_id}`; authenticated with existing `api_auth_with_user`; `Cache-Control: no-store` header
4. `StatusDashboard.jsx` (NEW, `components/StatusDashboard.jsx`) — Admin nav group; `/status` at App.jsx level (not symbol-scoped); polls health endpoint every 30s; color-coded service cards; shows WebSocket `reconnectCount`/`wsError` from context
5. `WebSocketContext.jsx` (MODIFIED) — add `reconnecting` state, `reconnectAttempts` count, `wsError` string to context value; ~15 lines of surgical changes

**Build order (strict dependency chain):**
`TelegramNotifier` → `HealthCheckService` → `health.py` + `main.py` → `WebSocketContext.jsx` (parallelizable) → `StatusDashboard.jsx` → `App.jsx` + `SymbolLayout.jsx` routing → `api/client.js`

### Critical Pitfalls

1. **Health checks returning false-positive "healthy"** — the existing `BinanceStreamManager._running == True` flag says nothing about data freshness; a price received 20 minutes ago looks identical to one from 2 seconds ago. Add `last_price_received_at` tracking to stream stats; health is DEGRADED if age > 90s. For Sentiment/Macro/Alpha services, read their existing TTL cache quality state (the quality badge pattern already exists in `SentimentDataService`). Prevention: define what "healthy" means for each service before writing any endpoint code.

2. **Telegram alert spam causing alert fatigue** — a 1-hour Binance outage with 30s polling generates 120 messages without deduplication. Implement the alert state machine first: `HealthCheckService._last_status` dict fires `TelegramNotifier` only when a service STATUS CHANGES (healthy → degraded, degraded → ok). 10-minute per-service cooldown on repeat DOWN alerts. This must be designed before the first Telegram call is made — retrofitting cooldown after the bot is live nearly always fails.

3. **Missed fills during WebSocket reconnect gap** — Binance User Data Stream does NOT replay missed events. After every reconnect, immediately trigger `reconciliation_service.run_orders_reconciliation()`. This REST-based check catches fills that arrived during the disconnect window. The reconciliation service already exists; this is a wiring step.

4. **SQLite lock contention from health writes** — never write health check results to the production `cashmgnt.db`. Health state is purely in-memory on `HealthCheckService`. Health endpoint result is cached 5s in memory. This prevents health polling from creating 12+ writes/minute that contend with trading writes under SQLite's single-writer model.

5. **Binance Listen Key silent expiry** — Binance does NOT send a disconnect event when a Listen Key expires; the stream connection stays open but silently stops receiving events (documented: no `listenKeyExpired` event for Spot stream). The current 30-minute keepalive ping is necessary but insufficient. Add `last_user_data_message_at` tracking; health is DEGRADED if age > 90s. If keepalive `_ws_api_request` returns `None` (failure), schedule immediate reconnect — do not wait for the next interval.

6. **Two competing notification systems** — health monitoring events (SERVICE_DOWN) must NOT appear in the frontend `AlertBanner`, which was designed for reconciliation alerts (1-2/day). If health alerts accumulate in `AlertEventDB`, the AlertBanner fills with operational noise and users stop dismissing it. Solution: keep health state in-memory only (Status Dashboard + Telegram); preserve `AlertEventDB` exclusively for reconciliation/business alerts.

## Implications for Roadmap

Based on the dependency ordering identified in ARCHITECTURE.md and the pitfall-to-phase mapping in PITFALLS.md, the following phase structure is recommended:

### Phase 1: Health Check Foundation
**Rationale:** Everything else — Telegram, Status Dashboard, WebSocket recovery metrics — depends on a structured health response. Building Telegram or the dashboard before the health endpoint forces retrofitting. The SQLite write-contention pitfall must also be decided at design time (in-memory state architecture), not added later.
**Delivers:** `HealthCheckService` singleton with 8 parallel service checks; `GET /api/health/{user_id}` endpoint; in-memory health state with 5s cache; structured JSON response with per-service status (ok/stale/degraded/stopped/unavailable/error); three-tier overall (healthy/degraded/critical); `Cache-Control: no-store` header; zero production DB writes
**Addresses:** Health endpoint with dependency checks, per-service status payload
**Avoids:** False-positive healthy status; SQLite lock contention; blocking event loop (asyncio.gather + 2s per-check timeouts)

### Phase 2: Telegram Notifications
**Rationale:** Alert deduplication must be designed before the first Telegram call is made. Phase 1 provides the health state machine that Telegram transitions react to. Alert routing strategy (operational vs. business alerts) must be decided here to prevent the dual-notification-system pitfall from being baked in.
**Delivers:** `TelegramNotifier` service class; lifespan start/stop in `main.py`; state-transition-only notification logic in `HealthCheckService`; 10-minute per-service cooldown; graceful no-op when env vars not set; alert routing that excludes health events from `AlertBanner`/`AlertEventDB`; `.env.example` additions (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
**Uses:** `python-telegram-bot==22.6` (one new dependency), existing lifespan hook pattern from `DryRunService`
**Addresses:** Telegram DOWN/RECOVERY notifications, alert deduplication/cooldown
**Avoids:** Alert spam (state machine); alert fatigue; dual notification systems; Telegram per-chat rate limit violations (layer 167 enforcement since Feb 2025)

### Phase 3: WebSocket Recovery + Listen Key Hardening
**Rationale:** The WebSocket reconnect logic already exists and works — this phase makes it resilient against two silent-failure scenarios (fill gaps during reconnect, Listen Key silent expiry). Post-reconnect reconciliation trigger is the most important deliverable: "reconnect working" without fill gap handling is incomplete.
**Delivers:** Post-reconnect reconciliation trigger in `BinanceStreamManager`; `last_user_data_message_at` tracking; health DEGRADED if user data stream age > 90s; keepalive failure (`_ws_api_request` returns `None`) → immediate reconnect; `WebSocketContext.jsx` enhancement — `reconnecting` state, `reconnectAttempts` count, `wsError` exposed in context value; reconnect counter in health endpoint
**Addresses:** WebSocket reconnect state in UI, WebSocket price stream last-message age, Listen Key silent expiry
**Avoids:** Missed fills during disconnect gap; silent stream death after Listen Key expiry; false reconnect-count inflation on intentional server restart

### Phase 4: Status Dashboard
**Rationale:** Frontend-only phase that consumes the infrastructure built in Phases 1-3. Scheduled last because it has no backend deliverables of its own — it depends on all prior phases. No novel patterns required.
**Delivers:** `StatusDashboard.jsx` + `StatusDashboard.css`; Admin nav "Status" link in `SymbolLayout.jsx`; `/status` route in `App.jsx` (global, not symbol-scoped); `getHealth` in `api/client.js`; per-service status cards (green/amber/red) with last-check timestamps and relative age display; WebSocket reconnect state display consuming `reconnectCount`/`wsError` from `useWebSocket()`; global nav status indicator dot (green/amber/red) linking to full dashboard
**Uses:** TanStack Query (existing), plain CSS (existing), `formatters.js` relative timestamps (existing)
**Addresses:** Status Dashboard, freshness indicators, WebSocket connection state visibility
**Avoids:** Polling every 2-3s (use 30s interval); defaulting to all-green on initial load (show CHECKING state until first response); symbol-scoped routing for a global concern

### Phase Ordering Rationale

- **Health first** because it is the dependency root for everything else. The definition of "healthy" per service must be finalized before building consumers that interpret those status values.
- **Telegram before Status Dashboard** because alert routing strategy must be decided before the dashboard is built; otherwise health events might accidentally get added to `AlertEventDB` and pollute `AlertBanner`.
- **WebSocket recovery in Phase 3** (not Phase 1) because the health endpoint must exist first for reconnect metrics to be surfaced there, and the post-reconnect reconciliation trigger is independent from the health and Telegram work.
- **Status Dashboard last** because it is a pure consumer; building it before the backend infrastructure produces a dashboard with no meaningful data to display and creates re-work.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3:** Binance Listen Key lifecycle has subtle documented behavior (no expiry event for Spot stream; keepalive confirmation via `_ws_api_request` is unverified in current code). Inspect `websocket_manager.py` lines 270-340 carefully before designing the reconnect enhancement. Specifically verify: does the current keepalive path actually read the response, or just send?
- **Phase 2:** Telegram's per-chat rate limits changed in layer 167 (Feb 2025) — the `retry_after` per-chat header behavior should be validated against a test bot before production implementation is finalized to ensure the cooldown strategy is sufficient.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Pure FastAPI + asyncio patterns; health check architecture is well-documented and the existing stack is fully capable. The service singleton pattern with `threading.Lock` and TTL cache is already established in this codebase.
- **Phase 4:** Pure TanStack Query + plain CSS frontend page; identical pattern to `CombinedScore.jsx` and `Orderblock.jsx`. No novel patterns involved.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | One new dependency (`python-telegram-bot==22.6`) verified for compatibility with `httpx==0.28.1` (requires `>=0.27,<0.29`). All other features use existing stack. Zero dependency conflicts. |
| Features | HIGH | Feature scope well-defined from explicit v3.1 goals in PROJECT.md. Anti-features clearly identified with rationale. MVP boundary is explicit. Codebase analysis confirmed existing AlertBanner, WebSocket, and health stub state. |
| Architecture | HIGH | Based on direct codebase analysis of 15+ source files. Component boundaries, build order, and integration points verified against existing code structure. No architectural surprises — every integration point maps to an existing pattern. |
| Pitfalls | HIGH | 6 critical pitfalls identified with specific codebase evidence (file names, line numbers, exact method names). Telegram rate limit behavior verified against official sources. Binance Listen Key expiry behavior confirmed via Binance developer community documentation. |

**Overall confidence:** HIGH

### Gaps to Address

- **`AlphaScoreDataService` health check specifics**: Architecture research references this service but the exact `_cache` dict structure with `CachedValue` TTL needs to be confirmed against the actual source file during Phase 1 planning. If the service structure has changed, the health check implementation may need adjustment.
- **WebSocket reconnect max-attempts cap**: The existing implementation has unbounded retry. Phase 3 adds a cap (research suggests 10). The right cap value should be validated against expected Binance maintenance window behavior — during extended outages, 10 attempts may be too few.
- **Alert category strategy**: Research recommends keeping health alerts out of `AlertEventDB` entirely (in-memory only). If historical health event records become desirable later, a separate `health_events` table or `alert_category` column migration would be needed. Confirm the in-memory-only decision before Phase 2 execution to avoid retrofitting.
- **Listen Key keepalive confirmation**: The current `_keepalive_listen_key` in `websocket_manager.py` calls `_ws_api_request("userDataStream.ping")` with a bare `except Exception` that returns `None` on failure. Whether the keepalive response is actually parsed (confirming success) must be verified before Phase 3 design — this determines whether the proposed "None → immediate reconnect" fix is additive or requires reworking the existing keepalive path.

## Sources

### Primary (HIGH confidence)
- `backend/app/services/websocket_manager.py` — `BinanceStreamManager` structure, `get_stats()`, keepalive interval (30min), `_user_data_stream_loop`, reconnect backoff (5→60s)
- `frontend/src/contexts/WebSocketContext.jsx` — existing reconnect logic (lines 191-201), exponential backoff implementation, `scheduleReconnect()` structure
- `backend/app/main.py` — lifespan hook structure, existing service start/stop pattern, current `/health` stub confirmed always returning `{"status": "healthy"}`
- `backend/app/api/routes/alerts.py` — `AlertEventDB` structure, unacknowledged count query, no existing alert category field
- `backend/app/db/database.py` — `NullPool` SQLite, session pattern, single-writer constraint
- `backend/app/services/sentiment_data_service.py` — TTL cache freshness model, quality badges (live/cached/stale/unavailable) — reuse as health status model
- PyPI `python-telegram-bot==22.6` — `httpx>=0.27,<0.29` requirement confirmed; Python >=3.10 confirmed; async `Bot` class pattern confirmed
- Binance Developer Community — Listen Key expiry: no `listenKeyExpired` event for Spot stream; connection stays open but silent after expiry

### Secondary (MEDIUM confidence)
- FastAPI health check patterns (index.dev, dev.to 2025-2026) — `asyncio.gather()` for parallel checks, three-tier status (healthy/degraded/down), pure implementation over health libraries
- WebSocket reconnection with exponential backoff (DEV Community, oneuptime.com 2026) — jitter pattern (±20%) confirmed as production best practice
- Telegram flood control docs (grammy.dev) — per-chat `retry_after` enforcement since layer 167 (Feb 2025); 30 msg/sec global, per-chat limit enforced
- Alert deduplication patterns (oneuptime.com 2026) — state machine vs. event stream approach

### Tertiary (LOW confidence)
- SQLite WAL mode write contention under concurrent health polling — based on SQLite official docs + inference from NullPool configuration; actual contention threshold not benchmarked for this specific workload pattern

---
*Research completed: 2026-02-28*
*Ready for roadmap: yes*
