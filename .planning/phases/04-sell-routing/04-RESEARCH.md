# Phase 4: Sell Routing - Research

**Researched:** 2026-02-21
**Domain:** Cross-pair sell order routing (Binance API + domain logic + sell allocation)
**Confidence:** HIGH

## Summary

Phase 4 automates the routing of pairing sells to the pair that maximizes EUR proceeds. The core mechanism already exists in Phase 3: `compute_dual_route_comparison()` is a pure domain function that computes net EUR proceeds for both routes (XRPEUR direct vs XRPBTC->BTCEUR indirect) and recommends the higher one. Phase 4 must wire this comparison into the execution path (`create_limit_sell_for_pairing`), select the winning symbol at order placement time, and ensure downstream sell allocation works correctly regardless of which pair was chosen.

The codebase is well-prepared for this change. The `OrderService.create_limit_sell_for_pairing()` method already handles symbol from the pairing, the `process_sell_fill_for_pairing()` already allocates against all pairing lots regardless of their individual symbols, and the `SellAllocationDB.realized_pnl_quote` already computes P&L in the quote currency of the sell event's symbol. The main work is: (1) fetching live prices for both routes at execution time, (2) computing the route comparison and selecting the winner, (3) placing the order on the winning symbol with correct precision, (4) persisting routing metadata for auditability, and (5) ensuring EUR-normalized P&L on allocation.

**Primary recommendation:** Extend `create_limit_sell_for_pairing()` to accept route comparison data, determine the optimal symbol, and place the order on that symbol. Add routing metadata columns to `OrderDB` or `PairingDB`. Reuse `compute_dual_route_comparison()` from Phase 3 for the actual route selection logic.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ROUTE-01 | Bei Pairing-Execution berechnet System EUR-Erloes fuer beide Routes (XRP/EUR direkt vs XRP/BTC x BTC/EUR) | `compute_dual_route_comparison()` exists (Phase 3), needs integration into execution flow with live prices from `BinancePublicClient.get_ticker_price()` or `BinanceService.get_current_price()` |
| ROUTE-02 | Sell-Order wird automatisch auf das Pair mit hoeherem EUR-Erloes geroutet | `create_limit_sell_for_pairing()` already uses `symbol` from pairing; needs to override with routed symbol + correct precision from `symbol_registry` |
| ROUTE-03 | Routing-Entscheidung wird geloggt (gewaehltes Pair, Preise, Erloes-Differenz) | New routing metadata on `PairingDB` (JSON column) or `OrderDB`; `DualRouteComparison` dataclass provides all needed fields |
| ROUTE-04 | Cross-Pair Sell-Allocation: Sell-Fills von geroutetem Pair allokieren gegen alle XRP-Lots mit EUR-normalisierter P&L | `process_sell_fill_for_pairing()` already allocates against pairing lots (cross-symbol). `realized_pnl_quote` currently uses sell event's quote currency; needs EUR-normalization for cross-pair pairings |
</phase_requirements>

## Architecture Patterns

### Current Execution Flow (Before Phase 4)

```
Frontend (PairingExistingTab)
  -> executePairing(userId, pairingId, marketPrice, feeBuffer, customSellPrice)
  -> POST /api/pairing/{userId}/{pairingId}/execute?market_price=X
  -> execute_pairing_endpoint()
    -> order_service.create_limit_sell_for_pairing(db, userId, pairingId, marketPrice, ...)
      -> 1. Load pairing (get_pairing_by_id)
      -> 2. Lock pairing (DRAFT -> LOCKED, or verify already LOCKED)
      -> 3. Validate lots, determine symbol = pairing_db.symbol
      -> 4. Compute target price = market_price * (1 + fee_buffer)
      -> 5. Compute total qty from all items
      -> 6. Check max order value
      -> 7. Generate idempotent client_order_id
      -> 8. Create PENDING OrderDB record (linked_pairing_id)
      -> 9. Call Binance API: create_order(symbol=pairing.symbol, ...)
      -> 10. Update order to OPEN
      -> 11. Mark pairing EXECUTED (execute_pairing)
      -> Return {status, pairing_id, order, count, total_qty}
```

