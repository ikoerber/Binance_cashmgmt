# Roadmap: BTC/EUR Cashflow-Management

## Milestones

- ✅ **v1.0 XRP Cross-Pair Pairing** — Phases 1-4 (shipped 2026-02-22)
- ✅ **v1.1 API Hardening** — Phases 5-8 (shipped 2026-02-23)
- ✅ **v2.0 Frontend Redesign + EUR-Fokus** — Phases 9-12 (shipped 2026-02-25)
- ✅ **v3.0 Multi-Factor Omni-Bot** — Phases 13-18 (shipped 2026-02-28)
- **v3.1 Hardening + Monitoring** — Phases 19-22 (in progress)

## Phases

<details>
<summary>v1.0 XRP Cross-Pair Pairing (Phases 1-4) — SHIPPED 2026-02-22</summary>

- [x] Phase 1: Sell Allocation Symbol Isolation (1/1 plans) — completed 2026-02-20
- [x] Phase 2: EUR Cost Basis (2/2 plans) — completed 2026-02-20
- [x] Phase 3: Cross-Pair Pairing (3/3 plans) — completed 2026-02-20
- [x] Phase 4: Sell Routing (2/2 plans) — completed 2026-02-22

See: `.planning/milestones/v1.0-ROADMAP.md` for full details

</details>

<details>
<summary>v1.1 API Hardening (Phases 5-8) — SHIPPED 2026-02-23</summary>

- [x] Phase 5: API Resilience (2/2 plans) — completed 2026-02-22
- [x] Phase 6: Sync Reliability (2/2 plans) — completed 2026-02-22
- [x] Phase 7: Proactive Reconciliation (2/2 plans) — completed 2026-02-22
- [x] Phase 8: Alert System + Frontend Observability (3/3 plans) — completed 2026-02-23

See: `.planning/milestones/v1.1-ROADMAP.md` for full details

</details>

<details>
<summary>v2.0 Frontend Redesign + EUR-Fokus (Phases 9-12) — SHIPPED 2026-02-25</summary>

- [x] Phase 9: XRPBTC Removal (3/3 plans) — completed 2026-02-23
- [x] Phase 10: CSS Variable Foundation (3/3 plans) — completed 2026-02-24
- [x] Phase 11: Dark Mode Activation + Charts (4/4 plans) — completed 2026-02-24
- [x] Phase 12: Navigation Restructure + Dashboard (2/2 plans) — completed 2026-02-25

See: `.planning/milestones/v2.0-ROADMAP.md` for full details

</details>

<details>
<summary>v3.0 Multi-Factor Omni-Bot (Phases 13-18) — SHIPPED 2026-02-28</summary>

- [x] Phase 13: XRPBTC Infrastructure (3/3 plans) — completed 2026-02-25
- [x] Phase 14: Multi-Factor Scoring Engine (4/4 plans) — completed 2026-02-26
- [x] Phase 15: Backtesting Engine (4/4 plans) — completed 2026-02-27
- [x] Phase 16: Dry-Run Mode + Bot Dashboard (3/3 plans) — completed 2026-02-27
- [x] Phase 17: Combined Score Integration (2/2 plans) — completed 2026-02-27
- [x] Phase 18: BotDashboard Integration Fixes (1/1 plans) — gap closure, completed 2026-02-28

See: `.planning/milestones/v3.0-ROADMAP.md` for full details

</details>

### v3.1 Hardening + Monitoring (In Progress)

**Milestone Goal:** Die App soll unbeaufsichtigt laufen koennen — Service-Gesundheit auf einen Blick, aktive Benachrichtigungen bei Ausfaellen, automatische WebSocket-Recovery.

- [x] **Phase 19: Health Check Foundation** — Structured health endpoint with 8 parallel service checks, in-memory state, 3-tier overall status (completed 2026-02-28)
- [x] **Phase 20: Telegram Notifications** — Out-of-band alerting on service state transitions, graceful no-op, alert routing separation (completed 2026-02-28)
- [x] **Phase 21: WebSocket Recovery + Listen Key Hardening** — Post-reconnect reconciliation, freshness tracking, keepalive failure handling, frontend reconnect state (completed 2026-02-28)
- [ ] **Phase 22: Status Dashboard** — Admin-area service status cards, timestamps, WebSocket state, global nav indicator

## Phase Details

### Phase 19: Health Check Foundation
**Goal**: Operator can query a single endpoint and instantly know which of the 8 core services are healthy, degraded, or down
**Depends on**: Nothing (dependency root for all v3.1 phases)
**Requirements**: HLTH-01, HLTH-02, HLTH-03, HLTH-04, HLTH-05
**Success Criteria** (what must be TRUE):
  1. GET /api/health/{user_id} returns structured JSON with per-service status for all 8 services (Backend, DB, WebSocket, Dry-Run, Alpha Score, Sentiment, Macro, Binance REST)
  2. Each service entry includes a status value from the set {ok, stale, degraded, stopped, unavailable, error} plus a last_checked timestamp
  3. Response includes an overall_status field aggregated as healthy/degraded/critical based on individual service states
  4. Health state lives entirely in memory — zero writes to production SQLite during health checks
  5. Repeated rapid polling (multiple requests within 5 seconds) returns cached results without re-executing service checks
