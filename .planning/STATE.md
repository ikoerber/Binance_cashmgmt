---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Multi-Factor Omni-Bot
status: in-progress
last_updated: "2026-02-27T16:14:58.579Z"
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 14
  completed_plans: 12
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-25)

**Core value:** Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System
**Current focus:** Phase 16 — Dry-Run Mode & Bot Dashboard

## Current Position

Milestone: v3.0 Multi-Factor Omni-Bot
Phase: 16 of 17 (Dry-Run Mode & Bot Dashboard)
Plan: 1 of 3 complete
Status: In Progress
Last activity: 2026-02-27 — Completed 16-01-PLAN.md (Dry-Run Backend Foundation)

Progress: [██████░░░░░░░░░░░░░░] 33%

## Performance Metrics

**Velocity (all milestones):**
- Total plans completed: 40 (8 v1.0 + 9 v1.1 + 12 v2.0 + 11 v3.0)
- Average duration: 3.4min
- Total execution time: 139min

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 13-01 | Symbol Registry + Migration + Domain | 4min | 2 | 6 |
| 13-02 | Sync Pipeline + Pairing/Order Guards | 4min | 2 | 6 |
| 13-03 | Frontend Dual Display + Pairing Isolation | 5min | 2 | 9 |
| 14-01 | Four Independent Factor Computations (TDD) | 4min | 1 | 2 |
| 14-02 | Alpha Score Settings Pipeline | 5min | 2 | 5 |
| 14-03 | Hurst Regime + Aggregation + Trailing Stops (TDD) | 5min | 1 | 2 |
| 14-04 | Data Service + API Routes | 5min | 2 | 3 |
| 15-01 | Pure Domain Backtest Engine (TDD) | 8min | 1 | 2 |
| 15-02 | Backtest Persistence + Service + API | 5min | 2 | 5 |
| 15-03 | Frontend Backtest Page | 5min | 2 | 5 |
| 15-04 | Parameter Sweep + Progress + CSV Export | 8min | 2 | 6 |
| 16-01 | Dry-Run Backend Foundation | 5min | 2 | 4 |

## Accumulated Context

v2.0 decision log archived in milestones/v2.0-phases/ SUMMARY.md files.
v1.1 decision log archived in milestones/v1.1-phases/ SUMMARY.md files.
v1.0 decision log archived in milestones/v1.0-phases/ SUMMARY.md files.

### Key Context for v3.0

