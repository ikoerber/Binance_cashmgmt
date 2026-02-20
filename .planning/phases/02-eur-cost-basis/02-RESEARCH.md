# Phase 2: EUR Cost Basis - Research

**Researched:** 2026-02-20
**Domain:** Historical exchange rate conversion, Alembic migration, TradeLot schema extension (Python/SQLAlchemy/Binance Klines API)
**Confidence:** HIGH

## Summary

Phase 2 adds a deterministic EUR cost basis to every TradeLot. For EUR-quoted lots (BTCEUR, ETHEUR, XRPEUR), `cost_eur = cost_quote` and `quote_to_eur_rate = 1.0` (trivial). For BTC-quoted lots (XRPBTC), the BTC/EUR exchange rate at fill time is fetched via the existing `get_historical_price()` mechanism (Binance Klines API, 1-minute interval) and persisted. Once stored, the rate is immutable -- the same lot always shows the same EUR cost, regardless of current BTC/EUR price.

The implementation reuses the exact same pattern already proven for BNB fee conversion: the sync service fetches the historical rate per fill, the service layer persists it, and the domain layer computes derived values (break_even_eur) from the persisted fields. Two new columns are added to `trade_lots` via Alembic migration with a backfill step. No new services or libraries are needed.

The Alembic migration must be quote-asset-aware: EUR-quoted lots get `cost_eur = cost_quote` and `rate = 1.0`. BTC-quoted lots either get a historical rate from a backfill script or a `needs_backfill` flag. Since this is a new project with potentially no existing XRPBTC lots, the migration can safely default BTC-quoted lots to `cost_eur = NULL` and `quote_to_eur_rate = NULL`, with a separate backfill script for existing data.

**Primary recommendation:** Add `cost_eur` and `quote_to_eur_rate` columns to TradeLotDB, extend lot creation to fetch BTC/EUR rate for non-EUR-quoted fills, add Alembic migration with quote-asset-aware backfill, expose `break_even_eur` and `cost_eur` in lot API responses.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COST-01 | Bei XRP/BTC Lot-Erstellung wird der BTC/EUR-Kurs zum Fill-Zeitpunkt via Klines API abgerufen | Reuse existing `get_historical_price("BTCEUR", fill.timestamp)` in sync_service during lot creation. Same minute-cache pattern as BNB fees. See "Architecture Patterns - Pattern 1". |
| COST-02 | `cost_eur` (EUR-Equivalent der Kosten) und `quote_to_eur_rate` (Konvertierungsrate) werden auf TradeLot persistiert | Two new Numeric columns on `TradeLotDB`. Domain `TradeLot` dataclass gets matching fields. Service layer computes and persists during `create_lot_from_buy_fill()`. See "Architecture Patterns - Pattern 2". |
| COST-03 | Fuer EUR-quoted Lots gilt `cost_eur = cost_quote` und `quote_to_eur_rate = 1.0` | Trivial branch in lot creation: check `get_quote_asset(symbol) == "EUR"` -- if true, skip API call, set rate=1.0 and cost_eur=cost_quote. See "Code Examples - Example 2". |
| COST-04 | Alembic-Migration fuegt neue Spalten hinzu und backfillt bestehende Lots korrekt (EUR-quoted: rate=1.0, BTC-quoted: historische Rate oder Flag) | Migration adds nullable columns, then runs SQL UPDATE to backfill EUR-quoted lots. BTC-quoted lots get a separate backfill script (same pattern as `backfill_fee_eur_value.py`). See "Architecture Patterns - Pattern 3". |
| COST-05 | Break-even in EUR (`break_even_eur`) berechenbar aus `cost_eur / qty_base_initial` | New computed property on domain `TradeLot` dataclass. Exposed in lot API response dict. See "Code Examples - Example 3". |
</phase_requirements>

## Standard Stack

