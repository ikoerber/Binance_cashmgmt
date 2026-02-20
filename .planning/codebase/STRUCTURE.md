# Structure

## Directory Layout

```
cashmgnt/
├── backend/
│   ├── app/
│   │   ├── main.py                              # FastAPI app, lifespan, route registration
│   │   ├── symbol_registry.py                   # Symbol → base/quote asset mapping, precision
│   │   ├── domain/                              # Pure business logic (no I/O)
│   │   │   ├── models.py                        # Dataclasses: LedgerEvent, TradeLot, PortfolioState, etc.
│   │   │   ├── portfolio.py                     # compute_portfolio_from_ledger(), compute_daily_performance()
│   │   │   ├── lots.py                          # Lot creation, sell allocation (FIFO/LIFO/HIGHEST_COST)
│   │   │   ├── pairing.py                       # suggest_pairings(), simulate_pairing()
│   │   │   ├── orders.py                        # Order domain logic
│   │   │   ├── lot_merge.py                     # Lot merge detection
│   │   │   ├── macro_signal.py                  # Macro factor analysis
│   │   │   ├── sentiment.py                     # 5-pillar sentiment scoring
│   │   │   ├── combined_score.py                # Unified score (-100 to +100)
│   │   │   ├── orderblock.py                    # 5-phase detection, conviction scoring (or orderblock/)
│   │   │   └── orderblock_backtest.py           # Triple-barrier backtesting
│   │   ├── services/                            # DB + external API integration
│   │   │   ├── binance.py                       # Binance API client (REST)
│   │   │   ├── binance_public_client.py         # Public endpoints (no auth)
│   │   │   ├── sync_service.py                  # Fills import, fee conversion
│   │   │   ├── lot_service.py                   # Lot CRUD + allocation
│   │   │   ├── order_service.py                 # Order creation (TAKE_PROFIT_LIMIT)
│   │   │   ├── order_tracking_service.py        # Order state lifecycle
│   │   │   ├── pairing_service.py               # Pairing persistence + row-level locking
│   │   │   ├── portfolio_service.py             # Portfolio state from ledger + Binance
│   │   │   ├── reconciliation_service.py        # Binance ↔ Ledger reconciliation
│   │   │   ├── cashflow_service.py              # External cashflow management
│   │   │   ├── csv_import_service.py            # CSV import for grid bot trades
│   │   │   ├── macro_data_service.py            # Macro data fetching
│   │   │   ├── sentiment_data_service.py        # Sentiment data (F&G, Klines, Funding)
│   │   │   ├── combined_score_service.py        # Combined score orchestration
│   │   │   ├── orderblock_data_service.py       # Kline fetching, detection orchestration, TTL cache
│   │   │   ├── orderblock_persistence_service.py # Zone CRUD, backtest persistence
│   │   │   ├── orderblock_config_service.py     # 3-tier config resolution
│   │   │   ├── websocket_manager.py             # Binance WebSocket streams
│   │   │   ├── websocket_event_handler.py       # WebSocket event dispatch
│   │   │   └── websocket_fill_handler.py        # Real-time fill processing
│   │   ├── api/
│   │   │   ├── auth.py                          # API key authentication dependency
│   │   │   └── routes/                          # Thin HTTP controllers (15 route modules)
│   │   │       ├── portfolio.py, lots.py, orders.py, pairing.py
│   │   │       ├── sync.py, reconciliation.py, cashflow.py
│   │   │       ├── settings.py, macro.py, sentiment.py, combined.py
│   │   │       ├── orderblock.py, websocket.py
│   │   │       └── __init__.py
│   │   └── db/
│   │       ├── database.py                      # Engine init, session management (yield pattern)
│   │       └── models.py                        # ORM models (SQLAlchemy declarative)
│   ├── tests/                                   # 22 test files, ~10600 lines, 569+ tests
│   │   ├── conftest.py                          # Test key setup, shared factories
│   │   ├── test_portfolio_breakeven.py          # WAC, fees, partial sells
│   │   ├── test_portfolio_cross_pair.py         # Multi-symbol isolation
│   │   ├── test_lots_fifo.py                    # FIFO allocation
│   │   ├── test_lots_strategies.py              # LIFO, HIGHEST_COST
│   │   ├── test_sentiment_v3.py                 # 45+ sentiment tests
│   │   ├── test_orderblock_detection.py         # Detection pipeline
│   │   ├── test_orderblock_backtest.py          # Backtesting
│   │   └── ... (14 more test files)
│   ├── alembic/                                 # Database migrations
│   │   ├── alembic.ini
│   │   └── versions/                            # Migration scripts
│   ├── scripts/
│   │   ├── backtest_sentiment.py                # Sentiment backtesting script
│   │   └── backtest_orderblock.py               # Orderblock parameter sweep
│   ├── requirements.txt                         # Pinned dependencies
│   └── .env                                     # Secrets (not committed)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                              # Root: routing, providers
│   │   ├── App.css                              # Global styles
│   │   ├── api/
│   │   │   └── client.js                        # Axios API client (all endpoints)
│   │   ├── components/                          # 30 component files
│   │   │   ├── Overview.jsx + .css              # Multi-symbol aggregate dashboard
│   │   │   ├── GlobalNav.jsx                    # Top navigation bar
│   │   │   ├── SymbolLayout.jsx                 # Per-symbol context wrapper
│   │   │   ├── Dashboard.jsx + .css             # 8 KPI tiles
│   │   │   ├── LotsTable.jsx + .css             # Trade cockpit (main table)
│   │   │   ├── LotFilters.jsx                   # Filter bar
│   │   │   ├── LotSummaryCards.jsx              # Summary KPIs
│   │   │   ├── OpenOrdersPanel.jsx              # Open sell orders
│   │   │   ├── PairingPanel.jsx + .css          # 3-tab pairing UI
│   │   │   ├── PairingExistingTab.jsx           # Existing pairings
│   │   │   ├── SimulationModal.jsx              # Simulation overlay
│   │   │   ├── CombinedScore.jsx + .css         # Unified signal dashboard
│   │   │   ├── Orderblock.jsx + .css            # Orderblock detection dashboard
│   │   │   ├── OrderblockChart.jsx              # Candlestick chart (lightweight-charts)
│   │   │   ├── OrderblockFilters.jsx            # Zone filters
│   │   │   ├── OrderblockKPIs.jsx               # KPI cards
│   │   │   ├── OrderblockZoneTable.jsx          # Zone table
│   │   │   ├── OrderblockTradeTable.jsx         # Backtest trade table
│   │   │   ├── Reconciliation.jsx + .css        # Data reconciliation
│   │   │   ├── Settings.jsx + .css              # User settings
│   │   │   └── FillNotification.jsx + .css      # WebSocket fill toasts
│   │   ├── contexts/
│   │   │   ├── SymbolContext.jsx                # Active symbol from URL param
│   │   │   ├── UserContext.jsx                  # User ID provider
│   │   │   └── WebSocketContext.jsx             # WS connection, prices, events
│   │   ├── hooks/
│   │   │   ├── useLotsData.js                   # Lots queries, filters, computed values
│   │   │   └── useNotification.js               # Toast notification hook
│   │   └── utils/
│   │       ├── formatters.js                    # formatNumber, formatEUR, formatBTC, etc.
│   │       ├── symbolRegistry.js                # Frontend symbol → asset mapping
│   │       └── orderblockHelpers.jsx            # Orderblock UI helpers
│   ├── package.json
│   └── vite.config.js
│
├── CLAUDE.md                                    # Project documentation for Claude Code
└── .gitignore
```