- XRPBTC re-added in Phase 13-01: KNOWN_PAIRS entry, is_eur_quoted/is_pairing_enabled/is_order_creation_enabled helpers
- `quote_to_eur_rate` column re-added via migration b2f6ed7bb098 (570 EUR lots backfilled with rate=1.0)
- BTC-quoted lots get cost_eur=None from domain; service layer fills after historical rate fetch
- Only quote_to_eur_rate re-added (not pairing columns) -- pairing disabled for XRPBTC
- Existing Combined Score is user-calibrated -- Alpha Score integration must be last phase
- numpy 2.2.6 is the only new backend dependency (Decimal boundary pattern: Decimal in, numpy compute, Decimal out)
- Sync pipeline enriches XRPBTC lots with historical BTC/EUR rate (minute-cached, graceful fallback to cost_eur=None)
- Three-layer pairing/order isolation: symbol_registry -> service guard -> API route guard
- Backfill script fixed: Decimal precision (no float), default DB=sqlite
- Frontend XRPBTC: amber pill (#f7931a), dual BTC/EUR display, pairing/order UI hidden, low-liquidity notice
- Live BTCEUR price from WebSocket for EUR conversion of BTC-quoted pair P&L (useWebSocket().prices['BTCEUR'])
- Phase 13 complete: full XRPBTC infrastructure (backend + frontend)
- Alpha Score domain module (14-01): pure Decimal factor computations -- no numpy, no float
- Four factors: Z-Score Mean Reversion, Lead-Lag Momentum, Orderbook Imbalance, Funding Rate Score
- Lead-Lag uses 5-candle divergence * cross-correlation (threshold 0.3), not raw correlation
- Funding rate BTC divergence weighted at 30% of base contrarian signal
- Pearson correlation in pure Decimal with zero-variance guards
- All sub-scores clamped to [-5, +5], warmup quality for insufficient data
- Alpha Score Settings (14-02): 14 alpha_score_* columns, weight auto-normalization, essential/advanced UI layout
- Settings validation: weights 0-100, threshold 0.1-5.0, windows 10-500, Hurst 0-1, ATR 0.5-10
- Indigo accent for Alpha Score settings section, collapsible advanced toggle
- Hurst R/S (14-03): regime detection (trending/mean-reverting/transitional), float only for log-log regression
- Regime-adjusted weights: gradual blend 0.45-0.55, freed Z-Score weight redistributed 60/30/10
- Alpha Score composite: weighted aggregation, renormalization, LONG/SHORT/NEUTRAL signals, quality levels
- Trailing stop: ratchet + ATR floor, freeze on stale data, resume after N fresh points, immutable state
- AlphaScoreDataService (14-04): singleton with mixed refresh cadences (candle-driven vs real-time)
- EMA-smoothed orderbook imbalance (alpha=0.4, 5 snapshots) reduces point-in-time noise
- Own OKX funding rate cache (not shared with SentimentDataService, avoids cross-service coupling)
- Portfolio-aware stop tightening: correlation > 0.7 triggers up to 15% ATR distance reduction
- XRPEUR trailing stop from XRPBTC ATR * BTCEUR price (no extra API call)
- GET /api/alpha-score/{user_id}/score: full Alpha Score with factor breakdown and regime info
- GET /api/alpha-score/{user_id}/trailing-stops: per-symbol stop levels with freeze/resume state
- Phase 14 complete: all SCORE-01 through SCORE-09 and EXIT-01/EXIT-02 requirements met
- **IMPORTANT**: Combined Score page is inside /s/:symbol route (symbol-specific), Backtest is standalone /backtest (symbol-agnostic at entry)
- Backtest engine (15-01): pure domain module, 946 lines, 48 tests, zero float contamination
- Degraded Alpha Score in backtest: orderbook + funding marked unavailable, Z-Score + Lead-Lag renormalized
- Equity curve downsampled to daily (max ~730 points for 24 months)
- Benchmark 50/50 BTC/XRP HODL with same fee_rate on purchase
- Candle dict format: {open_time, open, high, low, close, volume} all Decimal
- AlphaBacktestRunDB (15-02): immutable snapshots, key metrics as queryable columns + JSON blobs
- BacktestDataService singleton: paginated kline fetch (3 series), domain orchestration, persistence, cancellation
- XRPEUR fallback: derive from XRPBTC * BTCEUR via open_time matching when direct data unavailable
- 4 API endpoints: POST run, GET runs (list), GET run detail, POST cancel -- all with API key auth
- excess_return_pct computed at persistence time (net_return - benchmark_return)
- Frontend Backtest page (15-03): standalone /backtest route, indigo accent, Recharts equity curve + benchmark overlay
- Parameter Sweep (15-04): grid search via itertools.product, shared candle fetch, hard cap 500 combinations
- Sweep progress via WebSocket: backtest_progress message with phase/combination counters, auto-reset after 2s
- CSV export uses fetch+blob with X-API-Key header (not direct link)
- _build_backtest_config extracted for reuse between single-run and sweep
- Phase 15 complete: all BT-01 through BT-07 requirements met
- Backtest form converts user-friendly percentages to API decimals at mutation time
- History runs use lazy detail loading: expand card to fetch equity curve + trades
- Monthly heatmap uses CSS Grid (not Recharts) for cell-level color control
- Dry-run domain module (16-01): pure Decimal, no I/O, mirrors backtest engine cost model
- VirtualPosition, VirtualPortfolioState, VirtualTradeResult, DecisionContext dataclasses
- 7 pure functions: compute_position_size, execute_virtual_buy/sell, compute_virtual_equity, determine_action, should_enter/exit_trade
- 3 isolated DB tables: dry_run_decisions (signal log), dry_run_portfolios (state), dry_run_positions (open positions)
- DryRunDecisionDB stores full alpha score context (factor scores, regime, trailing stop) for audit trail
- Alembic migration dr01_dry_run_tab: creates 3 tables + dry_run_initial_capital on user_settings
- Settings API: dry_run_initial_capital (100-10M EUR), String transport, validated Decimal

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-27
Stopped at: Completed 16-01-PLAN.md
Resume file: None
