# XRP Cross-Pair Pairing

## What This Is

Erweiterung der BTC/EUR Cashflow-Management App um Cross-Pair Pairing für XRP. Ermöglicht das Zusammenführen von XRP/EUR und XRP/BTC Lots in einem Pairing mit automatischem Sell-Routing über das ertragreichere Pair. Behebt gleichzeitig die fehlende Symbol-Isolation in der Sell-Allocation.

## Core Value

XRP-Lots unabhängig vom Quote-Asset (EUR oder BTC) in einem Pairing bündeln und über das ertragreichere Pair verkaufen — mit deterministischer EUR-P&L-Berechnung über historische BTC/EUR-Kursumrechnung.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Multi-Symbol Support (Symbol Registry, qty_base Refactoring, Quote-Asset-Abstraktion) — v1.0
- ✓ Per-Symbol Portfolio-Berechnung mit Cross-Pair-Isolation — v1.0
- ✓ Per-Symbol Lot-Queries und -Filterung — v1.0
- ✓ Per-Symbol Binance Sync — v1.0
- ✓ Pairing-System (Heuristik v1.2, Simulation, Lifecycle DRAFT→LOCKED→EXECUTED) — v1.0
- ✓ Sell-Allocation Strategien (FIFO/LIFO/HIGHEST_COST) — v1.0
- ✓ Historische Fee-Konvertierung (BNB→EUR via Klines API zum Fill-Zeitpunkt) — v1.0
- ✓ Frontend Overview mit Cross-Pair Aggregation (BTC→EUR Umrechnung) — v1.0
- ✓ Order-Erstellung (TAKE_PROFIT_LIMIT, idempotent via clientOrderId) — v1.0

### Active

<!-- Current scope. Building toward these. -->

- [ ] Cross-Pair Sell-Allocation: Sell-Fills allokieren gegen alle Lots desselben Base-Assets (XRP), unabhängig vom Quote-Pair
- [ ] Sell-Allocation Symbol-Fix: FIFO/LIFO/HIGHEST_COST filtert nach Base-Asset (nicht Symbol) — verhindert BTC-Sells gegen XRP-Lots
- [ ] Historische EUR-Kostenbasis für BTC-quoted Lots: BTC/EUR-Kurs zum XRP/BTC Fill-Zeitpunkt speichern
- [ ] Cross-Pair Pairing: XRP/EUR und XRP/BTC Lots in einem Pairing bündelbar
- [ ] Pairing-Simulation Cross-Pair: EUR-P&L-Berechnung über beide Quote-Currencies mit historischer Kursumrechnung
- [ ] Automatisches Sell-Routing: System wählt bei Pairing-Execution das Pair mit höherem EUR-Erlös (XRP/EUR vs. XRP/BTC×BTC/EUR)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Generisches Cross-Pair für alle Assets — Erstmal nur XRP, andere Assets (ETH/BTC etc.) bei Bedarf später
- Aggregierte Portfolio-View pro Base-Asset — Frontend Overview macht das bereits, kein Backend-Endpoint nötig
- Auto-Order Automation (Trigger-basiert) — Separater Milestone
- Hardening (Monitoring, Alerting, Rate-Limit) — Separater Milestone
- Frontend-Tests (Vitest) — Separater Milestone

## Context

Bestehendes BTC/EUR Cashflow-Management-System mit ledger-basiertem, deterministischem Tracking. Multi-Symbol Support (Symbol Registry, qty_base, Quote-Asset-Abstraktion) ist implementiert, aber die Sell-Allocation filtert nicht nach Symbol — bestehender Bug, der gleichzeitig mit Cross-Pair behoben wird.

Historische Kursumrechnung existiert bereits für BNB-Fees (Klines API zum Fill-Zeitpunkt). Derselbe Mechanismus wird für BTC/EUR-Kursumrechnung bei XRP/BTC Lots wiederverwendet.

Symbol Registry kennt 4 Pairs: BTCEUR, ETHEUR, XRPEUR, XRPBTC. XRP ist das einzige Base-Asset mit zwei Quote-Pairs.

## Constraints

- **Determinismus**: Alle Berechnungen aus Ledger + Regeln reproduzierbar — historische BTC/EUR-Kurse, nicht aktuelle
- **Ledger-first**: Append-only Ledger als Single Source of Truth
- **Decimal-Präzision**: Kein float für Geld/Preise, API-Transport als String
- **Backward Compatibility**: Bestehende BTC/EUR und ETH/EUR Lots dürfen nicht beeinträchtigt werden
- **Idempotenz**: Cross-Pair Orders müssen dasselbe clientOrderId-Pattern einhalten

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Sell-Routing automatisch (bestes Pair) | Maximiert EUR-Erlös ohne manuellen Aufwand | — Pending |
| BTC/EUR-Kurs zum Kaufzeitpunkt speichern | Deterministische, historisch korrekte EUR-Kostenbasis (analog BNB-Fee-Konvertierung) | — Pending |
| Sell-Allocation nach Base-Asset filtern | Behebt bestehenden Bug + ermöglicht Cross-Pair Allocation für XRP | — Pending |
| Nur XRP Cross-Pair, nicht generisch | Reduziert Scope, XRP ist einziges Asset mit zwei Quote-Pairs | — Pending |

---
*Last updated: 2026-02-20 after initialization*
