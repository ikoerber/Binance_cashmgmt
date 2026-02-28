# Phase 26: Chart Overlays - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Add 4 overlay types to the dedicated Chart page (Phase 25): orderblock zones, portfolio break-even price, open sell order prices, and active trailing stop levels. Each overlay must be visually distinguishable. Phase does NOT add new data endpoints — all data sources already exist.

</domain>

<decisions>
## Implementation Decisions

### Overlay visual design
- Break-even line: Claude's Discretion — pick best style based on chart theme and existing patterns (solid/dashed, color choice)
- Sell orders: Clustered/grouped lines — orders within a small price range merged into a single thicker line with count badge (e.g., "3 orders"), not individual lines per order
- Trailing stop: Claude's Discretion — pick distinct style that signals "dynamic level" (this moves with price)
- All overlay types must be visually distinct from each other and from candles/volume

### Zone rendering
- Show UNMITIGATED + MITIGATED zones (not INVALID)
- UNMITIGATED zones at full opacity, MITIGATED zones dimmed/faded
- Zones are shaded rectangles between zone_top and zone_bottom
- Claude's Discretion: conviction-based styling (e.g., higher conviction = more opaque), zone direction coloring (bullish green, bearish red)

### Toggle controls
- All overlays on by default
- Each overlay type individually toggleable via buttons in the floating toolbar
- Toggle buttons added to the existing toolbar (alongside interval/lookback controls)

### Claude's Discretion
- Exact colors for break-even, trailing stop, and sell order lines
- Line styles (solid vs dashed vs dotted) per overlay type
- Toggle button icons/labels and toolbar layout expansion
- Zone label content (conviction score, direction indicator, etc.)
- Data refresh strategy for overlay data (polling interval, when to refetch)
- Whether trailing stops only appear when bot/dry-run is active, or always (showing "no active stop" state)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `OrderblockChart.jsx`: Complete overlay pattern — `createPriceLine()` for horizontal lines, `createSeriesMarkers()` for point markers, ref arrays for cleanup. Direct template for all 4 overlay types.
- `useChartTheme` hook: Rich color palette including `accentBlue` (#60a5fa), `accentOrderblock` (#fbbf24), `profit`/`loss` for directional coloring, `hexToRgb()` for rgba.
- `LineStyle` import from lightweight-charts: Solid, Dashed, Dotted, SparseDotted — available for visual distinction.

### Established Patterns
- Price lines: `series.createPriceLine({ price, color, lineWidth, lineStyle, axisLabelVisible, title })` — tracked in `useRef([])` array, removed in cleanup.
- Markers: `createSeriesMarkers(series, sortedMarkers)` — tracked in single ref, detached via `series.detachPrimitive()`.
- Timezone: `TZ_OFFSET_SEC` applied to all timestamps for local display.
- Cleanup: Always remove/detach overlays in useEffect return to prevent memory leaks.

### Integration Points
- `Chart.jsx` has `chartRef`, `candleSeriesRef`, `volumeSeriesRef` — overlays attach to `candleSeriesRef.current` via `createPriceLine()`.
- Existing API functions in `client.js`: `getPortfolio(userId)` for break-even, `getOrderblockZones(userId, params)` for zones, `getOrdersForUser(userId, params)` for sell orders, `getTrailingStops(userId)` for trailing stop levels.
- Floating toolbar in `Chart.jsx` already has interval + lookback groups — toggle buttons extend this toolbar.
- `useSymbol()` and `useUser()` contexts already available in Chart.jsx for API calls.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — standard TradingView-style overlay rendering using existing lightweight-charts primitives and data sources.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 26-chart-overlays*
*Context gathered: 2026-02-28*
