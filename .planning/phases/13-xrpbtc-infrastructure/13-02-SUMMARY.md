---
phase: 13-xrpbtc-infrastructure
plan: 02
subsystem: api, services, database
tags: [sync-service, pairing-guard, order-guard, eur-conversion, btc-quoted, decimal-precision, backfill]

# Dependency graph
requires:
  - phase: 13-01
    provides: "XRPBTC in KNOWN_PAIRS, is_eur_quoted/is_pairing_enabled/is_order_creation_enabled helpers, quote_to_eur_rate column, domain EUR cost branching"
provides:
  - "Sync pipeline fetches historical BTC/EUR rate for XRPBTC fills and populates cost_eur + quote_to_eur_rate"
  - "Minute-cached BTC/EUR rate lookups during sync (same pattern as fee conversion)"
  - "Graceful fallback: cost_eur stays None on rate fetch failure (backfillable)"
  - "Three-layer pairing isolation: symbol_registry, pairing_service, API routes"
  - "Three-layer order isolation: symbol_registry, API route guard, auto-order toggle guard"
  - "Backfill script uses Decimal precision (no float for financial values)"
affects: [13-03, frontend-lots, frontend-pairing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Minute-cached historical rate fetch during sync (reuses fee conversion pattern)"
    - "Three-layer feature gating: registry helper -> service guard -> API route guard"
    - "Graceful degradation for rate fetch failures (lot created, cost_eur=None, backfillable)"

key-files:
  created: []
  modified:
    - "backend/app/services/sync_service.py"
    - "backend/app/services/pairing_service.py"
    - "backend/app/api/routes/pairing.py"
    - "backend/app/api/routes/orders.py"
    - "backend/app/api/routes/lots.py"
    - "backend/scripts/backfill_cost_eur.py"

key-decisions:
  - "EUR rate enrichment happens in sync_service after lot creation (not in domain layer) to maintain domain purity"
  - "Pairing guards at both service and API level for defense-in-depth (service raises ValueError, API returns HTTP 400)"
  - "Auto-order toggle also gated for BTC-quoted lots (prevents meaningless auto-order flag)"
  - "Backfill script default changed from pg to sqlite to match project's actual database"

patterns-established:
  - "Post-creation lot enrichment via _enrich_lot_with_eur_rate() in sync_service"
  - "API-level pairing guard pattern: load pairing -> check symbol -> proceed or reject"

requirements-completed: [INFRA-02, INFRA-03, INFRA-04]

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 13 Plan 02: Sync Pipeline EUR Conversion + Pairing/Order Guards Summary

**XRPBTC sync pipeline with historical BTC/EUR rate conversion via minute-cached Klines API, three-layer pairing and order isolation for BTC-quoted pairs, and Decimal-precision backfill script fix**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T20:58:08Z
- **Completed:** 2026-02-25T21:02:59Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Sync pipeline now fetches historical BTC/EUR rate at fill timestamp for XRPBTC lots and populates cost_eur + quote_to_eur_rate
- All pairing API endpoints (suggestions, create, lock, execute, delete) return 400 or empty results for BTC-quoted pairs
- Order creation endpoint and auto-order toggle both reject BTC-quoted lots with HTTP 400
- Backfill script fixed: str() instead of float() for SQL params, default DB changed to sqlite
- Three-layer isolation pattern: symbol_registry helpers -> service guards -> API route guards
- All 661 existing tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Sync Pipeline EUR Conversion + Backfill Fix** - `58e954d` (feat)
2. **Task 2: Pairing + Order API Guards** - `5daecfe` (feat)

## Files Created/Modified

- `backend/app/services/sync_service.py` - Added _enrich_lot_with_eur_rate() method with minute-cached BTC/EUR rate fetch for non-EUR-quoted fills
- `backend/app/services/pairing_service.py` - Added is_pairing_enabled guards to suggest_pairings, create_pairing, lock_pairing, execute_pairing
- `backend/app/api/routes/pairing.py` - Added is_pairing_enabled guards to all 6 pairing endpoints (suggestions, create, lock, execute, delete, plus re-raise for HTTPException)
- `backend/app/api/routes/orders.py` - Added is_order_creation_enabled guard on create_order_for_lot endpoint with lot symbol lookup
- `backend/app/api/routes/lots.py` - Added is_order_creation_enabled guard on auto-order toggle endpoint
- `backend/scripts/backfill_cost_eur.py` - Fixed float() to str() for cost_eur and rate SQL params, changed default DB to sqlite, use DB_URL from env

## Decisions Made

- EUR rate enrichment in sync_service (not domain or lot_service) because it requires I/O (Binance API call). Domain layer stays pure, lot_service creates the lot with cost_eur=None, sync_service fills it after fetching the rate. This follows the pattern established in 13-01 where domain returns None for external-data-dependent fields.
- Pairing guards are implemented at both service level (raises ValueError) and API level (returns HTTP 400) for defense-in-depth. Even if a code path bypasses the API guard, the service guard catches it.
- Auto-order toggle is also gated because enabling auto_order_enabled on a BTC-quoted lot would be meaningless (orders can't be created for those lots).
- Backfill script default changed from PostgreSQL to SQLite to match the project's actual database configuration.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Sync pipeline complete: XRPBTC fills create lots with EUR financials populated via historical BTC/EUR rate
- Pairing isolation complete: BTC-quoted pairs fully excluded from all pairing operations at service and API level
- Order isolation complete: BTC-quoted lots rejected from manual sell order creation and auto-order toggle
- Plan 03 (Frontend) can proceed: lot API already returns cost_eur, break_even_eur, and quote_to_eur_rate for dual display

## Self-Check: PASSED

All 6 modified files verified present. Both task commits (58e954d, 5daecfe) verified in git log.

---
*Phase: 13-xrpbtc-infrastructure*
*Completed: 2026-02-25*
