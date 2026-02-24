# Roadmap: BTC/EUR Cashflow-Management

## Milestones

- ✅ **v1.0 XRP Cross-Pair Pairing** — Phases 1-4 (shipped 2026-02-22)
- ✅ **v1.1 API Hardening** — Phases 5-8 (shipped 2026-02-23)
- 🚧 **v2.0 Frontend Redesign + EUR-Fokus** — Phases 9-12 (in progress)

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

### 🚧 v2.0 Frontend Redesign + EUR-Fokus

**Milestone Goal:** Frontend komplett neugestalten (Dark Mode, 3-Bereichs-Navigation, Combined Score ins Dashboard) und XRPBTC-Support entfernen — nur noch EUR-Paare.

- [x] **Phase 9: XRPBTC Removal** - Alle XRPBTC Code-Pfade aus Backend und Frontend entfernen (historische DB-Daten bleiben)
- [x] **Phase 10: CSS Variable Foundation** - Alle hardcoded Farbwerte durch CSS Custom Properties ersetzen (kein visueller Unterschied) (completed 2026-02-24)
- [x] **Phase 11: Dark Mode Activation + Charts** - Dunkles Theme aktivieren, Chart-Bibliotheken integrieren, FOWT verhindern (completed 2026-02-24)
- [ ] **Phase 12: Navigation Restructure + Dashboard** - 3-Bereichs-Navigation, Combined Score ins Dashboard, API Docs entfernen

## Phase Details

### Phase 9: XRPBTC Removal
**Goal**: Die Codebase kennt nur noch EUR-quoted Pairs (BTCEUR, ETHEUR, XRPEUR) — alle Cross-Pair-Logik ist entfernt
**Depends on**: Nothing (first phase in v2.0; builds on shipped v1.1)
**Requirements**: REM-01, REM-02, REM-03, REM-04, REM-05, REM-06
**Success Criteria** (what must be TRUE):
  1. Symbol Registry liefert genau 3 Symbole (BTCEUR, ETHEUR, XRPEUR) — kein XRPBTC in Backend oder Frontend
  2. Pairing-Erstellung und Sell-Order-Platzierung funktionieren fuer alle 3 EUR-Paare ohne Routing-Logik oder BTC-Quote-Pfade
  3. Frontend zeigt keine Cross-Pair UI-Elemente (keine Pair-Herkunft-Badges, kein Dual-Route Vergleich, kein Cross-Pair Toggle)
  4. Alle Backend-Tests bestehen ohne XRPBTC-spezifische Testdateien, restliche Tests sind angepasst
  5. Historische XRPBTC-Daten in der Datenbank sind unberuehrt (Ledger-Events, Lots, Allocations bleiben erhalten)
**Plans**: 3 plans

Plans:
- [x] 09-01-PLAN.md — Backend domain, services, API, ORM: remove all XRPBTC cross-pair code paths
- [x] 09-02-PLAN.md — Frontend: remove cross-pair UI elements, simplify symbol registry and API client
- [x] 09-03-PLAN.md — Alembic migration (drop 6 columns) + test cleanup (delete 4 files, adapt 2)

### Phase 10: CSS Variable Foundation
**Goal**: Alle Farben im Frontend werden ueber CSS Custom Properties gesteuert — die App sieht identisch aus, aber jede Farbe ist eine Variable
**Depends on**: Nothing (kann parallel zu Phase 9 laufen, aber sequentiell geplant)
**Requirements**: DARK-01, DARK-02
**Success Criteria** (what must be TRUE):
  1. Kein hardcoded Hex-Farbwert existiert ausserhalb der `:root`-Definition in `index.css` (verifizierbar via grep)
  2. Die App im Browser sieht pixelidentisch zum Zustand vor der Konvertierung aus (kein visueller Unterschied)
  3. Die Dark-Mode-Farbpalette ist als `[data-theme="dark"]`-Block in `index.css` definiert (noch nicht aktiv, aber bereit)
**Plans**: 3 plans

Plans:
- [x] 10-01-PLAN.md — Define complete CSS Custom Property system in index.css (:root light tokens + [data-theme="dark"] palette)
- [x] 10-02-PLAN.md — Convert 6 heaviest CSS files to var() references (Orderblock, LotsTable, PairingPanel, Reconciliation, CombinedScore, Overview)
- [x] 10-03-PLAN.md — Convert remaining 5 CSS files + JSX inline color references + final zero-hex verification

### Phase 11: Dark Mode Activation + Charts
**Goal**: Das gesamte Frontend ist dunkel gestylt — alle Komponenten, Charts und Lade-Zustaende verwenden das Dark Theme
**Depends on**: Phase 10 (CSS Variables muessen komplett sein, sonst bleiben Elemente hell)
**Requirements**: DARK-03, DARK-04, DARK-05, DARK-06
**Success Criteria** (what must be TRUE):
  1. Alle 12 CSS-Dateien rendern korrekt im Dark Mode — keine weissen Flaechen, keine unlesbaren Texte, keine unsichtbaren Borders
  2. Candlestick-Chart (lightweight-charts) hat dunklen Hintergrund mit lesbaren Kerzen, Zonen-Overlays und Volume-Histogramm
  3. Recharts-Diagramme (Orderblock Stats, Overview PieChart) haben dunkle Hintergruende mit lesbaren Labels und Tooltips
  4. Beim Laden der Seite gibt es keinen weissen Blitz (Flash of Wrong Theme) — der dunkle Hintergrund ist sofort sichtbar
**Plans**: 4 plans

Plans:
- [x] 11-01-PLAN.md — FOWT prevention script + dark theme activation + useChartTheme hook + new CSS tokens
- [x] 11-02-PLAN.md — OrderblockChart.jsx lightweight-charts dark theme integration (25 color values)
- [x] 11-03-PLAN.md — Recharts + CombinedScore + orderblockHelpers dark theme integration (49 color values)
- [x] 11-04-PLAN.md — Gap closure: CombinedScore action_color hero banner + Overview PieChart tooltip dark fix

### Phase 12: Navigation Restructure + Dashboard
**Goal**: Die App hat 3 klare Bereiche (Trading, Orderblocks, Admin) und die zentrale Handlungsempfehlung ist direkt im Dashboard sichtbar
**Depends on**: Phase 9 (saubere 3-Symbol-Liste), Phase 11 (Dark-Mode-aware Komponenten)
**Requirements**: NAV-01, NAV-02, NAV-03, NAV-04
**Success Criteria** (what must be TRUE):
  1. Die Navigation zeigt 3 Bereiche (Trading, Orderblocks, Admin) statt 7 einzelne Tabs — Symbol-Selector bleibt immer sichtbar
  2. Das Dashboard enthaelt das Combined Score Hero-Widget (Action Banner + Score Bar) oberhalb der KPI-Kacheln
  3. API Docs ist nicht mehr in der Navbar (Link ggf. im Footer oder Settings)
  4. Alte URLs (z.B. `/s/:symbol/combined`) leiten korrekt auf die neue Struktur um — keine 404s fuer Bookmarks
  5. Browser-Navigation (Zurueck/Vorwaerts) funktioniert korrekt zwischen allen Bereichen und Symbolen
**Plans**: TBD

Plans:
- [ ] 12-01: TBD
- [ ] 12-02: TBD

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
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
| 11. Dark Mode Activation + Charts | v2.0 | Complete    | 2026-02-24 | 2026-02-24 |
| 12. Navigation Restructure + Dashboard | v2.0 | 0/? | Not started | - |
