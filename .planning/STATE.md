---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Multi-Factor Omni-Bot
status: unknown
last_updated: "2026-02-26T06:12:35.041Z"
progress:
  total_phases: 2
  completed_phases: 2
  total_plans: 7
  completed_plans: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-25)

**Core value:** Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System
**Current focus:** Phase 15 — Backtesting Engine

## Current Position

Milestone: v3.0 Multi-Factor Omni-Bot
Phase: 15 of 17 (Backtesting Engine)
Plan: 1 of 4 complete
Status: In Progress
Last activity: 2026-02-27 — Completed 15-01-PLAN.md (Pure Domain Backtest Engine)

Progress: [█████░░░░░░░░░░░░░░░] 25%

## Performance Metrics

**Velocity (all milestones):**
- Total plans completed: 37 (8 v1.0 + 9 v1.1 + 12 v2.0 + 8 v3.0)
- Average duration: 3.3min
- Total execution time: 134min

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
- Backtest engine (15-01): pure domain module, 946 lines, 48 tests, zero float contamination
- Degraded Alpha Score in backtest: orderbook + funding marked unavailable, Z-Score + Lead-Lag renormalized
- Equity curve downsampled to daily (max ~730 points for 24 months)
- Benchmark 50/50 BTC/XRP HODL with same fee_rate on purchase
- Candle dict format: {open_time, open, high, low, close, volume} all Decimal

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-27
Stopped at: Completed 15-01-PLAN.md
Resume file: None
