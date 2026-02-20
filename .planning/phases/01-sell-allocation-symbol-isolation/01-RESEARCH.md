# Phase 1: Sell Allocation Symbol Isolation - Research

**Researched:** 2026-02-20
**Domain:** Sell Allocation Logic (Domain + Service layer, Python/SQLAlchemy)
**Confidence:** HIGH

## Summary

Phase 1 addresses an existing correctness bug: the sell allocation system currently queries ALL open lots for a user without filtering by base asset. In a multi-symbol environment (BTCEUR, ETHEUR, XRPEUR, XRPBTC), a BTC sell fill could erroneously close an XRP lot. This is a prerequisite for all subsequent cross-pair work.

The fix is localized to 4 service-layer functions in `lot_service.py` that query `TradeLotDB` rows with `qty_base_open > 0`. Each must add a base-asset filter. The domain layer (`lots.py`) is already correct -- it operates on whatever lots list it receives. A new `get_symbols_for_base_asset()` helper is needed in `symbol_registry.py`.

**Primary recommendation:** Add base-asset filtering at the service layer (DB query level) in all 4 allocation paths, plus add `get_symbols_for_base_asset()` to the symbol registry. No schema migration required. No domain layer changes needed.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ALLOC-01 | Sell-Fills allokieren nur gegen Lots desselben Base-Assets (XRP-Sells gegen XRP-Lots, BTC-Sells gegen BTC-Lots) | All 4 allocation paths in `lot_service.py` need base-asset filtering on their DB queries. The sell event's symbol determines the base-asset via `get_base_asset()`. Lots are filtered using `TradeLotDB.symbol.in_(symbols_for_base)`. See "Architecture Patterns" section for exact code patterns. |
| ALLOC-02 | Symbol Registry bietet `get_symbols_for_base_asset()` Hilfsfunktion fuer Base-Asset-Gruppierung | New function in `symbol_registry.py` that iterates `KNOWN_PAIRS` and returns all symbols sharing a base-asset. E.g., `get_symbols_for_base_asset("XRP")` returns `["XRPEUR", "XRPBTC"]`. See "Code Examples" section. |
| ALLOC-03 | Alle 4 Sell-Allocation-Pfade (FIFO, LIFO, HIGHEST_COST, lot-specific) filtern nach Base-Asset | The 4 paths are: `process_sell_fill_fifo()`, `process_sell_fill_with_strategy()`, `process_sell_fill_lot_specific()`, `process_sell_fill_for_pairing()`. Each has 1-2 DB queries needing the filter. See "Bug Locations" section for exact lines. |
</phase_requirements>

## Standard Stack

### Core (already in project -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy 2 | pinned in requirements.txt | ORM queries with `.filter()` and `.in_()` | Already used everywhere in lot_service.py |
| pytest | pinned in requirements.txt | Test framework | Already used for 18 test files |

### Supporting
No new libraries needed. This phase is pure refactoring of existing query logic.

### Alternatives Considered
None. The fix is straightforward query filtering -- no library decision needed.

## Architecture Patterns

### Recommended Project Structure

No new files needed. Changes are in existing files:

```
backend/app/
  symbol_registry.py         # ADD: get_symbols_for_base_asset()
  services/lot_service.py    # MODIFY: 4 allocation functions (add base-asset filter)
backend/tests/
  test_sell_allocation_isolation.py  # NEW: cross-asset isolation tests
```

### Pattern 1: Base-Asset Filter at Query Level (Service Layer)

**What:** Extract base-asset from the sell event's symbol, get all symbols for that base-asset, filter lot queries with `.in_()`.

**When to use:** Every DB query in lot_service.py that fetches open lots for sell allocation.

