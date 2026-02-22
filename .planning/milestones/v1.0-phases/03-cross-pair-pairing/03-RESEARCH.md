# Phase 3: Cross-Pair Pairing - Research

**Researched:** 2026-02-20
**Domain:** Cross-pair pairing logic, EUR-normalized P&L, dual-route simulation, frontend pairing UI extension (Python/FastAPI/React)
**Confidence:** HIGH

## Summary

Phase 3 extends the pairing system to combine XRP lots from different trading pairs (XRPEUR and XRPBTC) into a single pairing. This requires three fundamental changes: (1) the pairing heuristic must accept lots from multiple symbols sharing the same base asset, using EUR-normalized cost (`cost_eur`) for P&L calculations instead of `cost_quote`, (2) the pairing data model must use `base_asset` to identify cross-pair pairings rather than a single `symbol`, and (3) the simulation must show a dual-route comparison (sell via XRPEUR direct vs. sell via XRPBTC then convert BTC to EUR).

Phase 1 (sell allocation symbol isolation) and Phase 2 (EUR cost basis) are complete prerequisites. Phase 1 established `get_symbols_for_base_asset()` and base-asset-scoped lot filtering. Phase 2 added `cost_eur` and `quote_to_eur_rate` to every TradeLot, making EUR-normalized cost comparison possible across different quote currencies. The cross-pair pairing builds directly on these two foundations.

The key architectural insight is that the pairing domain logic (`domain/pairing.py`) currently uses `lot.break_even * lot.qty_base_open` for cost calculations, which is in the lot's native quote currency. For cross-pair pairings, this must switch to `lot.cost_eur`-based calculations (or equivalently `lot.break_even_eur * lot.qty_base_open`). The existing `Pairing` dataclass uses a `symbol` field; for cross-pair pairings, this must be augmented with a `base_asset` field. The `PairingDB` table needs a corresponding `base_asset` column. The simulation currently computes proceeds as `total_base * market_price` -- for cross-pair pairings, it must compute EUR proceeds for both sell routes (XRPEUR and XRPBTC) and compare them.

**Primary recommendation:** Extend `Pairing` model with `base_asset` field, modify `suggest_pairings()` to accept multi-symbol lots and use `cost_eur` for P&L, extend `simulate_pairing()` with dual-route comparison, add `base_asset` column to `PairingDB` via Alembic migration, update frontend pairing UI with pair-of-origin badges and dual-route display.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PAIR-01 | Pairing-Heuristik akzeptiert Lots aus XRPEUR und XRPBTC in einem Pairing | Modify `suggest_pairings()` to accept lots from multiple symbols sharing the same base asset. Use `cost_eur` for P&L calculation. Service layer queries lots by base asset (using `get_symbols_for_base_asset()`). See "Architecture Patterns - Pattern 1". |
| PAIR-02 | P&L-Berechnung in Pairing-Heuristik verwendet EUR-normalisierte Kostenbasis (`cost_eur`) | Replace `lot.break_even * lot.qty_base_open` with `lot.cost_eur` in pairing P&L calculations. Requires all lots to have `cost_eur` populated (Phase 2 guarantee). Market price must also be EUR-normalized. See "Architecture Patterns - Pattern 2". |
| PAIR-03 | Pairing-Modell verwendet `base_asset` statt `symbol` fuer Cross-Pair-Pairings | Add `base_asset` field to `Pairing` dataclass and `PairingDB` table. Cross-pair pairings set `base_asset` (e.g., "XRP") and `symbol` to None or a sentinel. Single-pair pairings retain both `symbol` and `base_asset`. See "Architecture Patterns - Pattern 3". |
| PAIR-04 | Cross-Pair Simulation zeigt EUR-P&L mit Dual-Route-Vergleich (XRPEUR vs XRPBTC x BTCEUR) | Extend `simulate_pairing()` to compute EUR proceeds for both routes. Requires current prices for XRPEUR and XRPBTC + BTCEUR. Return both route calculations in simulation response. See "Architecture Patterns - Pattern 4". |
| PAIR-05 | Frontend Pairing-UI unterstuetzt gemischte XRP/EUR + XRP/BTC Lots mit Pair-Herkunft-Badge | Add `symbol` (pair-of-origin) badge on each lot within a cross-pair pairing card. Show dual-route comparison in SimulationModal. PairingPanel queries lots across symbols for the same base asset. See "Architecture Patterns - Pattern 5". |
</phase_requirements>

## Standard Stack

### Core (already in project -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy 2 | pinned in requirements.txt | ORM column addition + migration | Already used everywhere |
| Alembic | pinned in requirements.txt | Schema migration (`render_as_batch=True`) | All prior migrations use this |
| pytest | pinned in requirements.txt | Unit tests for cross-pair pairing logic | 18+ existing test files |
| React 19 | pinned in package.json | Frontend UI updates | Already used for all components |
| TanStack Query | pinned in package.json | Data fetching for dual-route prices | Already used for all API calls |

