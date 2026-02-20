---
phase: 03-cross-pair-pairing
plan: 01
subsystem: domain
tags: [decimal, dataclass, tdd, cross-pair, pairing, eur-cost, dual-route]

# Dependency graph
requires:
  - phase: 01-sell-allocation-symbol-isolation
    provides: get_base_asset() in symbol_registry for base-asset derivation
  - phase: 02-eur-cost-basis
    provides: TradeLot.cost_eur field for EUR-normalized cost comparison
provides:
  - Pairing.base_asset field (cross-pair identifier)
  - Pairing.is_cross_pair property
  - Pairing.net_cost_eur() method
  - PairingItem.cost_eur and PairingItem.lot_symbol fields
  - RouteDetails and DualRouteComparison dataclasses
  - suggest_pairings() use_eur_cost parameter for EUR-normalized P&L mode
  - compute_dual_route_comparison() for XRPEUR vs XRPBTC route comparison
affects: [03-02 service integration, 03-03 frontend cross-pair UI, 04 sell routing]

# Tech tracking
tech-stack:
  added: []
  patterns: [EUR-normalized P&L via cost_eur in pairing heuristic, dual-route comparison with compounded fees for indirect route, helper functions _lot_cost/_lot_pnl_pct for mode-switching between quote-currency and EUR cost]

key-files:
  created:
    - backend/tests/test_cross_pair_pairing.py
  modified:
    - backend/app/domain/models.py
    - backend/app/domain/pairing.py

key-decisions:
  - "suggest_pairings use_eur_cost defaults to False -- all existing callers produce identical results without changes"
  - "Cross-pair pairings set base_asset from get_base_asset(lots[0].symbol) -- derives from first lot's symbol"
  - "Dual-route indirect fees are compounded (two fee steps) not additive -- matches real Binance trading flow"
  - "PairingItem.cost_eur and lot_symbol are None in default mode -- distinguishes single-pair from cross-pair at item level"

patterns-established:
  - "_lot_cost() and _lot_pnl_pct() helpers encapsulate mode switching -- keeps suggest_pairings logic clean regardless of cost mode"
  - "Validation-first pattern: use_eur_cost=True with any lot.cost_eur=None raises ValueError immediately before any computation"

requirements-completed: [PAIR-01, PAIR-02, PAIR-03, PAIR-04]

# Metrics
duration: 4min
completed: 2026-02-20
---

# Phase 3 Plan 01: Cross-Pair Pairing Domain Logic Summary

**EUR-normalized pairing heuristic with use_eur_cost mode, dual-route comparison for XRPEUR vs XRPBTC routing, and Pairing/PairingItem model extensions for cross-pair support**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-20T17:35:54Z
- **Completed:** 2026-02-20T17:40:12Z
- **Tasks:** 1 feature (TDD: RED + GREEN, no refactor needed)
- **Files modified:** 3

## Accomplishments
- Extended Pairing model with base_asset, is_cross_pair property, and net_cost_eur() for cross-pair identification
- Extended PairingItem with cost_eur and lot_symbol fields for EUR-normalized cost tracking per item
- Added RouteDetails and DualRouteComparison dataclasses for dual-route sell simulation
- suggest_pairings() now supports use_eur_cost=True mode using lot.cost_eur for P&L (backward compatible)
- compute_dual_route_comparison() computes EUR proceeds for direct and indirect routes with compounded fees
- 26 new test cases covering all branches: model extensions, cross-pair heuristic, dual-route comparison, backward compatibility, edge cases
- Zero regressions: all 620 existing tests pass unchanged

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests** - `c64dfc7` (test)
2. **TDD GREEN: Implementation** - `2222847` (feat)

_No refactor commit needed -- implementation was minimal and followed existing patterns._

## Files Created/Modified
- `backend/tests/test_cross_pair_pairing.py` - 26 test cases for cross-pair pairing domain logic (293 lines)
- `backend/app/domain/models.py` - PairingItem: added cost_eur, lot_symbol; Pairing: added base_asset, is_cross_pair, net_cost_eur(); new RouteDetails and DualRouteComparison dataclasses
- `backend/app/domain/pairing.py` - suggest_pairings(): added use_eur_cost param + _lot_cost/_lot_pnl_pct helpers; new compute_dual_route_comparison() function

## Decisions Made
- use_eur_cost defaults to False -- existing callers (3 positional args) produce identical results without any changes
- Cross-pair base_asset derived from get_base_asset(lots[0].symbol) -- consistent with symbol_registry pattern from Phase 1
- Dual-route indirect route applies fees twice (sell XRPBTC, then sell BTCEUR) -- compounded, not additive
- PairingItem.cost_eur and lot_symbol remain None in default (non-cross-pair) mode -- clean separation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test data in test_cross_pair_basic**
- **Found during:** TDD GREEN phase
- **Issue:** Original test data had lot costs too close to market value -- combined P&L fell below 5% threshold, producing zero pairings
- **Fix:** Adjusted lot1 cost_eur from 40 to 30 and lot2 cost_eur from 60 to 55 to create a valid pairing scenario (combined P&L 17.6%)
- **Files modified:** backend/tests/test_cross_pair_pairing.py
- **Verification:** Test passes, P&L math verified in comments
- **Committed in:** 2222847 (GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 test data bug)
**Impact on plan:** Minor test data correction. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Domain layer is ready for Plan 02 (service integration + DB migration)
- Pairing model extensions (base_asset, cost_eur, lot_symbol) need corresponding DB columns (Alembic migration in Plan 02)
- Pairing service needs multi-symbol lot loading via get_symbols_for_base_asset() (Plan 02)
- API routes need base_asset parameter and dual-route price params (Plan 02)

## Self-Check: PASSED

All artifacts verified:
- [x] `backend/tests/test_cross_pair_pairing.py` exists (26 tests)
- [x] `backend/app/domain/models.py` contains base_asset, is_cross_pair, net_cost_eur, RouteDetails, DualRouteComparison
- [x] `backend/app/domain/pairing.py` contains use_eur_cost parameter, compute_dual_route_comparison function
- [x] Commit `c64dfc7` (RED) exists
- [x] Commit `2222847` (GREEN) exists
- [x] 26 new tests pass
- [x] 23 existing pairing tests pass (backward compatible)
- [x] 620 total tests pass (zero regressions)

---
*Phase: 03-cross-pair-pairing*
*Completed: 2026-02-20*
