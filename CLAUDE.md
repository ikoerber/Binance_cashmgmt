# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# BTC/EUR Cashflow-Management & Automation App

## Projektstatus

BTC/EUR Cashflow-Management & Automation App für Binance Spot Trading. Ledger-basiertes, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System.

**Implementiert (Iteration 1-3):**
- Append-only Ledger mit allen Event-Typen
- Portfolio Break-even (WAC) + Dashboard mit 8 KPI-Kacheln
- TradeLots (1 Fill = 1 Lot) + FIFO Sell Allocation
- Trade-Cockpit mit Filtern, Sortierung, Live-P&L, Sell-Order-Indikatoren, Erholungspreis-KPI
- Binance Sync (Fills Import, inkrementell)
- Order-Erstellung (TAKE_PROFIT_LIMIT Sell pro Lot) + Order-Tracking
- Pairing: Backend-Heuristik + Frontend-UI (Vorschläge, manuell, Simulation, Lifecycle)
- Reconciliation-Service + Reconciliation-UI (3 Sektionen: Orders, Balances, Fills)
- Settings-Seite (max_order_value_eur konfigurierbar)
- Live BTC/EUR Preis via Binance API
- Makro-Signal Dashboard (4 Faktoren, konfigurierbar, Richtungsempfehlung)
- Sentiment Engine v3 (5 Pillars, korrelationsgewichtete Aggregation, Dispersion + Volatility Scaling)
- CSV Import (Binance Spot Order History)
- API-Key Authentication (Header `X-API-Key`, konfigurierbar via `API_KEY` in `.env`)
- Transaction-Safety: SQLAlchemy Auto-Commit/Rollback via `yield`-Pattern
- Shared Formatters (`utils/formatters.js`) fuer alle Frontend-Komponenten
- Komponenten-Aufspaltung: LotFilters, OpenOrdersPanel, SimulationModal, PairingExistingTab
- Dependencies gepinnt auf exakte Versionen in `requirements.txt`
- Alternative Sell Allocation Strategien (FIFO, LIFO, HIGHEST_COST) konfigurierbar in Settings

**Offen (Iteration 4-5):**
- Auto-Order Automation (Trigger-basiert)
- Sentiment History Persistierung (SentimentHistoryDB, History-Endpoint)
- Combined Score (MacroSignal + Sentiment)
- Hardening: Monitoring/Alerting, Rate-Limit-Optimierung, WebSocket

## Kernprinzipien

- **Ledger-first**: Alle Berechnungen aus append-only Event-Ledger ableitbar
- **Deterministisch**: Jede Kennzahl aus Ledger + Regeln reproduzierbar
- **Decimal-Präzision**: `Decimal` für alle Geld-/Preisberechnungen (niemals float)
- **Idempotente Orders**: `clientOrderId` = `{userId}_{lotId}_{targetPrice}_{qty}_{version}`
- **FIFO Allocation**: Sell-Fills schließen immer die ältesten Lots zuerst
- **Simulation vor Execution**: Pairing-Ausführung nur nach Simulation-Preview

## Technologiestack

**Backend:** Python 3 + FastAPI, SQLAlchemy 2, Alembic, python-binance
**Frontend:** React 19 + Vite 7, TanStack Query, Axios, Recharts
**Datenbank:** PostgreSQL (Prod) / SQLite (Dev)
**Testing:** pytest (Backend), ruff + black (Linting)
**Infrastruktur:** Redis (geplant für Celery/RQ Worker)

## Projektstruktur