### Core (already in project -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy 2 | pinned in requirements.txt | ORM columns + migration | Already used everywhere |
| Alembic | pinned in requirements.txt | Schema migration with `render_as_batch=True` (SQLite) | All prior migrations use this |
| python-binance / BinancePublicClient | pinned in requirements.txt | Historical Klines API for BTC/EUR rate | Already used for BNB fee conversion |
| pytest | pinned in requirements.txt | Unit + integration tests | 18 existing test files |

### Supporting
No new libraries needed. This phase extends existing infrastructure.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Klines API (1-min close) | Ticker API (real-time) | Ticker gives current price, not historical. Would make cost basis non-deterministic. Klines is correct. |
| In-migration backfill (SQL) | Separate backfill script | In-migration backfill works for EUR-quoted lots (pure SQL). BTC-quoted lots need API calls, so a separate script is correct (same pattern as `backfill_fee_eur_value.py`). |
| Storing `cost_eur` as computed view | Persisting on the lot | View would recompute on every query. Persisted value is immutable and fast. Determinism requires persistence. |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure

No new files needed except test file and backfill script. Changes in existing files:

```
backend/app/
  db/models.py                    # MODIFY: add cost_eur, quote_to_eur_rate to TradeLotDB
  domain/models.py                # MODIFY: add cost_eur, quote_to_eur_rate, break_even_eur to TradeLot
  domain/lots.py                  # MODIFY: set cost_eur + rate in create_trade_lot_from_buy_fill
  services/lot_service.py         # MODIFY: pass quote_to_eur_rate during lot creation, expose in _lot_db_to_dict
  services/sync_service.py        # MODIFY: fetch BTC/EUR rate for non-EUR-quoted fills
backend/alembic/versions/
  XXXX_add_eur_cost_basis.py      # NEW: migration with backfill
backend/scripts/
  backfill_cost_eur.py            # NEW: backfill for existing BTC-quoted lots (optional, if any exist)
backend/tests/
  test_eur_cost_basis.py          # NEW: test suite for EUR cost basis
```

### Pattern 1: Historical Rate Fetching During Sync (Reuses BNB Fee Pattern)

**What:** During `sync_fills()`, after fetching fills from Binance, determine which fills need a BTC/EUR rate conversion. Fetch historical rate and pass it through the lot creation chain.

**When to use:** For every non-EUR-quoted buy fill during sync.

**Existing pattern (BNB fees) in `sync_service.py`:**
```python
# Current: _get_per_fill_fee_conversion_rates() fetches BNBEUR rate for BNB fees
# New: extend to also fetch BTCEUR rate for BTC-quoted fills

def _get_quote_to_eur_rate(self, fill: LedgerEvent) -> Decimal | None:
    """Get quote-to-EUR conversion rate for a fill.

    Returns:
        Decimal rate if quote != EUR, or None if quote == EUR (rate is 1.0)
    """
    symbol = fill.symbol or "BTCEUR"
    quote_asset = get_quote_asset(symbol)

    if quote_asset == "EUR":
        return None  # No conversion needed, caller sets 1.0

    rate_pair = f"{quote_asset}EUR"  # e.g., "BTCEUR"
    return self.binance_service.get_historical_price(rate_pair, fill.timestamp)
```

**Key design decisions:**
- **Minute-caching:** Same pattern as BNB fees. Multiple XRPBTC fills in the same minute share one API call. The existing `_get_per_fill_fee_conversion_rates` already implements minute-caching. A new method (or extension) should use the same approach.
- **Fallback chain:** Historical rate -> current rate -> None (with warning). Same as BNB fee fallback.
- **Separate from fee rates:** The quote-to-EUR rate is conceptually different from fee conversion rates. Keep them in separate data flows to avoid confusion.

### Pattern 2: Lot Creation With EUR Cost Basis

**What:** `create_trade_lot_from_buy_fill()` (domain) computes cost_eur from cost_quote and the provided rate. The service layer passes the rate.

