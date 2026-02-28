---
phase: 20-telegram-notifications
plan: 02
subsystem: notifications
tags: [telegram, health-check, fastapi-lifespan, integration]

requires:
  - phase: 20-telegram-notifications
    provides: TelegramNotifier singleton with check_transitions() and start()/stop()
provides:
  - TelegramNotifier wired into HealthCheckService notification hook
  - TelegramNotifier lifecycle managed via FastAPI lifespan (start/stop)
affects: []

tech-stack:
  added: []
  patterns: [notification-hook-in-health-check, lifespan-lifecycle-management]

key-files:
  created: []
  modified:
    - backend/app/services/health_check_service.py
    - backend/app/main.py

key-decisions:
  - "Notification hook placed in _run_all_checks() (not get_health()) so it fires at most once per 5s cache TTL"
  - "try/except wraps notification call so Telegram failures never block health responses"
  - "Notifier starts AFTER Dry-Run Service, stops BEFORE WebSocket Manager"

patterns-established:
  - "Notification hooks: wrapped in try/except, never blocking the primary response path"

requirements-completed: [TELE-01, TELE-03]

duration: 2min
completed: 2026-02-28
---

# Plan 20-02: Wire TelegramNotifier Integration Summary

**TelegramNotifier hooked into HealthCheckService cycle and FastAPI lifespan for automatic transition alerts and clean Bot lifecycle management**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28
- **Completed:** 2026-02-28
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- HealthCheckService._run_all_checks() calls check_transitions() after each health check
- Notification hook wrapped in try/except (Telegram failure never blocks health response)
- TelegramNotifier initialized at app startup, shutdown cleanly at app stop
- Full test suite (818 tests) green with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Hook into _run_all_checks()** - `15781ae` (feat)
2. **Task 2: Lifespan start/stop** - `b7ed97b` (feat)

## Files Created/Modified
- `backend/app/services/health_check_service.py` - Import get_telegram_notifier, call check_transitions() after result assembly
- `backend/app/main.py` - TelegramNotifier start() after Dry-Run, stop() before WebSocket

## Decisions Made
- Placed notification hook in _run_all_checks() rather than get_health() to respect 5s cache TTL
- Notifier starts after all other services for meaningful health checks

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - Telegram notifications disabled by default when env vars empty.

## Next Phase Readiness
- Phase 20 complete: TelegramNotifier sends alerts on health state transitions
- Ready for Phase 21 (WebSocket Resilience) or Phase 22 (Structured Logging)

---
*Phase: 20-telegram-notifications*
*Completed: 2026-02-28*