```
cashmgnt/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI App, Route-Registrierung
│   │   ├── domain/                    # Pure Domain-Logik (kein I/O)
│   │   │   ├── models.py             # Dataclasses: LedgerEvent, TradeLot, Pairing, PortfolioState
│   │   │   ├── portfolio.py           # compute_portfolio_from_ledger() - zentrale Berechnung
│   │   │   ├── lots.py                # create_trade_lot_from_buy_fill(), allocate_sell_with_strategy(), allocate_sell_fifo()
│   │   │   ├── pairing.py            # suggest_pairings(), simulate_pairing()
│   │   │   ├── macro_signal.py        # Makro-Faktoren Analyse + Richtungsempfehlung
│   │   │   └── sentiment.py           # Sentiment v3: 5-Pillar Scoring, Dispersion, Volatility Scaling
│   │   ├── services/                  # DB-Integration, Binance API
│   │   │   ├── binance.py            # Binance API Client
│   │   │   ├── sync_service.py       # Fills importieren
│   │   │   ├── lot_service.py        # Lot CRUD + FIFO
│   │   │   ├── order_service.py      # Order-Erstellung (TAKE_PROFIT_LIMIT)
│   │   │   ├── order_tracking_service.py # Order State Lifecycle
│   │   │   ├── pairing_service.py    # Pairing-Persistenz + Lifecycle
│   │   │   ├── portfolio_service.py  # Portfolio-State aus Ledger
│   │   │   ├── reconciliation_service.py
│   │   │   ├── csv_import_service.py  # Binance CSV Import
│   │   │   ├── macro_data_service.py  # Makro-Daten (Klines, Fear&Greed, etc.)
│   │   │   └── sentiment_data_service.py # Sentiment-Daten: F&G, OKX Funding, Klines, Caching (Singleton)
│   │   ├── db/
│   │   │   ├── database.py           # SQLAlchemy Session
│   │   │   └── models.py             # ORM: LedgerEventDB, TradeLotDB, PairingDB, OrderDB, UserSettingsDB
│   │   ├── api/
│   │   │   ├── auth.py                # API-Key Authentication Dependency
│   │   │   └── routes/                # Thin HTTP Layer
│   │   │       ├── portfolio.py       # GET /api/portfolio/{user_id}
│   │   │       ├── lots.py            # GET/POST /api/lots/...
│   │   │       ├── orders.py         # POST/GET/DELETE /api/orders/...
│   │   │       ├── pairing.py        # GET/POST/DELETE /api/pairing/...
│   │   │       ├── cashflow.py       # External Cashflows
│   │   │       ├── sync.py           # Binance Sync
│   │   │       ├── reconciliation.py # POST /api/reconciliation/...
│   │   │       ├── settings.py       # GET/PUT /api/settings/{user_id}
│   │   │       ├── macro.py          # GET /api/macro/...
│   │   │       └── sentiment.py     # GET /api/sentiment/{user_id}/current
│   ├── scripts/
│   │   └── backtest_sentiment.py     # Backtesting: v1/v2/v3 Sentiment vs. 2000+ Tage historische Daten
│   ├── tests/                         # 13 Testdateien
│   │   └── conftest.py               # TEST_BINANCE_API_KEY + Testnet
│   ├── alembic/                       # DB-Migrationen
│   ├── requirements.txt
│   └── .env                           # DB_URL, BINANCE_API_KEY/SECRET, TEST_BINANCE_API_KEY/SECRET
│
└── frontend/
    ├── src/
    │   ├── App.jsx                    # Routing: Dashboard | TradeLots | Reconciliation | Settings | Makro-Signal | Sentiment | API Docs
    │   ├── api/client.js              # Axios: Portfolio, Lots, Orders, Pairing, Sync, Reconciliation, Settings, Sentiment
    │   ├── components/
    │   │   ├── Dashboard.jsx          # 8 KPI-Kacheln (Break-even, P&L, BTC, EUR)
    │   │   ├── LotsTable.jsx          # Trade-Cockpit: Tabelle, Sort, Checkboxen, Pairing-Integration
    │   │   ├── LotFilters.jsx         # Filter-Bar (Status, Order Nr, Datum, Closed-Toggle)
    │   │   ├── OpenOrdersPanel.jsx    # Offene Sell Orders Tabelle
    │   │   ├── PairingPanel.jsx       # 2-Tab Panel: Vorschläge | Manuell + Routing zu Bestehende
    │   │   ├── PairingExistingTab.jsx # Tab "Bestehende Pairings" (Lifecycle, Mutations, Simulation)
    │   │   ├── SimulationModal.jsx    # Simulation Preview Overlay (presentational)
    │   │   ├── Reconciliation.jsx     # 3 Sektionen: Orders, Balances, Fills + Diskrepanzen
    │   │   ├── Settings.jsx           # Konfigurierbare Parameter (max_order_value_eur)
    │   │   ├── MacroSignal.jsx        # Makro-Signal Dashboard (4 Faktoren, Richtungsempfehlung)
    │   │   ├── Sentiment.jsx          # Sentiment Engine Dashboard (5 Pillars, Gauge, Empfehlung)
    │   │   ├── LotsTable.css
    │   │   ├── PairingPanel.css
    │   │   ├── Dashboard.css
    │   │   ├── Reconciliation.css
    │   │   ├── Settings.css
    │   │   ├── MacroSignal.css
    │   │   └── Sentiment.css
    │   ├── utils/
    │   │   └── formatters.js          # Shared: formatNumber, formatEUR, formatBTC, formatPct, formatDate, formatTime
    │   └── hooks/useLivePrice.js      # Binance Ticker Polling (10s)
    ├── package.json
    └── vite.config.js
```