**Example:**
```python
# In lot_service.py — pattern for all 4 allocation functions
from app.symbol_registry import get_base_asset, get_symbols_for_base_asset

def process_sell_fill_fifo(db, user_id, sell_event_id, fee_conversion_rates=None):
    sell_event_db = db.query(LedgerEventDB).filter(...).first()
    sell_event_domain = _db_event_to_domain(sell_event_db)

    # NEW: Derive base-asset symbols for filtering
    sell_symbol = sell_event_db.symbol or "BTCEUR"
    base_asset = get_base_asset(sell_symbol)
    base_symbols = get_symbols_for_base_asset(base_asset)

    lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_base_open > 0,
            TradeLotDB.symbol.in_(base_symbols),  # NEW: base-asset filter
        )
        .order_by(TradeLotDB.created_at.asc())
        .with_for_update()
        .all()
    )
    # ... rest unchanged
```

### Pattern 2: Symbol Registry Helper (Pure, No I/O)

**What:** New function that returns all symbols sharing a base-asset.

**Example:**
```python
# In symbol_registry.py
def get_symbols_for_base_asset(base_asset: str) -> list[str]:
    """Returns all known symbols for a given base asset.

    Example: get_symbols_for_base_asset("XRP") -> ["XRPEUR", "XRPBTC"]
    Example: get_symbols_for_base_asset("BTC") -> ["BTCEUR"]
    """
    return [
        pair.symbol
        for pair in KNOWN_PAIRS.values()
        if pair.base_asset == base_asset
    ]
```

### Anti-Patterns to Avoid

