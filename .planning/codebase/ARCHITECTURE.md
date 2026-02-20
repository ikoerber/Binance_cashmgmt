# Architecture

## Pattern: Layered Architecture (3-Tier)

```
API Routes (thin HTTP)  →  Services (DB + external APIs)  →  Domain (pure, no I/O)
     FastAPI                  SQLAlchemy + python-binance         Dataclasses + Decimal
     Pydantic validation      Session management                  Deterministic logic
```

**Principle:** Domain layer has zero I/O dependencies. All calculations are pure functions operating on dataclasses. Services bridge domain logic with database and external APIs.

## Layer Details

### 1. API Routes (`backend/app/api/routes/`)
- **Responsibility:** HTTP request/response handling, input validation, error sanitization
- **Pattern:** Thin controllers — parse request, call service, return response
- **Auth:** All routes protected via `require_api_key` dependency (`X-API-Key` header)
- **Error handling:** Generic error messages to client (`"Interner Serverfehler"`), `logger.exception()` server-side
- **Entry point:** `backend/app/main.py` — FastAPI app with lifespan, CORS, route registration

### 2. Services (`backend/app/services/`)
- **Responsibility:** Database queries, external API calls, orchestration
- **Pattern:** Functions receiving `db: Session` + parameters, calling domain functions
- **Transaction safety:** `get_db()` uses yield pattern — auto-commit on success, rollback on exception
- **Key services:**
  - `portfolio_service.py` — Portfolio KPIs from ledger + Binance balances
  - `sync_service.py` — Binance fills import (incremental, historical fee conversion)
  - `lot_service.py` — Lot CRUD + sell allocation
  - `pairing_service.py` — Pairing lifecycle with row-level locking
  - `order_service.py` — TAKE_PROFIT_LIMIT order creation
  - `orderblock_data_service.py` — Singleton with TTL cache, Binance kline fetching
  - `websocket_manager.py` — Binance WebSocket streams (ticker, user data)

### 3. Domain (`backend/app/domain/`)
- **Responsibility:** Pure business logic, no I/O, no database
- **Pattern:** Functions operating on dataclasses, returning dataclasses
- **Key modules:**
  - `portfolio.py` — `compute_portfolio_from_ledger()` — central WAC calculation
  - `lots.py` — Lot creation, sell allocation (FIFO/LIFO/HIGHEST_COST)
  - `pairing.py` — Pairing heuristic v1.2, simulation
  - `sentiment.py` — 5-pillar scoring, dispersion, volatility scaling
  - `orderblock.py` — 5-phase detection pipeline, conviction scoring
  - `combined_score.py` — Unified score (-100 to +100) from macro + sentiment

## Data Flow Examples

### Portfolio Query
```
GET /api/portfolio/{user_id}?market_price=X&symbol=BTCEUR
  → routes/portfolio.py: validate params, call service
    → portfolio_service.get_portfolio_state():
      1. Fetch Binance balances (optional, single source of truth)
      2. Query tracked lots from DB (symbol-filtered)
      3. Query ledger events from DB (symbol + NULL filtered)
      4. Call domain: compute_portfolio_from_ledger(events, symbol)
      5. Compute depot_pnl_quote = realized + unrealized
      6. Return dict with KPIs
```

### Binance Sync
```
POST /api/lots/{user_id}/sync?symbol=BTCEUR
  → sync_service:
    1. Fetch fills from Binance API (incremental, since last sync)
    2. Per fill: create LedgerEvent + TradeLot (1 fill = 1 lot)
    3. Per fill: convert BNB fees to EUR via historical kline price
    4. Sell fills: allocate via configurable strategy (FIFO/LIFO/HIGHEST_COST)
    5. Abort-on-error: if any allocation fails, stop loop (preserves FIFO invariant)
```

### WebSocket Real-time
```
Binance WebSocket → websocket_manager.py
  → executionReport: websocket_fill_handler.py
    → Create lot + allocate sells (same as sync, but real-time)
  → ticker: broadcast price to connected frontend clients
  → balanceUpdate: broadcast to frontend for query invalidation
```

## Frontend Architecture

### Component Hierarchy
```
App.jsx (BrowserRouter, QueryClient, WebSocketProvider, UserProvider)
├── GlobalNav.jsx (cross-symbol navigation)
├── Overview.jsx (aggregated multi-symbol dashboard)
├── SymbolLayout.jsx (per-symbol context via URL param :symbol)
│   ├── Dashboard.jsx (8 KPI tiles)
│   ├── LotsTable.jsx (trade cockpit)
│   │   ├── LotFilters.jsx
│   │   ├── LotSummaryCards.jsx
│   │   ├── OpenOrdersPanel.jsx
│   │   └── PairingPanel.jsx → PairingExistingTab.jsx, SimulationModal.jsx
│   ├── CombinedScore.jsx (macro 60% + sentiment 40%)
│   ├── Orderblock.jsx → OrderblockChart.jsx, OrderblockFilters.jsx, ...
│   └── Reconciliation.jsx
├── Settings.jsx (global)
└── FillNotification.jsx (WebSocket toasts)
```

### State Management
- **Server state:** TanStack Query (React Query) — all API data
- **URL state:** React Router search params for filters/sort (persisted across navigation)
- **WebSocket state:** WebSocketContext provides prices, balance updates, fill notifications
- **Symbol context:** SymbolContext extracts active symbol from URL (`/s/:symbol`)
- **No client-side store** (no Redux/Zustand) — server state via React Query is sufficient

### Routing
```
/                     → Overview (multi-symbol aggregate)
/s/:symbol            → SymbolLayout → Dashboard
/s/:symbol/lots       → LotsTable
/s/:symbol/combined   → CombinedScore
/s/:symbol/orderblock → Orderblock
/s/:symbol/reconciliation → Reconciliation
/settings             → Settings (global)
```

## Key Abstractions

### Ledger (Append-Only Event Store)
- All financial calculations derive from `ledger_events` table
- Event types: TRADE_FILL, FEE, DEPOSIT, WITHDRAWAL, EXTERNAL_CASHFLOW, ADJUSTMENT
- Corrections only via ADJUSTMENT events (never mutate existing events)
- Symbol field enables cross-pair isolation (legacy events with symbol=NULL still accepted)

### TradeLot (1 Fill = 1 Lot)
- Each buy fill creates exactly one lot — deterministic, auditable
- Lot tracks: qty_initial, qty_open, cost, break_even, status (OPEN/PARTIAL_CLOSED/CLOSED)
- Sell allocation: configurable strategy closes lots (FIFO by default)

### Pairing (Virtual Bundling)
- Groups multiple lots for combined sell at threshold margin
- Lifecycle: DRAFT → LOCKED → EXECUTED (only DRAFT deletable)
- Row-level locking prevents race conditions

### Symbol Registry (`backend/app/symbol_registry.py`, `frontend/src/utils/symbolRegistry.js`)
- Maps trading pairs to base/quote assets (BTCEUR → BTC/EUR)
- Dynamic precision per symbol (BTC: 8 decimals, XRP: 2, etc.)
- Single source of truth for multi-symbol support

## Database

- **Engine:** SQLite with Alembic migrations (`render_as_batch=True` for full compatibility)
- **ORM:** SQLAlchemy 2 declarative models in `backend/app/db/models.py`
- **Session:** Yield-based dependency injection with auto-commit/rollback
- **Key tables:** ledger_events, trade_lots, sell_allocations, orders, pairings, pairing_items, user_settings, orderblock_zones, backtest_runs