### Key Insight: Where Route Selection Must Happen

Route selection must occur between steps 3 and 4 in `create_limit_sell_for_pairing()`:
- After lots are validated but before the order is placed
- The method already has access to the pairing's `base_asset` to detect cross-pair mode
- Prices for both routes must be fetched (or provided) at this point
- The winning symbol determines: price precision, order price, order symbol

### Recommended New Flow (Phase 4)

```
Frontend (PairingExistingTab)
  -> executePairing(userId, pairingId, marketPrice, feeBuffer, customSellPrice)
  -> POST /api/pairing/{userId}/{pairingId}/execute?market_price=X
  -> execute_pairing_endpoint()
    -> order_service.create_limit_sell_for_pairing(db, userId, pairingId, marketPrice, ...)
      -> 1. Load pairing
      -> 2. Lock pairing
      -> 3. Validate lots
      -> **3a. IF cross-pair (pairing.base_asset is not None):**
      ->   - Fetch live prices: XRPEUR + XRPBTC + BTCEUR via BinanceService
      ->   - Call compute_dual_route_comparison(total_qty, ...)
      ->   - selected_symbol = drc.recommended_route ("XRPEUR" or "XRPBTC")
      ->   - selected_price = corresponding price
      ->   - Build routing_decision dict for logging
      -> **3b. ELSE (single-pair):**
      ->   - symbol = pairing.symbol (unchanged)
      -> 4. Compute target price using selected symbol's market price
      -> 5. Get precision from symbol_registry for selected_symbol
      -> 6. Compute total qty, check max order value
      -> 7. Generate client_order_id (includes selected_symbol)
      -> 8. Create PENDING OrderDB (with selected_symbol + routing metadata)
      -> 9. Call Binance API with selected_symbol
      -> 10. Update order to OPEN
      -> 11. Mark pairing EXECUTED + persist routing_decision
      -> Return {status, pairing_id, order, routing_decision, ...}
```

### Pattern: Routing as Enrichment, Not Restructuring

The route selection is an enrichment step that overrides the `symbol` used for order placement. The rest of the execution flow (lock, validate, place order, mark executed) remains structurally identical. This minimizes the change surface.

### Project Structure: Modified Files

```
backend/
  app/
    domain/
      pairing.py          # compute_dual_route_comparison() -- EXISTING, no changes needed
      models.py            # RoutingDecision dataclass -- NEW
      orders.py            # compute_pairing_order_params() -- extend with symbol param
    services/
      order_service.py     # create_limit_sell_for_pairing() -- main routing logic
      pairing_service.py   # execute_pairing() -- persist routing decision
    db/
      models.py            # PairingDB routing columns OR OrderDB routing columns
    api/
      routes/pairing.py    # execute endpoint -- return routing info
  alembic/
    versions/              # Migration for routing columns
  tests/
    test_sell_routing.py   # NEW: routing decision tests
    test_portfolio_cross_pair.py  # NEW (already in working tree)
frontend/
  src/
    api/client.js          # executePairing -- return routing info to caller
    components/
      PairingExistingTab.jsx  # Show routing result in success message
```

## Detailed Analysis of Key Code Paths

### 1. create_limit_sell_for_pairing() -- The Main Change Target

**File:** `backend/app/services/order_service.py` (lines 204-374)

