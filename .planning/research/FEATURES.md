# Feature Research: Multi-Factor Omni-Bot (v3.0)

**Domain:** Multi-factor crypto trading bot with backtesting and dry-run mode
**Researched:** 2026-02-25
**Confidence:** MEDIUM (based on established quantitative finance methods, crypto market microstructure research, and thorough codebase analysis -- web search unavailable for latest library versions)

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any multi-factor crypto trading system must have. Missing these = the bot is untrustworthy or useless.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Multi-factor score with configurable weights** | Single-factor bots are fragile. Every serious quant system combines signals to reduce false positives. Users expect to tune factor weights. | MEDIUM | 4 factors: Z-Score (40%), Lead-Lag (30%), Orderbook Imbalance (20%), Funding Rate (10%). Pure domain logic, Decimal precision. |
| **Z-Score Mean Reversion on XRP/BTC ratio** | The core thesis of the bot. Pair/ratio mean reversion is one of the most studied and validated strategies in quantitative finance. Without this, there is no bot. | HIGH | Requires XRPBTC re-addition to Symbol Registry, rolling window (60-period default), adaptive Z-Score thresholds. See "Z-Score Behavior" section below. |
| **Backtesting with historical data** | No trader trusts a system without historical validation. "Show me the backtest" is the first question anyone asks. Minimum viable: Sharpe ratio + max drawdown. | HIGH | 24-month Binance klines, benchmark vs HODL, transaction cost modeling. Existing orderblock backtest engine provides pattern but is structurally different (zone-based vs signal-based). New engine needed. |
| **Dry-run mode (paper trading)** | Mandatory bridge between backtest and live. Users must see real-time signal behavior before risking capital. Every serious bot framework (Freqtrade, Hummingbot, CCXT-based) has this. | MEDIUM | Real signals computed, decisions logged with timestamps, virtual portfolio tracked, no actual Binance order calls. |
| **Decision logging with full context** | Auditability is a core project principle (ledger-first). Every signal computation and threshold crossing must be recorded with all input values. | MEDIUM | Append-only decision log: timestamp, all factor scores, alpha score, threshold evaluation, action taken (or skipped), reason. |
| **ATR-based position exit management** | Fixed stop-losses fail in volatile crypto markets. ATR-adaptive stops are the standard approach for dynamic risk management across all asset classes. | MEDIUM | Reuse existing `compute_atr()` from orderblock scoring module. BTC: ATR x 2 trailing, XRP: ATR x 3 trailing (higher multiplier due to higher volatility). |
| **Combined Score integration** | The app already has a Combined Score (MacroSignal 60% + Sentiment 40%). A new Alpha Score must feed into this system, not exist as a disconnected silo. | MEDIUM | Alpha Score as additional signal source in Combined Score. Requires extending `CombinedScoreResult` and the orchestration in `CombinedScoreService`. |
| **Bot status dashboard** | Users need at-a-glance view of: is the bot running, what mode (dry-run/live), current alpha score, recent signals, open virtual positions. | MEDIUM | New 4th nav section "Bot". Dashboard page with status card, signal history, and virtual P&L (dry-run mode). |
| **Configurable thresholds** | Alpha Score threshold (+/-3.0 from -5 to +5 range) must be adjustable via Settings. Different users have different risk appetites. | LOW | Extend existing `UserSettingsDB` with `alpha_threshold`, `alpha_weights_json`, trailing stop multipliers. Pattern already established for orderblock settings. |
| **Graceful degradation when data sources fail** | Binance API may be temporarily unavailable for some endpoints. The system must compute partial scores with available data, not crash entirely. | LOW | Existing pattern in SentimentDataService: quality badges ("live"/"cached"/"stale"/"unavailable"), renormalization when pillars missing. Apply same pattern to Alpha Score factors. |

### Differentiators (Competitive Advantage)

