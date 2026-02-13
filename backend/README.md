# BTC/EUR Cashflow Management - Backend

Backend API für ledger-basiertes Cashflow-Tracking und automatisiertes Trading auf Binance Spot.

## Features (Iteration 1 + 2)

✅ **Iteration 1: Ledger + Portfolio Break-even**
- Append-only Ledger für alle Ereignisse
- Portfolio Break-even Berechnung (Weighted Average Cost)
- Realisierte und unrealisierte P&L
- Externe Cashflow-Tracking
- Binance API Integration

✅ **Iteration 2: TradeLots + FIFO Allocation**
- 1 Fill = 1 Lot (deterministisch)
- FIFO Sell Allocation
- TradeLot-Management (OPEN/PARTIAL_CLOSED/CLOSED)
- Automatischer Sync: Binance Fills → Ledger → TradeLots

## Setup

### 1. Virtual Environment erstellen

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Dependencies installieren

```bash
# Für Tests (keine DB-Dependencies)
pip install -r requirements-test.txt

# Für Full Stack (inkl. PostgreSQL)
pip install -r requirements.txt
```

### 3. Environment Variables

Kopiere `.env.example` zu `.env` und fülle die Werte:

```bash
cp .env.example .env
```

Beispiel `.env`:
```
DATABASE_URL=sqlite:///./cashmgnt.db
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
BINANCE_TESTNET=true
```

**WICHTIG:** Niemals `.env` committen!

### 4. Development Server starten

```bash
uvicorn app.main:app --reload
```

API läuft auf: http://localhost:8000

Docs (Swagger): http://localhost:8000/docs

## Tests ausführen

```bash
# Alle Tests
pytest

# Mit Coverage
pytest --cov=app tests/

# Spezifische Tests
pytest tests/test_portfolio_breakeven.py -v
pytest tests/test_lots_fifo.py -v
```

## API Endpoints

### Portfolio

**GET** `/api/portfolio/{user_id}?market_price={price}`
- Holt Portfolio-Zustand
- Berechnet Break-even, P&L, Zielpreise

### TradeLots

**GET** `/api/lots/{user_id}?status=OPEN&limit=100&offset=0`
- Liste TradeLots
- Filter nach Status: OPEN, PARTIAL_CLOSED, CLOSED
- Pagination

**GET** `/api/lots/{user_id}/{lot_id}`
- Lot-Details inkl. Sell-Allocations

### Sync

**POST** `/api/sync/{user_id}/fills?symbol=BTCEUR&start_time=2024-01-01T00:00:00`
- Synchronisiert Fills von Binance
- Erstellt automatisch Ledger Events + TradeLots
- Führt FIFO Allocation für Sells durch
- Idempotent (Doppel-Sync safe)

## Architektur

```
app/
├── domain/          # Pure Business Logic (kein I/O)
│   ├── models.py    # Domain Models (LedgerEvent, TradeLot, etc.)
│   ├── portfolio.py # Portfolio-Berechnungen
│   └── lots.py      # TradeLot + FIFO Allocation Logic
├── db/              # Database Layer
│   ├── models.py    # SQLAlchemy Models
│   └── database.py  # DB Connection
├── api/routes/      # FastAPI Endpoints
│   ├── portfolio.py
│   ├── lots.py
│   └── sync.py
├── services/        # Integration Layer
│   ├── portfolio_service.py
│   ├── lot_service.py
│   ├── binance.py   # Binance API Client
│   └── sync_service.py  # Sync-Orchestration
└── main.py          # FastAPI App
```

**Prinzipien:**
- Domain-First: Pure Business Logic ohne Side-Effects
- Append-only Ledger: Keine stillen Mutationen
- Decimal everywhere: Kein Float für Geld/Preise
- Idempotenz: Retry-safe
- Testbar: Unit Tests für alle Domain-Logik

## Workflow-Beispiel

### 1. User erstellen (TODO: Auth Endpoint)

Für jetzt: Direkt in DB oder via Python

### 2. Binance Fills synchronisieren

```bash
curl -X POST "http://localhost:8000/api/sync/user_123/fills?symbol=BTCEUR"
```

Response:
```json
{
  "status": "success",
  "new_fills": 10,
  "new_lots": 6,
  "allocations": 4,
  "message": "Synced 10 fills, created 6 lots, 4 allocations"
}
```

### 3. Portfolio-Status abrufen

```bash
curl "http://localhost:8000/api/portfolio/user_123?market_price=50000"
```

Response:
```json
{
  "timestamp": "2024-01-10T12:00:00",
  "btc_qty": "0.05",
  "btc_cost_basis_eur": "2500.00",
  "break_even": "50000.00",
  "market_price": "52000.00",
  "unrealized_pnl_eur": "100.00",
  "realized_pnl_eur": "50.00",
  "target_price": "52500.00"
}
```

### 4. TradeLots abrufen

```bash
curl "http://localhost:8000/api/lots/user_123?status=OPEN"
```

Response:
```json
{
  "lots": [
    {
      "id": "lot_fill_1",
      "qty_btc_open": "0.01",
      "cost_eur": "500.00",
      "break_even": "50000.00",
      "status": "OPEN",
      "created_at": "2024-01-01T12:00:00"
    }
  ],
  "count": 1
}
```

## Nächste Schritte (Iteration 3+)

- [ ] Pairing-Algorithmus + Simulation
- [ ] Auto-Order Erstellung (Limit Sell)
- [ ] WebSocket für Realtime Updates
- [ ] Frontend (React + TanStack Query)
- [ ] User Authentication & Management
- [ ] Reconciliation & Drift Detection

## Troubleshooting

### `psycopg2` Installation schlägt fehl

Für Development: Verwende SQLite statt PostgreSQL
```bash
DATABASE_URL=sqlite:///./cashmgnt.db
```

Oder installiere PostgreSQL-Dev-Tools:
```bash
# macOS
brew install postgresql

# Ubuntu
sudo apt-get install libpq-dev
```

### Tests schlagen fehl

Stelle sicher, dass du im venv bist:
```bash
source venv/bin/activate
pytest
```

## Lizenz

Internes Projekt
