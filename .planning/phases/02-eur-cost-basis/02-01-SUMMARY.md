---
phase: 02-eur-cost-basis
plan: 01
subsystem: domain
tags: [decimal, dataclass, tdd, eur-cost-basis, trade-lot]

# Dependency graph
requires:
  - phase: none
    provides: standalone domain logic (no prior phase dependency)
provides:
  - TradeLot.cost_eur field (EUR-equivalent cost at fill time)
  - TradeLot.quote_to_eur_rate field (historical conversion rate)
  - TradeLot.break_even_eur property (EUR break-even per base unit)
  - create_trade_lot_from_buy_fill() quote_to_eur_rate parameter
affects: [02-02 service integration, 03 cross-pair pairing]

# Tech tracking
tech-stack:
  added: []
  patterns: [EUR cost basis auto-detection via get_quote_asset(), Optional Decimal fields for backfill-capable data]

key-files:
  created:
    - backend/tests/test_eur_cost_basis.py
  modified:
    - backend/app/domain/models.py
    - backend/app/domain/lots.py

key-decisions:
  - "cost_eur and quote_to_eur_rate use Optional[Decimal] with None default for backward compatibility and backfill support"
  - "EUR-quoted lots auto-detect via get_quote_asset() -- no caller action needed for BTCEUR/XRPEUR"
  - "break_even_eur returns None (not zero) when cost_eur is unknown or qty is zero -- distinguishes missing data from zero-cost"

patterns-established:
  - "Optional Decimal fields with None sentinel: None = needs backfill, Decimal value = computed at fill time"
  - "Three-way branch for EUR cost: EUR-quoted -> trivial, non-EUR with rate -> multiply, non-EUR without rate -> None"

requirements-completed: [COST-02, COST-03, COST-05]

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 2 Plan 01: EUR Cost Basis Domain Logic Summary

**TradeLot dataclass extended with cost_eur, quote_to_eur_rate, and break_even_eur for deterministic EUR cost basis at lot creation time**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T15:38:09Z
- **Completed:** 2026-02-20T15:40:46Z
- **Tasks:** 1 feature (TDD: RED + GREEN, no refactor needed)
- **Files modified:** 3

## Accomplishments
- TradeLot dataclass extended with cost_eur and quote_to_eur_rate fields plus break_even_eur property
- create_trade_lot_from_buy_fill() auto-detects EUR-quoted lots and computes EUR cost basis when rate provided
- 15 new test cases covering all branches: EUR-quoted auto-detect, BTC-quoted with/without rate, edge cases, fee handling, backward compatibility
- Zero regressions: all 29 existing lot/portfolio tests + 29 cross-pair/strategy tests still pass

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests** - `a9ffffc` (test)
2. **TDD GREEN: Implementation** - `f35eba2` (feat)

_No refactor commit needed -- implementation was minimal and followed existing patterns._

## Files Created/Modified
- `backend/tests/test_eur_cost_basis.py` - 15 test cases for EUR cost basis domain logic (276 lines)
- `backend/app/domain/models.py` - TradeLot: added cost_eur, quote_to_eur_rate fields + break_even_eur property
- `backend/app/domain/lots.py` - create_trade_lot_from_buy_fill(): added quote_to_eur_rate parameter + EUR cost computation branch

## Decisions Made
- Used Optional[Decimal] with None default for both new fields -- enables backward compatibility (existing callers unaffected) and distinguishes "needs backfill" from "computed as zero"
- break_even_eur returns None (not Decimal("0")) when cost_eur is None or qty is zero -- consistent with PortfolioState.break_even returning None for empty portfolio
- EUR auto-detection reuses the existing quote_asset variable (already computed on line 69 of lots.py) -- no redundant symbol parsing

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Domain layer is ready for Plan 02 (service integration + DB migration + backfill)
- cost_eur and quote_to_eur_rate fields need corresponding TradeLotDB columns (Alembic migration in Plan 02)
- Sync service needs to fetch BTC/EUR rate and pass as quote_to_eur_rate parameter (Plan 02)

## Self-Check: PASSED

All artifacts verified:
- [x] `backend/tests/test_eur_cost_basis.py` exists (276 lines, 15 tests)
- [x] `backend/app/domain/models.py` contains cost_eur, quote_to_eur_rate, break_even_eur
- [x] `backend/app/domain/lots.py` contains quote_to_eur_rate parameter and EUR cost computation
- [x] Commit `a9ffffc` (RED) exists
- [x] Commit `f35eba2` (GREEN) exists
- [x] 15 new tests pass
- [x] 29 existing lot/portfolio tests pass (backward compatible)
- [x] 29 existing cross-pair/strategy tests pass (no regression)

---
*Phase: 02-eur-cost-basis*
*Completed: 2026-02-20*