Features that elevate this beyond a basic multi-factor scorer.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Lead-Lag Momentum detection (BTC leads XRP)** | Most retail bots treat assets independently. Detecting that BTC moves first and XRP follows (typically 5-30 minute lag) provides a genuine edge that manual traders struggle to exploit consistently. | HIGH | Cross-correlation analysis over rolling window. Binance klines for both BTCEUR and XRPEUR. Lag detection at 1m/5m/15m granularity. Must handle regime changes where correlation breaks down. |
| **Real-time Orderbook Imbalance from depth20 WebSocket** | Existing Sentiment Orderbook Imbalance uses REST API (1000-level depth, 1min cache TTL). A WebSocket depth20 stream provides sub-second updates for much faster signal response. This is a significant upgrade over polling. | MEDIUM | Subscribe to `xrpeur@depth20@100ms` and `btceur@depth20@100ms` streams via existing BinanceStreamManager. Compute bid/ask imbalance in real-time. |
| **Tax simulation in backtesting** | German crypto tax: gains tax-free after 1-year holding period (365 days). A backtest that ignores this is misleading -- it overstates returns. No retail bot I know of includes jurisdiction-specific tax modeling. | MEDIUM | Per-trade holding period check in backtest engine. Configurable tax rate (default 26.375% Abgeltungssteuer + Soli). Mark trades as tax-free/taxable. Show post-tax Sharpe alongside pre-tax. |
| **Conviction-weighted position sizing** | Instead of binary buy/sell, the Alpha Score intensity (-5 to +5) modulates position size. Score of +3.5 = minimum position, score of +5.0 = maximum position. More nuanced than threshold-only systems. | LOW | Linear interpolation between threshold and max score. Clamp to min/max lot sizes from settings. Pure domain logic. |
| **Regime detection (trending vs mean-reverting)** | Z-Score mean reversion fails spectacularly in trending markets. Detecting the current regime (Hurst exponent or simple ADX) and adjusting strategy weight prevents drawdowns during trends. | HIGH | ADX or rolling Hurst exponent on XRP/BTC ratio. When trending, reduce Z-Score weight, increase Lead-Lag weight. Adds complexity but dramatically improves robustness. |
| **Signal correlation monitoring** | Track whether the 4 factors agree or diverge. High agreement = high conviction. Divergence = caution. Similar to existing Pillar Dispersion in Sentiment Engine. | LOW | Reuse `compute_pillar_dispersion()` pattern from sentiment.py. Factor agreement as confidence multiplier on Alpha Score. |
| **Backtesting parameter sweep** | Existing orderblock backtesting has a parameter sweep mode (ATR multipliers, R:R ratios). Applying the same pattern to Alpha Score parameters (window lengths, weights, thresholds) enables systematic optimization. | MEDIUM | Grid search over Z-Score lookback, lead-lag window, weight combinations. CSV export with metrics per configuration. Pattern exists in `scripts/backtest_orderblock.py`. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for this specific project.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Live execution in v3.0** | "The whole point is automation" | Placing real orders without extensive dry-run validation is financially dangerous. The existing codebase has no circuit breakers, no max daily loss limits, no position size limits for automated trading. Live execution requires hardening that is explicitly out of scope (PROJECT.md). | Ship dry-run mode first. Validate signal quality over weeks. Live execution is a separate milestone with its own hardening phase. |
| **Machine learning signal optimization** | "Use ML to find optimal weights" | With 24 months of data and 4 factors, ML will overfit catastrophically. The parameter space is small enough for grid search. ML adds complexity (model serialization, retraining pipeline, feature engineering) with no benefit at this data scale. | Use backtesting parameter sweep (grid search). Interpretable, reproducible, no hidden correlations. ML only if data grows to years of tick-level data. |
| **Real-time P&L tracking with actual fills** | "Show me real money performance" | This is live execution tracking, not dry-run. Mixing dry-run virtual P&L with real portfolio ledger creates confusion and accounting nightmares. The ledger-first architecture must stay clean. | Dry-run tracks virtual portfolio in separate tables. Real portfolio stays in the existing ledger. Never mix. When live execution ships, it uses the real ledger. |
| **Multiple strategy profiles** | "Let me run different weight configurations simultaneously" | Multiplies complexity: multiple alpha scores, multiple decision logs, multiple virtual portfolios. Single-user app does not need this. | One active configuration at a time. Backtesting sweep to compare configurations. Switch configuration via Settings. |
| **Sub-second signal computation** | "HFT-level speed matters" | The bot operates on Binance Spot with maker/taker fees. At 0.1% per trade, sub-second timing provides negligible edge. The lead-lag momentum operates on 5-30 minute windows. Optimizing for microseconds adds WebSocket complexity for zero benefit. | 1-5 second signal refresh is sufficient. Depth20 WebSocket provides near-real-time orderbook data. Other factors (Z-Score, Lead-Lag) update on kline close. |
| **Telegram/Discord notifications** | "Alert me when signals fire" | External notification systems add operational complexity (bot tokens, message formatting, delivery guarantees). The user is looking at the dashboard. | In-app notifications via existing FillNotification WebSocket pattern. Bot status changes broadcast to connected frontend clients. |
| **Auto-adjusting factor weights based on recent performance** | "Adaptive weights that learn" | This is a form of online learning that is notoriously unstable in financial markets. Recent performance is a poor predictor of future performance (regime changes). Constant weight adjustment leads to whipsawing. | Fixed weights validated by backtesting. Manual weight adjustment via Settings when the user decides based on their judgment. |

