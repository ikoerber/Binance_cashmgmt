---
phase: 23-navigation-structure
plan: 01
subsystem: ui
tags: [react-router, navigation, localStorage, url-sync]

# Dependency graph
requires: []
provides:
  - All pages render inside SymbolLayout with consistent 4-group sub-navigation
  - Old bookmark URLs redirect to symbol-scoped routes via localStorage fallback
  - Backtest symbol state synced bidirectionally with URL
affects: [24-kpi-tiles-polish, 25-settings-revamp]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - SymbolRedirect component for legacy URL redirects with localStorage memory
    - URL-synced component state via useParams + navigate (Backtest symbol)

key-files:
  created: []
  modified:
    - frontend/src/App.jsx
    - frontend/src/components/GlobalNav.jsx
    - frontend/src/components/SymbolLayout.jsx
    - frontend/src/components/Backtest.jsx

key-decisions:
  - "localStorage key cashmgnt_last_symbol for cross-session symbol memory"
  - "Status dot links in GlobalNav use symbol-aware URLs when on symbol page, fallback to redirect"
  - "Backtest keeps inline symbol dropdown as quick-switch alongside URL sync"

patterns-established:
  - "SymbolRedirect pattern: localStorage.getItem('cashmgnt_last_symbol') || 'BTCEUR' for old bookmark fallback"
  - "URL-synced state: useParams for initial value, navigate() on change for bidirectional sync"

requirements-completed: [NAV-01]

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 23 Plan 01: Navigation Structure Summary

**Settings, Backtest, and Status moved inside SymbolLayout with 4-group sub-nav (Trading/Analyse/Bot/Admin), localStorage redirect fallback, and URL-synced Backtest symbol**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T16:41:26Z
- **Completed:** 2026-02-28T16:44:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- All 10 pages (Dashboard, TradeLots, Combined Score, Orderblocks, Bot Dashboard, Decision Log, Backtest, Reconciliation, Settings, Status) now render inside SymbolLayout with consistent sub-navigation
- Sub-nav restructured into 4 groups: Trading (Dashboard, TradeLots), Analyse (Combined Score, Orderblocks), Bot (Bot Dashboard, Decision Log, Backtest), Admin (Reconciliation, Settings, Status)
- Old bookmarks (/settings, /backtest, /status) redirect to /s/{lastSymbol}/... with localStorage fallback to BTCEUR
- Backtest symbol pre-selects from URL and navigates on dropdown change

## Task Commits

Each task was committed atomically:

1. **Task 1: Restructure routes and add redirects with localStorage symbol memory** - `5b193d0` (feat)
2. **Task 2: Restructure sub-nav groups and sync Backtest symbol with URL** - `6b441bf` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified
- `frontend/src/App.jsx` - Moved Settings/Backtest/Status into SymbolLayout children, added SymbolRedirect for old bookmarks
- `frontend/src/components/GlobalNav.jsx` - Added localStorage persistence of last-visited symbol, symbol-aware status dot links
- `frontend/src/components/SymbolLayout.jsx` - Restructured sub-nav: Backtest to Bot group, Settings+Status to Admin group, removed API Docs link
- `frontend/src/components/Backtest.jsx` - Added useParams/useNavigate for URL-synced symbol selection

## Decisions Made
- Used `cashmgnt_last_symbol` as localStorage key (namespaced to avoid collisions)
- Updated GlobalNav status dot links to use symbol-aware URLs when a symbol is active in the URL, preventing unnecessary redirects
- Kept Backtest inline symbol dropdown as quick-switch per user decision (not removed in favor of GlobalNav only)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated GlobalNav status dot links to symbol-aware URLs**
- **Found during:** Task 1 (Route restructuring)
- **Issue:** GlobalNav status dot links pointed to `/status` which now requires a redirect hop. When user is already on a symbol page, linking directly to `/s/${currentSymbol}/status` avoids the unnecessary redirect.
- **Fix:** Made status dot NavLinks conditional: use symbol-scoped URL when `currentSymbol` is available, fallback to `/status` redirect when on Overview
- **Files modified:** frontend/src/components/GlobalNav.jsx
- **Verification:** Build succeeds, links resolve correctly in both contexts
- **Committed in:** 5b193d0 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Minor UX improvement avoiding unnecessary redirect for status dot. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Navigation structure complete, all pages consistent
- Ready for Phase 24 (KPI Tiles Polish) which builds on the dashboard pages now inside SymbolLayout

## Self-Check: PASSED

All files found, all commits verified.

---
*Phase: 23-navigation-structure*
*Completed: 2026-02-28*
