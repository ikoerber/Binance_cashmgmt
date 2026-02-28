---
phase: 24-dynamic-symbol-visibility
plan: 01
subsystem: ui
tags: [react-query, binance-api, navigation, hooks, active-symbols]

# Dependency graph
requires:
  - phase: 23-navigation-structure
    provides: GlobalNav symbol pills, SymbolLayout route validation, Overview symbol cards
provides:
  - GET /api/balances/{user_id}/active-symbols endpoint based on Binance balances
  - useActiveSymbols hook with 60s polling and WebSocket invalidation
  - GlobalNav symbol pills filtered to held assets only
  - Overview cards filtered to held assets only
  - SymbolLayout redirect to Overview for non-held symbol URLs
affects: [25-settings-revamp]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Balance-driven symbol filtering: backend determines active symbols from Binance, frontend consumes via useActiveSymbols hook"
    - "Graceful degradation pattern: all symbols shown during loading/error, preventing empty nav or incorrect redirects"

key-files:
  created:
    - backend/app/api/routes/balances.py
    - frontend/src/hooks/useActiveSymbols.js
  modified:
    - backend/app/main.py
    - frontend/src/api/client.js
    - frontend/src/components/GlobalNav.jsx
    - frontend/src/components/Overview.jsx
    - frontend/src/components/SymbolLayout.jsx
    - frontend/src/contexts/WebSocketContext.jsx

key-decisions:
  - "Dust threshold 0.00000001 filters sub-satoshi Binance remainders while keeping any meaningful position"
  - "60s polling with 30s staleTime for balance-driven updates, WebSocket invalidation for immediate refresh"
  - "Fallback to all symbols during loading/error prevents nav flicker and incorrect redirects"

patterns-established:
  - "useActiveSymbols pattern: shared query key ['active-symbols'] deduplicates across GlobalNav, Overview, SymbolLayout consumers"
  - "WebSocket-driven cache invalidation: balance_update events immediately refresh active-symbols query"

requirements-completed: [NAV-02, NAV-03]

# Metrics
duration: 7min
completed: 2026-02-28
---

# Phase 24 Plan 01: Dynamic Symbol Visibility Summary

**Backend active-symbols endpoint from Binance balances with useActiveSymbols hook filtering GlobalNav pills, Overview cards, and SymbolLayout access**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-28T17:32:30Z
- **Completed:** 2026-02-28T17:39:30Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- Backend endpoint returns active symbols based on real Binance account balances with dust filtering
- XRPBTC included when XRP is held (base_asset check naturally covers both XRPEUR and XRPBTC since both have XRP as base)
- GlobalNav and Overview dynamically filter to show only held assets
- SymbolLayout redirects non-held symbol URLs to Overview page
- WebSocket balance_update events trigger immediate active-symbols cache invalidation

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend active-symbols endpoint** - `1657532` (feat)
2. **Task 2: Frontend useActiveSymbols hook and API client function** - `8c08a87` (feat)
3. **Task 3: Wire GlobalNav, Overview, and SymbolLayout to use active symbols** - `0b34d22` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified
- `backend/app/api/routes/balances.py` - New route: GET /api/balances/{user_id}/active-symbols with Binance balance lookup, dust threshold, and graceful degradation
- `backend/app/main.py` - Registered balances router with api_auth_with_user dependencies
- `frontend/src/api/client.js` - Added getActiveSymbols API function
- `frontend/src/hooks/useActiveSymbols.js` - New hook: 60s polling, 30s staleTime, fallback to getAllSymbols on error/loading
- `frontend/src/components/GlobalNav.jsx` - Symbol pills from useActiveSymbols instead of getAllSymbols
- `frontend/src/components/Overview.jsx` - Symbol cards from useActiveSymbols instead of getAllSymbols
- `frontend/src/components/SymbolLayout.jsx` - Added redirect to Overview for known but non-held symbols
- `frontend/src/contexts/WebSocketContext.jsx` - balance_update invalidates active-symbols query key

## Decisions Made
- Dust threshold set to 0.00000001 (sub-satoshi) -- any meaningful Binance balance counts as "holding"
- XRPBTC handling: no special rule needed because iterating KNOWN_PAIRS checks base_asset (XRP) for both XRPEUR and XRPBTC naturally
- 60s polling chosen for balance changes (infrequent event), supplemented by WebSocket invalidation for immediate response
- Fallback to BTCEUR when zero assets held (always at least one symbol in nav)
- Graceful degradation on Binance API error returns all symbols (showing more is safer than showing none)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Dynamic symbol visibility complete, nav and overview now balance-driven
- Ready for remaining Phase 24 plans or Phase 25 (Settings Revamp)

## Self-Check: PASSED

All files found, all commits verified.

---
*Phase: 24-dynamic-symbol-visibility*
*Completed: 2026-02-28*
