# Features Research: Cross-Pair Trading (XRP/EUR + XRP/BTC)

## Research Question

What features do cross-pair/cross-currency trading aggregation systems need? What's table stakes vs differentiating?

## Table Stakes (Must-Have)

### TS-1: Sell Allocation Symbol Isolation (Bug Fix)
**What:** Filter sell allocation to match lots by base-asset, preventing BTC sells from closing XRP lots.
**Current state:** `process_sell_fill_fifo` and all strategy variants query ALL open lots without symbol filter.
**Complexity:** LOW (~30 lines, 4 queries to fix). No schema change.
**Dependencies:** None — standalone bug fix.

### TS-2: EUR Cost Basis for BTC-Quoted Lots
**What:** Persist historical BTC/EUR rate and EUR-equivalent cost on XRP/BTC lots at fill time.
**Design:** Add `cost_eur` + `quote_to_eur_rate` to TradeLotDB. Reuse `get_historical_price()`.
**Complexity:** MEDIUM (~100 lines). Schema migration + lot creation logic + backfill.
**Dependencies:** Symbol registry (already has `get_quote_asset()`).

### TS-3: Cross-Pair Lot Selection in Pairing
**What:** Allow pairing heuristic to include lots from both XRPEUR and XRPBTC with EUR-normalized P&L.
**Design:** Query by base-asset instead of symbol. Change `Pairing.symbol` to `Pairing.base_asset`.
**Complexity:** HIGH (~200 lines). Domain models + heuristic + service + frontend.
**Dependencies:** TS-2 (EUR cost basis must exist).

### TS-4: Cross-Pair Pairing Simulation
**What:** `simulate_pairing` computes EUR P&L for mixed-pair lots with sell-route comparison.
**Design:** Simulation takes two market prices, shows both routing options.
**Complexity:** MEDIUM (~80 lines). Concentrated in simulation function.
**Dependencies:** TS-3.

### TS-5: Sell Routing (Best-Pair Selection)
**What:** Auto-select XRP/EUR vs XRP/BTC for sell order based on EUR proceeds.
**Complexity:** MEDIUM (~120 lines). Order creation flow change.
**Dependencies:** TS-3, TS-4.

### TS-6: Cross-Pair Sell Allocation
**What:** Sell fills allocate against ALL XRP lots regardless of purchase pair, with EUR P&L.
**Design:** Extends TS-1 base-asset filter + uses `cost_eur` for P&L calculation.
**Complexity:** HIGH (~150 lines). Allocation P&L logic changes.
**Dependencies:** TS-1, TS-2.

## Dependency Graph

```
TS-1 (Symbol Fix) ─────────────────────────┐
                                            │
TS-2 (EUR Cost Basis) ──┬──────────────────┤
                         │                  │
                         v                  v
                  TS-3 (Cross-Pair) --> TS-6 (Cross-Pair Alloc)
                         │
                         v
                  TS-4 (Simulation)
                         │
                         v
                  TS-5 (Sell Routing)
```

**TS-1 and TS-2 can be parallelized.** Critical path: TS-2 → TS-3 → TS-4 → TS-5.

## Differentiators (Nice-to-Have, Post-MVP)

| Feature | Complexity | Description |
|---------|-----------|-------------|
| D-1: Dual-Price Display | LOW | Show XRPEUR + XRPBTC prices side-by-side in pairing UI |
| D-2: Route Optimization Report | LOW | Post-execution: "Routing saved you X EUR" |
| D-3: XRP Total View | MEDIUM | Combined XRPEUR+XRPBTC portfolio card |
| D-4: Sell-Route Override | LOW | Settings: "Always sell via EUR/BTC/Auto" |
| D-5: Split Sell Orders | HIGH | Split across pairs based on liquidity |
| D-6: Arbitrage Alert | MEDIUM | Alert on significant price discrepancy |

## Anti-Features (Deliberately NOT Building)

| Feature | Reason |
|---------|--------|
| Generic cross-pair for all assets | XRP is the only asset with 2 quote-pairs. YAGNI. |
| Auto BTC-to-EUR conversion after sell | Separate trading decision, not pairing concern |
| Arbitrage execution | Different use case, requires sub-second latency |
| Tax-optimized routing | Out of project scope (CLAUDE.md) |
| Cross-base-asset pairing | Can't sell XRP to close BTC lot |
| Multi-exchange cross-pair | Single-exchange project |
| Aggregated backend endpoint | Frontend Overview already handles aggregation |

## Complexity Summary

**Total estimated scope:** ~680 lines of production code, 1 schema migration.

---

*Generated: 2026-02-20*
