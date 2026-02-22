---
phase: 04-sell-routing
plan: 02
subsystem: services
tags: [cross-pair, sell-routing, binance-api, eur-normalization, alembic, frontend]

# Dependency graph
requires:
  - phase: 04-sell-routing plan 01
    provides: compute_cross_pair_realized_pnl_eur, RoutingDecision dataclass, compute_pairing_order_params with symbol-aware precision
  - phase: 03-cross-pair-pairing
    provides: base_asset on PairingDB, cross-pair pairing creation and simulation, dual-route comparison
provides:
  - Automatic sell routing at pairing execution time (selects optimal route based on live prices)
  - Routing decision persistence as JSON audit trail on PairingDB
  - EUR-normalized realized P&L on SellAllocationDB for cross-pair sell fills
  - Frontend routing result display (success message + EXECUTED pairing badge)
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [live-price-at-execution routing, EUR-equivalent max order value check for non-EUR pairs]

key-files:
  created: [backend/alembic/versions/ddedaa7263d8_add_routing_decision_json_and_realized_.py]
  modified: [backend/app/db/models.py, backend/app/services/order_service.py, backend/app/services/lot_service.py, backend/app/services/pairing_service.py, frontend/src/components/PairingExistingTab.jsx, frontend/src/components/PairingPanel.css]

key-decisions:
  - "Routing decision persisted directly in order_service after execute_pairing call (not in pairing_service) because order_service has routing context"
  - "routing_decision_json returned from list_pairings for EXECUTED pairings (not just execute response) for persistent display"
  - "EUR-equivalent max order value computed using btceur_price from routing decision (same price snapshot used for route selection)"
  - "Client order ID format updated to symbol-aware format with satoshi encoding matching Plan 01 domain logic"

patterns-established:
  - "Live-price routing: fetch 3 prices at execution, compute comparison, select winner, persist audit"
  - "Cross-pair allocation P&L override: detect cross-pair pairing, recompute realized_pnl using EUR-normalization"

requirements-completed: [ROUTE-01, ROUTE-02, ROUTE-03, ROUTE-04]

# Metrics
duration: 5min
completed: 2026-02-22
---

# Phase 4 Plan 02: Sell Routing Service Integration Summary

**Automatic sell routing wired into pairing execution: live 3-price fetch, optimal route selection, routing audit persistence, EUR-normalized cross-pair P&L allocation, and frontend routing result display**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-22T19:26:40Z
- **Completed:** 2026-02-22T19:32:29Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- create_limit_sell_for_pairing now fetches live XRPEUR, XRPBTC, BTCEUR prices and automatically selects optimal route for cross-pair pairings
- Routing decision persisted as JSON on PairingDB with all audit fields (prices, proceeds, delta, timestamp)
- process_sell_fill_for_pairing detects cross-pair allocations and computes EUR-normalized realized_pnl_eur
- Frontend shows routing info in success message after execution and routing badge on EXECUTED pairings
- Single-pair pairings have zero behavioral changes (full backward compatibility)
- All 633 existing tests continue to pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: DB migration + service layer integration** - `0aafc04` (feat)
2. **Task 2: API response + frontend routing result display** - `a28e18f` (feat)

## Files Created/Modified
- `backend/app/db/models.py` - Added routing_decision_json on PairingDB, realized_pnl_eur on SellAllocationDB
- `backend/alembic/versions/ddedaa7263d8_...py` - Migration for new columns (gitignored)
- `backend/app/services/order_service.py` - Route selection in create_limit_sell_for_pairing: 3-price fetch, dual-route comparison, symbol override, routing audit persistence, EUR max-value check, satoshi client_order_id
- `backend/app/services/lot_service.py` - Cross-pair P&L override in process_sell_fill_for_pairing: detect cross-pair, compute EUR-normalized realized_pnl, persist realized_pnl_eur
- `backend/app/services/pairing_service.py` - Include routing_decision in list_pairings response for EXECUTED cross-pair pairings
- `frontend/src/components/PairingExistingTab.jsx` - Routing-aware execute success message, routing badge on EXECUTED pairing cards
- `frontend/src/components/PairingPanel.css` - Styles for routing-badge and routing-savings

## Decisions Made
- Routing decision is persisted in order_service.py (not pairing_service.py) because order_service has the routing context from price fetching and route comparison
- routing_decision_json is included in list_pairings response for persistent display of routing results on EXECUTED pairings
- EUR-equivalent max order value check uses btceur_price from the same routing decision snapshot for consistency
- Client order ID format updated to match Plan 01 symbol-aware format (satoshi encoding for sub-1 prices)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 4 (Sell Routing) is complete: all 4 requirements (ROUTE-01 through ROUTE-04) implemented
- Cross-pair pairing execution now automatically routes to optimal sell pair
- Routing decisions are auditable via routing_decision_json on PairingDB
- EUR-normalized P&L tracked on SellAllocationDB for cross-pair allocations

## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 04-sell-routing*
*Completed: 2026-02-22*
