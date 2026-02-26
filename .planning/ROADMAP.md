# Roadmap: BTC/EUR Cashflow-Management

## Milestones

- ✅ **v1.0 XRP Cross-Pair Pairing** — Phases 1-4 (shipped 2026-02-22)
- ✅ **v1.1 API Hardening** — Phases 5-8 (shipped 2026-02-23)
- ✅ **v2.0 Frontend Redesign + EUR-Fokus** — Phases 9-12 (shipped 2026-02-25)
- 🚧 **v3.0 Multi-Factor Omni-Bot** — Phases 13-17 (in progress)

## Phases

<details>
<summary>✅ v1.0 XRP Cross-Pair Pairing (Phases 1-4) — SHIPPED 2026-02-22</summary>

- [x] Phase 1: Sell Allocation Symbol Isolation (1/1 plans) — completed 2026-02-20
- [x] Phase 2: EUR Cost Basis (2/2 plans) — completed 2026-02-20
- [x] Phase 3: Cross-Pair Pairing (3/3 plans) — completed 2026-02-20
- [x] Phase 4: Sell Routing (2/2 plans) — completed 2026-02-22

See: `.planning/milestones/v1.0-ROADMAP.md` for full details

</details>

<details>
<summary>✅ v1.1 API Hardening (Phases 5-8) — SHIPPED 2026-02-23</summary>

- [x] Phase 5: API Resilience (2/2 plans) — completed 2026-02-22
- [x] Phase 6: Sync Reliability (2/2 plans) — completed 2026-02-22
- [x] Phase 7: Proactive Reconciliation (2/2 plans) — completed 2026-02-22
- [x] Phase 8: Alert System + Frontend Observability (3/3 plans) — completed 2026-02-23

See: `.planning/milestones/v1.1-ROADMAP.md` for full details

</details>

<details>
<summary>✅ v2.0 Frontend Redesign + EUR-Fokus (Phases 9-12) — SHIPPED 2026-02-25</summary>

- [x] Phase 9: XRPBTC Removal (3/3 plans) — completed 2026-02-23
- [x] Phase 10: CSS Variable Foundation (3/3 plans) — completed 2026-02-24
- [x] Phase 11: Dark Mode Activation + Charts (4/4 plans) — completed 2026-02-24
- [x] Phase 12: Navigation Restructure + Dashboard (2/2 plans) — completed 2026-02-25

See: `.planning/milestones/v2.0-ROADMAP.md` for full details

</details>

### v3.0 Multi-Factor Omni-Bot (In Progress)

**Milestone Goal:** Build a multi-factor scoring engine for BTC/EUR and XRP/EUR with backtesting and dry-run mode, laying the foundation for automated trading.

- [x] **Phase 13: XRPBTC Infrastructure** - Re-add XRPBTC to Symbol Registry and Sync with EUR-denominated P&L (no cross-pair pairing) (completed 2026-02-25)
- [x] **Phase 14: Multi-Factor Scoring Engine** - Four quantitative factors composing into Alpha Score (-5 to +5) with ATR-adaptive trailing exits (completed 2026-02-26)
- [ ] **Phase 15: Backtesting Engine** - Walk-forward simulation over 24 months with Sharpe ratio, drawdown, and HODL benchmark comparison
- [ ] **Phase 16: Dry-Run Mode + Bot Dashboard** - Real-time paper trading with decision logging, virtual portfolio, and unified Bot navigation section
- [ ] **Phase 17: Combined Score Integration** - Alpha Score feeds into existing Combined Score as backward-compatible third signal

## Phase Details

### Phase 13: XRPBTC Infrastructure
**Goal**: Users can view and sync XRPBTC trades with correct EUR-denominated financials, without contaminating EUR-pair workflows
**Depends on**: Phase 12 (v2.0 complete)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):
  1. User sees XRPBTC in the symbol selector and can navigate to its dashboard, lots, and order views
  2. User can trigger Binance sync for XRPBTC and sees newly imported fills as trade lots
  3. XRPBTC lots display break-even and P&L in EUR (converted via historical BTC/EUR rate at fill time), not in BTC
  4. XRPBTC lots never appear in pairing suggestions for EUR-denominated pairs (BTCEUR, ETHEUR, XRPEUR)
**Plans**: 3 plans

Plans:
- [ ] 13-01-PLAN.md — Backend foundation: Symbol Registry + Migration + Domain + Lot serialization
- [ ] 13-02-PLAN.md — Sync pipeline EUR conversion + Pairing/Order API guards + Backfill fix
- [ ] 13-03-PLAN.md — Frontend: Symbol selector, dual BTC/EUR display, pairing isolation, dashboard

### Phase 14: Multi-Factor Scoring Engine
**Goal**: Users can view a real-time Alpha Score (-5 to +5) composed of four independent quantitative factors, plus ATR-adaptive trailing stop levels
**Depends on**: Phase 13 (XRPBTC data available for Z-Score ratio and Lead-Lag computation)
**Requirements**: SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, SCORE-06, SCORE-07, SCORE-08, SCORE-09, EXIT-01, EXIT-02
**Success Criteria** (what must be TRUE):
  1. User can query the Alpha Score API endpoint and receives a score between -5 and +5 with per-factor breakdown (Z-Score, Lead-Lag, Orderbook Imbalance, Funding Rate)
  2. User can configure Alpha Score weights and trade threshold in Settings, and changes take effect on next score computation
  3. When one or more data sources are unavailable, Alpha Score still returns a partial result with a quality indicator showing which factors are missing
  4. During cold start (insufficient data), API returns a warmup status instead of extreme or misleading values
  5. User can view ATR-adaptive trailing stop distances for each symbol, and trailing stops freeze during data gaps and resume after fresh data arrives
