---
phase: 09-xrpbtc-removal
plan: 02
subsystem: ui
tags: [react, css, pairing, symbol-registry, frontend-cleanup]

# Dependency graph
requires:
  - phase: 09-xrpbtc-removal plan 01
    provides: Simplified backend API without cross-pair parameters
provides:
  - 3-symbol EUR-only frontend registry (BTCEUR, ETHEUR, XRPEUR)
  - Simplified pairing UI without cross-pair toggle or routing display
  - Clean API client without cross-pair parameters
  - CSS without dual-route, routing-badge, pair-origin-badge styles
affects: [09-xrpbtc-removal plan 03]

# Tech tracking
tech-stack:
  added: []
  patterns: [EUR-only symbol registry, simplified pairing API calls]

key-files:
  modified:
    - frontend/src/utils/symbolRegistry.js
    - frontend/src/api/client.js
    - frontend/src/components/PairingPanel.jsx
    - frontend/src/components/PairingExistingTab.jsx
    - frontend/src/components/SimulationModal.jsx
    - frontend/src/components/PairingPanel.css
    - frontend/src/hooks/useLotsData.js
    - frontend/src/components/Overview.jsx
    - frontend/src/components/Dashboard.jsx

key-decisions:
  - "Simplified getQuoteDecimals() to always return 2 (only EUR pairs remain)"
  - "Removed unused getPairLabel import from PairingPanel after pair-origin badges removed"
  - "Removed unused WebSocket prices import from PairingExistingTab after XRPBTC price logic removed"
  - "Removed unused formatEUR import from SimulationModal after dual-route section removed"

patterns-established:
  - "EUR-only registry: All KNOWN_PAIRS use EUR quote asset, no BTC-quoted pairs"
  - "No cross-pair parameters: Pairing API calls use only symbol, never base_asset"

requirements-completed: [REM-06]

# Metrics
duration: 5min
completed: 2026-02-23
---

# Phase 09 Plan 02: Frontend XRPBTC Removal Summary

**EUR-only symbol registry (3 pairs), simplified pairing UI without cross-pair toggle/routing badges, clean API client without XRPBTC parameters**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-23T22:45:21Z
- **Completed:** 2026-02-23T22:51:07Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Removed XRPBTC from frontend symbol registry, leaving 3 EUR-only pairs (BTCEUR, ETHEUR, XRPEUR)
- Eliminated all cross-pair UI elements: toggle checkbox, routing-badge, pair-origin-badge, dual-route comparison section, cross-pair-label
- Simplified API client (removed baseAsset, xrpbtcPrice, btceurPrice parameters from pairing calls)
- Deleted ~220 lines of cross-pair CSS (routing, dual-route cards, pair-origin badges, cross-pair toggle)
- Cleaned cosmetic cross-pair comments from useLotsData, Overview, Dashboard

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove XRPBTC from Frontend Symbol Registry and API Client** - `b937224` (feat)
2. **Task 2: Remove Cross-Pair UI Elements from Components and CSS** - `29a7537` (feat)

## Files Created/Modified
- `frontend/src/utils/symbolRegistry.js` - Removed XRPBTC entry, deleted getSymbolsForBaseAsset(), simplified getQuoteDecimals()
- `frontend/src/api/client.js` - Removed baseAsset/xrpbtcPrice/btceurPrice from getPairingSuggestions/simulatePairing/createPairing
- `frontend/src/components/PairingPanel.jsx` - Removed cross-pair toggle, effectiveCrossPair state, pair-origin badges, baseAsset params
- `frontend/src/components/PairingExistingTab.jsx` - Removed routing-badge, routing-savings, cross-pair-label, XRPBTC WebSocket price logic
- `frontend/src/components/SimulationModal.jsx` - Removed dual-route comparison section (45 lines of route cards)
- `frontend/src/components/PairingPanel.css` - Deleted routing-badge, routing-savings, dual-route, cross-pair-toggle, pair-origin-badge, cross-pair-label styles
- `frontend/src/hooks/useLotsData.js` - Cleaned cross-pair comment
- `frontend/src/components/Overview.jsx` - Cleaned cross-pair comments
- `frontend/src/components/Dashboard.jsx` - Cleaned cross-pair comment

## Decisions Made
- Simplified `getQuoteDecimals()` to always return 2 since only EUR-quoted pairs remain (no BTC branch needed)
- Removed unused imports after cross-pair code deletion: getPairLabel from PairingPanel, getPairLabel + useWebSocket from PairingExistingTab, formatEUR from SimulationModal
- Orderblock.jsx, OrderblockZoneTable.jsx, SymbolLayout.jsx had no cross-pair references (verified, no changes needed)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Frontend is now fully aligned with simplified backend API (Plan 01)
- Zero XRPBTC references remain in frontend src/
- Ready for Plan 03: Alembic migration to drop physical DB columns

## Self-Check: PASSED

All 9 modified files verified on disk. Both task commits (b937224, 29a7537) verified in git history.

---
*Phase: 09-xrpbtc-removal*
*Completed: 2026-02-23*
