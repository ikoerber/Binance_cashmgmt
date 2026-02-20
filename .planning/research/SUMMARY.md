# Project Research Summary

**Project:** XRP Cross-Pair Pairing
**Domain:** Cross-currency position aggregation in a ledger-based trading system
**Researched:** 2026-02-20
**Confidence:** HIGH

## Executive Summary

This project adds cross-pair lot aggregation to an existing ledger-based cashflow management system. The core challenge is straightforward: XRP can be bought via XRPEUR or XRPBTC, and lots from both pairs must be combinable in pairings with correct EUR-denominated P&L. The recommended approach follows a pattern already proven in this codebase — historical rate conversion at fill time, identical to how BNB fees are already converted via `get_historical_price()`. No new services, no new abstractions, no architectural changes. The existing 3-tier architecture (Domain/Service/API) absorbs this cleanly.

The critical prerequisite is fixing the existing sell-allocation bug where fills can cross-contaminate across base assets (a BTC sell could theoretically close an XRP lot). This bug fix is independent, low-risk, and must land first. Once that and EUR cost basis normalization are in place, cross-pair pairing and sell routing follow naturally from existing patterns. Total estimated scope is ~680 lines of production code and one schema migration.

The main risks are currency confusion in P&L calculations (mixing EUR and BTC values without conversion) and non-deterministic cost basis (using current rates instead of historical). Both are fully preventable by establishing EUR normalization early (Phase 2) and using pre-computed `cost_eur` everywhere downstream. The codebase already enforces Decimal precision and deterministic computation, so the patterns are well-understood by the team.

## Key Findings

### Recommended Stack

No new technologies required. The project extends existing infrastructure exclusively.

**Core patterns to apply:**
- **Historical rate conversion (existing):** `get_historical_price()` via Binance Klines API — reuse for BTC/EUR rate at XRP/BTC fill time
- **Symbol registry (existing):** `get_base_asset()`, `get_quote_asset()` — extend with `get_symbols_for_base_asset()` for cross-pair queries
- **Decimal-string transport (existing):** `cost_eur` and `quote_to_eur_rate` as Decimal, API transport as String
- **Alembic migration with backfill:** `render_as_batch=True` for SQLite, quote-asset-aware backfill logic

### Expected Features

**Must have (table stakes):**
- **TS-1: Sell allocation symbol isolation** — Bug fix, prevents cross-asset contamination (~30 lines, no schema change)
- **TS-2: EUR cost basis for BTC-quoted lots** — Historical BTC/EUR rate persisted at fill time (~100 lines, schema migration)
- **TS-3: Cross-pair lot selection in pairing** — Pairing heuristic queries by base-asset with EUR-normalized P&L (~200 lines)
- **TS-4: Cross-pair pairing simulation** — Simulation computes EUR P&L for mixed-pair lots (~80 lines)
- **TS-5: Sell routing (best-pair selection)** — Auto-select XRPEUR vs XRPBTC for max EUR proceeds (~120 lines)
- **TS-6: Cross-pair sell allocation** — Sell fills allocate against all XRP lots regardless of purchase pair (~150 lines)

**Should have (post-MVP differentiators):**
- D-1: Dual-price display (XRPEUR + XRPBTC side-by-side in pairing UI)
- D-2: Route optimization report ("routing saved you X EUR")
- D-3: XRP total view (combined XRPEUR+XRPBTC portfolio card)
- D-4: Sell-route override setting (always EUR / always BTC / auto)

**Defer (v2+):**
- D-5: Split sell orders across pairs based on liquidity (HIGH complexity)
- D-6: Arbitrage alert on price discrepancy
- Generic cross-pair for all assets (YAGNI — only XRP has two pairs)
- Tax-optimized routing (out of project scope)

### Architecture Approach

