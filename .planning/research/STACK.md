# Stack Research: Multi-Factor Omni-Bot

**Domain:** Multi-factor scoring engine, backtesting engine, real-time signal processing for crypto spot trading
**Researched:** 2026-02-25
**Confidence:** HIGH (backend), MEDIUM (WebSocket streams -- Binance rate limits need runtime validation)

## Existing Stack (DO NOT add -- already present)

These are validated and working. Listed to prevent redundant additions:

| Technology | Version | Already Used For |
|------------|---------|-----------------|
| Python 3.13 | 3.13.5 | Backend runtime |
| FastAPI | 0.128.7 | REST API |
| SQLAlchemy 2 | 2.0.46 | ORM + migrations |
| Alembic | 1.18.4 | DB migrations |
| python-binance | 1.0.35 | Binance REST + WebSocket (Client, BinanceSocketManager) |
| aiohttp | 3.13.3 | WebSocket streams (raw Combined Stream in BinanceStreamManager) |
| requests | 2.32.5 | REST calls (Binance Public Client, OKX, alternative.me) |
| React 19 | 19.2.0 | Frontend |
| TanStack Query | 5.90.20 | Data fetching + polling |
| Recharts | 3.7.0 | Bar/line charts |
| lightweight-charts | 5.1.0 | Candlestick charts |
| SQLite | (via SQLAlchemy) | Persistence |
| redis | 7.1.1 | Listed but not yet actively used |
| Decimal (stdlib) | Python 3.13 | All financial calculations |
| statistics (stdlib) | Python 3.13 | mean, stdev, correlation, linear_regression, quantiles, NormalDist |
| math (stdlib) | Python 3.13 | sqrt, log, exp, etc. |

## Recommended Stack Additions

### Backend: Statistical Computing

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| numpy | 2.2.6 | Z-Score computation, rolling windows, vectorized array ops for backtesting | The backtesting engine simulates 24 months of candle data (17,520 candles at 1h, 4,380 at 4h). Pure Python loops with Decimal over 17k+ rows for rolling Z-Score, rolling mean, rolling std is painfully slow. numpy vectorizes these into single-pass C operations. The scoring engine needs rolling windows (Z-Score over 50+ periods), lead-lag cross-correlation, and cumulative return series -- all numpy's sweet spot. Pin to 2.2.x (not 2.4.x) because 2.2.x is the last LTS-style release with broad ecosystem compatibility. |
| -- | -- | -- | -- |

**Why numpy 2.2.6 specifically (not 2.4.2):** numpy 2.4.x is very recent (February 2026). The 2.2.x line is the safe production choice -- well-tested with Python 3.13, no breaking API changes, and all downstream libraries are validated against it. Pin to exact version per project convention.

**Why NOT pandas:** The project does NOT need DataFrames. All data flows as lists of dataclasses (Candle, Orderblock, BacktestTrade). Adding pandas introduces a massive dependency (60+ MB) for functionality that numpy arrays + list comprehensions handle cleanly. The existing codebase pattern is `List[Candle]` not `pd.DataFrame`. Pandas would be architectural mismatch.

**Why NOT scipy:** scipy adds 80+ MB for functions we barely need. The `statistics` stdlib module already provides `mean`, `stdev`, `correlation`, `linear_regression`, `NormalDist` (all verified present in Python 3.13). The only scipy function we might want is `scipy.stats.percentileofscore` -- but the project already implements `rolling_percentile()` as pure Decimal in `domain/sentiment.py:307`. Stay consistent.

### Backend: No New Web/API Dependencies

The existing stack handles all API needs:

