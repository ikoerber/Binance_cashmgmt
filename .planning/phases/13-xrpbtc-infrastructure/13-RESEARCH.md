# Phase 13: XRPBTC Infrastructure - Research

**Researched:** 2026-02-25
**Domain:** Multi-pair symbol registry, BTC-quoted lot EUR conversion, Alembic migration, frontend dual-display
**Confidence:** HIGH

## Summary

Phase 13 re-adds XRPBTC to the Symbol Registry and enables Binance sync, lot creation, and EUR-denominated financial display for BTC-quoted pairs. The core technical challenge is the EUR conversion layer: XRPBTC lots are quoted in BTC, not EUR, so every financial metric (cost, break-even, P&L) must be converted via a historical BTC/EUR rate at fill time for display.

The migration path is well-defined: the Alembic migration `094dac6f695a` dropped `quote_to_eur_rate` from `trade_lots`, `cost_eur` and `lot_symbol` from `pairing_items`, and `realized_pnl_eur` from `sell_allocations`. A new forward migration must re-add the `quote_to_eur_rate` column to `trade_lots` (the other dropped columns are pairing-related and pairing is disabled for XRPBTC, so they are not needed). The existing `cost_eur` column on `trade_lots` was preserved and is where the EUR-converted cost will live.

The pairing isolation is straightforward: pairing is entirely disabled for BTC-quoted pairs at both backend (suggestion filtering by symbol) and frontend (hide PairingPanel, checkboxes, and order creation for XRPBTC).

