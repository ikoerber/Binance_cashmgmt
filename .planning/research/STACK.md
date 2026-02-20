# Stack Research: Cross-Pair Trading (XRP/EUR + XRP/BTC)

## Research Question

What patterns and tools are used for cross-pair/cross-currency trading position aggregation? How do trading systems handle multi-quote-currency cost basis conversion and optimal execution routing?

## Key Findings

### 1. Cost Basis Normalization Pattern

**Pattern:** Fixed-rate conversion at fill time (historical rate), not floating conversion.

**How it works:**
- When an XRP/BTC lot is created, fetch the BTC/EUR rate at fill-time via Klines API
- Persist `cost_eur` (EUR equivalent) and `quote_to_eur_rate` (conversion rate) on the lot
- All downstream calculations use pre-computed EUR values
- Rate is immutable — never recomputed

**Why this pattern:** Deterministic, auditable, consistent with IAS 21 foreign-currency translation. The existing BNB fee conversion (`get_historical_price()` + `fee_quote_value`) uses exactly this pattern.

**Confidence:** HIGH — Standard accounting practice, already proven in this codebase for BNB fees.

### 2. Base-Asset-Centric Position Grouping

**Pattern:** Group positions by base asset, not by trading pair.

**How it works:**
- Symbol registry already knows `get_base_asset("XRPEUR") == "XRP"` and `get_base_asset("XRPBTC") == "XRP"`
- Sell allocation queries filter by base asset (all XRP lots) instead of symbol
- Pairing groups by base asset with EUR-normalized P&L

**Why this pattern:** A position in XRP is the same economic exposure regardless of purchase pair.

**Confidence:** HIGH — Industry standard for multi-venue trading systems.

### 3. Sell Order Routing

**Pattern:** Best-execution routing based on EUR-equivalent proceeds comparison.

**Routing logic:**
```
xrp_eur_proceeds = qty * xrp_eur_price * (1 - fee)
xrp_btc_proceeds = qty * xrp_btc_price * btc_eur_price * (1 - fee)
route_to = max(xrp_eur_proceeds, xrp_btc_proceeds)
```

**Evaluate at execution time** (not simulation time) — prices change between simulation and execution.

**Confidence:** HIGH — Standard best-execution routing.

### 4. P&L Normalization

**Pattern:** All P&L in EUR (reporting currency), regardless of sell pair.

- XRP/EUR sell against XRP/EUR lot: `pnl = sell_price_eur * qty - cost_eur`
- XRP/EUR sell against XRP/BTC lot: `pnl = sell_price_eur * qty - cost_eur` (cost_eur pre-computed at fill time)
- XRP/BTC sell: `proceeds_eur = xrp_btc_price * btc_eur_price * qty`, then same formula

**Confidence:** HIGH — Standard single-currency reporting.

## Existing Infrastructure to Reuse

| Component | Current Use | Cross-Pair Reuse |
|-----------|------------|-----------------|
| `get_historical_price()` | BNB fee → EUR conversion | BTC → EUR rate at XRP/BTC fill time |
| `compute_fee_quote_value()` | Fee normalization | Pattern for cost normalization |
| `symbol_registry.get_base_asset()` | Asset identification | Base-asset lot grouping |
| Overview `toEur()` | Frontend BTC→EUR display | Already works, just needs lot-level EUR data |

## What NOT to Do

1. **Don't convert at current rate** — Cost basis must be fixed at fill time. Floating conversion makes P&L non-deterministic.
2. **Don't add a separate cross-pair service** — Extend existing lot_service and pairing_service. New service adds unnecessary abstraction.
3. **Don't change the ledger** — Ledger remains symbol-scoped. Cross-pair is a lot/pairing-level concern.
4. **Don't build generic multi-quote** — Only XRP has two pairs. YAGNI.

---

*Generated: 2026-02-20*
*Source: Codebase analysis + domain knowledge*