**Domain layer (lots.py):**
```python
def create_trade_lot_from_buy_fill(
    fill_event: LedgerEvent,
    fee_conversion_rates: dict[str, Decimal] | None = None,
    quote_to_eur_rate: Decimal | None = None,  # NEW parameter
) -> TradeLot:
    # ... existing cost_quote calculation ...

    # NEW: EUR cost basis
    quote_asset = get_quote_asset(symbol)
    if quote_asset == "EUR":
        effective_rate = Decimal("1")
        cost_eur = cost_quote
    elif quote_to_eur_rate is not None:
        effective_rate = quote_to_eur_rate
        cost_eur = cost_quote * quote_to_eur_rate
    else:
        effective_rate = None
        cost_eur = None  # Backfill needed

    lot = TradeLot(
        # ... existing fields ...
        cost_eur=cost_eur,
        quote_to_eur_rate=effective_rate,
    )
    return lot
```

**Service layer (lot_service.py):**
```python
def create_lot_from_buy_fill(
    db, user_id, fill_event_id,
    fee_conversion_rates=None,
    quote_to_eur_rate=None,  # NEW parameter
):
    # ... existing code ...
    lot_domain = create_trade_lot_from_buy_fill(
        event_domain, fee_conversion_rates, quote_to_eur_rate
    )
    # Persist including new fields
    lot_db = TradeLotDB(
        # ... existing fields ...
        cost_eur=lot_domain.cost_eur,
        quote_to_eur_rate=lot_domain.quote_to_eur_rate,
    )
```

### Pattern 3: Alembic Migration With Quote-Asset-Aware Backfill

**What:** Add two nullable columns, then backfill EUR-quoted lots via SQL UPDATE. BTC-quoted lots left as NULL for script backfill.

**Migration pattern (SQLite-compatible with `batch_alter_table`):**
```python
def upgrade():
    # 1. Add columns (nullable for backfill)
    with op.batch_alter_table("trade_lots") as batch_op:
        batch_op.add_column(sa.Column(
            "cost_eur",
            sa.Numeric(precision=20, scale=10),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            "quote_to_eur_rate",
            sa.Numeric(precision=20, scale=10),
            nullable=True,
        ))

    # 2. Backfill EUR-quoted lots (BTCEUR, ETHEUR, XRPEUR)
    # For these, cost_eur = cost_quote and rate = 1.0
    op.execute(
        sa.text("""
            UPDATE trade_lots
            SET cost_eur = cost_quote,
                quote_to_eur_rate = 1.0
            WHERE symbol IN ('BTCEUR', 'ETHEUR', 'XRPEUR')
        """)
    )
    # BTC-quoted lots (XRPBTC) left as NULL -- backfill script handles them
```

**Why nullable columns, not NOT NULL with default:**
- BTC-quoted lots need historical API data that cannot be computed in a migration
- Setting a wrong default (like 0 or cost_quote) would violate the determinism invariant
- NULL clearly signals "needs backfill" vs. "backfilled with wrong value"
- After backfill, a follow-up migration can add NOT NULL constraint if desired

### Pattern 4: Backfill Script (Same as `backfill_fee_eur_value.py`)

**What:** Standalone script that finds BTC-quoted lots with `cost_eur IS NULL`, fetches historical BTC/EUR rate, and updates.

**Key elements (from existing pattern):**
- `--commit` flag (dry-run default)
- Minute-caching for API calls
- Rate limiting (0.1s between unique API calls)
- Progress logging
- Handles API failures gracefully (skip with warning)

### Anti-Patterns to Avoid

- **Computing cost_eur at query time instead of persisting:** Would make the system non-deterministic (BTC/EUR rate changes). Violates the core invariant "same lot always shows same EUR cost."
- **Using current BTC/EUR rate for historical fills:** Same non-determinism problem. Must use Klines API at fill timestamp.
- **Putting API calls in domain layer:** Domain layer must stay pure (no I/O). The rate fetch happens in the service/sync layer, and the domain layer receives the rate as a parameter.
- **Making cost_eur NOT NULL in migration without backfill:** Would fail for existing lots. Use nullable, backfill, then optionally tighten.
- **Storing only cost_eur without quote_to_eur_rate:** Loses auditability. The rate must be stored so cost_eur can be verified: `cost_eur = cost_quote * quote_to_eur_rate`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Historical BTC/EUR price | New API client / external data source | `BinanceService.get_historical_price("BTCEUR", timestamp)` | Already implemented, tested (3 tests), uses public Klines API. |
| Minute-level caching for API calls | Custom cache | Same `minute_cache` dict pattern as `_get_per_fill_fee_conversion_rates()` | Proven pattern, saves API calls for fills in same minute. |
| Backfill script | In-migration API calls | Separate script (like `backfill_fee_eur_value.py`) | Migrations should be deterministic SQL. API calls belong in scripts. |
| Quote-asset determination | String parsing | `get_quote_asset(symbol)` from `symbol_registry` | Already handles all 4 pairs correctly. |

