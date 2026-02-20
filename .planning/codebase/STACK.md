# Technology Stack

**Analysis Date:** 2026-02-20

## Languages

**Primary:**
- Python 3.x - Backend API and domain logic (`backend/`)
- JavaScript (ES2020+) - Frontend React application (`frontend/`)

**Secondary:**
- SQL - Database schema migrations via Alembic

## Runtime

**Environment:**
- Python 3.x via `venv` (virtual environment)
- Node.js 16+ (inferred from ESLint/Vite config)

**Package Managers:**
- pip - Python dependencies
- npm - JavaScript dependencies (`frontend/package.json`)
- Lockfile: `requirements.txt` (pinned exact versions), `package-lock.json` (npm)

## Frameworks

**Backend Core:**
- FastAPI 0.128.7 - Web framework, routing, OpenAPI docs
- Uvicorn 0.40.0 - ASGI server, production deployable
- Pydantic 2.12.5 + pydantic-settings 2.12.0 - Data validation, environment config

**Frontend Core:**
- React 19.2.0 - UI library
- Vite 7.3.1 - Dev server and production build tool
- React Router DOM 7.13.0 - Client-side routing

**Database:**
- SQLAlchemy 2.0.46 - ORM for Python, database abstraction
- Alembic 1.18.4 - Database migrations (config: `backend/alembic.ini`)
- SQLite - Lightweight embedded database (default: `cashmgnt.db`)
  - Connection: `sqlite:///./cashmgnt.db` via `DATABASE_URL` env var
  - Full Foreign Key support enabled via `check_same_thread=False`
  - Alembic: `render_as_batch=True` for full schema flexibility

**Testing:**
- pytest 9.0.2 - Test runner
- pytest-cov 7.0.0 - Coverage reporting
- pytest-asyncio 1.3.0 - Async test support
- httpx 0.28.1 - Async HTTP client for testing

**Build/Dev Tools:**
- ruff 0.15.0 - Fast Python linter (bundled formatting + import sorting)
- black 26.1.0 - Python code formatter
- mypy 1.19.1 - Python type checker (optional)
- ESLint 9.39.1 - JavaScript linting (`frontend/eslint.config.js`)
- @vitejs/plugin-react 5.1.1 - React fast refresh for Vite

## Key Dependencies

**Critical (Business Logic):**
- python-binance 1.0.34 - Binance API client (sync trades, orders, balances, account info)
- aiohttp 3.13.3 - Async HTTP client (Binance WebSocket streams)
- requests 2.32.5 - Synchronous HTTP requests (Alternative.me, OKX, macro data sources)

**Frontend Data Management:**
- @tanstack/react-query 5.90.20 - Server state management, caching, polling
- axios 1.13.5 - HTTP client (Backend API calls)

**Frontend Charting:**
- lightweight-charts 5.1.0 - Professional candlestick charts (Orderblock visualization)
- recharts 3.7.0 - React charting library (Dashboard KPI cards, zone distribution charts)

**Infrastructure:**
- python-dotenv 1.2.1 - Environment variable loading from `.env`
- python-dateutil 2.9.0.post0 - Date/time utilities
- python-multipart 0.0.22 - MultiPart form data handling (file uploads)
- redis 7.1.1 - Redis client (future: Celery workers)

## Configuration

**Environment:**
- Loaded via `python-dotenv` from `.env` file (not committed)
- Key variables:
  - `BINANCE_API_KEY`, `BINANCE_API_SECRET` - Binance spot trading credentials
  - `BINANCE_TESTNET` - Switch between testnet/live (testnet=true for dev/test)
  - `TEST_BINANCE_API_KEY`, `TEST_BINANCE_API_SECRET` - Separate test credentials
  - `DATABASE_URL` - SQLAlchemy connection string (default: `sqlite:///./cashmgnt.db`)
  - `API_SECRET_KEY` - Authentication key for API endpoints (header: `X-API-Key`)
  - `TWELVE_DATA_API_KEY` - Optional: Twelve Data macro indicator API
  - `FRED_API_KEY` - Optional: Federal Reserve yield data (FRED API)
  - `APP_ENV` - Application environment (`production` or `development`)

**Build:**
- `backend/alembic.ini` - Alembic migration config (SQLAlchemy URL)
- `backend/pytest.ini` - pytest configuration
- `frontend/vite.config.js` - Vite build config (React plugin, no custom aliases)
- `frontend/eslint.config.js` - ESLint rules (React hooks, refresh, recommended JS)

**Environment Expansion (Frontend):**
- `VITE_API_URL` - Backend API base URL (default: `http://localhost:8000`)
- `VITE_API_KEY` - API key for requests (from env or local override)

## Platform Requirements

**Development:**
- Python 3.x with pip
- Node.js 16+ with npm
- SQLite 3 (bundled in Python)
- Binance API credentials (testnet recommended)
- Optional: Twelve Data/FRED/ECB API keys for macro features

**Production:**
- Python 3.x ASGI-compatible environment (Uvicorn)
- Node.js for frontend build step (or pre-built artifact)
- SQLite database file (or Postgres/MySQL with minimal config change)
- Binance API credentials (live account or testnet)
- Redis instance (future: async task workers)
- Optional: Cloud blob storage (S3-compatible) for backtest artifacts

**Deployment Target:**
- Docker containers recommended (Python + Node.js multi-stage)
- Or: Direct server (Python venv + Node.js)
- WebSocket support required (FastAPI/Uvicorn native)

---

*Stack analysis: 2026-02-20*
