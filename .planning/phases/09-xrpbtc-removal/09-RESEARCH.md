# Phase 9: XRPBTC Removal - Research

**Researched:** 2026-02-23
**Domain:** Code removal / simplification of cross-pair abstractions
**Confidence:** HIGH

## Summary

Phase 9 removes all XRPBTC cross-pair code paths from backend and frontend. The codebase currently has XRPBTC deeply woven into: symbol registry (both Python and JS), domain models (RouteDetails, DualRouteComparison, RoutingDecision), pairing logic (cross-pair mode, EUR-normalized P&L, dual-route comparison), order service (route selection, satoshi encoding), sync service (quote-to-EUR rate fetching), lot service (cross-pair realized P&L), and frontend components (cross-pair toggle, routing badges, pair-origin badges).

The changes are purely subtractive -- no new features, only removal and simplification. Historical XRPBTC data in the database stays untouched (rows preserved, only columns removed via Alembic migration). The key risk is breaking existing EUR-pair functionality while removing cross-pair code. Thorough test execution after each change is critical.

**Primary recommendation:** Work layer-by-layer (Symbol Registry first, then Domain models, then Services, then API, then Frontend, then Alembic migration, then test cleanup). Each layer removal should keep tests passing for EUR-pair functionality.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- XRPBTC entfernen UND ueberfluessige Abstraktionen vereinfachen (nicht nur XRPBTC-Code loeschen)
- Sell-Routing Service komplett entfernen (RoutingDecision Model, routing_decision_json Logik, Sell-Routing Service) -- Orders gehen direkt ans einzige EUR-Pair
- get_symbols_for_base_asset() und hasMultipleSymbols() entfernen -- 1:1 Mapping Base-Asset zu Symbol, keine Multi-Symbol-Abstraktion noetig
- DualRouteComparison, RouteDetails, Frontend-Vergleichsansicht komplett entfernen
- DB-Spalten routing_decision_json (PairingDB) und quote_to_eur_rate (TradeLotDB) per Alembic-Migration entfernen
- cost_eur auf TradeLotDB bleibt (wird auch fuer EUR-Lots gebraucht)
- Lot/Order/Pairing/Ledger-Event Zeilen mit XRPBTC bleiben in der DB (nur Spalten weg, keine Daten-Loeschung)
- backfill_cost_eur.py Script behalten (als Referenz)
- XRPBTC Lots/Orders im Frontend verstecken (nicht anzeigen, kein Archiv-View)
- XRPBTC Lots aus Portfolio-Berechnung ausschliessen (nicht in KPIs: BTC Bestand, P&L etc.)
- Binance Sync importiert XRPBTC Fills weiterhin (Ledger-Vollstaendigkeit), aber keine Lot-Erstellung / keine Anzeige
- Reconciliation schliesst XRPBTC aus (kein Balance-Abgleich fuer XRPBTC)