**Key insight:** The entire pattern for "fetch historical price, persist on record, use in downstream calculations" already exists for BNB fee conversion. Phase 2 replicates this pattern for quote-to-EUR conversion. No new infrastructure is needed.

## Common Pitfalls

### Pitfall 1: Setting cost_eur = cost_quote for BTC-quoted lots
**What goes wrong:** Migration or lot creation sets `cost_eur = cost_quote` without checking the quote asset. For XRPBTC lots, `cost_quote` is in BTC (e.g., 0.05 BTC), which would be stored as `cost_eur = 0.05` -- obviously wrong in EUR terms.
**Why it happens:** Copy-paste from EUR-quoted logic without conditional branch.
**How to avoid:** Always check `get_quote_asset(symbol) == "EUR"` before setting `cost_eur = cost_quote`. For BTC-quoted lots, always multiply by the historical rate.
**Warning signs:** Lots with impossibly low `cost_eur` values (BTC values treated as EUR).

### Pitfall 2: Forgetting the fallback chain for API failures
**What goes wrong:** `get_historical_price()` fails (network issue, no data for timestamp), lot creation crashes, sync fails.
**Why it happens:** BTC/EUR historical data may not be available for very old timestamps or during API outages.
**How to avoid:** Same fallback as BNB fees: try historical -> try current -> set to None with warning. Lot is still created with `cost_eur = NULL`, backfill later.
**Warning signs:** Sync failures when Klines API is unavailable.

### Pitfall 3: Breaking existing lot creation for EUR-quoted fills
**What goes wrong:** Adding the `quote_to_eur_rate` parameter changes the function signature, breaking callers that don't pass it.
**Why it happens:** Multiple callers of `create_lot_from_buy_fill` (sync, CSV import, WebSocket handler).
**How to avoid:** Make `quote_to_eur_rate` optional with `None` default. When `None` and quote is EUR, auto-compute as 1.0. When `None` and quote is not EUR, leave cost_eur as None (needs backfill). This makes the change backward-compatible.
**Warning signs:** Existing tests for BTC/EUR lot creation fail.

### Pitfall 4: Not exposing cost_eur in the API response
**What goes wrong:** Columns are added to DB but frontend cannot see them because `_lot_db_to_dict` does not include them.
**Why it happens:** Adding DB columns without updating the serialization layer.
**How to avoid:** Update `_lot_db_to_dict()` in `lot_service.py` to include `cost_eur`, `quote_to_eur_rate`, and `break_even_eur` in the response dict.
**Warning signs:** Frontend shows no EUR cost for BTC-quoted lots.

### Pitfall 5: Migration fails on SQLite without batch mode
**What goes wrong:** `ALTER TABLE` with column rename or constraint change fails on SQLite.
**Why it happens:** SQLite has limited ALTER TABLE support.
**How to avoid:** Alembic `env.py` already sets `render_as_batch=True`. Use `batch_alter_table` for all column additions. The project has a proven migration pattern (13 existing migrations all use batch mode).
**Warning signs:** `alembic upgrade head` fails with SQLite error.

