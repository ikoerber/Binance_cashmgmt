# Architecture Patterns: Multi-Factor Omni-Bot Integration

**Domain:** Multi-Factor Scoring Engine, Backtesting, and Dry-Run Mode for existing BTC/EUR Cashflow-Management App
**Researched:** 2026-02-25
**Overall Confidence:** HIGH (based on thorough analysis of 20+ source files, all patterns verified against existing codebase)

---

## 1. Existing Architecture Summary

The codebase follows a strict 3-layer architecture with well-established patterns:

```
API Routes (thin)  -->  Services (DB + External APIs)  -->  Domain (pure, no I/O)
     |                         |                                |
  FastAPI                SQLAlchemy ORM                  Dataclasses + Decimal
  Pydantic               Binance REST/WS                 Deterministic Logic
  Auth deps              Singleton + TTL Cache            Pure functions
```

**Key patterns that new code MUST follow (verified in codebase):**

| Pattern | Verified In | Implication for New Code |
|---------|-------------|------------------------|
| Domain = pure, no I/O | `domain/macro_signal.py` (516 lines), `domain/sentiment.py`, `domain/combined_score.py` | `domain/alpha_score.py` must have zero imports from services |
| Service = singleton + `threading.Lock` + `CachedValue` with TTL | `SentimentDataService.__init__()`: `self._lock = threading.Lock()`, `self._cache: dict[str, CachedValue]` | `AlphaDataService` uses identical pattern |
| CachedValue with TTL + stale detection (6x factor) | `services/binance_public_client.py:CachedValue.is_stale()` | Reuse `CachedValue` class from `binance_public_client.py` |
| Combined Score = orchestration service composing sub-signals | `CombinedScoreService.get_combined_score()` fetches macro + sentiment, calls pure domain `compute_combined_score()` | Alpha Score becomes 3rd input via same pattern |
| WebSocket = `BinanceStreamManager` singleton, `aiohttp.ClientSession` | `websocket_manager.py:_run_price_stream()` uses combined stream format | Depth data via REST, not WS (see Section 4.2) |
| API route = thin, `asyncio.wait_for(asyncio.to_thread(...), timeout=30)` | `api/routes/combined.py:get_combined_score()` | All new routes follow this exact pattern |
| DB = Alembic with `render_as_batch=True`, JSON columns for config snapshots | `BacktestRunDB.config_json`, `BacktestRunDB.trades_json` | New tables use same JSON-snapshot pattern |
| Frontend = TanStack Query + WebSocket context, component-per-page, Plain CSS | `App.jsx` routes, `SymbolLayout.jsx` sub-nav groups | New pages under new Bot nav group |
| Funding Rate = OKX public API (EU-compliant), shared across modules | `SentimentDataService._get_funding_rate()` with `OKX_FUNDING_URL` | Alpha Score reuses cached funding rate, no duplication |

---

## 2. New Components Inventory

### Complete list of new and modified components:

| Layer | Component | Type | Description |
|-------|-----------|------|-------------|
| **Domain** | `domain/alpha_score.py` | NEW | Pure scoring: 4 factors to Alpha Score (-5 to +5) |
| **Domain** | `domain/trailing_exit.py` | NEW | Pure ATR-adaptive trailing stop logic |
| **Domain** | `domain/alpha_backtest.py` | NEW | Pure walk-forward backtest engine with equity curve |
| **Domain** | `domain/combined_score.py` | MODIFIED | Add optional `AlphaInput` as 3rd signal (backward-compatible) |
| **Service** | `services/alpha_data_service.py` | NEW | Singleton, fetches klines + depth + reuses funding, TTL cache |
| **Service** | `services/alpha_backtest_service.py` | NEW | Orchestrates backtest runs, persists results |
| **Service** | `services/dry_run_service.py` | NEW | Async real-time signal logging loop, no order execution |
| **Service** | `services/combined_score_service.py` | MODIFIED | Add alpha score as 3rd input with graceful degradation |
| **Service** | `services/binance_public_client.py` | MODIFIED | Add `get_depth()` method for orderbook snapshots |
| **DB** | `DryRunLogDB` | NEW TABLE | Logged decisions with factor breakdowns |
| **DB** | `AlphaBacktestRunDB` | NEW TABLE | Backtest results (separate from OB backtest) |
| **DB** | `UserSettingsDB` | MODIFIED | Add bot-related settings columns |
| **API** | `api/routes/alpha.py` | NEW | Alpha Score endpoints |
| **API** | `api/routes/backtest.py` | NEW | Backtest endpoints (scoped to alpha, not OB) |
| **API** | `api/routes/dryrun.py` | NEW | Dry-run mode endpoints |
| **API** | `main.py` | MODIFIED | Register 3 new routers, optional lifespan init |
| **Frontend** | `components/AlphaScore.jsx` | NEW | Alpha Score detail page |
| **Frontend** | `components/Backtest.jsx` | NEW | Backtest results + equity curve charts |
| **Frontend** | `components/DryRunLog.jsx` | NEW | Dry-run decision log |
| **Frontend** | `components/SymbolLayout.jsx` | MODIFIED | Add Bot nav group (4th section) |
| **Frontend** | `App.jsx` | MODIFIED | Add 3 new routes under `:symbol` |
| **Frontend** | `api/client.js` | MODIFIED | Add new API functions |
| **Frontend** | `components/CombinedScore.jsx` | MODIFIED | Show alpha as 3rd sub-signal card |
| **Frontend** | `components/Dashboard.jsx` | MODIFIED | CombinedScoreWidget gains alpha indicator |

---

## 3. Domain Layer: New Modules (Pure, No I/O)

### 3.1 `domain/alpha_score.py` -- Multi-Factor Scoring Engine

**Design principle:** Identical pattern to `domain/macro_signal.py` (SignalScore dataclass, pure scoring functions, composite computation) and `domain/sentiment.py` (pillar weights, renormalization on missing data).

```python
# --- Dataclasses ---

@dataclass
class AlphaFactorScore:
    """Score for a single alpha factor. Pattern: SignalScore from macro_signal.py."""
    factor: str              # "z_score_mean_reversion", "lead_lag_momentum", etc.
    raw_value: Decimal       # The raw indicator value (e.g., z-score of -1.5)
    normalized_score: Decimal  # -1.0 to +1.0 (clamped)
    weight: Decimal          # Factor weight (sum of active = 1.0 after renorm)
    quality: str             # "live", "cached", "stale", "unavailable"
    reason: str              # Human-readable explanation

@dataclass
class AlphaScoreResult:
    """Complete alpha score output. Pattern: MacroSignalResult."""
    alpha_score: Decimal         # -5.0 to +5.0
    direction: str               # "LONG", "SHORT", "NEUTRAL"
    confidence: Decimal          # 0.0 to 1.0 (active_factors / total_factors)
    factor_scores: List[AlphaFactorScore]
    active_factors: int
    total_factors: int
    symbol: str
    timestamp: datetime
```

