---
phase: 14-multi-factor-scoring-engine
plan: 01
subsystem: domain
tags: [alpha-score, z-score, lead-lag, orderbook-imbalance, funding-rate, decimal, tdd]

# Dependency graph
requires:
  - phase: 13-xrpbtc-infrastructure
    provides: "XRPBTC symbol registry, sync pipeline, BTC-quoted pair support"
provides:
  - "Pure domain module with 4 independent factor computation functions"
  - "AlphaFactorScore, ZScoreResult, LeadLagResult, OrderbookImbalanceResult, FundingRateResult dataclasses"
  - "Decimal-only Pearson correlation helper for cross-series analysis"
  - "39 tests covering normal, edge, and boundary cases for all 4 factors"
affects: [14-02-PLAN, 14-03-PLAN, 14-04-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: [pure-domain-factor-computation, decimal-pearson-correlation, subscore-clamping]

key-files:
  created:
    - backend/app/domain/alpha_score.py
    - backend/tests/test_alpha_score.py
  modified: []

key-decisions:
  - "Lead-Lag signal uses recent 5-candle BTC/XRP divergence scaled by cross-correlation magnitude, not raw correlation value alone"
  - "Funding rate divergence (BTC vs asset) weighted at 30% of base signal to avoid overwhelming the primary contrarian signal"
  - "Orderbook imbalance uses linear mapping from [-1, +1] ratio to [-5, +5] sub-score (simplest correct mapping)"
  - "Pearson correlation implemented in pure Decimal with zero-variance guards (no numpy dependency)"

patterns-established:
  - "Alpha Score factor pattern: pure function returning typed Result dataclass with sub_score, quality, and raw values"
  - "Sub-score clamping: all factors use _clamp_subscore() to enforce [-5, +5] invariant"
  - "Warmup pattern: insufficient data returns quality='warmup' with sub_score=0 (never compute partial scores)"

requirements-completed: [SCORE-01, SCORE-02, SCORE-03, SCORE-04]

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 14 Plan 01: Four Independent Factor Computations Summary

**Pure Decimal domain module with Z-Score Mean Reversion, Lead-Lag Momentum, Orderbook Imbalance, and Funding Rate factor computations -- 39 tests, zero float contamination**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T22:33:20Z
- **Completed:** 2026-02-25T22:37:18Z
- **Tasks:** 1 (TDD: RED -> GREEN -> REFACTOR)
- **Files modified:** 2

## Accomplishments
- All 4 factor computation functions implemented as pure domain logic with Decimal-only math
- Each factor handles warmup (insufficient data) and unavailable (None input) cases correctly
- Sub-scores always clamped to [-5, +5] range
- 39 tests cover normal operation, edge cases, boundary conditions, and type correctness
- Zero float contamination verified (grep confirms 0 occurrences of float() in domain module)

## Task Commits

Each task was committed atomically (TDD pattern):

1. **RED: Failing tests** - `b5a8525` (test) - 39 test cases for all 4 factors
2. **GREEN: Implementation** - `8fd97f5` (feat) - All 4 compute functions + 5 dataclasses
3. **REFACTOR: Cleanup** - `0a4beda` (refactor) - Remove unused import

## Files Created/Modified
- `backend/app/domain/alpha_score.py` - Pure domain module: 4 factor computations, 5 dataclasses, 4 helpers (476 lines)
- `backend/tests/test_alpha_score.py` - 39 tests: 9 Z-Score, 8 Lead-Lag, 10 Orderbook, 10 Funding Rate, 2 dataclass (439 lines)

## Decisions Made
- Lead-Lag signal computed from recent 5-candle BTC/XRP return divergence scaled by cross-correlation magnitude at best lag. This captures the "BTC moved but XRP hasn't followed" pattern more directly than raw correlation alone.
- Funding rate BTC divergence weighted at 30% of base signal to keep the primary contrarian signal dominant while still incorporating relative information.
- Pearson correlation implemented in pure Decimal with explicit zero-variance guards, avoiding any numpy dependency.
- Correlation threshold set at 0.3 for Lead-Lag (lower than research suggestion of 0.5) to avoid missing moderate signals.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Domain module ready for Plan 02 (Hurst R/S regime detection + Alpha Score aggregation)
- All 4 factor functions can be imported and called by the aggregation layer
- AlphaFactorScore dataclass provides the standard interface for factor-to-aggregation communication

## Self-Check: PASSED

- FOUND: backend/app/domain/alpha_score.py
- FOUND: backend/tests/test_alpha_score.py
- FOUND: 14-01-SUMMARY.md
- FOUND: b5a8525 (RED commit)
- FOUND: 8fd97f5 (GREEN commit)
- FOUND: 0a4beda (REFACTOR commit)

---
*Phase: 14-multi-factor-scoring-engine*
*Completed: 2026-02-25*