### Pitfall 6: Minute-cache key collision between fee rates and quote rates
**What goes wrong:** If the same minute-cache dict is used for both BNB fee rates and BTC/EUR quote rates, a BNB fill at the same minute as an XRPBTC fill could get the wrong rate.
**Why it happens:** Both use `(asset, minute_key)` as cache key, and "BTC" in the fee context (BNBBTC pair? unlikely but possible) could conflict with "BTC" in the quote context (BTCEUR pair).
**How to avoid:** Keep fee conversion rates and quote-to-EUR rates in separate data flows. The sync service already separates these: `_get_per_fill_fee_conversion_rates()` handles fees. A new method handles quote-to-EUR rates.
**Warning signs:** Wrong EUR cost on lots that happen to have BNB fees in the same minute.

## Code Examples

Verified patterns from existing codebase:

### Example 1: Domain TradeLot Extension

```python
# In backend/app/domain/models.py

@dataclass
class TradeLot:
    id: str
    created_from_fill_id: str
    created_at: datetime
    qty_base_initial: Decimal
    qty_base_open: Decimal
    cost_quote: Decimal  # Cost in quote currency (existing)
    status: LotStatus = LotStatus.OPEN
    target_margin_pct: Optional[Decimal] = None
    symbol: str = "BTCEUR"

    # NEW: EUR cost basis
    cost_eur: Optional[Decimal] = None  # EUR-equivalent cost (None = needs backfill)
    quote_to_eur_rate: Optional[Decimal] = None  # Conversion rate at fill time (None = needs backfill)

    @property
    def break_even(self) -> Decimal:
        """Break-even in quote currency (existing)."""
        if self.qty_base_initial == 0:
            return Decimal("0")
        return self.cost_quote / self.qty_base_initial

    @property
    def break_even_eur(self) -> Optional[Decimal]:
        """Break-even in EUR (NEW). None if cost_eur not available."""
        if self.cost_eur is None or self.qty_base_initial == 0:
            return None
        return self.cost_eur / self.qty_base_initial
```

### Example 2: EUR Cost Computation in Lot Creation

```python
# In backend/app/domain/lots.py -- inside create_trade_lot_from_buy_fill()

    # After existing cost_quote calculation...
    symbol = fill_event.symbol or "BTCEUR"
    quote_asset = get_quote_asset(symbol)

    # Compute EUR cost basis
    if quote_asset == "EUR":
        # EUR-quoted: trivial, no conversion needed
        effective_rate = Decimal("1")
        computed_cost_eur = cost_quote  # cost_quote IS in EUR
    elif quote_to_eur_rate is not None:
        # Non-EUR-quoted with provided rate (e.g., XRPBTC with BTC/EUR rate)
        effective_rate = quote_to_eur_rate
        computed_cost_eur = cost_quote * quote_to_eur_rate
    else:
        # No rate available -- leave as None for backfill
        effective_rate = None
        computed_cost_eur = None

    lot = TradeLot(
        id=f"lot_{fill_event.id}",
        # ... existing fields ...
        cost_eur=computed_cost_eur,
        quote_to_eur_rate=effective_rate,
    )
```

### Example 3: API Response Extension

```python
# In backend/app/services/lot_service.py -- _lot_db_to_dict()

    return {
        # ... existing fields ...
        "cost_quote": str(lot_db.cost_quote),
        "break_even": str(lot_db.cost_quote / lot_db.qty_base_initial) if lot_db.qty_base_initial else "0",

        # NEW: EUR cost basis
        "cost_eur": str(lot_db.cost_eur) if lot_db.cost_eur is not None else None,
        "quote_to_eur_rate": str(lot_db.quote_to_eur_rate) if lot_db.quote_to_eur_rate is not None else None,
        "break_even_eur": (
            str(lot_db.cost_eur / lot_db.qty_base_initial)
            if lot_db.cost_eur is not None and lot_db.qty_base_initial
            else None
        ),
    }
```

### Example 4: Sync Service Rate Fetching

