---
phase: 01-sell-allocation-symbol-isolation
verified: 2026-02-20T16:00:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 1: Sell Allocation Symbol Isolation Verification Report

**Phase Goal:** Sell fills only close lots of the same base asset, preventing cross-asset contamination
**Verified:** 2026-02-20T16:00:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A BTC sell fill never allocates against an XRP lot (and vice versa) | VERIFIED | `test_fifo_only_receives_same_base_lots` and `test_strategy_lifo_only_receives_same_base_lots` pass; all 4 service-layer queries filter with `TradeLotDB.symbol.in_(base_symbols)` ensuring only same-base lots reach the domain layer |
| 2 | All 4 allocation paths (FIFO, LIFO, HIGHEST_COST, lot-specific) filter by base-asset before sorting | VERIFIED | `base_symbols = _get_base_symbols_for_sell_event(sell_event_db)` appears at lines 262, 359, 469, 637 of `lot_service.py`; `TradeLotDB.symbol.in_(base_symbols)` appears at lines 271, 382, 512, 645 (4 occurrences total, one per allocation function) |
| 3 | get_symbols_for_base_asset() returns all symbols for a given base asset | VERIFIED | Function exists at line 41 of `symbol_registry.py`; verified via Python import: XRP returns `['XRPEUR', 'XRPBTC']`, BTC returns `['BTCEUR']`, ETH returns `['ETHEUR']`; unknown base raises ValueError; 4 dedicated tests pass |
| 4 | Existing BTC/EUR-only sell allocation behavior is unchanged (backward compatible) | VERIFIED | `test_btceur_backward_compatibility` passes (FIFO across 2 BTCEUR lots); `test_legacy_event_without_symbol_defaults_btceur` passes (fallback path); full test suite: 579 passed, 0 failed |
| 5 | Overflow queries in lot-specific and pairing allocation also filter by base-asset | VERIFIED | lot-specific overflow query at line 376-387 includes `TradeLotDB.symbol.in_(base_symbols)`; pairing overflow query at line 506-516 includes `TradeLotDB.symbol.in_(base_symbols)`; `test_lot_specific_overflow_respects_base_asset` passes |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/symbol_registry.py` | `get_symbols_for_base_asset()` function | VERIFIED | Function at line 41-57, iterates KNOWN_PAIRS, raises ValueError for unknown base; 83 lines total |
| `backend/app/services/lot_service.py` | Base-asset filtered DB queries in all 4 allocation functions | VERIFIED | `_get_base_symbols_for_sell_event()` helper at lines 43-52; `base_symbols` computed and applied in `process_sell_fill_fifo` (L262/271), `process_sell_fill_lot_specific` (L359/382), `process_sell_fill_for_pairing` (L469/512), `process_sell_fill_with_strategy` (L637/645) |
| `backend/tests/test_sell_allocation_isolation.py` | Cross-asset isolation tests and backward compatibility tests | VERIFIED | 309 lines, 10 tests across 4 test classes: `TestGetSymbolsForBaseAsset` (4), `TestCrossAssetIsolation` (3), `TestBackwardCompatibility` (2), `TestOverflowIsolation` (1); all 10 pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `lot_service.py` | `symbol_registry.py` | `from app.symbol_registry import get_base_asset, get_symbols_for_base_asset` | WIRED | Import at line 37; used via `_get_base_symbols_for_sell_event()` helper at 4 call sites |
| `lot_service.py` | `db/models.py` | `TradeLotDB.symbol.in_(base_symbols)` filter in all 4 allocation queries | WIRED | 4 occurrences at lines 271, 382, 512, 645 -- one per allocation function |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ALLOC-01 | 01-01-PLAN | Sell-Fills allokieren nur gegen Lots desselben Base-Assets | SATISFIED | All 4 allocation DB queries filter by `TradeLotDB.symbol.in_(base_symbols)`; 3 cross-asset isolation tests pass |
| ALLOC-02 | 01-01-PLAN | Symbol Registry bietet `get_symbols_for_base_asset()` Hilfsfunktion | SATISFIED | Function exists in `symbol_registry.py` (line 41); returns correct results for XRP, BTC, ETH; raises ValueError for unknown base |
| ALLOC-03 | 01-01-PLAN | Alle 4 Sell-Allocation-Pfade filtern nach Base-Asset | SATISFIED | `process_sell_fill_fifo`, `process_sell_fill_lot_specific`, `process_sell_fill_for_pairing`, `process_sell_fill_with_strategy` all include `TradeLotDB.symbol.in_(base_symbols)` filter |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | -- | -- | -- | No anti-patterns found in any of the 3 modified/created files |

**Note:** Pre-existing linting issues in `lot_service.py` (F401 unused import `calculate_lot_target_price`, E402 import order, F821 string-quoted type hint for `BinanceService`) are NOT introduced by this phase -- they exist in lines that were not modified.

### Human Verification Required

None required. All truths are verifiable programmatically through tests and code inspection. The phase is purely backend logic (no UI, no external service integration, no visual behavior).

### Test Results

- **New tests:** 10/10 passed (`test_sell_allocation_isolation.py`)
- **Full suite:** 579/579 passed (zero regressions)
- **Commits verified:** `c784b6a` (fix) and `8c272f6` (test) both present in git history

### Gaps Summary

No gaps found. All 5 observable truths are verified, all 3 artifacts pass all three levels (exists, substantive, wired), all key links are confirmed, and all 3 requirements are satisfied. The phase goal -- preventing cross-asset contamination in sell allocation -- is achieved.

---

_Verified: 2026-02-20T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