Current behavior:
- Takes `market_price` (single price in the pairing's quote currency)
- Uses `symbol = pairing_db.symbol` (line 263, derived from first lot at pairing creation)
- Computes target price, qty, and places order on that symbol

For Phase 4, this method needs:
- Access to `BinanceService` (already available as `self.binance_service`)
- Detection of cross-pair mode: `pairing_db.base_asset is not None`
- Price fetching for both routes
- Route comparison and symbol selection
- Correct precision for the selected symbol (`get_price_precision(selected_symbol)`, `get_base_precision(selected_symbol)`)

**Critical detail:** The `client_order_id` includes the price and must use the selected symbol's price. The format `{userId}_pairing_{id}_{int(target_price)}_{version}` already works since it encodes the target price, which will differ per route.

### 2. compute_dual_route_comparison() -- Reusable Pure Function

**File:** `backend/app/domain/pairing.py` (lines 269-336)

Already computes everything ROUTE-01 needs:
- `route_direct`: XRPEUR gross/fees/net EUR proceeds
- `route_indirect`: XRPBTC->BTCEUR gross/fees/net EUR proceeds (compounded fees)
- `recommended_route`: "XRPEUR" or "XRPBTC" (whichever has higher net)
- `eur_difference`: absolute difference

Returns `DualRouteComparison` dataclass with full `RouteDetails` for each route.

**No changes needed** to this function -- it can be called at execution time with live prices.

### 3. process_sell_fill_for_pairing() -- Sell Allocation for Routed Orders

**File:** `backend/app/services/lot_service.py` (lines 442-592)

Current behavior:
- Loads pairing items by `pairing_id`
- Loads pairing lots (all symbols via `_get_base_symbols_for_sell_event`)
- Allocates sell qty to pairing lots first, then overflow via user strategy
- `realized_pnl_quote` = `net_proceeds_per_base * qty - cost_per_unit * qty`
  - `net_proceeds_per_base` comes from the sell event's price (in the sell event's quote currency)
  - `cost_per_unit` = `lot.break_even` (in the LOT's quote currency)

**ROUTE-04 concern: Quote currency mismatch for realized P&L**

If we sell on XRPBTC but the lot was purchased on XRPEUR:
- `sell_event.price` is in BTC (e.g., 0.00002345 BTC)
- `lot.break_even` is in EUR (e.g., 2.15 EUR)
- `realized_pnl_quote = sell_price_BTC * qty - break_even_EUR * qty` -- **this is wrong** (mixing BTC and EUR)

Conversely, if we sell on XRPEUR but the lot was purchased on XRPBTC:
- `sell_event.price` is in EUR (e.g., 2.20 EUR)
- `lot.break_even` is in BTC (e.g., 0.00002200 BTC)
- Same mismatch problem

**Solution:** For cross-pair pairing sell allocation, `realized_pnl_quote` must use EUR-normalized values:
- `net_proceeds_eur = net_proceeds_per_base_in_sell_quote * qty * quote_to_eur_rate` (if sell is on BTC pair) or directly EUR if sell is on EUR pair
- `cost_eur = lot.cost_eur / lot.qty_base_initial * qty` (already available from Phase 2)
- `realized_pnl_eur = net_proceeds_eur - cost_eur`

This is the most complex part of Phase 4. The existing `_allocate_qty_to_lots()` function uses `lot.break_even` (which is in the lot's native quote currency) and `net_proceeds_per_base` (which is in the sell event's quote currency). For cross-pair scenarios, these are in different currencies.

**Approach:** Modify `process_sell_fill_for_pairing()` to detect cross-pair scenario (pairing has `base_asset`), and when cross-pair, override the P&L computation to use EUR-normalized values. The `cost_eur` is already on every lot (from Phase 2). The sell proceeds need EUR conversion: if selling on XRPBTC, multiply by BTC/EUR rate at fill time.

### 4. Price Fetching at Execution Time

The system needs current prices for both routes. Options:

**Option A: Use BinanceService.get_current_price()**
- Already exists, uses the authenticated client
- `self.binance_service.get_current_price("XRPEUR")`
- `self.binance_service.get_current_price("XRPBTC")`
- `self.binance_service.get_current_price("BTCEUR")`
- Pro: Consistent with existing patterns, uses retry decorator
- Con: 3 sequential API calls add ~300-500ms latency

**Option B: Use BinancePublicClient.get_ticker_price()**
- Singleton, no API key needed
- Same latency concern

**Option C: Accept prices from frontend (like simulation)**
- Frontend already has WebSocket prices for XRPEUR, XRPBTC, BTCEUR
- Could pass them to execution endpoint
- Pro: No additional API calls
- Con: Prices may be stale, race condition between frontend price and actual fill price

**Recommendation: Option A (backend fetches prices)**
- The backend should always fetch fresh prices at execution time for accuracy
- Frontend-provided prices are useful for simulation/preview but not for execution decisions
- The routing decision should be based on prices as close to order placement time as possible
- The latency of 3 ticker fetches is acceptable for a one-time execution action

### 5. OrderDB Model -- Routing Metadata

The `OrderDB` model already has:
- `symbol` (String) -- can be set to the routed symbol
- `linked_pairing_id` (FK to pairings.id) -- already links to pairing
- `raw_response` (JSON) -- could hold routing info but is for Binance response

For routing metadata logging (ROUTE-03), two options:

**Option A: Add routing columns to PairingDB**
- `routing_decision_json` (JSON column) -- stores full routing decision
- Stored once per pairing execution
- Natural location since routing is a pairing-level decision
- Pro: Clean separation (pairing = routing, order = execution)

**Option B: Add routing columns to OrderDB**
- `routing_decision_json` (JSON column)
- Pro: Tied to the specific order
- Con: Routing is a pairing concern, not an order concern

**Recommendation: Option A (PairingDB)**
- The routing decision applies to the entire pairing execution
- PairingDB already has `executed_at` for the execution timestamp
- Add `routing_decision_json` JSON column to PairingDB
- Content: `{selected_route, xrpeur_price, xrpbtc_price, btceur_price, direct_net_eur, indirect_net_eur, eur_difference, decision_timestamp}`

### 6. Symbol Precision for Routed Orders

The `symbol_registry` already provides correct precision per symbol:

| Symbol | base_precision | price_precision |
|--------|---------------|-----------------|
| XRPEUR | 2 | 4 |
| XRPBTC | 2 | 8 |
| BTCEUR | 8 | 2 |

When routing to XRPBTC instead of XRPEUR:
- Base quantity precision stays the same (both XRP, precision=2)
- Price precision changes from 4 to 8 decimal places
- `target_price_rounded` and `stop_price` must use the selected symbol's precision

The current code in `create_limit_sell_for_pairing()` already gets precision dynamically:
```python
price_prec = get_price_precision(symbol)
base_prec = get_base_precision(symbol)
```
Just need to ensure `symbol` is set to the routed symbol before these calls.

### 7. Frontend Execution Flow

**Current:** `PairingExistingTab.handleExecute()` calls `executePairing(userId, pairingId, marketPrice, 0.002, sellPrice)`.

The frontend currently passes `marketPrice` which is the active symbol's market price. For cross-pair routing, the backend will determine the optimal route server-side, so no frontend changes are required for the routing decision itself.

The frontend should display the routing result after execution:
- Success message: "Pairing ausgefuehrt: 1 Order auf XRPBTC platziert (Route spart 0.12 EUR vs XRPEUR)"
- The execution response should include routing info

### 8. XRPBTC Indirect Route: Max Order Value Check

The current max order value check uses `order_value = total_qty_rounded * target_price_rounded`. For XRPBTC this would give value in BTC, not EUR. For accurate max-value checking on the indirect route, the order value should be EUR-equivalent: `total_qty * xrpbtc_price * btceur_price`.

### 9. Idempotency for Routed Orders

The `client_order_id` format for pairings: `{userId}_pairing_{safe_id}_{int(target_price)}_{version}`.

For XRPBTC routing, `int(target_price)` would be 0 (since XRPBTC prices are < 1). This would cause collisions.

**Fix:** Include the symbol in the client_order_id or use a different price encoding. For example: `{userId}_p_{safe_id}_{symbol}_{version}` with a hash-based approach, or encode the price with more precision.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Route comparison math | Custom EUR proceeds computation | `compute_dual_route_comparison()` from domain/pairing.py | Already correct, tested, handles compounded fees |
| Symbol precision | Hardcoded precision values | `get_price_precision()` / `get_base_precision()` from symbol_registry | Single source of truth, already used everywhere |
| Live price fetching | New price fetching mechanism | `BinanceService.get_current_price()` | Already has retry decorator, tested |
| Idempotent order ID | New ID generation | Extend existing `client_order_id` pattern | Proven pattern, works with Binance's 36-char limit |

## Common Pitfalls

### Pitfall 1: Quote Currency Mismatch in Realized P&L
**What goes wrong:** Sell on XRPBTC produces `sell_event.price` in BTC. Lot's `break_even` is in EUR (for XRPEUR lots). Computing `realized_pnl = sell_price_BTC * qty - break_even_EUR * qty` gives nonsensical results.
**Why it happens:** The existing `_allocate_qty_to_lots()` assumes sell event quote currency matches lot quote currency.
**How to avoid:** For cross-pair pairings, compute realized P&L in EUR using `lot.cost_eur` for costs and converting sell proceeds to EUR at the fill-time BTC/EUR rate.
**Warning signs:** Realized P&L values that are wildly wrong (e.g., -0.9999 or +999999).

### Pitfall 2: Price Staleness Between Route Decision and Order Fill
**What goes wrong:** Prices are fetched for route comparison, but by the time the order fills (which may be seconds to hours later for TAKE_PROFIT_LIMIT), the relative price advantage may have reversed.
**Why it happens:** TAKE_PROFIT_LIMIT orders are not market orders -- they wait for a trigger price.
**How to avoid:** This is acceptable behavior for v1. The routing decision is a best-effort optimization. The TAKE_PROFIT_LIMIT price is set at execution time and won't change. Document this as a known limitation.
**Warning signs:** Post-execution analysis showing the non-selected route would have been better.

### Pitfall 3: client_order_id Collision for XRPBTC
**What goes wrong:** `int(target_price)` for XRPBTC is 0 (price ~0.000023 BTC). Multiple pairings would get the same client_order_id prefix, causing "duplicate order" errors.
**Why it happens:** The existing ID format `{user}_{pairing}_{int(price)}_{version}` truncates sub-1 prices to 0.
**How to avoid:** For XRPBTC orders, encode the price differently. Options: use satoshi price (`int(price * 1e8)`), or include the symbol hash, or just use a UUID-based approach for pairing orders.
**Warning signs:** Binance API returning "duplicate clientOrderId" errors on second pairing execution.

### Pitfall 4: Max Order Value Check in Non-EUR Quote
**What goes wrong:** `order_value = qty * price_xrpbtc` gives value in BTC, which is always < max_order_value_eur (1000 EUR). The check becomes meaningless.
**Why it happens:** Max order value is denominated in EUR, but the order price is in BTC.
**How to avoid:** Convert order value to EUR: `order_value_eur = qty * xrpbtc_price * btceur_price` for the validation.
**Warning signs:** Orders that should be rejected by max-value check passing through.

### Pitfall 5: Indirect Route Requires Two Separate Orders
**What goes wrong:** Assuming a single XRPBTC sell order completes the indirect route.
**Why it happens:** The indirect route is XRPBTC -> BTCEUR (two trades). The user gets BTC from selling XRP, then needs to sell BTC for EUR.
**How to avoid:** For v1, the indirect route places only the first leg (XRPBTC sell). The second leg (BTCEUR sell) is explicitly out of scope per REQUIREMENTS.md: "Auto BTC->EUR Konvertierung nach XRPBTC Sell: Separate Trading-Entscheidung". The routing comparison accounts for the two-fee cost but the system only places the first order. The user manually sells BTC for EUR.
**This is a critical design decision.** The dual-route comparison shows the TOTAL EUR proceeds (including the hypothetical BTCEUR conversion), but execution only places the XRPBTC order. The user must then manually convert BTC to EUR.

**UPDATE:** Re-reading REQUIREMENTS.md out-of-scope: "Auto BTC->EUR Konvertierung nach XRPBTC Sell: Separate Trading-Entscheidung". This confirms: Phase 4 only places the first leg.

### Pitfall 6: Sell Allocation for XRPBTC Fills Against XRPEUR Lots
**What goes wrong:** When XRPBTC sell fills come in, the sell event's symbol is XRPBTC. The `_get_base_symbols_for_sell_event()` correctly returns `["XRPEUR", "XRPBTC"]` (all XRP symbols). So the lots will be found. But the `realized_pnl_quote` will be computed in BTC (sell event's quote currency) while lot costs are in different quote currencies.
**How to avoid:** See Pitfall 1 solution -- EUR-normalize the P&L computation for cross-pair pairing allocations.

