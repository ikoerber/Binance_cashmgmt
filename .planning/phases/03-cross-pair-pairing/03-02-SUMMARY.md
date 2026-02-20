---
phase: 03-cross-pair-pairing
plan: 02
subsystem: api
tags: [pairing, cross-pair, alembic, migration, service-layer, api, decimal-string-transport, dual-route]

# Dependency graph
requires:
  - phase: 03-cross-pair-pairing
    provides: Domain logic (suggest_pairings use_eur_cost, compute_dual_route_comparison, Pairing.base_asset, PairingItem.cost_eur/lot_symbol)
  - phase: 01-sell-allocation-symbol-isolation
    provides: symbol_registry (get_symbols_for_base_asset) for multi-symbol lot queries
  - phase: 02-eur-cost-basis
    provides: TradeLotDB.cost_eur for EUR-normalized cost lookup in service layer
provides:
  - PairingDB.base_asset column (cross-pair identifier in DB)
  - PairingItemDB.cost_eur and lot_symbol columns (EUR cost + pair-of-origin in DB)
  - Alembic migration 569e05c9ddf9 adding cross-pair columns
  - Service layer cross-pair aware suggestions, creation, simulation, listing
  - API endpoints accepting base_asset parameter for cross-pair mode
  - Simulate endpoint with xrpbtc_price/btceur_price Decimal-string params for dual-route comparison
  - List endpoint with base_asset filter
affects: [03-03 frontend cross-pair UI, 04 sell routing]

# Tech tracking
tech-stack:
  added: []
  patterns: [base_asset parameter passthrough from API -> service -> domain, Decimal-String-Transport for cross-pair prices (xrpbtc_price/btceur_price as query string not float), dual_route_comparison dict serialization with string Decimals, cost_eur proportional computation in create_pairing]

key-files:
  created:
    - backend/alembic/versions/569e05c9ddf9_add_cross_pair_pairing_columns.py
  modified:
    - backend/app/db/models.py
    - backend/app/services/pairing_service.py
    - backend/app/api/routes/pairing.py

key-decisions:
  - "Existing with_for_update() row-level locking preserved unchanged in create_pairing -- base_asset fields set AFTER locked query"
  - "xrpbtc_price and btceur_price transported as Decimal strings (not float) per CLAUDE.md invariant on price precision"
  - "base_asset validation in API layer via get_symbols_for_base_asset() returning 400 on unknown base asset"
  - "cost_eur on PairingItemDB computed proportionally from lot's cost_eur based on qty_base/qty_base_initial ratio"
  - "Existing pairings get base_asset=NULL -- no backfill needed for single-pair pairings"

patterns-established:
  - "base_asset parameter passthrough: API (query/body) -> service (function param) -> domain (use_eur_cost=True)"
  - "Cross-pair validation pattern: base_asset not None skips is_known_symbol check (base_asset takes precedence)"
  - "Dual-route comparison serialization: RouteDetails fields as string Decimals in dict, optional inclusion when prices provided"

requirements-completed: [PAIR-03, PAIR-04]

# Metrics
duration: 5min
completed: 2026-02-20
---

# Phase 3 Plan 02: Cross-Pair Pairing Service + API Integration Summary

**DB schema (base_asset, cost_eur, lot_symbol columns), Alembic migration, service layer multi-symbol lot loading, and API endpoints with base_asset param + Decimal-string dual-route prices**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-20T17:43:30Z
- **Completed:** 2026-02-20T17:49:11Z
- **Tasks:** 2 (DB+service, API routes)
- **Files modified:** 4

## Accomplishments
- Added base_asset column to PairingDB and cost_eur/lot_symbol to PairingItemDB with Alembic migration (SQLite batch_alter_table)
- Service layer extended for cross-pair: multi-symbol lot loading via get_symbols_for_base_asset(), EUR-normalized suggestions, cross-pair creation with proportional cost_eur, dual-route comparison in simulation
- API routes extended: suggestions/create/list accept base_asset, simulate accepts xrpbtc_price/btceur_price as Decimal strings
- Full backward compatibility: all 620 existing tests pass unchanged, single-pair behavior identical

## Task Commits

Each task was committed atomically:

1. **Task 1: DB schema + Alembic migration + service layer** - `fc7ce86` (feat)
2. **Task 2: API routes extension** - `59009ac` (feat)

## Files Created/Modified
- `backend/alembic/versions/569e05c9ddf9_add_cross_pair_pairing_columns.py` - Migration adding base_asset to pairings, cost_eur + lot_symbol to pairing_items
- `backend/app/db/models.py` - PairingDB: added base_asset column; PairingItemDB: added cost_eur, lot_symbol columns
- `backend/app/services/pairing_service.py` - Cross-pair aware: get_pairing_suggestions (base_asset), create_pairing (base_asset, cost_eur persistence), simulate_pairing_execution (dual-route), list_pairings (base_asset filter), _pairing_to_dict (cross-pair fields), _pairing_db_to_domain (new field mapping)
- `backend/app/api/routes/pairing.py` - Suggestions: base_asset query param; Create: base_asset in request body; Simulate: xrpbtc_price + btceur_price Decimal strings; List: base_asset filter; PairingCreateRequest: added base_asset field

## Decisions Made
- Preserved existing with_for_update() row-level locking in create_pairing -- the new base_asset fields are set after the locked lot query, not changing the locking mechanism itself (CLAUDE.md invariant 20)
- xrpbtc_price and btceur_price use Decimal-String-Transport (query params as `str`, converted via `Decimal(str)`) to avoid IEEE 754 precision loss on 8-decimal XRP/BTC prices
- base_asset validation uses get_symbols_for_base_asset() which raises ValueError for unknown base assets -- caught as 400 at API layer
- cost_eur on PairingItemDB computed proportionally: `(lot.cost_eur / lot.qty_base_initial) * qty_base` -- mirrors existing cost_quote proportional computation pattern
- dual_route_comparison is only included in simulation response when both xrpbtc_price and btceur_price are provided AND the pairing has base_asset -- fully optional, backward compatible

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Alembic autogenerate detected false positive type changes on api_credentials.testnet (VARCHAR -> Boolean) and trade_lots.auto_order_enabled -- cleaned up migration to only include the 3 new columns (standard pattern per Phase 2)
- Migration file was blocked by backend/.gitignore pattern `alembic/versions/*.py` -- used `git add -f` (same approach as previous migrations in the repository)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend API fully supports cross-pair pairing flow (suggestions, creation, simulation, listing)
- Ready for Plan 03 (frontend cross-pair UI) to consume these endpoints
- Frontend needs to pass base_asset param on suggestions/create, xrpbtc_price/btceur_price on simulate
- All domain, service, and API layers are cross-pair ready

## Self-Check: PASSED

All artifacts verified:
- [x] `backend/alembic/versions/569e05c9ddf9_add_cross_pair_pairing_columns.py` exists
- [x] `backend/app/db/models.py` contains base_asset on PairingDB, cost_eur + lot_symbol on PairingItemDB
- [x] `backend/app/services/pairing_service.py` contains base_asset parameter, compute_dual_route_comparison import
- [x] `backend/app/api/routes/pairing.py` contains base_asset query param, xrpbtc_price/btceur_price params
- [x] Commit `fc7ce86` (Task 1) exists
- [x] Commit `59009ac` (Task 2) exists
- [x] Migration at head (569e05c9ddf9)
- [x] 49 pairing tests pass
- [x] 620 total tests pass (zero regressions)

---
*Phase: 03-cross-pair-pairing*
*Completed: 2026-02-20*