## Z-Score Mean Reversion: Expected Behavior in Crypto

Z-Score measures how many standard deviations the current XRP/BTC ratio is from its rolling mean. This is the primary signal (40% weight) for good reason.

**Why XRP/BTC ratio (not XRP/EUR or XRP/USD):**
- The ratio eliminates common crypto market direction. Both XRP and BTC rise/fall with overall market sentiment. The ratio isolates the *relative* value of XRP vs BTC.
- Mean reversion in ratios is stronger than in absolute prices because the ratio has a natural anchor (the fundamental relationship between the two assets).
- Academic evidence: Gatev, Goetzmann, Rouwenhorst (2006) demonstrated pairs trading profitability; Vidyamurthy (2004) formalized the statistical approach.

**Typical Z-Score behavior in crypto markets:**
- **Lookback window:** 60 periods is a common starting point for hourly/4h data. Too short (20) = noisy, too many false signals. Too long (200) = slow to adapt to structural shifts.
- **Entry thresholds:** Z-Score of +/-2.0 is standard in traditional markets. Crypto is more volatile, so +/-2.5 or even +/-3.0 may be needed to filter noise. The project uses +/-3.0 for alpha threshold, which is conservative and appropriate.
- **Half-life of mean reversion:** In crypto, the XRP/BTC ratio typically mean-reverts with a half-life of 2-7 days. Faster than equity pairs (weeks) but slower than FX pairs (hours). This informs the holding period and trailing stop design.
- **Regime dependency:** Mean reversion breaks down during structural shifts (e.g., XRP delisting events, BTC dominance surges). This is why regime detection (differentiator, not table stakes) is valuable.
- **Fat tails:** Crypto Z-Scores have heavier tails than Gaussian. A Z-Score of 3.0 in crypto occurs more frequently than the 0.13% predicted by normal distribution. The threshold must account for this.

**Implementation requirements:**
- Rolling mean and standard deviation over configurable window (Decimal precision)
- Z-Score = (current_ratio - rolling_mean) / rolling_std
- Signal: Z < -threshold = XRP undervalued relative to BTC (buy XRP, or lean bullish on XRP/EUR). Z > +threshold = XRP overvalued (sell XRP, lean bearish).
- Must handle initialization period (first `window` periods have no valid Z-Score)

## Lead-Lag Momentum: Expected Behavior

BTC frequently "leads" altcoin price movements. When BTC makes a sharp move, altcoins follow with a delay. This is well-documented in crypto market microstructure literature.

