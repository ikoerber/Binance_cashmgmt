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
- Trade-Cockpit mit Filtern, Sortierung, Live-P&L, Sell-Order-Indikatoren
- Binance Sync (Fills Import, inkrementell)
- Order-Erstellung (TAKE_PROFIT_LIMIT Sell pro Lot) + Order-Tracking
- Pairing: Backend-Heuristik + Frontend-UI (Vorschläge, manuell, Simulation, Lifecycle)
- Reconciliation-Service + Reconciliation-UI (3 Sektionen: Orders, Balances, Fills)
- Settings-Seite (max_order_value_eur konfigurierbar)
- Live BTC/EUR Preis via Binance API

**Offen (Iteration 4-5):**
- Auto-Order Automation (Trigger-basiert)
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
│   │   │   ├── lots.py                # create_trade_lot_from_buy_fill(), allocate_sell_fifo()
│   │   │   └── pairing.py            # suggest_pairings(), simulate_pairing()
│   │   ├── services/                  # DB-Integration, Binance API
│   │   │   ├── binance.py            # Binance API Client
│   │   │   ├── sync_service.py       # Fills importieren
│   │   │   ├── lot_service.py        # Lot CRUD + FIFO
│   │   │   ├── order_service.py      # Order-Erstellung (TAKE_PROFIT_LIMIT)
│   │   │   ├── order_tracking_service.py # Order State Lifecycle
│   │   │   ├── pairing_service.py    # Pairing-Persistenz + Lifecycle
│   │   │   ├── portfolio_service.py  # Portfolio-State aus Ledger
│   │   │   └── reconciliation_service.py
│   │   ├── db/
│   │   │   ├── database.py           # SQLAlchemy Session
│   │   │   └── models.py             # ORM: LedgerEventDB, TradeLotDB, PairingDB, OrderDB, UserSettingsDB
│   │   └── api/routes/               # Thin HTTP Layer
│   │       ├── portfolio.py           # GET /api/portfolio/{user_id}
│   │       ├── lots.py                # GET/POST /api/lots/...
│   │       ├── orders.py             # POST/GET/DELETE /api/orders/...
│   │       ├── pairing.py            # GET/POST/DELETE /api/pairing/...
│   │       ├── cashflow.py           # External Cashflows
│   │       ├── sync.py               # Binance Sync
│   │       ├── reconciliation.py     # POST /api/reconciliation/...
│   │       └── settings.py           # GET/PUT /api/settings/{user_id}
│   ├── tests/                         # 11 Testdateien
│   │   └── conftest.py               # TEST_BINANCE_API_KEY + Testnet
│   ├── alembic/                       # DB-Migrationen
│   ├── requirements.txt
│   └── .env                           # DB_URL, BINANCE_API_KEY/SECRET, TEST_BINANCE_API_KEY/SECRET
│
└── frontend/
    ├── src/
    │   ├── App.jsx                    # Routing: Dashboard | TradeLots | Reconciliation | Settings | API Docs
    │   ├── api/client.js              # Axios: Portfolio, Lots, Orders, Pairing, Sync, Reconciliation, Settings
    │   ├── components/
    │   │   ├── Dashboard.jsx          # 8 KPI-Kacheln (Break-even, P&L, BTC, EUR)
    │   │   ├── LotsTable.jsx          # Trade-Cockpit: Filter, Sort, Checkboxen, Pairing-Integration
    │   │   ├── PairingPanel.jsx       # 3-Tab Panel: Vorschläge | Manuell | Bestehende + Simulation
    │   │   ├── Reconciliation.jsx     # 3 Sektionen: Orders, Balances, Fills + Diskrepanzen
    │   │   ├── Settings.jsx           # Konfigurierbare Parameter (max_order_value_eur)
    │   │   ├── LotsTable.css
    │   │   ├── PairingPanel.css
    │   │   ├── Dashboard.css
    │   │   ├── Reconciliation.css
    │   │   └── Settings.css
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
- `allocate_sell_fifo()` - FIFO Sell Allocation (deterministisch nach created_at)
- `allocate_sell_to_lot()` - Lot-spezifische Allocation + Overflow via FIFO

