---
phase: 01-sell-allocation-symbol-isolation
plan: 01
subsystem: database
tags: [sqlalchemy, symbol-registry, sell-allocation, cross-pair, fifo, lifo]

# Dependency graph
requires: []
provides:
  - "Base-asset filtered sell allocation queries (all 4 paths)"
  - "get_symbols_for_base_asset() helper in symbol_registry.py"
  - "Cross-asset isolation test suite (10 tests)"
affects: [02-eur-cost-basis, 03-cross-pair-pairing, 04-sell-routing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_get_base_symbols_for_sell_event() helper pattern for sell event symbol resolution with BTCEUR fallback"
    - "TradeLotDB.symbol.in_(base_symbols) filter pattern for base-asset scoped queries"

key-files:
  created:
    - "backend/tests/test_sell_allocation_isolation.py"
  modified:
    - "backend/app/symbol_registry.py"
    - "backend/app/services/lot_service.py"

key-decisions:
  - "Base-asset filtering at service layer (DB query level) not domain layer -- domain functions already work with pre-filtered lists"
  - "get_symbols_for_base_asset() raises ValueError for unknown base-asset (consistent with get_base_asset() behavior)"
  - "Fallback sell_event_db.symbol or 'BTCEUR' for legacy events without symbol, encapsulated in _get_base_symbols_for_sell_event() helper"

patterns-established:
  - "Base-asset scoping: derive base symbols from sell event, filter DB queries with .in_()"
  - "Symbol registry reverse-lookup: get_symbols_for_base_asset() for base-asset grouping"

requirements-completed: [ALLOC-01, ALLOC-02, ALLOC-03]

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 1 Plan 01: Sell Allocation Symbol Isolation Summary

**Base-asset filtered sell allocation with get_symbols_for_base_asset() helper preventing cross-asset contamination in all 4 allocation paths (FIFO, LIFO, HIGHEST_COST, lot-specific)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T15:04:15Z
- **Completed:** 2026-02-20T15:07:47Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added `get_symbols_for_base_asset()` to symbol_registry.py for reverse base-asset lookup
- Patched all 4 sell allocation functions in lot_service.py with `TradeLotDB.symbol.in_(base_symbols)` filter
- Created 10 comprehensive tests proving cross-asset isolation, backward compatibility, and overflow scoping
- Full test suite (579 tests) passes with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add get_symbols_for_base_asset() and patch all 4 allocation queries** - `c784b6a` (fix)
2. **Task 2: Write cross-asset isolation and backward compatibility tests** - `8c272f6` (test)

## Files Created/Modified
- `backend/app/symbol_registry.py` - Added `get_symbols_for_base_asset()` reverse-lookup function
- `backend/app/services/lot_service.py` - Added `_get_base_symbols_for_sell_event()` helper, patched 4 allocation functions with base-asset filter
- `backend/tests/test_sell_allocation_isolation.py` - 10 tests: symbol registry (4), cross-asset isolation (3), backward compatibility (2), overflow isolation (1)

## Decisions Made
- Base-asset filtering at service layer (DB query level), not domain layer -- domain functions already work correctly with pre-filtered lists
- `get_symbols_for_base_asset()` raises `ValueError` for unknown base-asset (consistent with existing `get_base_asset()`)
- Fallback `sell_event_db.symbol or "BTCEUR"` for legacy events encapsulated in `_get_base_symbols_for_sell_event()` helper

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 1 (Sell Allocation Symbol Isolation) is complete with all 3 requirements (ALLOC-01, ALLOC-02, ALLOC-03) met
- Phase 2 (EUR Cost Basis) can proceed independently -- no dependencies on this phase
- Phase 3 (Cross-Pair Pairing) can begin once both Phase 1 and Phase 2 are complete

## Self-Check: PASSED

All files verified present:
- `backend/app/symbol_registry.py` - FOUND
- `backend/app/services/lot_service.py` - FOUND
- `backend/tests/test_sell_allocation_isolation.py` - FOUND
- `.planning/phases/01-sell-allocation-symbol-isolation/01-01-SUMMARY.md` - FOUND

All commits verified:
- `c784b6a` (Task 1) - FOUND
- `8c272f6` (Task 2) - FOUND

---
*Phase: 01-sell-allocation-symbol-isolation*
*Completed: 2026-02-20*