**Four factors with empirical weights:**

| Factor | Weight | Input Data | Scoring Logic | Rationale |
|--------|--------|------------|---------------|-----------|
| Z-Score Mean Reversion | 40% | 50-period close prices (klines) | `z = (price - SMA_50) / std_50`; score = `-z` (contrarian); clamped to [-1, +1] | Mean reversion is the strongest signal in range-bound crypto markets; negative z-score = below mean = buy signal |
| Lead-Lag Momentum | 30% | BTC/USDT 5m klines + symbol 5m klines | Cross-correlation at lags 1-5; if BTC leads and is rising, symbol expected to follow | BTC leads altcoin price movements by 1-5 candles; well-documented in crypto microstructure |
| Orderbook Imbalance | 20% | Binance depth20 snapshot | `ratio = bid_vol / (bid_vol + ask_vol)`; score = `2 * (ratio - 0.5)`; clamped | Immediate supply/demand pressure; short-lived but impactful for timing |
| Funding Rate | 10% | OKX public API (REUSED from SentimentDataService) | Contrarian: high positive funding = overleveraged longs = bearish; score via existing `_FUNDING_RATE_BRACKETS` | Reuses existing scoring logic from `domain/sentiment.py:score_funding_rate()` |

**Core computation function:**

```python
# Factor weights (renormalized when factors unavailable)
ALPHA_FACTOR_WEIGHTS = {
    "z_score": Decimal("0.40"),
    "lead_lag": Decimal("0.30"),
    "orderbook": Decimal("0.20"),
    "funding": Decimal("0.10"),
}

def compute_alpha_score(
    factor_scores: List[AlphaFactorScore],
    weights: Dict[str, Decimal] = ALPHA_FACTOR_WEIGHTS,
) -> AlphaScoreResult:
    """
    Weighted sum of normalized factor scores, scaled to -5..+5.

    Pattern: follows compute_sentiment_v3() for weight renormalization:
    - If a factor is unavailable, redistribute its weight proportionally
    - Confidence = active / total (pattern from combined_score.py)
    - Direction: score > 1.5 = LONG, < -1.5 = SHORT, else NEUTRAL

    All Decimal, no float. Deterministic for same inputs.
    """
```

**Why -5 to +5 range:** Provides sufficient granularity (11 integer values) for the 5 direction levels (STRONG LONG / LONG / NEUTRAL / SHORT / STRONG SHORT) without matching the macro signal's -8..+8 (which has 6 underlying factors). Both get normalized to -1..+1 before feeding into Combined Score.

### 3.2 `domain/trailing_exit.py` -- ATR-Adaptive Trailing Stop

```python
@dataclass
class TrailingStopState:
    """Immutable state snapshot for trailing stop. New state returned per candle."""
    active: bool
    direction: str               # "LONG" or "SHORT"
    entry_price: Decimal
    current_stop: Decimal
    atr_value: Decimal
    atr_multiplier: Decimal
    highest_since_entry: Decimal  # For LONG: ratchets up
    lowest_since_entry: Decimal   # For SHORT: ratchets down
    triggered: bool              # True if stop was hit

def init_trailing_stop(
    direction: str,
    entry_price: Decimal,
    atr: Decimal,
    multiplier: Decimal = Decimal("2.0"),
) -> TrailingStopState:
    """Initialize trailing stop state at trade entry."""

def update_trailing_stop(
    state: TrailingStopState,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    atr: Decimal,
) -> TrailingStopState:
    """
    Pure function: given current state + new candle OHLC, returns new state.

    For LONG:
      new_highest = max(state.highest_since_entry, high)
      new_stop = max(state.current_stop, new_highest - atr * multiplier)
      triggered = low <= new_stop

    For SHORT:
      new_lowest = min(state.lowest_since_entry, low)
      new_stop = min(state.current_stop, new_lowest + atr * multiplier)
      triggered = high >= new_stop
    """
```