## Entwicklungskommandos

### Backend
```bash
cd backend
source venv/bin/activate

# Server starten
uvicorn app.main:app --reload

# Tests
pytest
pytest tests/test_pairing.py              # Einzelne Datei
pytest --cov=app tests/                   # Mit Coverage

# Linting
ruff check . && black --check .
black . && ruff check --fix .             # Auto-Fix
```

### Sentiment Backtesting
```bash
cd backend
python scripts/backtest_sentiment.py --days 2000 --symbol BTCUSDT
```

### Frontend
```bash
cd frontend
npm install
npm run dev                               # Dev Server
npm run build                             # Production Build
npm run lint
```

### Datenbank
```bash
cd backend
alembic upgrade head                      # Migrationen ausführen
alembic revision --autogenerate -m "..."  # Neue Migration
alembic downgrade -1                      # Rollback
```

## API-Endpoints (Backend)

| Route | Methode | Beschreibung |
|-------|---------|--------------|
| `/api/portfolio/{user_id}` | GET | Portfolio-State (KPIs, Break-even, P&L) |
| `/api/lots/{user_id}` | GET | Lots mit Filter (status, from_date, to_date) |
| `/api/lots/{user_id}/sync` | POST | Binance Fills importieren |
| `/api/lots/{user_id}/{lot_id}` | GET | Lot-Detail + Allocations |
| `/api/lots/{user_id}/{lot_id}/auto-order` | PATCH | Auto-Order Toggle |
| `/api/orders/{user_id}/lot/{lot_id}/create` | POST | TAKE_PROFIT_LIMIT Sell Order erstellen |
| `/api/orders/{user_id}/list` | GET | Orders filtern (status, lot_id, pairing_id) |
| `/api/orders/{order_id}` | DELETE | Order stornieren |
| `/api/pairing/{user_id}/suggestions` | GET | Auto-Vorschläge (market_price, threshold_pct) |
| `/api/pairing/{user_id}/create` | POST | Pairing persistieren (items[], threshold_pct) |
| `/api/pairing/{user_id}/list` | GET | Pairings filtern (status) |
| `/api/pairing/{user_id}/simulate/{id}` | GET | Simulation durchführen |
| `/api/pairing/{user_id}/{id}/lock` | POST | DRAFT -> LOCKED |
| `/api/pairing/{user_id}/{id}/execute` | POST | LOCKED -> EXECUTED |
| `/api/pairing/{user_id}/{id}` | DELETE | Nur DRAFT löschbar |
| `/api/reconciliation/{user_id}/run` | POST | Vollständige Reconciliation (Orders + Balances + Fills) |
| `/api/reconciliation/{user_id}/orders` | POST | Order-Status mit Binance abgleichen |
| `/api/reconciliation/{user_id}/balances` | POST | Balances vergleichen (Binance vs. Ledger) |
| `/api/reconciliation/{user_id}/fills` | POST | Fills synchronisieren |
| `/api/settings/{user_id}` | GET | User-Settings laden (oder Defaults) |
| `/api/settings/{user_id}` | PUT | User-Settings speichern (upsert) |
| `/api/sentiment/{user_id}/current` | GET | Aktueller Sentiment Score v3 (5 Pillars, Dispersion, Volatility) |

## Architektur

### Schichtenmodell
```
API Routes (thin)  →  Services (DB + Binance)  →  Domain (pure, no I/O)
     ↓                       ↓                          ↓
  FastAPI              SQLAlchemy ORM            Dataclasses + Decimal
  Pydantic             python-binance            Deterministische Logik
```

### Domain-Logik (kein I/O, pure Funktionen)

**`domain/portfolio.py`** - `compute_portfolio_from_ledger(events, market_price)`:
- Zentrale Funktion, berechnet alle KPIs aus Ledger-Events
- WAC Break-even, realisierte/unrealisierte P&L, EUR/BTC Bestände

**`domain/lots.py`**:
- `create_trade_lot_from_buy_fill()` - 1 Fill = 1 Lot (Fees in EUR/BTC/BNB)
- `allocate_sell_with_strategy()` - Strategy-Aware Sell Allocation (FIFO/LIFO/HIGHEST_COST)
- `allocate_sell_fifo()` - FIFO Wrapper (Rueckwaertskompatibilitaet)
- `allocate_sell_to_lot()` - Lot-spezifische Allocation + Overflow nach konfigurierbarer Strategie
- `_sort_lots_by_strategy()` - Sortierung nach Strategie (FIFO: created_at asc, LIFO: created_at desc, HIGHEST_COST: break_even desc)

