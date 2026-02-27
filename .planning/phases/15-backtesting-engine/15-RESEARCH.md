# Phase 15: Backtesting Engine - Research

**Researched:** 2026-02-27
**Domain:** Historical signal simulation, performance metrics, walk-forward backtesting
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Position sizing**: Fixed fraction of current portfolio (compounding)
- **Position management**: Single position per symbol at a time -- new signals while position open are ignored
- **Entry trigger**: Long-only above configurable threshold (matches Spot reality -- no short positions)
- **Exit mechanism**: Full trailing stop simulation using Phase 14's ATR-adaptive trailing stop, tick-by-tick on historical candles
- **Backtest method**: Simple in-sample (not walk-forward). Full period simulation.
- **Data resolution**: Match Alpha Score's configured candle interval from user settings
- **Warmup**: Auto-skip warmup candles needed by indicators (e.g. 200 for 200-DMA). No trades during warmup, shown as grayed-out period on equity curve.
- **Data fetching**: Fetch extra historical data before user's chosen start date to satisfy warmup buffer. Trading starts exactly at user's start date -- full requested period is tradeable.
- **Navigation**: Standalone "Backtest" page in navigation (not embedded in Alpha Score page)
- **Equity curve**: Line chart with HODL benchmark overlaid -- visual comparison at a glance
- **Drawdown chart**: Underwater area chart below equity curve showing drawdown percentage over time
- **Monthly returns**: Color-coded heatmap grid (months as columns, years as rows, red-to-green)
- **Trade distribution**: P&L histogram showing distribution of individual trade returns
- **Trade list**: Expandable trade table (collapsed by default) -- entry/exit date, price, P&L, duration, Alpha Score at entry
- **Backtest history**: Collapsible run cards (key metrics visible, click to expand full details + equity curve). Similar to existing Orderblock backtest pattern.
- **Initial capital**: Configurable by user (input field in backtest form)
- **Parameter sweep**: Form with range inputs (min, max, step) per parameter. Shows estimated combination count before running. Sweepable params: Z-Score lookback, factor weights, trade threshold, trailing stop ATR multiplier. Sortable results table with CSV export. Warn above ~100 combinations, hard cap at ~500.
- **Fees**: Configurable flat rate applied to both entry and exit. Default: 0.1%.
- **Slippage**: Configurable percentage added to entry price, subtracted from exit. Default: 0.05%.
- **Display**: Fees and slippage shown as separate line items in results. Total fees paid and total slippage cost visible as distinct metrics.
- **Execution**: Server-side (backend API runs simulation, not browser)
- **Progress streaming**: Via existing WebSocket infrastructure (WebSocketContext.jsx). Real-time progress bar with percentage, elapsed time, live counters (candles processed, trades found). For sweeps: X/N combinations done.
- **Cancellation**: Cancel button during execution. For sweeps: partial results up to cancellation are kept and displayed.
- **Benchmark**: Always 50/50 BTC/XRP HODL regardless of which symbol is tested. Static buy-and-hold from day 1, no periodic rebalancing. Same fee rate on initial purchase. Overlay line on equity curve + separate delta metrics (excess return, relative Sharpe).

### Claude's Discretion
- Exact chart library choices (Recharts vs. lightweight-charts for equity curve)
- Progress bar implementation details
- WebSocket message format for backtest progress
- Exact warmup candle count derivation from Phase 14 indicator config
- Sweep combination cap exact numbers
- Internal backtest engine architecture (pure domain vs. service split)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BT-01 | User can run backtests over configurable time period (up to 24 months) for any supported symbol | Paginated kline fetching pattern from OrderblockDataService, warmup buffer calculation from Alpha Score indicator windows, data resolution from user settings |
| BT-02 | Backtest computes performance metrics: net return, Sharpe ratio, max drawdown, trade count, win rate | Pure domain module `backtest_engine.py` with Decimal-precision metric computations, Sharpe formula (annualized, risk-free=0), drawdown tracking via high-water-mark |
| BT-03 | Backtest compares results against buy-and-hold benchmark (50/50 BTC/XRP HODL) | Benchmark computation as separate pure function, both BTC and XRP price series needed, same fee deduction on initial purchase |
| BT-04 | Backtest includes realistic transaction costs (configurable fee rate, slippage modeling) | Fee/slippage applied at entry and exit in simulation loop, tracked as cumulative totals for display |
| BT-05 | Backtest results are persisted as immutable snapshots (config + metrics + trades) | New `AlphaBacktestRunDB` table following existing `BacktestRunDB` pattern (JSON columns for config, metrics, trades, equity curve) |
| BT-06 | User can view backtest history with expandable run details | API routes following existing Orderblock backtest pattern (list + detail), frontend collapsible run cards |
| BT-07 | User can run parameter sweep (grid search) with CSV export | Sweep orchestrator generating parameter combinations, server-side execution with progress tracking, CSV serialization |
</phase_requirements>

