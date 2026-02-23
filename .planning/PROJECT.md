# BTC/EUR Cashflow-Management

## What This Is

BTC/EUR Cashflow-Management & Automation App fuer Binance Spot Trading. Ledger-basiertes, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System. Unterstuetzt BTCEUR, ETHEUR und XRPEUR Paare mit EUR als einzigem Quote-Asset.

## Core Value

Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System fuer EUR-denominierte Spot-Paare.

## Current Milestone: v2.0 Frontend Redesign + EUR-Fokus

**Goal:** Frontend komplett neugestalten (Dark Mode, 3-Bereichs-Navigation, Combined Score ins Dashboard) und XRPBTC-Support entfernen — nur noch EUR-Paare.

**Target features:**
- XRPBTC komplett entfernen (Backend + Frontend, Symbol Registry, Cross-Pair Routing, BTC-Quote-Logik)
- Navigation von 7 Tabs auf 3 Bereiche reduzieren: Trading (Dashboard + Combined Score + Lots + Pairing), Orderblocks, Admin (Reconciliation + Settings)
- Dark Mode Theme (Trading-App-Optik)
- Combined Score ins Dashboard integrieren (statt eigene Seite)
- API Docs aus Navbar entfernen

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Multi-Symbol Support (Symbol Registry, qty_base Refactoring, Quote-Asset-Abstraktion) — pre-v1.0
- ✓ Per-Symbol Portfolio-Berechnung mit Cross-Pair-Isolation — pre-v1.0
- ✓ Per-Symbol Lot-Queries und -Filterung — pre-v1.0
- ✓ Per-Symbol Binance Sync — pre-v1.0
- ✓ Pairing-System (Heuristik v1.2, Simulation, Lifecycle DRAFT→LOCKED→EXECUTED) — pre-v1.0
- ✓ Sell-Allocation Strategien (FIFO/LIFO/HIGHEST_COST) — pre-v1.0
- ✓ Historische Fee-Konvertierung (BNB→EUR via Klines API zum Fill-Zeitpunkt) — pre-v1.0
- ✓ Frontend Overview mit Cross-Pair Aggregation (BTC→EUR Umrechnung) — pre-v1.0
- ✓ Order-Erstellung (TAKE_PROFIT_LIMIT, idempotent via clientOrderId) — pre-v1.0
- ✓ Sell-Allocation Symbol-Isolation: Alle 4 Pfade (FIFO/LIFO/HIGHEST_COST/lot-specific) filtern nach Base-Asset — v1.0
- ✓ Symbol Registry get_symbols_for_base_asset() fuer Base-Asset-Gruppierung — v1.0
- ✓ Historische EUR-Kostenbasis: BTC/EUR-Kurs zum Fill-Zeitpunkt auf TradeLot persistiert — v1.0
- ✓ break_even_eur aus cost_eur / qty_base_initial berechenbar — v1.0
- ✓ Alembic-Migration mit Backfill fuer bestehende Lots — v1.0
- ✓ Cross-Pair Pairing: XRP/EUR + XRP/BTC Lots in einem Pairing buendelbar — v1.0
- ✓ EUR-normalisierte P&L in Pairing-Heuristik (cost_eur statt cost_quote) — v1.0
- ✓ Dual-Route Simulation (XRPEUR vs XRPBTC x BTCEUR) in Pairing-UI — v1.0
- ✓ Pair-Herkunft-Badge (XRPEUR/XRPBTC) im Frontend — v1.0
- ✓ Automatisches Sell-Routing: Live-Preise fuer 3 Pairs, Route mit hoechstem EUR-Erloes gewaehlt — v1.0
- ✓ Routing-Audit: RoutingDecision mit Preisen, EUR-Erloesen und Delta persistiert — v1.0
- ✓ EUR-normalisierte realized_pnl bei Cross-Pair Sell-Allocation — v1.0
- ✓ Binance REST API Resilience: Rate-Limit Backoff, konfigurierbares Timeout, strukturierte Fehlerklassifikation (transient vs permanent) — v1.1
- ✓ Sync Reliability: Per-Fill Tracking (PROCESSED/FAILED/SKIPPED_FIFO), explizite Fehlerrueckgabe, Watermark-basierte Wiederaufnahme — v1.1
- ✓ Proaktive Reconciliation: Auto-Trigger nach Sync, Threshold-basierte Alerts (warning/critical), persistierte Run-Historie — v1.1
- ✓ Alert-System: Persistent AlertBanner im Frontend, Dismiss/Bulk-Dismiss, strukturierte JSON-Logs (ALERT_EVENT/RECONCILIATION_RUN) — v1.1
- ✓ Reconciliation-Historie: Expandierbare Run-Details mit Alerts im Frontend — v1.1
- ✓ Konfigurierbare Reconciliation-Toleranzen (Base/Quote) in Settings — v1.1