## Code Examples

### Reusing compute_dual_route_comparison at Execution Time

```python
# In order_service.py, inside create_limit_sell_for_pairing():

if pairing_db.base_asset is not None:
    # Cross-pair: fetch live prices for both routes
    xrpeur_price = self.binance_service.get_current_price("XRPEUR")
    xrpbtc_price = self.binance_service.get_current_price("XRPBTC")
    btceur_price = self.binance_service.get_current_price("BTCEUR")

    # Compute route comparison (pure domain function)
    drc = compute_dual_route_comparison(
        total_base=total_qty,
        xrpeur_price=xrpeur_price,
        xrpbtc_price=xrpbtc_price,
        btceur_price=btceur_price,
        fee_pct=Decimal("0.001"),
    )

    # Select winning route
    selected_symbol = drc.recommended_route  # "XRPEUR" or "XRPBTC"
    if selected_symbol == "XRPEUR":
        effective_market_price = xrpeur_price
    else:
        effective_market_price = xrpbtc_price

    # Build routing decision for logging
    routing_decision = {
        "selected_route": selected_symbol,
        "xrpeur_price": str(xrpeur_price),
        "xrpbtc_price": str(xrpbtc_price),
        "btceur_price": str(btceur_price),
        "direct_net_eur": str(drc.route_direct.net_proceeds_eur),
        "indirect_net_eur": str(drc.route_indirect.net_proceeds_eur),
        "eur_difference": str(drc.eur_difference),
        "timestamp": utcnow().isoformat(),
    }
else:
    # Single-pair: existing behavior
    selected_symbol = symbol
    effective_market_price = market_price
    routing_decision = None

# Continue with selected_symbol for order placement...
price_prec = get_price_precision(selected_symbol)
base_prec = get_base_precision(selected_symbol)
```