**Typical characteristics:**
- **Lag window:** XRP typically follows BTC with a 5-30 minute delay, but this varies by market conditions. During high-volatility events (e.g., FOMC announcements), the lag compresses to seconds. During low-volatility periods, the lag can extend to hours.
- **Detection method:** Cross-correlation at multiple lags. Compute correlation between BTC returns at time `t` and XRP returns at time `t+lag` for lag = 1, 2, ..., N periods. The lag with maximum correlation is the detected lead-lag.
- **Signal generation:** When BTC makes a >X% move (scaled by ATR), and the optimal lag suggests XRP hasn't fully responded yet, this generates a momentum signal in the direction of BTC's move.
- **Decay:** The signal decays as time passes beyond the detected lag. If XRP hasn't moved after 2x the expected lag, the signal should be discarded (the relationship may have broken).
- **Correlation is not constant:** Lead-lag strength varies. During market stress, correlation spikes (all assets fall together, no lag). During calm markets, correlation may weaken. A rolling correlation coefficient should gate the signal -- only fire when correlation is strong enough.

**Implementation requirements:**
- Binance klines for BTCEUR and XRPEUR at the same timeframe
- Rolling cross-correlation computation
- BTC return calculation (percentage change over lookback period)
- Lag detection with confidence metric
- Signal decay function (linear or exponential)

## Orderbook Imbalance (depth20): Expected Behavior

Orderbook imbalance measures the asymmetry between bid and ask volume near the current price. A bid-heavy orderbook suggests buying pressure; ask-heavy suggests selling pressure.

**Existing vs. new implementation:**
- **Existing (SentimentDataService):** REST API, 1000-level depth, 5% spread window, 1min cache TTL. Used as one of 6 Sentiment pillars (10% weight). Formula: `(bid_vol - ask_vol) / total_vol`.
- **New (Omni-Bot Factor C):** WebSocket `depth20` stream, top 20 levels only, sub-second updates. Used as one of 4 Alpha Score factors (20% weight). Same formula but real-time.

**Why depth20 (not depth1000 REST):**
- depth20 via WebSocket updates every 100ms. REST depth1000 has 1min cache TTL. For a trading bot that needs to react to short-term imbalance shifts, 100ms is dramatically better than 60s.
- Top 20 levels capture the most actionable liquidity. Levels beyond top 20 are often from market makers who cancel orders before they fill.
- Lower data volume: 20 levels x 2 sides = 40 entries per update vs 1000 x 2 = 2000 entries. Less processing overhead.

**Typical behavior in crypto:**
- **Mean-reverting in quiet markets:** Imbalance oscillates around 0. Extreme imbalance (+/-0.5+) is temporary and reverts within minutes.
- **Predictive during momentum:** When imbalance persists in one direction during a price move, it confirms the move. Useful as a confirmation signal, less useful as a standalone signal.
- **Spoofing risk:** Large orders can appear and disappear (spoofing). Using the top 20 levels (tighter spread) mitigates this somewhat, as spoofed orders are typically placed further from mid-price.
- **Normalization:** Raw imbalance (-1 to +1) should be scored on a 0-100 scale (or -5 to +5 for Alpha Score) using rolling percentile normalization. Same approach as existing Sentiment Engine.

**Implementation requirements:**
- Subscribe to `xrpeur@depth20@100ms` and `btceur@depth20@100ms` via BinanceStreamManager
- Maintain current snapshot (depth20 provides full snapshot, not diff)
- Compute imbalance ratio for each symbol
- Rolling percentile or Z-Score normalization
- Score mapping to factor range

## Funding Rate Scoring: Expected Behavior

Funding rate measures the premium that perpetual futures traders pay. When funding is positive, longs pay shorts (bullish consensus, contrarian bearish signal). When negative, shorts pay longs (bearish consensus, contrarian bullish signal).

**Existing implementation reuse:**
- `SentimentDataService` already fetches OKX funding rate (EU-compliant, no Binance Futures needed)
- `score_funding_rate()` in `sentiment.py` already scores with fixed brackets (not percentile -- insufficient history)
- `_FUNDING_RATE_BRACKETS` already defines scoring thresholds

**For the Omni-Bot factor (10% weight):**
- Reuse the existing OKX funding rate data source
- Adapt scoring to the Alpha Score range (-5 to +5) instead of Sentiment's 0-100 range
- Consider adding relative funding rate (XRP funding vs BTC funding) as the existing Sentiment Engine already supports for altcoins via `score_funding_rate()` with `btc_funding_rate` parameter

