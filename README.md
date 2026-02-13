# BTC/EUR Cashflow Management & Automation App

Vollständiges ledger-basiertes, deterministisches Cashflow-Tracking und automatisiertes Trading-System für Binance Spot (BTC/EUR).

## 🎉 Status: Vollständig implementiert!

**Alle 4 Iterationen abgeschlossen:**
- ✅ Iteration 1: Ledger + Portfolio Break-even
- ✅ Iteration 2: TradeLots + FIFO Allocation
- ✅ Iteration 3: Pairing + Simulation
- ✅ Iteration 4: Auto-Orders + Frontend

## Features

### Backend (Python + FastAPI)

#### 📊 Portfolio Management
- Ledger-first Architecture (append-only)
- Weighted Average Cost (WAC) Break-even
- Realisierte & unrealisierte P&L
- Externe Cashflow-Tracking
- **30 Unit Tests** (alle grün ✅)

#### 🎯 TradeLot Management
- 1 Fill = 1 Lot (deterministisch)
- FIFO Sell Allocation
- Lot-Status: OPEN → PARTIAL_CLOSED → CLOSED
- Detaillierte P&L pro Lot

#### 🔀 Intelligentes Pairing
- Virtuelles Bündeln von Gewinner-/Verlierer-Lots
- Netto-Zielmarge Berechnung
- Pflicht-Simulation vor Execution
- Robuste Heuristik v1

#### 🤖 Auto-Order System
- Limit-Sell-Orders auf Binance
- Idempotente clientOrderId
- Zielpreis-Berechnung mit Fee-Puffer
- Order-Management (Create, Cancel, Status)

#### 🔄 Binance Integration
- Fill-Synchronisation (idempotent)
- Account Balance
- Market Price
- Rate-Limit-aware

### Frontend (React + Vite)

#### 📈 Dashboard
- Portfolio-KPIs Übersicht
- BTC Bestand & Marktwert
- Break-even & Zielpreise
- Realisierte/Unrealisierte P&L
- Auto-Refresh (30s)

## Tech Stack

**Backend:**
- Python 3.13
- FastAPI
- SQLAlchemy + Alembic
- PostgreSQL / SQLite
- python-binance
- pytest (30 Tests)

**Frontend:**
- React 18
- Vite
- TanStack Query
- Axios
- CSS3

## Quick Start

### 1. Backend starten

```bash
cd backend

# Virtual Environment
python3 -m venv venv
source venv/bin/activate

# Dependencies (Tests only)
pip install -r requirements-test.txt

# Tests ausführen
pytest  # 30/30 Tests grün ✅

# Environment
cp .env.example .env
# Fülle BINANCE_API_KEY und BINANCE_API_SECRET

# Server starten
uvicorn app.main:app --reload
```

Backend läuft auf: http://localhost:8000
Docs: http://localhost:8000/docs

### 2. Frontend starten

```bash
cd frontend

# Dependencies
npm install

# Environment
cp .env.example .env

# Dev Server
npm run dev
```

Frontend läuft auf: http://localhost:5173

## API Endpoints

### Portfolio
- `GET /api/portfolio/{user_id}?market_price={price}`

### TradeLots
- `GET /api/lots/{user_id}?status=OPEN&limit=100`
- `GET /api/lots/{user_id}/{lot_id}`

### Pairing
- `GET /api/pairing/{user_id}/suggestions?market_price={price}&threshold_pct=0.05`
- `GET /api/pairing/{user_id}/simulate/{pairing_id}?market_price={price}`

### Orders
- `POST /api/orders/{user_id}/lot/{lot_id}/create?target_margin_pct=0.05`
- `GET /api/orders/open?symbol=BTCEUR`
- `DELETE /api/orders/{order_id}?symbol=BTCEUR`

### Sync
- `POST /api/sync/{user_id}/fills?symbol=BTCEUR`

## Architektur

