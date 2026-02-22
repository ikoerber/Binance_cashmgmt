# Requirements: API Hardening

**Defined:** 2026-02-22
**Core Value:** Binance API Interaktionen resilient und beobachtbar machen — keine stillen Sync-Fehler, automatischer Retry mit Backoff, proaktive Reconciliation mit Alerts

## v1.1 Requirements

### API Resilience

- [ ] **API-01**: Binance REST Calls erkennen 429 Rate-Limit-Responses und warten automatisch (exponentieller Backoff)
- [ ] **API-02**: Binance REST Calls haben konfigurierbares Timeout und schlagen bei Ueberschreitung fehl (statt endlos zu haengen)
- [ ] **API-03**: Binance API Fehler werden strukturiert klassifiziert (transient vs. permanent) mit entsprechendem Retry-Verhalten

### Sync Reliability

- [ ] **SYNC-01**: Sync-Fehler werden explizit im Response zurueckgegeben (keine stillen Skips, fehlerhafte Fills sichtbar)
- [ ] **SYNC-02**: Transiente Fehler (Timeout, Rate-Limit) werden automatisch mit Backoff wiederholt (max N Retries)
- [ ] **SYNC-03**: Sync-Fortschritt wird tracierbar (welche Fills verarbeitet, welche fehlgeschlagen, wo Wiederaufnahme moeglich)

### Reconciliation

- [ ] **RECON-01**: Nach erfolgreichem Sync wird automatisch Reconciliation getriggert (Fills + Balances)
- [ ] **RECON-02**: Diskrepanzen ueber konfigurierbarem Threshold erzeugen Alert-Events
- [ ] **RECON-03**: Reconciliation-Ergebnis wird persistiert (Zeitstempel, Status, Diskrepanzen) fuer Historien-Ansicht

### Alerting

- [ ] **ALERT-01**: Alert-Events werden im Frontend als Banner/Toast angezeigt (Sync-Fehler, Diskrepanzen, fehlgeschlagene Orders)
- [ ] **ALERT-02**: Alert-Events werden als strukturierte Log-Eintraege geschrieben (maschinenlesbar, fuer externes Monitoring)
- [ ] **ALERT-03**: Alerts sind persistent (nicht nur fluechtiger Toast) und koennen vom User bestaetigt/dismissed werden

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
| API-01 | TBD | Pending |
| API-02 | TBD | Pending |
| API-03 | TBD | Pending |
| SYNC-01 | TBD | Pending |
| SYNC-02 | TBD | Pending |
| SYNC-03 | TBD | Pending |
| RECON-01 | TBD | Pending |
| RECON-02 | TBD | Pending |
| RECON-03 | TBD | Pending |
| ALERT-01 | TBD | Pending |
| ALERT-02 | TBD | Pending |
| ALERT-03 | TBD | Pending |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 0
- Unmapped: 12

---
*Requirements defined: 2026-02-22*
*Last updated: 2026-02-22 after initial definition*