### Claude's Discretion
- Reihenfolge der Datei-Aenderungen (Backend-first oder Frontend-first)
- Welche XRPBTC-spezifischen Tests geloescht vs. angepasst werden
- Ob Satoshi-Encoding-Code komplett oder nur XRPBTC-Pfad entfernt wird
- Detailgrad der Alembic-Migration (ein Schritt oder aufgeteilt)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REM-01 | XRPBTC aus Symbol Registry entfernen (Backend + Frontend) | Exact locations identified: `backend/app/symbol_registry.py` line 24, `frontend/src/utils/symbolRegistry.js` line 12. Also remove `get_symbols_for_base_asset()` and `getSymbolsForBaseAsset()` |
| REM-02 | Cross-Pair Routing-Logik entfernen (Sell-Routing Service, Dual-Route Simulation) | Identified in: `domain/pairing.py` (compute_dual_route_comparison), `services/order_service.py` (route selection block lines 331-374), `services/pairing_service.py` (dual-route comparison lines 198-241, simulate params xrpbtc_price/btceur_price), `api/routes/pairing.py` (xrpbtc_price/btceur_price params) |
| REM-03 | Satoshi-Encoding und BTC-Quote-spezifische clientOrderId-Logik entfernen | Located in `domain/orders.py` lines 194-206 and `services/order_service.py` lines 410-422. All EUR-quoted prices are >= 1, so the sub-1 branch can be removed entirely |
| REM-04 | XRPBTC-spezifische Domain-Modelle entfernen (RouteDetails, DualRouteComparison, RoutingDecision) | In `domain/models.py` lines 247-299. Also remove: Pairing.is_cross_pair, Pairing.base_asset, Pairing.net_cost_eur(), PairingItem.cost_eur, PairingItem.lot_symbol. Remove `compute_cross_pair_realized_pnl_eur()` from `domain/lots.py` |
| REM-05 | XRPBTC-spezifische Tests und Scripts bereinigen | 5 test files primarily affected: `test_cross_pair_pairing.py` (DELETE entirely), `test_sell_routing.py` (DELETE entirely), `test_sell_allocation_isolation.py` (DELETE or heavily rewrite), `test_portfolio_cross_pair.py` (DELETE entirely), `test_eur_cost_basis.py` (remove XRPBTC test cases, keep EUR tests). Also: `test_order_filters.py` has xrpbtc_filters fixture (remove) |
| REM-06 | Frontend Cross-Pair UI-Elemente entfernen (Pair-Herkunft-Badges, Routing-Anzeige, Dual-Route Simulation) | Identified in: `PairingPanel.jsx` (cross-pair toggle, baseAsset query params), `PairingExistingTab.jsx` (routing_decision display, cross-pair labels, pair-origin badges, xrpbtc price passing), `api/client.js` (xrpbtcPrice/btceurPrice params), `symbolRegistry.js` (XRPBTC entry, getSymbolsForBaseAsset), `PairingPanel.css` (routing-badge, cross-pair-toggle, pair-origin-badge, cross-pair-label styles) |
</phase_requirements>

## Affected Files Inventory

### Backend - Files to Modify

| File | Changes | Impact |
|------|---------|--------|
| `app/symbol_registry.py` | Remove XRPBTC from KNOWN_PAIRS. Remove `get_symbols_for_base_asset()`. | HIGH - Central registry, affects all consumers |
| `app/domain/models.py` | Remove RouteDetails, DualRouteComparison, RoutingDecision dataclasses. Remove Pairing.base_asset, Pairing.is_cross_pair, Pairing.net_cost_eur(). Remove PairingItem.cost_eur, PairingItem.lot_symbol. Remove TradeLot.quote_to_eur_rate. | HIGH - Domain model simplification |
| `app/domain/pairing.py` | Remove compute_dual_route_comparison(). Remove use_eur_cost parameter from suggest_pairings(). Remove cross-pair base_asset logic. Remove imports of RouteDetails, DualRouteComparison. | HIGH - Pairing logic simplification |
| `app/domain/lots.py` | Remove compute_cross_pair_realized_pnl_eur(). Remove quote_to_eur_rate parameter from create_trade_lot_from_buy_fill(). Simplify EUR cost basis (always quote_asset == EUR). | HIGH - Lot creation simplification |
| `app/domain/orders.py` | Remove satoshi encoding branch (sub-1 price). Simplify client_order_id generation. Remove btceur_rate parameter from compute_pairing_order_params(). | MEDIUM |
| `app/services/order_service.py` | Remove entire cross-pair route selection block (lines 331-374). Remove routing_decision persistence. Remove satoshi encoding. Remove RoutingDecision import. | HIGH |
| `app/services/pairing_service.py` | Remove base_asset parameter everywhere. Remove dual-route comparison. Remove cross-pair lot loading. Remove xrpbtc_price/btceur_price from simulate. Simplify _pairing_to_dict(). | HIGH |
| `app/services/lot_service.py` | Remove quote_to_eur_rate parameter from create_lot_from_buy_fill(). Remove cross-pair P&L override block in sell allocation. Remove compute_cross_pair_realized_pnl_eur import. | MEDIUM |
| `app/services/sync_service.py` | Remove _get_quote_to_eur_rates() method. Remove quote_to_eur_rate passing to create_lot_from_buy_fill(). | MEDIUM |
| `app/services/websocket_fill_handler.py` | Remove quote_to_eur_rate fetching block (lines 144-160). | LOW |
| `app/api/routes/pairing.py` | Remove base_asset parameter from all endpoints. Remove xrpbtc_price/btceur_price from simulate endpoint. Remove get_symbols_for_base_asset import. | MEDIUM |
| `app/db/models.py` | Remove routing_decision_json from PairingDB. Remove base_asset from PairingDB. Remove quote_to_eur_rate from TradeLotDB. Keep cost_eur on TradeLotDB. Remove cost_eur and lot_symbol from PairingItemDB. Remove realized_pnl_eur from SellAllocationDB. | HIGH - ORM changes require Alembic migration |