**`domain/pairing.py`**:
- `suggest_pairings(lots, market_price, threshold_pct)` - Heuristik v1
- `simulate_pairing(pairing, market_price, all_lots, fee_pct)` - Deterministische Simulation

**`domain/sentiment.py`** - Sentiment Engine v3 (pure, kein I/O):
- 5 korrelierte Pillars: DMA (42%), F&G (28%), Funding (20%), Taker (18%), Volume (12%)
- `compute_sentiment_v3(pillars, weights)` - Gewichtete Aggregation mit Renormalisierung bei fehlenden Pillars
- `compute_pillar_dispersion(scores)` - Confidence-Faktor (std=0 → 1.0, std≥30 → 0.0)
- `compute_volatility_scaling(daily_returns)` - Regime-Erkennung (HIGH/NORMAL/LOW)
- `compute_piecewise_linear_multiplier(score)` - Stetige Buy-Size-Empfehlung (1.5x Fear → 1.0x Neutral → 0.85x Greed)
- `get_recommendation_v3()` - Finaler Multiplikator: base × dispersion_confidence × volatility_scaling
- `rolling_percentile()`, `score_funding_rate()` - Pillar-Normalisierung
- Dataclasses: `PillarScore`, `DispersionInfo`, `VolatilityScaling`, `SentimentResultV3`, `SentimentRecommendationV3`

**`services/sentiment_data_service.py`** - Singleton mit TTL-Cache:
- Datenquellen: Alternative.me F&G (30min TTL), Binance Klines (5min TTL), OKX Funding Rate (15min TTL)
- 90-Tage Rolling Histories (deque) fuer Percentile-Scoring
- 120-Tage Daily Returns fuer Volatility Scaling
- `_initialize_history()` - Einmalige Population (300 Tage Klines)
- Graceful Degradation: Fehlende Quellen → Score 50, Quality "unavailable"
- Quality-Badges: "live", "cached", "stale" (6× TTL), "unavailable"

### Frontend-Komponenten

**LotsTable.jsx** - Hauptkomponente für Trade-Management:
- Tabelle mit 11 Spalten (Checkbox, Order Nr, Datum, Menge, Kosten, Break-even, Sell Order, P&L, Status)
- Summary-Cards: Kosten offener Positionen, Menge Offen, Erholungspreis (bei negativem Depoterfolg)
- Erholungspreis-KPI: Proportionaler Verkaufspreis bei dem alle Lots gemeinsam das Depot-Minus ausgleichen
  - Formel: `P = (total_qty × marktpreis + |deficit|) / (total_qty × (1 - fee_rate))`
  - Wird nur angezeigt wenn Depoterfolg < 0
- Delegiert an Subkomponenten: LotFilters, OpenOrdersPanel
- Sort: Datum, Break-even (client-side)
- Pairing: Checkbox-Selektion → PairingPanel (inline, aufklappbar)
- Live-P&L Berechnung mit marketPrice prop

**LotFilters.jsx** - Filter-Bar (extrahiert aus LotsTable):
- Order Nr (Text), Status (Select), Closed-Toggle, Datumsbereich, Reset-Button

**OpenOrdersPanel.jsx** - Offene Sell Orders (extrahiert aus LotsTable):
- Tabelle: Status, Preis, Menge, Referenz (Lot/Pairing), Erstellt
- "Unter Markt"-Warnung wenn Sell-Preis <= Marktpreis

**PairingPanel.jsx** - 3-Tab Pairing-UI:
- Tab "Vorschläge": Backend-Heuristik, Threshold-Input, Karten mit Netto-KPIs
- Tab "Manuell": Aus Checkbox-Auswahl, Live-Preview, "Pairing erstellen"
- Tab "Bestehende": Delegiert an PairingExistingTab

**PairingExistingTab.jsx** - Bestehende Pairings (extrahiert aus PairingPanel):
- DRAFT/LOCKED/EXECUTED Lifecycle mit eigenen Mutations (Lock/Unlock/Execute/Delete)
- Filter: Status, "Ausgeführte anzeigen"-Toggle
- Simulation-State + SimulationModal inline

