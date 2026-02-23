# Requirements: API Hardening

**Defined:** 2026-02-22
**Core Value:** Binance API Interaktionen resilient und beobachtbar machen — keine stillen Sync-Fehler, automatischer Retry mit Backoff, proaktive Reconciliation mit Alerts

## v1.1 Requirements

### API Resilience

- [x] **API-01**: Binance REST Calls erkennen 429 Rate-Limit-Responses und warten automatisch (exponentieller Backoff)
- [x] **API-02**: Binance REST Calls haben konfigurierbares Timeout und schlagen bei Ueberschreitung fehl (statt endlos zu haengen)
- [x] **API-03**: Binance API Fehler werden strukturiert klassifiziert (transient vs. permanent) mit entsprechendem Retry-Verhalten

### Sync Reliability

- [x] **SYNC-01**: Sync-Fehler werden explizit im Response zurueckgegeben (keine stillen Skips, fehlerhafte Fills sichtbar)
- [x] **SYNC-02**: Transiente Fehler (Timeout, Rate-Limit) werden automatisch mit Backoff wiederholt (max N Retries)
- [x] **SYNC-03**: Sync-Fortschritt wird tracierbar (welche Fills verarbeitet, welche fehlgeschlagen, wo Wiederaufnahme moeglich)

### Reconciliation

- [x] **RECON-01**: Nach erfolgreichem Sync wird automatisch Reconciliation getriggert (Fills + Balances)
- [x] **RECON-02**: Diskrepanzen ueber konfigurierbarem Threshold erzeugen Alert-Events
- [x] **RECON-03**: Reconciliation-Ergebnis wird persistiert (Zeitstempel, Status, Diskrepanzen) fuer Historien-Ansicht

### Alerting

- [x] **ALERT-01**: Alert-Events werden im Frontend als Banner/Toast angezeigt (Sync-Fehler, Diskrepanzen, fehlgeschlagene Orders)
- [ ] **ALERT-02**: Alert-Events werden als strukturierte Log-Eintraege geschrieben (maschinenlesbar, fuer externes Monitoring)
- [x] **ALERT-03**: Alerts sind persistent (nicht nur fluechtiger Toast) und koennen vom User bestaetigt/dismissed werden

## v2 Requirements

### Extended Hardening

- **HARD-01**: WebSocket-Recovery mit automatischem Reconnect und Gap-Detection
- **HARD-02**: Circuit Breaker Pattern fuer Binance API (automatische Deaktivierung bei wiederholten Fehlern)
- **HARD-03**: Health-Endpoint mit Binance API Status, WebSocket-Status, letzte Sync-Zeit

## Out of Scope

| Feature | Reason |
|---------|--------|
| WebSocket Hardening | v1.1 fokussiert auf REST + Sync, WebSocket-Recovery in v2 |
| External Alerting (Telegram, Slack) | Frontend + Logs reichen fuer v1.1, Webhook-Integration spaeter |
| Auto-Order Automation | Eigener Milestone, braucht Hardening als Voraussetzung |
| Rate-Limit Monitoring Dashboard | Logs reichen fuer v1.1, Dashboard spaeter |
| Automatic Retry fuer Order-Placement | Zu riskant — Order-Duplikate. Nur Sync wird retried. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| API-01 | Phase 5 | Complete |
| API-02 | Phase 5 | Complete |
| API-03 | Phase 5 | Complete |
| SYNC-01 | Phase 6 | Complete |
| SYNC-02 | Phase 6 | Complete |
| SYNC-03 | Phase 6 | Complete |
| RECON-01 | Phase 7 | Complete |
| RECON-02 | Phase 7 | Complete |
| RECON-03 | Phase 7 | Complete |
| ALERT-01 | Phase 8 | Complete |
| ALERT-02 | Phase 8 | Pending |
| ALERT-03 | Phase 8 | Complete |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0

---
*Requirements defined: 2026-02-22*
*Last updated: 2026-02-22 after roadmap creation*
