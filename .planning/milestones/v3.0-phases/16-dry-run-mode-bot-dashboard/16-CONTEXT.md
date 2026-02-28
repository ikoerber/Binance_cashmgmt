# Phase 16: Dry-Run Mode + Bot Dashboard - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Real-time paper trading mode where the Alpha Score engine evaluates signals and logs decisions without placing any real Binance orders. Virtual portfolio tracks positions and P&L in separate tables, fully isolated from the production ledger. A new Bot navigation section provides a unified dashboard for observing the scoring engine. Live execution is a separate future phase.

</domain>

<decisions>
## Implementation Decisions

### Signal logging & decisions
- **Detail level**: Full factor breakdown per entry — all 4 Alpha Score factors with individual scores, composite Alpha Score, trailing stop levels, current price, action taken (BUY/HOLD/SELL/NO_SIGNAL), and reason text
- **Evaluation frequency**: Every candle close matching the Alpha Score interval (e.g. every 15m). Produces ~96 entries/day at 15m interval.
- **Retention**: 30 days rolling, auto-purge older entries
- **Display**: Filterable table (columns: time, action, Alpha Score, price, reason) with date range, action type, symbol filters. Above it: time-series chart showing Alpha Score over time with buy/sell markers.

### Virtual portfolio behavior
- **Initial capital**: Configurable by user in Settings (same pattern as backtest initial capital). Can be reset anytime.
- **Cost model**: Reuse backtest fee rate (default 0.1%) and slippage (default 0.05%) from Phase 15. Consistent with backtest results for fair comparison.
- **Position sizing**: Fixed fraction of virtual equity per trade (compounding) — same model as backtest engine
- **Reset**: Reset button in Bot section with confirmation dialog. Wipes virtual positions and P&L. Decision log stays (separate concern).

### Dry-run activation & safety
- **Toggle location**: Prominent toggle at the top of the Bot Dashboard header. Always visible when in Bot view.
- **Confirmation**: No confirmation dialog needed — dry-run is a safe mode that never places real orders. Simple toggle on/off.
- **Active indicators**: Persistent amber banner at top of Bot section: "DRY-RUN MODE — No real orders". Plus a small badge on the Bot nav item when active.
- **Structural enforcement (DRY-05)**: Dry-run service has NO import/reference to order-placing code. Bot Dashboard has no "Place Order" buttons. The structural guarantee is invisible — there's simply nothing to click.

### Bot Dashboard layout
- **Visual hierarchy**: Hero section at top with large Alpha Score display + factor bars + dry-run status toggle/banner. Middle: Signal history chart (time series). Bottom: KPI cards (virtual P&L, trade count, win rate, last backtest summary, regime indicator).
- **Factor bars**: Horizontal bars with labels for each of the 4 factors (Z-Score, Lead-Lag, Orderbook, Funding). Similar to sentiment pillar bars in Combined Score page.
- **Navigation**: 4 nav groups — Trading (Dashboard, Lots) / Analyse (Combined Score, Orderblocks, Backtest) / Bot (Bot Dashboard, Decision Log) / Admin (Reconciliation, Settings, API Docs)
- **Real-time updates**: WebSocket for Alpha Score, virtual P&L, and dry-run status. Signal history chart updates when new decisions are logged.

### Claude's Discretion
- Regime indicator visual design (badge, icon, or chart annotation)
- Backtest summary widget format (which metrics to surface from most recent run)
- Decision log expandable row design (how factor details are shown on drill-down)
- Color scheme for Bot section (existing app palette or distinct accent)
- Signal history chart type (line chart vs. area chart vs. candlestick background)

</decisions>

<specifics>
## Specific Ideas

- Factor bars should follow the same visual pattern as sentiment pillar bars in the existing Combined Score page
- 4-group navigation restructure (Trading/Analyse/Bot/Admin) aligns with the roadmap's "4th area" specification
- Virtual portfolio must stay completely isolated from production ledger — separate DB tables, never appear on main Dashboard

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 16-dry-run-mode-bot-dashboard*
*Context gathered: 2026-02-27*