```
cashmgnt/
├── backend/                # Python Backend
│   ├── app/
│   │   ├── domain/        # 🎯 Pure Business Logic
│   │   │   ├── models.py       # Domain Models
│   │   │   ├── portfolio.py    # Portfolio Calculations
│   │   │   ├── lots.py          # TradeLot + FIFO Logic
│   │   │   └── pairing.py       # Pairing Algorithm
│   │   ├── db/            # 💾 Database Layer
│   │   │   ├── models.py        # SQLAlchemy Models
│   │   │   └── database.py      # DB Connection
│   │   ├── api/routes/    # 🌐 API Endpoints
│   │   │   ├── portfolio.py
│   │   │   ├── lots.py
│   │   │   ├── pairing.py
│   │   │   ├── orders.py
│   │   │   └── sync.py
│   │   ├── services/      # 🔧 Integration Layer
│   │   │   ├── portfolio_service.py
│   │   │   ├── lot_service.py
│   │   │   ├── pairing_service.py
│   │   │   ├── order_service.py
│   │   │   ├── binance.py
│   │   │   └── sync_service.py
│   │   └── main.py        # FastAPI App
│   ├── tests/             # ✅ 30 Unit Tests
│   │   ├── test_portfolio_breakeven.py  (10 Tests)
│   │   ├── test_lots_fifo.py            (11 Tests)
│   │   └── test_pairing.py              (9 Tests)
│   ├── requirements.txt
│   └── README.md
│
├── frontend/              # React Frontend
│   ├── src/
│   │   ├── api/
│   │   │   └── client.js       # API Client
│   │   ├── components/
│   │   │   ├── Dashboard.jsx   # Portfolio Dashboard
│   │   │   └── Dashboard.css
│   │   ├── App.jsx
│   │   └── App.css
│   ├── package.json
│   └── README.md
│
└── CLAUDE.md              # Entwicklungsanleitung (German)
```

## Kernprinzipien

### 1. Ledger-First
Alle Zustandsänderungen gehen durch append-only Ledger Events:
- `TRADE_FILL` - Binance Fills
- `DEPOSIT` / `WITHDRAWAL` - Binance Wallet
- `EXTERNAL_CASHFLOW` - Bank Transfers
- `ADJUSTMENT` - Admin Korrekturen

### 2. Deterministisch
Jede Kennzahl ist reproduzierbar aus Ledger + Regeln:
- Portfolio Break-even = f(Ledger Events)
- TradeLots = f(Buy Fills)
- FIFO Allocation = deterministisch (älteste Lots zuerst)

### 3. Decimal-Präzision
**Niemals float für Geld/Preise!**
```python
from decimal import Decimal
price = Decimal("50000.00")  # ✅
price = 50000.0              # ❌
```

### 4. Idempotent
Orders mit deterministischer `clientOrderId`:
```python
client_order_id = f"{user_id}_{lot_id}_{target_price}_{qty}_{version}"
```
→ Retry-safe, keine Doppel-Orders

### 5. Separation of Concerns
- Domain = Pure Logic (kein I/O)
- Services = Integration (DB, API)
- API = HTTP Interface

## Tests

```bash
cd backend
pytest

# Output:
# test_portfolio_breakeven.py  10 passed ✅
# test_lots_fifo.py            11 passed ✅
# test_pairing.py               9 passed ✅
# ================================
# 30 passed in 0.05s
```

## Workflow-Beispiel

### 1. Binance Fills synchronisieren

```bash
curl -X POST "http://localhost:8000/api/sync/user_123/fills?symbol=BTCEUR"
```

Response:
```json
{
  "status": "success",
  "new_fills": 10,
  "new_lots": 6,
  "allocations": 4
}
```

### 2. Portfolio abrufen

```bash
curl "http://localhost:8000/api/portfolio/user_123?market_price=50000"
```

### 3. Pairing-Vorschläge

```bash
curl "http://localhost:8000/api/pairing/user_123/suggestions?market_price=50000&threshold_pct=0.05"
```

### 4. Auto-Order erstellen

```bash
curl -X POST "http://localhost:8000/api/orders/user_123/lot/lot_fill_1/create?target_margin_pct=0.05"
```

## Nächste Schritte (Optional)

- [ ] Pairing-Execution implementieren
- [ ] WebSocket für Live-Preise
- [ ] TradeLots Tabelle im Frontend
- [ ] Charts (P&L Historie)
- [ ] User Authentication
- [ ] Reconciliation Jobs
- [ ] Monitoring/Alerting

## Lizenz

Internes Projekt

---

**Entwickelt mit Claude Code** 🤖
