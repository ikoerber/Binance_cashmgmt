---
phase: 15-backtesting-engine
plan: 01
subsystem: domain
tags: [backtest, simulation, alpha-score, sharpe, drawdown, benchmark, decimal, trailing-stop, tdd]

# Dependency graph
requires:
  - phase: 14-multi-factor-scoring-engine
    provides: "Alpha Score domain functions (Z-Score, Lead-Lag, Hurst, ATR, trailing stop)"
provides:
  - "Pure domain backtest engine with simulation loop, metrics, benchmark (backtest_engine.py)"
  - "48-test comprehensive test suite for backtest engine (test_backtest_engine.py)"
  - "BacktestConfig, TradeRecord, EquityPoint, MonthlyReturn, BenchmarkResult, BacktestMetrics, BacktestResult dataclasses"
  - "compute_warmup_period, compute_sharpe_ratio, compute_max_drawdown, compute_monthly_returns, compute_benchmark, run_alpha_backtest functions"
affects: [15-02, 15-03, 15-04, backtest-data-service, backtest-api, backtest-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure domain backtest simulation (no I/O, all Decimal)"
    - "Degraded Alpha Score computation (2/4 factors, weight renormalization)"
    - "Candle-by-candle trailing stop simulation using Phase 14 primitives"
    - "Daily equity curve downsampling for storage efficiency"

key-files:
  created:
    - backend/app/domain/backtest_engine.py
    - backend/tests/test_backtest_engine.py
  modified: []

key-decisions:
  - "Zero float contamination: all financial math in Decimal, only math.sqrt for Sharpe annualization"
  - "Degraded Alpha Score: orderbook + funding marked unavailable, weights auto-renormalized via existing compute_alpha_score()"
  - "Equity curve downsampled to daily granularity to keep data compact (max ~730 points for 24 months)"
  - "Benchmark 50/50 BTC/XRP HODL with same fee_rate on initial purchase for fair comparison"
  - "Single position per symbol: new signals while position open are ignored (prevents overlapping trades)"
  - "Compounding position sizing: position_fraction * current_equity (user decision from CONTEXT.md)"

patterns-established:
  - "Backtest simulation loop pattern: warmup -> iterate candles -> compute signals -> manage positions -> record equity"
  - "TDD for domain modules: RED (failing tests) -> GREEN (implementation) -> REFACTOR (linting, cleanup)"
  - "Candle dict format: {open_time: datetime, open: Decimal, high: Decimal, low: Decimal, close: Decimal, volume: Decimal}"

requirements-completed: [BT-01, BT-02, BT-03, BT-04]

# Metrics
duration: 8min
completed: 2026-02-27
---

# Phase 15 Plan 01: Backtest Engine Summary

**Pure domain backtest engine with Alpha Score signal simulation, trailing stop exits, Sharpe/drawdown/win-rate metrics, 50/50 HODL benchmark, and 48-test TDD suite -- all in Decimal precision**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-27T14:25:45Z
- **Completed:** 2026-02-27T14:33:22Z
- **Tasks:** 1 (TDD: RED + GREEN + REFACTOR)
- **Files created:** 2

## Accomplishments
- Pure domain backtest engine (946 lines) with simulation loop, metrics, and benchmark
- 48 tests (939 lines) covering all categories: config validation, warmup, signal entry, trailing stop exit, equity curve, performance metrics, monthly returns, benchmark, degraded alpha score, cancellation, edge cases
- Zero float contamination in financial calculations (verified by grep)
- No I/O imports in domain module (only stdlib + alpha_score domain)
- Full regression-safe: 782 total backend tests pass (734 existing + 48 new)

## Task Commits

Each task was committed atomically (TDD pattern):

1. **Task 1 RED: Failing tests** - `da0ecd8` (test)
2. **Task 1 GREEN+REFACTOR: Implementation** - `4232c21` (feat)

## Files Created/Modified
- `backend/app/domain/backtest_engine.py` - Pure domain backtest engine: simulation loop, metrics computation, benchmark, monthly returns, warmup handling, cancellation
- `backend/tests/test_backtest_engine.py` - 48 tests across 11 categories: config validation, warmup, signals, trailing stops, equity curve, metrics, monthly returns, benchmark, degraded mode, cancellation, edge cases

## Decisions Made
- Used existing `compute_alpha_score()` graceful degradation for backtesting (mark orderbook + funding as "unavailable", auto-renormalize weights)
- Entry price = candle close * (1 + slippage_pct), exit price = stop_level * (1 - slippage_pct)
- Entry cost = entry_price * qty * (1 + fee_rate), exit proceeds = exit_price * qty * (1 - fee_rate)
- Benchmark buys at start_index (after warmup), not at candle 0
- Monthly returns use rolling equity (end-of-previous-month as start for next month)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed sum() on empty trade list returning int instead of Decimal**
- **Found during:** Task 1 GREEN phase
- **Issue:** `sum(t.fees_paid for t in trades)` returns `int(0)` when trades list is empty, causing AttributeError on `.quantize()`
- **Fix:** Changed to `sum((t.fees_paid for t in trades), Decimal("0"))` to ensure Decimal return type
- **Files modified:** backend/app/domain/backtest_engine.py
- **Verification:** All tests pass including zero-trade edge cases
- **Committed in:** 4232c21

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backtest engine domain module complete and tested
- Ready for Plan 02: Persistence layer (AlphaBacktestRunDB table, service layer)
- Ready for Plan 03: API routes and WebSocket progress streaming
- Ready for Plan 04: Frontend Backtest page with charts

## Self-Check: PASSED

- [x] backend/app/domain/backtest_engine.py exists (946 lines)
- [x] backend/tests/test_backtest_engine.py exists (939 lines)
- [x] Commit da0ecd8 exists (RED phase tests)
- [x] Commit 4232c21 exists (GREEN+REFACTOR implementation)
- [x] 48/48 tests pass
- [x] 782/782 total backend tests pass (no regressions)
- [x] ruff check passes
- [x] black formatting passes
- [x] 0 float() calls in domain module

---
*Phase: 15-backtesting-engine*
*Completed: 2026-02-27*
