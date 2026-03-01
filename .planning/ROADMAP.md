# Roadmap: BTC/EUR Cashflow-Management

## Milestones

- ✅ **v1.0 XRP Cross-Pair Pairing** — Phases 1-4 (shipped 2026-02-22)
- ✅ **v1.1 API Hardening** — Phases 5-8 (shipped 2026-02-23)
- ✅ **v2.0 Frontend Redesign + EUR-Fokus** — Phases 9-12 (shipped 2026-02-25)
- ✅ **v3.0 Multi-Factor Omni-Bot** — Phases 13-18 (shipped 2026-02-28)
- ✅ **v3.1 Hardening + Monitoring** — Phases 19-22 (shipped 2026-02-28)
- ✅ **v3.2 UX Improvements** — Phases 23-26 (shipped 2026-02-28)
- 🚧 **v3.3 Polish & Completeness** — Phases 27-29 (in progress)

## Phases

<details>
<summary>v1.0 XRP Cross-Pair Pairing (Phases 1-4) — SHIPPED 2026-02-22</summary>

- [x] Phase 1: Sell Allocation Symbol Isolation (1/1 plans) — completed 2026-02-20
- [x] Phase 2: EUR Cost Basis (2/2 plans) — completed 2026-02-20
- [x] Phase 3: Cross-Pair Pairing (3/3 plans) — completed 2026-02-20
- [x] Phase 4: Sell Routing (2/2 plans) — completed 2026-02-22

See: `.planning/milestones/v1.0-ROADMAP.md` for full details

</details>

<details>
<summary>v1.1 API Hardening (Phases 5-8) — SHIPPED 2026-02-23</summary>

- [x] Phase 5: API Resilience (2/2 plans) — completed 2026-02-22
- [x] Phase 6: Sync Reliability (2/2 plans) — completed 2026-02-22
- [x] Phase 7: Proactive Reconciliation (2/2 plans) — completed 2026-02-22
- [x] Phase 8: Alert System + Frontend Observability (3/3 plans) — completed 2026-02-23

See: `.planning/milestones/v1.1-ROADMAP.md` for full details

</details>

<details>
<summary>v2.0 Frontend Redesign + EUR-Fokus (Phases 9-12) — SHIPPED 2026-02-25</summary>

- [x] Phase 9: XRPBTC Removal (3/3 plans) — completed 2026-02-23
- [x] Phase 10: CSS Variable Foundation (3/3 plans) — completed 2026-02-24
- [x] Phase 11: Dark Mode Activation + Charts (4/4 plans) — completed 2026-02-24
- [x] Phase 12: Navigation Restructure + Dashboard (2/2 plans) — completed 2026-02-25

See: `.planning/milestones/v2.0-ROADMAP.md` for full details

</details>

<details>
<summary>v3.0 Multi-Factor Omni-Bot (Phases 13-18) — SHIPPED 2026-02-28</summary>

- [x] Phase 13: XRPBTC Infrastructure (3/3 plans) — completed 2026-02-25
- [x] Phase 14: Multi-Factor Scoring Engine (4/4 plans) — completed 2026-02-26
- [x] Phase 15: Backtesting Engine (4/4 plans) — completed 2026-02-27
- [x] Phase 16: Dry-Run Mode + Bot Dashboard (3/3 plans) — completed 2026-02-27
- [x] Phase 17: Combined Score Integration (2/2 plans) — completed 2026-02-27
- [x] Phase 18: BotDashboard Integration Fixes (1/1 plans) — gap closure, completed 2026-02-28

See: `.planning/milestones/v3.0-ROADMAP.md` for full details

</details>

<details>
<summary>v3.1 Hardening + Monitoring (Phases 19-22) — SHIPPED 2026-02-28</summary>

- [x] Phase 19: Health Check Foundation (2/2 plans) — completed 2026-02-28
- [x] Phase 20: Telegram Notifications (2/2 plans) — completed 2026-02-28
- [x] Phase 21: WebSocket Recovery + Listen Key Hardening (2/2 plans) — completed 2026-02-28
- [x] Phase 22: Status Dashboard (2/2 plans) — completed 2026-02-28

See: `.planning/milestones/v3.1-ROADMAP.md` for full details

</details>

<details>
<summary>v3.2 UX Improvements (Phases 23-26) — SHIPPED 2026-02-28</summary>