## Summary

Phase 15 builds a comprehensive backtesting engine for the Alpha Score signal (Phase 14). The engine simulates historical trading based on Alpha Score signals using candle-by-candle walk-through with Phase 14's trailing stop exit logic. The architecture follows the existing project pattern of pure domain logic (no I/O) orchestrated by a service layer, with results persisted as immutable DB snapshots.

The primary technical challenge is combining Phase 14's Alpha Score computation (which requires 4 live data sources: XRPBTC klines, BTCEUR klines, orderbook depth, OKX funding) into a historical simulation where only kline data is available. The decision to use simple in-sample backtesting (not walk-forward) and long-only positions simplifies the engine significantly. Orderbook and funding rate data are unavailable historically, so the backtest must degrade gracefully by computing Alpha Score with only the kline-driven factors (Z-Score and Lead-Lag), which together carry 70% of default weight.

The frontend adds a standalone Backtest page with Recharts-based equity curve, drawdown chart, monthly returns heatmap, P&L histogram, and a trade list. Progress streaming uses the existing WebSocket infrastructure with a new `backtest_progress` message type. The parameter sweep feature generates grid combinations server-side with cancellation support.

**Primary recommendation:** Build the backtest engine as a pure domain module (`domain/backtest_engine.py`) that takes candle data + config and returns complete results, then orchestrate via `services/backtest_data_service.py` that handles data fetching, progress callbacks, and persistence. Reuse `BinancePublicClient.get_klines()` with the paginated fetch pattern from `OrderblockDataService`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `decimal.Decimal` | stdlib | All financial calculations | Project invariant: never float for money/prices |
| `dataclasses` | stdlib | Result types (BacktestResult, TradeRecord, etc.) | Project pattern: all domain types are dataclasses |
| SQLAlchemy 2.0 | 2.0.46 | Persistence of backtest runs | Existing ORM, Alembic migrations |
| FastAPI | 0.128.7 | API routes for backtest execution | Existing web framework |
| Recharts | (existing) | Equity curve, drawdown chart, P&L histogram | Already used for Orderblock charts, Combined Score |
| TanStack Query | (existing) | Frontend data fetching + cache | Already used everywhere in frontend |
| WebSocket (existing) | native | Progress streaming | Existing WebSocketContext.jsx infrastructure |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `csv` | stdlib | CSV export for sweep results | Parameter sweep export |
| `io.StringIO` | stdlib | In-memory CSV generation | Streaming CSV response |
| `asyncio` | stdlib | Async backtest execution with cancellation | Long-running backtest in thread pool |
| `threading.Event` | stdlib | Cancellation signal for backtest loop | Cancel button support |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Recharts for equity curve | lightweight-charts (TradingView) | lightweight-charts is better for financial charts but Recharts is already used for line charts in the project. Equity curve is a simple line chart -- Recharts is sufficient. lightweight-charts is only used for the Orderblock candlestick chart. |
| Custom metrics computation | numpy/pandas | Project uses Decimal exclusively. numpy is only permitted for non-financial computations (Hurst exponent). Sharpe/drawdown are simple enough in pure Decimal. |
| In-memory sweep results | Redis/Celery task queue | Sweep is synchronous within a single request (hard cap ~500 combinations). No need for distributed task queue at this scale. |

