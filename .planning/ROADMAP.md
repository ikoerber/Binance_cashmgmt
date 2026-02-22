# Roadmap: XRP Cross-Pair Pairing

## Milestones

- ✅ **v1.0 XRP Cross-Pair Pairing** — Phases 1-4 (shipped 2026-02-22)
- 🚧 **v1.1 API Hardening** — Phases 5-8 (in progress)

## Phases

<details>
<summary>✅ v1.0 XRP Cross-Pair Pairing (Phases 1-4) — SHIPPED 2026-02-22</summary>

- [x] Phase 1: Sell Allocation Symbol Isolation (1/1 plans) — completed 2026-02-20
- [x] Phase 2: EUR Cost Basis (2/2 plans) — completed 2026-02-20
- [x] Phase 3: Cross-Pair Pairing (3/3 plans) — completed 2026-02-20
- [x] Phase 4: Sell Routing (2/2 plans) — completed 2026-02-22

See: `.planning/milestones/v1.0-ROADMAP.md` for full details

</details>

### 🚧 v1.1 API Hardening (In Progress)

**Milestone Goal:** Binance API Interaktionen resilient und beobachtbar machen — keine stillen Sync-Fehler, automatischer Retry mit Backoff, proaktive Reconciliation mit In-App Alerts.

- [ ] **Phase 5: API Resilience** - Binance REST Client erkennt Rate-Limits, respektiert Timeouts und klassifiziert Fehler
- [ ] **Phase 6: Sync Reliability** - Sync-Prozess gibt Fehler explizit zurueck, wiederholt transiente Fehler und trackt Fortschritt
- [ ] **Phase 7: Proactive Reconciliation** - Reconciliation triggert automatisch nach Sync mit Threshold-Alerts und persistierter Historie
- [ ] **Phase 8: Alert System** - Frontend zeigt persistente Alerts fuer Sync-Fehler und Diskrepanzen, Logs sind maschinenlesbar

## Phase Details

### Phase 5: API Resilience
**Goal**: Binance REST API Calls sind robust gegen Rate-Limits, Timeouts und transiente Fehler
**Depends on**: Phase 4 (v1.0 shipped)
**Requirements**: API-01, API-02, API-03
**Success Criteria** (what must be TRUE):
  1. Ein 429 Rate-Limit-Response von Binance fuehrt zu automatischem Warten mit exponentiellem Backoff — der Call wird erfolgreich wiederholt, nicht abgebrochen
  2. Ein Binance API Call der laenger als das konfigurierte Timeout dauert, schlaegt mit einem klaren Timeout-Fehler fehl (kein Haengen)
  3. Fehler werden als transient (retryable: Timeout, Rate-Limit, 5xx) oder permanent (nicht retryable: 4xx Auth, Invalid Parameter) klassifiziert — transiente Fehler werden automatisch wiederholt, permanente sofort propagiert
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Sync Reliability
**Goal**: Sync-Prozess ist transparent, wiederholbar und gibt niemals stille Fehler
**Depends on**: Phase 5
**Requirements**: SYNC-01, SYNC-02, SYNC-03
**Success Criteria** (what must be TRUE):
  1. Nach einem Sync-Lauf zeigt der Response explizit an, welche Fills verarbeitet wurden und welche fehlgeschlagen sind — keine stillen Skips
  2. Ein transienter Fehler (Timeout, Rate-Limit) waehrend des Syncs wird automatisch mit Backoff wiederholt, ohne dass der User manuell neu triggern muss
  3. Nach einem abgebrochenen Sync kann der naechste Lauf dort fortsetzen, wo der letzte aufgehoert hat (kein vollstaendiger Re-Sync noetig)
  4. Der User kann im Sync-Response erkennen, wie viele Fills erfolgreich, fehlgeschlagen und uebersprungen wurden
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: Proactive Reconciliation
**Goal**: Reconciliation laeuft automatisch nach Sync und erkennt Diskrepanzen proaktiv
**Depends on**: Phase 6
**Requirements**: RECON-01, RECON-02, RECON-03
**Success Criteria** (what must be TRUE):
  1. Nach einem erfolgreichen Sync wird automatisch eine Reconciliation (Fills + Balances) ausgefuehrt — ohne manuellen Klick
  2. Diskrepanzen die einen konfigurierbaren Threshold ueberschreiten erzeugen Alert-Events (sichtbar im naechsten Phase-8-Frontend)
  3. Jede Reconciliation wird mit Zeitstempel, Status und gefundenen Diskrepanzen persistiert und ist spaeter abrufbar
  4. Die manuelle Reconciliation-UI funktioniert weiterhin wie bisher (kein Breaking Change)
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

### Phase 8: Alert System
**Goal**: User sieht Sync-Fehler und Diskrepanzen sofort im Frontend und kann sie bestaetigen
**Depends on**: Phase 7
**Requirements**: ALERT-01, ALERT-02, ALERT-03
**Success Criteria** (what must be TRUE):
  1. Sync-Fehler und Diskrepanzen erscheinen als Banner oder Toast im Frontend — der User muss nicht manuell auf die Reconciliation-Seite navigieren
  2. Alert-Events werden als strukturierte Log-Eintraege geschrieben (JSON-Format mit Typ, Severity, Zeitstempel, Details) fuer externes Monitoring
  3. Alerts sind persistent (bleiben sichtbar ueber Page-Refreshes) und koennen vom User bestaetigt/dismissed werden
  4. Dismissed Alerts verschwinden aus der UI, bleiben aber im Log erhalten
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 5 → 6 → 7 → 8

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Sell Allocation Symbol Isolation | v1.0 | 1/1 | Complete | 2026-02-20 |
| 2. EUR Cost Basis | v1.0 | 2/2 | Complete | 2026-02-20 |
| 3. Cross-Pair Pairing | v1.0 | 3/3 | Complete | 2026-02-20 |
| 4. Sell Routing | v1.0 | 2/2 | Complete | 2026-02-22 |
| 5. API Resilience | v1.1 | 0/? | Not started | - |
| 6. Sync Reliability | v1.1 | 0/? | Not started | - |
| 7. Proactive Reconciliation | v1.1 | 0/? | Not started | - |
| 8. Alert System | v1.1 | 0/? | Not started | - |