### EUR-Normalized Realized P&L for Cross-Pair Allocation

```python
# In lot_service.py, enhanced process_sell_fill_for_pairing():

# Detect cross-pair pairing
pairing_db = db.query(PairingDB).filter(PairingDB.id == pairing_id).first()
is_cross_pair = pairing_db and pairing_db.base_asset is not None

if is_cross_pair:
    # EUR-normalized P&L: use lot.cost_eur and convert sell proceeds to EUR
    sell_quote = get_quote_asset(sell_event_domain.symbol or "XRPEUR")
    if sell_quote == "EUR":
        # Direct EUR sell: proceeds already in EUR
        eur_per_base = net_proceeds_per_base
    else:
        # Indirect sell (e.g., XRPBTC): need BTC/EUR rate at fill time
        # Get from routing decision stored on pairing
        btceur_rate = _get_btceur_rate_for_sell(sell_event_domain, pairing_db)
        eur_per_base = net_proceeds_per_base * btceur_rate

    # Override P&L computation to use EUR
    for lot in pairing_lots_domain:
        cost_eur_per_unit = lot.cost_eur / lot.qty_base_initial  # EUR cost per base
        # realized_pnl_eur = (eur_per_base - cost_eur_per_unit) * qty_allocated
```

### Routing Decision Persistence (Alembic Migration)