**ATR reuse:** `compute_atr()` exists in `domain/orderblock.py` (Wilder's Smoothing). Import it directly -- the function is pure and has no orderblock-specific logic. If the team prefers cleaner separation, extract to `domain/indicators.py` as a shared module. For phase 1, importing from `orderblock.py` is pragmatic and avoids unnecessary refactoring.

### 3.3 `domain/alpha_backtest.py` -- Walk-Forward Backtesting Engine

```python
@dataclass
class AlphaBacktestConfig:
    symbol: str
    months: int                       # Lookback (default: 24)
    signal_threshold: Decimal         # Alpha score for entry (default: Decimal("2.0"))
    exit_threshold: Decimal           # Alpha score for exit (default: Decimal("0.0"))
    atr_trailing_multiplier: Decimal  # Trailing stop ATR mult (default: Decimal("2.0"))
    position_size_pct: Decimal        # Percent of capital per trade (default: Decimal("5"))
    fee_pct: Decimal                  # Trading fee (default: Decimal("0.1"))
    initial_capital: Decimal          # Starting capital EUR (default: Decimal("10000"))

@dataclass
class AlphaBacktestTrade:
    entry_timestamp: datetime
    exit_timestamp: Optional[datetime]
    direction: str                 # "LONG" or "SHORT"
    entry_price: Decimal
    exit_price: Optional[Decimal]
    alpha_score_at_entry: Decimal
    exit_reason: str              # "signal_reversal", "trailing_stop", "time_exit", "open"
    pnl_eur: Optional[Decimal]
    pnl_pct: Optional[Decimal]
    holding_duration_candles: int

@dataclass
class AlphaBacktestMetrics:
    total_trades: int
    win_rate: Optional[Decimal]
    total_pnl_eur: Decimal
    total_pnl_pct: Decimal
    max_drawdown_pct: Decimal
    sharpe_ratio: Optional[Decimal]     # Annualized, based on daily returns
    sortino_ratio: Optional[Decimal]    # Downside deviation only
    hodl_pnl_pct: Decimal               # Benchmark: buy-and-hold
    alpha_vs_hodl: Decimal              # Strategy return - HODL return
    avg_holding_duration: Decimal
    longest_drawdown_candles: int
    trades_per_month: Decimal

@dataclass
class AlphaBacktestResult:
    config: AlphaBacktestConfig
    metrics: AlphaBacktestMetrics
    trades: List[AlphaBacktestTrade]
    equity_curve: List[dict]    # [{"timestamp": ..., "equity": ...}, ...]
    drawdown_curve: List[dict]  # [{"timestamp": ..., "drawdown_pct": ...}, ...]
    timestamp: datetime

def run_alpha_backtest(
    candles: List[Candle],
    config: AlphaBacktestConfig,
) -> AlphaBacktestResult:
    """
    Walk-forward backtest: at each candle, compute alpha score using
    only data available at that point (no look-ahead bias).

    Algorithm:
    1. For each candle i (starting at warmup period = 50):
       a. Compute Z-Score from candles[i-50:i] (trailing window)
       b. Compute Lead-Lag from cross-asset klines (if available)
       c. Score = weighted sum of available factors
       d. If no position and |score| > signal_threshold: ENTER
       e. If position and score crosses exit_threshold: EXIT (signal reversal)
       f. If position: update trailing stop, check trigger
       g. Track equity curve point
    2. Compute HODL benchmark: (last_close / first_close - 1)
    3. Compute Sharpe from daily equity returns

    Critical: This is DIFFERENT from orderblock backtesting.
    OB backtest: detect zones offline, then simulate zone touches.
    Alpha backtest: compute score at each candle, enter/exit on score.
    No shared logic beyond the Candle dataclass.
    """
```

---

## 4. Service Layer: New and Modified

### 4.1 `services/alpha_data_service.py` -- Data Provider (NEW)

**Pattern:** Identical to `SentimentDataService` -- singleton via module-level instance, `threading.Lock`, `CachedValue` with TTL, graceful degradation.

```python
# Cache TTLs (aligned with existing service patterns)
KLINE_CACHE_TTL = timedelta(seconds=30)    # Same as MacroDataService.BINANCE_CACHE_TTL
DEPTH_CACHE_TTL = timedelta(seconds=5)     # Orderbook is very short-lived
CROSS_KLINE_CACHE_TTL = timedelta(seconds=30)  # BTC/USDT for lead-lag

class AlphaDataService:
    """
    Singleton service for Alpha Score data.

    Data sources:
    1. Binance Public REST: Symbol klines (for Z-Score) -- via BinancePublicClient
    2. Binance Public REST: BTC/USDT klines (for Lead-Lag) -- via BinancePublicClient
    3. Binance Public REST: depth20 (orderbook imbalance) -- NEW method on BinancePublicClient
    4. OKX Funding Rate -- REUSED from SentimentDataService (no new fetch)

    Thread-safe. Graceful degradation: missing data source = factor unavailable,
    weight redistributed to available factors (pattern from sentiment.py).
    """

    def __init__(self):
        self._cache: dict[str, CachedValue] = {}
        self._lock = threading.Lock()

    def get_alpha_score(self, symbol: str = "BTCEUR") -> dict:
        """
        Fetches all factor data, computes alpha score, returns serialized dict.

        Steps:
        1. Fetch/cache symbol klines (50 candles, 5m interval)
        2. Fetch/cache BTC/USDT klines (50 candles, 5m)
        3. Fetch/cache depth20 snapshot
        4. Read funding rate from SentimentDataService cache
        5. Build factor inputs
        6. Call domain/alpha_score.compute_alpha_score()
        7. Serialize and return
        """

    def _get_klines(self, symbol: str, now: datetime) -> Tuple[list, str]:
        """Fetch klines via BinancePublicClient with TTL cache."""

    def _get_depth(self, symbol: str, now: datetime) -> Tuple[dict, str]:
        """Fetch depth20 via BinancePublicClient.get_depth() with TTL cache."""

    def _get_funding_rate(self, base_asset: str) -> Tuple[Optional[Decimal], str]:
        """Reuse funding rate from SentimentDataService cache. No new fetch."""
        sentiment_svc = get_sentiment_data_service()
        with sentiment_svc._lock:
            return sentiment_svc._get_funding_rate(
                datetime.now(timezone.utc),
                f"{base_asset}-USDT-SWAP"
            )
```

**Singleton pattern (copy of existing):**

```python
_service_instance: Optional[AlphaDataService] = None
_service_lock = threading.Lock()

def get_alpha_data_service() -> AlphaDataService:
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = AlphaDataService()
    return _service_instance
```

### 4.2 Orderbook Depth Integration Decision: REST over WebSocket

**Current WebSocket streams in `BinanceStreamManager`:**
- `{symbol}@ticker` for each KNOWN_PAIR (price updates)
- `userDataStream` (executionReport, outboundAccountPosition)

**Decision: Use REST polling for depth20, NOT WebSocket.**

| Criterion | WebSocket `depth20@1000ms` | REST `GET /api/v3/depth?limit=20` |
|-----------|--------------------------|-----------------------------------|
| Latency | ~1s real-time | ~5s (TTL cache) |
| Bandwidth | Always-on, even when bot tab not active | On-demand only |
| Complexity | Modify `BinanceStreamManager`, add depth parsing | New `get_depth()` on existing `BinancePublicClient` |
| Factor weight | 20% of alpha score | 20% of alpha score |
| Acceptable staleness | 5s is fine for 20%-weight factor | Yes |

**Verdict: REST.** The 5s staleness is acceptable for a factor that contributes 20% weight to a score that itself contributes 30% to the Combined Score. The effective impact of 5s staleness is `20% * 30% = 6%` of the final signal. Adding always-on depth streaming to the WebSocket manager increases bandwidth and complexity with negligible signal quality improvement.

**New method on `BinancePublicClient`:**

```python
class BinancePublicClient:
    # ... existing methods ...

    @retry_on_transient_error()
    def get_depth(self, symbol: str, limit: int = 20) -> dict:
        """
        Fetch orderbook depth snapshot.

        GET /api/v3/depth?symbol=BTCEUR&limit=20

        Returns:
            {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}
        """
        resp = requests.get(
            f"{BASE_URL}/api/v3/depth",
            params={"symbol": symbol, "limit": limit},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()
```

### 4.3 `services/combined_score_service.py` (MODIFIED)

**Current flow (verified in codebase):**
```python
def get_combined_score(self, interval_minutes, symbol):
    macro_result = macro_service.get_signal(...)        # DirectionInput
    sentiment_data = sentiment_service.get_sentiment(...)  # SizingInput
    result = compute_combined_score(direction, sizing)  # Pure domain
    return self._serialize(result, macro_result, sentiment_data)
```

**New flow (backward-compatible):**
```python
def get_combined_score(self, interval_minutes, symbol):
    macro_result = macro_service.get_signal(...)
    sentiment_data = sentiment_service.get_sentiment(...)

    # NEW: Try to get alpha score (graceful degradation)
    alpha_input = None
    try:
        alpha_service = get_alpha_data_service()
        alpha_data = alpha_service.get_alpha_score(symbol=symbol)
        alpha_input = AlphaInput(
            alpha_score=Decimal(str(alpha_data["alpha_score"])),
            direction=alpha_data["direction"],
            confidence=Decimal(str(alpha_data["confidence"])),
            active_factors=alpha_data["active_factors"],
            total_factors=alpha_data["total_factors"],
        )
    except Exception:
        logger.warning("Alpha Score unavailable, using 2-signal mode")

    result = compute_combined_score(direction, sizing, alpha=alpha_input)
    return self._serialize(result, macro_result, sentiment_data, alpha_data)
```

**Weight redistribution in `domain/combined_score.py`:**

| Signal | Without Alpha (current) | With Alpha |
|--------|------------------------|------------|
| MacroSignal (Direction) | 60% | 40% |
| Sentiment (Sizing) | 40% | 30% |
| Alpha Score (Precision) | -- | 30% |

```python
# In domain/combined_score.py

# Existing constants (unchanged for backward compatibility)
DIRECTION_WEIGHT = Decimal("0.60")
SIZING_WEIGHT = Decimal("0.40")

# New constants for 3-signal mode
DIRECTION_WEIGHT_WITH_ALPHA = Decimal("0.40")
SIZING_WEIGHT_WITH_ALPHA = Decimal("0.30")
ALPHA_WEIGHT = Decimal("0.30")

@dataclass
class AlphaInput:
    """Normalized Alpha Score input for Combined Scoring."""
    alpha_score: Decimal          # -5.0 to +5.0
    direction: str                # "LONG", "SHORT", "NEUTRAL"
    confidence: Decimal           # 0.0 to 1.0
    active_factors: int
    total_factors: int

def compute_combined_score(
    direction: DirectionInput,
    sizing: SizingInput,
    alpha: Optional[AlphaInput] = None,  # NEW parameter, backward-compatible
) -> CombinedScoreResult:
    """
    When alpha is None: uses existing 60/40 weights (zero behavior change).
    When alpha is provided: uses 40/30/30 weights.

    Alpha normalization: score / 5.0 -> -1.0..+1.0 (same as macro's raw/8)
    """
```

### 4.4 `services/dry_run_service.py` (NEW)

**Architecture decision: DB-based logging (not file-based).**

Reasons:
1. All persistent state in this app lives in SQLite -- files would be inconsistent
2. DB is queryable (filter by symbol, date, decision type) via standard API patterns
3. Frontend can display via TanStack Query (same as every other data source)
4. Position state reconstructable from log on process restart

```python
class DryRunService:
    """
    Singleton service for dry-run mode.

    Lifecycle:
    - start(user_id, symbols) -> creates async task per symbol
    - stop(user_id) -> cancels all tasks
    - _tick(user_id, symbol) -> single evaluation cycle (runs every N seconds)

    Each tick:
    1. Fetch alpha score (via AlphaDataService)
    2. Fetch combined score (via CombinedScoreService)
    3. Read current market price (from BinanceStreamManager.current_prices)
    4. Evaluate entry/exit conditions against virtual position
    5. Update trailing stop state (in-memory, reconstructed from DB on restart)
    6. Log decision to DryRunLogDB
    7. Optionally broadcast via WebSocket to frontend

    State:
    - _running: Dict[str, bool] -- per-user running state
    - _tasks: Dict[str, List[asyncio.Task]] -- per-user async tasks
    - _positions: Dict[Tuple[str, str], VirtualPosition] -- (user_id, symbol) -> position
    """

    def __init__(self):
        self._running: Dict[str, bool] = {}
        self._tasks: Dict[str, List[asyncio.Task]] = {}
        self._positions: Dict[Tuple[str, str], Optional[VirtualPosition]] = {}
        self._lock = threading.Lock()

    async def start(self, user_id: str, symbols: List[str], interval_sec: int = 60):
        """Start dry-run evaluation loop for specified symbols."""

    async def stop(self, user_id: str):
        """Stop all dry-run tasks for user."""

    async def _tick(self, user_id: str, symbol: str):
        """
        Single evaluation cycle. Runs in event loop (async).

        Critical: Uses asyncio.to_thread() for DB writes (same pattern
        as websocket_fill_handler.py:handle_fill_event).
        """

    def _reconstruct_position(self, user_id: str, symbol: str) -> Optional[VirtualPosition]:
        """
        Reconstruct virtual position from DryRunLogDB on service restart.
        Queries last ENTRY_LONG/ENTRY_SHORT + subsequent updates.
        """
```

**Virtual position tracking:**

```python
@dataclass
class VirtualPosition:
    direction: str           # "LONG" or "SHORT"
    entry_price: Decimal
    entry_timestamp: datetime
    trailing_stop: TrailingStopState
    alpha_score_at_entry: Decimal
```

### 4.5 `services/alpha_backtest_service.py` (NEW)

**Pattern:** Follows `services/orderblock_data_service.py` -- orchestrates data fetching, calls domain logic, persists results to DB.

```python
class AlphaBacktestService:
    """
    Orchestrates alpha score backtesting.

    Flow:
    1. Fetch historical klines (paginated via BinancePublicClient, up to 24 months)
    2. Optionally fetch BTC/USDT klines for lead-lag (same period)
    3. Call domain/alpha_backtest.run_alpha_backtest() (pure)
    4. Persist to AlphaBacktestRunDB (immutable snapshot)
    5. Return serialized results

    Runs synchronously (CPU-bound). Called via asyncio.to_thread() from API route.
    """

    def run_backtest(self, user_id: str, symbol: str, config: dict) -> dict:
        """Run backtest and persist results. Returns serialized result dict."""

    def get_runs(self, user_id: str, symbol: str) -> List[dict]:
        """Get historical backtest runs for display."""

    def get_run_detail(self, user_id: str, run_id: str) -> dict:
        """Get single run with trades + equity curve."""
```

---

## 5. Database Layer: New Tables and Modifications

### 5.1 `DryRunLogDB` (NEW TABLE)

```python
class DryRunDecisionEnum(str, enum.Enum):
    ENTRY_LONG = "ENTRY_LONG"
    ENTRY_SHORT = "ENTRY_SHORT"
    EXIT_SIGNAL = "EXIT_SIGNAL"      # Score crossed exit threshold
    EXIT_TRAILING = "EXIT_TRAILING"  # Trailing stop triggered
    HOLD = "HOLD"                    # Has position, no exit signal
    NO_SIGNAL = "NO_SIGNAL"          # No position, score below threshold

class DryRunLogDB(Base):
    __tablename__ = "dry_run_logs"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)

    decision = Column(SQLEnum(DryRunDecisionEnum), nullable=False)
    alpha_score = Column(Numeric(precision=10, scale=4), nullable=False)
    combined_score = Column(Numeric(precision=10, scale=4), nullable=True)
    market_price = Column(Numeric(precision=20, scale=10), nullable=False)

    # Virtual position state at time of decision
    has_position = Column(Boolean, nullable=False, default=False)
    position_direction = Column(String, nullable=True)   # "LONG" or "SHORT"
    position_entry_price = Column(Numeric(precision=20, scale=10), nullable=True)
    trailing_stop_price = Column(Numeric(precision=20, scale=10), nullable=True)
    virtual_pnl_pct = Column(Numeric(precision=10, scale=4), nullable=True)

    # Factor breakdown (JSON for flexibility -- same pattern as config_json on zones/backtest)
    factor_scores_json = Column(JSON, nullable=False)
    reason = Column(Text, nullable=False)  # Human-readable decision rationale

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("idx_dryrun_user_symbol_created", "user_id", "symbol", "created_at"),
        Index("idx_dryrun_user_decision", "user_id", "decision"),
    )
```

**Growth estimate:** At 1 log/minute per symbol, 3 symbols = 4,320 rows/day = ~130K rows/month. With index on `(user_id, symbol, created_at)`, queries remain fast. Add 30-day retention cleanup as a scheduled task (not blocking for v3.0).

### 5.2 `AlphaBacktestRunDB` (NEW TABLE)

```python
class AlphaBacktestRunDB(Base):
    __tablename__ = "alpha_backtest_runs"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)

    data_start = Column(DateTime, nullable=False)
    data_end = Column(DateTime, nullable=False)
    candle_count = Column(Numeric(precision=10, scale=0), nullable=False)

    # Core metrics (denormalized for list queries without JSON parsing)
    total_trades = Column(Numeric(precision=10, scale=0), nullable=False)
    win_rate = Column(Numeric(precision=10, scale=4), nullable=True)
    total_pnl_pct = Column(Numeric(precision=10, scale=4), nullable=False)
    max_drawdown_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    sharpe_ratio = Column(Numeric(precision=10, scale=4), nullable=True)
    hodl_pnl_pct = Column(Numeric(precision=10, scale=4), nullable=False)
    alpha_vs_hodl = Column(Numeric(precision=10, scale=4), nullable=False)

    # Full results as JSON (immutable snapshot -- pattern from BacktestRunDB)
    config_json = Column(JSON, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    trades_json = Column(JSON, nullable=False)
    equity_curve_json = Column(JSON, nullable=True)  # Can be large, optional

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("idx_alpha_bt_user_symbol", "user_id", "symbol"),
    )
```

### 5.3 `UserSettingsDB` Column Additions (MODIFIED)

```python
# New columns added to existing UserSettingsDB:

# Bot Configuration
bot_enabled = Column(Boolean, nullable=False, server_default="0")
bot_mode = Column(String, nullable=False, server_default="dry_run")  # "dry_run" or "disabled"

# Alpha Score Tuning
alpha_signal_threshold = Column(Numeric(precision=10, scale=4), nullable=True)   # Default: 2.0
alpha_exit_threshold = Column(Numeric(precision=10, scale=4), nullable=True)     # Default: 0.0
alpha_trailing_atr_mult = Column(Numeric(precision=10, scale=4), nullable=True)  # Default: 2.0
alpha_eval_interval_sec = Column(Numeric(precision=5, scale=0), nullable=True)   # Default: 60
```

All nullable with defaults handled in service layer -- follows exact pattern of existing `ob_interval`, `ob_atr_multiplier` etc.

---

## 6. API Layer: New Routes

### 6.1 `api/routes/alpha.py` (NEW)

| Route | Method | Description | Pattern Source |
|-------|--------|-------------|---------------|
| `/api/alpha/{user_id}/score` | GET | Current alpha score for symbol (`?symbol=BTCEUR`) | `combined.py:get_combined_score` |
| `/api/alpha/{user_id}/factors` | GET | Detailed factor breakdown (`?symbol=BTCEUR`) | `sentiment.py:get_sentiment` |

### 6.2 `api/routes/backtest.py` (NEW)

| Route | Method | Description | Pattern Source |
|-------|--------|-------------|---------------|
| `/api/backtest/{user_id}/alpha/run` | POST | Run alpha backtest (body: config JSON) | `orderblock.py:analyze` |
| `/api/backtest/{user_id}/alpha/runs` | GET | List backtest runs (`?symbol=`) | `orderblock.py:get_backtest_runs` |
| `/api/backtest/{user_id}/alpha/runs/{run_id}` | GET | Backtest detail with trades + equity curve | `orderblock.py:get_backtest_run` |

### 6.3 `api/routes/dryrun.py` (NEW)

| Route | Method | Description | Pattern Source |
|-------|--------|-------------|---------------|
| `/api/dryrun/{user_id}/start` | POST | Start dry-run (`body: {symbols: [...]}`) | New (lifecycle management) |
| `/api/dryrun/{user_id}/stop` | POST | Stop dry-run | New |
| `/api/dryrun/{user_id}/status` | GET | Current status + virtual positions | New |
| `/api/dryrun/{user_id}/log` | GET | Decision log (`?symbol=&limit=100&decision=`) | Similar to `alerts.py:get_alerts` |
| `/api/dryrun/{user_id}/log/stats` | GET | Aggregated performance stats | New |

### 6.4 Modified Routes

| Route | Modification |
|-------|-------------|
| `/api/combined/{user_id}/score` | Response gains `alpha` sub-signal object when available |
| `/api/settings/{user_id}` GET/PUT | Gains bot-related fields in request/response |

### 6.5 `main.py` Registration

```python
from app.api.routes import alpha, backtest, dryrun

# In route registration block (after existing routers):
app.include_router(alpha.router, dependencies=api_auth)
app.include_router(backtest.router, dependencies=api_auth)
app.include_router(dryrun.router, dependencies=api_auth)
```

---

## 7. Frontend Layer: New Components and Modifications

### 7.1 Navigation: 4-Area Sub-Nav

**Current in `SymbolLayout.jsx`:** 3 groups (Trading / Analyse / Admin)
**New:** 4 groups (Trading / Analyse / Bot / Admin)

```jsx
// NEW group added to SymbolLayout.jsx subnav:
<div className="subnav-group">
  <span className="subnav-group-label">Bot</span>
  <NavLink to={`/s/${symbol}/alpha`}>Alpha Score</NavLink>
  <NavLink to={`/s/${symbol}/backtest`}>Backtest</NavLink>
  <NavLink to={`/s/${symbol}/dryrun`}>Dry Run</NavLink>
</div>
```

**New routes in `App.jsx`:**
```jsx
// Inside <Route path="s/:symbol" element={<SymbolLayout />}>:
<Route path="alpha" element={<AlphaScore />} />
<Route path="backtest" element={<Backtest />} />
<Route path="dryrun" element={<DryRunLog />} />
```

### 7.2 `AlphaScore.jsx` (NEW)

- Hero card: Alpha Score gauge (-5 to +5) with direction badge (LONG/SHORT/NEUTRAL)
- 4 Factor cards: Raw value, normalized bar (-1..+1), weight badge, quality indicator
- Trailing stop panel (when dry-run position active): entry price, current stop, distance
- Score history chart (Recharts line chart, last 50 data points from polling)
- Accent color: Teal `#0d9488` (distinct from existing amber/indigo/sky-blue)

### 7.3 `Backtest.jsx` (NEW)

- Config form: Symbol selector, months (6/12/18/24), threshold slider, ATR multiplier
- Run button (POST, loading state)
- KPI cards: Total PnL%, Win Rate%, Sharpe, Max Drawdown%, vs HODL delta
- Equity curve chart (Recharts area chart): Strategy line + HODL line overlay
- Trade table (sortable): Entry/Exit timestamps, direction, PnL%, duration, exit reason
- Historical runs list (collapsible, showing key metrics)
- Accent color: Follows Bot group color

### 7.4 `DryRunLog.jsx` (NEW)

- Status card: Running/Stopped badge, Start/Stop buttons
- Virtual position card (when active): Direction, entry price, current PnL, trailing stop level
- Decision timeline: Chronological list with alpha score sparkline, color-coded by decision type
- Filter bar: Symbol, decision type, date range
- Performance summary cards: Virtual trades count, virtual win rate, virtual total PnL
- Auto-refresh: TanStack Query polling every 10s when running

### 7.5 Modified Components

**`CombinedScore.jsx`:** Add 3rd sub-signal card for Alpha Score:
```jsx
// Existing: direction card (MacroSignal) + sizing card (Sentiment)
// NEW: alpha card when data.alpha is present
{data.alpha && (
  <div className="sub-signal-card alpha-card">
    <h4>Alpha Score (30%)</h4>
    <span className="alpha-score">{data.alpha.alpha_score}</span>
    <span className="alpha-direction">{data.alpha.direction}</span>
    {/* Expandable factor details */}
  </div>
)}
```

**`Dashboard.jsx`:** The CombinedScoreWidget (already integrated in v2.0) automatically shows the alpha signal because it reads from the same `/api/combined/{user_id}/score` endpoint.

**`api/client.js`:** Add new API functions:
```javascript
// Alpha Score
export const getAlphaScore = async (userId, symbol = 'BTCEUR') => { ... };

// Backtest
export const runAlphaBacktest = async (userId, config) => { ... };
export const getAlphaBacktestRuns = async (userId, symbol) => { ... };
export const getAlphaBacktestRun = async (userId, runId) => { ... };

// Dry Run
export const startDryRun = async (userId, symbols) => { ... };
export const stopDryRun = async (userId) => { ... };
export const getDryRunStatus = async (userId) => { ... };
export const getDryRunLog = async (userId, params) => { ... };
export const getDryRunStats = async (userId) => { ... };
```

---

## 8. Data Flow Diagrams

### 8.1 Alpha Score Computation (Real-Time)

```
[Binance Public REST]                [OKX Public REST]
  |                                     |
  +-- GET /klines (BTCEUR, 5m, 50)     |  (reused from
  +-- GET /klines (BTCUSDT, 5m, 50)    |   SentimentDataService
  +-- GET /depth (BTCEUR, limit=20)     |   cache)
  |                                     |
  v                                     v
[AlphaDataService]              [SentimentDataService]
  (30s cache)     (5s cache)      (15min cache)
       |               |              |
       +-------+-------+--------------+
               |
               v
    [domain/alpha_score.py]
    compute_alpha_score(factors, weights)
               |
               v
       AlphaScoreResult
               |
       +-------+-------+
       |       |       |
       v       v       v
   [Combined  [Dry   [API
    Score]    Run]   /alpha/score]
```

### 8.2 Combined Score v2 (With Alpha)

```
[MacroDataService]       [SentimentDataService]     [AlphaDataService]
      |                         |                          |
      v                         v                          v
  DirectionInput            SizingInput              AlphaInput (optional)
      |                         |                          |
      +-------------------------+--------------------------+
                                |
                                v
                [domain/combined_score.py]
                compute_combined_score(dir, sizing, alpha?)
                                |
                    +-----------+-----------+
                    |                       |
                    v                       v
            alpha=None:              alpha=present:
            60% dir + 40% siz       40% dir + 30% siz + 30% alpha
                    |                       |
                    +-----------+-----------+
                                |
                                v
                      CombinedScoreResult
                                |
                                v
                    [API /combined/score]
                                |
                                v
                 [CombinedScore.jsx / Dashboard Widget]
```

### 8.3 Dry-Run Mode Lifecycle

```
[User clicks "Start Dry Run" in DryRunLog.jsx]
            |
            v
    POST /api/dryrun/{user_id}/start
            |
            v
    [DryRunService.start()]
    Creates async task per symbol
            |
            v
    [_tick() loop every 60s]
        |
        +-- 1. alpha_data_service.get_alpha_score(symbol)
        +-- 2. combined_score_service.get_combined_score(symbol)
        +-- 3. stream_manager.current_prices[symbol]  (live price)
        +-- 4. Evaluate: entry? exit? hold?
        +-- 5. Update trailing stop state (if position)
        +-- 6. asyncio.to_thread(log_decision_to_db)  -->  [DryRunLogDB]
        +-- 7. (optional) broadcast via WS to frontend
        |
        v
    [Frontend polls GET /api/dryrun/log every 10s]
            |
            v
    [DryRunLog.jsx renders decision timeline]
```

### 8.4 Backtest Flow

```
[User configures and clicks "Run Backtest" in Backtest.jsx]
            |
            v
    POST /api/backtest/{user_id}/alpha/run
            |
            v
    asyncio.to_thread(alpha_backtest_service.run_backtest)
            |
            +-- 1. Fetch 24-month klines (paginated, BinancePublicClient)
            +-- 2. (Optional) Fetch BTC/USDT klines for lead-lag
            +-- 3. Call domain/alpha_backtest.run_alpha_backtest()
            |         Walk-forward at each candle:
            |           a. Compute z-score from trailing 50-candle window
            |           b. Compute lead-lag from BTC correlation
            |           c. Weighted score
            |           d. Enter if |score| > threshold, exit on reversal/trailing
            |           e. Track equity curve point
            +-- 4. Compute HODL benchmark
            +-- 5. Compute Sharpe/Sortino from equity curve
            +-- 6. Persist to AlphaBacktestRunDB (immutable JSON snapshot)
            |
            v
    [API returns serialized AlphaBacktestResult]
            |
            v
    [Backtest.jsx renders KPIs + equity chart + trade table]
```

---

## 9. Integration Points (Explicit)

### 9.1 New Components Depending on Existing Code

| New Component | Depends On | How |
|---------------|------------|-----|
| `domain/alpha_score.py` | Nothing | Pure module, zero imports from existing code |
| `domain/trailing_exit.py` | `domain/orderblock.py:compute_atr()` | Import function (pure, no side effects) |
| `domain/alpha_backtest.py` | `domain/orderblock.py:Candle` dataclass | Import dataclass |
| `domain/combined_score.py` (mod) | New `AlphaInput` dataclass | Added to same file |
| `services/alpha_data_service.py` | `BinancePublicClient` (singleton) | Import `get_binance_public_client()` |
| `services/alpha_data_service.py` | `SentimentDataService` (funding rate) | Import `get_sentiment_data_service()`, access cached funding |
| `services/combined_score_service.py` (mod) | `AlphaDataService` | Import `get_alpha_data_service()` |
| `services/dry_run_service.py` | `AlphaDataService` | Import singleton |
| `services/dry_run_service.py` | `CombinedScoreService` | Import singleton |
| `services/dry_run_service.py` | `BinanceStreamManager.current_prices` | Access dict for live price |
| `services/dry_run_service.py` | `SessionLocal` from `db/database.py` | For DB writes (pattern from `websocket_fill_handler.py`) |
| `services/alpha_backtest_service.py` | `BinancePublicClient` | Kline fetching (paginated) |
| `main.py` (mod) | 3 new route modules | `include_router()` calls |
| Frontend (mod) | `SymbolLayout.jsx` | Add Bot nav group |
| Frontend (mod) | `App.jsx` | Add 3 new Route entries |
| Frontend (mod) | `api/client.js` | Add new API functions |

### 9.2 Existing Code Modified by New Features

| Existing File | Modification | Risk Level | Reason |
|---------------|-------------|------------|--------|
| `domain/combined_score.py` | Add `AlphaInput` dataclass + optional parameter | LOW | `None` default = zero behavior change |
| `services/combined_score_service.py` | Add alpha fetch with try/except fallback | LOW | Fallback to existing 60/40 on any error |
| `services/binance_public_client.py` | Add `get_depth()` method | LOW | New method, no changes to existing ones |
| `db/models.py` | Add 2 new table classes + settings columns | LOW | Additive, no modifications to existing tables |
| `main.py` | Register 3 new routers | LOW | Additive |
| `SymbolLayout.jsx` | Add Bot nav group | LOW | Additive, existing groups unchanged |
| `App.jsx` | Add 3 new routes | LOW | Additive |
| `api/client.js` | Add new API functions | LOW | Additive |
| `CombinedScore.jsx` | Show alpha sub-signal card | LOW | Conditional rendering, only when data present |
| `symbol_registry.py` | Add XRPBTC back | MEDIUM | Needs testing that existing EUR-only code paths still work |

---

## 10. Suggested Build Order (Dependency-Driven)

Strict dependency chain: domain first (no deps) --> services (depend on domain) --> API (depends on services) --> frontend (depends on API). Each phase is independently testable.

### Pre-Phase: XRPBTC Re-Addition

**Independent of bot features. Can run in parallel with Phase 1.**

- `symbol_registry.py`: Add XRPBTC back (analysis + trading, no cross-pair pairing)
- Frontend `symbolRegistry.js`: Add XRPBTC
- Verify sync works for XRPBTC fills
- Verify existing EUR-pair tests still pass

### Phase 1: Domain Layer (Pure Logic, Fully Testable)

**Zero external dependencies. Pure Python + Decimal. Test with pytest immediately.**

1. `domain/alpha_score.py`: AlphaFactorScore, AlphaScoreResult, `compute_alpha_score()`
2. `domain/trailing_exit.py`: TrailingStopState, `init_trailing_stop()`, `update_trailing_stop()`
3. `domain/alpha_backtest.py`: Config/Trade/Metrics dataclasses, `run_alpha_backtest()`
4. `domain/combined_score.py` (mod): Add AlphaInput, modify `compute_combined_score()`
5. Tests: `test_alpha_score.py`, `test_trailing_exit.py`, `test_alpha_backtest.py`, update `test_combined_score.py`

### Phase 2: Data + Service Layer

**Depends on Phase 1 domain modules + existing singleton services.**

6. `services/binance_public_client.py` (mod): Add `get_depth()` method
7. `services/alpha_data_service.py`: Singleton, data fetching, caching
8. `services/combined_score_service.py` (mod): Integrate alpha score with fallback
9. DB migration (Alembic): Add `DryRunLogDB`, `AlphaBacktestRunDB`, settings columns
10. `services/alpha_backtest_service.py`: Orchestration + persistence
11. `services/dry_run_service.py`: Async evaluation loop + DB logging
12. Tests: Service-level tests with mocked data sources

### Phase 3: API Layer

**Depends on Phase 2 services.**

13. `api/routes/alpha.py`: Alpha score endpoints
14. `api/routes/backtest.py`: Backtest endpoints
15. `api/routes/dryrun.py`: Dry-run lifecycle + log endpoints
16. `main.py` (mod): Register new routers
17. Integration tests: Full request/response cycle

### Phase 4: Frontend

**Depends on Phase 3 API.**

18. `api/client.js` (mod): Add new API functions
19. `SymbolLayout.jsx` (mod): Add Bot nav group
20. `App.jsx` (mod): Add 3 new routes
21. `AlphaScore.jsx`: Alpha Score detail page
22. `Backtest.jsx`: Backtest results + equity curve charts
23. `DryRunLog.jsx`: Dry-run decision log + controls
24. `CombinedScore.jsx` (mod): Add alpha sub-signal card
25. CSS files for new components (Bot section accent color)

---

## 11. Anti-Patterns to Avoid

### Anti-Pattern 1: I/O in Domain Layer
**What:** Fetching data inside `domain/alpha_score.py` (e.g., importing `requests`)
**Why bad:** Breaks the foundational architecture invariant. All 6 existing domain modules are pure.
**Instead:** All data fetching in `alpha_data_service.py`; domain receives pre-fetched data as function arguments.

### Anti-Pattern 2: Duplicating Funding Rate Fetching
**What:** Creating a new OKX funding rate fetcher in `AlphaDataService`
**Why bad:** Two caches for same data, double API calls to OKX, inconsistent values between Sentiment and Alpha
**Instead:** Import `get_sentiment_data_service()`, read its cached funding rate value.

### Anti-Pattern 3: File-Based Dry-Run Logging
**What:** Writing dry-run decisions to a log file instead of DryRunLogDB
**Why bad:** Not queryable via API, not visible in frontend without custom parsing, lost on deployment, breaks "everything through SQLite" pattern
**Instead:** DB table with JSON column for factor details, standard API endpoint for reading.

### Anti-Pattern 4: Always Using 3-Signal Combined Score Weights
**What:** Using 40/30/30 weights even when alpha data service is down
**Why bad:** Degraded combined score (30% of input is zero/missing)
**Instead:** Detect alpha availability via try/except; when unavailable, fall back to existing 60/40 weights (exactly how SentimentDataService handles missing pillars via weight renormalization).

### Anti-Pattern 5: WebSocket for Orderbook Depth
**What:** Adding `{symbol}@depth20@1000ms` to `BinanceStreamManager` combined stream
**Why bad:** Always-on bandwidth for 20%-weight factor, complexity for marginal improvement over 5s REST polling
**Instead:** REST `GET /api/v3/depth` with 5s TTL cache in `AlphaDataService`.

### Anti-Pattern 6: Monolithic 2000-Line Bot Component
**What:** Single `BotDashboard.jsx` containing alpha score, backtest, and dry-run
**Why bad:** Violates component-per-page pattern established across 10+ existing components
**Instead:** Three separate pages (AlphaScore, Backtest, DryRunLog) under Bot nav group, each with its own CSS file.

### Anti-Pattern 7: Shared Backtest Engine with Orderblocks
**What:** Trying to generalize `domain/orderblock_backtest.py` to handle alpha score backtesting
**Why bad:** Fundamentally different models -- OB is zone-approach (detect zone, wait for touch), Alpha is signal-based (score every candle, enter on threshold). No meaningful shared logic.
**Instead:** Separate `domain/alpha_backtest.py`. The only shared entity is the `Candle` dataclass (imported from `domain/orderblock.py`).

### Anti-Pattern 8: Float for Alpha Scores
**What:** Using Python `float` for alpha score calculations
**Why bad:** Violates project-wide Decimal invariant (CLAUDE.md: "Decimal ueberall -- niemals float fuer Geld/Preise")
**Instead:** All scoring in `Decimal`, API transport as String, `parseFloat()` only in frontend display layer.

---

## 12. Scalability Considerations

| Concern | Current Scale | At 10x Scale | Mitigation |
|---------|--------------|-------------|------------|
| DryRunLog table growth | ~4.3K rows/day (3 symbols, 1/min) | ~43K rows/day | Index on `(user_id, symbol, created_at)`, 30-day retention |
| Alpha backtest compute | ~30-60s for 24 months | Same (CPU-bound, single request) | `asyncio.to_thread()` + timeout (pattern from combined route) |
| Depth REST calls | 1 call/5s per symbol when active | 3 calls/5s | Shared `BinancePublicClient`, TTL cache prevents duplicate calls |
| Combined Score with alpha | +1 service call per request | Same | Alpha data cached 30s, lazy evaluation |
| Frontend polling | DryRunLog: 10s polling | Same | TanStack Query staleTime, only when dry-run tab active |

---

## 13. Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Domain layer design (alpha_score, trailing, backtest) | HIGH | Follows exact patterns from 6 existing domain modules, verified against source |
| Service layer patterns (singleton, TTL cache, lock) | HIGH | Identical to 4 existing service singletons, CachedValue class reused |
| Combined Score integration | HIGH | Backward-compatible via `None` default, renormalization pattern proven |
| REST vs WebSocket for depth | HIGH | 5s staleness acceptable for 20%-weight factor at 30% of combined signal |
| DB table design | HIGH | Follows BacktestRunDB / AlertEventDB patterns exactly |
| Build order (domain -> service -> API -> frontend) | HIGH | Strict dependency chain proven across v1.0, v1.1, v2.0 delivery |
| Dry-run state management | MEDIUM | DB-based logging is correct, but position reconstruction from log entries needs careful edge case handling (e.g., process crash mid-position) |
| Alpha factor weights (40/30/20/10) | LOW | Starting point only; needs backtesting to validate. Easy to adjust (single dict). |
| Frontend component structure | MEDIUM | Component-per-page pattern is clear, but Bot as 4th nav group is new territory; visual design needs iteration |

---

## Sources

All findings based on direct codebase analysis:

- Domain patterns: `backend/app/domain/macro_signal.py` (516 lines), `domain/sentiment.py`, `domain/combined_score.py` (351 lines), `domain/orderblock.py`, `domain/orderblock_backtest.py`
- Service patterns: `services/combined_score_service.py` (158 lines), `services/macro_data_service.py`, `services/sentiment_data_service.py` (120+ lines), `services/orderblock_data_service.py`
- WebSocket architecture: `services/websocket_manager.py` (464 lines), `services/websocket_fill_handler.py` (296 lines)
- DB patterns: `db/models.py` (621 lines, 13 existing tables), `db/database.py`
- API patterns: `api/routes/combined.py` (57 lines), `api/routes/websocket.py` (107 lines)
- Frontend patterns: `App.jsx` (83 lines), `components/SymbolLayout.jsx` (83 lines), `contexts/WebSocketContext.jsx` (349 lines), `api/client.js`
- Navigation: `components/GlobalNav.jsx` (69 lines)
- Project context: `.planning/PROJECT.md` (v3.0 milestone definition, 150 lines)

---

*Generated: 2026-02-25*
