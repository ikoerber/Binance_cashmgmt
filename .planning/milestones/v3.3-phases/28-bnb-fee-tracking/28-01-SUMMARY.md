---
phase: 28-bnb-fee-tracking
plan: 01
subsystem: api, ui
tags: [fastapi, react, binance, bnb, fees, portfolio, overview]

# Dependency graph
requires:
  - phase: 27-overview-layout-restructure
    provides: Overview asset table component structure
provides:
  - GET /api/portfolio/{user_id}/bnb-fees endpoint returning BNB balance, EUR value, and cumulative fee total
  - getBnbFees() API client function
  - BNB row in Overview asset table with balance and cumulative fee EUR display
  - Muted row CSS styles for non-tradable supplementary assets
affects: [overview, portfolio, dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Supplementary asset row pattern: non-clickable muted rows appended after tradable assets in Overview table"
    - "BNB fee aggregation via SUM(fee_quote_value) with EventTypeEnum.TRADE_FILL filter"

key-files:
  created: []
  modified:
    - backend/app/services/portfolio_service.py
    - backend/app/api/routes/portfolio.py
    - frontend/src/api/client.js
    - frontend/src/components/Overview.jsx
    - frontend/src/components/Overview.css

key-decisions:
  - "Used authenticated BinanceService client for BNB/EUR ticker instead of public client (avoids new dependency, reuses existing singleton)"
  - "BNB row conditionally rendered only when bnb_balance > 0 (no empty row for users without BNB)"
  - "P&L column repurposed to show cumulative fee EUR with italic 'Fees:' prefix instead of percentage"

patterns-established:
  - "Supplementary asset rows: overview-asset-row--muted class disables click, hover, and applies muted colors"

requirements-completed: [OVW-04, OVW-05]

# Metrics
duration: 3min
completed: 2026-03-01
---

# Phase 28 Plan 01: BNB Fee Tracking Summary

**BNB fee tracking endpoint with Binance balance fetch and cumulative fee_quote_value aggregation, integrated as muted row in Overview asset table**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-01T10:37:24Z
- **Completed:** 2026-03-01T10:40:23Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- New GET /api/portfolio/{user_id}/bnb-fees endpoint with BNB balance, EUR valuation, cumulative fee total, and graceful degradation
- Overview asset table shows BNB row with current balance and cumulative EUR-equivalent trading fee costs
- BNB row is visually distinct (muted, non-clickable) and only appears when BNB balance > 0

## Task Commits

Each task was committed atomically:

1. **Task 1: Add get_bnb_fee_summary() service function and GET /api/portfolio/{user_id}/bnb-fees endpoint** - `de344ea` (feat)
2. **Task 2: Add getBnbFees() to API client and integrate BNB row into Overview asset table** - `0e4d2c4` (feat)
3. **Task 3: Add CSS styles for BNB muted row and fee info display** - `6bd537e` (feat)

## Files Created/Modified
- `backend/app/services/portfolio_service.py` - Added get_bnb_fee_summary() with BNB balance fetch, fee_quote_value aggregation, and BNB/EUR pricing
- `backend/app/api/routes/portfolio.py` - Added GET /{user_id}/bnb-fees endpoint with error sanitization
- `frontend/src/api/client.js` - Added getBnbFees() API client function
- `frontend/src/components/Overview.jsx` - Added useQuery for BNB data, rendered BNB row after tradable assets
- `frontend/src/components/Overview.css` - Added overview-asset-row--muted and overview-fee-info styles

## Decisions Made
- Used authenticated BinanceService client for BNB/EUR ticker (get_symbol_ticker) instead of public client -- avoids adding a new dependency and reuses the existing singleton
- BNB row conditionally rendered only when bnb_balance > 0 to avoid empty supplementary rows
- P&L% column repurposed for BNB to show "Fees: X EUR" with italic styling since P&L percentage is not meaningful for a fee-payment asset

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failure in tests/test_health_check.py (AttributeError) -- unrelated to BNB fee tracking changes, 222 of 223 tests pass

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- BNB fee visibility complete in Overview
- No blockers for subsequent phases

## Self-Check: PASSED

All files exist. All 3 task commits verified (de344ea, 0e4d2c4, 6bd537e).

---
*Phase: 28-bnb-fee-tracking*
*Completed: 2026-03-01*