### Active

<!-- Current scope. Building toward these. -->

- [ ] XRPBTC aus Symbol Registry, Backend und Frontend entfernen
- [ ] Navigation auf 3 Bereiche: Trading, Orderblocks, Admin
- [ ] Dark Mode Theme fuer gesamtes Frontend
- [ ] Combined Score ins Dashboard integrieren
- [ ] API Docs aus Navbar entfernen

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Generisches Cross-Pair fuer alle Assets — Erstmal nur XRP, andere Assets (ETH/BTC etc.) bei Bedarf spaeter
- Aggregierte Portfolio-View pro Base-Asset — Frontend Overview macht das bereits, kein Backend-Endpoint noetig
- Auto BTC→EUR Konvertierung nach XRPBTC Sell — Separate Trading-Entscheidung
- Auto-Order Automation (Trigger-basiert) — Separater Milestone
- Hardening: Monitoring + WebSocket-Recovery — v1.1 fokussiert auf REST-Resilience und Sync, WebSocket-Hardening spaeter
- Frontend-Tests (Vitest) — Separater Milestone
- listPairings base_asset Frontend-Filter — v2 Enhancement (Badges anzeigen funktioniert ohne Filter)

## Context

Shipped v1.0 mit 8.035 neuen Zeilen ueber 50 Dateien (4 Phasen, 8 Plaene, 13 Tasks).
Shipped v1.1 mit 6.054 neuen Zeilen ueber 52 Dateien (4 Phasen, 9 Plaene, 17 Tasks).
Tech Stack: Python 3 + FastAPI, SQLAlchemy 2, Alembic, React 19, TanStack Query.
633+ Backend-Tests, Frontend-Build sauber.

Symbol Registry kennt aktuell 4 Pairs: BTCEUR, ETHEUR, XRPEUR, XRPBTC. v2.0 entfernt XRPBTC — nur noch EUR-quoted Pairs. Historische Kursumrechnung (Klines API) wird fuer BNB-Fee-Konvertierung verwendet.

API-Schicht hat exponentiellen Backoff mit Retry-After Support, konfigurierbare Timeouts, strukturierte Fehlerklassifikation. Sync liefert per-Fill Ergebnisse (PROCESSED/FAILED/SKIPPED_FIFO). Auto-Reconciliation nach jedem Sync mit Threshold-Alerts. AlertBanner persistent im Frontend, Reconciliation-Historie mit expandierbaren Run-Details.

Frontend aktuell: 7 Top-Level Tabs (Dashboard, TradeLots, Combined Score, Orderblocks, Reconciliation, Settings, API Docs). Plain CSS, Light Mode, Purple-Gradient Navbar. v2.0 redesigned zu 3 Bereichen mit Dark Mode.

### Known Tech Debt (v1.0)
- backfill_cost_eur.py verwendet float() statt Decimal fuer SQL-Writes
- Single-Pairing GET Endpoint liefert routing_decision_json nicht (List-Endpoint tut es)
- EUR P&L Normalisierung bei Fill-Zeit nutzt btceur_price vom Routing-Zeitpunkt (akzeptierte Approximation)
- Phase 1 hat kein VERIFICATION.md (vor Einfuehrung des Verify-Steps ausgefuehrt)

