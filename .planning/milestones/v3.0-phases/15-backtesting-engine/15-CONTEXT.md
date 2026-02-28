# Phase 15: Backtesting Engine - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Historical simulation of the Alpha Score signal quality through walk-forward backtesting over configurable periods (up to 24 months). Includes performance metrics, HODL benchmark comparison, immutable result snapshots, and parameter sweep (grid search) with CSV export. Dry-run mode and live execution are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Simulation rules
- **Position sizing**: Fixed fraction of current portfolio (compounding)
- **Position management**: Single position per symbol at a time — new signals while position open are ignored
- **Entry trigger**: Long-only above configurable threshold (matches Spot reality — no short positions)
- **Exit mechanism**: Full trailing stop simulation using Phase 14's ATR-adaptive trailing stop, tick-by-tick on historical candles
- **Backtest method**: Simple in-sample (not walk-forward). Full period simulation.
- **Data resolution**: Match Alpha Score's configured candle interval from user settings

### Warmup & data handling
- **Warmup**: Auto-skip warmup candles needed by indicators (e.g. 200 for 200-DMA). No trades during warmup, shown as grayed-out period on equity curve.
- **Data fetching**: Fetch extra historical data before user's chosen start date to satisfy warmup buffer. Trading starts exactly at user's start date — full requested period is tradeable.

### Results presentation
- **Navigation**: Standalone "Backtest" page in navigation (not embedded in Alpha Score page)
- **Equity curve**: Line chart with HODL benchmark overlaid — visual comparison at a glance
- **Drawdown chart**: Underwater area chart below equity curve showing drawdown percentage over time
- **Monthly returns**: Color-coded heatmap grid (months as columns, years as rows, red-to-green)
- **Trade distribution**: P&L histogram showing distribution of individual trade returns
- **Trade list**: Expandable trade table (collapsed by default) — entry/exit date, price, P&L, duration, Alpha Score at entry
- **Backtest history**: Collapsible run cards (key metrics visible, click to expand full details + equity curve). Similar to existing Orderblock backtest pattern.
- **Initial capital**: Configurable by user (input field in backtest form)

### Parameter sweep
- **Configuration**: Form with range inputs (min, max, step) per parameter. Shows estimated combination count before running.
- **Sweepable parameters**: Core scoring params — Z-Score lookback, factor weights, trade threshold, trailing stop ATR multiplier
- **Results display**: Sortable table with one row per combination (return, Sharpe, drawdown, trade count). CSV export button.
- **Safeguard**: Warn above ~100 combinations, hard cap at ~500. Confirmation dialog before sweep starts.

### Cost & slippage model
- **Fees**: Configurable flat rate applied to both entry and exit. Default: 0.1% (Binance Spot standard tier).
- **Slippage**: Configurable percentage added to entry price, subtracted from exit. Default: 0.05%.
- **Display**: Fees and slippage shown as separate line items in results (not just baked into net P&L). Total fees paid and total slippage cost visible as distinct metrics.

### Progress & execution
- **Execution**: Server-side (backend API runs simulation, not browser)
- **Progress streaming**: Via existing WebSocket infrastructure (WebSocketContext.jsx). Real-time progress bar with percentage, elapsed time, live counters (candles processed, trades found). For sweeps: X/N combinations done.
- **Cancellation**: Cancel button during execution. For sweeps: partial results up to cancellation are kept and displayed.

### Benchmark
- **Composition**: Always 50/50 BTC/XRP HODL regardless of which symbol is tested
- **Rebalancing**: Static buy-and-hold from day 1 — no periodic rebalancing
- **Transaction costs**: Benchmark incurs same fee rate on initial purchase (fair comparison)
- **Display**: Benchmark as overlay line on equity curve + separate delta metrics (excess return, relative Sharpe)

### Claude's Discretion
- Exact chart library choices (Recharts vs. lightweight-charts for equity curve)
- Progress bar implementation details
- WebSocket message format for backtest progress
- Exact warmup candle count derivation from Phase 14 indicator config
- Sweep combination cap exact numbers
- Internal backtest engine architecture (pure domain vs. service split)

</decisions>

<specifics>
## Specific Ideas

- Backtest history should follow existing Orderblock backtest run pattern (collapsible cards with immutable snapshots)
- Monthly returns heatmap inspired by standard quant dashboard patterns
- Underwater drawdown chart is standard quant tooling — immediately shows risk periods
- P&L histogram helps understand whether profits come from many small wins or few big ones

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-backtesting-engine*
*Context gathered: 2026-02-27*
