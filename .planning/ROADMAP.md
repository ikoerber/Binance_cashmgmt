# Roadmap: XRP Cross-Pair Pairing

## Overview

This project extends the BTC/EUR cashflow management system with cross-pair lot aggregation for XRP. The journey starts with two independent foundation fixes (sell allocation symbol isolation and EUR cost basis for BTC-quoted lots), converges into the core cross-pair pairing feature, and concludes with automated sell routing for maximum EUR proceeds. Phases 1 and 2 are fully independent and can be built in parallel. Phase 3 depends on both completing. Phase 4 depends on Phase 3.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

**Parallelization Note:** Phases 1 and 2 have zero dependencies on each other. They can be executed in any order or in parallel. Both must complete before Phase 3 begins.

- [x] **Phase 1: Sell Allocation Symbol Isolation** - Fix cross-asset contamination bug by filtering sell allocation queries on base-asset
- [x] **Phase 2: EUR Cost Basis** - Persist historical BTC/EUR rate on BTC-quoted lots for deterministic EUR-normalized P&L (completed 2026-02-20)
- [ ] **Phase 3: Cross-Pair Pairing** - Enable mixed XRP/EUR + XRP/BTC lot pairings with EUR-normalized P&L and dual-route simulation
- [ ] **Phase 4: Sell Routing** - Automatically route pairing execution to the pair with highest EUR proceeds

## Phase Details

### Phase 1: Sell Allocation Symbol Isolation
**Goal**: Sell fills only close lots of the same base asset, preventing cross-asset contamination
**Depends on**: Nothing (independent, parallelizable with Phase 2)
**Requirements**: ALLOC-01, ALLOC-02, ALLOC-03
**Success Criteria** (what must be TRUE):
  1. A BTC sell fill never allocates against an XRP lot (and vice versa) under any allocation strategy
  2. All 4 allocation paths (FIFO, LIFO, HIGHEST_COST, lot-specific) filter by base-asset before sorting
  3. Symbol Registry provides `get_symbols_for_base_asset()` that returns all symbols for a given base (e.g., XRP -> [XRPEUR, XRPBTC])
  4. Existing BTC/EUR and ETH/EUR sell allocation behavior is unchanged (backward compatible)
**Plans**: 1 plan

Plans:
- [x] 01-01-PLAN.md -- Add base-asset filtering to all 4 sell allocation paths + symbol registry helper + isolation tests

### Phase 2: EUR Cost Basis
**Goal**: Every lot has a deterministic EUR cost basis computed from the historical exchange rate at fill time
**Depends on**: Nothing (independent, parallelizable with Phase 1)
**Requirements**: COST-01, COST-02, COST-03, COST-04, COST-05
**Success Criteria** (what must be TRUE):
  1. When an XRP/BTC lot is created via sync, `cost_eur` reflects the BTC cost converted at the BTC/EUR rate from the fill timestamp (not current rate)
  2. `quote_to_eur_rate` is persisted on the lot and never recomputed -- same lot always shows same EUR cost
  3. For EUR-quoted lots, `cost_eur` equals `cost_quote` and `quote_to_eur_rate` is 1.0 (no API call needed)
  4. Alembic migration backfills existing lots correctly: EUR-quoted lots get rate=1.0, BTC-quoted lots get historical rate or backfill flag
  5. `break_even_eur` (cost_eur / qty_base_initial) is computable for every lot regardless of quote currency
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- TDD: Domain layer EUR cost basis (TradeLot dataclass + lots.py cost computation + tests)
- [x] 02-02-PLAN.md -- Service integration + DB migration + backfill script (sync rate fetching, lot persistence, Alembic, backfill)

### Phase 3: Cross-Pair Pairing
**Goal**: Users can create pairings that combine XRP/EUR and XRP/BTC lots with accurate EUR-denominated P&L
**Depends on**: Phase 1, Phase 2
**Requirements**: PAIR-01, PAIR-02, PAIR-03, PAIR-04, PAIR-05
**Success Criteria** (what must be TRUE):
  1. Pairing suggestion heuristic considers all XRP lots (both XRPEUR and XRPBTC) when building pairing candidates
  2. P&L calculation within pairings uses EUR-normalized cost basis (`cost_eur`), producing correct EUR profit/loss for mixed-pair pairings
  3. Pairing simulation shows dual-route comparison: projected EUR proceeds via XRPEUR direct vs XRPBTC-then-BTC/EUR conversion
  4. Frontend pairing UI displays pair-of-origin badge (XRPEUR / XRPBTC) on each lot within a cross-pair pairing
  5. Pairing model stores `base_asset` for cross-pair pairings, distinguishing them from single-pair pairings
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md -- TDD: Cross-pair pairing domain logic (EUR-normalized heuristic, dual-route comparison, model extensions)
- [ ] 03-02-PLAN.md -- Service layer + DB migration + API extension (multi-symbol lot loading, base_asset persistence, dual-route simulation endpoint)
- [ ] 03-03-PLAN.md -- Frontend cross-pair UI (cross-pair toggle, pair-of-origin badges, dual-route display in SimulationModal)

### Phase 4: Sell Routing
**Goal**: System automatically executes pairing sells via the pair that maximizes EUR proceeds
**Depends on**: Phase 3
**Requirements**: ROUTE-01, ROUTE-02, ROUTE-03, ROUTE-04
**Success Criteria** (what must be TRUE):
  1. At pairing execution time, system computes EUR proceeds for both routes (XRPEUR direct and XRPBTC * current BTCEUR) and selects the higher one
  2. Sell order is placed on the selected pair via Binance API with correct symbol, price, and quantity
  3. Routing decision is logged with both prices, both computed EUR proceeds, and the delta between routes
  4. After execution, sell fills from the routed pair correctly allocate against all XRP lots in the pairing (regardless of original purchase pair) with EUR-normalized realized P&L
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

## Progress

**Execution Order:**
Phases 1 and 2 are independent and can execute in any order or in parallel. Phase 3 requires both. Phase 4 requires Phase 3.

Dependency graph: `(Phase 1 || Phase 2) -> Phase 3 -> Phase 4`

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Sell Allocation Symbol Isolation | 1/1 | Complete | 2026-02-20 |
| 2. EUR Cost Basis | 2/2 | Complete | 2026-02-20 |
| 3. Cross-Pair Pairing | 1/3 | In Progress | - |
| 4. Sell Routing | 0/? | Not started | - |
