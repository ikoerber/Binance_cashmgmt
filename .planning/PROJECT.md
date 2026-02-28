# BTC/EUR Cashflow-Management

## What This Is

BTC/EUR Cashflow-Management & Automation App fuer Binance Spot Trading. Ledger-basiertes, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System. Unterstuetzt BTCEUR, ETHEUR und XRPEUR Paare mit EUR als einzigem Quote-Asset. Multi-Faktor Alpha Score Engine (Z-Score, Lead-Lag, Orderbook, Funding) mit ATR-adaptiven Trailing Stops, Walk-Forward Backtesting (24 Monate, Sharpe/Drawdown), Dry-Run Paper Trading und Bot Dashboard. Dark Mode Frontend mit 4-Bereichs-Navigation (Trading/Analyse/Bot/Admin).

## Core Value

Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System fuer EUR-denominierte Spot-Paare.

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
- ✓ XRPBTC aus Symbol Registry, Backend und Frontend entfernt — v2.0
- ✓ 3-Bereichs-Navigation (Trading/Analyse/Admin) — v2.0
- ✓ Dark Mode Theme (Dark-only, FOWT-safe, alle Chart-Bibliotheken) — v2.0
- ✓ Combined Score Hero-Widget ins Dashboard integriert — v2.0
- ✓ API Docs aus Navbar entfernt (Footer-Link) — v2.0
- ✓ XRPBTC re-added to Symbol Registry + Binance Sync (analysis + trading, no cross-pair pairing) — v3.0
- ✓ Multi-Factor Scoring Engine: Z-Score (40%), Lead-Lag (30%), Orderbook Imbalance (20%), Funding Rate (10%) → Alpha Score (-5 to +5) — v3.0
- ✓ ATR-Adaptive Trailing Stops with data-gap freeze/resume — v3.0
- ✓ Regime Detection (Hurst exponent, trending/mean-reverting) with adaptive Z-Score weighting — v3.0
- ✓ Walk-Forward Backtesting (24-month, Sharpe, drawdown, HODL benchmark, parameter sweep) — v3.0
- ✓ Dry-Run Mode (real-time signals, virtual portfolio, structural isolation from orders) — v3.0
- ✓ Combined Score Integration (Alpha Score as optional 3rd signal, 50/30/20 with 60/40 fallback) — v3.0
- ✓ Bot Dashboard (4-group nav: Trading/Analyse/Bot/Admin, signal history, regime badge) — v3.0
- ✓ Decision Log (filterable, expandable factor details) — v3.0

### Active

<!-- Current scope. Building toward these. -->

(None yet — planning next milestone)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Auto-Order Automation (Trigger-basiert) — Separater Milestone (nach Omni-Bot Live-Execution)
- Live Execution (Auto-Placing Orders) — Follow-up nach Backtesting + Dry-Run validiert
- German Tax Veto (365-Tage Haltefrist) — Deferred bis Live Execution Milestone
- Cross-Pair Pairing fuer XRPBTC — Removed in v2.0, nicht wieder eingefuehrt
- Hardening: Monitoring + WebSocket-Recovery — WebSocket-Hardening spaeter
- Frontend-Tests (Vitest) — Separater Milestone
- Light/Dark Toggle — Dark-only in v2.0, Toggle kann spaeter ergaenzt werden
- Responsive/Mobile Layout — Desktop-fokussiert

## Current Milestone: Planning Next

v3.0 Multi-Factor Omni-Bot shipped 2026-02-27. Next milestone TBD via `/gsd:new-milestone`.

## Context

Shipped v1.0 mit 8.035 neuen Zeilen ueber 50 Dateien (4 Phasen, 8 Plaene, 13 Tasks).
Shipped v1.1 mit 6.054 neuen Zeilen ueber 52 Dateien (4 Phasen, 9 Plaene, 17 Tasks).
Shipped v2.0 mit 9.387 neuen Zeilen ueber 93 Dateien (4 Phasen, 12 Plaene, 24 Tasks).
Shipped v3.0 mit 42.148 LOC gesamt (26.132 Python + 16.016 JS/CSS), 5 Phasen, 16 Plaene, 63 Commits.
Tech Stack: Python 3 + FastAPI, SQLAlchemy 2, Alembic, React 19, TanStack Query, Recharts, lightweight-charts.
799+ Backend-Tests, Frontend-Build sauber.

