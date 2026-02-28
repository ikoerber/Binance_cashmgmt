---
phase: 15-backtesting-engine
plan: 03
subsystem: ui
tags: [backtest, react, recharts, equity-curve, heatmap, histogram, drawdown, tanstack-query]

# Dependency graph
requires:
  - phase: 15-backtesting-engine
    provides: "BacktestDataService + 4 API endpoints (run/list/detail/cancel)"
provides:
  - "Standalone Backtest page with configuration form, result visualization, and history browser"
  - "4 API client functions: runBacktest, getBacktestRuns, getBacktestRunDetail, cancelBacktest"
  - "/backtest route + GlobalNav link"
  - "Recharts equity curve with HODL benchmark overlay + warmup region"
  - "Drawdown underwater chart, monthly returns heatmap, P&L histogram"
  - "Collapsible backtest history with expandable run details (mini equity curve + trade list)"
affects: [15-04, backtest-sweep, backtest-websocket-progress]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Backtest form with auto-ATR-multiplier on symbol change (BTCEUR: 2.0, XRPEUR: 3.0)"
    - "Percentage-to-decimal conversion at mutation call (user enters 0.1%, API receives 0.001)"
    - "Monthly returns heatmap via CSS Grid with dynamic color function"
    - "Trade P&L histogram via Recharts BarChart with runtime bucketing"
    - "Collapsible history run cards with lazy detail loading via getBacktestRunDetail"

key-files:
  created:
    - frontend/src/components/Backtest.jsx
    - frontend/src/components/Backtest.css
  modified:
    - frontend/src/api/client.js
    - frontend/src/App.jsx
    - frontend/src/components/GlobalNav.jsx

key-decisions:
  - "Indigo accent color for Backtest section (distinct from amber Orderblock and combined purple)"
  - "Form inputs accept user-friendly percentages (0.1%) and convert to API decimals (0.001) at mutation time"
  - "Heatmap uses inline CSS Grid (not Recharts) for precise cell-level color control"
  - "History runs use lazy loading: header metrics always visible, detail (equity curve + trades) fetched on expand"
  - "trades and monthlyReturns wrapped in useMemo to satisfy react-hooks/exhaustive-deps"

patterns-established:
  - "Backtest page pattern: form section -> metrics grid -> chart stack -> collapsible trade list -> history cards"
  - "Auto-parameter adjustment on symbol change (ATR multiplier defaults per asset)"

requirements-completed: [BT-01, BT-02, BT-03, BT-05, BT-06]

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 15 Plan 03: Frontend Backtest Page Summary

**Standalone Backtest page with configurable form, Recharts equity curve + HODL benchmark, drawdown chart, monthly heatmap, P&L histogram, trade list, and collapsible history browser**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T14:45:36Z
- **Completed:** 2026-02-27T14:50:42Z
- **Tasks:** 2
- **Files created/modified:** 5

## Accomplishments
- 4 API client functions for backtest operations (run, list, detail, cancel) added to client.js
- /backtest route + GlobalNav "Backtest" link for standalone page access
- Backtest.jsx (805 lines): full-featured page with 8-field config form, 10 metric cards, 4 chart types, collapsible trade list, and expandable history browser
- Backtest.css (700 lines): responsive indigo-accented styles with dark mode support via CSS variables
- Frontend builds without errors, 0 ESLint errors

## Task Commits

Each task was committed atomically:

1. **Task 1: API client functions + App routing + GlobalNav link** - `3d1b2fd` (feat)
2. **Task 2: Backtest page with form, charts, metrics, and history** - `bbbe026` (feat)

## Files Created/Modified
- `frontend/src/api/client.js` - Added runBacktest, getBacktestRuns, getBacktestRunDetail, cancelBacktest functions
- `frontend/src/App.jsx` - Added Backtest import + /backtest route
- `frontend/src/components/GlobalNav.jsx` - Added "Backtest" navigation link in global nav right section
- `frontend/src/components/Backtest.jsx` - Full Backtest page: config form, metric cards, equity curve (Recharts LineChart), drawdown (AreaChart), monthly heatmap (CSS Grid), P&L histogram (BarChart), trade list, history browser
- `frontend/src/components/Backtest.css` - Scoped styles: indigo accent, responsive grids, heatmap colors, dark mode support

## Decisions Made
- Indigo accent (`--color-accent-indigo` / `#818cf8`) chosen for Backtest section to distinguish from amber Orderblock and purple Combined Score
- Form inputs use user-friendly units (percentages) and convert to API decimals at mutation call time -- avoids confusing the user with decimal entry
- Monthly returns heatmap implemented as CSS Grid rather than Recharts -- better control over cell-level dynamic colors and text
- History runs use lazy detail loading: run summary metrics always visible in card header, full equity curve + trade list fetched on-demand when user expands a card
- Wrapped `trades` and `monthlyReturns` in `useMemo` to fix react-hooks/exhaustive-deps warnings (ESLint clean)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed react-hooks/exhaustive-deps warnings**
- **Found during:** Task 2 (ESLint verification)
- **Issue:** `trades` and `monthlyReturns` derived as `const trades = currentResult?.trades || []` created new array references on every render, causing useMemo dependency instability
- **Fix:** Wrapped both in `useMemo(() => currentResult?.trades || [], [currentResult])` to stabilize references
- **Files modified:** frontend/src/components/Backtest.jsx
- **Verification:** ESLint passes with 0 errors and 0 warnings
- **Committed in:** bbbe026 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial fix for ESLint compliance. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Frontend Backtest page complete and operational
- Ready for Plan 04: Parameter sweep form, WebSocket progress streaming, CSV export, cancellation
- WebSocket progress placeholder (spinner) in place, ready to wire to real-time updates in Plan 04

## Self-Check: PASSED

- [x] frontend/src/components/Backtest.jsx exists (805 lines, >= 500 min_lines)
- [x] frontend/src/components/Backtest.css exists (700 lines, >= 200 min_lines)
- [x] frontend/src/api/client.js contains runBacktest, getBacktestRuns, getBacktestRunDetail, cancelBacktest
- [x] frontend/src/App.jsx contains /backtest route
- [x] frontend/src/components/GlobalNav.jsx contains backtest link
- [x] Commit 3d1b2fd exists (Task 1)
- [x] Commit bbbe026 exists (Task 2)
- [x] Frontend builds without errors
- [x] ESLint passes with 0 errors

---
*Phase: 15-backtesting-engine*
*Completed: 2026-02-27*
