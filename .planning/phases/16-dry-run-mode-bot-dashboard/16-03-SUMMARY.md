---
phase: 16-dry-run-mode-bot-dashboard
plan: 03
subsystem: frontend, navigation, websocket
tags: [react, tanstack-query, recharts, websocket, dry-run, bot-dashboard, decision-log, navigation]

# Dependency graph
requires:
  - phase: 16-dry-run-mode-bot-dashboard
    plan: 01
    provides: "Pure domain module (dry_run.py), 3 DB tables, Settings API extension (dry_run_initial_capital)"
  - phase: 16-dry-run-mode-bot-dashboard
    plan: 02
    provides: "6 API endpoints under /api/dry-run, WebSocket message types (dry_run_decision/status/portfolio_update)"
  - phase: 14-alpha-score
    provides: "GET /api/alpha-score/{user_id}/score endpoint for Alpha Score display"
  - phase: 15-backtesting-engine
    provides: "GET /api/backtest/{user_id}/runs for backtest summary display"
provides:
  - "Bot Dashboard page with Alpha Score hero, factor bars, signal chart, dry-run controls, KPI cards"
  - "Decision Log page with filterable table, expandable factor detail rows, pagination"
  - "4-group navigation (Trading/Analyse/Bot/Admin) in SymbolLayout"
  - "API client functions: getAlphaScore, getDryRunStatus/Toggle/Decisions/DecisionDetail/Portfolio/Reset"
  - "WebSocket handlers for dry_run_decision, dry_run_status, dry_run_portfolio_update"
  - "Settings UI: dry_run_initial_capital input with validation"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["4-group navigation in SymbolLayout (Trading/Analyse/Bot/Admin)", "Dry-run badge with pulse animation on nav item", "Bidirectional factor bars with center-out fill pattern"]

key-files:
  created:
    - frontend/src/components/BotDashboard.jsx
    - frontend/src/components/BotDashboard.css
    - frontend/src/components/DecisionLog.jsx
    - frontend/src/components/DecisionLog.css
  modified:
    - frontend/src/App.jsx
    - frontend/src/components/GlobalNav.jsx
    - frontend/src/components/SymbolLayout.jsx
    - frontend/src/components/Settings.jsx
    - frontend/src/api/client.js
    - frontend/src/contexts/WebSocketContext.jsx

key-decisions:
  - "getAlphaScore API client function added (was missing from Phase 14 frontend, needed for BotDashboard)"
  - "Navigation links Backtest and Settings moved from GlobalNav to SymbolLayout groups (Analyse and Admin)"
  - "Factor bars use bidirectional fill from center (50% = neutral, <50% = negative, >50% = positive)"
  - "DecisionLog reuses BotDashboard CSS classes (bot-factor-bar, bot-factor-bar-track) for factor detail bars"

patterns-established:
  - "4-group SymbolLayout navigation pattern: Trading (Dashboard, Lots) / Analyse (Combined Score, Orderblocks, Backtest) / Bot (Bot Dashboard, Decision Log) / Admin (Reconciliation, Settings, API Docs)"
  - "Dry-run nav badge pattern: query dry-run status at SymbolLayout level, show amber dot with pulse animation"

requirements-completed: [BOT-01, BOT-02, BOT-03, BOT-04, BOT-05, BOT-06, DRY-04]

# Metrics
duration: 12min
completed: 2026-02-27
---

# Phase 16 Plan 03: Bot Dashboard + Decision Log Frontend Summary