**Implementation requirements:**
- Reuse `SentimentDataService._get_funding_rate()` or extract shared data fetching
- New scoring function mapping to Alpha Score factor range
- Handle "unavailable" gracefully (factor weight redistributed to remaining factors)

## Dry-Run Mode: Expected Behavior

Dry-run (paper trading) mode is the mandatory validation step between backtesting and live execution. It must be indistinguishable from live execution in terms of signal computation, with the sole difference being that no real orders are placed.

**Table-stakes expectations:**
- **Identical signal computation:** Same code path for signal calculation in dry-run and live. No "dry-run shortcut" that produces different results.
- **Virtual portfolio tracking:** Starting capital, virtual fills at market price when signals fire, virtual P&L tracking. Must use Decimal precision.
- **Decision log with full context:** Every signal evaluation logged: timestamp, all 4 factor scores, alpha score, threshold comparison, decision (BUY/SELL/HOLD), reason text.
- **Clear mode indicator:** The UI must make it unmistakably obvious that dry-run mode is active. Users must never mistake paper trading for live trading.
- **Persistent state:** Dry-run state survives server restarts. Virtual positions and decision log stored in database (separate tables from real ledger).
- **Real market data:** Dry-run uses live Binance prices and orderbook data. It does not use simulated or delayed data.

**Implementation pattern:**
```
SignalEngine.compute()  -- shared, pure domain logic
    |
    v
DecisionEngine.evaluate(signal, mode)  -- checks threshold, generates decision
    |
    +-- mode == DRY_RUN --> DryRunExecutor.log_decision() + VirtualPortfolio.update()
    |
    +-- mode == LIVE --> BinanceExecutor.place_order() + RealLedger.record()  [future milestone]
```

**Virtual portfolio model:**
- Separate table: `dry_run_positions` (not mixed with `trade_lots`)
- Separate table: `dry_run_decisions` (not mixed with `ledger_events`)
- Entry: virtual fill at next available price after signal fires
- Exit: ATR trailing stop triggered, or opposing signal
- P&L calculation: same formulas as real portfolio, different data store

**What NOT to include in dry-run:**
- Slippage simulation (impossible to model accurately on Binance Spot with unknown liquidity at future fill time)
- Latency simulation (adds complexity, marginal value for Spot trading at 5-30 minute signal horizons)
- Fee modeling in signal computation (fees should be modeled in backtesting P&L, but should not affect signal generation)

## Backtesting Engine: Expected Behavior

The new backtesting engine differs fundamentally from the existing orderblock backtest. Orderblock backtest simulates zone-approach trades (entry at zone, triple barrier exit). The Alpha Score backtester simulates multi-factor signal-driven trades over continuous time.

**Key differences from existing orderblock backtest:**

| Aspect | Orderblock Backtest | Alpha Score Backtest |
|--------|--------------------|--------------------|
| Entry trigger | Price touches zone | Alpha Score crosses threshold |
| Exit trigger | Triple barrier (target/stop/time) | ATR trailing stop or opposing signal |
| Continuous position | No (discrete zone trades) | Yes (can be in position for extended periods) |
| Multi-factor | No (single zone conviction) | Yes (4 factors combined) |
| Benchmark | Hit rate | Sharpe ratio, max drawdown, vs HODL |
| Tax simulation | No | Yes (German 365-day holding rule) |

**Required metrics:**
- **Sharpe ratio:** Annualized (return - risk_free_rate) / std(returns). Risk-free rate: 0% for crypto (no meaningful risk-free benchmark). Use daily returns.
- **Max drawdown:** Largest peak-to-trough decline in portfolio value. Both absolute EUR and percentage.
- **HODL benchmark:** "What if I just held XRP/BTC over the same period?" Essential for determining if the bot adds value over buy-and-hold.
- **Win rate:** Percentage of trades that are profitable (after fees).
- **Profit factor:** Gross profits / gross losses. >1.0 is profitable, >2.0 is strong.
- **Average trade duration:** How long positions are held on average (informs capital efficiency).
- **Tax-adjusted returns:** Post-tax P&L assuming German Abgeltungssteuer (26.375%) on gains from positions held <365 days.