The existing 3-tier architecture (Domain pure logic / Service I/O / API thin routes) absorbs cross-pair cleanly. Domain functions receive EUR-normalized data; services handle conversion before calling domain. The ledger structure, per-symbol portfolio computation, Binance sync, order tracking, reconciliation, and all other modules remain unchanged. Two schema extensions (TradeLotDB: `cost_eur` + `quote_to_eur_rate`; PairingDB: `base_asset` + `is_cross_pair`) with backward-compatible backfill.

**Major components affected:**
1. **lot_service.py** — Base-asset filter on sell allocation queries, EUR cost basis persistence
2. **lots.py (domain)** — EUR cost basis calculation, `break_even_eur` property
3. **pairing.py (domain)** — EUR-normalized heuristic and simulation (already pure)
4. **order_service.py** — Sell routing with real-time price comparison
5. **sync_service.py** — Historical BTC/EUR rate fetch during XRP/BTC lot creation

### Critical Pitfalls

1. **Currency confusion in P&L (P-1, CRITICAL)** — Mixing EUR and BTC values in the same formula. Prevent by always using pre-computed `cost_eur`, never mixing `cost_quote` across different quote currencies.
2. **Sell allocation cross-contamination (P-2, CRITICAL)** — Existing bug where wrong-asset sells can close lots. Fix first in Phase 1 by adding base-asset filter to all 4 allocation functions.
3. **Non-deterministic cost basis (P-3, CRITICAL)** — Using current BTC/EUR rate instead of historical. Prevent by persisting `quote_to_eur_rate` at fill time, never recomputing.
4. **Migration data loss (P-5, HIGH)** — Backfill must be quote-asset-aware: EUR-quoted lots get `cost_eur = cost_quote`, BTC-quoted lots need historical rate lookup or manual backfill flag.
5. **BTC proceeds not tracked after XRPBTC sell (P-8, HIGH)** — Selling XRP via XRPBTC yields BTC, not EUR. Ledger events must correctly flow into BTC portfolio. Reconciliation already handles multi-asset.

## Implications for Roadmap

Based on research, the project decomposes into 4 phases with a clear dependency chain.

### Phase 1: Sell Allocation Symbol Fix
**Rationale:** Fixes an existing correctness bug. Independent of all other phases. Must land first to prevent cross-contamination in production while other phases are developed.
**Delivers:** Safe sell allocation that respects base-asset boundaries.
**Addresses:** TS-1 (Sell Allocation Symbol Isolation).
**Avoids:** P-2 (cross-contamination). Without this fix, adding XRP/BTC lots would make the existing bug actively dangerous.
**Estimated scope:** ~30 lines, no schema change, 4 queries to fix.

### Phase 2: EUR Cost Basis for BTC-Quoted Lots
**Rationale:** Foundational data layer that all downstream cross-pair features depend on. Can be built in parallel with Phase 1.
**Delivers:** `cost_eur` and `quote_to_eur_rate` on every lot, enabling EUR-normalized P&L calculations.
**Addresses:** TS-2 (EUR Cost Basis).
**Avoids:** P-1 (currency confusion), P-3 (non-deterministic cost basis), P-5 (migration data loss), P-10 (rate API unavailability).
**Estimated scope:** ~100 lines + Alembic migration with backfill.

### Phase 3: Cross-Pair Pairing and Simulation
**Rationale:** Core feature, requires Phase 1 + 2. Groups lots by base-asset and enables mixed-pair pairings with EUR-normalized P&L.
**Delivers:** Cross-pair pairing suggestions, manual pairing across quote-currencies, simulation with dual-route comparison.
**Addresses:** TS-3 (Cross-Pair Lot Selection), TS-4 (Cross-Pair Simulation), TS-6 (Cross-Pair Sell Allocation).
**Avoids:** P-6 (single-price assumption), P-9 (frontend display confusion), P-11 (locking scope), P-12 (test coverage gap).
**Estimated scope:** ~350 lines (domain + service + frontend).

