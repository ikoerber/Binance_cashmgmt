# Milestones

## v1.0 XRP Cross-Pair Pairing (Shipped: 2026-02-22)

**Phases completed:** 4 phases, 8 plans, 13 tasks
**Timeline:** 3 days (2026-02-20 → 2026-02-22)
**Lines:** +8,035 / -329 across 50 files
**Tests:** 633 backend tests passing

**Key accomplishments:**
- Base-asset sell allocation isolation — XRP/BTC sells never contaminate BTC/EUR lots (all 4 allocation paths filtered)
- Deterministic EUR cost basis — Every lot has historical exchange-rate-based cost_eur (BTC-quoted lots use Klines API rate at fill time)
- Cross-pair pairing — Mixed XRPEUR + XRPBTC lots in one pairing with EUR-normalized P&L and dual-route simulation
- Automatic sell routing — At execution, system fetches 3 live prices and routes to the pair with highest EUR proceeds
- Full routing audit trail — RoutingDecision persisted with prices, EUR proceeds, and delta; visible in frontend
- EUR-normalized realized P&L — Cross-pair sell fills compute correct EUR profit using lot.cost_eur regardless of sell pair

---

