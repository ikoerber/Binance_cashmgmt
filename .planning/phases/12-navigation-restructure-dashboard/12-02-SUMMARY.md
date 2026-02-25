---
phase: 12-navigation-restructure-dashboard
plan: 02
subsystem: ui
tags: [react, react-router, navigation, css-variables, dark-mode, footer]

# Dependency graph
requires:
  - phase: 12-navigation-restructure-dashboard
    plan: 01
    provides: CombinedScoreWidget + Dashboard integration (Dashboard.jsx ready for routing)
provides:
  - 3-area grouped sub-navigation (Trading, Analyse, Admin) with visual separators
  - Dashboard as default symbol page (/s/:symbol -> /s/:symbol/dashboard)
  - Footer API Docs link to FastAPI Swagger UI
  - All legacy URLs preserved (lots, combined, orderblock, reconciliation)
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [subnav-group pattern for visually grouped navigation with labels and separators]

key-files:
  created: []
  modified:
    - frontend/src/components/SymbolLayout.jsx
    - frontend/src/App.jsx
    - frontend/src/App.css

key-decisions:
  - "3 navigation groups: Trading (Dashboard, TradeLots), Analyse (Combined Score, Orderblocks), Admin (Reconciliation)"
  - "Index redirect changed from /lots to /dashboard -- Dashboard is now the default landing page per symbol"
  - "API Docs link placed in footer (not navbar) to avoid clutter in primary navigation"
  - "subnav-group separator uses rgba(255,255,255,0.15) border-left consistent with existing subnav rgba patterns"

patterns-established:
  - "Grouped sub-nav: subnav-group containers with subnav-group-label spans for visual grouping"

requirements-completed: [NAV-01, NAV-03, NAV-04]

# Metrics
duration: 2min
completed: 2026-02-25
---

# Phase 12 Plan 02: 3-Area Sub-Navigation Restructure + Dashboard Routing Summary

**3-area grouped sub-nav (Trading/Analyse/Admin) with Dashboard as default landing page and footer API Docs link**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-25T19:25:39Z
- **Completed:** 2026-02-25T19:27:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Restructured flat nav into 3 visually grouped areas with uppercase labels and border separators
- Dashboard is now the default page when selecting a symbol (index redirect from /lots to /dashboard)
- All legacy URLs preserved -- existing bookmarks to /lots, /combined, /orderblock, /reconciliation continue to work
- Footer API Docs link points to FastAPI /docs Swagger UI endpoint
- Zero hardcoded hex values in all modified files (dark mode compatible)

## Task Commits

Each task was committed atomically:

1. **Task 1: Restructure SymbolLayout 3-area sub-nav and App.jsx routes** - `dca16d7` (feat)
2. **Task 2: Add subnav-group CSS styles** - `c294595` (feat)

## Files Created/Modified
- `frontend/src/components/SymbolLayout.jsx` - 3-area grouped sub-nav: Trading (Dashboard, TradeLots), Analyse (Combined Score, Orderblocks), Admin (Reconciliation)
- `frontend/src/App.jsx` - Dashboard import, dashboard route, index redirect to dashboard, footer API Docs link
- `frontend/src/App.css` - subnav-group, subnav-group-label, group separator, footer-link styles

## Decisions Made
- Used "Analyse" (German) as group label for Combined Score + Orderblocks, consistent with the German-language application context
- Changed "Orderblock" nav label to "Orderblocks" (plural) for grammatical consistency
- API Docs link placed in footer between version text and server IP -- keeps primary navigation uncluttered
- Group separator uses border-left with rgba(255,255,255,0.15), consistent with existing subnav rgba color patterns in App.css

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 12 is now complete: all 2 plans executed
- All NAV requirements fulfilled: NAV-01 (3-area nav), NAV-02 (CombinedScoreWidget), NAV-03 (footer API docs), NAV-04 (Dashboard as default)
- GlobalNav buildSymbolUrl() automatically preserves sub-path on symbol switch (no changes needed)

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 12-navigation-restructure-dashboard*
*Completed: 2026-02-25*