**Implementation requirements:**
- Fetch 24 months of klines for BTCEUR, XRPEUR, and XRPBTC from Binance (reuse existing paginated kline fetcher from orderblock service)
- Compute all 4 factors at each bar
- Generate Alpha Score time series
- Simulate entry/exit decisions based on threshold and trailing stop
- Track virtual portfolio through simulation
- Compute all metrics at end
- Support parameter sweep (grid search over window lengths, weights, thresholds)

## Feature Dependencies

```
XRPBTC Symbol Registry Re-Addition
    |
    +--requires--> Z-Score Mean Reversion (needs XRPBTC ratio data)
    |
    +--requires--> Lead-Lag Momentum (needs BTCEUR + XRPEUR + XRPBTC klines)

Z-Score Mean Reversion (Factor A, 40%)
    |
    +--feeds-into--> Alpha Score Computation

Lead-Lag Momentum (Factor B, 30%)
    |
    +--feeds-into--> Alpha Score Computation

Orderbook Imbalance depth20 (Factor C, 20%)
    |
    +--requires--> BinanceStreamManager extension (new depth20 stream subscription)
    |
    +--feeds-into--> Alpha Score Computation

Funding Rate Scoring (Factor D, 10%)
    |
    +--reuses--> SentimentDataService._get_funding_rate()
    |
    +--feeds-into--> Alpha Score Computation

Alpha Score Computation (-5 to +5)
    |
    +--requires--> All 4 factors above
    |
    +--feeds-into--> Combined Score Integration
    |
    +--feeds-into--> Backtesting Engine
    |
    +--feeds-into--> Dry-Run Mode
    |
    +--feeds-into--> Bot Dashboard

ATR-Adaptive Trailing
    |
    +--reuses--> compute_atr() from orderblock/scoring.py
    |
    +--required-by--> Backtesting Engine (exit logic)
    |
    +--required-by--> Dry-Run Mode (exit logic)

Backtesting Engine
    |
    +--requires--> Alpha Score Computation
    |
    +--requires--> ATR-Adaptive Trailing (exit simulation)
    |
    +--requires--> Historical klines (reuse orderblock paginated fetcher)
    |
    +--independent-of--> Dry-Run Mode (can be built in parallel)

Dry-Run Mode
    |
    +--requires--> Alpha Score Computation (real-time signals)
    |
    +--requires--> ATR-Adaptive Trailing (exit management)
    |
    +--requires--> Decision Logging (new DB tables)
    |
    +--requires--> Virtual Portfolio (new DB tables)

Combined Score Integration
    |
    +--requires--> Alpha Score Computation
    |
    +--extends--> existing CombinedScoreResult, CombinedScoreService

Bot Dashboard (Frontend)
    |
    +--requires--> Alpha Score API endpoint
    |
    +--requires--> Dry-Run status/decisions API endpoints
    |
    +--requires--> Decision log API endpoint
    |
    +--extends--> GlobalNav (4th section: Bot)
```

### Dependency Notes

- **XRPBTC re-addition is the hard prerequisite:** Z-Score and Lead-Lag both require XRPBTC data. This must be done first, but it was already removed in v2.0 (Symbol Registry entry + Binance Sync support removed). Historical DB data was preserved. Re-addition is scoped: analysis + trading, but no cross-pair pairing (per PROJECT.md).
- **Alpha Score factors can be built in parallel:** Z-Score, Lead-Lag, Orderbook Imbalance, and Funding Rate are independent. They only converge at the Alpha Score computation step.
- **Backtesting and Dry-Run are independent of each other:** Backtesting uses historical data. Dry-Run uses live data. They share the Alpha Score computation and ATR trailing logic but have different execution paths.
- **Combined Score Integration can be deferred to late phase:** The Alpha Score is useful standalone (in Bot Dashboard) before it is integrated into the Combined Score system.
- **ATR trailing reuses existing code:** `compute_atr()` from `orderblock/scoring.py` is pure domain logic that can be imported directly. No duplication needed.
- **Orderbook depth20 WebSocket conflicts with nothing:** It is a new stream subscription added to the existing BinanceStreamManager. No changes to existing streams.

