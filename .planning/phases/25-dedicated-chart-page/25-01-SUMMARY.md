---
phase: 25-dedicated-chart-page
plan: "01"
subsystem: ui
tags: [lightweight-charts, candlestick, ohlcv, react, chart, volume, polling]

# Dependency graph
requires:
  - phase: 23-url-symbol-routing
    provides: SymbolLayout, useSymbol context, symbol-scoped routes
provides:
  - Dedicated full-page Chart component at /s/:symbol/chart
  - Interval selection (15m/1h/4h/1d/1w) with 1w backend support
  - Lookback presets (1W/1M/3M/6M)
  - Live 30s polling for latest candle
affects: [orderblock-chart-enhancements, chart-overlays, chart-indicators]

# Tech tracking
tech-stack:
  added: []
  patterns: [full-viewport chart with floating toolbar, live polling via update()]

key-files:
  created:
    - frontend/src/components/Chart.jsx
    - frontend/src/components/Chart.css
  modified:
    - backend/app/services/orderblock_data_service.py
    - frontend/src/App.jsx
    - frontend/src/components/SymbolLayout.jsx

key-decisions:
  - "contextCandles: 20 (backend minimum) for both initial fetch and polling"
  - "Chart negates .content padding for edge-to-edge viewport fill"
  - "Polling uses update() per-candle for efficient latest-bar merge"

patterns-established:
  - "Full-viewport chart: negative margin to negate .content padding"
  - "Floating toolbar pattern: absolute positioned, semi-transparent dark bg with backdrop-filter blur"

requirements-completed: [CHART-01, CHART-02, CHART-07]

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 25 Plan 01: Chart Page Route, Component & Backend Interval Support Summary

**Full-page OHLCV candlestick chart with floating interval/lookback toolbar, volume histogram overlay, and 30s live polling via lightweight-charts**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T17:58:49Z
- **Completed:** 2026-02-28T18:02:04Z
- **Tasks:** 4
- **Files modified:** 5

## Accomplishments
- Dedicated Chart page at /s/:symbol/chart with full-viewport candlestick chart using lightweight-charts
- Floating toolbar with interval buttons (15m/1h/4h/1d/1w) and lookback presets (1W/1M/3M/6M)
- Volume histogram overlaid behind candles with semi-transparent directional coloring
- 30s live polling updates latest candle(s) in-place via update() without full data refetch
- Backend INTERVAL_MS extended with 1w (604,800,000ms) for weekly candle support

## Task Commits

Each task was committed atomically:

1. **Task 1: Add 1w interval to backend ALLOWED_INTERVALS** - `f23de36` (feat)
2. **Task 2: Add Chart route to App.jsx and nav link to SymbolLayout.jsx** - `019bb83` (feat)
3. **Task 3: Create Chart.jsx with full-page candlestick chart, floating toolbar, and live polling** - `653cdf2` (feat)
4. **Task 4: Create Chart.css with full-viewport layout and floating toolbar styles** - `62a7da7` (feat)

## Files Created/Modified
- `backend/app/services/orderblock_data_service.py` - Added "1w": 604_800_000 to INTERVAL_MS
- `frontend/src/App.jsx` - Imported Chart, added /chart route as SymbolLayout child
- `frontend/src/components/SymbolLayout.jsx` - Added Chart NavLink in Trading group after TradeLots
- `frontend/src/components/Chart.jsx` - Full-page candlestick chart with floating toolbar and live polling
- `frontend/src/components/Chart.css` - Full-viewport layout, floating toolbar, loading/error states

## Decisions Made
- Used contextCandles: 20 (backend minimum validation ge=20) for both initial fetch and polling requests
- Chart page negates .content wrapper padding (margin: -20px, width: calc(100% + 40px)) for true edge-to-edge viewport fill
- Polling uses lightweight-charts update() method per-candle which merges if timestamp matches or appends if new

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed contextCandles validation error**
- **Found during:** Post-task verification
- **Issue:** Used contextCandles: 0 but backend endpoint requires ge=20 (FastAPI Query validation)
- **Fix:** Changed contextCandles to 20 in both initial fetch and polling fetch
- **Files modified:** frontend/src/components/Chart.jsx
- **Verification:** Frontend builds successfully
- **Committed in:** bbb34e2

**2. [Rule 2 - Missing Critical] Added edge-to-edge layout for chart page**
- **Found during:** Post-task verification
- **Issue:** .content wrapper has padding: 20px which would leave gaps around the full-viewport chart
- **Fix:** Added negative margin and expanded width to negate .content padding
- **Files modified:** frontend/src/components/Chart.css
- **Verification:** CSS correctly negates padding for full-viewport coverage
- **Committed in:** bbb34e2

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both fixes essential for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Chart page is fully functional with all required features
- Ready for future enhancements: orderblock zone overlays, technical indicators, crosshair data display

---
*Phase: 25-dedicated-chart-page*
*Completed: 2026-02-28*

## Self-Check: PASSED

All 5 created/modified files verified present. All 5 commits verified in git log.
