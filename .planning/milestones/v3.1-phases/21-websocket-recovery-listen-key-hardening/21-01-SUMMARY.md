---
phase: 21-websocket-recovery-listen-key-hardening
plan: 01
subsystem: websocket
tags: [binance, websocket, hmac, subscribe-signature, health-check, reconciliation]

requires:
  - phase: 20-health-check-endpoint
    provides: HealthCheckService with _check_websocket()
provides:
  - subscribe.signature-based User Data Stream (replaces legacy listen keys)
  - Post-reconnect fill reconciliation with 60s debounce
  - User data freshness tracking (_last_user_data_message_at)
  - Health check DEGRADED detection for silent user data streams (>90s)
affects: [22-status-dashboard-frontend, websocket-manager, health-check]

tech-stack:
  added: [hmac, hashlib, urllib.parse]
  patterns: [subscribe.signature HMAC-SHA256 signing, post-reconnect reconciliation, freshness tracking]

key-files:
  created:
    - backend/tests/test_websocket_recovery.py
  modified:
    - backend/app/services/websocket_manager.py
    - backend/app/services/health_check_service.py
    - backend/tests/test_health_check.py

key-decisions:
  - "Used module-level pure function _build_subscribe_message for testability"
  - "Debounce reconciliation at 60s to avoid redundant Binance API calls on rapid reconnects"
  - "Track freshness at message handler level (before processing) for accuracy"
  - "Health check only reports DEGRADED when user_data_subscribers exist (no false alerts)"

patterns-established:
  - "subscribe.signature: HMAC-SHA256 with alphabetically-sorted params for Binance ws-api/v3"
  - "Post-reconnect reconciliation: automatic fill sync after disconnect with configurable debounce"

requirements-completed: [WSRC-01, WSRC-02, WSRC-03]

duration: 12min
completed: 2026-02-28
---

# Phase 21 Plan 01: WebSocket Recovery + Subscribe Signature Migration Summary

**Migrated User Data Stream from legacy listen keys to HMAC-SHA256 subscribe.signature, added post-reconnect fill reconciliation with 60s debounce and health check freshness detection**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-28T10:00:00Z
- **Completed:** 2026-02-28T10:12:00Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 4

## Accomplishments
- Replaced defunct legacy userDataStream.start/ping/stop with subscribe.signature (HMAC-SHA256)
- Post-reconnect fill reconciliation automatically syncs fills for all KNOWN_PAIRS since disconnect
- Health check reports DEGRADED when user data stream silent >90s with active subscribers
- 12 new tests (9 recovery + 3 health freshness) all passing
- All legacy listen key code removed (_keepalive_listen_key, _ws_api_request, _listen_keys dict)

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD RED - Failing tests** - `89b154c` (test)
2. **Task 2: TDD GREEN - Implementation** - `9d00962` (feat)

## Files Created/Modified
- `backend/tests/test_websocket_recovery.py` - 9 tests for subscribe.signature, reconciliation, freshness, debounce
- `backend/app/services/websocket_manager.py` - Full migration: subscribe.signature, reconciliation, freshness tracking
- `backend/app/services/health_check_service.py` - WSRC-02: User data freshness check (>90s -> DEGRADED)
- `backend/tests/test_health_check.py` - 3 new tests for user data freshness scenarios

## Decisions Made
- Used module-level pure function `_build_subscribe_message()` for easy unit testing of HMAC signing
- Debounce at 60 seconds prevents redundant Binance API calls on rapid reconnects
- Freshness tracked at handler entry (before processing) for maximum accuracy
- Health check only checks freshness when `user_data_subscribers` is non-empty to avoid false DEGRADED alerts

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test mock targets for lazy imports**
- **Found during:** Task 2 (TDD GREEN - running tests)
- **Issue:** Tests patched `app.services.websocket_manager.SessionLocal` and `handle_order_update` but these are lazy imports inside functions, not module-level attributes
- **Fix:** Changed patch targets to actual import locations: `app.db.database.SessionLocal`, `app.services.websocket_event_handler.handle_order_update`
- **Files modified:** backend/tests/test_websocket_recovery.py
- **Verification:** All 22 tests pass
- **Committed in:** 9d00962

**2. [Rule 1 - Bug] Fixed async iterator mock for reconnect test**
- **Found during:** Task 2 (TDD GREEN - running tests)
- **Issue:** `mock_ws.__aiter__` returned a regular iterator, but `async for` requires `__anext__` (async iterator protocol)
- **Fix:** Created proper `AsyncWSIter` class implementing `__aiter__` and `__anext__`
- **Files modified:** backend/tests/test_websocket_recovery.py
- **Verification:** test_reconnect_on_connection_drop passes
- **Committed in:** 9d00962

---

**Total deviations:** 2 auto-fixed (2 bugs in test mocking)
**Impact on plan:** Both fixes were necessary for correct test mocking. No scope change.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend WebSocket migration complete, subscribe.signature operational
- Health check freshness detection ready for StatusDashboard (Phase 22)
- Ready for Plan 21-02 (frontend WebSocketContext reconnect state)

---
*Phase: 21-websocket-recovery-listen-key-hardening*
*Completed: 2026-02-28*
