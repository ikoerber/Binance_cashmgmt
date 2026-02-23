---
phase: 08-alert-system
plan: 02
subsystem: ui
tags: [react, alerts, tanstack-query, polling, banner, sync-details]

# Dependency graph
requires:
  - phase: 08-alert-system
    provides: Alert API endpoints (GET list, PATCH acknowledge, POST bulk-acknowledge)
provides:
  - AlertBanner component with persistent dismiss and 30s polling
  - Alert API client functions (getAlerts, acknowledgeAlert, acknowledgeAllAlerts)
  - Reconciliation history API client functions
  - Sync fill_details display in LotsTable (fills_failed, fills_skipped_fifo)
  - Alerts query invalidation after sync for immediate banner update
affects: [08-03-PLAN.md, reconciliation-history-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [alert-banner-polling, severity-colored-ui, sync-error-awareness]

key-files:
  created: [frontend/src/components/AlertBanner.jsx, frontend/src/components/AlertBanner.css]
  modified: [frontend/src/api/client.js, frontend/src/App.jsx, frontend/src/components/LotsTable.jsx]

key-decisions:
  - "AlertBanner uses useQuery with 30s refetchInterval for polling (consistent with existing CombinedScore polling pattern)"
  - "Severity-based styling via CSS class names matching backend severity values (warning/critical/info)"
  - "Alerts query invalidated in LotsTable onSuccess to surface auto-reconciliation alerts immediately after sync"
  - "Fill error display uses warning message type (not success) when fills_failed or fills_skipped_fifo > 0"

patterns-established:
  - "Alert polling via TanStack Query refetchInterval (30s) with cache invalidation on mutation"
  - "Severity icon mapping via config object (critical/warning/info) for consistent display"

requirements-completed: [ALERT-01, ALERT-03]

# Metrics
duration: 2min
completed: 2026-02-23
---

# Phase 8 Plan 2: Frontend AlertBanner + Sync Fill Details Summary

**Persistent alert banner with severity-colored dismiss/bulk-dismiss and sync fill error counts in LotsTable sync message**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-23T16:41:21Z
- **Completed:** 2026-02-23T16:43:49Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- AlertBanner component renders below GlobalNav on every page, polling backend every 30s for unacknowledged alerts
- Each alert shows severity icon (critical/warning/info), title text, and dismiss button calling PATCH acknowledge API
- "Alle bestaetigen" bulk-dismiss button appears when >1 alert, calling POST acknowledge-all
- Sync fill_details (fills_failed, fills_skipped_fifo) now visible in sync result message with warning-level display
- Alerts query invalidated after sync for immediate AlertBanner update when auto-reconciliation creates new alerts

## Task Commits

Each task was committed atomically:

1. **Task 1: Alert API client functions + AlertBanner component** - `993dcc1` (feat)
2. **Task 2: Sync fill details in LotsTable sync result message** - `336e52b` (feat)

## Files Created/Modified
- `frontend/src/components/AlertBanner.jsx` - Persistent alert banner with severity styling, dismiss/bulk-dismiss, 30s polling
- `frontend/src/components/AlertBanner.css` - Alert banner styles (warning amber, critical red, info blue, dismiss button, actions bar)
- `frontend/src/api/client.js` - Alert API functions (getAlerts, acknowledgeAlert, acknowledgeAllAlerts) + reconciliation history API functions
- `frontend/src/App.jsx` - AlertBanner import and render after GlobalNav inside AppContent
- `frontend/src/components/LotsTable.jsx` - Sync fill_details display (fills_failed, fills_skipped_fifo) + alerts query invalidation

## Decisions Made
- AlertBanner uses useQuery with 30s refetchInterval for polling (consistent with existing CombinedScore polling pattern)
- Severity-based styling via CSS class names matching backend severity values (warning/critical/info) for zero-mapping overhead
- Alerts query invalidated in LotsTable onSuccess to surface auto-reconciliation alerts immediately after sync
- Fill error display uses warning message type (not success) when fills_failed or fills_skipped_fifo > 0

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AlertBanner and sync details complete, ready for 08-03 (Reconciliation history UI + Settings threshold configuration)
- All API client functions for reconciliation history already added in this plan (getReconciliationHistory, getReconciliationRunDetail)
- Frontend builds successfully

---
*Phase: 08-alert-system*
*Completed: 2026-02-23*
