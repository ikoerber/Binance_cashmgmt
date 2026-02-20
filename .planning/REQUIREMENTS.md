# Requirements: XRP Cross-Pair Pairing

**Defined:** 2026-02-20
**Core Value:** XRP-Lots unabhängig vom Quote-Asset (EUR oder BTC) in einem Pairing bündeln und über das ertragreichere Pair verkaufen

## v1 Requirements

### Sell Allocation

- [ ] **ALLOC-01**: Sell-Fills allokieren nur gegen Lots desselben Base-Assets (XRP-Sells gegen XRP-Lots, BTC-Sells gegen BTC-Lots)
- [ ] **ALLOC-02**: Symbol Registry bietet `get_symbols_for_base_asset()` Hilfsfunktion für Base-Asset-Gruppierung
- [ ] **ALLOC-03**: Alle 4 Sell-Allocation-Pfade (FIFO, LIFO, HIGHEST_COST, lot-specific) filtern nach Base-Asset

### EUR Cost Basis

- [ ] **COST-01**: Bei XRP/BTC Lot-Erstellung wird der BTC/EUR-Kurs zum Fill-Zeitpunkt via Klines API abgerufen
- [ ] **COST-02**: `cost_eur` (EUR-Equivalent der Kosten) und `quote_to_eur_rate` (Konvertierungsrate) werden auf TradeLot persistiert
- [ ] **COST-03**: Für EUR-quoted Lots gilt `cost_eur = cost_quote` und `quote_to_eur_rate = 1.0`
- [ ] **COST-04**: Alembic-Migration fügt neue Spalten hinzu und backfillt bestehende Lots korrekt (EUR-quoted: rate=1.0, BTC-quoted: historische Rate oder Flag)
- [ ] **COST-05**: Break-even in EUR (`break_even_eur`) berechenbar aus `cost_eur / qty_base_initial`

### Cross-Pair Pairing

- [ ] **PAIR-01**: Pairing-Heuristik akzeptiert Lots aus XRPEUR und XRPBTC in einem Pairing
- [ ] **PAIR-02**: P&L-Berechnung in Pairing-Heuristik verwendet EUR-normalisierte Kostenbasis (`cost_eur`)
- [ ] **PAIR-03**: Pairing-Modell verwendet `base_asset` statt `symbol` für Cross-Pair-Pairings
- [ ] **PAIR-04**: Cross-Pair Simulation zeigt EUR-P&L mit Dual-Route-Vergleich (XRPEUR vs XRPBTC×BTCEUR)
- [ ] **PAIR-05**: Frontend Pairing-UI unterstützt gemischte XRP/EUR + XRP/BTC Lots mit Pair-Herkunft-Badge

### Sell Routing

- [ ] **ROUTE-01**: Bei Pairing-Execution berechnet System EUR-Erlös für beide Routes (XRP/EUR direkt vs XRP/BTC×BTC/EUR)
- [ ] **ROUTE-02**: Sell-Order wird automatisch auf das Pair mit höherem EUR-Erlös geroutet
- [ ] **ROUTE-03**: Routing-Entscheidung wird geloggt (gewähltes Pair, Preise, Erlös-Differenz)
- [ ] **ROUTE-04**: Cross-Pair Sell-Allocation: Sell-Fills von geroutetem Pair allokieren gegen alle XRP-Lots mit EUR-normalisierter P&L

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
| Generisches Cross-Pair für alle Assets | XRP einziges Asset mit 2 Quote-Pairs, YAGNI |
| Auto BTC→EUR Konvertierung nach XRPBTC Sell | Separate Trading-Entscheidung |
| Arbitrage-Execution | Anderer Use Case, braucht Sub-Sekunden-Latenz |
| Tax-optimiertes Routing | Steuerreporting out of scope (CLAUDE.md) |
| Cross-Base-Asset Pairing | Kann XRP nicht verkaufen um BTC-Lot zu schließen |
| Split Sell Orders über Pairs | Orderbook-Tiefenanalyse, zu komplex für v1 |
| Aggregierter Backend-Endpoint | Frontend Overview reicht |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ALLOC-01 | — | Pending |
| ALLOC-02 | — | Pending |
| ALLOC-03 | — | Pending |
| COST-01 | — | Pending |
| COST-02 | — | Pending |
| COST-03 | — | Pending |
| COST-04 | — | Pending |
| COST-05 | — | Pending |
| PAIR-01 | — | Pending |
| PAIR-02 | — | Pending |
| PAIR-03 | — | Pending |
| PAIR-04 | — | Pending |
| PAIR-05 | — | Pending |
| ROUTE-01 | — | Pending |
| ROUTE-02 | — | Pending |
| ROUTE-03 | — | Pending |
| ROUTE-04 | — | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 0
- Unmapped: 17 ⚠️

---
*Requirements defined: 2026-02-20*
*Last updated: 2026-02-20 after initial definition*