```python
# Migration: add routing_decision_json to pairings table
def upgrade():
    with op.batch_alter_table("pairings") as batch_op:
        batch_op.add_column(
            sa.Column("routing_decision_json", sa.JSON, nullable=True)
        )

def downgrade():
    with op.batch_alter_table("pairings") as batch_op:
        batch_op.drop_column("routing_decision_json")
```

## State of the Art

| Old Approach (Pre-Phase 4) | New Approach (Phase 4) | Impact |
|---------------------------|------------------------|--------|
| Pairing execution always uses pairing's symbol | Route comparison selects optimal symbol | Maximizes EUR proceeds automatically |
| No routing metadata logged | Full routing decision persisted as JSON | Auditability for every execution |
| Sell allocation assumes sell and lot in same quote currency | EUR-normalized P&L for cross-pair | Correct realized P&L regardless of sell route |
| Frontend passes market_price for execution | Backend fetches all needed prices | More accurate, no stale-price risk |

## Open Questions

1. **Indirect route: One order or two?**
   - What we know: REQUIREMENTS.md explicitly marks "Auto BTC->EUR Konvertierung nach XRPBTC Sell" as out of scope
   - What's clear: Phase 4 places only the XRPBTC sell order, not the BTCEUR conversion
   - Recommendation: Document clearly that indirect route places first leg only. User converts BTC to EUR separately.