## MVP Definition

### Launch With (v3.0)

- [ ] XRPBTC re-addition to Symbol Registry + Binance Sync -- hard prerequisite for Z-Score and Lead-Lag
- [ ] Z-Score Mean Reversion engine (Factor A) -- core signal, pure domain logic, rolling window + threshold
- [ ] Lead-Lag Momentum detector (Factor B) -- cross-correlation, lag detection, signal decay
- [ ] Orderbook Imbalance from depth20 WebSocket (Factor C) -- BinanceStreamManager extension
- [ ] Funding Rate scoring adapted for Alpha Score (Factor D) -- reuse existing OKX data source
- [ ] Alpha Score computation (-5 to +5, weighted combination, threshold +/-3.0)
- [ ] ATR-Adaptive Trailing stop engine -- reuse compute_atr(), configurable multipliers per symbol
- [ ] Backtesting Engine -- 24-month simulation, Sharpe, max drawdown, HODL benchmark, fee modeling
- [ ] Dry-Run Mode -- real-time signals, decision logging, virtual portfolio, no real orders
- [ ] Decision logging with full context -- append-only log of all signal evaluations
- [ ] Bot Dashboard -- status card, current alpha score, signal history, virtual P&L
- [ ] Combined Score Integration -- Alpha Score as additional signal source
- [ ] Settings extension -- alpha threshold, factor weights, trailing stop multipliers, dry-run toggle

### Add After Validation (v3.x)

- [ ] Tax simulation in backtesting -- German 365-day rule, Abgeltungssteuer modeling
- [ ] Backtesting parameter sweep -- grid search over weights, windows, thresholds with CSV export
- [ ] Regime detection -- ADX or Hurst exponent to weight factors dynamically
- [ ] Signal correlation monitoring -- factor agreement as confidence metric
- [ ] Conviction-weighted position sizing -- Alpha Score intensity modulates size

### Future Consideration (v4+)

- [ ] Live execution mode -- actual order placement via Binance API, requires circuit breakers, max daily loss, position limits
- [ ] Multi-strategy profiles -- run different configurations simultaneously
- [ ] WebSocket recovery hardening -- reconnection logic, missed-message detection, state reconciliation
- [ ] Extended backtest data -- >24 months, tick-level data if available

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| XRPBTC re-addition | HIGH (blocker) | LOW (registry + sync, pattern known) | P1 |
| Z-Score Mean Reversion | HIGH (core signal) | MEDIUM (rolling stats, Decimal math) | P1 |
| Lead-Lag Momentum | HIGH (key differentiator) | HIGH (cross-correlation, lag detection) | P1 |
| Orderbook Imbalance depth20 | MEDIUM (upgrade over REST) | MEDIUM (WebSocket stream, new subscription) | P1 |
| Funding Rate scoring | MEDIUM (reuses existing) | LOW (adapter from Sentiment scoring) | P1 |
| Alpha Score computation | HIGH (combines all factors) | LOW (weighted sum, pure domain) | P1 |
| ATR-Adaptive Trailing | HIGH (exit management) | LOW (reuses compute_atr()) | P1 |
| Backtesting Engine | HIGH (validation) | HIGH (new engine, metrics, benchmark) | P1 |
| Dry-Run Mode | HIGH (trust building) | MEDIUM (new tables, decision logging, virtual portfolio) | P1 |
| Bot Dashboard | MEDIUM (visibility) | MEDIUM (new nav section, 3-4 components) | P1 |
| Combined Score Integration | MEDIUM (unification) | MEDIUM (extend existing domain + service) | P1 |
| Settings extension | MEDIUM (configurability) | LOW (extend existing pattern) | P1 |
| Tax simulation | LOW (nice-to-have) | MEDIUM (per-trade tax logic) | P2 |
| Parameter sweep | LOW (optimization) | MEDIUM (grid search, CSV export) | P2 |
| Regime detection | MEDIUM (robustness) | HIGH (Hurst/ADX, dynamic weights) | P3 |