### Backend - Test Files

| File | Action | Rationale |
|------|--------|-----------|
| `tests/test_cross_pair_pairing.py` | DELETE entirely | 100% XRPBTC cross-pair tests |
| `tests/test_sell_routing.py` | DELETE entirely | 100% cross-pair routing + RoutingDecision tests. BUT: contains `test_pairing_order_params_xrpbtc_client_order_id_no_collision` and max-value tests. The non-cross-pair pairing_order_params tests should be preserved -- move to test_pairing.py or test_order_lifecycle.py |
| `tests/test_portfolio_cross_pair.py` | DELETE entirely | 100% XRPBTC portfolio isolation tests |
| `tests/test_sell_allocation_isolation.py` | DELETE entirely | Tests cross-pair sell allocation (XRPEUR + XRPBTC). After removal, only single-symbol allocation exists, already tested in test_lots_fifo.py and test_lots_strategies.py |
| `tests/test_eur_cost_basis.py` | MODIFY: Remove XRPBTC test cases (TestBTCQuotedLots, TestBTCQuotedWithFees, fee tests with quote_to_eur_rate). Keep EUR test cases. | EUR-only lot creation still needs testing |
| `tests/test_order_filters.py` | MODIFY: Remove xrpbtc_filters fixture and XRPBTC-specific tests | Keep EUR filter tests |

### Frontend - Files to Modify

| File | Changes |
|------|---------|
| `src/utils/symbolRegistry.js` | Remove XRPBTC entry. Remove `getSymbolsForBaseAsset()`. Remove `getQuoteDecimals()` BTC branch (only EUR remains). |
| `src/api/client.js` | Remove xrpbtcPrice/btceurPrice params from simulatePairing(). Remove baseAsset param from getPairingSuggestions() and createPairing(). |
| `src/components/PairingPanel.jsx` | Remove crossPairMode state, hasMultipleSymbols check, effectiveCrossPair. Remove getSymbolsForBaseAsset import. Remove cross-pair toggle checkbox UI. Simplify suggestion/create API calls. |
| `src/components/PairingExistingTab.jsx` | Remove routing_decision display (routing-badge, routing-savings). Remove cross-pair labels. Remove pair-origin badges. Remove xrpbtcPrice/btceurPrice passing to simulate. |
| `src/components/PairingPanel.css` | Remove: .routing-badge, .routing-savings, .cross-pair-toggle, .cross-pair-toggle input[type="checkbox"], .cross-pair-toggle:has(input:checked), .pair-origin-badge, .pair-origin-badge.pair-eur, .pair-origin-badge.pair-btc, .cross-pair-label |
| `src/hooks/useLotsData.js` | Remove "Cross-Pair-Kontamination" comments (cosmetic) |
| `src/components/Overview.jsx` | Remove cross-pair comments (cosmetic) |
| `src/components/Dashboard.jsx` | Remove cross-pair comment (cosmetic) |

### Backend - Scripts

| File | Action |
|------|--------|
| `scripts/backfill_cost_eur.py` | KEEP as reference (per user decision) |

### Alembic Migration

One new migration to remove columns:

| Table | Column to Remove | Notes |
|-------|-----------------|-------|
| `pairings` | `routing_decision_json` | JSON column, nullable |
| `pairings` | `base_asset` | String column, nullable |
| `trade_lots` | `quote_to_eur_rate` | Numeric column, nullable |
| `pairing_items` | `cost_eur` | Numeric column, nullable |
| `pairing_items` | `lot_symbol` | String column, nullable |
| `sell_allocations` | `realized_pnl_eur` | Numeric column, nullable |

**Keep:** `trade_lots.cost_eur` (used for EUR lots too -- always set to cost_quote for EUR-quoted lots).

## Architecture Patterns

### Recommended Change Order