**Installation:** No new backend dependencies needed. Frontend already has Recharts.

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── domain/
│   └── backtest_engine.py        # Pure simulation logic (no I/O)
├── services/
│   └── backtest_data_service.py  # Orchestration: fetch + simulate + persist
├── api/routes/
│   └── backtest.py               # API endpoints
├── db/
│   └── models.py                 # AlphaBacktestRunDB (add to existing)
frontend/src/
├── components/
│   ├── Backtest.jsx              # Main page component
│   ├── BacktestForm.jsx          # Config form (symbol, period, capital, fees)
│   ├── BacktestResults.jsx       # Metrics display + charts
│   ├── BacktestHistory.jsx       # Collapsible run cards
│   ├── BacktestSweep.jsx         # Parameter sweep form + results table
│   └── Backtest.css              # Styles
├── api/
│   └── client.js                 # Add backtest API functions (existing file)
```

### Pattern 1: Pure Domain Simulation Loop
**What:** The backtest engine is a pure function that takes candle data, config, and an optional progress callback. It returns a complete result object with metrics, trades, and equity curve data points. No I/O, no DB, no API calls.
**When to use:** All financial simulation logic belongs here.
**Example:**
```python
# domain/backtest_engine.py
@dataclass
class BacktestConfig:
    symbol: str
    initial_capital: Decimal
    position_fraction: Decimal       # e.g. 0.1 = 10% of portfolio per trade
    entry_threshold: Decimal          # Alpha Score threshold for LONG entry
    fee_rate: Decimal                 # 0.001 = 0.1%
    slippage_pct: Decimal             # 0.0005 = 0.05%
    atr_period: int
    atr_multiplier: Decimal           # Trailing stop ATR multiplier
    # Alpha Score params (for re-computation from historical data)
    zscore_window: int
    leadlag_window: int
    hurst_lookback: int
    weights: Dict[str, Decimal]       # Factor weights
    hurst_trending: Decimal
    hurst_reverting: Decimal

@dataclass
class BacktestResult:
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: List[TradeRecord]
    equity_curve: List[EquityPoint]   # (timestamp, equity, benchmark_equity)
    monthly_returns: List[MonthlyReturn]
    warmup_end_index: int
    data_start: datetime
    data_end: datetime
    candle_count: int
    benchmark: BenchmarkResult

def run_alpha_backtest(
    xrpbtc_candles: List[dict],       # OHLCV dicts with Decimal values
    btceur_candles: List[dict],       # For Lead-Lag + benchmark + XRPEUR conversion
    xrpeur_candles: List[dict],       # For XRP benchmark leg
    config: BacktestConfig,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
) -> BacktestResult:
    ...
```

### Pattern 2: Service Layer Orchestration with Progress Streaming
**What:** The service fetches data, calls the domain function, persists results, and streams progress via WebSocket. Uses `asyncio.to_thread()` for non-blocking execution with cancellation via `threading.Event`.
**When to use:** All API-facing backtest operations.
**Example:**
```python
# services/backtest_data_service.py
class BacktestDataService:
    async def run_backtest(
        self,
        user_id: str,
        settings: dict,
        config: dict,
        ws_callback: Optional[Callable] = None,
    ) -> dict:
        # 1. Parse config from settings + request params
        # 2. Fetch historical candles (paginated, with warmup buffer)
        # 3. Run simulation in thread pool with progress callback
        # 4. Persist result as immutable snapshot
        # 5. Return serialized result
```

### Pattern 3: WebSocket Progress Messages
**What:** Extend existing WebSocket infrastructure with a `backtest_progress` message type. The backend broadcasts progress updates to the user's WebSocket connection during simulation.
**When to use:** During long-running backtest and sweep operations.
**Example:**
```python
# WebSocket message format
{
    "type": "backtest_progress",
    "run_id": "abt_abc123def456",
    "phase": "simulating",          # "fetching_data" | "warming_up" | "simulating" | "computing_metrics" | "complete" | "cancelled"
    "progress_pct": 45.2,
    "candles_processed": 4520,
    "candles_total": 10000,
    "trades_found": 12,
    "elapsed_seconds": 8.3,
    "timestamp": "2026-02-27T10:00:00Z"
}

