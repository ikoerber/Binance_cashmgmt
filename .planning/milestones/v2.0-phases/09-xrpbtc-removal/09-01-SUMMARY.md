---
phase: 09-xrpbtc-removal
plan: 01
subsystem: api, domain, database
tags: [symbol-registry, pairing, order-service, orm, cross-pair-removal]

# Dependency graph
requires: []
provides:
  - EUR-only symbol registry (3 pairs: BTCEUR, ETHEUR, XRPEUR)
  - Simplified domain models without cross-pair abstractions
  - Simplified services without routing/dual-route/base_asset logic
  - ORM without cross-pair columns (migration pending Plan 03)
affects: [09-02 (frontend cleanup), 09-03 (migration + tests)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "1:1 base-asset to symbol mapping (no multi-symbol per base)"
    - "cost_eur = cost_quote for all EUR-quoted pairs (trivial identity)"

key-files:
  created: []
  modified:
    - backend/app/symbol_registry.py
    - backend/app/domain/models.py
    - backend/app/domain/pairing.py
    - backend/app/domain/lots.py
    - backend/app/domain/orders.py
    - backend/app/domain/portfolio.py
    - backend/app/services/order_service.py
    - backend/app/services/pairing_service.py
    - backend/app/services/lot_service.py
    - backend/app/services/sync_service.py
    - backend/app/services/websocket_fill_handler.py
    - backend/app/api/routes/pairing.py
    - backend/app/db/models.py

key-decisions:
  - "Retained satoshi encoding for sub-1 EUR prices (XRPEUR ~0.50 EUR needs it)"
  - "Retained cost_eur on TradeLotDB (equals cost_quote for EUR pairs, still useful)"
  - "Simplified _get_base_symbols_for_sell_event to return single symbol (1:1 mapping)"
  - "ORM columns removed from Python only; physical DB columns remain until Alembic migration in Plan 03"

patterns-established:
  - "EUR-only pairs: all price/cost computations use native quote currency = EUR"
  - "Single-symbol sell allocation: no multi-symbol lot loading for sells"

requirements-completed: [REM-01, REM-02, REM-03, REM-04]

# Metrics
duration: 11min
completed: 2026-02-23
---

# Phase 09 Plan 01: Backend XRPBTC Removal Summary

**EUR-only backend: removed XRPBTC from registry, deleted RouteDetails/DualRouteComparison/RoutingDecision, simplified 13 files with ~470 lines removed**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-23T22:31:13Z
- **Completed:** 2026-02-23T22:42:42Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- Symbol registry reduced to 3 EUR-only pairs (BTCEUR, ETHEUR, XRPEUR)
- Deleted 3 cross-pair dataclasses (RouteDetails, DualRouteComparison, RoutingDecision)
- Removed all cross-pair parameters (base_asset, use_eur_cost, btceur_rate, xrpbtc_price, quote_to_eur_rate) from domain, services, and API
- Removed 6 ORM columns across 4 tables (routing_decision_json, base_asset, quote_to_eur_rate, pairing_items.cost_eur, pairing_items.lot_symbol, sell_allocations.realized_pnl_eur)
- Zero references to XRPBTC, RouteDetails, DualRouteComparison, RoutingDecision, or get_symbols_for_base_asset in backend/app/

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove XRPBTC from Symbol Registry + Simplify Domain Models and Logic** - `31f277e` (feat)
2. **Task 2: Simplify Services, API Routes, and ORM Definitions** - `54da15d` (feat)

## Files Created/Modified
- `backend/app/symbol_registry.py` - Removed XRPBTC entry and get_symbols_for_base_asset()
- `backend/app/domain/models.py` - Deleted RouteDetails, DualRouteComparison, RoutingDecision; simplified Pairing/PairingItem/TradeLot
- `backend/app/domain/pairing.py` - Removed compute_dual_route_comparison(), simplified suggest_pairings()
- `backend/app/domain/lots.py` - Deleted compute_cross_pair_realized_pnl_eur(), simplified create_trade_lot_from_buy_fill()
- `backend/app/domain/orders.py` - Removed btceur_rate parameter, simplified order value check
- `backend/app/domain/portfolio.py` - Removed cross-pair comment
- `backend/app/services/order_service.py` - Removed route selection block and routing_decision persistence
- `backend/app/services/pairing_service.py` - Removed base_asset, dual-route comparison, cross-pair serialization
- `backend/app/services/lot_service.py` - Removed cross-pair P&L override, quote_to_eur_rate usage
- `backend/app/services/sync_service.py` - Removed _get_quote_to_eur_rates() method
- `backend/app/services/websocket_fill_handler.py` - Removed quote_to_eur_rate fetching for BUY fills
- `backend/app/api/routes/pairing.py` - Removed base_asset/xrpbtc_price/btceur_price from all endpoints
- `backend/app/db/models.py` - Removed 6 ORM columns across 4 tables

## Decisions Made
- Retained satoshi encoding for sub-1 EUR prices -- XRPEUR trades at ~0.50 EUR, so the sub-1 client_order_id encoding is still needed to avoid collisions
- Retained cost_eur on TradeLotDB -- it equals cost_quote for EUR pairs and is still used in break_even_eur calculations
- Simplified _get_base_symbols_for_sell_event to return a single-element list since there is now a 1:1 mapping between base asset and symbol
- ORM columns are removed from Python definitions only; the actual DB columns still exist and will be physically dropped by the Alembic migration in Plan 03

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend is fully simplified for EUR-only pairs
- Plan 02 (Frontend) can proceed: API contract changes are complete
- Plan 03 (Migration + Tests) can proceed: ORM definitions are ready for Alembic migration to drop physical columns

---
*Phase: 09-xrpbtc-removal*
*Completed: 2026-02-23*