### Supporting
No new libraries needed. This phase extends existing infrastructure.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `base_asset` column on PairingDB | Derive from lots at query time | Would require join + aggregation on every pairing query. Persisted `base_asset` is simpler and O(1). |
| EUR-normalized P&L in domain | Compute EUR P&L in service layer | Domain layer already has `cost_eur` on TradeLot. Computing in domain keeps it pure and testable. |
| Separate "cross-pair" pairing type | Boolean `is_cross_pair` flag | `base_asset` is more expressive (supports future multi-pair assets) and cleaner than a boolean. |
| Fetching BTCEUR price server-side for dual-route | Frontend computes from existing price data | Frontend already has live prices for all symbols via WebSocket. Server-side would add latency. However, simulation endpoint needs it for deterministic comparison, so server-side is correct for simulation. |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Changes Map

```
backend/app/
  domain/models.py                # MODIFY: add base_asset to Pairing, PairingItem gets lot_symbol
  domain/pairing.py               # MODIFY: suggest_pairings() accepts multi-symbol lots, uses cost_eur
  db/models.py                    # MODIFY: add base_asset to PairingDB
  services/pairing_service.py     # MODIFY: query lots by base_asset, pass prices for dual-route
  api/routes/pairing.py           # MODIFY: accept base_asset param, return dual-route simulation
backend/alembic/versions/
  XXXX_add_pairing_base_asset.py  # NEW: migration adds base_asset column
backend/tests/
  test_cross_pair_pairing.py      # NEW: tests for cross-pair pairing logic
frontend/src/
  components/PairingPanel.jsx     # MODIFY: support cross-pair lot selection + pair-of-origin badges
  components/PairingExistingTab.jsx # MODIFY: show pair-of-origin badges, dual-route in simulation
  components/SimulationModal.jsx  # MODIFY: add dual-route comparison section
  api/client.js                   # MODIFY: pass base_asset to suggestion/create endpoints
```

### Pattern 1: Multi-Symbol Lot Loading for Pairing Suggestions (PAIR-01)

**What:** The pairing suggestion service currently queries lots by a single `symbol`. For cross-pair pairings, it must query lots by `base_asset` -- i.e., all XRP lots regardless of whether they are XRPEUR or XRPBTC.

**Current code (pairing_service.py `get_pairing_suggestions()`):**
```python
# Current: Filters by single symbol
lots_db = db.query(TradeLotDB).filter(
    TradeLotDB.user_id == user_id,
    TradeLotDB.symbol == symbol,  # <-- single symbol
    TradeLotDB.qty_base_open > 0
).all()
```

**New approach:**
```python
from app.symbol_registry import get_symbols_for_base_asset

def get_pairing_suggestions(
    db: Session,
    user_id: str,
    market_price_eur: Decimal,  # Must be EUR-denominated
    threshold_pct: Decimal = Decimal("0.05"),
    base_asset: str | None = None,  # NEW: e.g., "XRP" for cross-pair
    symbol: str = "BTCEUR",  # Backward-compatible
) -> List[dict]:
    if base_asset:
        # Cross-pair mode: load all lots for this base asset
        symbols = get_symbols_for_base_asset(base_asset)
        lots_db = db.query(TradeLotDB).filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.symbol.in_(symbols),
            TradeLotDB.qty_base_open > 0
        ).order_by(TradeLotDB.created_at.asc()).all()
    else:
        # Single-symbol mode (backward-compatible)
        lots_db = db.query(TradeLotDB).filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.symbol == symbol,
            TradeLotDB.qty_base_open > 0
        ).order_by(TradeLotDB.created_at.asc()).all()
```

**Key constraint:** When `base_asset` is provided, the `market_price_eur` parameter MUST be in EUR. The service layer is responsible for ensuring this (for XRPBTC lots, the caller must provide the EUR-equivalent XRP price, not the BTC-denominated price).

### Pattern 2: EUR-Normalized P&L in Pairing Heuristic (PAIR-02)

**What:** The `suggest_pairings()` domain function currently computes P&L using `lot.break_even * lot.qty_base_open` (cost in quote currency) and `market_price * lot.qty_base_open` (value in quote currency). For cross-pair pairings where lots have different quote currencies, all calculations must use EUR.

**Current cost calculation:**
```python
# Current: Uses break_even (in quote currency)
items = [PairingItem(
    lot_id=winner.id,
    qty_base=winner.qty_base_open,
    cost_quote=winner.break_even * winner.qty_base_open  # <-- in quote currency
)]
current_cost = items[0].cost_quote
current_value = market_price * items[0].qty_base  # <-- assumes market_price is in same currency
```

