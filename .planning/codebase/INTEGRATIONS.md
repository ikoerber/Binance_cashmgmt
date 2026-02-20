# External Integrations

**Analysis Date:** 2026-02-20

## APIs & External Services

**Binance Spot Trading (Critical):**
- Service: Binance REST + WebSocket API
  - SDK/Client: `python-binance 1.0.34` (REST sync calls) + `binance.AsyncClient` (WebSocket)
  - Auth: `BINANCE_API_KEY`, `BINANCE_API_SECRET` (env vars)
  - Purpose: Trade fills, order creation, balance queries, account info, live tickers
  - Implementation:
    - REST: `app/services/binance.py` (fetch_trades, create_order, get_account, get_historical_price)
    - WebSocket: `app/services/websocket_manager.py` (Binance stream hub) + `app/api/routes/websocket.py` (client handshake)
    - Modes: Testnet (`BINANCE_TESTNET=true`) + Production
    - Rate Limiting: Handled by python-binance library + custom `@retry_on_transient_error` exponential backoff

**Binance Public Klines API (Market Data):**
- Service: Binance REST Klines endpoint (public, no API key)
  - SDK/Client: `requests 2.32.5` + custom caching
  - Purpose: OHLCV candles for sentiment indicators, macro signals, orderblock detection
  - Implementation: `app/services/binance_public_client.py` (singleton with TTL cache, 5min default)
  - Pagination: Max 1000 candles per request, auto-paginated for multi-month queries
  - Cache: Threading-safe via `CachedValue` dataclass, TTL-aware

**Alternative.me Fear & Greed Index (Sentiment):**
- Service: Alternative.me API (public, no auth)
  - URL: `https://api.alternative.me/fng/`
  - Purpose: Daily emotional sentiment score (0-100) for sentiment engine v3 (28% weight)
  - Implementation: `app/services/sentiment_data_service.py` (singleton)
  - Cache: 30-minute TTL (index updates daily)
  - Graceful Degradation: Score defaults to 50 if unavailable

**OKX Public Funding Rate API (Sentiment):**
- Service: OKX REST API (public, no auth)
  - URL: `https://www.okx.com/api/v5/public/funding-rate`
  - Instrument ID: `BTC-USDT-SWAP` (funding rate is currency-agnostic)
  - Purpose: Derivatives heating indicator for sentiment engine v3 (20% weight)
  - Implementation: `app/services/sentiment_data_service.py`
  - Compliance: EU-compliant alternative to Binance Futures (MiCA-friendly, OKX supports EU users)
  - Cache: 15-minute TTL (funding updates every 8 hours on-chain)
  - Graceful Degradation: Score defaults to 50 if unavailable

**Twelve Data API (Macro Signals - Optional):**
- Service: Twelve Data REST API
  - URL: `https://api.twelvedata.com/time_series`
  - Auth: `TWELVE_DATA_API_KEY` (env var, free tier ~800 req/day)
  - Purpose: Macro indicators (DXY, US 2Y/10Y spreads) for macro signal v1 (5-factor analysis)
  - Implementation: `app/services/macro_data_service.py`
  - Cache: 5-minute TTL
  - Graceful Degradation: Macro signal defaults to neutral (0) if unavailable
  - Status: Optional; system functions with OKX/Alternative.me only

**Federal Reserve FRED API (Macro Signals - Optional):**
- Service: FRED REST API (St. Louis Federal Reserve)
  - URL: `https://api.stlouisfed.org/fred/series/observations`
  - Auth: `FRED_API_KEY` (env var, free tier available)
  - Purpose: US Treasury yields (2Y, 10Y) for yield spread analysis
  - Implementation: `app/services/macro_data_service.py`
  - Cache: 1-hour TTL (yields update daily)
  - Graceful Degradation: Skipped if unavailable

**ECB Statistical Data Warehouse (Macro Signals - Optional):**
- Service: ECB REST API
  - URL: `https://data-api.ecb.europa.eu/service/data`
  - Purpose: EUR/USD, EUR/GBP spot rates for macro analysis
  - Implementation: `app/services/macro_data_service.py`
  - Cache: 1-hour TTL
  - Graceful Degradation: Skipped if unavailable

## Data Storage

**Databases:**
- SQLite (Primary)
  - Connection: `sqlite:///./cashmgnt.db` (file-based, auto-created)
  - Client: SQLAlchemy 2.0.46 ORM
  - Features: Full ACID compliance, JSON columns, indexes for performance
  - Migrations: Alembic 1.18.4 (auto-generate via `alembic revision --autogenerate`)
  - Location: Repository root (`.gitignore`d)

**File Storage:**
- Local filesystem only (v1)
  - Backtest results: JSON serialization, stored in `backtest_runs` table
  - CSV imports: Handled in-memory, persisted to ledger events
  - Future: S3-compatible object storage for backtest artifacts

**Caching:**
- In-Memory (Runtime)
  - Pattern: `CachedValue` dataclass (timestamp + TTL)
  - Thread-safe via `threading.Lock` in singleton services
  - Sentiment Data Service: 90-day rolling histories (deque, max-length)
  - Orderblock Data Service: 1-hour TTL for kline cache
  - Macro Data Service: Per-indicator TTL (30sec-1hr)
