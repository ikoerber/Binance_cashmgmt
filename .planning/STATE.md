# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** XRP-Lots unabhaengig vom Quote-Asset (EUR oder BTC) in einem Pairing buendeln und ueber das ertragreichere Pair verkaufen
**Current focus:** Phase 3 (Cross-Pair Pairing) -- Plan 01 complete, Plan 02 next

## Current Position

Phase: 3 of 4 (Cross-Pair Pairing)
Plan: 1 of 3 in current phase
Status: 03-01 complete (domain logic), 03-02 next (service integration)
Last activity: 2026-02-20 -- Completed 03-01-PLAN.md

Progress: [####------] 33% (Phase 3)

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 3.5min
- Total execution time: 14min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 Sell Allocation | 1 | 3min | 3min |
| 02 EUR Cost Basis | 2 | 7min | 3.5min |
| 03 Cross-Pair Pairing | 1 | 4min | 4min |

**Recent Trend:**
- Last 5 plans: 01-01 (3min), 02-01 (3min), 02-02 (4min), 03-01 (4min)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Phases 1 and 2 are independent -- can be planned and executed in any order or in parallel
- [Roadmap]: 4 phases derived from 4 natural requirement categories (ALLOC, COST, PAIR, ROUTE)
- [Research]: Existing `get_historical_price()` pattern reused for BTC/EUR rate conversion (no new services)
- [Phase 01]: Base-asset filtering at service layer (DB query level), not domain layer
- [Phase 01]: get_symbols_for_base_asset() raises ValueError for unknown base-asset (consistent with get_base_asset())
- [Phase 02-01]: cost_eur and quote_to_eur_rate use Optional[Decimal] with None default for backward compatibility and backfill support
- [Phase 02-01]: EUR-quoted lots auto-detect via get_quote_asset() -- no caller action needed
- [Phase 02-01]: break_even_eur returns None (not zero) when cost_eur is unknown or qty is zero
- [Phase 02-02]: Separate _get_quote_to_eur_rates() from _get_per_fill_fee_conversion_rates() to avoid cache key collisions
- [Phase 02-02]: Migration backfills EUR-quoted lots via SQL; BTC-quoted lots require standalone script with Binance API calls
- [Phase 02-02]: csv_import_service.py intentionally unchanged -- backward compatible, backfill via script for non-EUR lots
- [Phase 02-02]: WebSocket fill handler fetches quote_to_eur_rate inline for real-time non-EUR buy fills
- [Phase 03-01]: suggest_pairings use_eur_cost defaults to False -- all existing callers produce identical results without changes
- [Phase 03-01]: Cross-pair base_asset derived from get_base_asset(lots[0].symbol) -- consistent with symbol_registry pattern
- [Phase 03-01]: Dual-route indirect fees are compounded (two fee steps) not additive -- matches real Binance trading flow
- [Phase 03-01]: PairingItem.cost_eur and lot_symbol are None in default mode -- clean single-pair vs cross-pair separation

### Pending Todos

None yet.

### Blockers/Concerns

- [Research gap]: Frontend UX for mixed-pair pairings needs wireframe during Phase 3 planning

## Session Continuity

Last session: 2026-02-20
Stopped at: Completed 03-01-PLAN.md (Phase 3 plan 1 of 3, service integration next)
Resume file: None
