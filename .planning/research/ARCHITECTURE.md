# Architecture Research: Cross-Pair Trading Integration

## Research Question

How does cross-pair lot aggregation integrate with the existing 3-tier architecture?

## Layer Assignment

| Concern | Layer | File | Rationale |
|---------|-------|------|-----------|
| EUR cost basis calculation | **Domain** | `lots.py` | Pure computation |
| Historical BTC/EUR rate fetching | **Service** | `sync_service.py` | I/O (Binance API) |
| Persisting `cost_eur` on lot | **Service** | `lot_service.py` | DB write |
| Sell allocation base-asset filter | **Service** | `lot_service.py` | DB query filter |
| Cross-pair P&L normalization | **Domain** | `lots.py`, `pairing.py` | Pure math with pre-computed EUR |
| Sell routing (best pair) | **Service** | `order_service.py` | Requires real-time prices |
| Cross-pair pairing suggestions | **Domain** | `pairing.py` | Pure heuristic on EUR-normalized lots |
| Cross-pair pairing simulation | **Domain** | `pairing.py` | Pure calculation |

**Principle preserved:** Domain layer stays pure (no I/O). Services handle conversion before calling domain functions.

## Data Model Extensions

### TradeLotDB (new columns)
- `cost_eur: Decimal` — EUR-normalized cost (= cost_quote for EUR-quoted lots, converted for BTC-quoted)
- `quote_to_eur_rate: Decimal` — conversion rate at fill time (1.0 for EUR-quoted)
- Migration backfill: `cost_eur = cost_quote`, `rate = 1.0` for all existing lots

### PairingDB (new columns)
- `base_asset: String` — base asset for the pairing (e.g., "XRP")
- `is_cross_pair: Boolean` — true if lots span multiple quote currencies
- Migration backfill: derive `base_asset` from `symbol`, set `is_cross_pair = False`

### Domain TradeLot (new fields)
- `cost_eur: Decimal`, `quote_to_eur_rate: Decimal`
- `break_even_eur` property: `cost_eur / qty_base_initial`

## Data Flow: Cross-Pair Sell Allocation

```
Sell Fill (XRP/EUR)
  → Extract base_asset: get_base_asset("XRPEUR") = "XRP"
  → Get all XRP symbols: get_symbols_for_base_asset("XRP") = ["XRPEUR", "XRPBTC"]
  → Query lots WHERE symbol IN ["XRPEUR", "XRPBTC"] AND qty_base_open > 0
  → Sort by strategy (FIFO/LIFO/HIGHEST_COST)
  → Allocate using EUR-normalized values:
       proceeds_eur = sell_price * qty_allocated  (EUR sell)
       cost_eur = lot.cost_eur / lot.qty_base_initial * qty_allocated
       realized_pnl_eur = proceeds_eur - cost_eur
```

## Data Flow: Cross-Pair Pairing

```
GET /api/pairing/{user_id}/suggestions?base_asset=XRP&market_prices=XRPEUR:0.55,XRPBTC:0.0000065
  → Service: query lots WHERE base_asset_of(symbol) == "XRP"
  → Service: pass EUR-normalized lots + EUR market price to domain
  → Domain: suggest_pairings(lots_eur_normalized, market_price_eur, threshold)
  → Return: pairing suggestions with EUR P&L
```

## Data Flow: Sell Routing

```
POST /api/pairing/{user_id}/{id}/execute
  → Service: fetch real-time XRPEUR + XRPBTC + BTCEUR prices
  → Service: calculate proceeds_eur for each route
  → Service: select best route, create order on that pair
  → Service: log routing decision for auditability
```

## Build Order (4 Phases)

### Phase 1: Sell Allocation Fix (independent)
- Add `get_symbols_for_base_asset()` to symbol registry
- Add base-asset filter to all sell allocation queries in lot_service.py
- Tests: sell fills only allocate against same-base-asset lots

### Phase 2: EUR Cost Basis (independent, parallel with Phase 1)
- Add `cost_eur`, `quote_to_eur_rate` to DB + domain models
- Alembic migration with backfill
- Fetch BTC/EUR historical rate during XRP/BTC sync
- Update lot creation for BTC-quoted fills

### Phase 3: Cross-Pair Pairing (requires Phase 1 + 2)
- Add `base_asset`, `is_cross_pair` to Pairing model
- Update pairing heuristic for EUR-normalized P&L
- Update pairing service to query by base-asset
- Cross-pair simulation with dual-route comparison
- Frontend pairing UI for mixed-pair lots

### Phase 4: Sell Routing + Execution (requires Phase 3)
- Real-time price comparison for route selection
- Order creation on selected pair
- Cross-pair sell allocation P&L normalization
- Frontend routing display in simulation modal

## What Does NOT Change

- Ledger structure (append-only, event-sourced)
- Per-symbol portfolio computation
- Per-symbol Binance sync flow
- Order tracking, reconciliation, orderblock, sentiment, combined score
- Frontend routing (`/s/:symbol`)
- WebSocket fill handling

## New Invariants

1. **Cross-pair EUR normalization:** `cost_eur` computed once at fill time, never recomputed
2. **Sell allocation base-asset scope:** Sells allocate against ALL open lots of the same base asset
3. **Cross-pair pairing constraint:** Only lots with the same base asset can be cross-pair paired
4. **Sell routing determinism:** Best-pair selection is logged and auditable

---

*Generated: 2026-02-20*
