---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-02-28T05:59:41.653Z"
progress:
  total_phases: 1
  completed_phases: 1
  total_plans: 1
  completed_plans: 1
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-28)

**Core value:** Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System
**Current focus:** Planning next milestone

## Current Position

Milestone: v3.0 Multi-Factor Omni-Bot — SHIPPED 2026-02-28
Status: Complete (all 35 requirements satisfied, 6 phases, 17 plans)
Last activity: 2026-02-28 — Milestone v3.0 archived

Progress: [████████████████████] 100%

## Performance Metrics

**Velocity (all milestones):**
- Total plans completed: 43 (8 v1.0 + 9 v1.1 + 12 v2.0 + 13 v3.0 + 1 gap closure)
- Average duration: 3.4min
- Total execution time: 148min

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
| 16-02 | DryRunService + API Routes | 5min | 2 | 4 |
| 16-03 | Bot Dashboard + Decision Log Frontend | 12min | 2 | 10 |
| 17-01 | Combined Score Alpha Integration (TDD) | 5min | 1 | 4 |
| 17-02 | Combined Score Alpha Frontend | 2min | 1 | 2 |
| 18-01 | BotDashboard Integration Fixes | 2min | 2 | 3 |

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
- DryRunService (16-02): singleton with candle-close evaluation loop, wall-clock boundary alignment
- 6 API endpoints under /api/dry-run: status, toggle, decisions (filterable), decision detail, reset, portfolio
- Evaluation loop uses SessionLocal() (not request-scoped get_db()), asyncio.Lock for toggle/eval race
- Idempotency check prevents double-evaluation on server restart mid-interval
- 30-day auto-purge in evaluation loop, public broadcast_message() on BinanceStreamManager
- Structural isolation (DRY-05) verified: zero forbidden imports in dry_run_service.py
- Bot Dashboard (16-03): Alpha Score hero, 4 factor bars, signal history chart, dry-run toggle/reset, 6 KPI cards
- Decision Log: filterable table (date/action/symbol), expandable rows with factor bars, pagination
- Navigation restructured to 4 groups: Trading (Dashboard, Lots) / Analyse (Combined Score, Orderblocks, Backtest) / Bot (Bot Dashboard, Decision Log) / Admin (Reconciliation, Settings, API Docs)
- Backtest and Settings links moved from GlobalNav to SymbolLayout nav groups
- Dry-run nav badge: amber dot with pulse animation when dry-run active
- getAlphaScore API client function added (was missing from Phase 14 frontend)
- WebSocket handlers for dry_run_decision, dry_run_status, dry_run_portfolio_update
- Settings: dry_run_initial_capital input with 100 EUR minimum validation
- Phase 16 complete: all BOT-01 through BOT-06 and DRY-01 through DRY-05 requirements met
- Combined Score Alpha Integration (17-01): AlphaInput dataclass, 50/30/20 three-signal weights with 60/40 fallback
- Fixed three-way weights rather than user-configurable (preserves calibration, one-constant change later if needed)
- Alpha quality warmup/unavailable triggers exact existing 60/40 code path
- Combined route now loads user settings from DB (Depends(get_db)) for Alpha Score computation
- _detect_conflict extended with alpha-vs-macro divergence, _assess_quality with three-signal coverage
- Combined Score Frontend (17-02): Alpha Score sub-signal card conditionally rendered when alpha.status=ok
- Dynamic weight badges from API response (50/30/20 with Alpha, 60/40 without) -- no hardcoded percentages
- Alpha factor bars use /5 divisor (sub_scores [-5,+5]) vs Macro /2 divisor (scores [-2,+2])
- 3-column grid layout via combined-subsignals-three CSS class, responsive collapse on mobile
- Phase 17 complete: all COMB-01 and COMB-02 requirements met
- v3.0 milestone complete: phases 13-17 all done
- Phase 18 gap closure (18-01): Fixed 4 BotDashboard integration gaps from v3.0 audit
- Alpha Score field fix: score (not composite_score), trade_signal (not signal), sub_score (not score/value)
- Backtest envelope fix: backtestRuns.runs unwrapping (API returns {runs: [...], count})
- getTrailingStops API client + trailing stop display section with freeze state indicator
- getAlphaScore default symbol changed from BTCEUR to XRPBTC (Alpha Score engine designed for XRPBTC)

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-28
Stopped at: Completed 18-01-PLAN.md (BotDashboard Integration Fixes) -- Phase 18 complete
Resume file: None
