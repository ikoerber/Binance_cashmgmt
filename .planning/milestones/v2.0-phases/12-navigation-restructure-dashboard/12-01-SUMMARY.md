---
phase: 12-navigation-restructure-dashboard
plan: 01
subsystem: ui
tags: [react, tanstack-query, combined-score, dashboard, css-variables, dark-mode]

# Dependency graph
requires:
  - phase: 11-dark-mode-activation-charts
    provides: CSS custom property system, useChartTheme hook, ACTION_COLOR_MAP pattern
provides:
  - CombinedScoreWidget.jsx -- compact hero banner with action label, multiplier, score bar
  - Dashboard.jsx with embedded CombinedScoreWidget above depot-flow KPIs
affects: [12-02 navigation restructure, dashboard routing]

# Tech tracking
tech-stack:
  added: []
  patterns: [widget extraction from full-page component with shared useQuery cache key]

key-files:
  created:
    - frontend/src/components/CombinedScoreWidget.jsx
    - frontend/src/components/CombinedScoreWidget.css
  modified:
    - frontend/src/components/Dashboard.jsx
    - frontend/src/components/Dashboard.css

key-decisions:
  - "Widget uses identical queryKey as CombinedScore.jsx for TanStack Query cache deduplication"
  - "Widget-specific CSS class prefixes (widget-*) to avoid collision with CombinedScore.css classes"
  - "Compact sizing: 26px action label (vs 32px full page), 10px score track (vs 12px), 500px max-width bar (vs 600px)"

patterns-established:
  - "Widget extraction pattern: extract hero section from detail page into standalone component with own data fetching and shared cache key"

requirements-completed: [NAV-02]

# Metrics
duration: 2min
completed: 2026-02-25
---

# Phase 12 Plan 01: Combined Score Hero Widget + Dashboard Integration Summary

**CombinedScoreWidget with action label, multiplier, and score bar embedded in per-symbol Dashboard above depot-flow KPIs**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-25T19:20:50Z
- **Completed:** 2026-02-25T19:23:09Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created self-contained CombinedScoreWidget with own data fetching (same queryKey as CombinedScore.jsx for TanStack cache sharing)
- Embedded widget in Dashboard.jsx above depot-flow section with proper spacing
- Zero hardcoded hex values in both new files (dark mode compatible via CSS custom properties)
- Accessible widget: role=button, tabIndex, keyboard navigation, click-to-navigate to full Combined Score page

## Task Commits

Each task was committed atomically:

1. **Task 1: Create CombinedScoreWidget component** - `57876a2` (feat)
2. **Task 2: Embed CombinedScoreWidget in Dashboard** - `a3ebc18` (feat)

## Files Created/Modified
- `frontend/src/components/CombinedScoreWidget.jsx` - Compact hero banner: action label, multiplier, unified score bar with thresholds, click-to-navigate
- `frontend/src/components/CombinedScoreWidget.css` - Widget styling with CSS variables, hover effects, responsive breakpoints
- `frontend/src/components/Dashboard.jsx` - Added CombinedScoreWidget import and render above depot-flow
- `frontend/src/components/Dashboard.css` - Added .dashboard .combined-widget spacing rule

## Decisions Made
- Used identical queryKey `['combined-score', symbol, userId, interval]` as CombinedScore.jsx to leverage TanStack Query automatic cache deduplication (no duplicate API calls when navigating between Dashboard and Combined Score page)
- Widget CSS classes use `widget-` prefix to avoid collision with existing `combined-` prefixed classes from CombinedScore.css
- Slightly smaller sizing (26px label, 10px track) for compact dashboard context while maintaining readability
- Added accessibility attributes (role, tabIndex, onKeyDown) for keyboard-only users

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CombinedScoreWidget is ready for use in Dashboard
- Plan 02 (navigation restructure + routing) can now add the Dashboard route and restructure sub-nav
- Dashboard.jsx needs to be added to App.jsx routing (covered in Plan 02)

---
*Phase: 12-navigation-restructure-dashboard*
*Completed: 2026-02-25*