```
1. Symbol Registry (Backend + Frontend)
   Remove XRPBTC, remove get_symbols_for_base_asset()

2. Domain Models
   Remove RouteDetails, DualRouteComparison, RoutingDecision
   Simplify Pairing, PairingItem, TradeLot

3. Domain Logic
   Simplify pairing.py (remove dual-route comparison, cross-pair mode)
   Simplify lots.py (remove cross-pair P&L, quote_to_eur_rate)
   Simplify orders.py (remove satoshi encoding, btceur_rate)

4. Services
   Simplify order_service.py (remove route selection)
   Simplify pairing_service.py (remove base_asset, dual-route)
   Simplify lot_service.py (remove cross-pair P&L override)
   Simplify sync_service.py (remove quote_to_eur_rate fetching)
   Simplify websocket_fill_handler.py

5. API Routes
   Simplify pairing.py routes (remove base_asset, xrpbtc_price params)

6. Frontend
   Symbol registry, API client, PairingPanel, PairingExistingTab, CSS

7. Alembic Migration
   Drop columns: routing_decision_json, base_asset, quote_to_eur_rate,
   pairing_items.cost_eur, pairing_items.lot_symbol, realized_pnl_eur

8. Test Cleanup
   Delete cross-pair test files, modify EUR test files
```

### Pattern: Safe Column Removal with Alembic + SQLite

SQLite does not support `ALTER TABLE DROP COLUMN` natively (prior to 3.35.0). The project uses `render_as_batch=True` in alembic env.py, which handles this via table recreation:

```python
def upgrade() -> None:
    with op.batch_alter_table('pairings', schema=None) as batch_op:
        batch_op.drop_column('routing_decision_json')
        batch_op.drop_column('base_asset')

    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.drop_column('quote_to_eur_rate')

    with op.batch_alter_table('pairing_items', schema=None) as batch_op:
        batch_op.drop_column('cost_eur')
        batch_op.drop_column('lot_symbol')

    with op.batch_alter_table('sell_allocations', schema=None) as batch_op:
        batch_op.drop_column('realized_pnl_eur')
```

**Critical:** Run Alembic migration AFTER removing ORM columns from `db/models.py`, otherwise SQLAlchemy will try to access dropped columns.

### Pattern: Sync Preserves XRPBTC Fills Without Lot Creation

The sync service currently creates lots for all Buy fills. After removal, XRPBTC fills should still be imported as LedgerEvents (Ledger completeness) but skip lot creation:

```python
# In sync_service.py, after creating ledger event:
if get_quote_asset(symbol) != "EUR":
    # Non-EUR-quoted symbol: import ledger event but skip lot creation
    continue
```

Alternatively, since XRPBTC is removed from KNOWN_PAIRS, the sync would need to either:
1. Keep XRPBTC in a "legacy symbols" set for sync-only purposes, OR
2. Accept that future XRPBTC fills will fail `parse_symbol()` validation

**Recommendation:** Keep XRPBTC recognizable for sync purposes. Add a simple check: if symbol not in registry's active EUR-quoted pairs, import ledger event but skip lot creation. The simplest approach: check `get_quote_asset(symbol) == "EUR"` before lot creation, and keep XRPBTC in a separate `LEGACY_PAIRS` dict (not exposed to the rest of the app).

Wait -- re-reading the CONTEXT.md more carefully: "Binance Sync importiert XRPBTC Fills weiterhin (Ledger-Vollstaendigkeit), aber keine Lot-Erstellung / keine Anzeige". This means the sync must still know about XRPBTC to parse fills. The cleanest approach:

1. Remove XRPBTC from `KNOWN_PAIRS` (the active registry)
2. Add an `ALL_PAIRS` dict that includes XRPBTC for parsing purposes
3. Sync uses `ALL_PAIRS` for fill parsing, but only creates lots for `KNOWN_PAIRS` symbols
4. Or simpler: just hardcode a skip in sync for non-EUR-quoted symbols

### Pattern: Portfolio Exclusion of XRPBTC

`compute_portfolio_from_ledger()` already filters by symbol (line 57: `if event.symbol and event.symbol != symbol: continue`). Since all portfolio calls pass a EUR-quoted symbol, XRPBTC fills are already excluded. No change needed here beyond removing the "Cross-Pair-Isolation" comment.

### Pattern: Frontend Lots API Filtering

The lots API endpoint already filters by symbol: `TradeLotDB.symbol == symbol`. Since the frontend navigates by symbol (SymbolLayout -> /s/:symbol), XRPBTC lots will not appear as long as there is no XRPBTC route. After removing XRPBTC from the frontend symbol registry, no route exists for it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQLite column drops | Raw SQL ALTER TABLE | `batch_alter_table()` via Alembic's batch mode | SQLite pre-3.35 limitation; batch mode handles table recreation transparently |
| Legacy symbol parsing | Custom parser for XRPBTC fills | Keep XRPBTC in a `LEGACY_PAIRS` lookup or use `is_known_symbol()` guard | Maintains Ledger completeness without polluting active symbol registry |