### Phase 4: Sell Routing and Execution
**Rationale:** Final phase, requires Phase 3. Adds automated best-pair selection at execution time.
**Delivers:** Auto-routing XRPEUR vs XRPBTC for maximum EUR proceeds, auditable routing decisions.
**Addresses:** TS-5 (Sell Routing).
**Avoids:** P-4 (partial execution with cross-pair routing), P-7 (order creation on wrong pair), P-8 (BTC proceeds not tracked).
**Estimated scope:** ~120 lines.

### Phase Ordering Rationale

- **Phase 1 and Phase 2 are independent and can be parallelized.** This is the most important scheduling insight from the research. Both are prerequisites for Phase 3 but have zero dependency on each other.
- **Phase 3 is the critical path bottleneck.** It is the largest phase (~350 lines, domain + service + frontend) and depends on both Phase 1 and Phase 2 completing first.
- **Phase 4 depends only on Phase 3.** Sell routing is a service-layer concern that sits on top of the cross-pair pairing model.
- **The dependency graph is: `(P1 || P2) → P3 → P4`.** This means the project can start with two parallel workstreams.

### Research Flags

Phases with standard patterns (skip research-phase):
- **Phase 1 (Symbol Fix):** Straightforward query filter change. Pattern is adding a WHERE clause. No ambiguity.
- **Phase 2 (EUR Cost Basis):** Directly reuses existing `get_historical_price()` pattern from BNB fee conversion. Well-proven in codebase.
- **Phase 4 (Sell Routing):** Simple price comparison + order creation. Standard best-execution logic.

Phases that may need deeper attention during planning:
- **Phase 3 (Cross-Pair Pairing):** Largest phase with domain + service + frontend changes. The pairing heuristic modification and frontend UX for mixed-pair lots need careful task breakdown. Not "research" per se, but needs thorough specification during planning.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new technologies. All patterns already exist in codebase (BNB fee conversion, symbol registry). |
| Features | HIGH | Clear dependency graph, well-bounded scope (~680 lines total). Feature list derived from codebase analysis. |
| Architecture | HIGH | Existing 3-tier architecture absorbs changes cleanly. Layer assignments are unambiguous. |
| Pitfalls | HIGH | All pitfalls have concrete prevention strategies. Most critical ones (P-1, P-2, P-3) are addressed by Phase 1+2 landing first. |

**Overall confidence:** HIGH

This is a well-scoped extension to an existing system with proven patterns. The codebase already solves the harder variant of this problem (BNB fee conversion with historical rates). Cross-pair is the same pattern applied to lot cost basis.

### Gaps to Address

- **Backfill strategy for existing XRP/BTC lots:** If XRP/BTC lots already exist in production, the migration needs historical BTC/EUR rates. Determine whether to batch-fetch rates or flag for manual review during Phase 2 planning.
- **Frontend UX for mixed-pair pairings:** How to clearly communicate to the user that a pairing contains lots from different quote-currencies. Needs wireframe/mockup during Phase 3 planning.
- **BTC proceeds flow after XRPBTC sell:** Verify that the existing ledger event flow correctly credits BTC balance when selling XRP via XRPBTC. May need a targeted test during Phase 4.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `backend/app/domain/lots.py`, `backend/app/services/sync_service.py`, `backend/app/services/binance.py` — existing historical rate conversion pattern
- Codebase analysis: `backend/app/domain/pairing.py`, `backend/app/services/pairing_service.py` — pairing heuristic and simulation architecture
- Codebase analysis: `backend/app/services/lot_service.py` — sell allocation flow (all 4 strategy functions)
- CLAUDE.md project specification — invariants, architecture, domain model

### Secondary (MEDIUM confidence)
- Domain knowledge: IAS 21 foreign-currency translation principles — cost basis at historical rate
- Domain knowledge: Best-execution routing patterns in multi-venue trading systems

---
*Research completed: 2026-02-20*
*Ready for roadmap: yes*
