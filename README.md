# BTC/EUR Cashflow Management & Automation App

Vollständiges ledger-basiertes, deterministisches Cashflow-Tracking und automatisiertes Trading-System für Binance Spot (BTC/EUR).

## Features

### Backend (Python + FastAPI)

- **Portfolio Management** - Ledger-first (append-only), WAC Break-even, realisierte/unrealisierte P&L, externe Cashflows
- **TradeLot Management** - 1 Fill = 1 Lot (deterministisch), FIFO Sell Allocation, Status-Lifecycle (OPEN → PARTIAL_CLOSED → CLOSED)
- **Intelligentes Pairing** - Virtuelles Bündeln von Gewinner-/Verlierer-Lots, Netto-Zielmarge, Pflicht-Simulation vor Execution
- **Auto-Order System** - TAKE_PROFIT_LIMIT Sell Orders auf Binance, idempotente clientOrderId, Max-Order-Wert-Limit
- **Binance Integration** - Fill-Synchronisation (idempotent), Account Balance, Market Price, Rate-Limit-aware
- **Reconciliation** - Abgleich Orders/Balances/Fills zwischen Binance und Ledger
- **Makro-Signal** - 4 konfigurierbare Makro-Faktoren mit Richtungsempfehlung
- **CSV Import** - Binance Spot Order History Import

### Frontend (React + Vite)

- **Dashboard** - 8 KPI-Kacheln: Marktpreis, BTC Bestand, Break-even, Target, Unrealisiert/Realisiert P&L, EUR, Extern
- **Trade-Cockpit** - Lots-Tabelle mit Filtern, Sortierung, Live-P&L, Sell-Order-Indikatoren, Erholungspreis-KPI
- **Pairing-Panel** - 3-Tab UI: Vorschläge, Manuell, Bestehende + Simulation-Overlay
- **Reconciliation** - 3 Sektionen: Orders, Balances, Fills mit Diskrepanz-Anzeige
- **Makro-Signal** - 4 Faktoren mit konfigurierbarem Intervall und Richtungsempfehlung
- **Settings** - Konfigurierbare Parameter (max_order_value_eur)
- **Live-Preis** - Binance Ticker Polling (10s)

## Tech Stack

**Backend:** Python 3.13, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL/SQLite, python-binance, pytest (156 Tests)
**Frontend:** React 19, Vite 7, TanStack Query, Axios, Plain CSS
**Infrastruktur:** Redis (geplant für Worker)

## Quick Start

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Environment
cp .env.example .env
# BINANCE_API_KEY und BINANCE_API_SECRET eintragen

# DB-Migrationen
alembic upgrade head

# Server starten
uvicorn app.main:app --reload
```

Backend: http://localhost:8000 | API Docs: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend: http://localhost:5173

### 3. Tests

```bash
cd backend
pytest                    # 156 Tests
pytest --cov=app tests/   # Mit Coverage
```

## API Endpoints

| Route | Methode | Beschreibung |
|-------|---------|--------------|
| `/api/portfolio/{user_id}` | GET | Portfolio-State (KPIs, Break-even, P&L) |
| `/api/lots/{user_id}` | GET | Lots mit Filter (status, from_date, to_date) |
| `/api/lots/{user_id}/sync` | POST | Binance Fills importieren |
| `/api/lots/{user_id}/{lot_id}` | GET | Lot-Detail + Allocations |
| `/api/orders/{user_id}/lot/{lot_id}/create` | POST | TAKE_PROFIT_LIMIT Sell Order |
| `/api/orders/{user_id}/list` | GET | Orders filtern |
| `/api/pairing/{user_id}/suggestions` | GET | Auto-Vorschläge |
| `/api/pairing/{user_id}/create` | POST | Pairing erstellen |
| `/api/pairing/{user_id}/simulate/{id}` | GET | Simulation |
| `/api/reconciliation/{user_id}/run` | POST | Vollständige Reconciliation |
| `/api/settings/{user_id}` | GET/PUT | User-Settings |
| `/api/macro/{user_id}/signals` | GET | Makro-Signale |

## Architektur

```
cashmgnt/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI App
│   │   ├── domain/                    # Pure Business Logic (kein I/O)
│   │   │   ├── models.py             # Domain Models (Dataclasses)
│   │   │   ├── portfolio.py           # Portfolio-Berechnung (WAC)
│   │   │   ├── lots.py                # TradeLot + FIFO Logic
│   │   │   ├── pairing.py            # Pairing-Algorithmus
│   │   │   └── macro_signal.py        # Makro-Faktoren Analyse
│   │   ├── services/                  # Integration Layer (DB + Binance)
│   │   ├── db/                        # SQLAlchemy ORM + Session
│   │   └── api/routes/                # Thin HTTP Layer
│   ├── tests/                         # 12 Testdateien, 156 Tests
│   └── alembic/                       # DB-Migrationen
│
└── frontend/
    ├── src/
    │   ├── App.jsx                    # Routing + Live-Preis
    │   ├── api/client.js              # Axios API Client
    │   ├── components/
    │   │   ├── Dashboard.jsx          # 8 KPI-Kacheln
    │   │   ├── LotsTable.jsx          # Trade-Cockpit + Erholungspreis
    │   │   ├── PairingPanel.jsx       # 3-Tab Pairing UI
    │   │   ├── Reconciliation.jsx     # Binance vs. Ledger Abgleich
    │   │   ├── Settings.jsx           # User-Konfiguration
    │   │   └── MacroSignal.jsx        # Makro-Signal Dashboard
    │   └── hooks/useLivePrice.js      # Binance Ticker Polling
    └── package.json
```

## Kernprinzipien

1. **Ledger-First** - Alle Zustandsänderungen via append-only Events
2. **Deterministisch** - Jede Kennzahl reproduzierbar aus Ledger + Regeln
3. **Decimal-Präzision** - Niemals float für Geld/Preise
4. **Idempotent** - Orders mit deterministischer clientOrderId
5. **FIFO Allocation** - Älteste offene Lots zuerst schließen
6. **Simulation vor Execution** - Pairing-Ausführung nur nach Preview

## Lizenz

Internes Projekt