**Primary recommendation:** Implement in 3 focused plans: (1) Backend -- Symbol Registry + Migration + Domain Logic, (2) Backend -- Sync + Backfill + EUR conversion, (3) Frontend -- dual display, pairing isolation, symbol selector styling.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Dual display: show both BTC and EUR values side by side (e.g., "0.00002345 BTC / 1.87 EUR")
- Side-by-side layout in table columns (separated by slash), same font size for both values
- Pair badge on each lot row: small badge showing "XRPBTC" or "XRPEUR" to distinguish lots visually
- Unrealized P&L uses live BTCEUR price for EUR conversion (real-time EUR equivalent, not historical rate at purchase)
- Backfill existing XRPBTC lots via Binance Klines API (fetch historical BTC/EUR rate at each lot's fill time)
- New Alembic forward migration to re-add ALL columns dropped in v2.0 migration 094dac6f695a (quote_to_eur_rate, lot_symbol, base_asset, and any others)
- Few or no existing XRPBTC lots expected, but backfill script handles whatever exists
- Backfill uses proper Decimal precision (fix the float() issue from original backfill_cost_eur.py)
- XRPBTC pill placed after XRPEUR in navbar: BTCEUR | ETHEUR | XRPEUR | XRPBTC
- Different accent color for XRPBTC pill (amber/orange for BTC-quoted, distinguishes from purple EUR pairs)
- Subtle "Low liquidity" indicator on the XRPBTC dashboard (not intrusive, informational)
- No pairing for XRPBTC lots at all (not just excluded from EUR pairings -- pairing is entirely disabled for BTC-quoted pairs)
- Hide PairingPanel UI entirely on XRPBTC page (no checkboxes, no pairing tabs)
- No sell order creation for XRPBTC lots (analysis/tracking only, automated selling via Omni-Bot later)

### Claude's Discretion
- Overview page inclusion of XRPBTC in portfolio totals (Claude determines based on existing component patterns)
- Pairing isolation strictness (Claude determines whether suggestions-only or full isolation from manual selection is cleaner)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | User can see XRPBTC as available trading pair in Symbol Registry and frontend symbol selector | Add XRPBTC to backend `KNOWN_PAIRS` and frontend `KNOWN_PAIRS`. WebSocket price stream auto-subscribes via `KNOWN_PAIRS`. Amber pill styling in GlobalNav. |
| INFRA-02 | User can sync XRPBTC fills from Binance and create lots from them | Sync service already supports any symbol parameter. Domain `create_trade_lot_from_buy_fill` needs EUR cost calculation for BTC-quoted pairs. `quote_to_eur_rate` column needed on lots. |
| INFRA-03 | XRPBTC lots display correct EUR-denominated break-even and P&L (via historical BTC/EUR rate at fill time) | `cost_eur = cost_quote * btceur_rate_at_fill_time`. `break_even_eur = cost_eur / qty`. Unrealized P&L uses live BTCEUR price. Dual BTC/EUR display in frontend. |
| INFRA-04 | XRPBTC lots are excluded from EUR-pair pairing suggestions (no cross-pair pairing) | Pairing service already filters by symbol. Full isolation: hide PairingPanel, checkboxes, and order creation buttons for XRPBTC. Backend: `is_pairing_enabled(symbol)` guard. |
</phase_requirements>

## Standard Stack

### Core (no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.x (existing) | ORM, migration support | Already in use, `render_as_batch=True` for SQLite |
| Alembic | existing | Forward migration for `quote_to_eur_rate` | Project standard for all schema changes |
| python-binance | existing | `get_my_trades(symbol="XRPBTC")`, Klines API | Already used for all pairs |
| BinancePublicClient | existing singleton | Historical BTC/EUR rate via Klines | Already used for fee conversion, orderblock data |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Decimal | stdlib | All financial calculations | Always -- never float for money |
| React Router | existing | `/s/XRPBTC/*` routes | Already handles dynamic `:symbol` param |
| TanStack Query | existing | Data fetching + cache invalidation | Already used for all API calls |

### Alternatives Considered
None -- this phase uses only existing stack. No new dependencies needed.

## Architecture Patterns

### Pattern 1: Symbol Registry Extension
**What:** Add XRPBTC to both backend and frontend registries with BTC as quote asset.
**When to use:** Always -- all symbol-aware code reads from these registries.

**Backend (`backend/app/symbol_registry.py`):**
```python
KNOWN_PAIRS = {
    "BTCEUR": TradingPair("BTCEUR", "BTC", "EUR", 8, 2, "BTC/EUR"),
    "ETHEUR": TradingPair("ETHEUR", "ETH", "EUR", 5, 2, "ETH/EUR"),
    "XRPEUR": TradingPair("XRPEUR", "XRP", "EUR", 2, 4, "XRP/EUR"),
    "XRPBTC": TradingPair("XRPBTC", "XRP", "BTC", 2, 8, "XRP/BTC"),
}

def is_eur_quoted(symbol: str) -> bool:
    """Returns True if the pair's quote asset is EUR."""
    return parse_symbol(symbol).quote_asset == "EUR"

def is_pairing_enabled(symbol: str) -> bool:
    """Pairing is only available for EUR-quoted pairs."""
    return is_eur_quoted(symbol)

def is_order_creation_enabled(symbol: str) -> bool:
    """Manual sell order creation only for EUR-quoted pairs."""
    return is_eur_quoted(symbol)
```

**Frontend (`frontend/src/utils/symbolRegistry.js`):**
```javascript
export const KNOWN_PAIRS = {
  BTCEUR: { symbol: 'BTCEUR', base: 'BTC', quote: 'EUR', baseDecimals: 8, label: 'BTC/EUR' },
  ETHEUR: { symbol: 'ETHEUR', base: 'ETH', quote: 'EUR', baseDecimals: 5, label: 'ETH/EUR' },
  XRPEUR: { symbol: 'XRPEUR', base: 'XRP', quote: 'EUR', baseDecimals: 2, label: 'XRP/EUR' },
  XRPBTC: { symbol: 'XRPBTC', base: 'XRP', quote: 'BTC', baseDecimals: 2, label: 'XRP/BTC' },
};

export const isEurQuoted = (symbol) => KNOWN_PAIRS[symbol]?.quote === 'EUR';
export const isPairingEnabled = (symbol) => isEurQuoted(symbol);
export const isOrderCreationEnabled = (symbol) => isEurQuoted(symbol);
export const getQuoteDecimals = (symbol) => KNOWN_PAIRS[symbol]?.quote === 'BTC' ? 8 : 2;
```

### Pattern 2: EUR Conversion for BTC-Quoted Lots
**What:** At lot creation time, fetch historical BTC/EUR rate and compute `cost_eur = cost_quote * btceur_rate`. Store rate on lot for auditability.
**When to use:** Every time a XRPBTC buy fill creates a lot.

**Domain logic (`domain/lots.py`):**
```python
# Current code (line 97-98):
# EUR Cost Basis: All remaining pairs are EUR-quoted, so cost_eur = cost_quote
computed_cost_eur = cost_quote

# New logic:
if quote_asset == "EUR":
    computed_cost_eur = cost_quote
    quote_to_eur_rate = Decimal("1")
else:
    # BTC-quoted: cost_eur requires conversion rate (passed from service layer)
    computed_cost_eur = None  # Set by service layer after historical price fetch
    quote_to_eur_rate = None  # Set by service layer
```

**Service layer flow:**
1. `sync_fills()` calls `create_lot_from_buy_fill()`
2. For non-EUR-quoted pairs, service fetches `get_historical_price("BTCEUR", fill_timestamp)`
3. `cost_eur = cost_quote * btceur_rate`
4. `quote_to_eur_rate = btceur_rate` persisted on lot

### Pattern 3: Dual Display (BTC + EUR) in Frontend
**What:** For BTC-quoted pairs, show both BTC and EUR values in lot table columns.
**When to use:** LotsTable columns for cost, break-even, P&L when `activeSymbol` is BTC-quoted.

```javascript
// In LotsTable.jsx, for cost/break-even/P&L columns:
const isEurPair = isEurQuoted(activeSymbol);

// Cost column:
{isEurPair
  ? formatQuote(lot.cost_quote, activeSymbol)
  : <>{formatQuote(lot.cost_quote, activeSymbol)} / {formatEUR(lot.cost_eur)}</>
}

// Break-even column:
{isEurPair
  ? formatQuote(lot.break_even, activeSymbol)
  : <>{formatQuote(lot.break_even, activeSymbol)} / {formatEUR(lot.break_even_eur)}</>
}

// Unrealized P&L: uses live BTCEUR price
const eurPnl = isEurPair ? unrealizedPnl : unrealizedPnl * liveBtcEurPrice;
```

### Pattern 4: Pairing & Order Isolation
**What:** Completely hide pairing UI and order creation for BTC-quoted pairs.
**When to use:** LotsTable when `activeSymbol` is XRPBTC.

```javascript
// LotsTable.jsx:
const canPair = isPairingEnabled(activeSymbol);
const canCreateOrders = isOrderCreationEnabled(activeSymbol);

// Conditionally render:
{canPair && <PairingPanel ... />}
{canPair && /* checkboxes in table rows */}
{canCreateOrders && /* "+ Order" buttons */}
```

### Recommended Project Structure (changes only)
```
backend/
├── app/
│   ├── symbol_registry.py       # + XRPBTC entry, + is_eur_quoted(), is_pairing_enabled()
│   ├── domain/
│   │   └── lots.py              # Modified: EUR conversion logic for BTC-quoted pairs
│   ├── services/
│   │   ├── lot_service.py       # Modified: pass quote_to_eur_rate on lot creation
│   │   ├── sync_service.py      # Modified: fetch BTC/EUR rate for BTC-quoted fills
│   │   └── pairing_service.py   # Modified: guard with is_pairing_enabled()
│   ├── api/routes/
│   │   ├── lots.py              # Modified: guard order creation
│   │   ├── pairing.py           # Modified: guard all endpoints
│   │   └── orders.py            # Modified: guard order creation
│   └── db/
│       └── models.py            # + quote_to_eur_rate column on TradeLotDB
├── alembic/versions/
│   └── xxxx_readd_xrpbtc_columns.py  # Forward migration
└── scripts/
    └── backfill_cost_eur.py     # Already exists, needs Decimal fix

frontend/
├── src/
│   ├── utils/symbolRegistry.js  # + XRPBTC, + helpers
│   ├── components/
│   │   ├── GlobalNav.jsx        # + amber pill styling for XRPBTC
│   │   ├── SymbolLayout.jsx     # + "Low liquidity" indicator, quote label handling
│   │   ├── LotsTable.jsx        # + dual display, hide pairing/orders for XRPBTC
│   │   ├── LotSummaryCards.jsx  # + EUR conversion for recovery price
│   │   ├── Dashboard.jsx        # + low liquidity notice, dual display
│   │   └── Overview.jsx         # + XRPBTC in portfolio totals (already handles non-EUR)
│   └── hooks/useLotsData.js     # No changes needed (already symbol-aware)
```

### Anti-Patterns to Avoid
- **Float conversion for cost_eur:** The original `backfill_cost_eur.py` uses `float(cost_eur)` on line 198. All new code must use `Decimal(str(...))` consistently.
- **Hardcoded EUR assumption in domain logic:** The current `lots.py` line 97 hardcodes `cost_eur = cost_quote`. This must become conditional on quote asset.
- **Cross-pair pairing leaks:** Do not just filter XRPBTC from suggestions -- guard all pairing entry points (create, lock, execute) at the service level.
- **Live price confusion:** XRPBTC unrealized P&L calculation must use the XRPBTC market price for BTC P&L, then multiply by live BTCEUR for EUR P&L. Do not use BTCEUR price as the "market price" for XRPBTC lots.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Historical BTC/EUR price lookup | Custom API calls | Existing `BinancePublicClient.get_klines()` / `BinanceService.get_historical_price()` | Already has retry, caching, error handling |
| WebSocket price subscription for XRPBTC | Manual stream setup | Adding to `KNOWN_PAIRS` auto-subscribes via `websocket_manager.py` line 126 | Combined stream builds from `KNOWN_PAIRS` automatically |
| Symbol validation | Per-endpoint checks | `symbol_registry.is_known_symbol()` and `parse_symbol()` | Already validates and raises ValueError |
| EUR cost backfill | New script | Fix and reuse existing `scripts/backfill_cost_eur.py` | Already has minute-caching, rate limiting, dry-run mode |

## Common Pitfalls

### Pitfall 1: EUR Conversion Precision Loss
**What goes wrong:** Using `float()` for EUR conversion rates loses Decimal precision, violating the project's core invariant.
**Why it happens:** The existing `backfill_cost_eur.py` on line 198 passes `float(cost_eur)` and `float(btceur_rate)` to SQL params.
**How to avoid:** All rate storage and computation must use `Decimal`. SQL params accept Decimal directly via SQLAlchemy.
**Warning signs:** Any `float()` call touching financial values.

### Pitfall 2: Break-even Calculation for BTC-Quoted Pairs
**What goes wrong:** `break_even` returns BTC price, but UI shows it alongside EUR break-even. If EUR conversion uses the wrong price (cost-time vs. live), display is confusing.
**Why it happens:** `break_even` is `cost_quote / qty_base_initial` which gives XRP/BTC price. `break_even_eur` needs `cost_eur / qty_base_initial`.
**How to avoid:** Clearly separate: `break_even` = native quote price (BTC), `break_even_eur` = EUR equivalent from `cost_eur`. The `break_even_eur` already exists on `_lot_db_to_dict()` (line 947-950 of lot_service.py).
**Warning signs:** Mixing live BTCEUR rate with historical rate for static cost display.

### Pitfall 3: Live P&L EUR Conversion vs. Historical Cost EUR Conversion
**What goes wrong:** Confusing which BTCEUR rate to use where.
**Why it happens:** Two different rates serve two different purposes.
**How to avoid:** Follow CONTEXT.md decision strictly:
- **Cost/Break-even EUR:** Historical BTC/EUR rate at fill time (stored as `quote_to_eur_rate`, deterministic)
- **Unrealized P&L EUR:** Live BTC/EUR rate (real-time, changes every tick)

### Pitfall 4: Pairing Isolation Incomplete
**What goes wrong:** XRPBTC lots appear in pairing suggestions or can be manually selected.
**Why it happens:** Only filtering backend suggestions but not guarding manual creation or frontend checkboxes.
**How to avoid:** Three-layer isolation:
1. **Backend:** `is_pairing_enabled()` guard on all pairing API endpoints (suggestions, create, lock, execute)
2. **Frontend LotsTable:** Hide checkboxes entirely for XRPBTC
3. **Frontend LotsTable:** Hide PairingPanel and pairing action bar for XRPBTC

### Pitfall 5: WebSocket Price Stream Disruption
**What goes wrong:** Adding XRPBTC to `KNOWN_PAIRS` changes the combined stream URL, potentially causing reconnection.
**Why it happens:** The stream URL is built dynamically from `KNOWN_PAIRS` keys (websocket_manager.py line 126).
**How to avoid:** This is expected and harmless -- the WebSocket manager has reconnection logic. Just add the pair and the stream rebuilds automatically. Verify by checking WS connects after restart.

### Pitfall 6: Overview Page Double-Counting
**What goes wrong:** XRPBTC and XRPEUR both hold XRP, causing double-counting of XRP value.
**Why it happens:** Overview already deduplicates by `getBaseAsset()` (line 86-92 of Overview.jsx), preferring EUR-quoted pairs. XRPBTC XRP value would be skipped if XRPEUR already populated `binanceValueByBase["XRP"]`.
**How to avoid:** The existing deduplication logic handles this correctly. XRPBTC lots track the same XRP asset but their BTC-denominated market value is already handled separately. The Overview should include XRPBTC's P&L contribution (converted to EUR) but NOT double-count the XRP balance. Review the existing `toEur()` helper which already converts non-EUR values.

### Pitfall 7: Migration Column Re-addition Order
**What goes wrong:** Migration fails because of column dependencies or missing batch mode.
**Why it happens:** SQLite requires `render_as_batch=True` for ALTER TABLE operations.
**How to avoid:** Use `batch_alter_table` (project standard) and add all columns as nullable. The migration re-adds `quote_to_eur_rate` on `trade_lots` plus any other columns from migration `094dac6f695a` that are needed. Pairing-related columns (`cost_eur` on `pairing_items`, `lot_symbol`, `base_asset` on `pairings`, `realized_pnl_eur` on `sell_allocations`) are NOT needed since pairing is disabled for XRPBTC.

## Code Examples

### Alembic Forward Migration
```python
"""readd xrpbtc columns for v3.0

Reverse of 094dac6f695a (partial): only re-adds quote_to_eur_rate on trade_lots.
Pairing columns not needed (pairing disabled for BTC-quoted pairs).
"""
def upgrade() -> None:
    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('quote_to_eur_rate', sa.Numeric(precision=20, scale=10), nullable=True)
        )

    # Backfill EUR-quoted lots: rate = 1.0 (cost_eur already equals cost_quote)
    op.execute(sa.text("""
        UPDATE trade_lots
        SET quote_to_eur_rate = 1.0
        WHERE symbol IN ('BTCEUR', 'ETHEUR', 'XRPEUR')
          AND quote_to_eur_rate IS NULL
    """))


def downgrade() -> None:
    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.drop_column('quote_to_eur_rate')
```

### Domain Logic: EUR Cost Computation for BTC-Quoted Lots
```python
# In domain/lots.py create_trade_lot_from_buy_fill():

if quote_asset == "EUR":
    computed_cost_eur = cost_quote
else:
    # BTC-quoted: cost_eur will be set by service layer
    # after fetching historical BTC/EUR rate
    computed_cost_eur = None
```

### Service Layer: EUR Rate Fetch During Sync
```python
# In lot_service.py create_lot_from_buy_fill():

# After creating lot from domain logic...
symbol = event_db.symbol or "BTCEUR"
quote_asset = get_quote_asset(symbol)

if quote_asset != "EUR":
    # Fetch historical BTC/EUR rate at fill time
    from app.services.binance_public_client import get_binance_public_client
    client = get_binance_public_client()
    fill_timestamp = event_db.timestamp
    ts_ms = int(fill_timestamp.timestamp() * 1000)
    klines = client.get_klines("BTCEUR", "1m", limit=1, start_time=ts_ms)
    if klines:
        btceur_rate = Decimal(str(klines[0][4]))
        lot_db.cost_eur = lot_db.cost_quote * btceur_rate
        lot_db.quote_to_eur_rate = btceur_rate
```

### Frontend: Dual BTC/EUR Display
```javascript
// LotsTable.jsx cost column:
<td>
  {formatQuote(lot.cost_quote, activeSymbol)}
  {!isEurQuoted(activeSymbol) && lot.cost_eur && (
    <span className="eur-equivalent"> / {formatEUR(lot.cost_eur)}</span>
  )}
</td>
```

### Frontend: Pair Badge
```javascript
// LotsTable.jsx row, after order nr column:
<td className="order-id">
  {lot.symbol !== activeSymbol && (
    <span className="pair-badge">{getPairLabel(lot.symbol)}</span>
  )}
  {lot.binance_order_id || '...'}
</td>
```

### API Response: Extended Lot Dict
```python
# lot_service.py _lot_db_to_dict() additions:
"quote_to_eur_rate": str(lot_db.quote_to_eur_rate) if lot_db.quote_to_eur_rate else None,
```

## State of the Art

| Old Approach (v1.0-v2.0) | Current Approach (v3.0) | When Changed | Impact |
|---------------------------|-------------------------|--------------|--------|
| XRPBTC in registry with cross-pair pairing | XRPBTC in registry, pairing disabled, analysis-only | v2.0 removed, v3.0 re-adds | Simpler isolation, no cross-pair pairing complexity |
| `cost_eur = cost_quote` hardcoded | Conditional: EUR-quoted 1:1, BTC-quoted via historical rate | v3.0 Phase 13 | Correct EUR financials for BTC-quoted pairs |
| `float()` in backfill script | `Decimal()` throughout | v3.0 Phase 13 | Precision preservation |
| No `quote_to_eur_rate` column (dropped in v2.0) | Re-added for auditability | v3.0 Phase 13 | Deterministic EUR cost reproduction |

## Open Questions

1. **XRPBTC sell allocation across pairs**
   - What we know: XRPBTC sell fills should only allocate to XRPBTC lots. The `_get_base_symbols_for_sell_event()` function already returns `[sell_symbol]` which handles this correctly.
   - What's unclear: Nothing -- this works correctly as-is.
   - Recommendation: Verify in tests but no code change needed.

2. **Reconciliation for XRPBTC**
   - What we know: Reconciliation service compares Binance balances with ledger. XRP balance is shared between XRPEUR and XRPBTC trades.
   - What's unclear: Whether reconciliation should run per-symbol or aggregate XRP across both pairs.
   - Recommendation: Reconciliation already runs per-symbol. XRPBTC reconciliation would compare XRP balance from XRPBTC lots only, which may not match Binance (since some XRP came via XRPEUR). This is acceptable -- reconciliation shows the discrepancy, user understands the context. No special handling needed.

3. **Combined Score / Orderblocks for XRPBTC**
   - What we know: These features use the `symbol` parameter. Adding XRPBTC to registry means they could theoretically be accessed.
   - What's unclear: Whether MacroSignal/Sentiment/Orderblock analysis makes sense for XRPBTC.
   - Recommendation: Let the existing code handle it. If data is unavailable (e.g., no XRPBTC funding rate), graceful degradation already handles missing pillars. The subnav already renders "Combined Score" and "Orderblocks" links for any symbol.

## Sources

### Primary (HIGH confidence)
- **Codebase inspection** -- All findings verified by direct reading of source files:
  - `backend/app/symbol_registry.py` -- current KNOWN_PAIRS (3 EUR pairs, no XRPBTC)
  - `backend/app/db/models.py` -- TradeLotDB schema (has `cost_eur`, no `quote_to_eur_rate`)
  - `backend/alembic/versions/094dac6f695a_remove_xrpbtc_cross_pair_columns.py` -- exact columns dropped
  - `backend/alembic/versions/f0f489761dc8_add_eur_cost_basis_columns_to_trade_lots.py` -- original EUR cost migration
  - `backend/app/domain/lots.py` lines 97-98 -- hardcoded `cost_eur = cost_quote`
  - `backend/app/services/sync_service.py` -- sync flow (symbol-parameterized)
  - `backend/app/services/lot_service.py` -- lot creation and dict serialization
  - `backend/app/services/websocket_manager.py` line 126 -- auto-subscription from KNOWN_PAIRS
  - `backend/scripts/backfill_cost_eur.py` -- existing backfill with float() bug on line 198
  - `frontend/src/utils/symbolRegistry.js` -- frontend KNOWN_PAIRS
  - `frontend/src/components/GlobalNav.jsx` -- pill rendering from `getAllSymbols()`
  - `frontend/src/components/SymbolLayout.jsx` -- validation + subnav
  - `frontend/src/components/LotsTable.jsx` -- table rendering, pairing UI
  - `frontend/src/components/Overview.jsx` -- cross-symbol aggregation with deduplication
  - `frontend/src/utils/formatters.js` -- `formatQuote()` already handles BTC quote

### Secondary (MEDIUM confidence)
- **CONTEXT.md** -- User decisions from discussion phase (direct input, locked decisions)
- **STATE.md** -- Key context: `quote_to_eur_rate` dropped in migration `094dac6f695a`, numpy 2.2.6 only new backend dep

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all patterns exist in codebase
- Architecture: HIGH -- extension of existing symbol-aware patterns, all code paths inspected
- Pitfalls: HIGH -- identified from direct codebase inspection (float bug, hardcoded EUR, pairing leaks)
- Migration: HIGH -- exact columns known from migration `094dac6f695a` downgrade function
- Frontend: HIGH -- all components inspected, existing non-EUR handling already in place (Overview, formatQuote)

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable domain, no external dependencies to change)