**SimulationModal.jsx** - Simulation Preview (extrahiert aus PairingPanel):
- Presentational Overlay: Marktpreis, BTC, Erlös, Kosten, Fees, P&L, betroffene Lots
- Geplante Binance Order (aggregiert), Max-Value-Warnung

**Dashboard.jsx** - Portfolio-Übersicht:
- 8 KPI-Kacheln: Marktpreis, BTC Bestand, Break-even, Target, Unrealisiert/Realisiert P&L, EUR, Extern

**Reconciliation.jsx** - Datenabgleich Binance vs. Ledger:
- "Vollständige Reconciliation" Button + 3 Einzel-Buttons (Orders, Balances, Fills)
- Balances-Sektion: BTC/EUR Vergleichskarten (Binance vs. Berechnet, Differenz, Toleranz-Badge)
- Orders-Sektion: Sync-Stats + Diskrepanz-Tabelle
- Fills-Sektion: Neue Fills/Lots/Allocations Zähler
- useMutation für alle POST-Endpoints, Query-Invalidierung nach Erfolg

**Settings.jsx** - Konfigurierbare Parameter:
- Formular fuer `max_order_value_eur` (Default: 1000 EUR)
- Sell-Allocation Strategie (FIFO / LIFO / Hoechste Kosten) als Button-Group
- useQuery + useMutation fuer GET/PUT Settings-API

**MacroSignal.jsx** - Makro-Signal Dashboard:
- 4 Makro-Faktoren mit konfigurierbarer Richtungsempfehlung
- Intervall-Auswahl (1m/5m/15m) aus User-Settings
- Richtungseinfluss (bullish/bearish) visuell auf Indikator-Karten

**Sentiment.jsx** - Sentiment Engine Dashboard:
- Halbkreis-Gauge mit animierter Nadel (Fear ← Neutral → Greed)
- 5 Pillar-Karten: Score (0-100), Quality-Badge, Progress-Bar mit Gradient, Raw-Value, Erklaerung
- Empfehlungs-Karte: Action-Text + Buy-Size Multiplikator mit Breakdown (base × confidence × volatility)
- Analyse-Grid: Pillar Agreement (Confidence %), Volatility Regime (HIGH/NORMAL/LOW mit Scaling)
- TanStack Query mit 60s Refetch-Intervall
- Loading/Error States, Disclaimer Footer

### Datenmodell (Kern-Tabellen)

| Tabelle | Beschreibung |
|---------|--------------|
| `ledger_events` | Append-only Event-Log (TRADE_FILL, FEE, DEPOSIT, WITHDRAWAL, EXTERNAL_CASHFLOW, ADJUSTMENT) |
| `trade_lots` | BTC-Positionen (1 pro Buy-Fill): qty_initial, qty_open, cost_eur, break_even, status, auto_order |
| `sell_allocations` | FIFO Zuordnung: sell_fill_id, lot_id, qty_allocated, realized_pnl_eur |
| `orders` | Order-Tracking: client_order_id, binance_order_id, price, stop_price, linked_lot_id, linked_pairing_id |
| `pairings` | Virtuelle Bündelung: threshold_pct, status (DRAFT/LOCKED/EXECUTED) |
| `pairing_items` | N:M Pairing ↔ Lot: qty_btc, cost_eur (unterstützt Teilmengen) |
| `user_settings` | Konfigurierbare Parameter pro User: max_order_value_eur, sell_allocation_strategy (FIFO/LIFO/HIGHEST_COST) |

### Kritische Invarianten

1. Ledger ist **append-only** - Korrekturen nur via ADJUSTMENT Events
2. **Decimal überall** - niemals float für Geld/Preise
3. **1 Fill = 1 Lot** - deterministische Lot-Bildung, 1:1 Auditierbarkeit
4. **Sell Allocation Strategy** - konfigurierbar (FIFO/LIFO/HIGHEST_COST), deterministisch pro Strategie. Lot-spezifische und Pairing-spezifische Allocations ueberschreiben die Default-Strategie
5. **Idempotente Orders** - `clientOrderId` Format: `{userId}_{lotId}_{targetPrice}_{qty}_{version}`
6. **Simulation vor Execution** - Pairing-Ausführung erzwingt vorherige Simulation
7. Pairing-Lifecycle: **DRAFT → LOCKED → EXECUTED** (nur DRAFT löschbar)
8. Externe Cashflows beeinflussen **NICHT** die BTC-Kostenbasis
9. **TAKE_PROFIT_LIMIT** - Alle Sell Orders als Stop-Limit (stopPrice = price = targetPrice)
10. **Max Order-Wert** - Order-Erstellung abgelehnt wenn `qty * price > max_order_value_eur` (konfigurierbar via Settings)
11. **Test-Isolation** - Tests verwenden `TEST_BINANCE_API_KEY` + Testnet, nie Produktions-Keys
12. **Sentiment Scoring** - Korrelationsbasierte Gewichte (nicht gleich), Dispersion als Confidence, Volatility als Scaling - stetige piecewise-linear Multiplikatoren (keine Buckets/Cliff-Effekte)