**Plans**: 4 plans

Plans:
- [ ] 14-01-PLAN.md — TDD: Pure domain factor computations (Z-Score, Lead-Lag, Orderbook Imbalance, Funding Rate)
- [ ] 14-02-PLAN.md — Settings migration + backend/frontend Alpha Score configuration
- [ ] 14-03-PLAN.md — TDD: Hurst regime detection + Alpha Score aggregation + Trailing stop state machine
- [ ] 14-04-PLAN.md — Data service singleton + API routes + warmup/degradation wiring

### Phase 15: Backtesting Engine
**Goal**: Users can validate Alpha Score signal quality through historical simulation with performance metrics and benchmark comparison
**Depends on**: Phase 14 (scoring logic and trailing exit logic must exist to simulate)
**Requirements**: BT-01, BT-02, BT-03, BT-04, BT-05, BT-06, BT-07
**Success Criteria** (what must be TRUE):
  1. User can run a backtest for any supported symbol over a configurable period (up to 24 months) and sees results within a reasonable time
  2. Backtest results show net return, Sharpe ratio, max drawdown, trade count, and win rate alongside a buy-and-hold benchmark (50/50 BTC/XRP HODL)
  3. Backtest results are persisted as immutable snapshots and user can browse backtest history with expandable run details
  4. User can run a parameter sweep (grid search over Z-Score lookback, weights, thresholds) and export results as CSV
  5. Backtest includes realistic transaction costs (configurable fee rate and slippage modeling) visible in the results
**Plans**: TBD

Plans:
- [ ] 15-01: TBD
- [ ] 15-02: TBD
- [ ] 15-03: TBD

### Phase 16: Dry-Run Mode + Bot Dashboard
**Goal**: Users can observe the scoring engine operating in real-time paper trading mode through a dedicated Bot navigation section, building trust before any future live execution
**Depends on**: Phase 15 (backtesting validates parameters before dry-run uses them)
**Requirements**: DRY-01, DRY-02, DRY-03, DRY-04, DRY-05, BOT-01, BOT-02, BOT-03, BOT-04, BOT-05, BOT-06
**Success Criteria** (what must be TRUE):
  1. User can activate dry-run mode and sees real-time Alpha Score signals being logged without any actual Binance orders being placed
  2. User can view the dry-run decision log filtered by date range, action type, and symbol, with full factor context per decision
  3. Dry-run tracks virtual positions and P&L in separate tables that never appear on the main Dashboard or contaminate the production ledger
  4. A new "Bot" section appears in the navigation (4th area: Trading/Analyse/Bot/Admin) showing current Alpha Score with factor bars, signal history chart, dry-run status, virtual P&L, most recent backtest summary, and regime indicator
  5. Dry-run mode has no structural access to order-placing functionality (enforced by service architecture, not a boolean flag)
**Plans**: TBD

Plans:
- [ ] 16-01: TBD
- [ ] 16-02: TBD
- [ ] 16-03: TBD

### Phase 17: Combined Score Integration
**Goal**: Alpha Score enriches the existing Combined Score as a backward-compatible third signal without disrupting calibrated thresholds
**Depends on**: Phase 16 (Alpha Score validated through backtesting and dry-run before modifying production-facing signal)
**Requirements**: COMB-01, COMB-02
**Success Criteria** (what must be TRUE):
  1. When Alpha Score is available, Combined Score incorporates it as a third signal and the factor breakdown in the dashboard details view shows the Alpha Score contribution
  2. When Alpha Score is unavailable (cold start, data gap, or dry-run not active), Combined Score falls back to existing 60/40 MacroSignal/Sentiment weights with no change in behavior
**Plans**: TBD

Plans:
- [ ] 17-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 13 → 14 → 15 → 16 → 17

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Sell Allocation Symbol Isolation | v1.0 | 1/1 | Complete | 2026-02-20 |
| 2. EUR Cost Basis | v1.0 | 2/2 | Complete | 2026-02-20 |
| 3. Cross-Pair Pairing | v1.0 | 3/3 | Complete | 2026-02-20 |
| 4. Sell Routing | v1.0 | 2/2 | Complete | 2026-02-22 |
| 5. API Resilience | v1.1 | 2/2 | Complete | 2026-02-22 |
| 6. Sync Reliability | v1.1 | 2/2 | Complete | 2026-02-22 |
| 7. Proactive Reconciliation | v1.1 | 2/2 | Complete | 2026-02-22 |
| 8. Alert System | v1.1 | 3/3 | Complete | 2026-02-23 |
| 9. XRPBTC Removal | v2.0 | 3/3 | Complete | 2026-02-23 |
| 10. CSS Variable Foundation | v2.0 | 3/3 | Complete | 2026-02-24 |
| 11. Dark Mode Activation + Charts | v2.0 | 4/4 | Complete | 2026-02-24 |
| 12. Navigation Restructure + Dashboard | v2.0 | 2/2 | Complete | 2026-02-25 |
| 13. XRPBTC Infrastructure | 3/3 | Complete    | 2026-02-25 | - |
| 14. Multi-Factor Scoring Engine | 4/4 | Complete    | 2026-02-26 | - |
| 15. Backtesting Engine | v3.0 | 0/? | Not started | - |
| 16. Dry-Run Mode + Bot Dashboard | v3.0 | 0/? | Not started | - |
| 17. Combined Score Integration | v3.0 | 0/? | Not started | - |
