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


## v1.1 API Hardening (Shipped: 2026-02-23)

**Phases completed:** 4 phases, 9 plans, 17 tasks
**Timeline:** 2 days (2026-02-22 → 2026-02-23)
**Lines:** +6,054 / -174 across 52 files

**Key accomplishments:**
- Structured error classification (transient vs permanent) with exponential backoff + Retry-After support
- Configurable timeouts on all Binance API clients (REST + public), no more hanging calls
- Per-fill sync result tracking with explicit outcomes (PROCESSED/FAILED/SKIPPED_FIFO/SKIPPED_DUPLICATE)
- Auto-reconciliation after every sync with threshold-based alerts (warning at >tolerance, critical at >10x)
- Persistent AlertBanner in frontend with dismiss/bulk-dismiss, 30s polling, severity-colored (amber/red/blue)
- Reconciliation history UI with expandable run details + configurable tolerance thresholds in Settings

---