**Plans**: 2 plans

Plans:
- [ ] 19-01-PLAN.md — TDD: HealthCheckService with 8 parallel checks, in-memory TTL cache, overall status aggregation + 10 tests
- [ ] 19-02-PLAN.md — Health route registration (GET /api/health/{user_id}) + main.py wiring

### Phase 20: Telegram Notifications
**Goal**: Operator receives immediate Telegram messages when a service goes down and does not get spammed during sustained outages
**Depends on**: Phase 19 (needs health state machine for transition detection)
**Requirements**: TELE-01, TELE-02, TELE-03
**Success Criteria** (what must be TRUE):
  1. When a service transitions from healthy to DOWN, a Telegram message arrives within one health-check cycle naming the failed service
  2. When TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured in .env, the app starts and runs without errors — no Telegram calls attempted
  3. Health-related events do NOT appear in the frontend AlertBanner and do NOT create AlertEventDB rows — health alerts route exclusively through Telegram and the Status Dashboard
**Plans**: 2 plans

Plans:
- [ ] 20-01-PLAN.md — TDD: TelegramNotifier service with transition detection, graceful no-op, 9 tests + python-telegram-bot dependency
- [ ] 20-02-PLAN.md — Integration: health check notification hook + main.py lifespan wiring

### Phase 21: WebSocket Recovery + Listen Key Hardening
**Goal**: WebSocket disconnects are recovered automatically without losing fills, and silent Listen Key expiry is detected before it causes data gaps
**Depends on**: Phase 19 (reconnect metrics surface in health endpoint)
**Requirements**: WSRC-01, WSRC-02, WSRC-03, WSRC-04
**Success Criteria** (what must be TRUE):
  1. After a WebSocket reconnect completes, an orders reconciliation runs automatically — fills that arrived during the disconnect gap are recovered into the correct lots
  2. Health endpoint reports DEGRADED for the User Data Stream service when no user data message has been received for more than 90 seconds
  3. When the keepalive ping returns None (failure), a reconnect is triggered immediately instead of waiting for the next keepalive interval
  4. Frontend WebSocketContext exposes reconnecting state, reconnect attempt count, and error string — UI consumers can display connection status
**Plans**: 2 plans

Plans:
- [ ] 21-01-PLAN.md — TDD: Migrate User Data Stream to subscribe.signature, post-reconnect reconciliation, freshness tracking, health check extension + 12 tests
- [ ] 21-02-PLAN.md — Frontend WebSocketContext: expose reconnecting, reconnectAttempts, lastError to context consumers

### Phase 22: Status Dashboard
**Goal**: Operator can see the health of every service at a glance from the Admin area without SSH access or checking logs
**Depends on**: Phase 19, Phase 20, Phase 21 (consumes all prior infrastructure)
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04
**Success Criteria** (what must be TRUE):
  1. StatusDashboard.jsx renders a card for each service with color-coded status (green for ok, amber for degraded/stale, red for error/unavailable/stopped)
  2. Each service card shows the last-check timestamp and a relative age indicator (e.g. "12s ago")
  3. WebSocket reconnect state (current attempt count and error message) is displayed on the dashboard, sourced from WebSocketContext
  4. A status dot in the global navigation (green/amber/red) reflects overall system health and links to the Status Dashboard
**Plans**: 2 plans

Plans:
- [ ] 22-01-PLAN.md — TDD: StatusDashboard.jsx with 8 service cards, relative-age timestamps, WS reconnect panel, API client function, /status route, 10 tests
- [ ] 22-02-PLAN.md — GlobalNav status dot (green/amber/red) with health polling, SymbolLayout admin link, 6 tests

## Progress

**Execution Order:**
Phases execute in numeric order: 19 -> 20 -> 21 -> 22

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-4 | v1.0 | 8/8 | Complete | 2026-02-22 |
| 5-8 | v1.1 | 9/9 | Complete | 2026-02-23 |
| 9-12 | v2.0 | 12/12 | Complete | 2026-02-25 |
| 13-18 | v3.0 | 17/17 | Complete | 2026-02-28 |
| 19. Health Check Foundation | 2/2 | Complete    | 2026-02-28 | - |
| 20. Telegram Notifications | 2/2 | Complete    | 2026-02-28 | - |
| 21. WebSocket Recovery | 2/2 | Complete    | 2026-02-28 | - |
| 22. Status Dashboard | 1/2 | In Progress|  | - |