**Bot Dashboard with Alpha Score hero and factor bars, signal history chart, dry-run toggle and KPI cards, Decision Log with filterable expandable rows, and 4-group navigation restructure**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-27T16:25:27Z
- **Completed:** 2026-02-27T16:37:57Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Bot Dashboard (BotDashboard.jsx, 270+ lines): Alpha Score hero with 4 factor bars, regime badge, quality badge, signal history LineChart with BUY/SELL markers, dry-run toggle and reset, 6 KPI cards (P&L, trades, win rate, backtest summary, regime, portfolio)
- Decision Log (DecisionLog.jsx, 270+ lines): Filterable table (date range, action, symbol) with expandable rows showing factor detail bars, regime info, virtual trade details, full reason text, pagination
- Navigation restructured from 3 to 4 groups: Trading, Analyse (with Backtest), Bot (Dashboard + Decision Log with dry-run badge), Admin (Reconciliation, Settings, API Docs)
- 7 API client functions added (getAlphaScore, getDryRunStatus, toggleDryRun, getDryRunDecisions, getDryRunDecisionDetail, resetDryRunPortfolio, getDryRunPortfolio)
- WebSocket handlers for 3 dry-run message types with TanStack Query invalidation
- Settings page extended with dry_run_initial_capital number input and validation
- No order-placing UI elements in Bot section (DRY-05 frontend enforcement verified)

## Task Commits

Each task was committed atomically:

1. **Task 1: Navigation restructure + Bot Dashboard + API client functions** - `dbf9c94` (feat)
2. **Task 2: Decision Log component with filtering and expandable rows** - `1f0c0e2` (feat)

## Files Created/Modified
- `frontend/src/components/BotDashboard.jsx` - Bot Dashboard: Alpha Score hero, factor bars, signal chart, dry-run controls, KPI cards
- `frontend/src/components/BotDashboard.css` - Bot Dashboard styling with amber accent, bidirectional factor bars, nav badge
- `frontend/src/components/DecisionLog.jsx` - Filterable decision log table with expandable factor detail rows
- `frontend/src/components/DecisionLog.css` - Decision Log styling, reuses factor bar CSS from BotDashboard
- `frontend/src/App.jsx` - Added BotDashboard and DecisionLog route imports + routes under /s/:symbol
- `frontend/src/components/GlobalNav.jsx` - Removed Backtest and Settings NavLinks (moved to SymbolLayout)
- `frontend/src/components/SymbolLayout.jsx` - 4 nav groups, dry-run status query, amber badge on Bot Dashboard
- `frontend/src/components/Settings.jsx` - dry_run_initial_capital state, useEffect, validation, save, UI section
- `frontend/src/api/client.js` - getAlphaScore + 6 dry-run API functions
- `frontend/src/contexts/WebSocketContext.jsx` - 3 dry-run WebSocket message handlers

## Decisions Made
- Added getAlphaScore API client function that was missing from Phase 14 frontend (Rule 3 - blocking issue: BotDashboard requires it)
- Backtest and Settings links moved entirely from GlobalNav to SymbolLayout groups, making them contextual to symbol view
- Factor bars use bidirectional fill from center: score mapped from [-5, +5] to [0%, 100%] with center at 50%, fill extends left (negative/red) or right (positive/green)
- DecisionLog reuses BotDashboard CSS classes for factor bars rather than duplicating, keeping styling consistent

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added missing getAlphaScore API client function**
- **Found during:** Task 1 (BotDashboard requires getAlphaScore import)
- **Issue:** Plan references "import getAlphaScore from api/client.js (already exists from Phase 14)" but the function was never added to client.js in Phase 14
- **Fix:** Added getAlphaScore function following existing API client patterns
- **Files modified:** frontend/src/api/client.js
- **Verification:** Frontend builds successfully, import resolves
- **Committed in:** dbf9c94 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for BotDashboard functionality. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 16 complete: all 3 plans executed (foundation, service+API, frontend)
- All BOT-01 through BOT-06 and DRY-01 through DRY-05 requirements met across the three plans
- Bot Dashboard and Decision Log are fully wired to backend API endpoints from Plan 02
- WebSocket real-time updates connected for dry-run decisions, status, and portfolio changes

## Self-Check: PASSED

All files exist, all commits verified, frontend builds successfully.

---
*Phase: 16-dry-run-mode-bot-dashboard*
*Completed: 2026-02-27*