## Styling-Konventionen (Frontend)

- **Kein UI-Framework** - Plain CSS, component-scoped (`Component.css`)
- **Farbschema**:
  - Navbar: Purple-Gradient (`#667eea` → `#764ba2`)
  - Profit: Grün `#16a34a`, Loss: Rot `#dc2626`
  - Pairing/Akzent: Indigo `#6366f1`
  - Reconciliation: Sky-Blue `#0ea5e9`
  - Sentiment: Teal `#0d9488` (Gauge-Gradient: Rot `#dc2626` → Slate `#64748b` → Gruen `#16a34a`)
  - Binance-Sync: Orange `#f7931a`
  - Neutrals: Slate-Palette (`#f8fafc`, `#e2e8f0`, `#64748b`, `#1e293b`)
- **Patterns**: Summary-Cards, Filter-Groups mit Labels, Toggle-Switches, Status-Badges, Sort-Icons

## Testing

**Backend (14 Testdateien):**
- `test_portfolio_breakeven.py` - WAC, Fees, Partial Sells
- `test_lots_fifo.py` - FIFO Allocation Deterministik
- `test_lots_strategies.py` - LIFO, HIGHEST_COST, Strategy-Routing, Overflow-Strategien (18 Tests)
- `test_lots_lot_specific.py` - Lot-spezifische Targets
- `test_lot_fee_handling.py` - Fee-Berechnung (EUR/BTC/BNB)
- `test_pairing.py` - Pairing-Heuristik, Thresholds
- `test_pairing_execution.py` - Simulation, Affected Lots
- `test_order_lifecycle.py` - Create → Fill → Closed
- `test_sync_lots.py` - Binance Sync
- `test_reconciliation.py` - Balance-Abgleich
- `test_csv_import.py` - CSV Import Validierung
- `test_timezone_handling.py` - Timezone Edge Cases
- `test_macro_signal.py` - Makro-Signal Berechnung
- `test_sentiment_v3.py` - Sentiment v3: Pillar Dispersion, Funding Scoring, Piecewise Multiplier, Volatility Scaling, Recommendation (45+ Tests)

**Test-Konfiguration (`tests/conftest.py`):**
- Alle Tests verwenden automatisch `TEST_BINANCE_API_KEY` statt Produktions-Keys
- `BINANCE_TESTNET=true` wird gesetzt (Testnet-Endpoint)
- Session-scoped, autouse Fixture

**Frontend:** Noch keine automatisierten Tests (geplant: Vitest)

## Sicherheit

- **API-Key Authentication** - Alle API-Routen geschuetzt via `X-API-Key` Header, konfigurierbar via `API_KEY` in `.env`
- **Niemals Secrets committen** - `.env` ist in `.gitignore`
- API-Keys verschlüsselt oder im Secret Manager
- Environment Variables für Konfiguration
- Strukturiertes Logging ohne Secret-Exposure
- **Test-Keys getrennt** - `TEST_BINANCE_API_KEY` in `.env`, automatisch via `conftest.py` verwendet
- **Max Order-Wert** - Konfigurierbares Limit pro User (Default: 1000 EUR, via Settings-Seite)
- **Transaction-Safety** - SQLAlchemy Sessions mit Auto-Commit/Rollback (`yield`-Pattern in `get_db()`)
- **Sentiment EU-Compliance** - OKX Funding Rate statt Binance Futures (MiCA-konform), alle Quellen oeffentlich (keine Extra-Credentials)

---

# Vollständige Spezifikation

## Konzeptionsdokument – BTC/EUR Cashflow-Management & Automation App (Binance Spot)
**Version:** 1.0
**Prinzip:** Ledger-first, deterministisch, auditierbar, automatisierbar.

---

## 1. Projektübersicht

Diese App liefert:
- **Transparenz** über Euro-Cashflow (intern auf Binance und extern via Bank/Off-Exchange).
- **Rentabilitätssteuerung** auf Portfolio- und Trade-Ebene.
- **Automatisierte Gewinnmitnahmen** über Binance Orders (Limit / optional Stop-Limit).
- **Virtuelle Trade-Verrechnung (Pairing)** zur Liquiditätsfreisetzung bei netto erreichter Zielmarge.

