# Phase 14: Multi-Factor Scoring Engine - Research

**Researched:** 2026-02-25
**Domain:** Quantitative multi-factor scoring (Z-Score, Lead-Lag, Orderbook Imbalance, Funding Rate), regime detection (Hurst exponent), ATR trailing stops
**Confidence:** HIGH

## Summary

Phase 14 implements a real-time Alpha Score engine (-5 to +5) composed of four independent quantitative factors: Z-Score Mean Reversion on XRP/BTC ratio, Lead-Lag Momentum (BTC leading XRP), Orderbook Imbalance (from Binance depth data), and Funding Rate (from existing OKX data). The engine also includes Hurst-exponent-based regime detection that dynamically adjusts Z-Score weight, plus ATR-adaptive trailing stop levels with freeze/resume semantics for data gaps.

The existing codebase provides strong foundational patterns: the Sentiment Engine v3 demonstrates pure domain logic with weighted pillars, graceful degradation, quality badges, and Decimal precision. The Combined Score Service shows orchestration of multiple sub-services into a unified score. The Binance Public Client already has `get_order_book()` and `get_klines()` methods. The Sentiment Data Service already fetches OKX funding rates with caching. All four data sources are already accessible through existing infrastructure -- no new external dependencies or API keys are needed.

The project has no numpy dependency yet (despite STATE.md mentioning it for Phase 13). All domain computations use `Decimal` throughout. The Alpha Score engine should follow the same pattern: pure Decimal domain logic, no numpy. The R/S Hurst exponent, Z-Score, cross-correlation, and ATR computations are all implementable with pure Decimal math, consistent with the project's existing patterns for orderblock scoring and sentiment scoring.

**Primary recommendation:** Build as three layers following existing patterns: (1) pure domain module `domain/alpha_score.py` with all factor computations and Hurst exponent in Decimal, (2) data service `services/alpha_score_data_service.py` as Singleton with TTL-cache reusing existing BinancePublicClient and SentimentDataService's OKX funding cache, (3) thin API route. Settings extend existing `UserSettingsDB` with Alpha Score columns via Alembic migration.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Default candle interval: 15m (configurable: 5m/15m/1h in Settings)
- Z-Score and Lead-Lag refresh on candle close (15m cadence)
- Orderbook Imbalance and Funding Rate refresh independently between candle closes (more responsive)
- Mixed refresh model: candle-driven factors are synchronized, real-time factors update independently
- Regime detection via Hurst exponent using Rescaled Range (R/S) Analysis
- Lookback window: 100-200 candles (15m)
- Thresholds: H > 0.55 = trending (reduce Z-Score weight progressively), H < 0.45 = mean-reverting (Z-Score gets full 40% weight), 0.45-0.55 = transitional (gradual blend)
- Freed weight redistribution: Lead-Lag 60%, Imbalance 30%, Funding 10% of freed Z-Score weight
- Regime indicator visible in API response (label + Hurst value + confidence)
- Grouped Settings layout: essential visible, advanced collapsed
- Essential: factor weights (4), trade threshold (+-3.0), candle interval (5m/15m/1h)
- Advanced: rolling windows, ATR multipliers, Hurst lookback, regime thresholds, trailing stop resume threshold
- Trailing stop: hybrid ratchet + ATR floor, per-symbol multipliers (ATR*2 BTC, ATR*3 XRP)
- Portfolio-aware trailing stops: combined BTC + XRP exposure for stop tightening
- Freeze during data gaps, resume after N consecutive fresh data points (configurable, default 5)
- Frozen state in API: `frozen: true`, `frozen_since: timestamp`, `data_points_needed: N`

### Claude's Discretion
- Orderbook Imbalance data source approach (snapshot frequency vs rolling average)
- Weight input UX (enforce sum-to-100% vs auto-normalize)
- Internal caching strategy for factor computations
- API endpoint structure and response shape
- Exact Hurst exponent implementation details within R/S framework