# For sweeps
{
    "type": "backtest_progress",
    "run_id": "sweep_abc123",
    "phase": "sweep",
    "combination_current": 15,
    "combination_total": 48,
    "progress_pct": 31.25,
    "elapsed_seconds": 45.0,
    "timestamp": "..."
}
```

### Pattern 4: Immutable Backtest Snapshots (DB)
**What:** Follow the existing `BacktestRunDB` pattern -- a single table with JSON columns for config, metrics, trades, and equity curve. New table `alpha_backtest_runs` (not reusing `backtest_runs` to avoid confusion with Orderblock backtests).
**When to use:** Every completed backtest run is persisted.
**Example:**
```python
class AlphaBacktestRunDB(Base):
    __tablename__ = "alpha_backtest_runs"
    id = Column(String, primary_key=True)            # "abt_{uuid_hex[:12]}"
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    data_start = Column(DateTime, nullable=False)
    data_end = Column(DateTime, nullable=False)
    candle_count = Column(Numeric, nullable=False)
    initial_capital = Column(Numeric, nullable=False)
    # Key metrics (queryable without JSON parsing)
    net_return_pct = Column(Numeric, nullable=True)
    sharpe_ratio = Column(Numeric, nullable=True)
    max_drawdown_pct = Column(Numeric, nullable=True)
    trade_count = Column(Numeric, nullable=True)
    win_rate = Column(Numeric, nullable=True)
    total_fees = Column(Numeric, nullable=True)
    total_slippage = Column(Numeric, nullable=True)
    # Benchmark
    benchmark_return_pct = Column(Numeric, nullable=True)
    excess_return_pct = Column(Numeric, nullable=True)
    # Sweep reference (NULL for single runs)
    sweep_id = Column(String, nullable=True)
    # JSON blobs
    config_json = Column(JSON, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    trades_json = Column(JSON, nullable=False)
    equity_curve_json = Column(JSON, nullable=False)   # [{t, equity, benchmark, drawdown_pct}]
    monthly_returns_json = Column(JSON, nullable=True)  # [{year, month, return_pct}]
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    __table_args__ = (
        Index("idx_alpha_bt_user_symbol", "user_id", "symbol"),
        Index("idx_alpha_bt_sweep", "sweep_id"),
    )
```

### Pattern 5: Historical Alpha Score Computation (Degraded Mode)
**What:** In backtesting, only kline data is available (no live orderbook, no historical funding rates). The Alpha Score must be recomputed per candle using only Z-Score and Lead-Lag factors, with weights renormalized to sum to 1.0 -- exactly as the existing `compute_alpha_score()` graceful degradation already handles (unavailable factors get quality="unavailable" and are excluded from weighted sum).
**When to use:** All historical Alpha Score evaluations during backtest.
**Key insight:** The existing `compute_alpha_score()` function already supports this via quality-based renormalization. Mark orderbook and funding as "unavailable" and the function correctly renormalizes Z-Score + Lead-Lag weights.

### Pattern 6: Warmup Buffer Calculation
**What:** The warmup period is determined by the maximum of all indicator windows: `max(zscore_window, leadlag_window, hurst_lookback, atr_period)`. Extra candles are fetched before the user's start date so trading begins exactly at the chosen date.
**Example:**
```python
# Warmup = max indicator window + safety margin
warmup_candles = max(
    config.zscore_window,      # Default 60
    config.leadlag_window,     # Default 30
    config.hurst_lookback,     # Default 100
    config.atr_period + 1,     # Default 14 + 1 for Wilder's init
) + 10  # Safety buffer

# Data fetch: start_time = user_start - warmup_candles * interval_ms
# Trading starts at index warmup_candles (user's chosen start date)
```

### Anti-Patterns to Avoid
- **Float for financial metrics:** Never use float for returns, equity, P&L. All Decimal. Exception: Sharpe ratio's annualization factor (sqrt(252)) can use float for the sqrt then convert back.
- **Recomputing orderbook/funding from historical data:** This data doesn't exist historically. Degrade gracefully using existing quality-based renormalization.
- **Blocking the event loop:** Run simulation in `asyncio.to_thread()`, never directly in async handler.
- **Mixing single-run and sweep DB tables:** Keep them in the same table with a nullable `sweep_id` for sweep membership.
- **Building custom WebSocket progress protocol:** Extend existing `_broadcast_to_user()` pattern, add new message type.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Paginated kline fetching | Custom fetcher | Reuse `OrderblockDataService._fetch_klines_paginated()` pattern | Proven pagination logic with 1000-candle chunks, already handles Binance API constraints |
| Alpha Score computation | New scoring function | Reuse `compute_alpha_score()` with factors marked as "unavailable" | Existing graceful degradation handles missing factors correctly |
| ATR computation | New ATR function | Reuse `compute_atr_standalone()` from `domain/alpha_score.py` | Wilder's Smoothing already implemented correctly |
| Trailing stop logic | New stop logic | Reuse `update_trailing_stop()` from `domain/alpha_score.py` | Ratchet + freeze/resume already correct |
| WebSocket broadcasting | Custom WS protocol | Extend `BinanceStreamManager._broadcast_to_user()` | Existing user-targeted broadcast works |
| CSV export | Custom serializer | stdlib `csv.DictWriter` + `io.StringIO` | Standard Python, no library needed |
| DB snapshots | Custom persistence | Follow `save_backtest_result()` pattern from `orderblock_persistence_service.py` | Proven immutable snapshot pattern |

**Key insight:** Phase 14 already built all the computational primitives (Alpha Score, Hurst, ATR, trailing stop). Phase 15's domain logic is the simulation loop that wires these together on historical data. The new code is the loop, not the components.

## Common Pitfalls

### Pitfall 1: Warmup Period Off-by-One
**What goes wrong:** Trading starts before indicators have enough data, producing invalid scores in the first few candles.
**Why it happens:** Forgetting that Z-Score needs `window` candles of history, Hurst needs `hurst_lookback`, and ATR needs `period + 1` candles.
**How to avoid:** Compute `warmup = max(all_windows) + buffer`. Fetch `warmup` extra candles before start date. First trade can only occur at index `warmup`.
**Warning signs:** First few trades have suspiciously extreme Alpha Scores.

### Pitfall 2: Look-Ahead Bias in Benchmark
**What goes wrong:** Benchmark uses knowledge of future prices for allocation decisions.
**Why it happens:** Easy to accidentally compute benchmark returns using end-of-period prices.
**How to avoid:** Benchmark buys 50/50 BTC/XRP at the first candle's close price (after fees). Track each position's value forward through time using only past/current prices.
**Warning signs:** Benchmark returns look unrealistically good.

### Pitfall 3: Decimal Precision Cascading Errors
**What goes wrong:** Small rounding errors compound over thousands of candles, producing slightly incorrect final equity.
**Why it happens:** Repeated quantize operations can accumulate.
**How to avoid:** Use high precision (scale=10) for intermediate calculations. Only quantize for display/persistence. Track exact Decimal portfolio value.
**Warning signs:** Equity curve final value doesn't match (entry_equity + sum(all_trade_pnls) - sum(all_fees)).

### Pitfall 4: Position Sizing with Compounding
**What goes wrong:** Fixed fraction of current portfolio means position sizes grow exponentially. A bad streak after a good run can be devastating.
**Why it happens:** Compounding is the user's choice (locked decision), but the display needs to make this clear.
**How to avoid:** Track position size per trade. Show it in trade list. Drawdown chart makes risk visible.
**Warning signs:** Late trades have much larger absolute P&L than early trades (this is expected behavior with compounding, but must be displayed clearly).

### Pitfall 5: WebSocket Progress Flooding
**What goes wrong:** Sending progress update for every candle (10,000+ messages for 24 months of 1h data) overwhelms the WebSocket connection and frontend.
**Why it happens:** Naive implementation calls progress callback on every iteration.
**How to avoid:** Throttle progress updates to max 2-4 per second (every 250-500ms). Batch candle counts.
**Warning signs:** Browser tab becomes unresponsive during backtest, WebSocket disconnects.

### Pitfall 6: Sweep Parameter Explosion
**What goes wrong:** User enters wide ranges with small steps, generating thousands of combinations.
**Why it happens:** UI allows arbitrary min/max/step values.
**How to avoid:** Calculate combination count before execution. Warn at 100+. Hard reject at 500. Show estimated time.
**Warning signs:** Server becomes unresponsive, timeouts.

### Pitfall 7: Cancellation Race Condition
**What goes wrong:** Backtest loop doesn't check cancellation flag, or checks it too infrequently, making cancel appear unresponsive.
**Why it happens:** `threading.Event.is_set()` check is missing from inner loop.
**How to avoid:** Check `cancel_event.is_set()` at every candle iteration in the main simulation loop. For sweeps, check between combinations.
**Warning signs:** Cancel button clicked but simulation continues for seconds.

## Code Examples

Verified patterns from existing project codebase:

### Paginated Kline Fetch (from OrderblockDataService)
```python
# Source: backend/app/services/orderblock_data_service.py
def _fetch_klines_paginated(self, symbol, interval, start_time, end_time):
    """Fetch candles in chunks of 1000 (Binance limit)."""
    client = get_binance_public_client()
    all_klines = []
    current_start = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    interval_ms = INTERVAL_MS[interval]

    while current_start < end_ms:
        klines = client.get_klines(
            symbol, interval,
            limit=1000,
            start_time=current_start,
            end_time=end_ms,
        )
        if not klines:
            break
        all_klines.extend(klines)
        # Move past last candle's close time
        current_start = int(klines[-1][6]) + 1
        if len(klines) < 1000:
            break
    return [parse_binance_kline(k) for k in all_klines]
```

### Immutable Snapshot Persistence (from orderblock_persistence_service)
```python
# Source: backend/app/services/orderblock_persistence_service.py
def save_backtest_result(db, user_id, result, *, config_json, metrics_json, trades_json):
    run_id = f"bt_{uuid.uuid4().hex[:12]}"
    db_run = BacktestRunDB(
        id=run_id,
        user_id=user_id,
        symbol=result.symbol,
        config_json=config_json,
        metrics_json=metrics_json,
        trades_json=trades_json,
    )
    db.add(db_run)
    db.flush()
    return run_id
```

### Alpha Score with Graceful Degradation (from domain/alpha_score.py)
```python
# Source: backend/app/domain/alpha_score.py
# Existing function already handles missing factors:
# - Factors with quality="unavailable" are excluded from weighted sum
# - Remaining weights are renormalized to sum=1.0
# For backtesting: mark orderbook and funding as "unavailable"
# Z-Score (40%) + Lead-Lag (30%) renormalize to ~57%/43%

factors = [
    AlphaFactorScore(name="zscore", sub_score=zscore_sub, weight=w_z, quality="live", ...),
    AlphaFactorScore(name="leadlag", sub_score=ll_sub, weight=w_ll, quality="live", ...),
    AlphaFactorScore(name="imbalance", sub_score=Decimal("0"), weight=w_i, quality="unavailable", ...),
    AlphaFactorScore(name="funding", sub_score=Decimal("0"), weight=w_f, quality="unavailable", ...),
]
result = compute_alpha_score(factors=factors, regime=regime, threshold=threshold)
# result.quality will be "partial" (2 out of 4 factors active)
```

### WebSocket User Broadcast (from websocket_manager.py)
```python
# Source: backend/app/services/websocket_manager.py
async def _broadcast_to_user(self, user_id: str, message: dict):
    subscribers = self.user_data_subscribers.get(user_id, set())
    if not subscribers:
        return
    disconnected = set()
    for ws in subscribers:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    if disconnected:
        self.user_data_subscribers[user_id] -= disconnected
```

### Trailing Stop State Machine (from domain/alpha_score.py)
```python
# Source: backend/app/domain/alpha_score.py
# In backtesting, the trailing stop is simulated candle-by-candle:
# 1. Compute ATR from candle data
# 2. Update trailing stop state (ratchet up, never down for long positions)
# 3. Check if price hits stop level -> exit trade

state = TrailingStopState(symbol=symbol, stop_level=None, ..., direction="long", frozen=False, ...)
for candle in candles[entry_idx:]:
    atr = compute_atr_standalone(candle_history, period=atr_period)
    state = update_trailing_stop(state, current_price=candle.close, current_atr=atr,
                                  multiplier=atr_mult, data_is_fresh=True, now=candle.timestamp)
    if candle.low <= state.stop_level:  # Stop hit
        exit_trade(...)
```

### Sharpe Ratio Computation (pure Decimal)
```python
# Annualized Sharpe = mean(daily_returns) / std(daily_returns) * sqrt(trading_days)
# For crypto (24/7): 365 trading days
# Risk-free rate: 0 (standard for crypto backtesting)

def compute_sharpe_ratio(
    equity_curve: List[Decimal],  # daily equity values
    annualization_factor: int = 365,
) -> Optional[Decimal]:
    if len(equity_curve) < 2:
        return None
    daily_returns = [
        (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
        for i in range(1, len(equity_curve))
        if equity_curve[i-1] != 0
    ]
    if not daily_returns:
        return None
    n = Decimal(str(len(daily_returns)))
    mean_r = sum(daily_returns) / n
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / n
    std_r = variance.sqrt() if variance > 0 else Decimal("0")
    if std_r == 0:
        return None
    # sqrt(365) as Decimal (pre-computed to avoid float)
    import math
    ann_factor = Decimal(str(math.sqrt(annualization_factor)))
    return (mean_r / std_r * ann_factor).quantize(Decimal("0.0001"))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Float-based backtesting (numpy/pandas) | Pure Decimal simulation | Project convention | Exact reproducibility, no floating-point drift |
| Walk-forward with optimization | Simple in-sample (locked decision) | Phase design | Simpler implementation, user understands limitations |
| External backtesting frameworks (backtrader, zipline) | Custom engine reusing existing domain functions | Project convention | Better integration with Alpha Score, Decimal precision, no new dependencies |
| REST polling for progress | WebSocket progress streaming | Existing WS infrastructure | Real-time feedback during long simulations |

**Deprecated/outdated:**
- None relevant. The project is on current versions of all dependencies.

## Open Questions

1. **Equity curve data volume for long periods**
   - What we know: 24 months of 15-minute candles = ~70,000 data points. Storing all as JSON equity curve could be 2-5 MB per run.
   - What's unclear: Whether this impacts SQLite performance or frontend rendering.
   - Recommendation: Downsample equity curve to daily granularity for storage and display (max ~730 points for 24 months). Keep full-resolution only for the current session (not persisted). This keeps JSON small and Recharts performant.

2. **Benchmark price data availability**
   - What we know: Benchmark requires BTCEUR and XRPEUR prices. BTCEUR is always available. XRPEUR might need to be derived from XRPBTC * BTCEUR.
   - What's unclear: Whether Binance has direct XRPEUR klines for the full 24-month lookback.
   - Recommendation: Fetch XRPEUR directly from Binance. If unavailable, derive from XRPBTC * BTCEUR. The BinancePublicClient already supports arbitrary symbol kline fetches.

3. **Sweep execution time**
   - What we know: A single backtest over 24 months of 15-min data (~70k candles) involves Alpha Score computation per candle. Each Alpha Score call computes Z-Score, Lead-Lag, Hurst, and trailing stop.
   - What's unclear: Exact wall-clock time per combination. Estimate: 2-10 seconds per combination (pure Python Decimal math on ~70k iterations).
   - Recommendation: Time the first combination and show estimated remaining time. Hard cap at 500 combinations. For 15-min data over 24 months, consider suggesting hourly interval for sweeps.

## Sources

### Primary (HIGH confidence)
- Project codebase: `backend/app/domain/alpha_score.py` -- all factor computation functions
- Project codebase: `backend/app/services/alpha_score_data_service.py` -- data fetching patterns
- Project codebase: `backend/app/domain/orderblock_backtest.py` -- existing backtest patterns
- Project codebase: `backend/app/services/orderblock_persistence_service.py` -- immutable snapshot persistence
- Project codebase: `backend/app/services/orderblock_data_service.py` -- paginated kline fetching
- Project codebase: `backend/app/services/websocket_manager.py` -- WebSocket broadcast patterns
- Project codebase: `backend/app/db/models.py` -- DB model conventions (BacktestRunDB)
- Project codebase: `frontend/src/contexts/WebSocketContext.jsx` -- WS message handling
- Project codebase: `frontend/src/components/Orderblock.jsx` -- backtest UI patterns

### Secondary (MEDIUM confidence)
- Binance API docs: Klines endpoint supports startTime/endTime for historical data fetching
- Recharts: Line chart, Area chart, Bar chart all used in existing project components

### Tertiary (LOW confidence)
- None. All findings verified against project source code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, reuses existing project patterns entirely
- Architecture: HIGH -- follows proven domain/service/route layering, existing backtest persistence pattern
- Pitfalls: HIGH -- based on actual codebase analysis and known Decimal/WebSocket behaviors
- Domain (backtesting logic): HIGH -- Alpha Score computation already exists, simulation loop is straightforward

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable -- all components are in-project)