Nicht Ziel in v1:
- Futures/Margin/Derivate
- Multi-Exchange
- Steuerreporting nach nationalem Recht (nur Export/CSV als späteres Add-on)

---

## 2. Kernfunktionen

### 2.1 Break-Even-Analyse & Cashflow-Tracking

#### 2.1.1 Grundprinzip: Ledger statt "Saldo raten"
Alle Berechnungen basieren auf einem **append-only Ledger** (Ereignisstrom). Keine stillen Korrekturen, keine "Excel-Logik" im UI.

**Ledger-Event-Typen:**
- `TRADE_FILL` (Binance Ausführung)
- `FEE` (falls nicht im Fill enthalten)
- `DEPOSIT` / `WITHDRAWAL` (EUR/BTC, Binance)
- `EXTERNAL_CASHFLOW` (Bank rein/raus, manuell oder später via Import/API)
- `ADJUSTMENT` (Admin-Korrektur, immer als neues Event)

#### 2.1.2 Cashflow-Definitionen (EUR-Sicht)

**(A) Trading-Only (operativ)** - Binance Ledger-Events → Orders, Break-even, Bestände
**(B) Full Cashflow (wirtschaftlich)** - Binance + externe Cashflows → Gesamtperformance

KPIs: EUR verfügbar, BTC Bestand + Marktwert, External Net EUR, Realisierte/Unrealisierte P&L

#### 2.1.3 Break-even Berechnung (Portfolio)
- **Weighted Average Cost (WAC)** auf Portfolio-Ebene
- `portfolio_break_even = cost_basis_eur / btc_qty`
- Externe Cashflows verändern NICHT die BTC-Kostenbasis

#### 2.1.4 Ziel-Marge & Zielverkaufspreise
- `target_price = break_even * (1 + target_margin_pct) * (1 + fee_buffer_pct)`
- Kann global oder pro Lot gesetzt werden

### 2.2 Trade-Ebene-Management

#### 2.2.2 TradeLot-Bildung: 1 Fill = 1 Lot
- Jeder Buy-Fill erzeugt genau einen TradeLot
- Partial Fills → mehrere Lots (UI mit Gruppierung/Filter)

#### 2.2.3 TradeLot-Kennzahlen
- `qty_btc_initial`, `qty_btc_open`, `cost_eur`, `break_even`
- `unrealized_pnl_eur`, `unrealized_pnl_pct`
- Status: `OPEN` / `PARTIAL_CLOSED` / `CLOSED`

#### 2.2.4 Sell-Allocation: FIFO
- Älteste offene Lots zuerst schließen
- Allocation wird persistiert: `sell_fill_id`, `trade_lot_id`, `qty_allocated`, `realized_pnl_eur`

### 2.3 Virtuelles Pairing

#### 2.3.2 Pairing-Grundmodell
Ein Pairing = Set von TradeLots (ggf. Teilmengen).
- `net_pnl_pct >= threshold_pct` → verkaufsfähig

#### 2.3.3 Algorithmus (Heuristik v1)
1. Sortiere: Gewinner absteigend, Verlierer aufsteigend nach P&L%
2. Pro Gewinner: Verlierer hinzufügen bis Threshold erreicht
3. Ausgabe: Pairing-Vorschläge mit Netto-Effekt

#### 2.3.4 Simulation (Pflicht vor Ausführung)
Zeigt: betroffene Lots, erwartete P&L, Fees, verbleibende Bestände

#### 2.3.5 Execution: Order pro Lot
- Jede Lot-Schließung als separate Order (saubere Referenzierung)

### 2.4 Automatisierung (Binance Integration)

- **Order-Erstellung**: TAKE_PROFIT_LIMIT Sell (stopPrice = price = targetPrice)
- **Max Order-Wert**: Konfigurierbar via Settings (Default: 1000 EUR), Validierung vor Binance API Call
- **Sync**: Polling + inkrementell (v1), WebSocket (v2)
- **Idempotenz**: Deterministische `clientOrderId`
- **Safety**: Rate-Limit Backoff, Balance-Check, Auto-Order Toggle, Max-Order-Value-Check

---

## 3. UI Design-Vorgaben

### 3.1 Dashboard
8 KPI-Kacheln: EUR, BTC, Break-even, Target, Unrealisierte/Realisierte P&L, Externe Cashflows

