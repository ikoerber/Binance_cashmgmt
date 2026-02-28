---
phase: 16-dry-run-mode-bot-dashboard
plan: 01
subsystem: domain, database, api
tags: [dry-run, virtual-portfolio, decimal, alembic, sqlalchemy, settings]

# Dependency graph
requires:
  - phase: 15-backtesting-engine
    provides: "Backtest engine cost model (position_fraction, fee_rate, slippage_pct)"
  - phase: 14-alpha-score
    provides: "AlphaScoreResult, TrailingStopState dataclasses, Settings columns"
provides:
  - "Pure domain module for virtual portfolio management (dry_run.py)"
  - "3 new DB tables: dry_run_decisions, dry_run_portfolios, dry_run_positions"
  - "Alembic migration dr01_dry_run_tab"
  - "Settings API extension: dry_run_initial_capital"
affects: [16-02, 16-03]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Virtual portfolio isolation (separate tables from production)", "Fixed fraction position sizing matching backtest engine"]

key-files:
  created:
    - backend/app/domain/dry_run.py
    - backend/alembic/versions/dr01_dry_run_tables.py
  modified:
    - backend/app/db/models.py
    - backend/app/api/routes/settings.py

key-decisions:
  - "Dry-run domain module is pure (no I/O) matching backtest engine Decimal-only pattern"
  - "Three separate tables for complete production isolation (DRY-03/DRY-05)"
  - "dry_run_initial_capital range 100-10M EUR with String transport for Decimal precision"

patterns-established:
  - "VirtualPosition/VirtualTradeResult dataclasses for dry-run state management"
  - "DecisionContext captures full alpha score context for decision audit trail"

requirements-completed: [DRY-01, DRY-02, DRY-03, DRY-05]

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 16 Plan 01: Dry-Run Backend Foundation Summary

**Pure domain module for virtual portfolio with Decimal-only math, 3 isolated DB tables, Alembic migration, and Settings API extension for initial capital**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T16:08:10Z
- **Completed:** 2026-02-27T16:13:10Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Pure domain module (dry_run.py) with 4 dataclasses and 7 pure functions, all Decimal math, no I/O
- Position sizing matching backtest engine cost model (fixed fraction of equity)
- 3 new DB tables completely isolated from production (decisions, portfolios, positions)
- Alembic migration with upgrade/downgrade verified, batch mode for SQLite
- Settings API extended with dry_run_initial_capital validation (100-10M range)
- All 782 existing backend tests pass without regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Pure domain module for virtual portfolio management** - `2bd50f7` (feat)
2. **Task 2: DB models + Alembic migration + Settings extension** - `418dac1` (feat)

## Files Created/Modified
- `backend/app/domain/dry_run.py` - Pure domain: VirtualPosition, VirtualPortfolioState, VirtualTradeResult, DecisionContext + 7 pure functions
- `backend/app/db/models.py` - DryRunDecisionDB, DryRunPortfolioDB, DryRunPositionDB + dry_run_initial_capital on UserSettingsDB
- `backend/alembic/versions/dr01_dry_run_tables.py` - Migration creating 3 tables + settings column
- `backend/app/api/routes/settings.py` - dry_run_initial_capital in SettingsUpdate, DEFAULTS, _settings_to_dict, validation

## Decisions Made
- Domain module is pure (no I/O imports) matching the pattern from backtest_engine.py and alpha_score.py
- Three separate DB tables provide complete isolation from production ledger/lots/orders (DRY-03/DRY-05)
- dry_run_initial_capital range set to 100-10,000,000 EUR covering realistic simulation ranges
- DecisionContext captures full alpha score breakdown for decision audit trail

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Domain logic ready for service layer integration (16-02: dry-run service + API endpoints)
- DB tables and migration ready for persistence
- Settings column available for frontend integration in 16-03

---
*Phase: 16-dry-run-mode-bot-dashboard*
*Completed: 2026-02-27*