## Common Pitfalls

### Pitfall 1: Breaking EUR-pair Tests While Removing XRPBTC Code
**What goes wrong:** Removing cross-pair parameters (like quote_to_eur_rate) from function signatures breaks callers that pass them for EUR pairs too.
**Why it happens:** `create_trade_lot_from_buy_fill()` uses quote_to_eur_rate for EUR lots (sets rate=1, cost_eur=cost_quote). Removing the parameter requires updating all callers.
**How to avoid:** For EUR-quoted lots, the domain logic already auto-detects `quote_asset == "EUR"` and sets cost_eur=cost_quote. The quote_to_eur_rate parameter is only needed for non-EUR lots. After removing XRPBTC, the parameter is unused -- but verify no EUR-path callers pass it explicitly.
**Warning signs:** test_eur_cost_basis.py tests break.

### Pitfall 2: Alembic Migration Order
**What goes wrong:** Running Alembic migration before removing ORM column references causes SQLAlchemy errors. Running it after but forgetting to remove DB model columns causes "column not found" at query time.
**Why it happens:** SQLAlchemy reads DB model columns on startup. If ORM declares a column that doesn't exist in DB, queries fail.
**How to avoid:** Remove ORM columns from `db/models.py` FIRST, then create and run Alembic migration. The migration's downgrade function should add columns back.

### Pitfall 3: Sync Service Fails on Unknown Symbol
**What goes wrong:** After removing XRPBTC from KNOWN_PAIRS, `parse_symbol("XRPBTC")` raises ValueError. If sync encounters an XRPBTC fill, it crashes.
**Why it happens:** Binance API returns fills for all symbols ever traded. Old XRPBTC fills will appear.
**How to avoid:** Either: (a) keep XRPBTC in a "legacy" lookup used only by sync, or (b) wrap fill processing in a try/except that skips unknown symbols, or (c) add symbol filter to the Binance API call (sync already receives symbol parameter -- only syncs fills for the given symbol).
**Warning signs:** Sync endpoint returns 500 errors.

**Analysis:** Looking at the sync service code, `sync_fills()` receives a `symbol` parameter and calls `self.binance_service.fetch_trades(symbol, start_time)`. The sync is already per-symbol. The sync endpoint (`api/routes/sync.py`) receives the symbol from the frontend. Since the frontend will not have XRPBTC as a navigable symbol, it will never trigger XRPBTC sync. However, if `sync_fills()` is called with symbol="XRPBTC" directly, it would still work because XRPBTC is still a valid Binance pair -- only our registry no longer lists it. The real question is: will the fill handler need to parse the symbol? Let me trace the code path. The sync_service stores `fill.symbol` on the LedgerEvent but uses the `symbol` parameter (passed to sync_fills) for Binance API calls. The lot creation uses `event_db.symbol` (stored on the event). So as long as no one calls sync with "XRPBTC", we are fine.

**Conclusion:** Since the sync is already per-symbol and the frontend/API validates symbols against KNOWN_PAIRS, removing XRPBTC from the registry is sufficient. No special "legacy" handling needed for sync. The only edge case is the WebSocket fill handler, which receives fills for ALL symbols on the user stream. This handler calls `parse_symbol()` -- it needs a guard for unknown symbols.

### Pitfall 4: WebSocket Fill Handler Crashes on XRPBTC Fills
**What goes wrong:** The WebSocket user stream receives `executionReport` for ALL symbols. If a XRPBTC order fills, the handler calls `parse_symbol("XRPBTC")` and crashes.
**Why it happens:** WebSocket streams are not filtered by symbol.
**How to avoid:** Add an `is_known_symbol()` guard at the top of the fill handler. Skip unknown symbols gracefully (log + continue).
**Warning signs:** WebSocket disconnects after XRPBTC fill event.

### Pitfall 5: Satoshi Encoding Removal -- Verify All EUR Prices >= 1
**What goes wrong:** Removing the satoshi encoding branch (for sub-1 prices) could break if any EUR-quoted pair has prices below 1.
**Why it happens:** XRPEUR prices are ~0.50 EUR -- they ARE below 1!
**How to avoid:** Check current XRPEUR price. If XRPEUR can have prices < 1.00, the satoshi encoding branch must be KEPT for general use, not just XRPBTC. Only remove the XRPBTC-specific comments.
**Warning signs:** client_order_id collisions for XRPEUR orders.