2. **EUR-normalized realized_pnl: Where to store?**
   - What we know: `SellAllocationDB.realized_pnl_quote` is currently in the sell event's quote currency
   - Options: (a) Add `realized_pnl_eur` column to SellAllocationDB, (b) Repurpose `realized_pnl_quote` for cross-pair to always be EUR, (c) Compute EUR P&L on read from lot.cost_eur
   - Recommendation: Option (a) -- add `realized_pnl_eur` as nullable column. Clean separation, no breaking changes. Existing BTC/EUR lots continue to use `realized_pnl_quote` (which is already in EUR for EUR-quoted sells).

3. **Should the execute endpoint accept prices from frontend?**
   - What we know: Phase 3 simulation passes prices from WebSocket via query params
   - Recommendation: Backend fetches prices independently for execution (more accurate). Frontend prices are acceptable for preview/simulation only. This avoids stale-price attacks.

4. **What if both routes produce identical EUR proceeds?**
   - What we know: `compute_dual_route_comparison` returns "XRPEUR" when `net_direct >= net_indirect` (equality goes to direct route)
   - Recommendation: This is correct -- prefer the simpler route (1 fee step vs 2) when proceeds are equal.

## Sources

### Primary (HIGH confidence)
- `backend/app/domain/pairing.py` -- `compute_dual_route_comparison()` implementation, `DualRouteComparison`/`RouteDetails` dataclasses
- `backend/app/services/order_service.py` -- `create_limit_sell_for_pairing()` full implementation
- `backend/app/services/lot_service.py` -- `process_sell_fill_for_pairing()`, `_allocate_qty_to_lots()`
- `backend/app/services/pairing_service.py` -- `execute_pairing()`, `simulate_pairing_execution()`
- `backend/app/db/models.py` -- `OrderDB`, `PairingDB`, `SellAllocationDB` schemas
- `backend/app/symbol_registry.py` -- XRPEUR (price_prec=4, base_prec=2), XRPBTC (price_prec=8, base_prec=2)
- `backend/app/domain/lots.py` -- `_compute_net_proceeds_per_base()`, `_allocate_qty_to_lots()`
- `backend/app/services/binance.py` -- `get_current_price()`, `get_historical_price()`
- `backend/app/domain/models.py` -- `Pairing`, `PairingItem`, `TradeLot` (cost_eur, break_even_eur)
- `.planning/REQUIREMENTS.md` -- ROUTE-01 through ROUTE-04, out of scope items
- `.planning/phases/03-cross-pair-pairing/03-02-SUMMARY.md` -- Phase 3 patterns and decisions

### Secondary (MEDIUM confidence)
- `frontend/src/components/PairingExistingTab.jsx` -- Frontend execution flow
- `frontend/src/api/client.js` -- `executePairing()` API call
- `frontend/src/components/SimulationModal.jsx` -- Dual-route display (Phase 3)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries needed, all tools exist in codebase
- Architecture: HIGH - Clear modification path in well-understood code
- Pitfalls: HIGH - All pitfalls identified through code reading (not speculative)
- Sell allocation P&L: HIGH - Verified by reading `_allocate_qty_to_lots()` line by line

**Research date:** 2026-02-21
**Valid until:** No external dependencies; valid as long as codebase structure unchanged
