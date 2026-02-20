# Pitfalls Research: Cross-Pair Trading

## Research Question

What commonly goes wrong when adding cross-currency position aggregation to trading systems?

## CRITICAL Pitfalls

### P-1: Currency Confusion in P&L Calculation
**Risk:** Mixing EUR and BTC values in the same calculation without explicit conversion.
**Example:** `realized_pnl = sell_price_eur * qty - cost_quote_btc * qty` (units don't match).
**Warning signs:** P&L values that are orders of magnitude too large or too small.
**Prevention:** Always use `cost_eur` (pre-converted). Never mix `cost_quote` across different quote currencies.
**Phase:** Phase 2 (EUR Cost Basis) — establish EUR normalization before any cross-pair logic.

### P-2: Sell Allocation Cross-Contamination (Existing Bug)
**Risk:** A BTC/EUR sell fill closing an XRP lot (or vice versa).
**Warning signs:** Lots with impossible allocations (wrong base asset).
**Prevention:** Filter by base-asset in ALL sell allocation paths (4 functions in lot_service.py).
**Phase:** Phase 1 (Symbol Fix) — must land first, before any cross-pair features.

### P-3: Non-Deterministic Cost Basis
**Risk:** Using current BTC/EUR rate instead of historical rate, making cost basis fluctuate.
**Warning signs:** Same lot shows different break-even at different times.
**Prevention:** Persist `quote_to_eur_rate` at fill time, never recompute. Same pattern as BNB fee conversion.
**Phase:** Phase 2 (EUR Cost Basis).

### P-4: Partial Execution with Cross-Pair Routing
**Risk:** Sell order routed to XRPBTC, but partial fill + cancellation leaves orphaned state.
**Warning signs:** Pairing marked EXECUTED but lots not fully closed.
**Prevention:** Cross-pair sell follows same partial-fill handling as existing system. Allocation happens per fill, not per order.
**Phase:** Phase 4 (Sell Routing).

## HIGH Pitfalls

### P-5: Migration Data Loss
**Risk:** Backfill migration for `cost_eur` uses wrong default for BTC-quoted lots.
**Warning signs:** XRP/BTC lots with `cost_eur = cost_quote` (which would be in BTC, not EUR).
**Prevention:** Migration must be quote-asset-aware: EUR-quoted lots get `cost_eur = cost_quote`, BTC-quoted lots need historical rate lookup (or flag for manual backfill).
**Phase:** Phase 2 (EUR Cost Basis migration).

### P-6: Pairing Heuristic Assumes Single Price
**Risk:** `suggest_pairings()` takes a single `market_price`. Cross-pair needs EUR-equivalent price.
**Warning signs:** Wrong threshold calculations, pairings that shouldn't be profitable appearing profitable.
**Prevention:** Normalize market price to EUR before calling domain function. Domain stays pure.
**Phase:** Phase 3 (Cross-Pair Pairing).

### P-7: Order Creation on Wrong Pair
**Risk:** Sell routing selects XRPBTC but order_service creates order on XRPEUR (or vice versa).
**Warning signs:** Orders with wrong symbol on Binance.
**Prevention:** Route selection returns explicit symbol string, passed directly to order creation. Log routing decision.
**Phase:** Phase 4 (Sell Routing).

### P-8: BTC Proceeds Not Tracked
**Risk:** Selling XRP via XRPBTC yields BTC, not EUR. If not tracked, user's BTC balance becomes inconsistent.
**Warning signs:** Reconciliation shows BTC balance discrepancy after cross-pair sell.
**Prevention:** Ledger events from XRPBTC sells produce BTC, which flows into existing BTC portfolio. Reconciliation already handles multi-asset balances.
**Phase:** Phase 4 (Sell Routing).

## MEDIUM Pitfalls

### P-9: Frontend Display Confusion
**Risk:** Lots from different pairs shown together without clear indication of original purchase pair.
**Warning signs:** User confused about which pair a lot came from.
**Prevention:** Show original symbol as badge/tag on each lot in cross-pair pairing view.
**Phase:** Phase 3 (Cross-Pair Pairing frontend).

### P-10: Rate API Unavailability
**Risk:** BTC/EUR historical rate not available for some XRP/BTC fills (Klines API gap).
**Warning signs:** `cost_eur` is NULL for some lots.
**Prevention:** Same fallback chain as BNB fees: historical → current → skip with warning. Flag lots without EUR cost basis.
**Phase:** Phase 2 (EUR Cost Basis).

### P-11: Locking Scope in Concurrent Environment
**Risk:** Cross-pair pairing locks XRP lots across both pairs. If two pairings try different XRP lots simultaneously, deadlock.
**Warning signs:** Database deadlocks under concurrent pairing creation.
**Prevention:** Single-user system, row-level locking already in place. For future multi-user: lock by base-asset.
**Phase:** Phase 3 (Cross-Pair Pairing).

### P-12: Test Coverage Gap
**Risk:** Cross-pair scenarios not tested, regression in existing single-pair flows.
**Warning signs:** Existing tests pass but cross-pair produces wrong results.
**Prevention:** Add dedicated cross-pair test suite: lot creation with EUR cost basis, cross-pair allocation, cross-pair pairing simulation, sell routing.
**Phase:** All phases — test as you build.

---

*Generated: 2026-02-20*
