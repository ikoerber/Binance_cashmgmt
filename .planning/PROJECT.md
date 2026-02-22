# XRP Cross-Pair Pairing

## What This Is

Erweiterung der BTC/EUR Cashflow-Management App um Cross-Pair Pairing fuer XRP. XRP/EUR und XRP/BTC Lots werden in einem Pairing gebuendelt, das System waehlt automatisch das Pair mit hoechstem EUR-Erloes und berechnet deterministisch EUR-normalisierte P&L ueber historische BTC/EUR-Kursumrechnung. Symbol-Isolation in der Sell-Allocation verhindert Cross-Asset-Kontamination.

## Core Value

XRP-Lots unabhaengig vom Quote-Asset (EUR oder BTC) in einem Pairing buendeln und ueber das ertragreichere Pair verkaufen — mit deterministischer EUR-P&L-Berechnung ueber historische BTC/EUR-Kursumrechnung.

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

### Active

<!-- Current scope. Building toward these. -->

- [ ] Binance REST API Resilience (Rate-Limit Backoff, Timeout-Handling, Fehlerklassifikation)
- [ ] Sync Reliability (keine stillen Fehler, Retry mit Backoff, resumable Partial Sync)
- [ ] Proaktive Reconciliation (Auto-Trigger nach Sync, Threshold-basierte Diskrepanz-Erkennung)
- [ ] Alert-System (In-App Benachrichtigungen + strukturierte Logs fuer Sync-Fehler und Diskrepanzen)

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
Tech Stack: Python 3 + FastAPI, SQLAlchemy 2, Alembic, React 19, TanStack Query.
633 Backend-Tests, Frontend-Build sauber.

Symbol Registry kennt 4 Pairs: BTCEUR, ETHEUR, XRPEUR, XRPBTC. XRP ist das einzige Base-Asset mit zwei Quote-Pairs. Historische Kursumrechnung (Klines API) wird sowohl fuer BNB-Fees als auch fuer EUR-Kostenbasis bei BTC-quoted Lots verwendet.

### Known Tech Debt (v1.0)
- backfill_cost_eur.py verwendet float() statt Decimal fuer SQL-Writes
- Single-Pairing GET Endpoint liefert routing_decision_json nicht (List-Endpoint tut es)
- EUR P&L Normalisierung bei Fill-Zeit nutzt btceur_price vom Routing-Zeitpunkt (akzeptierte Approximation)
- Phase 1 hat kein VERIFICATION.md (vor Einfuehrung des Verify-Steps ausgefuehrt)

## Constraints

- **Determinismus**: Alle Berechnungen aus Ledger + Regeln reproduzierbar — historische BTC/EUR-Kurse, nicht aktuelle
- **Ledger-first**: Append-only Ledger als Single Source of Truth
- **Decimal-Praezision**: Kein float fuer Geld/Preise, API-Transport als String
- **Backward Compatibility**: Bestehende BTC/EUR und ETH/EUR Lots duerfen nicht beeintraechtigt werden
- **Idempotenz**: Cross-Pair Orders halten dasselbe clientOrderId-Pattern ein (mit Satoshi-Encoding fuer sub-1 Preise)

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

## Current Milestone: v1.1 API Hardening

**Goal:** Binance API Interaktionen resilient und beobachtbar machen — keine stillen Sync-Fehler, automatischer Retry mit Backoff, proaktive Reconciliation mit In-App Alerts.

**Target features:**
- Binance REST Resilience (429 Backoff, Timeouts, Error Classification)
- Sync Reliability (explizite Fehler, Retry, resumable Partial Sync)
- Proaktive Reconciliation (Auto-Trigger, Threshold-Alerts)
- Alert-System (Frontend Banner + strukturierte Logs)

---
*Last updated: 2026-02-22 after v1.1 milestone start*
