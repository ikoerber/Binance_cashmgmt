---
phase: 13-xrpbtc-infrastructure
plan: 01
subsystem: database, api, domain
tags: [symbol-registry, alembic, migration, decimal, btc-quoted, lot-service]

# Dependency graph
requires: []
provides:
  - "XRPBTC in KNOWN_PAIRS with BTC quote asset and price_precision=8"
  - "Helper functions: is_eur_quoted, is_pairing_enabled, is_order_creation_enabled"
  - "quote_to_eur_rate column on TradeLotDB (Numeric 20,10, nullable)"
  - "Alembic migration b2f6ed7bb098 with EUR lot backfill (rate=1.0)"
  - "Domain lots.py conditional EUR cost branching (EUR vs BTC-quoted)"
  - "TradeLot dataclass quote_to_eur_rate field and break_even_eur property"
  - "Lot API response includes quote_to_eur_rate field"
affects: [13-02, 13-03, sync-service, lot-service, frontend-lots]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Quote-asset-conditional cost calculation in domain layer"
    - "Service-layer deferred EUR rate assignment for non-EUR pairs"

key-files:
  created:
    - "backend/alembic/versions/b2f6ed7bb098_readd_quote_to_eur_rate_for_v3_0.py"
  modified:
    - "backend/app/symbol_registry.py"
    - "backend/app/db/models.py"
    - "backend/app/domain/lots.py"
    - "backend/app/domain/models.py"
    - "backend/app/services/lot_service.py"

key-decisions:
  - "Only re-add quote_to_eur_rate column (not pairing columns) since pairing is disabled for XRPBTC"
  - "BTC-quoted lots get cost_eur=None from domain layer; service layer fills after historical rate fetch"
  - "EUR-quoted lots backfilled with quote_to_eur_rate=1.0 in migration (570 rows)"

patterns-established:
  - "is_eur_quoted(symbol) guard pattern for feature gating by quote asset"
  - "Domain returns None for external-data-dependent fields; service layer enriches"

requirements-completed: [INFRA-01, INFRA-03]

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 13 Plan 01: Symbol Registry + Migration + Domain Logic Summary

**XRPBTC added to symbol registry with Alembic migration for quote_to_eur_rate, conditional EUR cost branching in domain layer, and lot API serialization**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T20:50:58Z
- **Completed:** 2026-02-25T20:55:04Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- XRPBTC registered as known trading pair with BTC quote asset and price_precision=8
- Three helper functions (is_eur_quoted, is_pairing_enabled, is_order_creation_enabled) gate features by quote asset
- Alembic migration b2f6ed7bb098 re-adds quote_to_eur_rate column (dropped in v2.0 migration 094dac6f695a) and backfills 570 EUR-quoted lots with rate=1.0
- Domain layer correctly returns cost_eur=None for BTC-quoted lots (service layer will set after historical rate fetch)
- Lot API response includes quote_to_eur_rate field for frontend consumption
- All 661 existing tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Symbol Registry + Migration + ORM** - `4ed754f` (feat)
2. **Task 2: Domain Logic + Lot Serialization** - `12e32f7` (feat)

## Files Created/Modified

- `backend/app/symbol_registry.py` - Added XRPBTC to KNOWN_PAIRS, added is_eur_quoted, is_pairing_enabled, is_order_creation_enabled helpers
- `backend/app/db/models.py` - Added quote_to_eur_rate column to TradeLotDB (Numeric 20,10, nullable)
- `backend/alembic/versions/b2f6ed7bb098_readd_quote_to_eur_rate_for_v3_0.py` - Forward migration re-adding quote_to_eur_rate with EUR lot backfill
- `backend/app/domain/lots.py` - Conditional EUR cost calculation: EUR-quoted = cost_quote, BTC-quoted = None
- `backend/app/domain/models.py` - Added quote_to_eur_rate field to TradeLot dataclass
- `backend/app/services/lot_service.py` - Added quote_to_eur_rate to API response dict, lot creation, and domain conversion

## Decisions Made

- Only re-added `quote_to_eur_rate` column from the dropped columns in migration 094dac6f695a. Pairing columns (base_asset, routing_decision_json, cost_eur on pairing_items, lot_symbol, realized_pnl_eur) are not needed because pairing is disabled for BTC-quoted pairs per user decision.
- BTC-quoted lots receive `cost_eur = None` from the domain layer. The service layer (sync_service, Plan 02) will set `cost_eur` and `quote_to_eur_rate` after fetching the historical BTC/EUR rate via Binance Klines API.
- Backfilled all 570 existing EUR-quoted lots with `quote_to_eur_rate = 1.0` since their cost_eur already equals cost_quote.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Alembic version table not stamped**
- **Found during:** Task 1 (Migration application)
- **Issue:** Database had all tables but no alembic_version stamp, causing `alembic upgrade head` to try running all migrations from scratch
- **Fix:** Stamped database with `alembic stamp 094dac6f695a` before applying the new migration
- **Files modified:** None (database metadata only)
- **Verification:** `alembic upgrade head` succeeded after stamping
- **Committed in:** N/A (runtime database state, not code)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Standard Alembic state resolution. No scope creep.

## Issues Encountered

None beyond the Alembic stamp issue documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Symbol registry foundation complete: XRPBTC recognized with correct metadata
- Database schema ready: quote_to_eur_rate column available for BTC/EUR rate storage
- Domain layer ready: correctly branches EUR vs BTC-quoted cost calculation
- Plan 02 (Sync + Backfill + EUR conversion) can proceed: needs to implement historical BTC/EUR rate fetching in sync_service and backfill existing XRPBTC lots
- Plan 03 (Frontend) can proceed: lot API already returns quote_to_eur_rate field

## Self-Check: PASSED

All 7 files verified present. Both task commits (4ed754f, 12e32f7) verified in git log.

---
*Phase: 13-xrpbtc-infrastructure*
*Completed: 2026-02-25*
