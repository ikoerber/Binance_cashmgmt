# Requirements: XRP Cross-Pair Pairing

**Defined:** 2026-02-20
**Core Value:** XRP-Lots unabhaengig vom Quote-Asset (EUR oder BTC) in einem Pairing buendeln und ueber das ertragreichere Pair verkaufen

## v1 Requirements

### Sell Allocation

- [x] **ALLOC-01**: Sell-Fills allokieren nur gegen Lots desselben Base-Assets (XRP-Sells gegen XRP-Lots, BTC-Sells gegen BTC-Lots)
- [x] **ALLOC-02**: Symbol Registry bietet `get_symbols_for_base_asset()` Hilfsfunktion fuer Base-Asset-Gruppierung
- [x] **ALLOC-03**: Alle 4 Sell-Allocation-Pfade (FIFO, LIFO, HIGHEST_COST, lot-specific) filtern nach Base-Asset

### EUR Cost Basis

- [x] **COST-01**: Bei XRP/BTC Lot-Erstellung wird der BTC/EUR-Kurs zum Fill-Zeitpunkt via Klines API abgerufen
- [x] **COST-02**: `cost_eur` (EUR-Equivalent der Kosten) und `quote_to_eur_rate` (Konvertierungsrate) werden auf TradeLot persistiert
- [x] **COST-03**: Fuer EUR-quoted Lots gilt `cost_eur = cost_quote` und `quote_to_eur_rate = 1.0`
- [x] **COST-04**: Alembic-Migration fuegt neue Spalten hinzu und backfillt bestehende Lots korrekt (EUR-quoted: rate=1.0, BTC-quoted: historische Rate oder Flag)
- [x] **COST-05**: Break-even in EUR (`break_even_eur`) berechenbar aus `cost_eur / qty_base_initial`

### Cross-Pair Pairing

- [x] **PAIR-01**: Pairing-Heuristik akzeptiert Lots aus XRPEUR und XRPBTC in einem Pairing
- [x] **PAIR-02**: P&L-Berechnung in Pairing-Heuristik verwendet EUR-normalisierte Kostenbasis (`cost_eur`)
- [x] **PAIR-03**: Pairing-Modell verwendet `base_asset` statt `symbol` fuer Cross-Pair-Pairings
- [x] **PAIR-04**: Cross-Pair Simulation zeigt EUR-P&L mit Dual-Route-Vergleich (XRPEUR vs XRPBTC x BTCEUR)
- [x] **PAIR-05**: Frontend Pairing-UI unterstuetzt gemischte XRP/EUR + XRP/BTC Lots mit Pair-Herkunft-Badge

### Sell Routing

- [x] **ROUTE-01**: Bei Pairing-Execution berechnet System EUR-Erloes fuer beide Routes (XRP/EUR direkt vs XRP/BTC x BTC/EUR)
- [x] **ROUTE-02**: Sell-Order wird automatisch auf das Pair mit hoeherem EUR-Erloes geroutet
- [x] **ROUTE-03**: Routing-Entscheidung wird geloggt (gewaehltes Pair, Preise, Erloes-Differenz)
- [x] **ROUTE-04**: Cross-Pair Sell-Allocation: Sell-Fills von geroutetem Pair allokieren gegen alle XRP-Lots mit EUR-normalisierter P&L

## v2 Requirements

### Enhanced Display

- **DISP-01**: Dual-Price-Anzeige (XRPEUR + XRPBTC) im Pairing-Panel
- **DISP-02**: Post-Execution Route-Optimierungsbericht ("Routing hat X EUR gespart/gekostet")
- **DISP-03**: XRP Total Portfolio-Card (kombinierte XRPEUR+XRPBTC Ansicht)

### Configuration

- **CONF-01**: Sell-Route Override in Settings (Immer EUR / Immer BTC / Auto)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Generisches Cross-Pair fuer alle Assets | XRP einziges Asset mit 2 Quote-Pairs, YAGNI |
| Auto BTC->EUR Konvertierung nach XRPBTC Sell | Separate Trading-Entscheidung |
| Arbitrage-Execution | Anderer Use Case, braucht Sub-Sekunden-Latenz |
| Tax-optimiertes Routing | Steuerreporting out of scope (CLAUDE.md) |
| Cross-Base-Asset Pairing | Kann XRP nicht verkaufen um BTC-Lot zu schliessen |
| Split Sell Orders ueber Pairs | Orderbook-Tiefenanalyse, zu komplex fuer v1 |
| Aggregierter Backend-Endpoint | Frontend Overview reicht |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ALLOC-01 | Phase 1 | Complete |
| ALLOC-02 | Phase 1 | Complete |
| ALLOC-03 | Phase 1 | Complete |
| COST-01 | Phase 2 | Complete |
| COST-02 | Phase 2 | Complete |
| COST-03 | Phase 2 | Complete |
| COST-04 | Phase 2 | Complete |
| COST-05 | Phase 2 | Complete |
| PAIR-01 | Phase 3 | Complete |
| PAIR-02 | Phase 3 | Complete |
| PAIR-03 | Phase 3 | Complete |
| PAIR-04 | Phase 3 | Complete |
| PAIR-05 | Phase 3 | Complete |
| ROUTE-01 | Phase 4 | Complete |
| ROUTE-02 | Phase 4 | Complete |
| ROUTE-03 | Phase 4 | Complete |
| ROUTE-04 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-02-20*
*Last updated: 2026-02-22 after Phase 4 completion*