**Priority key:**
- P1: Must have for v3.0 launch
- P2: Should have, add when possible within milestone
- P3: Nice to have, defer to v3.x or later

## Existing Module Reuse Analysis

The codebase has significant infrastructure that can be reused or extended for the Omni-Bot. This reduces implementation risk.

| Existing Module | What to Reuse | Adaptation Needed |
|-----------------|---------------|-------------------|
| `orderblock/scoring.py: compute_atr()` | ATR computation with Wilder's Smoothing | None -- import directly for trailing stop computation |
| `sentiment.py: score_orderbook_imbalance()` | Orderbook imbalance scoring pattern | Adapt for depth20 data (20 levels vs 1000) and Alpha Score range |
| `sentiment.py: score_funding_rate()` | Funding rate scoring with brackets | Adapt scoring output to -5..+5 range instead of 0..100 |
| `sentiment.py: compute_pillar_dispersion()` | Factor agreement / confidence metric | Apply to Alpha Score factors for signal quality assessment |
| `sentiment_data_service.py: _get_funding_rate()` | OKX funding rate data fetching | Reuse data source, extract shared utility if needed |
| `orderblock_data_service.py: fetch_candles()` | Paginated Binance kline fetching with TTL cache | Reuse for backtesting historical data fetching |
| `websocket_manager.py: BinanceStreamManager` | WebSocket stream management, subscriber pattern | Extend with depth20 stream subscription |
| `combined_score.py: compute_combined_score()` | Signal combination with conflict detection | Extend to accept Alpha Score as third signal source |
| `combined_score_service.py` | Signal orchestration pattern | Extend to fetch Alpha Score alongside Macro + Sentiment |
| `FillNotification.jsx` | Real-time notification pattern | Reuse for signal fire notifications in dry-run mode |
| `CombinedScore.jsx` | Score visualization, sub-signal cards | Pattern for Alpha Score display in Bot Dashboard |
| `UserSettingsDB` | Per-user settings with defaults | Extend schema for alpha threshold, weights, trailing params |
| `symbol_registry.py` | Symbol management, precision config | Add XRPBTC entry (was removed in v2.0, pattern known) |

## Sources

- Z-Score mean reversion methodology: Gatev, Goetzmann, Rouwenhorst (2006) "Pairs Trading: Performance of a Relative Value Arbitrage Rule" -- HIGH confidence (established academic work, from training data)
- Pairs trading statistical framework: Vidyamurthy (2004) "Pairs Trading: Quantitative Methods and Analysis" -- HIGH confidence (established textbook)
- Lead-lag relationships in crypto: well-documented in crypto market microstructure literature. BTC dominance as leading indicator is a standard observation -- MEDIUM confidence (from training data, specific lag characteristics may vary)
- ATR-based trailing stops: Wilder (1978) "New Concepts in Technical Trading Systems" -- HIGH confidence (foundational work, ATR already implemented in codebase)
- Orderbook imbalance as trading signal: Cont, Stoikov, Talreja (2010) "A Stochastic Model for Order Book Dynamics" -- MEDIUM confidence (academic foundation, crypto-specific behavior from training data)
- Binance depth20 WebSocket stream: documented in Binance API docs, stream format `<symbol>@depth20@100ms` -- MEDIUM confidence (from training data, need to verify current API spec)
- German crypto tax (365-day holding period, Abgeltungssteuer 26.375%): well-established German tax law -- MEDIUM confidence (tax rates may have changed since training data cutoff, verify)
- Existing codebase analysis: 100% of reuse candidates verified by direct code inspection -- HIGH confidence
- Triple Barrier Method: Lopez de Prado (2018) "Advances in Financial Machine Learning" -- HIGH confidence (already implemented in orderblock_backtest.py)
- Sharpe ratio, max drawdown: standard quantitative finance metrics -- HIGH confidence

---
*Feature research for: Multi-Factor Omni-Bot (v3.0)*
*Researched: 2026-02-25*
