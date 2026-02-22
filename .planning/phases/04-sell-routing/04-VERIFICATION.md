---
phase: 04-sell-routing
verified: 2026-02-22T21:00:00Z
status: passed
score: 4/4 must-haves verified
gaps: []
human_verification:
  - test: "Live cross-pair pairing execution with real Binance API"
    expected: "System fetches 3 live prices, selects the higher-EUR-proceeds route, places order on selected symbol, persists routing_decision_json"
    why_human: "Requires real Binance API keys and XRP lots in an account; cannot verify actual live price fetch and order placement programmatically without mocking"
---

# Phase 4: Sell Routing Verification Report

**Phase Goal:** System automatically executes pairing sells via the pair that maximizes EUR proceeds
**Verified:** 2026-02-22T21:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (From ROADMAP.md Success Criteria)

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | At pairing execution time, system computes EUR proceeds for both routes (XRPEUR direct and XRPBTC * current BTCEUR) and selects the higher one | VERIFIED | `order_service.py` lines 290-330: `compute_dual_route_comparison()` called with 3 live prices fetched via `binance_service.get_current_price()` for all 3 symbols; `drc.recommended_route` drives symbol override |
| 2  | Sell order is placed on the selected pair via Binance API with correct symbol, price, and quantity | VERIFIED | `order_service.py` lines 332-418: symbol overridden to `selected_symbol`; precision from `get_price_precision(symbol)` / `get_base_precision(symbol)` via symbol_registry; `create_order()` called with correct symbol |
| 3  | Routing decision is logged with both prices, both computed EUR proceeds, and the delta between routes | VERIFIED | `RoutingDecision` dataclass in `models.py` (lines 277-299) captures all fields; persisted as JSON on `PairingDB.routing_decision_json` (line 457); included in `list_pairings()` response (pairing_service.py lines 478-479) and in execute response (order_service.py lines 468-469) |
| 4  | After execution, sell fills from the routed pair correctly allocate against all XRP lots in the pairing (regardless of original purchase pair) with EUR-normalized realized P&L | VERIFIED | `lot_service.py` lines 559-604: cross-pair detection via `pairing_db.base_asset is not None`; `compute_cross_pair_realized_pnl_eur()` called per lot allocation with `btceur_rate` from routing_decision_json; result stored in `alloc_db.realized_pnl_eur` |

**Score:** 4/4 truths verified

### Required Artifacts — Plan 01

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/domain/models.py` | RoutingDecision dataclass | VERIFIED | Lines 277-299: Full dataclass with all 8 fields + `to_dict()` serializing Decimals as strings |
| `backend/app/domain/lots.py` | compute_cross_pair_realized_pnl_eur | VERIFIED | Lines 176-227: Handles EUR/BTC sell quotes, raises ValueError when btceur_rate missing for BTC sells |
| `backend/app/domain/orders.py` | compute_pairing_order_params with symbol-aware precision | VERIFIED | Symbol-registry precision, satoshi encoding for sub-1 prices, EUR max-value conversion |
| `backend/tests/test_sell_routing.py` | Test suite (min 150 lines) | VERIFIED | 281 lines, 13 tests — all 13 pass in 0.02s |

### Required Artifacts — Plan 02

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/services/order_service.py` | Route selection logic with compute_dual_route_comparison | VERIFIED | Lines 287-330: 3-price fetch, DRC computation, selected_symbol override, RoutingDecision build, routing_decision_json persistence at lines 456-458 |
| `backend/app/services/lot_service.py` | EUR-normalized P&L in process_sell_fill_for_pairing | VERIFIED | Lines 559-604: is_cross_pair detection, compute_cross_pair_realized_pnl_eur per allocation, realized_pnl_eur persistence |
| `backend/app/db/models.py` | routing_decision_json on PairingDB and realized_pnl_eur on SellAllocationDB | VERIFIED | PairingDB line 339-341: `JSON nullable=True`; SellAllocationDB lines 239-241: `Numeric(20,10) nullable=True` |
| `backend/app/services/pairing_service.py` | routing_decision in list_pairings response | VERIFIED | Lines 477-479: routing_decision_json included if present |
| `backend/app/api/routes/pairing.py` | Routing info flows through execute endpoint | VERIFIED | Execute endpoint returns result dict directly from `create_limit_sell_for_pairing()` which includes `routing_decision` key |
| `backend/alembic/versions/ddedaa7263d8_...py` | Migration for new columns | VERIFIED | Migration exists, `alembic current` shows `ddedaa7263d8 (head)` — migration applied |
| `frontend/src/components/PairingExistingTab.jsx` | Routing result display | VERIFIED | Lines 84-94: routing-aware success message on execute; lines 314-321: routing-badge on EXECUTED pairing cards |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `order_service.py` | `domain/pairing.py` | `compute_dual_route_comparison` | WIRED | Imported line 25, called line 299 |
| `order_service.py` | `services/binance.py` | `get_current_price` for 3 symbols | WIRED | Lines 292-294: fetches XRPEUR, XRPBTC, BTCEUR prices |
| `lot_service.py` | `domain/lots.py` | `compute_cross_pair_realized_pnl_eur` | WIRED | Imported line 17, called line 574 |
| `pairing_service.py` | `db/models.py` | `routing_decision_json` column | WIRED | Lines 478-479 in list_pairings; column defined on PairingDB |
| `tests/test_sell_routing.py` | `domain/lots.py` | `import compute_cross_pair_realized_pnl_eur` | WIRED | Line 13: `from app.domain.lots import compute_cross_pair_realized_pnl_eur` |
| `tests/test_sell_routing.py` | `domain/models.py` | `import RoutingDecision` | WIRED | Line 14: `from app.domain.models import RoutingDecision, PairingItem` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ROUTE-01 | 04-01, 04-02 | At execution, compute EUR proceeds for both routes and select the higher one | SATISFIED | `compute_dual_route_comparison()` in order_service.py; `drc.recommended_route` selects the symbol |
| ROUTE-02 | 04-02 | Sell order automatically routed to pair with higher EUR proceeds | SATISFIED | `symbol = selected_symbol` overrides pairing.symbol before Binance API call; correct price precision applied via symbol_registry |
| ROUTE-03 | 04-01, 04-02 | Routing decision logged (chosen pair, prices, proceeds delta) | SATISFIED | `RoutingDecision` dataclass with 8 fields; persisted as `routing_decision_json` JSON on PairingDB; returned in API response and list |
| ROUTE-04 | 04-01, 04-02 | Cross-pair sell fills allocate against all XRP lots with EUR-normalized P&L | SATISFIED | `process_sell_fill_for_pairing()` detects cross-pair via `base_asset is not None`; calls `compute_cross_pair_realized_pnl_eur()` per allocation; persists to `realized_pnl_eur` column |