| Need | Covered By | Notes |
|------|-----------|-------|
| Binance REST (klines, depth) | `BinancePublicClient` (requests + retry) | Already fetches klines, orderbook depth for sentiment. Extend, do not replace. |
| Binance WebSocket (depth stream, kline stream) | `BinanceStreamManager` (aiohttp) | Already manages combined ticker + user data streams via raw aiohttp. Add depth + kline streams to the same manager. |
| OKX Funding Rate | `SentimentDataService` (requests) | Already fetches OKX funding. Reuse for the scoring engine's funding rate factor. |
| Data caching (TTL) | `CachedValue` pattern | Already implemented in `binance_public_client.py` and `sentiment_data_service.py`. Use same pattern for new signal caches. |

### Backend: Time-Series Storage for Backtesting

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| SQLite (existing) | via SQLAlchemy 2.0.46 | Signal history, backtest runs, dry-run logs | No new DB needed. The existing pattern (`BacktestRunDB` with JSON columns for trades/metrics) works well. Signal history is append-only time-series data -- SQLite handles this efficiently with proper indexing. A new `SignalSnapshotDB` table follows the same pattern as `BacktestRunDB`. |

**Why NOT TimescaleDB / InfluxDB / DuckDB:** The data volume is small. Signal snapshots at 1-minute intervals for 3 symbols = ~4,320 rows/day. SQLite handles millions of rows. The project is single-user, single-machine. Adding a separate time-series DB introduces operational complexity (another service to run, another connection pool) for zero benefit at this scale.

**Why NOT Redis for caching:** Redis is already in requirements.txt but unused. For this milestone, in-memory caching (existing `CachedValue` + `deque` patterns in SentimentDataService) is sufficient. The scoring engine recalculates on each tick -- there's no complex cache invalidation problem. Redis is better suited for the future worker/queue architecture (Auto-Order Automation milestone).

### Frontend: No New Charting Dependencies

| Need | Covered By | Notes |
|------|-----------|-------|
| Backtest equity curve | Recharts `<LineChart>` | Already used for Orderblock charts. Equity curve is a simple line chart. |
| Signal history chart | Recharts `<AreaChart>` + `<ReferenceLine>` | Score over time with threshold lines. Standard Recharts pattern. |
| Drawdown visualization | Recharts `<AreaChart>` with negative fill | Drawdown is negative -- use `fill` with loss color below zero baseline. |
| Bot status indicators | Plain CSS | Status badges, toggles -- existing pattern from reconciliation/alert system. |

### Frontend: One New Utility Library

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| -- | -- | -- | -- |

No new frontend dependencies needed. The existing stack (Recharts + lightweight-charts + TanStack Query + plain CSS) covers all visualization and data-fetching needs for the Bot Dashboard.

## Integration Points with Existing Architecture

### 1. Multi-Factor Scoring Engine Integration

The scoring engine follows the existing **pure domain + service + route** pattern:

```
domain/alpha_score.py          (pure: Z-Score, Lead-Lag, scoring math -- uses numpy internally)
services/alpha_score_service.py (data fetching, caching, orchestration)
api/routes/alpha.py             (thin HTTP layer)
```

**Reuses from existing codebase:**
- `BinancePublicClient.get_klines()` -- already fetches OHLCV candles (used by orderblock + sentiment)
- `BinancePublicClient.get_order_book()` -- already fetches depth (used by sentiment orderbook imbalance)
- `SentimentDataService._get_funding_rate()` -- already fetches OKX funding (reuse via public method or extract)
- `CombinedScoreService` pattern -- orchestrates multiple sub-services into unified score
- `Decimal` for API output, `numpy float64` for internal batch computation, convert at boundaries

**Decimal/numpy boundary pattern:**

```python
# domain/alpha_score.py
import numpy as np
from decimal import Decimal

def compute_zscore_array(prices: list[Decimal], window: int = 50) -> list[Decimal]:
    """Vectorized Z-Score computation. Input/output Decimal, numpy internally."""
    arr = np.array([float(p) for p in prices], dtype=np.float64)
    rolling_mean = np.convolve(arr, np.ones(window)/window, mode='valid')
    rolling_std = np.array([arr[i:i+window].std() for i in range(len(arr)-window+1)])
    zscore = (arr[window-1:] - rolling_mean) / np.where(rolling_std == 0, 1, rolling_std)
    return [Decimal(str(round(z, 8))) for z in zscore]
```

