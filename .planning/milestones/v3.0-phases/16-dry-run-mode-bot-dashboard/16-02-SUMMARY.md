---
phase: 16-dry-run-mode-bot-dashboard
plan: 02
subsystem: services, api, websocket
tags: [dry-run, paper-trading, asyncio, evaluation-loop, virtual-portfolio, websocket]

# Dependency graph
requires:
  - phase: 16-dry-run-mode-bot-dashboard
    plan: 01
    provides: "Pure domain module (dry_run.py), 3 DB tables, Settings API extension"
  - phase: 14-alpha-score
    provides: "AlphaScoreDataService.get_alpha_score() for real-time signal computation"
provides:
  - "DryRunService singleton with candle-close evaluation loop"
  - "6 API endpoints under /api/dry-run (status, toggle, decisions, detail, reset, portfolio)"
  - "WebSocket broadcast for dry_run_decision, dry_run_status, dry_run_portfolio_update"
  - "Public broadcast_message() method on BinanceStreamManager"
affects: [16-03]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Candle-close boundary alignment via wall-clock sleep calculation", "asyncio.Lock for toggle/evaluation race prevention", "30-day auto-purge in evaluation loop"]

key-files:
  created:
    - backend/app/services/dry_run_service.py
    - backend/app/api/routes/dry_run.py
  modified:
    - backend/app/main.py
    - backend/app/services/websocket_manager.py

key-decisions:
  - "DryRunService uses SessionLocal() for DB operations in evaluation loop (not request-scoped get_db())"
  - "Public broadcast_message() wrapper on BinanceStreamManager for external service access"
  - "Evaluation loop uses minimum interval from all active users (avoids one-task-per-user proliferation)"
  - "Idempotency check queries most recent decision per user+symbol within current interval boundary"

patterns-established:
  - "Wall-clock boundary alignment: sleep = next_boundary - seconds_since_midnight"
  - "asyncio.Lock for concurrent toggle/evaluation protection"
  - "30-day auto-purge runs once per evaluation loop iteration (not per user)"

requirements-completed: [DRY-01, DRY-02, DRY-03, DRY-04, DRY-05]

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 16 Plan 02: DryRunService + API Routes Summary

**DryRunService singleton with candle-close evaluation loop, virtual trading via domain module, 6 API endpoints, and WebSocket broadcast for real-time dry-run updates**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T16:16:36Z
- **Completed:** 2026-02-27T16:21:36Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- DryRunService singleton with evaluation loop aligned to wall-clock interval boundaries (5m/15m/1h)
- Structural isolation verified: zero imports from order_service, binance.py, order_tracking_service, pairing_service (DRY-05)
- 6 API endpoints registered: status, toggle, decisions (filterable by date/action/symbol), decision detail, reset, portfolio
- Idempotency check prevents double-evaluation on server restart mid-interval
- 30-day auto-purge of old decisions during evaluation loop
- asyncio.Lock prevents race between toggle and evaluation
- WebSocket broadcast for decisions, status changes, and portfolio updates
- All 782 existing backend tests pass without regression

## Task Commits

Each task was committed atomically:

1. **Task 1: DryRunService singleton with evaluation loop and virtual trading** - `0c020cf` (feat)
2. **Task 2: API routes + main.py lifespan + WebSocket message types** - `7f87a93` (feat)

## Files Created/Modified
- `backend/app/services/dry_run_service.py` - DryRunService singleton: evaluation loop, virtual buy/sell, toggle, reset, status, decisions, WebSocket broadcast
- `backend/app/api/routes/dry_run.py` - 6 API endpoints under /api/dry-run with auth, validation, error handling
- `backend/app/main.py` - dry_run route registration, DryRunService start/stop in lifespan
- `backend/app/services/websocket_manager.py` - Public broadcast_message() method, dry-run message type documentation

## Decisions Made
- DryRunService uses SessionLocal() for DB operations inside the evaluation loop since FastAPI's get_db() is request-scoped and unavailable in background tasks
- Added public broadcast_message() wrapper on BinanceStreamManager rather than calling private _broadcast_to_user directly from external services
- Evaluation loop determines minimum interval from all active users to avoid multiple asyncio tasks for different intervals
- Idempotency check calculates current interval boundary from wall clock and queries for existing decisions within that boundary

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Service layer and API endpoints ready for frontend integration (16-03: Bot Dashboard + Decision Log)
- WebSocket message types ready for frontend consumption in WebSocketContext.jsx
- All dry-run requirements (DRY-01 through DRY-05) met at backend level

---
*Phase: 16-dry-run-mode-bot-dashboard*
*Completed: 2026-02-27*