- Redis (Future)
  - Placeholder: `redis 7.1.1` in requirements (planned for Celery workers)

## Authentication & Identity

**Auth Scheme:**
- Custom API Key (Header-based)
  - Implementation: `app/api/auth.py`
  - Header: `X-API-Key`
  - Secret: `API_SECRET_KEY` environment variable
  - Validation: `hmac.compare_digest()` (timing-safe comparison)
  - Mode: Disabled in development if unset; required in production (`APP_ENV=production`)

**External Service Auth:**
- Binance: API Key + Secret (asymmetric signing)
- Alternative.me, OKX: Public APIs (no auth required)
- Twelve Data, FRED, ECB: Optional API keys (free tier if unset, degraded features)

**WebSocket Auth (Phase 2):**
- Binance User Data Streams: Listen Key (expires every 60min, auto-renewed)
- Frontend WebSocket: Propagates `X-API-Key` header from initial upgrade

## Monitoring & Observability

**Error Tracking:**
- None (logging only)
- Implementation: `logging` module (Python standard library)
- Strategy: Structured logging via `logger.exception()` on all API routes
- Sanitization: API responses never include stacktraces (generic error messages only)

**Logs:**
- Approach: Python `logging` module to console/file (configurable)
- Level: DEBUG for development, INFO/WARNING for production
- Structured: JSON-serializable fields where applicable (dates as ISO8601)

**Health Checks:**
- Database: Auto-initialized on startup (Alembic migrations)
- WebSocket Streams: Health check via periodic heartbeat (future)

## CI/CD & Deployment

**Hosting:**
- Self-hosted (Docker or bare metal)
- Python: Uvicorn ASGI server (no Nginx reverse proxy required, but recommended)
- Node.js: Pre-built artifacts (`npm run build` → `frontend/dist/`)

**CI Pipeline:**
- None detected
- Recommendation: GitHub Actions (lint, test, build, deploy)

**Build Artifacts:**
- Backend: Source code + `.venv/` (committed in dev, built in Docker)
- Frontend: `frontend/dist/` (built, served as static assets)

## Environment Configuration

**Required env vars:**
- `BINANCE_API_KEY` - Binance API credentials
- `BINANCE_API_SECRET` - Binance API credentials
- `BINANCE_TESTNET` - Boolean (true/false, default false)
- `DATABASE_URL` - SQLAlchemy connection string (default: sqlite)
- `API_SECRET_KEY` - API authentication secret (empty = disabled in dev)

**Optional env vars:**
- `TWELVE_DATA_API_KEY` - Macro signals (optional, fallback to neutral)
- `FRED_API_KEY` - US yields (optional, skipped if missing)
- `ECB_API_KEY` - EUR rates (optional, skipped if missing)
- `APP_ENV` - Environment flag (production requires API_SECRET_KEY)
- `TEST_BINANCE_API_KEY` - Testnet credentials for automated tests
- `TEST_BINANCE_API_SECRET` - Testnet credentials for automated tests
- `VITE_API_URL` - Frontend API base (default: http://localhost:8000)
- `VITE_API_KEY` - Frontend API key (from env or local override)

**Secrets location:**
- `.env` file (local, auto-loaded via `python-dotenv`)
- `.gitignore`d; `.env.example` as template
- Production: Environment variables injected by deployment platform (Docker Compose, k8s, etc.)

## Webhooks & Callbacks

**Incoming:**
- Binance WebSocket Events: Fills, orders, balances (no external webhooks)
- Frontend WebSocket: Browser client connects to `/ws` endpoint for live updates

**Outgoing:**
- None implemented
- Future: Slack/Discord alerts for order execution, balance discrepancies

## Data Flow Summary

1. **Binance Spot Trading (REST)**
   - App → Binance API: `create_order()`, `fetch_account_info()`, `get_historical_price()`
   - Binance → App: Trade fills, order status, balances (via REST polling or WebSocket)

2. **Sentiment Engine (Public APIs)**
   - App → Alternative.me: `GET https://api.alternative.me/fng/?limit=1`
   - App → OKX: `GET https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP`
   - App → Binance Klines: `GET https://api.binance.com/api/v3/klines?symbol=BTCEUR&interval=1d`

3. **Macro Signals (Optional APIs)**
   - App → Twelve Data: `GET https://api.twelvedata.com/time_series?symbol=DXY&interval=1d`
   - App → FRED: `GET https://api.stlouisfed.org/fred/series/observations?series_id=T10Y2Y`
   - App → ECB: `GET https://data-api.ecb.europa.eu/service/data/...`

4. **WebSocket Streams (Binance + Frontend)**
   - Binance → App (AsyncClient): User data stream (executionReport, account balance events)
   - App → Frontend: WebSocket `/ws` endpoint broadcasts live price, order fills, balance updates
   - Frontend → App: WebSocket connection upgrade (X-API-Key propagation)

5. **Database Persistence**
   - All events: `ledger_events` table (append-only)
   - Orders, lots, pairings: Dedicated tables with foreign keys
   - Orderblock zones: `orderblock_zones` table (UPSERT on detection)
   - Backtest runs: `backtest_runs` table (immutable snapshots)

---

*Integration audit: 2026-02-20*