### Known Tech Debt (v1.1)
- ROADMAP.md Plan-Checkboxen fuer Phase 5/6/8 nicht alle markiert (nur Phase 7 hat [x]) — rein kosmetisch, alle SUMMARYs vorhanden

## Constraints

- **Determinismus**: Alle Berechnungen aus Ledger + Regeln reproduzierbar — historische BTC/EUR-Kurse, nicht aktuelle
- **Ledger-first**: Append-only Ledger als Single Source of Truth
- **Decimal-Praezision**: Kein float fuer Geld/Preise, API-Transport als String
- **Backward Compatibility**: Bestehende BTC/EUR, ETH/EUR und XRP/EUR Lots duerfen nicht beeintraechtigt werden
- **Idempotenz**: Orders halten dasselbe clientOrderId-Pattern ein
- **Plain CSS**: Kein UI-Framework, eigenes Design-System

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Sell-Allocation nach Base-Asset filtern | Behebt bestehenden Bug + ermoeglicht Cross-Pair Allocation fuer XRP | ✓ Good — alle 4 Pfade isoliert, 10 Tests |
| BTC/EUR-Kurs zum Kaufzeitpunkt speichern | Deterministische, historisch korrekte EUR-Kostenbasis (analog BNB-Fee-Konvertierung) | ✓ Good — cost_eur + quote_to_eur_rate auf jedem Lot |
| Nur XRP Cross-Pair, nicht generisch | Reduziert Scope, XRP ist einziges Asset mit zwei Quote-Pairs | ✓ Good — YAGNI bestaetigt |
| EUR-normalisierte P&L statt Quote-P&L fuer Cross-Pair | Einheitliche Waehrung fuer gemischte EUR/BTC Lots | ✓ Good — cost_eur als Basis, realized_pnl_eur auf SellAllocation |
| Routing-Entscheidung auf Pairing (nicht Order) | Routing ist eine Pairing-Ebene Entscheidung, nicht pro Order | ✓ Good — routing_decision_json auf PairingDB |
| Sell-Routing automatisch (bestes Pair) | Maximiert EUR-Erloes ohne manuellen Aufwand | ✓ Good — 3 Live-Preise, DRC-basierte Selektion |
| Satoshi-Encoding fuer XRPBTC clientOrderId | Verhindert Kollisionen bei sub-1 Preisen (int(price) waere 0) | ✓ Good — int(price * 1e8) + Symbol-Abkuerzung |
| Phase 4 platziert nur erstes Leg (XRPBTC Sell) | Auto BTC→EUR Konvertierung ist separate Trading-Entscheidung | ✓ Good — klare Abgrenzung, User kontrolliert BTC |
| BinanceAPIError als einzige Exception fuer alle API-Fehler | Einheitlicher Error-Pfad (permanent + exhausted retry) | ✓ Good — Single exception type |
| create_order ohne Retry | Doppel-Order-Risiko bei Retry (out of scope) | ✓ Good — Nur Reads retried |
| Auto-Recon nur Balances + Orders (nicht Fills) | Fills gerade abgeschlossen, Re-Run redundant | ✓ Good — Performant, kein doppelter Fill-Check |
| AlertBanner mit 30s Polling (nicht WebSocket) | Konsistent mit CombinedScore Pattern, einfach | ✓ Good — WebSocket-Push in v2 |
| Tolerance Inputs als type=text | Decimal-Praezision per Projekt-Konvention | ✓ Good — Backend validiert via Decimal |

| XRPBTC komplett entfernen | Nur EUR-Paare, vereinfacht Codebase (kein Cross-Pair Routing, kein Satoshi-Encoding, kein BTC-Quote) | — Pending |
| 3-Bereichs-Navigation statt 7 Tabs | Weniger kognitive Last, logische Gruppierung (Trading/Orderblocks/Admin) | — Pending |
| Dark Mode statt Light Mode | Trading-App-Konvention, bessere Lesbarkeit bei laengerer Nutzung | — Pending |
| Combined Score ins Dashboard | Zentrale Handlungsempfehlung gehoert zur Trading-Uebersicht, nicht auf eigene Seite | — Pending |

---
*Last updated: 2026-02-23 after v2.0 milestone start*