This preserves the project's Decimal invariant at service/API boundaries while getting numpy's performance for batch operations. The pattern is: **Decimal in, numpy compute, Decimal out.**

### 2. WebSocket Stream Extension

The existing `BinanceStreamManager` uses Binance Combined Streams (`wss://stream.binance.com:9443/stream?streams=...`). New streams are added to the same combined URL:

| Stream | Format | Use Case | Update Frequency |
|--------|--------|----------|-----------------|
| `btceur@ticker` | Existing | Price updates | ~1/sec |
| `btceur@depth20@100ms` | **NEW** | Orderbook imbalance (top 20 levels) | 100ms |
| `btceur@kline_1m` | **NEW** | Lead-Lag momentum detection (1-min candles) | On close (~1/min) |

**Why `@depth20@100ms` not full `@depth`:** The full depth stream sends ALL orderbook changes -- extremely high throughput that would overwhelm a Python async handler. `@depth20` sends only top 20 bid/ask levels as a snapshot every 100ms. This is exactly what orderbook imbalance needs (the existing sentiment service already computes imbalance from top levels within +/-5% of mid-price). At 100ms intervals, Python can comfortably process this without backpressure.

**Why not `@aggTrade` for lead-lag:** Individual trades are too noisy. 1-minute kline closes give clean OHLCV that the lead-lag calculation needs. The kline stream fires once per completed candle plus a partial update stream -- we only process completed candles (check `kline.x === true` in the WebSocket payload).

**Implementation in existing BinanceStreamManager:**

```python
# Extend _run_price_stream to include new streams
streams = []
for sym in KNOWN_PAIRS:
    s = sym.lower()
    streams.append(f"{s}@ticker")
    streams.append(f"{s}@depth20@100ms")  # NEW: orderbook snapshots
    streams.append(f"{s}@kline_1m")       # NEW: 1-min candle stream

combined = "/".join(streams)
ws_url = f"wss://stream.binance.com:9443/stream?streams={combined}"
```

**Rate limit note:** Binance allows up to 1024 streams per combined connection. With 3 symbols x 3 stream types = 9 streams -- well within limits.

### 3. Backtesting Engine Integration

Follows the existing `orderblock_backtest.py` pattern:

```
domain/backtest_engine.py      (pure: simulation loop, equity curve, metrics)
services/backtest_service.py   (orchestration: fetch candles, run simulation, persist)
api/routes/backtest.py         (HTTP layer)
db/models.py                   (AlphaBacktestRunDB -- same pattern as BacktestRunDB)
```

**Reuses:**
- `BinancePublicClient` paginated kline fetching (already handles 1000-candle pagination)
- `BacktestRunDB` pattern (immutable snapshot with JSON columns)
- Existing `compute_backtest_metrics()` patterns from `orderblock_backtest.py`

**New metrics beyond existing orderblock backtest:**
- Sharpe Ratio: `(mean_returns - risk_free) / std_returns * sqrt(periods_per_year)` -- numpy vectorizes this
- Max Drawdown: `np.minimum.accumulate(equity_curve) / equity_curve - 1` -- clean numpy one-liner
- Equity Curve: `np.cumprod(1 + returns_array)` -- vectorized cumulative product
- HODL Benchmark: Simple buy-and-hold comparison -- `final_price / initial_price`

### 4. Dry-Run Mode Integration

Follows existing service patterns:

```
services/dry_run_service.py    (signal logging, mock order creation)
db/models.py                   (DryRunSignalDB, DryRunOrderDB)
```