```python
# In backend/app/services/sync_service.py

def _get_quote_to_eur_rates(
    self, fills: List[LedgerEvent]
) -> Dict[str, Decimal]:
    """
    Fetches historical quote-to-EUR rates for non-EUR-quoted fills.

    Uses minute-caching (same as BNB fee conversion).

    Returns:
        Dict[fill_id, Decimal] - Per-fill quote-to-EUR rate
    """
    fills_needing_rate = [
        f for f in fills
        if f.side == TradeSide.BUY and get_quote_asset(f.symbol or "BTCEUR") != "EUR"
    ]

    if not fills_needing_rate:
        return {}

    minute_cache: Dict[str, Decimal] = {}  # minute_key -> rate
    per_fill_rates: Dict[str, Decimal] = {}

    for fill in fills_needing_rate:
        quote_asset = get_quote_asset(fill.symbol)
        rate_pair = f"{quote_asset}EUR"  # e.g., "BTCEUR"
        minute_key = fill.timestamp.strftime("%Y-%m-%d %H:%M")

        if minute_key not in minute_cache:
            try:
                rate = self.binance_service.get_historical_price(rate_pair, fill.timestamp)
                minute_cache[minute_key] = rate
            except Exception:
                try:
                    rate = self.binance_service.get_current_price(rate_pair)
                    minute_cache[minute_key] = rate
                except Exception:
                    continue  # skip -- cost_eur will be None

        if minute_key in minute_cache:
            per_fill_rates[fill.id] = minute_cache[minute_key]

    return per_fill_rates
```

### Example 5: TradeLotDB Schema Extension

```python
# In backend/app/db/models.py -- TradeLotDB

class TradeLotDB(Base):
    __tablename__ = "trade_lots"

    # ... existing columns ...

    # NEW: EUR cost basis
    cost_eur = Column(Numeric(precision=20, scale=10), nullable=True)
    quote_to_eur_rate = Column(Numeric(precision=20, scale=10), nullable=True)
```

### Example 6: Domain-to-DB Conversion Updates

```python
# In lot_service.py -- _lot_db_to_domain()

def _lot_db_to_domain(lot_db: TradeLotDB) -> DomainLot:
    return DomainLot(
        # ... existing fields ...
        cost_eur=lot_db.cost_eur,
        quote_to_eur_rate=lot_db.quote_to_eur_rate,
    )
```

## Affected Callers Audit

These are all code paths that create lots and must be updated to pass `quote_to_eur_rate`:

| Caller | File | How it calls | Impact |
|--------|------|-------------|--------|
| `SyncService.sync_fills` | `sync_service.py` | `create_lot_from_buy_fill(db, user_id, event_db.id, fill_rates)` | Must also pass quote_to_eur_rate. Sync is the primary path. |
| CSV import | `csv_import_service.py` | `create_lot_from_buy_fill(db, user_id, event_db.id)` | Should pass rate if available; None for backfill is acceptable. |
| WebSocket handler | `websocket_fill_handler.py` (if exists) | `create_lot_from_buy_fill(...)` | Same as sync -- must pass rate. |

All paths go through `lot_service.create_lot_from_buy_fill()` which calls `domain.lots.create_trade_lot_from_buy_fill()`. The new parameter is optional with None default, making all existing callers backward-compatible.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Only EUR-quoted lots, no cross-currency support | Quote-generic `cost_quote` column | Recent (migration `q1w2e3r4t5y6`) | Lots track cost in their native quote currency |
| BNB fees tracked at current price | Historical BNB fee via Klines API, persisted as `fee_quote_value` | Iteration 3 | Proven pattern for historical price persistence |
| No EUR normalization for cross-pair | Phase 2 adds `cost_eur` + `quote_to_eur_rate` | This phase | Enables cross-pair P&L comparison in Phase 3 |

**Existing precedent for this exact pattern:**
- `fee_quote_value` on `LedgerEventDB`: Historical fee conversion rate, persisted once, immutable
- `backfill_fee_eur_value.py`: Standalone script that backfills historical prices for existing records
- `_get_per_fill_fee_conversion_rates()` in `sync_service.py`: Minute-cached batch rate fetching

## Scope Boundaries