### Deferred Ideas (OUT OF SCOPE)
- Backtesting with performance curves -- Phase 15
- Tax simulation (26.375% Abgeltungssteuer + Soli) -- deferred to live execution milestone
- Conviction-weighted position sizing based on Alpha Score intensity -- future milestone (ADV-01)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCORE-01 | Z-Score Mean Reversion on XRP/BTC ratio with configurable rolling window (default 60) | Pure domain function: fetch XRPBTC klines, compute rolling mean/std, Z-Score = (price - mean) / std, map to -5..+5 sub-score. Use BinancePublicClient.get_klines("XRPBTC", interval). |
| SCORE-02 | Lead-Lag Momentum: BTC movements XRP has not yet followed (cross-correlation) | Pure domain function: rolling cross-correlation of BTCEUR and XRPBTC returns at lags 1..N candles. Detect max correlation lag. Signal = BTC moved but XRP lagged. |
| SCORE-03 | Orderbook Imbalance from Binance depth data (bid/ask within 1% of mid-price) | Reuse BinancePublicClient.get_order_book(). Existing SentimentDataService uses 5% band; Alpha Score needs 1% per SCORE-03 spec. New dedicated imbalance fetch with narrower band. |
| SCORE-04 | Funding Rate from existing OKX data (reuse SentimentDataService cache) | Reuse SentimentDataService._get_funding_rate() cache for BTC-USDT-SWAP and XRP-USDT-SWAP. Both instruments confirmed available on OKX. |
| SCORE-05 | Global Alpha Score (-5 to +5) as weighted sum (Z 40%, LL 30%, OB 20%, FR 10%) | Pure domain aggregation function with configurable weights, regime-adjusted via Hurst. Clamp to [-5, +5]. |
| SCORE-06 | User configures Alpha Score weights and trade threshold via Settings | Extend UserSettingsDB with alpha_score columns. Extend Settings API route + frontend. |
| SCORE-07 | Graceful degradation with quality indicator for missing data sources | Follow SentimentDataService pattern: unavailable factors get neutral sub-score, quality badges track each factor, renormalize weights. |
| SCORE-08 | Warmup status during cold start (MIN_WINDOW_SIZE guard) | Return `{"status": "warmup", "candles_available": N, "candles_needed": M}` when insufficient history. Prevent extreme values. |
| SCORE-09 | Regime detection (trending vs mean-reverting) adjusts Z-Score weight | Hurst exponent via R/S analysis. Gradual weight blend: H>0.55 reduces Z-Score progressively, freed weight to LL/OB/FR per locked ratios. |
| EXIT-01 | ATR-adaptive trailing stop distances (ATR*2 BTC, ATR*3 XRP, configurable) | Reuse existing compute_atr() from orderblock/scoring.py (Wilder's Smoothing). Apply per-symbol multiplier. Ratchet logic: only moves in favorable direction. |
| EXIT-02 | Trailing stops freeze during data gaps, resume after N fresh data points | Track last_data_timestamp per symbol. Freeze = hold last value when data age > threshold. Resume counter tracks consecutive fresh data points. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python Decimal | stdlib | All price/score computations | Project invariant: never float for money/scores |
| FastAPI | 0.128.7 | API endpoint | Existing stack |
| SQLAlchemy 2 | 2.0.46 | Settings persistence | Existing stack |
| Alembic | 1.18.4 | Schema migration | Existing stack, render_as_batch=True for SQLite |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| BinancePublicClient | existing | Klines + Depth data | All market data fetching |
| SentimentDataService | existing | OKX Funding Rate cache | Reuse for SCORE-04 |
| CachedValue | existing | TTL-based caching | All data service caching |
| threading.Lock | stdlib | Thread-safe singleton | Data service state protection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pure Decimal R/S Hurst | `nolds` library (0.6.3) | nolds requires numpy, adds dependency; R/S is ~30 lines of Decimal code. Project prefers no numpy. |
| Pure Decimal Z-Score | `scipy.stats.zscore` | scipy is massive; Z-Score is trivial: `(x - mean) / std`. Not justified. |
| Custom cross-correlation | `numpy.correlate` | numpy dependency not present; Decimal cross-correlation is ~20 lines. |

**Installation:**
```bash
# No new dependencies needed. All computations use stdlib Decimal + existing infrastructure.
```

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── domain/
│   └── alpha_score.py           # Pure domain: all 4 factor computations, Hurst R/S,
│                                 # regime detection, weight adjustment, Alpha Score
│                                 # aggregation, trailing stop logic, dataclasses
├── services/
│   └── alpha_score_data_service.py  # Singleton data service: kline fetching, depth
│                                     # fetching, caching, orchestration, serialization
├── api/routes/
│   └── alpha_score.py           # GET /api/alpha-score/{user_id}/score
│                                 # GET /api/alpha-score/{user_id}/trailing-stops
├── db/models.py                 # UserSettingsDB extended with alpha_score_* columns
├── api/routes/settings.py       # Extended with alpha score settings fields
└── tests/
    ├── test_alpha_score.py      # Domain logic: Z-Score, Lead-Lag, Hurst, aggregation
    └── test_alpha_score_service.py  # Service: caching, degradation, warmup
```

### Pattern 1: Pure Domain Module (following sentiment.py)
**What:** All scoring computations as pure functions with Decimal I/O, no external dependencies
**When to use:** Every factor computation, aggregation, regime detection
**Example:**
```python
# Source: Existing pattern from domain/sentiment.py
@dataclass
class AlphaFactorScore:
    name: str
    sub_score: Decimal          # -5 to +5 per factor
    raw_value: Optional[Decimal]
    weight: Decimal             # Current weight (may be regime-adjusted)
    base_weight: Decimal        # User-configured weight before regime adjustment
    quality: str                # "live" | "cached" | "stale" | "unavailable" | "warmup"
    description: str = ""

@dataclass
class AlphaScoreResult:
    score: Decimal              # -5 to +5
    factors: List[AlphaFactorScore]
    regime: RegimeInfo
    quality: str                # "full" | "partial" | "degraded" | "warmup"
    active_factors: int
    total_factors: int
    trade_signal: str           # "LONG" | "SHORT" | "NEUTRAL"
    threshold: Decimal
    timestamp: datetime
```

### Pattern 2: Singleton Data Service with TTL Cache (following sentiment_data_service.py)
**What:** Thread-safe singleton with in-memory TTL cache, mixed refresh cadences
**When to use:** The AlphaScoreDataService orchestrating data fetch + domain computation
**Example:**
```python
# Source: Existing pattern from services/sentiment_data_service.py
class AlphaScoreDataService:
    def __init__(self):
        self._cache: dict[str, CachedValue] = {}
        self._lock = threading.Lock()
        # Rolling kline histories per symbol+interval
        self._kline_history: dict[str, deque] = {}
        self._warmup_status: dict[str, bool] = {}

    def get_alpha_score(self, settings: dict) -> dict:
        # 1. Fetch candle-driven data (Z-Score, Lead-Lag) — cached per interval
        # 2. Fetch real-time data (Orderbook, Funding) — shorter TTL
        # 3. Check warmup status
        # 4. Call pure domain functions
        # 5. Serialize result
        ...
```

### Pattern 3: Settings Extension (following existing UserSettingsDB)
**What:** Add alpha_score_* columns to UserSettingsDB, extend Settings API with validation
**When to use:** All configurable parameters
**Example:**
```python
# New columns on UserSettingsDB (via Alembic migration)
alpha_score_interval = Column(String, nullable=True)           # "5m" | "15m" | "1h"
alpha_score_weight_zscore = Column(Numeric(5,2), nullable=True)   # Default 40
alpha_score_weight_leadlag = Column(Numeric(5,2), nullable=True)  # Default 30
alpha_score_weight_imbalance = Column(Numeric(5,2), nullable=True) # Default 20
alpha_score_weight_funding = Column(Numeric(5,2), nullable=True)  # Default 10
alpha_score_threshold = Column(Numeric(5,2), nullable=True)       # Default 3.0
alpha_score_zscore_window = Column(Numeric(5,0), nullable=True)   # Default 60
alpha_score_leadlag_window = Column(Numeric(5,0), nullable=True)  # Default 30
alpha_score_hurst_lookback = Column(Numeric(5,0), nullable=True)  # Default 100
alpha_score_hurst_trending = Column(Numeric(5,4), nullable=True)  # Default 0.55
alpha_score_hurst_reverting = Column(Numeric(5,4), nullable=True) # Default 0.45
alpha_score_atr_mult_btc = Column(Numeric(5,2), nullable=True)   # Default 2.0
alpha_score_atr_mult_xrp = Column(Numeric(5,2), nullable=True)   # Default 3.0
alpha_score_stop_resume_n = Column(Numeric(3,0), nullable=True)   # Default 5
```

### Pattern 4: API Route with asyncio.to_thread (following combined.py)
**What:** Async route delegating to synchronous service via asyncio.to_thread
**When to use:** The alpha score API endpoint
**Example:**
```python
# Source: Existing pattern from api/routes/combined.py
@router.get("/{user_id}/score")
async def get_alpha_score(user_id: str, ...):
    service = get_alpha_score_data_service()
    return await asyncio.wait_for(
        asyncio.to_thread(service.get_alpha_score, settings=...), timeout=30
    )
```

### Anti-Patterns to Avoid
- **Using numpy for simple computations:** The project has no numpy dependency. Z-Score, cross-correlation, and Hurst R/S are all straightforward in Decimal. Do not add numpy.
- **Sharing cache between Alpha Score and Sentiment Engine:** Each service owns its cache. Alpha Score should not reach into SentimentDataService internals. For Funding Rate reuse, call the public method or reuse the same OKX fetch pattern independently with its own cache key.
- **Binary regime switching:** CONTEXT.md explicitly specifies gradual weight blend, not a binary switch. The weight transition must be smooth across the 0.45-0.55 Hurst range.
- **Returning extreme scores during warmup:** SCORE-08 requires explicit warmup status. Never compute a partial score from 3 candles and present it as valid.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Kline fetching | Custom HTTP client | BinancePublicClient.get_klines() | Handles retry, timeout, rate limits |
| Orderbook fetching | Custom HTTP client | BinancePublicClient.get_order_book() | Same retry/timeout infrastructure |
| Funding Rate | New OKX client | Reuse pattern from SentimentDataService._get_funding_rate() | Same endpoint, same cache pattern |
| ATR computation | New ATR function | Extract/reuse compute_atr() from orderblock/scoring.py | Wilder's Smoothing already tested |
| TTL caching | Custom cache | CachedValue from binance_public_client.py | Already used in 3+ services |
| Settings persistence | Custom table | Extend existing UserSettingsDB | Single settings table, consistent UX |
| Input validation | Custom validators | Follow Settings route Decimal validation pattern | Consistent error handling |

**Key insight:** Every data source and caching pattern needed already exists in the codebase. The Alpha Score engine is a new domain computation layer that orchestrates existing infrastructure with new pure math.

## Common Pitfalls

### Pitfall 1: Float Contamination in Z-Score / Hurst Computation
**What goes wrong:** Using `float` for standard deviation or mean in Z-Score produces IEEE 754 rounding errors that compound across the 60-period rolling window
**Why it happens:** `math.sqrt()` returns float; division can silently convert to float
**How to avoid:** Use `Decimal.sqrt()` for all square root operations. All intermediate values must be Decimal. Follow the exact pattern in `compute_pillar_dispersion()` which uses `variance.sqrt()`.
**Warning signs:** Test assertions fail on the 4th decimal place; scores differ between runs

### Pitfall 2: Hurst Exponent Edge Cases
**What goes wrong:** R/S analysis returns NaN or extreme values with insufficient data or constant series
**Why it happens:** R/S computation involves log-log regression; with fewer than ~20 data points, the regression is meaningless. A constant series has std=0, causing division by zero in R/S.
**How to avoid:** Guard: minimum 20 sub-windows for R/S. Return H=0.5 (random walk) as default when data is insufficient. Catch std=0 case explicitly.
**Warning signs:** H values outside [0, 1] or wildly fluctuating between calls

### Pitfall 3: XRPBTC Kline Alignment with BTCEUR for Lead-Lag
**What goes wrong:** XRPBTC and BTCEUR candles may have slightly different open times, causing misaligned cross-correlation
**Why it happens:** Binance klines align to UTC intervals, but low-liquidity pairs may have gaps
**How to avoid:** Align by candle open timestamp. Fill gaps with last known value (forward-fill). Cross-correlation should operate on aligned time series of equal length.
**Warning signs:** Lead-Lag factor returns wildly different values between calls; NaN from misaligned arrays

### Pitfall 4: Orderbook Imbalance Volatility
**What goes wrong:** Raw orderbook snapshots are extremely noisy; a single large order appearing/disappearing causes score to swing
**Why it happens:** Orderbook is a point-in-time snapshot, not a time-averaged metric
**How to avoid:** Use rolling average of N recent snapshots (e.g., 3-5 snapshots with 1min TTL each = ~3-5min average). This is Claude's discretion area. Recommend exponential moving average of last 5 snapshots.
**Warning signs:** Orderbook Imbalance sub-score oscillates between -5 and +5 within seconds

### Pitfall 5: Weight Normalization After Regime Adjustment
**What goes wrong:** After Hurst regime reduces Z-Score weight and redistributes to other factors, the weights no longer sum to 100%
**Why it happens:** Redistribution formula applies freed weight incorrectly, or rounding errors accumulate
**How to avoid:** Explicit normalization step: after redistribution, assert `sum(weights) == 1.0` (within Decimal tolerance). Compute freed_weight = base_zscore_weight - adjusted_zscore_weight, then distribute according to locked ratios (60/30/10).
**Warning signs:** Alpha Score exceeds [-5, +5] range; total weight sum deviates from 1.0

### Pitfall 6: Trailing Stop Ratchet Concurrency
**What goes wrong:** Two concurrent requests both compute a new trailing stop; one overwrites the other's ratchet
**Why it happens:** Trailing stop state is mutable (must only move in favorable direction). Without locking, concurrent computations can move it backward.
**How to avoid:** Trailing stop state lives in the data service under threading.Lock. Each update is: lock -> read current -> compute new -> max(current, new) for longs / min(current, new) for shorts -> write -> unlock.
**Warning signs:** Stop level jumps backward temporarily

### Pitfall 7: Settings Migration Bloat
**What goes wrong:** Adding 15+ columns to UserSettingsDB makes the migration unwieldy and the Settings API overly complex
**Why it happens:** Each Alpha Score parameter as a separate column
**How to avoid:** Group Alpha Score settings as a JSON column (`alpha_score_config JSON`) with typed deserialization, OR use individual columns but with a clear naming convention (`alpha_*`). Recommendation: individual columns for type safety and Alembic compatibility, consistent with existing `ob_*` columns.
**Warning signs:** Settings serialization becomes error-prone; frontend form state management is painful

## Code Examples

### Z-Score Mean Reversion on XRP/BTC Ratio
```python
# Pattern: Pure domain function, Decimal throughout
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class ZScoreResult:
    zscore: Decimal           # Raw Z-Score value
    sub_score: Decimal        # Mapped to -5..+5
    mean: Decimal
    std: Decimal
    current_ratio: Decimal
    window_size: int
    quality: str

def compute_zscore_mean_reversion(
    prices: List[Decimal],     # XRPBTC close prices, newest last
    window: int = 60,
) -> ZScoreResult:
    """
    Z-Score of current XRP/BTC ratio vs rolling window.

    Negative Z-Score (ratio below mean) = XRP undervalued vs BTC = BUY signal (+score)
    Positive Z-Score (ratio above mean) = XRP overvalued vs BTC = SELL signal (-score)
    """
    if len(prices) < window:
        return ZScoreResult(
            zscore=Decimal("0"), sub_score=Decimal("0"),
            mean=Decimal("0"), std=Decimal("0"),
            current_ratio=prices[-1] if prices else Decimal("0"),
            window_size=len(prices), quality="warmup"
        )

    window_prices = prices[-window:]
    n = Decimal(str(window))
    mean = sum(window_prices) / n
    variance = sum((p - mean) ** 2 for p in window_prices) / n
    std = variance.sqrt() if variance > 0 else Decimal("0")

    if std == 0:
        return ZScoreResult(
            zscore=Decimal("0"), sub_score=Decimal("0"),
            mean=mean, std=std, current_ratio=prices[-1],
            window_size=window, quality="live"
        )

    zscore = (prices[-1] - mean) / std

    # Map Z-Score to -5..+5 sub-score
    # Z = -3 -> +5 (strongly mean-reverting buy)
    # Z = 0 -> 0 (at mean)
    # Z = +3 -> -5 (strongly mean-reverting sell)
    sub_score = (-zscore * Decimal("5") / Decimal("3")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    sub_score = max(Decimal("-5"), min(Decimal("5"), sub_score))

    return ZScoreResult(
        zscore=zscore.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        sub_score=sub_score,
        mean=mean, std=std, current_ratio=prices[-1],
        window_size=window, quality="live"
    )
```

### Hurst Exponent via R/S Analysis
```python
# Pattern: Pure Decimal implementation of Rescaled Range analysis
import math
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

@dataclass
class HurstResult:
    hurst: Decimal              # 0..1; 0.5 = random walk
    regime: str                 # "trending" | "mean_reverting" | "transitional"
    confidence: Decimal         # 0..1 based on R-squared of log-log fit
    data_points: int

def compute_hurst_rs(
    prices: List[Decimal],
    min_window: int = 10,
) -> HurstResult:
    """
    Hurst exponent via Rescaled Range (R/S) Analysis.

    1. Compute log returns
    2. For multiple sub-window sizes, compute R/S statistic
    3. Regress log(R/S) on log(n) -- slope = H
    """
    n = len(prices)
    if n < min_window * 2:
        return HurstResult(
            hurst=Decimal("0.5"), regime="transitional",
            confidence=Decimal("0"), data_points=n
        )

    # Log returns (using Decimal ln approximation or ratio-based)
    returns = []
    for i in range(1, n):
        if prices[i - 1] > 0:
            returns.append(prices[i] / prices[i - 1] - Decimal("1"))

    if len(returns) < min_window:
        return HurstResult(
            hurst=Decimal("0.5"), regime="transitional",
            confidence=Decimal("0"), data_points=len(returns)
        )

    # Window sizes: powers of 2 up to len(returns)/2
    window_sizes = []
    size = min_window
    while size <= len(returns) // 2:
        window_sizes.append(size)
        size *= 2

    if len(window_sizes) < 2:
        return HurstResult(
            hurst=Decimal("0.5"), regime="transitional",
            confidence=Decimal("0"), data_points=len(returns)
        )

    log_ns = []
    log_rs_values = []

    for ws in window_sizes:
        rs_list = []
        num_windows = len(returns) // ws
        for j in range(num_windows):
            segment = returns[j * ws : (j + 1) * ws]
            seg_mean = sum(segment) / Decimal(str(ws))

            # Cumulative deviation from mean
            cumdev = []
            running = Decimal("0")
            for val in segment:
                running += val - seg_mean
                cumdev.append(running)

            R = max(cumdev) - min(cumdev)

            # Standard deviation
            var = sum((v - seg_mean) ** 2 for v in segment) / Decimal(str(ws))
            S = var.sqrt() if var > 0 else Decimal("0")

            if S > 0:
                rs_list.append(R / S)

        if rs_list:
            avg_rs = sum(rs_list) / Decimal(str(len(rs_list)))
            if avg_rs > 0:
                log_ns.append(Decimal(str(math.log(float(ws)))))
                log_rs_values.append(Decimal(str(math.log(float(avg_rs)))))

    if len(log_ns) < 2:
        return HurstResult(
            hurst=Decimal("0.5"), regime="transitional",
            confidence=Decimal("0"), data_points=len(returns)
        )

    # Simple linear regression: slope of log(R/S) vs log(n)
    hurst, r_squared = _decimal_linear_regression(log_ns, log_rs_values)
    hurst = max(Decimal("0"), min(Decimal("1"), hurst))

    # Classify regime
    if hurst > Decimal("0.55"):
        regime = "trending"
    elif hurst < Decimal("0.45"):
        regime = "mean_reverting"
    else:
        regime = "transitional"

    return HurstResult(
        hurst=hurst.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        regime=regime,
        confidence=max(Decimal("0"), min(Decimal("1"), r_squared)).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        ),
        data_points=len(returns),
    )
```

### ATR Trailing Stop with Freeze/Resume
```python
# Pattern: Stateful trailing stop with freeze semantics
@dataclass
class TrailingStopState:
    symbol: str
    stop_level: Optional[Decimal]   # Current stop price
    atr_value: Optional[Decimal]    # Latest ATR
    atr_distance: Optional[Decimal] # ATR * multiplier
    direction: str                  # "long" | "short"
    frozen: bool
    frozen_since: Optional[datetime]
    fresh_data_count: int           # Consecutive fresh data points since unfreeze attempt
    resume_threshold: int           # N needed to resume
    last_price: Optional[Decimal]
    last_updated: Optional[datetime]

def update_trailing_stop(
    state: TrailingStopState,
    current_price: Decimal,
    current_atr: Decimal,
    multiplier: Decimal,
    data_is_fresh: bool,
    now: datetime,
) -> TrailingStopState:
    """
    Ratchet logic: stop only moves in favorable direction.
    ATR floor: never closer than ATR * multiplier.
    Freeze: holds last value during data gaps.
    Resume: after N consecutive fresh data points.
    """
    # Handle freeze/resume
    if not data_is_fresh:
        if not state.frozen:
            return TrailingStopState(
                **{**state.__dict__,
                   "frozen": True,
                   "frozen_since": now,
                   "fresh_data_count": 0}
            )
        return state  # Stay frozen

    # Data is fresh
    if state.frozen:
        new_count = state.fresh_data_count + 1
        if new_count < state.resume_threshold:
            return TrailingStopState(
                **{**state.__dict__,
                   "fresh_data_count": new_count}
            )
        # Resume: unfreeze
        state = TrailingStopState(
            **{**state.__dict__,
               "frozen": False,
               "frozen_since": None,
               "fresh_data_count": 0}
        )

    atr_distance = current_atr * multiplier

    if state.direction == "long":
        new_stop = current_price - atr_distance
        # Ratchet: never lower than current stop
        if state.stop_level is not None:
            new_stop = max(new_stop, state.stop_level)
    else:  # short
        new_stop = current_price + atr_distance
        if state.stop_level is not None:
            new_stop = min(new_stop, state.stop_level)

    return TrailingStopState(
        symbol=state.symbol,
        stop_level=new_stop,
        atr_value=current_atr,
        atr_distance=atr_distance,
        direction=state.direction,
        frozen=False,
        frozen_since=None,
        fresh_data_count=0,
        resume_threshold=state.resume_threshold,
        last_price=current_price,
        last_updated=now,
    )
```

### Regime-Adjusted Weight Redistribution
```python
def compute_regime_adjusted_weights(
    base_weights: dict,          # {"zscore": 0.40, "leadlag": 0.30, "imbalance": 0.20, "funding": 0.10}
    hurst: Decimal,
    trending_threshold: Decimal = Decimal("0.55"),
    reverting_threshold: Decimal = Decimal("0.45"),
) -> dict:
    """
    Gradual weight blend based on Hurst exponent.

    H < 0.45: Z-Score gets full base weight (mean-reverting regime)
    H > 0.55: Z-Score weight reduced to 0; freed weight redistributed
    0.45-0.55: Linear interpolation (transitional)

    Freed weight distribution (locked): Lead-Lag 60%, Imbalance 30%, Funding 10%
    """
    zscore_base = Decimal(str(base_weights["zscore"]))

    if hurst <= reverting_threshold:
        # Full mean-reversion: Z-Score at full weight
        return {k: Decimal(str(v)) for k, v in base_weights.items()}

    if hurst >= trending_threshold:
        # Full trend: Z-Score reduced to 0
        reduction_pct = Decimal("1")
    else:
        # Transitional: linear blend
        reduction_pct = (hurst - reverting_threshold) / (trending_threshold - reverting_threshold)

    freed_weight = zscore_base * reduction_pct

    adjusted = {
        "zscore": zscore_base - freed_weight,
        "leadlag": Decimal(str(base_weights["leadlag"])) + freed_weight * Decimal("0.6"),
        "imbalance": Decimal(str(base_weights["imbalance"])) + freed_weight * Decimal("0.3"),
        "funding": Decimal(str(base_weights["funding"])) + freed_weight * Decimal("0.1"),
    }

    # Sanity: ensure sum = 1.0
    total = sum(adjusted.values())
    if total != Decimal("1"):
        # Normalize (handles Decimal rounding)
        adjusted = {k: v / total for k, v in adjusted.items()}

    return adjusted
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Binary regime switch | Gradual Hurst-based weight blend | User decision | Avoids sudden portfolio whipsaws at regime boundary |
| numpy-based R/S | Pure Decimal R/S | Project pattern | Consistent with project's no-numpy, all-Decimal philosophy |
| Single orderbook snapshot | EMA of N snapshots | Best practice | Reduces noise in highly volatile orderbook data |
| Separate trailing stop table | In-memory state in data service | Architectural choice | Trailing stops are ephemeral; no need for DB persistence until live execution |

**Deprecated/outdated:**
- `hurst` PyPI package (0.0.5, 2019): Unmaintained, requires numpy. Do not use.
- `nolds` library: Well-maintained (0.6.3, Nov 2025) but requires numpy. Not justified for one function.

## Open Questions

1. **Orderbook Imbalance: Snapshot vs Rolling Average (Claude's Discretion)**
   - What we know: Raw snapshots are noisy (per Pitfall 4). SentimentDataService uses 5% band with 1min TTL single snapshot.
   - What's unclear: How many snapshots to average, whether to use simple average or EMA
   - Recommendation: EMA of last 5 snapshots (alpha=0.4), 30-second fetch interval. This gives ~2.5min effective averaging, responsive enough for 15m candle cadence but smooth enough to avoid noise. Store last 5 snapshots in a deque within the data service.

2. **Weight Input UX: Enforce Sum vs Auto-Normalize (Claude's Discretion)**
   - What we know: 4 weights must sum to 100% conceptually. Users may enter arbitrary values.
   - What's unclear: Whether strict enforcement or auto-normalization is better UX
   - Recommendation: Auto-normalize on save. Display normalized percentages. Show a note: "Weights are automatically normalized to sum to 100%." This prevents frustrating validation errors while maintaining mathematical correctness. Store raw values in DB, normalize at computation time.

3. **ATR Source for Trailing Stops**
   - What we know: ATR needs klines. Same BinancePublicClient.get_klines() used elsewhere.
   - What's unclear: Which interval to use for ATR computation (same as alpha_score_interval, or always a longer timeframe?)
   - Recommendation: Use alpha_score_interval for consistency. ATR(14) on the configured interval (default 15m). This means ATR is computed from the same klines already fetched for Z-Score/Lead-Lag, avoiding extra API calls.

4. **Portfolio-Aware Stop Tightening**
   - What we know: CONTEXT.md specifies "combined BTC + XRP exposure considered for stop tightening when both positions are correlated"
   - What's unclear: Exact tightening formula
   - Recommendation: Compute rolling correlation between BTC and XRP returns (same window as Lead-Lag). When correlation > 0.7, multiply ATR distance by `1 - (correlation - 0.7) * 0.5` (max 15% tightening at correlation 1.0). This is a simple, transparent formula.

5. **Lead-Lag Cross-Correlation Implementation**
   - What we know: Need to detect BTC price movements that XRP has not yet followed
   - What's unclear: Exact lag range, return computation period
   - Recommendation: Compute returns over configurable window (default 30 candles). Cross-correlate BTCEUR returns with XRPBTC returns at lags 1..10. Signal = max correlation lag and magnitude. If BTC moved strongly (recent BTC return > 1 std dev) and XRP hasn't followed (lag > 0, correlation > 0.5), sub-score is positive (buy XRP). This captures the "BTC leads, XRP follows" pattern.

## Binance API Rate Impact Analysis

| Endpoint | Call Frequency | Weight | Notes |
|----------|---------------|--------|-------|
| GET /api/v3/klines (XRPBTC, 15m) | Every 15m (candle close) | 2 | 200 candles for Z-Score+Hurst |
| GET /api/v3/klines (BTCEUR, 15m) | Every 15m (candle close) | 2 | 200 candles for Lead-Lag |
| GET /api/v3/depth (XRPBTC) | Every 30s | 5 | limit=100 (1% band = ~100 levels sufficient) |
| OKX funding-rate | Every 15m (reuse cache) | N/A | External API, separate rate limit |

**Total Binance weight per 15m cycle:** ~4 (klines) + ~50 (10 depth snapshots at 5 weight each) = ~54 weight per 15 minutes. Well within Binance's 6000 weight/minute limit (API rate limit for IP-based requests).

## Sources

### Primary (HIGH confidence)
- Existing codebase: `domain/sentiment.py`, `services/sentiment_data_service.py`, `services/combined_score_service.py` -- patterns for pure domain scoring, graceful degradation, TTL cache, singleton services
- Existing codebase: `services/binance_public_client.py` -- `get_klines()`, `get_order_book()`, `CachedValue`
- Existing codebase: `domain/orderblock/scoring.py` -- `compute_atr()` with Wilder's Smoothing
- Existing codebase: `db/models.py`, `api/routes/settings.py` -- Settings extension pattern
- Existing codebase: `symbol_registry.py` -- XRPBTC confirmed in KNOWN_PAIRS
- [Binance Spot API Docs - Market Data Endpoints](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints) -- Depth endpoint weight: 5 for limit<=100

### Secondary (MEDIUM confidence)
- [OKX Funding Rate Chart - XRP-USDT-SWAP](https://coinalyze.net/ripple/usdt/okx/funding-rate-chart/xrpusdt_perp_fr/) -- XRP-USDT-SWAP instrument exists on OKX
- [GitHub - Mottl/hurst](https://github.com/Mottl/hurst) -- R/S algorithm reference
- [nolds 0.6.3 on PyPI](https://pypi.org/project/nolds/) -- Alternative Hurst implementation (not recommended due to numpy dep)
- [ATR Trailing Stop Ratchet](https://c.mql5.com/forextsd/forum/161/exit_strategy_atr_ratchet1.doc) -- Original ATR Ratchet concept by Chuck LeBeau
- [Wikipedia - Rescaled Range](https://en.wikipedia.org/wiki/Rescaled_range) -- R/S analysis mathematical foundation

### Tertiary (LOW confidence)
- [Finding Optimal Lag Between Financial Assets Time Series](https://sandrasullivan.tech/2023/09/26/finding-optimal-lag-between-financial-assets-time-series/) -- Lead-lag cross-correlation methodology (single blog post, needs validation)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing infrastructure reused
- Architecture: HIGH - follows established codebase patterns exactly (sentiment v3, combined score, orderblock)
- Factor computations (Z-Score, Lead-Lag, Funding): HIGH - straightforward math, well-understood algorithms
- Hurst R/S implementation: MEDIUM - algorithm is well-documented but edge cases (short series, constant returns) need careful testing
- Trailing stop freeze/resume: MEDIUM - novel state machine, no existing codebase pattern to follow exactly
- Pitfalls: HIGH - identified from experience with existing sentiment/orderblock engines

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable domain, no fast-moving dependencies)