**Reuses:**
- `OrderDB` schema pattern for mock orders (same columns, additional `is_dry_run=True` flag or separate table)
- `AlertEventDB` pattern for signal logging (append-only, timestamped)
- `BinanceStreamManager` for real-time data (consumes same streams, just doesn't execute)

### 5. Combined Score Integration

The Alpha Score feeds into the existing `CombinedScoreService` as a third signal source:

```python
# Current: Direction (MacroSignal 60%) + Sizing (Sentiment 40%)
# New:     Direction (MacroSignal 40%) + Sizing (Sentiment 30%) + Alpha (AlphaScore 30%)
```

The `compute_combined_score()` domain function already accepts `DirectionInput` and `SizingInput` dataclasses. Add an `AlphaInput` dataclass following the same pattern.

## Installation

```bash
# Backend: One new dependency
cd backend
pip install numpy==2.2.6

# Add to requirements.txt:
# Statistical Computing (Backtesting + Scoring Engine)
# numpy==2.2.6

# Frontend: No new dependencies
# Existing Recharts + lightweight-charts cover all visualization needs
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| numpy 2.2.6 (arrays only) | pandas (DataFrames) | If you need labeled columns, groupby, merge, pivot -- none of which this project needs. Data stays as `List[Candle]` dataclasses. |
| numpy 2.2.6 | Pure Python + Decimal | If backtesting were limited to <500 candles. At 17k+ candles with rolling windows, pure Python is 50-100x slower. |
| numpy 2.2.6 | scipy | If you need advanced stats (KDE, hypothesis testing, optimization). We only need rolling mean/std/zscore -- numpy covers this. |
| SQLite signal tables | TimescaleDB / InfluxDB | If signal volume exceeds 10M+ rows or needs sub-millisecond query latency. At ~4k rows/day, SQLite is more than sufficient. |
| SQLite signal tables | DuckDB (analytical queries) | If backtesting queries became the bottleneck (complex aggregations over millions of rows). Not the case here -- backtest runs pre-compute all metrics. |
| aiohttp raw streams | python-binance BinanceSocketManager | If you want callback-based stream handling. The project already built a custom `BinanceStreamManager` with reconnection, backoff, and broadcast -- switching to python-binance's socket manager would be a rewrite for no gain. |
| In-memory CachedValue | Redis pub/sub | If multiple backend processes need shared signal state. Single-process FastAPI with in-memory cache is simpler and faster for single-user deployment. |
| Recharts (existing) | Apache ECharts / Plotly.js | If you need 3D charts, heatmaps, or complex interactive dashboards. Equity curves and drawdown charts are simple line/area charts -- Recharts handles these cleanly. |
| No new frontend deps | chart.js for backtest charts | Recharts already does everything needed. Adding chart.js creates two competing charting libraries. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| pandas | 60+ MB dependency for DataFrame features this project never uses. All data flows as typed dataclasses, not tabular DataFrames. Pandas would fight the existing architecture. | numpy arrays for batch math, List[dataclass] for data transport |
| scipy | 80+ MB dependency. Python 3.13 `statistics` module provides mean, stdev, correlation, linear_regression, NormalDist. The one missing function (percentileofscore) is already hand-implemented in `domain/sentiment.py`. | numpy + statistics stdlib |
| TA-Lib (technical analysis) | C dependency with notoriously difficult installation (especially on macOS). The project already hand-implements ATR (Wilder's Smoothing), Z-Score, rolling percentile, etc. in pure domain logic. Adding TA-Lib creates a hard-to-install dependency for functions already written. | numpy + existing domain functions |
| Backtrader / Zipline / vectorbt | Full backtesting frameworks designed for portfolio simulation with broker APIs. Massive overkill -- this project needs a simple candle-by-candle simulation loop (already proven in `orderblock_backtest.py`). These frameworks impose their own data models that conflict with the Ledger-first architecture. | Custom backtesting engine following existing `orderblock_backtest.py` pattern |
| ccxt (multi-exchange library) | Project constraint: Binance-only. ccxt adds 30+ MB and abstracts away Binance-specific features (combined streams, specific order types). python-binance is already integrated and working. | python-binance (existing) |
| websockets library (standalone) | aiohttp already provides WebSocket client support and is already a dependency. Adding `websockets` creates two competing WebSocket implementations. | aiohttp (existing) |
| Redis for signal caching | Adds operational complexity (Redis server must run). In-memory CachedValue pattern is simpler, faster, and already proven across 3 services (BinancePublicClient, SentimentDataService, OrderblockDataService). | In-memory CachedValue + deque (existing pattern) |
| Celery for background tasks | Requires Redis/RabbitMQ broker + separate worker process. The scoring engine runs in the FastAPI event loop (asyncio). Signal computation takes <100ms -- no need for a task queue. | asyncio.create_task() + asyncio.to_thread() (existing pattern in websocket_fill_handler.py) |

## Decimal/numpy Coexistence Strategy

The project has a strict Decimal invariant for financial calculations. numpy uses float64. Here is the boundary pattern:

```
API Layer (Decimal strings) → Service Layer (Decimal) → Domain Layer (Decimal at boundaries, numpy internally for batch ops) → Service Layer (Decimal) → API Layer (Decimal strings)
```

**Rules:**
1. All API inputs/outputs remain Decimal strings (project convention)
2. All persisted values remain Decimal (SQLAlchemy Numeric columns)
3. numpy is used ONLY inside domain batch computation functions
4. Every numpy function accepts `list[Decimal]` and returns `list[Decimal]`
5. float64 precision (15-16 significant digits) is sufficient for Z-Scores, Sharpe ratios, and signal scores -- these are statistical indicators, not financial amounts
6. Financial amounts (order quantities, prices, P&L) NEVER touch numpy -- they stay Decimal throughout

**Where numpy is used:**
- `compute_zscore_array()` -- rolling Z-Score over 50+ candle windows
- `compute_lead_lag_correlation()` -- cross-correlation between two price series
- `compute_equity_curve()` -- cumulative product of return series
- `compute_sharpe_ratio()` -- mean/std of returns
- `compute_max_drawdown()` -- cumulative minimum tracking
- `compute_rolling_stats()` -- rolling mean/std for ATR-adaptive calculations

**Where numpy is NOT used:**
- Order placement (price, quantity) -- Decimal
- P&L calculation -- Decimal
- Portfolio computations -- Decimal
- Fee calculations -- Decimal
- Any value that becomes a Binance API parameter -- Decimal

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| numpy 2.2.6 | Python 3.13.5 | Verified: numpy 2.2.x supports Python 3.13. Available via pip in project venv. |
| numpy 2.2.6 | SQLAlchemy 2.0.46 | No interaction -- numpy operates on in-memory arrays, SQLAlchemy on DB. |
| numpy 2.2.6 | FastAPI 0.128.7 | No interaction -- numpy runs in domain layer, FastAPI in API layer. |
| aiohttp 3.13.3 | Binance Combined Streams | Already validated (price + user data streams working). Adding depth20 + kline_1m streams uses same connection pattern. |
| Recharts 3.7.0 | Equity curve / drawdown charts | LineChart and AreaChart components already used. No version concern. |
| lightweight-charts 5.1.0 | Signal overlay on price charts | markers API already used for orderblock visualization. Extend for signal markers. |

## WebSocket Stream Architecture (Detailed)

### Current Architecture

```
BinanceStreamManager (singleton)
  |
  +-- Price Stream (combined: btceur@ticker + etheur@ticker + xrpeur@ticker)
  |     |-- Reconnection with exponential backoff
  |     |-- Broadcast to price_subscribers (Set[WebSocket])
  |
  +-- User Data Stream (per user_id, via listen key)
        |-- executionReport -> order_update + fill processing
        |-- outboundAccountPosition -> balance_update
```

### Extended Architecture for v3.0

```
BinanceStreamManager (singleton)
  |
  +-- Market Stream (combined: ticker + depth20 + kline_1m per symbol)
  |     |-- @ticker -> price_subscribers (existing)
  |     |-- @depth20@100ms -> depth_handler -> alpha_score_service (NEW)
  |     |-- @kline_1m -> kline_handler -> alpha_score_service (NEW)
  |
  +-- User Data Stream (unchanged)
  |
  +-- Signal Processor (NEW -- asyncio task, not WebSocket)
        |-- Receives depth + kline updates from handlers
        |-- Computes Alpha Score on each significant update
        |-- Broadcasts signal_update to signal_subscribers
        |-- Logs to DryRunSignalDB (if dry-run mode active)
```

**Key design decision:** The signal processor is an asyncio coroutine, NOT a WebSocket consumer. It receives data from the stream handlers via an `asyncio.Queue` and processes signals asynchronously. This decouples stream ingestion from signal computation -- if scoring takes longer than 100ms, depth updates queue without blocking.

### Binance Stream Rate Limits

| Stream | Messages/sec | Processing Budget |
|--------|-------------|-------------------|
| `@ticker` (3 symbols) | ~3/sec | Trivial (existing) |
| `@depth20@100ms` (3 symbols) | ~30/sec | 33ms per message -- comfortable |
| `@kline_1m` (3 symbols) | ~3/min (on close) | 333ms per message -- very comfortable |
| **Total** | ~33/sec peak | Well within Python asyncio capacity |

**Confidence:** HIGH for ticker and kline streams (already proven in codebase). MEDIUM for depth20@100ms -- rate is documented by Binance but actual processing load under Python asyncio needs runtime validation. The 100ms update interval (vs 1000ms for @depth@1000ms) is more aggressive; if backpressure occurs, fall back to `@depth20@1000ms`.

## Data Volume Estimates

| Data Type | Volume/Day | Storage (SQLite) |
|-----------|-----------|-----------------|
| Signal snapshots (1-min, 3 symbols) | ~4,320 rows | ~500 KB/day |
| Dry-run mock orders | ~10-50 rows | ~5 KB/day |
| Backtest runs (on-demand) | 1-5 rows | ~50-200 KB/run (JSON trades) |
| Depth snapshots (NOT persisted) | In-memory only | 0 (computed on the fly) |
| Kline data for backtesting | Fetched from Binance, cached in-memory | 0 (existing paginated fetch pattern) |

**Annual signal storage:** ~180 MB/year -- trivial for SQLite.

## Sources

- Codebase analysis: `requirements.txt` (current pinned versions), `backend/app/services/websocket_manager.py` (existing stream architecture), `backend/app/domain/sentiment.py` (existing scoring patterns, rolling_percentile, Z-Score), `backend/app/domain/orderblock_backtest.py` (existing backtest engine pattern), `backend/app/services/binance_public_client.py` (existing REST client + caching), `backend/app/services/combined_score_service.py` (existing multi-signal orchestration pattern), `backend/app/db/models.py` (existing BacktestRunDB pattern) -- HIGH confidence
- Python 3.13 `statistics` module: Verified via runtime inspection -- `mean`, `stdev`, `pstdev`, `NormalDist`, `correlation`, `linear_regression` all present -- HIGH confidence
- numpy 2.2.6: Verified available via `pip index versions numpy` in project venv -- HIGH confidence
- pandas 3.0.1 / scipy 1.17.1: Verified available but deliberately excluded (see rationale) -- HIGH confidence
- Binance WebSocket stream documentation: `@depth20@100ms`, `@kline_1m` stream formats based on training data knowledge of Binance API -- MEDIUM confidence (Binance may have changed stream names; verify with official docs before implementation)
- aiohttp 3.13.3 WebSocket capabilities: Confirmed from existing working code in `websocket_manager.py` -- HIGH confidence

---
*Stack research for: v3.0 Multi-Factor Omni-Bot (Scoring Engine + Backtesting + Dry-Run)*
*Researched: 2026-02-25*