### Changes IN Scope
1. `db/models.py`: Add `cost_eur`, `quote_to_eur_rate` columns to TradeLotDB
2. `domain/models.py`: Add fields to TradeLot dataclass + `break_even_eur` property
3. `domain/lots.py`: Compute `cost_eur` in `create_trade_lot_from_buy_fill()`
4. `services/lot_service.py`: Pass rate to domain, persist to DB, expose in API response
5. `services/sync_service.py`: Fetch BTC/EUR rate for non-EUR-quoted buy fills
6. Alembic migration: Add columns + backfill EUR-quoted lots
7. Backfill script: For existing BTC-quoted lots (optional, only needed if XRPBTC lots exist)
8. Tests: EUR cost basis computation, rate persistence, backfill correctness

### Changes OUT of Scope
- No pairing changes (Phase 3)
- No sell allocation P&L changes (Phase 3/4 -- sell allocation currently uses `cost_quote` which is correct per-symbol)
- No frontend changes (lot API response adds new optional fields, frontend can use them in Phase 3)
- No portfolio service changes (portfolio still computes per-symbol in quote currency)
- No order service changes
- No ledger changes

## Open Questions

1. **Should cost_eur be NOT NULL after backfill?**
   - What we know: Making it nullable simplifies the migration and handles edge cases (API unavailable at fill time). Making it NOT NULL ensures data completeness.
   - What's unclear: Whether there are existing XRPBTC lots that would block a NOT NULL constraint.
   - Recommendation: Start nullable. Add NOT NULL constraint in a follow-up migration after confirming all lots are backfilled. This is the same approach used for `fee_quote_value` (still nullable).

2. **Should the backfill script be part of the migration or separate?**
   - What we know: EUR-quoted lots can be backfilled in the migration (pure SQL: `SET cost_eur = cost_quote`). BTC-quoted lots need API calls.
   - What's unclear: Whether any XRPBTC lots exist yet.
   - Recommendation: Backfill EUR-quoted lots in migration (SQL). Create backfill script for BTC-quoted lots but only run if needed. This matches the `backfill_fee_eur_value.py` precedent.

3. **Should CSV import also fetch historical rates?**
   - What we know: CSV import creates lots from historical fills. It has access to fill timestamps.
   - Recommendation: For Phase 2, CSV import can leave `cost_eur = NULL` for BTC-quoted lots (backfill later). This keeps the CSV import simple. Enhancement can be added later if needed.

## Sources

### Primary (HIGH confidence)
- Direct code reading: `backend/app/services/binance.py` -- `get_historical_price()` implementation verified
- Direct code reading: `backend/app/services/sync_service.py` -- BNB fee conversion pattern verified (minute-cache, fallback chain)
- Direct code reading: `backend/app/domain/lots.py` -- `create_trade_lot_from_buy_fill()` signature and cost computation verified
- Direct code reading: `backend/app/db/models.py` -- TradeLotDB column structure verified
- Direct code reading: `backend/app/services/lot_service.py` -- `_lot_db_to_dict()` and `create_lot_from_buy_fill()` verified
- Direct code reading: `backend/scripts/backfill_fee_eur_value.py` -- backfill script pattern verified
- Direct code reading: `backend/alembic/env.py` -- `render_as_batch=True` confirmed for SQLite compatibility
- Direct code reading: All 13 existing Alembic migrations -- `batch_alter_table` pattern confirmed
- `.planning/research/ARCHITECTURE.md` -- Layer assignment for EUR cost basis confirmed
- `.planning/research/STACK.md` -- Cost basis normalization pattern confirmed
- `.planning/research/PITFALLS.md` -- P-1, P-3, P-5, P-10 directly relevant pitfalls confirmed

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` -- TS-2 complexity estimate (~100 lines) appears accurate based on code reading

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, extends proven patterns
- Architecture: HIGH -- direct code reading of all affected files, pattern reuse from BNB fee conversion
- Pitfalls: HIGH -- 6 pitfalls identified from code analysis and existing pitfall research, all have clear prevention
- Migration: HIGH -- 13 existing migrations provide clear template, SQLite batch mode confirmed

**Research date:** 2026-02-20
**Valid until:** 2026-04-20 (stable -- no external dependencies, pure codebase analysis)