## Naming Conventions

### Backend (Python)
- **Files:** `snake_case.py` (e.g., `portfolio_service.py`, `sync_service.py`)
- **Functions:** `snake_case` (e.g., `compute_portfolio_from_ledger`, `get_portfolio_state`)
- **Classes:** `PascalCase` (e.g., `LedgerEvent`, `TradeLotDB`, `PortfolioState`)
- **DB models:** Suffix `DB` for ORM classes (e.g., `TradeLotDB` vs domain `TradeLot`)
- **Domain models:** Plain dataclasses (e.g., `LedgerEvent`, `PortfolioState`)
- **Test files:** `test_<module>.py` (e.g., `test_portfolio_breakeven.py`)

### Frontend (JavaScript/React)
- **Components:** `PascalCase.jsx` (e.g., `Dashboard.jsx`, `LotsTable.jsx`)
- **Hooks:** `use<Name>.js` (e.g., `useLotsData.js`, `useNotification.js`)
- **Utils:** `camelCase.js` (e.g., `formatters.js`, `symbolRegistry.js`)
- **CSS:** Component-scoped `ComponentName.css` (e.g., `Dashboard.css`)
- **Contexts:** `PascalCase` with `Context` suffix (e.g., `SymbolContext.jsx`)

### API Fields
- Backend returns `snake_case` field names (e.g., `base_qty`, `market_value_quote`)
- Decimal values transported as strings (`"1234.56"`) to avoid IEEE 754 precision loss
- Suffix `_quote` for currency-denominated values (e.g., `realized_pnl_quote`, `depot_pnl_quote`)
- Suffix `_base` for base-asset quantities (e.g., `qty_base_open`, `buys_volume_base_today`)

## Key File Locations

| What | Where |
|------|-------|
| FastAPI entry point | `backend/app/main.py` |
| Database models (ORM) | `backend/app/db/models.py` |
| Domain models (dataclasses) | `backend/app/domain/models.py` |
| Central portfolio calculation | `backend/app/domain/portfolio.py` |
| API authentication | `backend/app/api/auth.py` |
| DB session management | `backend/app/db/database.py` |
| Frontend entry point | `frontend/src/App.jsx` |
| API client (all endpoints) | `frontend/src/api/client.js` |
| Shared formatters | `frontend/src/utils/formatters.js` |
| Symbol registry (backend) | `backend/app/symbol_registry.py` |
| Symbol registry (frontend) | `frontend/src/utils/symbolRegistry.js` |
| Environment config | `backend/.env` |
| Alembic migrations | `backend/alembic/versions/` |
| Test configuration | `backend/tests/conftest.py` |