**Orphaned requirements from REQUIREMENTS.md mapped to Phase 4:** None — all 4 ROUTE-xx requirements are claimed and satisfied.

**Coverage:** 4/4 Phase 4 requirements verified.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No anti-patterns detected in modified files |

Scan covered: `domain/models.py`, `domain/lots.py`, `services/order_service.py`, `services/lot_service.py`, `services/pairing_service.py`, `frontend/src/components/PairingExistingTab.jsx`. No TODOs, FIXMEs, placeholders, stubs, or empty handlers found.

### Human Verification Required

#### 1. Live Cross-Pair Pairing Execute End-to-End

**Test:** With a real Binance testnet account holding XRP lots from both XRPEUR and XRPBTC pairs: create a cross-pair pairing, run simulation, execute. Observe the routing decision JSON on the returned response and PairingDB record.
**Expected:** Response includes `routing_decision` with `selected_route`, live prices for all 3 symbols, `direct_net_eur`, `indirect_net_eur`, `eur_difference`. The Binance order appears on the symbol matching `selected_route`.
**Why human:** Requires real Binance API keys with XRP holdings; the actual route selection depends on live market prices which cannot be deterministically tested without real API access.

#### 2. EUR-Normalized P&L on Post-Execution Sell Fill

**Test:** After a cross-pair pairing is executed and the order fills on Binance, trigger a reconciliation sync. Check the `sell_allocations` table: verify `realized_pnl_eur` is populated and is numerically correct (EUR proceeds minus EUR cost basis).
**Why human:** Requires a real fill event from Binance to trigger `process_sell_fill_for_pairing()` in the live code path; cannot simulate with unit tests.

### Gaps Summary

No gaps. All 4 observable truths are verified. All 8 artifacts (4 per plan) exist, are substantive, and are correctly wired. All 4 ROUTE requirements are satisfied with evidence in the codebase. The full test suite of 633 tests passes with no regressions. The frontend builds cleanly.

**One minor observation (not a gap):** The single-pairing GET endpoint (`GET /api/pairing/{user_id}/{pairing_id}`) does not include `routing_decision_json` in its response — it calls `_pairing_to_dict()` directly without the routing_decision augmentation that `list_pairings()` adds. However: the execute endpoint returns `routing_decision` directly, and the list endpoint includes it for display. The single-GET omission is a minor API completeness issue but does not affect ROUTE-03 satisfaction since routing decisions are logged via execute response and list endpoint. This is a v2 enhancement candidate (DISP-02), not a v1 gap.

---

_Verified: 2026-02-22T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
