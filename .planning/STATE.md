# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-25)

**Core value:** Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System
**Current focus:** Phase 14 — Multi-Factor Scoring Engine

## Current Position

Milestone: v3.0 Multi-Factor Omni-Bot
Phase: 14 of 17 (Multi-Factor Scoring Engine)
Plan: 3 of 4 complete
Status: In Progress
Last activity: 2026-02-26 — Completed 14-03-PLAN.md (Hurst Regime + Aggregation + Trailing Stops)

Progress: [███████████████░░░░░] 75%

## Performance Metrics

**Velocity (all milestones):**
- Total plans completed: 35 (8 v1.0 + 9 v1.1 + 12 v2.0 + 6 v3.0)
- Average duration: 3.2min
- Total execution time: 121min

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 13-01 | Symbol Registry + Migration + Domain | 4min | 2 | 6 |
| 13-02 | Sync Pipeline + Pairing/Order Guards | 4min | 2 | 6 |
| 13-03 | Frontend Dual Display + Pairing Isolation | 5min | 2 | 9 |
| 14-01 | Four Independent Factor Computations (TDD) | 4min | 1 | 2 |
| 14-02 | Alpha Score Settings Pipeline | 5min | 2 | 5 |
| 14-03 | Hurst Regime + Aggregation + Trailing Stops (TDD) | 5min | 1 | 2 |

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

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-25
Stopped at: Completed 14-01-PLAN.md
Resume file: None
