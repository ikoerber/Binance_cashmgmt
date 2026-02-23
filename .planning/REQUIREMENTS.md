# Requirements: BTC/EUR Cashflow-Management

**Defined:** 2026-02-23
**Core Value:** Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System fuer EUR-denominierte Spot-Paare

## v2.0 Requirements

Requirements for v2.0 Frontend Redesign + EUR-Fokus. Each maps to roadmap phases.

### XRPBTC Removal

- [ ] **REM-01**: XRPBTC aus Symbol Registry entfernen (Backend + Frontend)
- [ ] **REM-02**: Cross-Pair Routing-Logik entfernen (Sell-Routing Service, Dual-Route Simulation)
- [ ] **REM-03**: Satoshi-Encoding und BTC-Quote-spezifische clientOrderId-Logik entfernen
- [ ] **REM-04**: XRPBTC-spezifische Domain-Modelle entfernen (RouteDetails, DualRouteComparison, RoutingDecision)
- [ ] **REM-05**: XRPBTC-spezifische Tests und Scripts bereinigen
- [ ] **REM-06**: Frontend Cross-Pair UI-Elemente entfernen (Pair-Herkunft-Badges, Routing-Anzeige, Dual-Route Simulation)

### Dark Mode

- [ ] **DARK-01**: CSS Custom Property System vervollstaendigen (alle hardcoded Hex-Werte in Variablen)
- [ ] **DARK-02**: Dark Mode Farbpalette definieren (Slate-950 Background, WCAG AA Kontrast)
- [ ] **DARK-03**: Alle 12 CSS-Dateien auf Dark-Mode-Variablen umstellen
- [ ] **DARK-04**: lightweight-charts Dark Theme Integration (via applyOptions())
- [ ] **DARK-05**: Recharts Dark Theme Integration (via JS Theme Hook)
- [ ] **DARK-06**: Flash-of-Wrong-Theme Prevention (Blocking Script in index.html)

### Navigation

- [ ] **NAV-01**: 3-Bereichs-Navigation implementieren (Trading, Orderblocks, Admin)
- [ ] **NAV-02**: Combined Score Hero-Widget ins Dashboard integrieren
- [ ] **NAV-03**: API Docs aus Navbar entfernen (Footer-Link oder versteckt)
- [ ] **NAV-04**: Router-Struktur anpassen (alte URLs redirecten)

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Auto-Order Automation

- **AUTO-01**: Trigger-basierte Sell Orders ("Sell bei Break-even + X%")
- **AUTO-02**: Konfigurierbare Trigger-Regeln pro Lot oder Pairing

### Hardening v2

- **HARD-01**: WebSocket-Recovery und Reconnection-Logik
- **HARD-02**: Health-Check Endpoints und Monitoring

### Frontend Tests

- **TEST-01**: Vitest Setup und Konfiguration
- **TEST-02**: Kritische Flow-Tests (Pairing-Lifecycle, Lot-Filter, Formatters)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| UI-Framework (Tailwind, MUI, Shadcn) | Projekt-Konvention: Plain CSS, eigenes Design-System |
| Light/Dark Toggle | v2.0 ist Dark-only. Toggle kann spaeter ergaenzt werden via data-theme Attribut |
| XRPBTC Daten loeschen (DB) | Historische Daten bleiben erhalten (Ledger-first). Nur Code-Pfade entfernt |
| Responsive/Mobile Layout | Desktop-fokussiert. Mobile spaeter |
| Theme per User-Setting (Backend) | Dark Mode ist clientseitig (localStorage). Kein Backend-Roundtrip noetig |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REM-01 | — | Pending |
| REM-02 | — | Pending |
| REM-03 | — | Pending |
| REM-04 | — | Pending |
| REM-05 | — | Pending |
| REM-06 | — | Pending |
| DARK-01 | — | Pending |
| DARK-02 | — | Pending |
| DARK-03 | — | Pending |
| DARK-04 | — | Pending |
| DARK-05 | — | Pending |
| DARK-06 | — | Pending |
| NAV-01 | — | Pending |
| NAV-02 | — | Pending |
| NAV-03 | — | Pending |
| NAV-04 | — | Pending |

**Coverage:**
- v2.0 requirements: 16 total
- Mapped to phases: 0
- Unmapped: 16 (pending roadmap creation)

---
*Requirements defined: 2026-02-23*
*Last updated: 2026-02-23 after initial definition*