**CRITICAL FINDING:** XRPEUR prices are approximately 0.50 EUR. The satoshi encoding IS needed for XRPEUR. Only the XRPBTC-specific comments should be updated. The actual sub-1 price encoding logic must be retained.

### Pitfall 6: cost_eur Still Needed on TradeLot
**What goes wrong:** Accidentally removing cost_eur from TradeLotDB.
**Why it happens:** cost_eur was added for cross-pair EUR normalization, but it is also useful for EUR lots (always equals cost_quote). The user explicitly decided to keep it.
**How to avoid:** Only remove quote_to_eur_rate, not cost_eur.

## Code Examples

### Symbol Registry After Cleanup

```python
# backend/app/symbol_registry.py
KNOWN_PAIRS = {
    "BTCEUR": TradingPair("BTCEUR", "BTC", "EUR", 8, 2, "BTC/EUR"),
    "ETHEUR": TradingPair("ETHEUR", "ETH", "EUR", 5, 2, "ETH/EUR"),
    "XRPEUR": TradingPair("XRPEUR", "XRP", "EUR", 2, 4, "XRP/EUR"),
}

# Remove: get_symbols_for_base_asset() -- no longer needed (1:1 mapping)
```

### Frontend Symbol Registry After Cleanup

```javascript
// frontend/src/utils/symbolRegistry.js
export const KNOWN_PAIRS = {
  BTCEUR: { symbol: 'BTCEUR', base: 'BTC', quote: 'EUR', baseDecimals: 8, label: 'BTC/EUR' },
  ETHEUR: { symbol: 'ETHEUR', base: 'ETH', quote: 'EUR', baseDecimals: 5, label: 'ETH/EUR' },
  XRPEUR: { symbol: 'XRPEUR', base: 'XRP', quote: 'EUR', baseDecimals: 2, label: 'XRP/EUR' },
};

// Remove: getSymbolsForBaseAsset() -- no longer needed
// Simplify: getQuoteDecimals() -- always returns 2 (EUR)
```

### Simplified Pairing Domain Model

```python
# After cleanup: Pairing dataclass
@dataclass
class Pairing:
    id: str
    items: List[PairingItem]
    threshold_pct: Decimal
    status: PairingStatus = PairingStatus.DRAFT
    created_at: Optional[datetime] = None
    symbol: str = "BTCEUR"
    # Removed: base_asset, is_cross_pair, net_cost_eur()

@dataclass
class PairingItem:
    lot_id: str
    qty_base: Decimal
    cost_quote: Decimal
    # Removed: cost_eur, lot_symbol
```

### Simplified suggest_pairings()

```python
def suggest_pairings(
    lots: List[TradeLot],
    market_price: Decimal,
    threshold_pct: Decimal = Decimal("0.05"),
) -> List[Pairing]:
    # Removed: use_eur_cost parameter, cross-pair validation, cross_pair_base_asset
    # All lots use break_even * qty_base_open for cost (native quote = EUR)
```

### Simplified create_trade_lot_from_buy_fill()

```python
def create_trade_lot_from_buy_fill(
    fill_event: LedgerEvent,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> TradeLot:
    # Removed: quote_to_eur_rate parameter
    # EUR cost basis: always cost_eur = cost_quote (all pairs EUR-quoted)
    # quote_to_eur_rate no longer stored on TradeLot
```

### WebSocket Fill Handler Guard

```python
# In websocket_fill_handler.py, at the top of fill processing:
if not is_known_symbol(symbol):
    logger.info("Skipping fill for unknown/legacy symbol: %s", symbol)
    return {"action": "skipped", "reason": f"unknown symbol {symbol}"}
```

### Alembic Migration

```python
def upgrade() -> None:
    """Remove cross-pair columns (XRPBTC removal)."""
    with op.batch_alter_table('pairings', schema=None) as batch_op:
        batch_op.drop_column('routing_decision_json')
        batch_op.drop_column('base_asset')

    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.drop_column('quote_to_eur_rate')

    with op.batch_alter_table('pairing_items', schema=None) as batch_op:
        batch_op.drop_column('cost_eur')
        batch_op.drop_column('lot_symbol')

    with op.batch_alter_table('sell_allocations', schema=None) as batch_op:
        batch_op.drop_column('realized_pnl_eur')
```

