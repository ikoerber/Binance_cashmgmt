# Phase 25: Dedicated Chart Page - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Full-page interactive OHLCV candlestick chart for the current symbol, accessible from the Trading nav group inside SymbolLayout. Includes interval selection, lookback period controls, and a volume histogram. Overlays (orderblocks, break-even, sell orders, trailing stops) are Phase 26.

</domain>

<decisions>
## Implementation Decisions

### Chart layout & sizing
- Chart fills the remaining viewport below the sub-nav bar — no fixed height, resizes with browser window
- Chart only — no additional header, info bar, or sidebar. Price info already visible in SymbolLayout's live ticker
- Volume histogram overlaid behind candles (semi-transparent, same pane) — matches existing OrderblockChart pattern, maximizes candlestick space

### Controls placement
- Top-right floating toolbar over the chart — interval buttons + lookback controls
- No separate bar above the chart — keep it TradingView-style minimal

### Intervals
- 15m, 1h, 4h, 1d, 1w — broader than roadmap's minimum (1h/4h/1d), user requested 15m and 1w additions
- Default interval: 1h

### Lookback
- Claude's Discretion — presets (1w/1m/3m/6m buttons) or dropdown, whatever fits the toolbar design best

### Live updates
- Poll for latest candle periodically (e.g., every 30s) to keep chart current
- No full refetch — just update/append the latest candle

### Data source
- Reuse existing `/api/orderblock/{user_id}/candles` endpoint — already supports time-range queries with `start_time` + `end_time`, returns `{time, open, high, low, close, volume}` format compatible with lightweight-charts
- No new backend endpoint needed

### Navigation placement
- Chart link in Trading nav group, after TradeLots: Trading → Dashboard, TradeLots, Chart
- Route: `/s/:symbol/chart`

### Claude's Discretion
- Lookback control design (presets vs dropdown)
- Loading state / skeleton while candles fetch
- Error state when candle fetch fails
- 15m and 1w interval backend validation (may need to add to allowed intervals in orderblock.py)

</decisions>

<specifics>
## Specific Ideas

No specific requirements — standard TradingView-style chart page using existing lightweight-charts library.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `OrderblockChart.jsx`: Complete lightweight-charts setup with candlestick series, volume histogram, dark theme, crosshair, timezone handling. Can serve as reference/template for the new chart component.
- `useChartTheme` hook: Returns theme colors for chart (profit/loss, bg, text, borders). Already used by OrderblockChart.
- `getOrderblockCandles()` API function: Supports `start_time + end_time` mode without `zone_id`. Returns candle array in correct format.
- `lightweight-charts` library: Already in `package.json` with `CandlestickSeries`, `HistogramSeries`, `ColorType`, `CrosshairMode` imports proven.

### Established Patterns
- Chart creation: `createChart()` → `addSeries(CandlestickSeries)` → `addSeries(HistogramSeries)` → `setData()`. Cleanup via `chart.remove()` in useEffect return.
- Timezone conversion: `TZ_OFFSET_SEC = new Date().getTimezoneOffset() * -60` applied to candle timestamps for local display.
- Volume coloring: Semi-transparent, color-matched to candle direction (green bullish, red bearish).

### Integration Points
- `App.jsx`: Add `<Route path="chart" element={<Chart />} />` as SymbolLayout child (alongside dashboard, lots, etc.)
- `SymbolLayout.jsx`: Add Chart NavLink to Trading group after TradeLots (currently lines 41-45)
- `SymbolContext`: Provides `symbol` for the candle API call — chart component reads from context or useParams

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 25-dedicated-chart-page*
*Context gathered: 2026-02-28*
