---
phase: 15-backtesting-engine
plan: 02
subsystem: api
tags: [backtest, persistence, alembic, api, service, singleton, klines, paginated-fetch, decimal]

# Dependency graph
requires:
  - phase: 15-backtesting-engine
    provides: "Pure domain backtest engine with run_alpha_backtest(), BacktestConfig, BacktestResult dataclasses"
provides:
  - "AlphaBacktestRunDB ORM model with immutable backtest snapshots"
  - "BacktestDataService singleton: paginated kline fetch, simulation orchestration, persistence, cancellation"
  - "4 API routes: POST run, GET list, GET detail, POST cancel"
  - "XRPEUR fallback derivation from XRPBTC * BTCEUR"
  - "WebSocket progress callback for real-time backtest progress"
affects: [15-03, 15-04, backtest-frontend, backtest-sweep]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BacktestDataService singleton with active_runs tracking and cancel events"
    - "Paginated kline fetch with Decimal parsing (same pattern as OrderblockDataService)"
    - "asyncio.to_thread for blocking I/O (kline fetch) and CPU-bound work (simulation)"
    - "AlphaBacktestRunDB immutable snapshots with queryable key metrics + JSON blobs"
    - "XRPEUR derivation fallback: XRPBTC * BTCEUR price matching on open_time"

key-files:
  created:
    - backend/app/db/models.py (AlphaBacktestRunDB class added)
    - backend/alembic/versions/061714dcd26c_add_alpha_backtest_runs_table.py
    - backend/app/services/backtest_data_service.py
    - backend/app/api/routes/backtest.py
  modified:
    - backend/app/main.py

key-decisions:
  - "AlphaBacktestRunDB separate from existing BacktestRunDB (orderblock) to avoid schema confusion"
  - "Key metrics (net_return, sharpe, drawdown, win_rate) stored as queryable columns alongside JSON blobs"
  - "excess_return_pct computed at persistence time (net_return - benchmark_return)"
  - "XRPEUR fallback: derive from XRPBTC * BTCEUR via open_time matching when direct pair data unavailable"
  - "Config overrides merge with user settings at API layer, not service layer (separation of concerns)"
  - "5-minute async timeout for backtest execution (sufficient for 24-month simulations)"

patterns-established:
  - "BacktestDataService singleton with threading.Event for run cancellation"
  - "Paginated Binance kline fetch with Decimal parsing for backtest candle data"
  - "Pydantic request model with optional string-typed Decimal overrides (matching project decimal-string-transport convention)"

requirements-completed: [BT-01, BT-05, BT-06]

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 15 Plan 02: Backtest Persistence + Service + API Summary

**AlphaBacktestRunDB table + BacktestDataService singleton with paginated kline fetch, simulation orchestration, and 4 REST API endpoints (run/list/detail/cancel)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T14:36:41Z
- **Completed:** 2026-02-27T14:42:30Z
- **Tasks:** 2
- **Files created/modified:** 5

## Accomplishments
- AlphaBacktestRunDB model with all columns (key metrics queryable, JSON blobs for detail) + Alembic migration
- BacktestDataService singleton: paginated kline fetch for 3 candle series, domain engine orchestration, immutable result persistence, WebSocket progress callback, cancellation support
- 4 API endpoints: POST run (configurable), GET runs (list summary), GET run detail (full), POST cancel
- XRPEUR fallback derivation from XRPBTC * BTCEUR when direct Binance data unavailable
- Full regression-safe: 782 total backend tests pass (no regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: AlphaBacktestRunDB model + Alembic migration** - `c048ef7` (feat)
2. **Task 2: BacktestDataService + API routes + main.py registration** - `0ebd948` (feat)

## Files Created/Modified
- `backend/app/db/models.py` - Added AlphaBacktestRunDB class with 2 indexes (user+symbol, sweep_id)
- `backend/alembic/versions/061714dcd26c_add_alpha_backtest_runs_table.py` - Migration creates alpha_backtest_runs table (gitignored, generated locally)
- `backend/app/services/backtest_data_service.py` - BacktestDataService singleton: paginated fetch, simulation orchestration, persistence, cancellation, serialization helpers
- `backend/app/api/routes/backtest.py` - 4 API endpoints with Pydantic request model, input validation, user settings integration
- `backend/app/main.py` - Registered backtest router with API key auth

## Decisions Made
- AlphaBacktestRunDB kept separate from existing BacktestRunDB (orderblock backtests) to avoid schema confusion and enable independent evolution
- Key metrics stored as queryable Numeric columns (net_return, sharpe, drawdown, win_rate, fees, slippage) for list views without JSON parsing
- excess_return_pct computed at persistence time rather than on-the-fly
- XRPEUR fallback derivation via timestamp matching ensures benchmark calculation works even without direct XRPEUR Binance data
- Config overrides use Pydantic optional string fields matching the project's decimal-string-transport convention (no float precision loss)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Persistence + service + API complete and operational
- Ready for Plan 03: Frontend Backtest page with parameter form, equity curve chart, drawdown chart, monthly returns heatmap
- Ready for Plan 04: Parameter sweep with grid search and CSV export

## Self-Check: PASSED

- [x] backend/app/db/models.py contains AlphaBacktestRunDB class
- [x] backend/app/services/backtest_data_service.py exists (590+ lines)
- [x] backend/app/api/routes/backtest.py exists (4 routes)
- [x] backend/app/main.py includes backtest router
- [x] Commit c048ef7 exists (Task 1)
- [x] Commit 0ebd948 exists (Task 2)
- [x] 782/782 tests pass (no regressions)
- [x] ruff check passes on new files
- [x] black formatting passes

---
*Phase: 15-backtesting-engine*
*Completed: 2026-02-27*