**`domain/pairing.py`**:
- `suggest_pairings(lots, market_price, threshold_pct)` - Heuristik v1
- `simulate_pairing(pairing, market_price, all_lots, fee_pct)` - Deterministische Simulation

### Frontend-Komponenten

**LotsTable.jsx** - Hauptkomponente für Trade-Management:
- Tabelle mit 11 Spalten (Checkbox, Order Nr, Datum, Menge, Kosten, Break-even, Sell Order, P&L, Status)
- Filter: Order Nr, Status, Datumsbereich, Closed-Toggle
- Sort: Datum, Break-even (client-side)
- Pairing: Checkbox-Selektion → PairingPanel (inline, aufklappbar)
- Live-P&L Berechnung mit marketPrice prop

**PairingPanel.jsx** - 3-Tab Pairing-UI:
- Tab "Vorschläge": Backend-Heuristik, Threshold-Input, Karten mit Netto-KPIs
- Tab "Manuell": Aus Checkbox-Auswahl, Live-Preview, "Pairing erstellen"
- Tab "Bestehende": DRAFT/LOCKED/EXECUTED Lifecycle, Simulation-Overlay
- Simulation: Modal mit Marktpreis, BTC, Erlös, Kosten, Fees, P&L, betroffene Lots

**Dashboard.jsx** - Portfolio-Übersicht:
- 8 KPI-Kacheln: Marktpreis, BTC Bestand, Break-even, Target, Unrealisiert/Realisiert P&L, EUR, Extern

**Reconciliation.jsx** - Datenabgleich Binance vs. Ledger:
- "Vollständige Reconciliation" Button + 3 Einzel-Buttons (Orders, Balances, Fills)
- Balances-Sektion: BTC/EUR Vergleichskarten (Binance vs. Berechnet, Differenz, Toleranz-Badge)
- Orders-Sektion: Sync-Stats + Diskrepanz-Tabelle
- Fills-Sektion: Neue Fills/Lots/Allocations Zähler
- useMutation für alle POST-Endpoints, Query-Invalidierung nach Erfolg

**Settings.jsx** - Konfigurierbare Parameter:
- Formular für `max_order_value_eur` (Default: 1000 EUR)
- useQuery + useMutation für GET/PUT Settings-API
- Erweiterbar für zukünftige Settings

### Datenmodell (Kern-Tabellen)

| Tabelle | Beschreibung |
|---------|--------------|
| `ledger_events` | Append-only Event-Log (TRADE_FILL, FEE, DEPOSIT, WITHDRAWAL, EXTERNAL_CASHFLOW, ADJUSTMENT) |
| `trade_lots` | BTC-Positionen (1 pro Buy-Fill): qty_initial, qty_open, cost_eur, break_even, status, auto_order |
| `sell_allocations` | FIFO Zuordnung: sell_fill_id, lot_id, qty_allocated, realized_pnl_eur |
| `orders` | Order-Tracking: client_order_id, binance_order_id, price, stop_price, linked_lot_id, linked_pairing_id |
| `pairings` | Virtuelle Bündelung: threshold_pct, status (DRAFT/LOCKED/EXECUTED) |
| `pairing_items` | N:M Pairing ↔ Lot: qty_btc, cost_eur (unterstützt Teilmengen) |
| `user_settings` | Konfigurierbare Parameter pro User: max_order_value_eur (Default: 1000 EUR) |

### Kritische Invarianten

