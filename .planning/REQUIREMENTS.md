# Requirements: BTC/EUR Cashflow-Management

**Defined:** 2026-02-28
**Core Value:** Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System

## v3.1 Requirements

Requirements for Hardening + Monitoring milestone. Each maps to roadmap phases.

### Health Check

- [x] **HLTH-01**: Health Endpoint prueft 8 Kern-Services parallel (Backend, DB, WebSocket, Dry-Run, Alpha Score, Sentiment, Macro, Binance REST)
- [x] **HLTH-02**: Jeder Service liefert strukturierten Status (ok/stale/degraded/stopped/unavailable/error) mit Timestamps
- [x] **HLTH-03**: Overall-Status aggregiert als healthy/degraded/critical (3-Tier)
- [x] **HLTH-04**: Health-State lebt ausschliesslich in-memory (kein SQLite-Write, kein Lock-Contention)
- [x] **HLTH-05**: Health-Response wird 5s gecacht (verhindert excessive Polling-Last)

### Telegram

- [ ] **TELE-01**: TelegramNotifier Service sendet Nachricht bei Service-Ausfall (DOWN)
- [ ] **TELE-02**: Graceful No-Op wenn TELEGRAM_BOT_TOKEN/CHAT_ID nicht konfiguriert
- [ ] **TELE-03**: Alert-Routing trennt Health-Events von AlertBanner (keine AlertEventDB-Eintraege fuer Health)

### WebSocket Recovery

- [x] **WSRC-01**: Post-Reconnect Reconciliation wird automatisch nach WebSocket-Reconnect getriggert
- [x] **WSRC-02**: Listen Key Freshness Tracking — Health DEGRADED wenn User Data Stream >90s ohne Nachricht
- [x] **WSRC-03**: Keepalive-Failure (None-Response) triggert sofortigen Reconnect
- [x] **WSRC-04**: Frontend zeigt Reconnect-State (reconnecting, attempts, error) im WebSocketContext

### Status Dashboard

- [x] **DASH-01**: StatusDashboard.jsx im Admin-Bereich mit per-Service Status-Karten (gruen/amber/rot)
- [x] **DASH-02**: Last-Check Timestamps und Relative-Age-Anzeige pro Service
- [x] **DASH-03**: WebSocket Reconnect-State Anzeige (attempts, error) aus WebSocketContext
- [x] **DASH-04**: Global Nav Status-Dot (gruen/amber/rot) mit Link zum Dashboard

## Future Requirements

Deferred to v3.2+. Tracked but not in current roadmap.

### Health Check (v3.2)

- **HLTH-06**: Liveness vs. Readiness Distinction (/health/live vs /health/ready)
- **HLTH-07**: WebSocket Price Stream Last-Message Age (silent staleness detection)

### Telegram (v3.2)

- **TELE-04**: Recovery-Benachrichtigung wenn Service wieder healthy
- **TELE-05**: Cooldown/Deduplication State Machine (10min per Service)
- **TELE-06**: Telegram Markdown Formatting

## Out of Scope

| Feature | Reason |
|---------|--------|
| Prometheus + Grafana | Overkill fuer Single-User App |
| Email Notifications | Telegram deckt den Use-Case ab |
| Public Status Page | Single-User App, nicht noetig |
| Health History in SQLite | Write-Contention Risiko, kein Consumer |
| Responsive/Mobile Dashboard | Desktop-fokussiert (Projekt-Constraint) |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| HLTH-01 | Phase 19 | Complete |
| HLTH-02 | Phase 19 | Complete |
| HLTH-03 | Phase 19 | Complete |
| HLTH-04 | Phase 19 | Complete |
| HLTH-05 | Phase 19 | Complete |
| TELE-01 | Phase 20 | Pending |
| TELE-02 | Phase 20 | Pending |
| TELE-03 | Phase 20 | Pending |
| WSRC-01 | Phase 21 | Complete |
| WSRC-02 | Phase 21 | Complete |
| WSRC-03 | Phase 21 | Complete |
| WSRC-04 | Phase 21 | Complete |
| DASH-01 | Phase 22 | Complete |
| DASH-02 | Phase 22 | Complete |
| DASH-03 | Phase 22 | Complete |
| DASH-04 | Phase 22 | Complete |

**Coverage:**
- v3.1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0

---
*Requirements defined: 2026-02-28*
*Last updated: 2026-02-28 after roadmap creation (traceability populated)*