- **Filtering in domain layer instead of service layer:** The domain functions (`allocate_sell_fifo`, etc.) receive pre-filtered lot lists. Adding symbol filtering there would violate the principle that domain is pure and receives pre-prepared data. The service layer should filter.
- **Filtering by exact symbol instead of base-asset:** A sell on XRPEUR should close XRPEUR lots AND XRPBTC lots (they're all XRP positions). Filter by base-asset, not by exact symbol. This is the core of cross-pair support.
- **Forgetting the overflow queries:** `process_sell_fill_lot_specific` and `process_sell_fill_for_pairing` each have TWO queries -- the primary lots AND the overflow lots. Both must be filtered.

## Bug Locations (Exact Code to Change)

### 1. `process_sell_fill_fifo()` (line ~253-258)

**Current:** Queries ALL open lots without symbol filter.
```python
lots_db = (
    db.query(TradeLotDB)
    .filter(TradeLotDB.user_id == user_id, TradeLotDB.qty_base_open > 0)
    .order_by(TradeLotDB.created_at.asc())
    .with_for_update()
    .all()
)
```
**Fix:** Add `.filter(TradeLotDB.symbol.in_(base_symbols))`

### 2. `process_sell_fill_with_strategy()` (line ~617-622)

**Current:** Same -- queries ALL open lots.
```python
lots_db = (
    db.query(TradeLotDB)
    .filter(TradeLotDB.user_id == user_id, TradeLotDB.qty_base_open > 0)
    .with_for_update()
    .all()
)
```
**Fix:** Add `.filter(TradeLotDB.symbol.in_(base_symbols))`

### 3. `process_sell_fill_lot_specific()` (line ~357-367)

**Current:** Overflow query fetches ALL open lots except target.
```python
remaining_lots_db = (
    db.query(TradeLotDB)
    .filter(
        TradeLotDB.user_id == user_id,
        TradeLotDB.qty_base_open > 0,
        TradeLotDB.id != target_lot_id,
    )
    .order_by(TradeLotDB.created_at.asc())
    .with_for_update()
    .all()
)
```
**Fix:** Add `.filter(TradeLotDB.symbol.in_(base_symbols))` to overflow query. Target lot query (line ~345-351) does not need filtering because it's fetched by ID directly.

### 4. `process_sell_fill_for_pairing()` (line ~485-495)

**Current:** Overflow query fetches ALL open lots except pairing lots.
```python
remaining_lots_db = (
    db.query(TradeLotDB)
    .filter(
        TradeLotDB.user_id == user_id,
        TradeLotDB.qty_base_open > 0,
        ~TradeLotDB.id.in_(pairing_lot_ids),
    )
    .with_for_update()
    .all()
)
```
**Fix:** Add `.filter(TradeLotDB.symbol.in_(base_symbols))` to overflow query. Pairing lots query (line ~467-476) filters by specific lot IDs from the pairing, so it's already scoped correctly.

### 5. `process_sell_fill()` routing function (line ~669-761)

**No change needed.** This function routes to one of the 4 functions above. It does not query lots directly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Base-asset extraction from symbol | String parsing (`symbol[:3]`) | `get_base_asset(symbol)` from symbol_registry | Registry handles all edge cases (3-char vs 4-char assets). Already in codebase. |
| Symbol-to-base mapping | Hardcoded dict in lot_service | `get_symbols_for_base_asset()` in symbol_registry | Single source of truth. When new pairs are added, only registry changes. |

**Key insight:** The symbol registry (`KNOWN_PAIRS`) already has the base-asset mapping. Adding a reverse-lookup function is 4 lines of code. Do not duplicate this logic.

## Common Pitfalls

### Pitfall 1: Forgetting Overflow Queries
**What goes wrong:** The primary lot query gets the base-asset filter, but the overflow query in `process_sell_fill_lot_specific` or `process_sell_fill_for_pairing` is missed.
**Why it happens:** These functions have 2 separate DB queries. Easy to fix one and miss the other.
**How to avoid:** Enumerate all 6 queries (1 each in fifo/strategy, 2 each in lot-specific/pairing). Verify each has the filter.
**Warning signs:** Test where lot-specific sell overflows to wrong-base lots.

### Pitfall 2: Breaking Backward Compatibility for BTC-Only Users
**What goes wrong:** Existing BTC/EUR users experience behavior changes.
**Why it happens:** `get_symbols_for_base_asset("BTC")` returns `["BTCEUR"]` -- only one symbol. The filter is effectively a no-op for BTC-only scenarios.
**How to avoid:** Write explicit backward-compatibility tests: a BTC sell with only BTCEUR lots should behave identically to current code.
**Warning signs:** Existing FIFO/LIFO/HIGHEST_COST tests start failing.

### Pitfall 3: Forgetting the `symbol or "BTCEUR"` Default
**What goes wrong:** A sell event with `symbol=None` (legacy data) causes `get_base_asset(None)` to fail.
**Why it happens:** Legacy events may not have `symbol` set.
**How to avoid:** Use the existing pattern `sell_event_db.symbol or "BTCEUR"` before calling `get_base_asset()`. This is already done in the existing code for sell event domain conversion.
**Warning signs:** `ValueError: Unknown symbol: None` in production.

### Pitfall 4: Testing Only Domain Layer
**What goes wrong:** Domain-layer tests pass (lots.py already works correctly with filtered lists) but service-layer queries still fetch wrong lots.
**Why it happens:** Domain functions receive pre-filtered lists. The bug is in the DB queries, not the allocation logic.
**How to avoid:** Write integration-style tests that exercise `process_sell_fill_*()` with real DB state containing multiple base-assets.
**Warning signs:** Unit tests green, manual testing shows cross-asset contamination.

### Pitfall 5: Cross-Pair Pairing Lots Still Scoped to Same Base
**What goes wrong:** Pairing lots from XRPEUR and XRPBTC are in the same pairing. The pairing-specific allocation must still correctly scope overflow to XRP lots only.
**Why it happens:** Pairing lots are fetched by ID (already correct), but overflow lots are fetched for the user globally.
**How to avoid:** The base-asset filter on the overflow query in `process_sell_fill_for_pairing` handles this. The filter uses the sell event's symbol, which matches the base-asset of all pairing lots.
**Warning signs:** Overflow from a pairing sell hitting BTC lots when it should hit XRP lots.

## Code Examples

### Example 1: `get_symbols_for_base_asset()` Implementation

```python
# In backend/app/symbol_registry.py

def get_symbols_for_base_asset(base_asset: str) -> list[str]:
    """Returns all known symbols for a given base asset.

    Examples:
        get_symbols_for_base_asset("XRP") -> ["XRPEUR", "XRPBTC"]
        get_symbols_for_base_asset("BTC") -> ["BTCEUR"]
        get_symbols_for_base_asset("ETH") -> ["ETHEUR"]

    Raises:
        ValueError: If no symbols found for the base asset.
    """
    symbols = [
        pair.symbol
        for pair in KNOWN_PAIRS.values()
        if pair.base_asset == base_asset
    ]
    if not symbols:
        raise ValueError(f"No symbols found for base asset: {base_asset}")
    return symbols
```

### Example 2: Typical Service-Layer Fix Pattern

```python
# Before (BUG -- no symbol filter):
lots_db = (
    db.query(TradeLotDB)
    .filter(TradeLotDB.user_id == user_id, TradeLotDB.qty_base_open > 0)
    .with_for_update()
    .all()
)

# After (FIXED -- base-asset filter):
sell_symbol = sell_event_db.symbol or "BTCEUR"
base_symbols = get_symbols_for_base_asset(get_base_asset(sell_symbol))

lots_db = (
    db.query(TradeLotDB)
    .filter(
        TradeLotDB.user_id == user_id,
        TradeLotDB.qty_base_open > 0,
        TradeLotDB.symbol.in_(base_symbols),
    )
    .with_for_update()
    .all()
)
```

### Example 3: Cross-Asset Isolation Test

```python
# In tests/test_sell_allocation_isolation.py

def test_btc_sell_does_not_close_xrp_lot(db_session):
    """BTC/EUR sell must NOT allocate against XRP lots."""
    # Setup: 1 BTC lot + 1 XRP lot
    btc_lot = TradeLotDB(
        id="lot_btc_1", user_id="user1", symbol="BTCEUR",
        qty_base_initial=Decimal("0.01"), qty_base_open=Decimal("0.01"),
        cost_quote=Decimal("500"), status=LotStatusEnum.OPEN, ...
    )
    xrp_lot = TradeLotDB(
        id="lot_xrp_1", user_id="user1", symbol="XRPEUR",
        qty_base_initial=Decimal("1000"), qty_base_open=Decimal("1000"),
        cost_quote=Decimal("550"), status=LotStatusEnum.OPEN, ...
    )
    db_session.add_all([btc_lot, xrp_lot])

    # Create BTC sell event
    btc_sell = LedgerEventDB(
        id="sell_1", user_id="user1", symbol="BTCEUR",
        type=EventTypeEnum.TRADE_FILL, side=TradeSideEnum.SELL,
        amount=Decimal("0.01"), price=Decimal("55000"), ...
    )
    db_session.add(btc_sell)
    db_session.flush()

    # Execute
    result = process_sell_fill_fifo(db_session, "user1", "sell_1")

    # Assert: only BTC lot was closed
    assert len(result["allocations"]) == 1
    assert result["allocations"][0]["trade_lot_id"] == "lot_btc_1"

    # XRP lot must be untouched
    xrp_refreshed = db_session.query(TradeLotDB).get("lot_xrp_1")
    assert xrp_refreshed.qty_base_open == Decimal("1000")
    assert xrp_refreshed.status == LotStatusEnum.OPEN
```

### Example 4: Backward Compatibility Test

```python
def test_btceur_only_user_unchanged(db_session):
    """For BTC-only users, behavior must be identical to pre-fix."""
    # Setup: 2 BTC lots only (no XRP)
    lot1 = TradeLotDB(id="lot1", symbol="BTCEUR", qty_base_open=Decimal("0.01"), ...)
    lot2 = TradeLotDB(id="lot2", symbol="BTCEUR", qty_base_open=Decimal("0.01"), ...)
    db_session.add_all([lot1, lot2])

    # BTC sell -- should allocate against BTC lots as before
    sell = LedgerEventDB(id="sell1", symbol="BTCEUR", amount=Decimal("0.015"), ...)
    db_session.add(sell)
    db_session.flush()

    result = process_sell_fill_fifo(db_session, "user1", "sell1")
    assert len(result["allocations"]) == 2  # FIFO across both lots
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-symbol system (BTCEUR only) | Multi-symbol with symbol filter on portfolio queries | Recent (P3 commit `0c5c0c8`) | Portfolio already filtered; sell allocation was missed |

**Note:** The portfolio service (`get_portfolio_state`) already filters lots by symbol (line 64-68: `TradeLotDB.symbol == symbol`). The domain layer (`compute_portfolio_from_ledger`) already filters events by symbol (line 57: `if event.symbol and event.symbol != symbol`). The sell allocation paths are the gap.

## Scope Boundaries

### Changes in Scope
1. `symbol_registry.py`: Add `get_symbols_for_base_asset()` function
2. `lot_service.py`: Add base-asset filter to 6 DB queries across 4 functions
3. New test file: `test_sell_allocation_isolation.py`
4. Verify existing tests still pass

### Changes OUT of Scope
- No schema migration (TradeLotDB.symbol already exists)
- No domain layer changes (lots.py already works with filtered lists)
- No frontend changes
- No API route changes
- No Alembic migration
- No changes to `sync_service.py`, `csv_import_service.py`, or `websocket_fill_handler.py` (they call `process_sell_fill()` which routes to the fixed functions)
- No changes to `portfolio_service.py` (already filtered by symbol)
- No changes to `repair_allocations.py` script (calls `process_sell_fill()` which will route correctly)

### Callers of Sell Allocation (Upstream Audit)

All callers go through `process_sell_fill()` which routes to one of the 4 fixed functions:

| Caller | File | How it calls | Impact |
|--------|------|-------------|--------|
| SyncService.sync_fills | sync_service.py:167 | `process_sell_fill(db, user_id, event_db.id, fill_rates)` | Auto-fixed (routes through `process_sell_fill`) |
| CSV import | csv_import_service.py:260 | `process_sell_fill(db, user_id, event_db.id)` | Auto-fixed |
| WebSocket handler | websocket_fill_handler.py:147 | `process_sell_fill(db, user_id, event_id, fee_conversion_rates)` | Auto-fixed |
| Repair script | repair_allocations.py:119 | `process_sell_fill(db, user_id, event.id)` | Auto-fixed |

No caller bypasses `process_sell_fill()` to call the 4 sub-functions directly. This means fixing the 4 sub-functions is sufficient.

## Open Questions

1. **Should `get_symbols_for_base_asset()` raise on unknown base-asset?**
   - What we know: Current `get_base_asset()` raises `ValueError` for unknown symbols. Consistency suggests raising here too.
   - What's unclear: Whether empty list or exception is safer for the caller.
   - Recommendation: Raise `ValueError`. An unknown base-asset in a sell event is a programming error, not a recoverable condition. Callers already use `get_base_asset()` which validates the symbol first.

2. **Should we add an index for the `.in_()` query?**
   - What we know: `TradeLotDB` already has `Index("idx_lots_user_symbol_status", "user_id", "symbol", "status")`. The `.in_()` filter on `symbol` should use this index efficiently.
   - What's unclear: Whether SQLite optimizes `.in_()` with an existing composite index.
   - Recommendation: No new index needed. The existing composite index covers `(user_id, symbol, status)`. Lot counts per user are typically < 1000, so performance is not a concern.

## Sources

### Primary (HIGH confidence)
- Direct code reading: `backend/app/services/lot_service.py` -- all 4 allocation functions and their DB queries
- Direct code reading: `backend/app/symbol_registry.py` -- existing `KNOWN_PAIRS`, `get_base_asset()`, no `get_symbols_for_base_asset()` yet
- Direct code reading: `backend/app/domain/lots.py` -- domain functions receive pre-filtered lists, no symbol filtering needed there
- Direct code reading: `backend/app/db/models.py` -- `TradeLotDB.symbol` column already exists with index

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` -- confirmed Phase 1 scope and data flow
- `.planning/research/PITFALLS.md` -- P-2 (cross-contamination) identified as existing bug
- `.planning/research/FEATURES.md` -- TS-1 confirmed as LOW complexity (~30 lines, 4 queries)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, pure SQLAlchemy query changes
- Architecture: HIGH -- direct code reading of all affected files, complete call-chain audit
- Pitfalls: HIGH -- identified all 6 queries, all 4 callers, verified no bypass paths

**Research date:** 2026-02-20
**Valid until:** 2026-04-20 (stable -- no external dependencies, pure codebase analysis)