**New approach for cross-pair mode:**
```python
def suggest_pairings(
    lots: List[TradeLot],
    market_price_eur: Decimal,  # EUR price of the base asset
    threshold_pct: Decimal = Decimal("0.05"),
    use_eur_cost: bool = False,  # NEW: True for cross-pair mode
) -> List[Pairing]:
    # ...
    for lot in lots:
        if use_eur_cost:
            # Cross-pair: use EUR-normalized cost
            lot_cost = lot.cost_eur  # Must not be None
            lot_value = market_price_eur * lot.qty_base_open
        else:
            # Single-pair: use native quote currency (backward-compatible)
            lot_cost = lot.break_even * lot.qty_base_open
            lot_value = market_price_eur * lot.qty_base_open
```

**PairingItem extension:**
```python
@dataclass
class PairingItem:
    lot_id: str
    qty_base: Decimal
    cost_quote: Decimal  # Existing: cost in lot's native quote currency
    cost_eur: Decimal | None = None  # NEW: EUR-normalized cost (for cross-pair)
    lot_symbol: str | None = None  # NEW: pair-of-origin (e.g., "XRPEUR" or "XRPBTC")
```

**Critical validation:** If `use_eur_cost=True`, all lots MUST have `cost_eur` populated (not None). The function should raise `ValueError` if any lot has `cost_eur is None`. This is guaranteed by Phase 2, but an explicit check prevents silent bugs.

### Pattern 3: Pairing Model Extension with base_asset (PAIR-03)

**Domain model (`domain/models.py`):**
```python
@dataclass
class Pairing:
    id: str
    items: List[PairingItem]
    threshold_pct: Decimal
    status: PairingStatus = PairingStatus.DRAFT
    created_at: Optional[datetime] = None
    symbol: str = "BTCEUR"  # Existing: primary symbol (for single-pair)
    base_asset: str | None = None  # NEW: base asset for cross-pair (e.g., "XRP")
```

**DB model (`db/models.py`):**
```python
class PairingDB(Base):
    __tablename__ = "pairings"
    # ... existing columns ...
    base_asset = Column(String, nullable=True)  # NEW: "XRP" for cross-pair, None for single-pair
```