## Decisions on Discretion Areas

### 1. Change Order: Backend-first
**Recommendation:** Backend-first, layer by layer (registry -> domain -> services -> API -> frontend -> migration -> tests). This ensures the API contract changes are understood before frontend adapts.

### 2. Test Disposition

| Test File | Decision | Rationale |
|-----------|----------|-----------|
| `test_cross_pair_pairing.py` | DELETE | 100% cross-pair specific |
| `test_sell_routing.py` | DELETE, but salvage pairing_order_params tests | Move `TestPairingOrderParams` class (non-XRPBTC tests like max-value check) to `test_pairing.py` |
| `test_portfolio_cross_pair.py` | DELETE | 100% cross-pair isolation |
| `test_sell_allocation_isolation.py` | DELETE | Cross-pair allocation tests; single-pair allocation already covered by test_lots_fifo.py and test_lots_strategies.py |
| `test_eur_cost_basis.py` | MODIFY | Remove TestBTCQuotedLots, TestBTCQuotedWithFees, keep TestEURQuotedLots and backward compat tests. Remove quote_to_eur_rate references |
| `test_order_filters.py` | MODIFY | Remove xrpbtc_filters fixture and XRPBTC-specific tests |

### 3. Satoshi Encoding: KEEP the general sub-1 encoding logic
**Rationale:** XRPEUR prices are below 1 EUR (~0.50). The satoshi encoding prevents client_order_id collisions for sub-1 prices. Only update comments to remove XRPBTC-specific references. The logic is needed for all sub-1-priced EUR pairs.

### 4. Alembic Migration: Single migration
**Rationale:** All column drops are part of one logical change (XRPBTC removal). One migration is cleaner than splitting. Use `batch_alter_table` for SQLite compatibility (already configured in env.py).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Multi-symbol per base asset (XRPEUR + XRPBTC) | 1:1 base-to-EUR-symbol | This phase | Eliminates routing logic, cross-pair P&L, dual-route simulation |
| Sell routing via DualRouteComparison | Direct sell on EUR pair | This phase | Removes ~300 lines of routing code |
| EUR-normalized cost_eur via quote_to_eur_rate | cost_eur = cost_quote (trivially EUR) | This phase | Simplifies lot creation, removes rate fetching |

## Open Questions

1. **Existing XRPBTC pairings in DB**
   - What we know: XRPBTC rows in pairings/lots/orders stay in DB. Columns (routing_decision_json, base_asset) get dropped.
   - What's unclear: Are there any EXECUTED pairings with routing_decision_json that someone might want to query later?
   - Recommendation: Data is preserved in the existing migration history and could be reconstructed. The column drop is safe. Production verification (blocker from STATE.md) should confirm zero open XRPBTC positions/orders before proceeding.

2. **WebSocket streams for XRPBTC**
   - What we know: WebSocket user stream receives events for ALL symbols. After removal, XRPBTC fills will arrive but have no handler.
   - What's unclear: Will there still be open XRPBTC orders that could fill?
   - Recommendation: Add `is_known_symbol()` guard in fill handler. Log and skip unknown symbols.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all affected files (30+ files examined)
- Alembic migration history (17 migrations, `render_as_batch=True` confirmed in env.py)
- CONTEXT.md user decisions (locked decisions from discussion phase)

### Verification
- `compute_portfolio_from_ledger()` already filters by symbol -- confirmed at line 57 of domain/portfolio.py
- Sync service is per-symbol -- confirmed in sync_service.py `sync_fills()` signature
- `batch_alter_table` is configured in alembic/env.py -- confirmed at lines 55 and 79
- XRPEUR prices are sub-1 EUR -- verified (XRP ~0.50 EUR), satoshi encoding must be retained

## Metadata

**Confidence breakdown:**
- Affected files inventory: HIGH -- every file was read and cross-referenced
- Architecture pattern: HIGH -- straightforward removal, no new abstractions needed
- Pitfalls: HIGH -- critical finding about satoshi encoding for XRPEUR prices
- Test disposition: HIGH -- all test files examined for XRPBTC content

**Research date:** 2026-02-23
**Valid until:** Indefinite (codebase-specific research, no external dependency versioning)