- [x] Phase 23: Navigation Structure (1/1 plans) — completed 2026-02-28
- [x] Phase 24: Dynamic Symbol Visibility (1/1 plans) — completed 2026-02-28
- [x] Phase 25: Dedicated Chart Page (1/1 plans) — completed 2026-02-28
- [x] Phase 26: Chart Overlays (2/2 plans) — completed 2026-02-28

See: `.planning/milestones/v3.2-ROADMAP.md` for full details

</details>

### v3.3 Polish & Completeness (In Progress)

**Milestone Goal:** Streamline Overview into compact portfolio table with BNB fee tracking and add contextual help to Backtest page.

- [x] **Phase 27: Overview Layout Restructure** - Replace per-symbol card grid with compact asset table, retain KPI cards and allocation pie chart (completed 2026-03-01)
- [x] **Phase 28: BNB Fee Tracking** - Backend endpoint for BNB balance + cumulative fee EUR aggregation, BNB row in asset table (completed 2026-03-01)
- [ ] **Phase 29: Backtest Tooltips** - Contextual help icons with tooltips on all backtest configuration fields and result metrics

## Phase Details

### Phase 27: Overview Layout Restructure
**Goal**: User sees a streamlined Overview with a compact asset table instead of per-symbol cards, while retaining the aggregate KPI cards and allocation pie chart
**Depends on**: Nothing (first phase in v3.3, no new backend data needed)
**Requirements**: OVW-01, OVW-02, OVW-03
**Success Criteria** (what must be TRUE):
  1. Overview page displays a single table with one row per crypto asset (columns: Asset, Balance, Value EUR, P&L%)
  2. The allocation pie chart is visible alongside the asset table
  3. The 4 aggregate KPI cards (Depotwert, Eingezahlt, EUR verfuegbar, Performance) appear above the asset section
  4. Clicking an asset row navigates to that symbol's dashboard (existing behavior preserved)
**Plans**: TBD

Plans:
- [ ] 27-01: Overview table + layout restructure

### Phase 28: BNB Fee Tracking
**Goal**: User sees BNB balance and cumulative trading fee costs in the Overview asset table, backed by a new backend endpoint
**Depends on**: Phase 27 (asset table must exist for BNB row)
**Requirements**: OVW-04, OVW-05
**Success Criteria** (what must be TRUE):
  1. A new backend endpoint returns the current Binance BNB balance for the user
  2. The same endpoint returns the cumulative EUR-equivalent of all BNB trading fees (aggregated from LedgerEvents with fee_eur_value)
  3. The Overview asset table shows a BNB row with the current BNB balance
  4. The BNB row displays the cumulative fee EUR value (total BNB fees paid, converted to EUR)
**Plans**: TBD

Plans:
- [ ] 28-01: BNB balance + fee aggregation backend endpoint and frontend integration

### Phase 29: Backtest Tooltips
**Goal**: User gets contextual help on every backtest configuration field and result metric without leaving the page
**Depends on**: Nothing (independent of Overview work)
**Requirements**: BTE-01, BTE-02, BTE-03
**Success Criteria** (what must be TRUE):
  1. Each of the 8 backtest configuration fields has a help icon that shows a tooltip explaining what the field controls
  2. Each of the 4 parameter sweep fields has a help icon with a tooltip explaining the sweep parameter
  3. Each result metric card (Sharpe, Drawdown, Win Rate, etc.) has a help icon with a tooltip explaining the metric
  4. Tooltips are readable, concise, and styled consistently with the dark mode theme
**Plans**: TBD

Plans:
- [ ] 29-01: Backtest tooltip implementation

## Progress

**Execution Order:**
Phases execute in numeric order: 27 → 28 → 29

| Phase Range | Milestone | Plans Complete | Status | Completed |
|-------------|-----------|----------------|--------|-----------|
| 1-4 | v1.0 | 8/8 | Complete | 2026-02-22 |
| 5-8 | v1.1 | 9/9 | Complete | 2026-02-23 |
| 9-12 | v2.0 | 12/12 | Complete | 2026-02-25 |
| 13-18 | v3.0 | 17/17 | Complete | 2026-02-28 |
| 19-22 | v3.1 | 8/8 | Complete | 2026-02-28 |
| 23-26 | v3.2 | 5/5 | Complete | 2026-02-28 |
| 27. Overview Layout Restructure | 1/1 | Complete    | 2026-03-01 | - |
| 28. BNB Fee Tracking | 1/1 | Complete    | 2026-03-01 | - |
| 29. Backtest Tooltips | v3.3 | 0/1 | Not started | - |