Symbol Registry kennt 3 EUR-Pairs (BTCEUR, ETHEUR, XRPEUR) + XRPBTC (re-added in v3.0 fuer Analyse). Alpha Score Engine mit 4 Faktoren, Regime-Erkennung (Hurst), ATR-Trailing. Walk-Forward Backtesting mit Parameter-Sweep. Dry-Run Paper Trading mit struktureller Isolation (DRY-05). Combined Score integriert Alpha als optionalen 3. Signal (50/30/20).

Frontend: Dark Mode (dark-only), 4-Bereichs-Navigation (Trading/Analyse/Bot/Admin), Bot Dashboard mit Alpha Score Hero, Signal History Chart, Regime Badge. Decision Log mit filterbarer Tabelle und aufklappbaren Faktor-Details. Plain CSS mit 79+ CSS Custom Properties.

### Known Tech Debt
- backfill_cost_eur.py verwendet float() statt Decimal fuer SQL-Writes (v1.0)
- Single-Pairing GET Endpoint liefert routing_decision_json nicht (v1.0)
- getQuoteDecimals(symbol) wird mit ignoriertem Argument aufgerufen (v2.0)
- XRPEUR price_precision=4 Backend vs getQuoteDecimals()=2 Frontend (pre-existing)
- orderblockHelpers.jsx hardcoded Fallback-Gradients (unerreichbar im Normalbetrieb) (v2.0)
- Keine Frontend-Tests (Vitest geplant)
- Pytest ResourceWarning: 52 unclosed database connections in Test-Fixtures (v2.0 Code Review)

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

| XRPBTC komplett entfernen | Nur EUR-Paare, vereinfacht Codebase (kein Cross-Pair Routing, kein Satoshi-Encoding, kein BTC-Quote) | ✓ Good — 6 DB-Spalten, 4 Testdateien entfernt, historische Daten erhalten |
| 3-Bereichs-Navigation statt 7 Tabs | Weniger kognitive Last, logische Gruppierung (Trading/Analyse/Admin) | ✓ Good — "Analyse" statt "Orderblocks" als Gruppenlabel (Combined Score + Orderblocks) |
| Dark Mode (dark-only) statt Light Mode | Trading-App-Konvention, bessere Lesbarkeit bei laengerer Nutzung | ✓ Good — FOWT-safe, 440+ Hex-Werte konvertiert, beide Chart-Libs theme-aware |
| Combined Score ins Dashboard | Zentrale Handlungsempfehlung gehoert zur Trading-Uebersicht, nicht auf eigene Seite | ✓ Good — CombinedScoreWidget mit TanStack Cache-Sharing |
| CSS Custom Properties statt hardcoded Hex | Vorbereitung Dark Mode + zukuenftiges Theming | ✓ Good — 79+ semantische Tokens, zero hardcoded Hex in 12 CSS-Dateien |
| useChartTheme als zentraler Chart-Theme-Hook | Einheitlicher Zugriff auf CSS-Variablen fuer lightweight-charts + Recharts | ✓ Good — getComputedStyle-basiert, 74 Chart-Farbwerte konvertiert |
| Dashboard als Default-Landing-Page pro Symbol | Trading-Empfehlung sofort sichtbar statt Lot-Liste | ✓ Good — Index-Redirect von /lots zu /dashboard |
| 4 quantitative Faktoren fuer Alpha Score | Z-Score (40%), Lead-Lag (30%), Imbalance (20%), Funding (10%) — korrelationsbasierte Gewichtung | ✓ Good — Regime-adaptive Z-Score Gewichtung, Hurst-Exponent Erkennung |
| Structural Isolation fuer Dry-Run (DRY-05) | Import-Verbot statt Runtime-Flag — keine order_service/binance.py Imports im DryRunService | ✓ Good — Zero forbidden imports, verified in Phase 16 |
| Alpha Score als optionaler 3. Signal im Combined Score | 50/30/20 Gewichtung wenn verfuegbar, exakter 60/40 Fallback wenn nicht | ✓ Good — Backward-kompatibel, 17 neue Tests |
| Bot als 4. Nav-Gruppe (Trading/Analyse/Bot/Admin) | Unified Bot-Bereich fuer Alpha Score, Dry-Run, Backtest-Ueberblick | ✓ Good — Amber-Akzent, Dry-Run Badge in Nav |
| Walk-Forward Backtesting statt In-Sample | Vermeidet Overfitting, realistische Out-of-Sample Performance | ✓ Good — 24-Monate, Sharpe/Drawdown, HODL Benchmark |
| Wall-Clock Evaluation Loop (nicht fixed sleep) | Candle-Close Alignment, idempotent bei Server-Restart | ✓ Good — asyncio.sleep bis naechste Grenze |

---
*Last updated: 2026-02-28 after v3.0 milestone*