1. Ledger ist **append-only** - Korrekturen nur via ADJUSTMENT Events
2. **Decimal überall** - niemals float für Geld/Preise
3. **1 Fill = 1 Lot** - deterministische Lot-Bildung, 1:1 Auditierbarkeit
4. **FIFO Allocation** - nach `created_at` sortiert, deterministisch
5. **Idempotente Orders** - `clientOrderId` Format: `{userId}_{lotId}_{targetPrice}_{qty}_{version}`
6. **Simulation vor Execution** - Pairing-Ausführung erzwingt vorherige Simulation
7. Pairing-Lifecycle: **DRAFT → LOCKED → EXECUTED** (nur DRAFT löschbar)
8. Externe Cashflows beeinflussen **NICHT** die BTC-Kostenbasis
9. **TAKE_PROFIT_LIMIT** - Alle Sell Orders als Stop-Limit (stopPrice = price = targetPrice)
10. **Max Order-Wert** - Order-Erstellung abgelehnt wenn `qty * price > max_order_value_eur` (konfigurierbar via Settings)
11. **Test-Isolation** - Tests verwenden `TEST_BINANCE_API_KEY` + Testnet, nie Produktions-Keys

## Styling-Konventionen (Frontend)

- **Kein UI-Framework** - Plain CSS, component-scoped (`Component.css`)
- **Farbschema**:
  - Navbar: Purple-Gradient (`#667eea` → `#764ba2`)
  - Profit: Grün `#16a34a`, Loss: Rot `#dc2626`
  - Pairing/Akzent: Indigo `#6366f1`
  - Reconciliation: Sky-Blue `#0ea5e9`
  - Binance-Sync: Orange `#f7931a`
  - Neutrals: Slate-Palette (`#f8fafc`, `#e2e8f0`, `#64748b`, `#1e293b`)
- **Patterns**: Summary-Cards, Filter-Groups mit Labels, Toggle-Switches, Status-Badges, Sort-Icons

## Testing

**Backend (11 Testdateien, 99 Tests):**
- `test_portfolio_breakeven.py` - WAC, Fees, Partial Sells
- `test_lots_fifo.py` - FIFO Allocation Deterministik
- `test_lots_lot_specific.py` - Lot-spezifische Targets
- `test_lot_fee_handling.py` - Fee-Berechnung (EUR/BTC/BNB)
- `test_pairing.py` - Pairing-Heuristik, Thresholds
- `test_pairing_execution.py` - Simulation, Affected Lots
- `test_order_lifecycle.py` - Create → Fill → Closed
- `test_sync_lots.py` - Binance Sync
- `test_reconciliation.py` - Balance-Abgleich
- `test_csv_import.py` - CSV Import Validierung
- `test_timezone_handling.py` - Timezone Edge Cases

**Test-Konfiguration (`tests/conftest.py`):**
- Alle Tests verwenden automatisch `TEST_BINANCE_API_KEY` statt Produktions-Keys
- `BINANCE_TESTNET=true` wird gesetzt (Testnet-Endpoint)
- Session-scoped, autouse Fixture

**Frontend:** Noch keine automatisierten Tests (geplant: Vitest)

## Sicherheit

- **Niemals Secrets committen** - `.env` ist in `.gitignore`
- API-Keys verschlüsselt oder im Secret Manager
- Environment Variables für Konfiguration
- Strukturiertes Logging ohne Secret-Exposure
- **Test-Keys getrennt** - `TEST_BINANCE_API_KEY` in `.env`, automatisch via `conftest.py` verwendet
- **Max Order-Wert** - Konfigurierbares Limit pro User (Default: 1000 EUR, via Settings-Seite)

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

## 4. Offene Punkte
- Fee-Umrechnung: Fill-Preis vs separate Preisquelle
- Alternative Sell Allocation Regeln (LIFO, Highest-cost-first) (v1.1+)
- Aggregierte Pairing-Orders (v1.1+)
- Frontend-Tests (Vitest)
- Auto-Order Trigger-Logik
- WebSocket für Realtime-Sync

## 5. Akzeptanzkriterien
- Break-even und P&L reproduzierbar aus Ledger
- Lots und Sell-Allocations deterministisch (FIFO)
- Pairing liefert Simulation vor Execution
- Auto-Order erzeugt keine Doppelorders (Idempotenz via clientOrderId)
- UI bedienbar bei hoher Lot-Anzahl (Gruppierung/Filter)