### 3.2 Trade-Cockpit (LotsTable)
- Tabelle mit Checkbox (Pairing), Order Nr, Datum, Menge, Kosten, Break-even, Sell Order, P&L, Status
- Filter: Order Nr, Status, Datumsbereich, Closed-Toggle
- Pairing-Action-Bar + aufklappbares PairingPanel

### 3.3 Pairing-Screen (PairingPanel, inline)
- 3 Tabs: Vorschläge (auto) | Manuell (Checkbox-Auswahl) | Bestehende Pairings
- Simulation-Overlay: Modal mit KPIs, betroffenen Lots, verbleibendem Portfolio
- Lifecycle: DRAFT → Simulation → LOCKED → Simulation → EXECUTED

### 3.4 Reconciliation-Screen
- "Vollständige Reconciliation" Button + 3 Einzel-Buttons (Orders, Balances, Fills)
- Balances: BTC/EUR Vergleichskarten (Binance vs. Berechnet) mit Toleranz-Badge
- Orders: Sync-Stats + Diskrepanz-Tabelle
- Fills: Neue Fills/Lots/Allocations Zähler
- Sky-Blue Akzentfarbe (`#0ea5e9`)

### 3.5 Settings-Screen
- Formular für max_order_value_eur (Default: 1000 EUR)
- Erweiterbar für zukünftige Settings

---

### 2.5 Sentiment Engine (v3)

Krypto-spezifische Stimmungsanalyse, komplementaer zum MacroSignal (Makro-Richtung ≠ Sentiment-Sizing).

**5 Pillars (korrelationsbasierte Gewichte):**
| Pillar | Gewicht | Quelle | Beschreibung |
|--------|---------|--------|-------------|
| Trend-Deviation (DMA) | 42% | Binance Klines | Price Distance to 50-DMA + 200-DMA Regime-Filter |
| Fear & Greed Index | 28% | alternative.me | Emotional Sentiment (0-100) |
| Funding Rate | 20% | OKX Public API | Derivate-Hitze (EU-kompatibel, kein Binance Futures) |
| Taker Buy/Sell Ratio | 18% | Binance Klines | Orderflow-Indikator (7d avg) |
| Volume-Momentum | 12% | Binance Klines | Volume Ratio vs. 20d-Avg, richtungsangepasst |

**Scoring-Modell:**
- Rolling Percentile (90-Tage Historie) statt fixer Schwellwerte
- Pillar Dispersion als Confidence: std=0 → 1.0, std≥30 → 0.0 (lineare Daempfung)
- Volatility Scaling: HIGH (vol_ratio>1.5, komprimiert), NORMAL, LOW (vol_ratio<0.7, expandiert)
- Piecewise-Linear Multiplikator: 1.5x (Extreme Fear) → 1.0x (Neutral 40-60) → 0.85x (Extreme Greed)
- Finaler Multiplikator: base × dispersion_confidence × volatility_scaling

**Abgrenzung MacroSignal vs. SentimentEngine:**
- MacroSignal: Kurzfristige Richtung (1m/5m/15m), Score -2 bis +2
- SentimentEngine: Mittelfristiges Position-Sizing (taeglich/rollierend), Score 0-100

---

## 4. Offene Punkte
- Fee-Umrechnung: Fill-Preis vs separate Preisquelle
- Aggregierte Pairing-Orders (v1.1+)
- Frontend-Tests (Vitest)
- Auto-Order Trigger-Logik
- WebSocket für Realtime-Sync
- Sentiment History Persistierung (SentimentHistoryDB Tabelle + `/api/sentiment/{user_id}/history`)
- Combined Score: MacroSignal + Sentiment (Timing + Sizing)
- Social Sentiment (Twitter/X, Reddit via LunarCrush/Santiment)
- Echte On-Chain-Daten (Glassnode/CryptoQuant)

## 5. Akzeptanzkriterien
- Break-even und P&L reproduzierbar aus Ledger
- Lots und Sell-Allocations deterministisch (FIFO)
- Pairing liefert Simulation vor Execution
- Auto-Order erzeugt keine Doppelorders (Idempotenz via clientOrderId)
- UI bedienbar bei hoher Lot-Anzahl (Gruppierung/Filter)
- Sentiment Score reproduzierbar aus gleichen Rohdaten (deterministische Domain-Logik)
- Sentiment Graceful Degradation: System funktioniert mit 1-5 aktiven Pillars
- Sentiment EU-kompatibel: Keine geo-blockierten APIs (OKX statt Binance Futures)
