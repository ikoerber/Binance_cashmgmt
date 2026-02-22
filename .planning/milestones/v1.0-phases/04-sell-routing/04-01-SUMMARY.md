---
phase: 04-sell-routing
plan: 01
subsystem: domain
tags: [cross-pair, sell-routing, pnl, decimal, tdd, dataclass]

# Dependency graph
requires:
  - phase: 03-cross-pair-pairing
    provides: DualRouteComparison, PairingItem.cost_eur, TradeLot.cost_eur
provides:
  - compute_cross_pair_realized_pnl_eur() for EUR-normalized P&L across sell routes
  - RoutingDecision dataclass for audit logging of route selection
  - Symbol-aware compute_pairing_order_params with sub-1 price handling and EUR max-value check
affects: [04-sell-routing plan 02 service integration, lot_service sell allocation]

# Tech tracking
tech-stack:
  added: []
  patterns: [satoshi-encoding for sub-1 price client_order_ids, symbol_registry-driven precision quantization]

key-files:
  created: [backend/tests/test_sell_routing.py]
  modified: [backend/app/domain/models.py, backend/app/domain/lots.py, backend/app/domain/orders.py, backend/tests/test_pairing_execution.py]

key-decisions:
  - "Satoshi encoding (price * 1e8) for XRPBTC client_order_id to prevent sub-1 price collisions"
  - "Symbol-aware precision from symbol_registry instead of hardcoded Decimal('0.01') and Decimal('0.00001')"
  - "btceur_rate parameter optional with fallback to quote-value-as-is for backward compatibility"
  - "BTCEUR base_precision=8 now correctly applied (was hardcoded to 5 decimals before)"

patterns-established:
  - "EUR-normalization pattern: convert proceeds to EUR via btceur_rate, use lot.cost_eur for cost portion"
  - "Satoshi encoding: int(price * 1e8) for sub-1 prices in deterministic identifiers"

requirements-completed: [ROUTE-01, ROUTE-03, ROUTE-04]

# Metrics
duration: 4min
completed: 2026-02-22
---

# Phase 4 Plan 01: Sell Routing Domain Logic Summary

**TDD-built pure domain functions for cross-pair EUR-normalized P&L, RoutingDecision audit dataclass, and symbol-aware order parameter computation with sub-1 price collision fix**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-22T19:20:12Z
- **Completed:** 2026-02-22T19:24:00Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 5

## Accomplishments
- compute_cross_pair_realized_pnl_eur correctly computes EUR P&L for all 4 cross-pair scenarios (EUR sell + EUR lot, BTC sell + EUR lot, EUR sell + BTC lot, loss scenario)
- RoutingDecision dataclass stores all audit fields and serializes Decimals to strings via to_dict()
- compute_pairing_order_params now uses symbol_registry precision, satoshi-safe client_order_ids for sub-1 XRPBTC prices, and EUR-converted max order value check
- 13 new tests pass, 633 total tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD RED -- Write failing tests** - `d52c2e7` (test)
2. **Task 2: TDD GREEN -- Implement domain functions** - `dcab5d5` (feat)

## Files Created/Modified
- `backend/tests/test_sell_routing.py` - 13 test cases covering cross-pair P&L, RoutingDecision, and order params
- `backend/app/domain/models.py` - Added RoutingDecision dataclass with to_dict() serialization
- `backend/app/domain/lots.py` - Added compute_cross_pair_realized_pnl_eur() for EUR-normalized P&L
- `backend/app/domain/orders.py` - Rewritten compute_pairing_order_params with symbol-aware precision, satoshi encoding, EUR max-value
- `backend/tests/test_pairing_execution.py` - Updated existing test for correct BTCEUR base_precision=8

## Decisions Made
- Satoshi encoding (price * 1e8) chosen over UUID or hash-based approach for XRPBTC client_order_ids -- maintains determinism and human readability while preventing collisions
- Symbol-aware precision replaces hardcoded quantizers -- BTCEUR quantity now correctly uses 8 decimal places (was 5)
- btceur_rate parameter is optional with fallback -- existing callers that only use EUR-quoted symbols need no changes
- Client order ID format changed from `{user}_pairing_{id}_{price}_{version}` to `{user}_p_{id}_{symbol}_{price}_{version}` -- shorter prefix to fit 36-char Binance limit with symbol included

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test for correct BTCEUR base_precision**
- **Found during:** Task 2 (implementation)
- **Issue:** `test_compute_pairing_order_params_basic` expected quantity="0.01235" (5 decimals) but BTCEUR has base_precision=8 in symbol_registry
- **Fix:** Updated test assertion to expect "0.01234567" (8 decimals) and removed hardcoded "pairing" check from client_order_id
- **Files modified:** backend/tests/test_pairing_execution.py
- **Verification:** All 633 tests pass
- **Committed in:** dcab5d5 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Test correction necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Domain functions ready for service-layer integration in Plan 02
- compute_cross_pair_realized_pnl_eur ready for use in process_sell_fill_for_pairing
- RoutingDecision ready for persistence in PairingDB routing_decision_json column
- compute_pairing_order_params ready for cross-pair order creation with correct precision

## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 04-sell-routing*
*Completed: 2026-02-22*
