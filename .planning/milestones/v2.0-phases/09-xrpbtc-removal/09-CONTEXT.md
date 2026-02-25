# Phase 9: XRPBTC Removal - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Alle XRPBTC Cross-Pair Code-Pfade aus Backend und Frontend entfernen. Historische DB-Zeilen (Lots, Orders, Ledger-Events) bleiben erhalten. Die Codebase kennt danach nur noch BTCEUR, ETHEUR, XRPEUR.

</domain>

<decisions>
## Implementation Decisions

### Vereinfachungstiefe
- XRPBTC entfernen UND ueberfluessige Abstraktionen vereinfachen (nicht nur XRPBTC-Code loeschen)
- Sell-Routing Service komplett entfernen (RoutingDecision Model, routing_decision_json Logik, Sell-Routing Service) — Orders gehen direkt ans einzige EUR-Pair
- get_symbols_for_base_asset() und hasMultipleSymbols() entfernen — 1:1 Mapping Base-Asset zu Symbol, keine Multi-Symbol-Abstraktion noetig
- DualRouteComparison, RouteDetails, Frontend-Vergleichsansicht komplett entfernen

### Alembic Migration
- DB-Spalten routing_decision_json (PairingDB) und quote_to_eur_rate (TradeLotDB) per Alembic-Migration entfernen
- cost_eur auf TradeLotDB bleibt (wird auch fuer EUR-Lots gebraucht)
- Lot/Order/Pairing/Ledger-Event Zeilen mit XRPBTC bleiben in der DB (nur Spalten weg, keine Daten-Loeschung)
- backfill_cost_eur.py Script behalten (als Referenz)

### Historische XRPBTC-Daten
- XRPBTC Lots/Orders im Frontend verstecken (nicht anzeigen, kein Archiv-View)
- XRPBTC Lots aus Portfolio-Berechnung ausschliessen (nicht in KPIs: BTC Bestand, P&L etc.)
- Binance Sync importiert XRPBTC Fills weiterhin (Ledger-Vollstaendigkeit), aber keine Lot-Erstellung / keine Anzeige
- Reconciliation schliesst XRPBTC aus (kein Balance-Abgleich fuer XRPBTC)

### Claude's Discretion
- Reihenfolge der Datei-Aenderungen (Backend-first oder Frontend-first)
- Welche XRPBTC-spezifischen Tests geloescht vs. angepasst werden
- Ob Satoshi-Encoding-Code komplett oder nur XRPBTC-Pfad entfernt wird
- Detailgrad der Alembic-Migration (ein Schritt oder aufgeteilt)

</decisions>

<specifics>
## Specific Ideas

- Sync importiert XRPBTC Fills weiter, aber erstellt keine Lots — Ledger-Events werden gespeichert, Lot-Erstellung wird fuer XRPBTC uebersprungen
- Portfolio-Berechnung filtert nach Symbol Registry (nur registrierte EUR-Pairs zaehlen)
- Frontend-Filter schliesst XRPBTC Lots/Orders implizit aus (API gibt sie nicht mehr zurueck, oder Frontend filtert)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-xrpbtc-removal*
*Context gathered: 2026-02-23*