**Semantics:**
- `base_asset = None`: Traditional single-pair pairing. `symbol` is authoritative.
- `base_asset = "XRP"`: Cross-pair pairing. Lots may come from XRPEUR and/or XRPBTC. The `symbol` field should still be set (to the primary/intended sell symbol, or to the first lot's symbol), but `base_asset` is the canonical identifier.
- For backward compatibility, existing pairings get `base_asset = NULL` in migration.

**Migration pattern:**
```python
def upgrade():
    with op.batch_alter_table("pairings") as batch_op:
        batch_op.add_column(sa.Column(
            "base_asset",
            sa.String(),
            nullable=True,
        ))
    # Optional backfill: derive base_asset from symbol for existing pairings
    # e.g., BTCEUR -> BTC, XRPEUR -> XRP
    # This is optional since existing pairings are all single-pair
```

**PairingItemDB extension:**
```python
class PairingItemDB(Base):
    # ... existing columns ...
    cost_eur = Column(Numeric(precision=20, scale=10), nullable=True)  # NEW: EUR-normalized cost
    lot_symbol = Column(String, nullable=True)  # NEW: pair-of-origin for display
```

### Pattern 4: Dual-Route Simulation (PAIR-04)

**What:** For cross-pair pairings, the simulation must show EUR proceeds for two routes:
1. **XRPEUR direct:** Sell XRP on XRPEUR market. Proceeds = `qty * xrpeur_price * (1 - fee)`.
2. **XRPBTC indirect:** Sell XRP on XRPBTC market for BTC, then sell BTC on BTCEUR for EUR. Proceeds = `qty * xrpbtc_price * btceur_price * (1 - fee)^2`.

**Simulation extension:**
```python
@dataclass
class DualRouteComparison:
    """Comparison of two sell routes for cross-pair pairings."""
    route_direct: RouteDetails  # XRPEUR
    route_indirect: RouteDetails  # XRPBTC -> BTCEUR
    recommended_route: str  # "XRPEUR" or "XRPBTC"
    eur_difference: Decimal  # How much more/less the recommended route yields

@dataclass
class RouteDetails:
    symbol: str  # "XRPEUR" or "XRPBTC"
    price: Decimal  # Sell price on this market
    gross_proceeds_eur: Decimal  # Before fees, in EUR
    fees_eur: Decimal
    net_proceeds_eur: Decimal  # After fees, in EUR
    conversion_rate: Decimal | None  # BTC/EUR rate for indirect route, None for direct
```

**Service layer must provide:**
- XRPEUR current price (from `market_price` parameter or Binance API)
- XRPBTC current price + BTCEUR current price (for the indirect route calculation)
- The endpoint accepts multiple prices or the service fetches them

**API design option (recommended):**
```python
@router.get("/{user_id}/simulate/{pairing_id}")
def simulate(
    user_id: str,
    pairing_id: str,
    market_price: float,  # Primary market price (XRPEUR for EUR, or base-asset EUR price)
    xrpbtc_price: float | None = None,  # NEW: optional, for dual-route
    btceur_price: float | None = None,  # NEW: optional, for dual-route
    # ... existing params ...
):
```

When `xrpbtc_price` and `btceur_price` are provided, the response includes a `dual_route_comparison` section. When omitted, only single-route simulation is returned (backward-compatible).

### Pattern 5: Frontend Cross-Pair UI (PAIR-05)

**What:** The frontend PairingPanel needs to:
1. Show pair-of-origin badges (XRPEUR / XRPBTC) on each lot chip within a pairing card
2. Allow cross-pair lot selection from the LotsTable (lots from both XRPEUR and XRPBTC routes)
3. Show dual-route comparison in SimulationModal

**Pair-of-origin badge on lot chips:**
```jsx
// In PairingPanel.jsx and PairingExistingTab.jsx
{p.items.map((item) => (
  <span key={item.lot_id} className="lot-chip" title={item.lot_id}>
    {item.lot_symbol && (
      <span className={`pair-badge pair-${item.lot_symbol.toLowerCase()}`}>
        {item.lot_symbol}
      </span>
    )}
    {item.lot_id.slice(0, 8)}...
  </span>
))}
```

**Dual-route comparison in SimulationModal:**
```jsx
{simulationData.dual_route_comparison && (
  <div className="dual-route-section">
    <h4>Verkaufsrouten-Vergleich</h4>
    <div className="route-cards">
      <RouteCard route={simulationData.dual_route_comparison.route_direct} />
      <RouteCard route={simulationData.dual_route_comparison.route_indirect} />
    </div>
    <div className="route-recommendation">
      Empfohlen: {simulationData.dual_route_comparison.recommended_route}
      (+ {formatEUR(simulationData.dual_route_comparison.eur_difference)})
    </div>
  </div>
)}
```

**Cross-pair suggestion flow:**
The suggestion endpoint needs a `base_asset` parameter. When the user is on a symbol route (e.g., `/s/XRPEUR/lots`), the frontend can offer a "Cross-Pair-Modus" toggle that:
1. Changes the suggestion query from `symbol=XRPEUR` to `base_asset=XRP`
2. Provides both XRPEUR and XRPBTC prices for dual-route simulation
3. Badges lots with their pair-of-origin

**Important UX consideration (from STATE.md):** "Frontend UX for mixed-pair pairings needs wireframe during Phase 3 planning." The simplest approach is a toggle in the PairingPanel that switches between single-pair and cross-pair mode. Cross-pair mode loads lots from both symbols and shows pair-of-origin badges.

### Anti-Patterns to Avoid

- **Mixing quote currencies in P&L calculation:** NEVER add `cost_quote` from an XRPEUR lot (in EUR) with `cost_quote` from an XRPBTC lot (in BTC). Always use `cost_eur` for cross-pair calculations.
- **Assuming market_price is always in the lot's quote currency:** For cross-pair pairings, the simulation must use EUR prices regardless of the lot's quote currency.
- **Modifying existing single-pair behavior:** All changes must be backward-compatible. Existing BTCEUR, ETHEUR, XRPEUR pairings must continue to work identically.
- **Computing EUR cost at simulation time instead of using persisted cost_eur:** This would make results non-deterministic (BTC/EUR rate changes). Always use the persisted `cost_eur` from Phase 2.
- **Fetching live prices in domain layer:** Domain functions must remain pure. Price fetching belongs in the service layer; domain functions receive prices as parameters.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Base-asset symbol lookup | String parsing (e.g., "XRP" from "XRPEUR") | `get_base_asset()` + `get_symbols_for_base_asset()` from `symbol_registry` | Already implemented in Phase 1, tested, handles all edge cases |
| EUR cost for lots | Live BTC/EUR conversion at pairing time | `lot.cost_eur` (persisted in Phase 2) | Determinism: cost must be the historical rate, not current rate |
| Multi-symbol lot query | Multiple separate queries per symbol | Single query with `TradeLotDB.symbol.in_(symbols)` | SQLAlchemy `in_()` is simpler and avoids N+1 queries |
| Quote-to-EUR price conversion | New price service | Existing `BinanceService.get_current_price()` or WebSocket price feed | Already available for BTCEUR, XRPEUR, XRPBTC |
| Alembic migration | Raw SQL | `batch_alter_table` + `add_column` | SQLite requires batch mode, project pattern established |

**Key insight:** Phase 1 and Phase 2 built the foundations this phase needs. `get_symbols_for_base_asset()` (Phase 1) provides multi-symbol lookup. `cost_eur` (Phase 2) provides EUR-normalized costs. This phase orchestrates these existing capabilities into the pairing flow.

## Common Pitfalls

### Pitfall 1: Using cost_quote instead of cost_eur for cross-pair P&L
**What goes wrong:** Pairing P&L mixes EUR and BTC costs, producing nonsensical results (e.g., adding 500 EUR + 0.005 BTC = 500.005, which is meaningless).
**Why it happens:** The existing `suggest_pairings()` uses `lot.break_even * lot.qty_base_open` which returns cost in the lot's native quote currency. Copy-pasting this pattern for cross-pair pairings silently produces wrong results.
**How to avoid:** Use `lot.cost_eur` exclusively for cross-pair P&L calculations. Add an assertion/validation that `cost_eur is not None` for all lots in cross-pair mode.
**Warning signs:** Pairings with suspiciously low cost (BTC values treated as EUR) or suspiciously high P&L percentages.

### Pitfall 2: Forgetting to normalize market_price to EUR for cross-pair
**What goes wrong:** The XRPBTC lots are valued at `qty * xrpbtc_price` where `xrpbtc_price` is in BTC, not EUR. Without EUR normalization, the market value comparison is meaningless.
**Why it happens:** The existing code assumes `market_price` is in the same currency as the lot's quote. For cross-pair, there is no single "same currency."
**How to avoid:** For cross-pair pairings, the service layer must provide `market_price_eur` -- the XRP price in EUR (either from XRPEUR price directly, or from XRPBTC * BTCEUR). The domain layer receives only EUR-denominated prices.
**Warning signs:** Cross-pair pairing P&L that differs wildly from what you'd expect looking at individual lots.

### Pitfall 3: Not handling lots with cost_eur = None
**What goes wrong:** If any XRPBTC lot was not backfilled (Phase 2 script not run), `cost_eur` is None. Using it in arithmetic causes `TypeError: unsupported operand type(s) for *: 'NoneType' and 'Decimal'`.
**Why it happens:** Phase 2 made `cost_eur` nullable. If backfill was incomplete, some lots will have `cost_eur = None`.
**How to avoid:** Validate all lots before cross-pair pairing: filter out or reject lots with `cost_eur is None`. Show a warning in the frontend: "X Lots ohne EUR-Kostenbasis -- bitte Backfill ausfuehren."
**Warning signs:** Runtime errors in `suggest_pairings()` or simulation when XRPBTC lots are included.

### Pitfall 4: Breaking existing single-pair pairing flow
**What goes wrong:** Changes to `suggest_pairings()` signature or behavior break the existing BTCEUR/ETHEUR/XRPEUR single-pair flow.
**Why it happens:** Modifying a shared function without maintaining backward compatibility.
**How to avoid:** Make all new parameters optional with defaults that preserve existing behavior (`base_asset=None`, `use_eur_cost=False`). Write tests that verify the existing single-pair flow still works identically.
**Warning signs:** Existing `test_pairing.py` tests fail after changes.

### Pitfall 5: Incorrect fee calculation for dual-route
**What goes wrong:** Dual-route (XRPBTC -> BTCEUR) has TWO fees (one for XRPBTC sell, one for BTCEUR sell), but the simulation only accounts for one.
**Why it happens:** The existing simulation uses `gross_proceeds * fee_pct` once. The indirect route needs two fee applications.
**How to avoid:** For indirect route: `net_eur = qty * xrpbtc_price * btceur_price * (1 - fee_pct)^2`. Clearly document that the indirect route has compounded fees.
**Warning signs:** Indirect route appears more profitable than it actually is.

### Pitfall 6: PairingItemDB.cost_quote confusion in cross-pair context
**What goes wrong:** `PairingItemDB.cost_quote` stores cost in the lot's native quote currency. For cross-pair pairings, summing these values across different quote currencies is meaningless.
**Why it happens:** The existing `create_pairing()` service function computes `cost_quote` from the lot's `cost_quote / qty_base_initial * qty_base`. This is correct per-lot but not summable across currencies.
**How to avoid:** Add `cost_eur` to `PairingItemDB` and use it for cross-pair aggregate calculations. Keep `cost_quote` for backward compatibility and per-lot display.
**Warning signs:** Cross-pair pairing `net_cost()` returns a value in mixed currencies.

## Code Examples

Verified patterns from existing codebase:

### Example 1: Cross-Pair Suggestion Service Function

```python
# In backend/app/services/pairing_service.py

def get_pairing_suggestions(
    db: Session,
    user_id: str,
    market_price: Decimal,
    threshold_pct: Decimal = Decimal("0.05"),
    symbol: str = "BTCEUR",
    base_asset: str | None = None,  # NEW
) -> List[dict]:
    if base_asset:
        # Cross-pair: load all lots for this base asset
        symbols = get_symbols_for_base_asset(base_asset)
        lots_db = (
            db.query(TradeLotDB)
            .filter(
                TradeLotDB.user_id == user_id,
                TradeLotDB.symbol.in_(symbols),
                TradeLotDB.qty_base_open > 0
            )
            .order_by(TradeLotDB.created_at.asc())
            .all()
        )
        # Validate all lots have cost_eur
        lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]
        missing_eur = [lot for lot in lots_domain if lot.cost_eur is None]
        if missing_eur:
            raise ValueError(
                f"{len(missing_eur)} Lots ohne EUR-Kostenbasis. "
                "Bitte Backfill-Script ausfuehren."
            )
        # market_price MUST be EUR-denominated for cross-pair
        pairings = suggest_pairings(
            lots_domain, market_price, threshold_pct, use_eur_cost=True
        )
    else:
        # Existing single-symbol path (unchanged)
        lots_db = (
            db.query(TradeLotDB)
            .filter(
                TradeLotDB.user_id == user_id,
                TradeLotDB.symbol == symbol,
                TradeLotDB.qty_base_open > 0
            )
            .order_by(TradeLotDB.created_at.asc())
            .all()
        )
        lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]
        pairings = suggest_pairings(lots_domain, market_price, threshold_pct)

    return [_pairing_to_dict(pairing, market_price) for pairing in pairings]
```

### Example 2: EUR-Normalized P&L in Domain

```python
# In backend/app/domain/pairing.py - inside suggest_pairings()

def suggest_pairings(
    lots: List[TradeLot],
    market_price: Decimal,
    threshold_pct: Decimal = Decimal("0.05"),
    use_eur_cost: bool = False,  # NEW
) -> List[Pairing]:
    if use_eur_cost:
        # Validate all lots have cost_eur
        for lot in lots:
            if lot.cost_eur is None:
                raise ValueError(f"Lot {lot.id} has no cost_eur -- cannot use EUR-normalized P&L")

    # ... existing sorting logic uses _lot_pnl_pct() helper ...

    def _lot_cost(lot: TradeLot) -> Decimal:
        """Returns lot cost in the appropriate currency."""
        if use_eur_cost:
            return lot.cost_eur  # EUR
        return lot.break_even * lot.qty_base_open  # Quote currency

    def _lot_value(lot: TradeLot) -> Decimal:
        """Returns lot value at market price (always EUR for cross-pair)."""
        return market_price * lot.qty_base_open

    # Use _lot_cost() and _lot_value() throughout instead of direct break_even access
```

### Example 3: Pairing Domain Model Extension

```python
# In backend/app/domain/models.py

@dataclass
class PairingItem:
    lot_id: str
    qty_base: Decimal
    cost_quote: Decimal  # Existing: in lot's native quote currency
    cost_eur: Optional[Decimal] = None  # NEW: EUR-normalized cost
    lot_symbol: Optional[str] = None  # NEW: "XRPEUR" or "XRPBTC"

@dataclass
class Pairing:
    id: str
    items: List[PairingItem]
    threshold_pct: Decimal
    status: PairingStatus = PairingStatus.DRAFT
    created_at: Optional[datetime] = None
    symbol: str = "BTCEUR"  # Primary symbol (backward-compatible)
    base_asset: Optional[str] = None  # NEW: e.g., "XRP" for cross-pair

    @property
    def is_cross_pair(self) -> bool:
        """True if pairing contains lots from multiple symbols."""
        return self.base_asset is not None

    def net_cost_eur(self) -> Optional[Decimal]:
        """EUR-normalized net cost (for cross-pair). None if any item lacks cost_eur."""
        costs = [item.cost_eur for item in self.items]
        if any(c is None for c in costs):
            return None
        return sum(costs, Decimal("0"))
```

### Example 4: Dual-Route Simulation Data

```python
# In backend/app/domain/pairing.py - new function or extension of simulate_pairing()

@dataclass
class RouteDetails:
    symbol: str  # "XRPEUR" or "XRPBTC"
    sell_price: Decimal
    gross_proceeds_eur: Decimal
    fees_eur: Decimal
    net_proceeds_eur: Decimal
    conversion_rate: Optional[Decimal]  # BTC/EUR for indirect, None for direct
    fee_steps: int  # 1 for direct, 2 for indirect

@dataclass
class DualRouteComparison:
    route_direct: RouteDetails
    route_indirect: RouteDetails
    recommended_route: str
    eur_difference: Decimal

def compute_dual_route_comparison(
    total_base: Decimal,
    xrpeur_price: Decimal,
    xrpbtc_price: Decimal,
    btceur_price: Decimal,
    fee_pct: Decimal = Decimal("0.001"),
) -> DualRouteComparison:
    # Route 1: XRPEUR direct
    gross_direct = total_base * xrpeur_price
    fees_direct = gross_direct * fee_pct
    net_direct = gross_direct - fees_direct

    # Route 2: XRPBTC -> BTCEUR (two fees)
    gross_btc = total_base * xrpbtc_price
    fees_btc = gross_btc * fee_pct
    net_btc = gross_btc - fees_btc
    gross_eur = net_btc * btceur_price
    fees_eur = gross_eur * fee_pct
    net_indirect = gross_eur - fees_eur

    recommended = "XRPEUR" if net_direct >= net_indirect else "XRPBTC"
    diff = abs(net_direct - net_indirect)

    return DualRouteComparison(
        route_direct=RouteDetails("XRPEUR", xrpeur_price, gross_direct, fees_direct, net_direct, None, 1),
        route_indirect=RouteDetails("XRPBTC", xrpbtc_price, gross_btc * btceur_price, fees_btc * btceur_price + fees_eur, net_indirect, btceur_price, 2),
        recommended_route=recommended,
        eur_difference=diff,
    )
```

### Example 5: API Endpoint Extension

```python
# In backend/app/api/routes/pairing.py

@router.get("/{user_id}/suggestions")
def get_suggestions(
    user_id: str,
    market_price: float,
    threshold_pct: float = Query(0.05),
    symbol: str = Query("BTCEUR"),
    base_asset: str | None = Query(None, description="Base asset for cross-pair (e.g., 'XRP')"),
    db: Session = Depends(get_db)
):
    _validate_market_price(market_price)
    # If base_asset provided, market_price must be in EUR
    # Validate base_asset if provided
    if base_asset:
        try:
            get_symbols_for_base_asset(base_asset)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unbekanntes Base-Asset: {base_asset}")
    # ... rest of handler ...
```

### Example 6: Frontend Pair-of-Origin Badge

```jsx
// In PairingPanel.jsx / PairingExistingTab.jsx

// Lot chip with pair-of-origin badge
<span key={item.lot_id} className="lot-chip" title={item.lot_id}>
  {item.lot_symbol && item.lot_symbol !== p.symbol && (
    <span className={`pair-origin-badge ${item.lot_symbol.includes('BTC') ? 'pair-btc' : 'pair-eur'}`}>
      {getPairLabel(item.lot_symbol)}
    </span>
  )}
  {item.lot_id.slice(0, 8)}...
</span>
```

```css
/* In PairingPanel.css */
.pair-origin-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  margin-right: 4px;
  font-weight: 600;
}
.pair-origin-badge.pair-eur {
  background: #dbeafe;
  color: #1d4ed8;
}
.pair-origin-badge.pair-btc {
  background: #fef3c7;
  color: #92400e;
}
```

## Scope Boundaries

### Changes IN Scope
1. `domain/models.py`: Add `base_asset` to `Pairing`, `cost_eur` and `lot_symbol` to `PairingItem`
2. `domain/pairing.py`: `suggest_pairings()` with `use_eur_cost` mode, `simulate_pairing()` with dual-route, `compute_dual_route_comparison()`
3. `db/models.py`: Add `base_asset` to `PairingDB`, `cost_eur` and `lot_symbol` to `PairingItemDB`
4. `services/pairing_service.py`: Multi-symbol lot loading, `base_asset` parameter, dual-route prices
5. `api/routes/pairing.py`: `base_asset` query parameter, dual-route price parameters
6. Alembic migration: Add `base_asset` to `pairings`, `cost_eur` and `lot_symbol` to `pairing_items`
7. Frontend PairingPanel.jsx: Cross-pair toggle, pair-of-origin badges
8. Frontend PairingExistingTab.jsx: Pair-of-origin badges on lot chips
9. Frontend SimulationModal.jsx: Dual-route comparison section
10. Frontend api/client.js: `base_asset` parameter for suggestion/create
11. Tests: Cross-pair pairing heuristic, EUR-normalized P&L, dual-route simulation

### Changes OUT of Scope
- No sell routing changes (Phase 4 -- ROUTE-01 through ROUTE-04)
- No order execution changes (orders are still placed on a single symbol)
- No portfolio service changes
- No sell allocation changes (Phase 1 already handles base-asset filtering)
- No Binance API client changes
- No ledger changes
- No settings changes

## Open Questions

1. **Should cross-pair mode be a separate API endpoint or a parameter on the existing endpoint?**
   - What we know: Adding `base_asset` as an optional query parameter is backward-compatible and simpler than a new endpoint.
   - Recommendation: Use optional `base_asset` parameter. When absent, existing single-pair behavior. When present, cross-pair mode with EUR normalization.

2. **How should the frontend handle the cross-pair toggle UX?**
   - What we know: STATE.md notes "Frontend UX for mixed-pair pairings needs wireframe during Phase 3 planning." The simplest approach is a toggle button in PairingPanel.
   - Recommendation: When the active symbol has multiple trading pairs (e.g., XRP has XRPEUR and XRPBTC), show a "Cross-Pair" toggle in the PairingPanel. When activated, it loads lots from all symbols for that base asset and shows pair-of-origin badges. This toggle is only visible for base assets with multiple pairs (currently only XRP).

3. **Should the Pairing.symbol field be set for cross-pair pairings?**
   - What we know: The `symbol` field is used for filtering (`list_pairings`), order creation, and display. Cross-pair pairings don't map to a single symbol.
   - Recommendation: For cross-pair pairings, set `symbol` to the first lot's symbol (or the lot with the largest quantity) as a "primary" symbol, but always use `base_asset` as the canonical identifier. The list endpoint should support filtering by `base_asset` in addition to `symbol`. This preserves backward compatibility.

4. **What happens when XRPBTC price is unavailable for dual-route simulation?**
   - What we know: The WebSocket provides live prices for all known symbols. If XRPBTC price is temporarily unavailable, the dual-route comparison cannot be computed.
   - Recommendation: Make dual-route comparison optional in the simulation response. If prices for the indirect route are not provided, return only the direct route results. Frontend shows "Preise fuer indirekten Route nicht verfuegbar."

5. **Should cross-pair pairings show cost_eur or cost_quote in the pairing card?**
   - What we know: For cross-pair pairings, cost_quote is meaningless (mixed currencies). cost_eur is the comparable metric.
   - Recommendation: Cross-pair pairing cards show `cost_eur` (labeled "Kosten (EUR)"). Single-pair pairing cards continue to show `cost_quote` with the appropriate currency label. The `_pairing_to_dict()` function should include both.

## Sources

### Primary (HIGH confidence)
- Direct code reading: `backend/app/domain/pairing.py` -- `suggest_pairings()` uses `lot.break_even * lot.qty_base_open` for cost. Must switch to `lot.cost_eur` for cross-pair.
- Direct code reading: `backend/app/domain/models.py` -- `Pairing` has `symbol` field, `PairingItem` has `cost_quote`. Both need extension.
- Direct code reading: `backend/app/services/pairing_service.py` -- `get_pairing_suggestions()` queries by single `symbol`. Must support `base_asset` query.
- Direct code reading: `backend/app/db/models.py` -- `PairingDB` has `symbol` column. `PairingItemDB` has `cost_quote`.
- Direct code reading: `backend/app/symbol_registry.py` -- `get_symbols_for_base_asset()` returns all symbols for a base asset (Phase 1).
- Direct code reading: `backend/app/domain/models.py` -- `TradeLot` has `cost_eur` and `break_even_eur` (Phase 2).
- Direct code reading: `backend/app/services/lot_service.py` -- `_lot_db_to_domain()` maps `cost_eur` and `quote_to_eur_rate`.
- Direct code reading: `frontend/src/components/PairingPanel.jsx` -- Uses `activeSymbol` from SymbolContext for queries.
- Direct code reading: `frontend/src/components/SimulationModal.jsx` -- Renders simulation grid, needs dual-route section.
- Direct code reading: `frontend/src/utils/symbolRegistry.js` -- `getBaseLabel()`, `getPairLabel()` available for badge labels.
- Phase 2 research: `02-RESEARCH.md` -- Confirms `cost_eur` pattern and guarantees.
- Phase 1 verification: `01-01-SUMMARY.md` + `VERIFICATION.md` -- Confirms base-asset filtering works.
- STATE.md accumulated decisions: Phase 02 decisions on `cost_eur`, `quote_to_eur_rate`, EUR-auto-detect.

### Secondary (MEDIUM confidence)
- REQUIREMENTS.md -- PAIR-01 through PAIR-05 requirement definitions.
- Existing test patterns: `test_pairing.py` -- 9 tests covering suggest + simulate. New tests should follow same structure.
- Existing test patterns: `test_portfolio_cross_pair.py` -- Cross-pair isolation tests demonstrate the multi-symbol testing approach.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, pure extension of existing infrastructure
- Architecture: HIGH -- direct code reading of all 8+ affected files, patterns from Phase 1 and Phase 2 reused
- Pitfalls: HIGH -- 6 pitfalls identified from code analysis, all have clear prevention strategies
- Migration: HIGH -- simple column addition, existing batch mode pattern
- Frontend: MEDIUM -- UX for cross-pair toggle needs design during planning (flagged in STATE.md)

**Research date:** 2026-02-20
**Valid until:** 2026-04-20 (stable -- no external dependencies, pure codebase analysis)
