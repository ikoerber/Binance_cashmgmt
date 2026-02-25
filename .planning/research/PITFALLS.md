# Pitfalls Research

**Domain:** Multi-Factor Omni-Bot addition to existing BTC/EUR Cashflow-Management app -- re-adding removed trading pair, multi-factor scoring engine, real-time signal processing, backtesting, dry-run mode, Combined Score integration
**Researched:** 2026-02-25
**Confidence:** HIGH (based on deep codebase analysis of existing WebSocket, Combined Score, Alembic, and Symbol Registry code)

## Critical Pitfalls

### Pitfall 1: XRPBTC Re-Addition Collides with Column-Dropping Migration

**What goes wrong:**
In v2.0, migration `094dac6f695a` explicitly dropped 6 columns across 4 tables that were essential for XRPBTC cross-pair support:
- `pairings.routing_decision_json` (Text)
- `pairings.base_asset` (String)
- `trade_lots.quote_to_eur_rate` (Numeric)
- `pairing_items.cost_eur` (Numeric)
- `pairing_items.lot_symbol` (String)
- `sell_allocations.realized_pnl_eur` (Numeric)

The PROJECT.md states "XRPBTC re-added ... no cross-pair pairing", meaning these columns should NOT be re-added. But XRPBTC lots will have `quote_asset="BTC"` (not EUR). The existing `cost_quote` column stores costs in quote currency -- for XRPBTC lots this will be BTC, not EUR. Every existing code path that treats `cost_quote` as EUR-denominated will produce wrong P&L calculations. The `break_even` calculated from `cost_quote / qty_base_initial` will be in BTC, not EUR.

Additionally, the `cost_eur` column on `trade_lots` exists but was designed in v1.0 for EUR-equivalent costs. For XRPBTC lots, `cost_eur` must be populated via BTC-to-EUR conversion at fill time. If the backfill or real-time conversion fails, `cost_eur` will be NULL for some lots, causing NoneType errors in P&L calculations.

**Why it happens:**
The decision to "re-add XRPBTC without cross-pair pairing" sounds simple -- just add it to the Symbol Registry. But the v2.0 removal was thorough: it stripped ALL BTC-quote handling infrastructure. Re-adding the symbol without restoring the quote-currency abstraction means every computation that assumes `cost_quote` is in EUR breaks silently with wrong numbers (not crashes).

**How to avoid:**
1. XRPBTC needs `quote_to_eur_rate` back on `trade_lots` (new forward migration, NOT a downgrade of 094dac6f695a). This captures the BTC/EUR rate at fill time for deterministic EUR conversion.
2. Every domain function that reads `cost_quote` must be audited for EUR assumption. Key functions: `compute_portfolio_from_ledger()`, `suggest_pairings()`, `simulate_pairing()`, lot P&L calculations.
3. The `cost_eur` column already exists on `trade_lots` -- populate it for XRPBTC lots using `cost_quote * quote_to_eur_rate`.
4. Explicitly test: "XRPBTC lot displays correct EUR break-even on Dashboard" and "XRPBTC lots do NOT appear in EUR-pair Pairing suggestions".

**Warning signs:**
- XRPBTC lots showing break-even in the range of 0.00002 (BTC-denominated) instead of ~0.50 EUR
- Portfolio aggregation showing wrong totals when XRPBTC lots are included
- `cost_eur = None` for new XRPBTC lots if conversion fails

**Phase to address:**
Phase 1 (XRPBTC Re-Addition) -- must handle quote-currency abstraction BEFORE any scoring/trading logic touches XRPBTC.

---

### Pitfall 2: WebSocket Connection Explosion with Multiple Binance Streams

**What goes wrong:**
The current `BinanceStreamManager` uses a single combined ticker stream (`_run_price_stream`) and a single user data stream per user (`_run_user_data_stream`). Adding depth20 orderbook streams and tick-level trade streams means:

1. **Binance enforces a max of 5 WebSocket connections per IP for streams** (documented in Binance API docs). The current architecture opens 2 connections (1 combined ticker + 1 user data). Adding separate depth20 streams per symbol could easily exceed the 5-connection limit: ticker(1) + user_data(1) + depth20_BTCEUR(1) + depth20_XRPEUR(1) + depth20_XRPBTC(1) = 5, leaving zero headroom.

2. **The depth20 stream pushes every second** (1 Hz) per symbol. With 3 symbols, that is 3 messages/second just from orderbook data. The current `_broadcast_price` method iterates subscribers synchronously -- if any WebSocket send is slow, it blocks ALL updates. At 3 messages/second per stream, a slow client causes cascading delays.

3. **The `aiohttp.ClientSession` is created per connection** in `_run_price_stream` and `_run_user_data_stream` (lines 134 and 279). Creating a new `ClientSession` for each reconnect leaks TCP connections if not properly closed during error paths.

**Why it happens:**
The existing WebSocket architecture was designed for 2 streams (ticker + user data) with low update frequency (ticker: ~1/sec, user data: event-driven). It was never stress-tested with continuous high-frequency data streams. Adding streams seems like "just add another connection" but hits the Binance connection limit.

**How to avoid:**
1. Use Binance combined streams (`/stream?streams=`) for ALL public data. A single combined stream URL can carry ticker + depth20 + trade streams for multiple symbols. This keeps the connection count at 2 (1 public combined + 1 user data).
2. Combined stream URL format: `wss://stream.binance.com:9443/stream?streams=btceur@ticker/btceur@depth20/xrpbtc@ticker/xrpbtc@depth20/xrpbtc@trade`
3. Use a shared `aiohttp.ClientSession` for all stream connections (one per manager lifetime, not per connection).
4. Add non-blocking broadcast: replace the synchronous subscriber iteration with `asyncio.gather()` with timeouts per client, dropping slow clients.
5. Track connection count in `get_stats()` to detect approaching the limit.

**Warning signs:**
- "Max reconnect attempts reached" errors appearing within seconds of startup
- Depth data arriving with 2-3 second delays (queuing behind slow broadcasts)
- `aiohttp` warnings about unclosed client sessions in logs

**Phase to address:**
Phase 2 (Multi-Factor Scoring Engine) or whenever depth20/trade streams are first needed. Must be addressed BEFORE adding any real-time data consumers.

---

### Pitfall 3: Combined Score Weight Rebalancing Breaks Existing Signal Interpretation

**What goes wrong:**
The current Combined Score uses hardcoded weights in `combined_score.py`:
```python
DIRECTION_WEIGHT = Decimal("0.60")  # MacroSignal
SIZING_WEIGHT = Decimal("0.40")     # Sentiment
```

Adding Alpha Score as a third signal requires rebalancing. If weights change to, say, MacroSignal 40% + Sentiment 25% + Alpha 35%, the same market conditions will produce different Unified Scores than before. A market state that previously produced +45 (BUY) might now produce +30 (LEAN_BUY). Users who have learned the signal thresholds will be confused.

Worse, the `ACTION_THRESHOLDS` array maps scores to 7 action levels with fixed breakpoints (-60, -30, -10, +10, +30, +60). If the score distribution shifts due to rebalancing, previously rare actions ("Aggressiv kaufen") could become common or vice versa, making the system feel unreliable.

The conflict detection logic (`_detect_conflict`) currently checks only 2 signals. With 3 signals, you need 3-way conflict detection: MacroSignal bullish + Sentiment bearish + Alpha neutral is qualitatively different from MacroSignal bullish + Sentiment bullish + Alpha bearish.

**Why it happens:**
Developers add Alpha Score as "just another weighted input" without modeling the score distribution change. The existing Combined Score was carefully calibrated -- weights, thresholds, and conflict detection form an interconnected system. Changing any weight changes the output distribution of ALL thresholds.

**How to avoid:**
1. Do NOT change existing MacroSignal/Sentiment weights. Instead, add Alpha Score as a modulating factor that adjusts the existing Combined Score by a bounded amount (e.g., +/- 15 points).
2. Alternative: Create a separate "Bot Score" that includes Alpha Score, keeping the existing Combined Score intact for the Dashboard widget. The Bot Dashboard uses Bot Score; the Trading area keeps the familiar Combined Score.
3. If weights must change: run historical simulation comparing old vs. new score distribution, document threshold recalibration, and version the scoring model (v1 = current, v2 = with Alpha).
4. Extend `_detect_conflict` to handle N signals, not just 2.

**Warning signs:**
- The Combined Score Widget on the Dashboard shows different recommendations than before the Alpha Score integration, despite identical market conditions
- Action distribution shifts noticeably (e.g., "Abwarten" was 40% of the time, now 60%)
- Users report "the system changed its mind" on familiar market patterns

**Phase to address:**
Phase 4 (Combined Score Integration) -- must include score distribution analysis and threshold recalibration. Consider keeping Combined Score unchanged and creating a separate Bot Score.

---

### Pitfall 4: Backtesting Engine Rate-Limited During Historical Data Fetch

**What goes wrong:**
The backtesting engine needs 24 months of 1h klines. For a single symbol (BTCEUR), that is ~17,520 candles. Binance returns max 1000 klines per request, requiring 18 paginated requests. For 3 symbols, that is 54 requests.

The existing `orderblock_data_service.py` already handles pagination, but its 1-hour TTL cache is designed for detection (not backtesting). The backtesting engine will need to fetch fresh data on each run if parameters change, and 54 requests in rapid succession risks hitting Binance's IP-based rate limit (1200 requests/minute for public endpoints, but the `requests` library does not track this). Combined with other services (MacroDataService, SentimentDataService) also fetching klines, the cumulative request rate could exceed limits.

The `BinancePublicClient` uses `@retry_on_transient_error(max_retries=3)` which waits up to 30 seconds between retries. If rate-limited at request 30 out of 54, the backtest could stall for 90+ seconds (3 retries x 30s) before either succeeding or failing.

**Why it happens:**
Each service (Orderblock, MacroData, SentimentData, new BacktestEngine) independently fetches from Binance without coordinating request budgets. There is no global rate limiter. Each service has its own retry logic that can collide -- when one service backs off, another keeps firing, and the backed-off service's retry hits again during the other service's active window.

**How to avoid:**
1. Implement a global rate limiter in `BinancePublicClient` (token bucket or sliding window). Since `BinancePublicClient` is already a singleton (`get_binance_public_client()`), add rate limiting there. All services already use this client.
2. Cache historical klines aggressively: 24-month 1h klines change only at the most recent candle. Cache the first 17,500 candles indefinitely, only re-fetch the last 20 candles. Use disk-based cache (SQLite or pickle file) for historical klines, not just in-memory TTL cache.
3. Stagger requests: insert 50-100ms delays between paginated kline requests to stay well under the 1200/min limit.
4. Pre-fetch data for all symbols in a single batch job before backtesting, rather than on-demand during backtest execution.

**Warning signs:**
- Backtest initiation takes 30+ seconds (rate-limit retries)
- "429 Rate Limit" errors in logs during backtesting
- Other services (Combined Score Widget) start showing stale data because their retries are being consumed by backtest traffic

**Phase to address:**
Phase 3 (Backtesting Engine) -- must implement centralized rate limiting and historical kline caching BEFORE allowing multi-symbol backtest runs.

---

### Pitfall 5: Z-Score Rolling Window Cold Start Produces False Signals

**What goes wrong:**
Z-Score Mean Reversion (40% of Alpha Score) requires a rolling window of historical values to compute mean and standard deviation. During cold start (first application launch or after data gap), the rolling window is empty or too small. Computing Z-Score from 5 data points instead of the intended 50 produces:
- Wildly inaccurate mean (a few outliers skew it)
- Near-zero or NaN standard deviation (division by zero if all values are identical)
- Z-Scores of +50 or -50 for normal price movements, triggering extreme signals

The existing `SentimentDataService` has this exact pattern with `_initialize_history()` (line 78 shows `_history_initialized` flag). It solves it by pre-loading 300 days of klines. But the new Z-Score calculator needs sub-hourly data (1m or 5m klines), and 50 rolling periods of 1m klines is only 50 minutes of data -- a much faster initialization. The risk is that developers see "only 50 minutes" and skip the initialization step, assuming data will accumulate naturally.

The problem is worse for Lead-Lag Momentum (30% of Alpha Score) which compares XRP price movement to BTC price movement. If one symbol's window is full and the other's is not, the lead-lag correlation is computed from mismatched window sizes, producing spurious correlation values.

**Why it happens:**
Developers implement the steady-state algorithm (rolling window full, Z-Score valid) and forget about the transient state (window filling up). Unit tests typically pre-populate the window, so the cold-start path is never tested.

**How to avoid:**
1. Define a `MIN_WINDOW_SIZE` constant (e.g., 30 data points) below which the Z-Score returns `None` (not 0, not a default). The Alpha Score must handle `None` inputs gracefully by excluding that factor and renormalizing weights.
2. The initialization function must pre-load enough historical data to fill the window. For 1m klines with a 50-period window, fetch the last 60 minutes of klines on startup.
3. For Lead-Lag: both symbols' windows must have the SAME timestamps. Use a shared time index. If one symbol has gaps, the other's corresponding data point must be excluded from correlation.
4. Add a "warmup" status flag to the Alpha Score API response: `{"alpha_score": ..., "warmup": true, "warmup_remaining_pct": 40}`. The UI should show "warming up" instead of displaying unreliable scores.
5. Write explicit cold-start tests: test Z-Score with 0, 1, 5, 29, 30, and 50 data points.

**Warning signs:**
- Alpha Score showing extreme values (+5 or -5) immediately after app restart
- Z-Score mean that jumps around wildly during the first hour of operation
- Lead-Lag correlation flipping between +1 and -1 within minutes

**Phase to address:**
Phase 2 (Multi-Factor Scoring Engine) -- cold start handling must be part of the initial implementation, not bolted on later.

---

### Pitfall 6: Dry-Run Mode State Divergence from Live Mode

**What goes wrong:**
Dry-run mode must log decisions (when it would have bought/sold) without placing real orders. The divergence problem occurs because dry-run mode cannot know the ACTUAL fill price, slippage, or partial fill behavior. Dry-run assumes:
- Fills at the decision price (reality: slippage)
- Complete fills (reality: partial fills, especially for XRP with lower liquidity)
- Instant fills (reality: TAKE_PROFIT_LIMIT orders can sit unfilled for hours)

Over 24 months of dry-run, these small divergences compound. A dry-run backtest might show +15% returns, but live execution might achieve only +8% because of slippage on every trade.

The deeper issue: the existing system tracks lots, allocations, and orders in the database. Dry-run mode needs a SEPARATE tracking path that does not pollute production data. If dry-run decisions are written to the same `trade_lots` or `orders` tables (even with a flag), queries that filter by status will include dry-run data unless every query adds `AND is_dry_run = FALSE`.

**Why it happens:**
Dry-run seems like "just don't call the Binance API". But the entire system downstream of order placement (lot creation, sell allocation, portfolio P&L) assumes real fills. Dry-run must simulate the ENTIRE pipeline, not just skip the API call.

**How to avoid:**
1. Dry-run uses a completely separate set of tables or a separate SQLite database file. No production data contamination.
2. Alternative: Dry-run writes to a `dry_run_decisions` table with its own schema (timestamp, symbol, side, intended_price, intended_qty, alpha_score_at_decision, reason). This is an append-only log, NOT an integration with the lot/allocation system.
3. Dry-run must include realistic slippage modeling: assume 0.05% slippage for BTC/EUR, 0.15% for XRP/BTC (lower liquidity). These are conservative estimates.
4. Never add `is_dry_run` boolean to production tables. This is the path to data contamination.
5. The dry-run log should capture the FULL scoring state at decision time (all 4 factor scores, Alpha Score, trailing stop levels) for later analysis.

**Warning signs:**
- Dry-run P&L looks suspiciously good compared to backtesting results
- Production queries start returning unexpected data after dry-run mode was activated
- "Ghost lots" appearing in the Trade Cockpit that do not correspond to real positions

**Phase to address:**
Phase 4 (Dry-Run Mode) -- must be designed as separate data path from day one. Resist the temptation to reuse production infrastructure.

---

### Pitfall 7: ATR-Adaptive Trailing Triggers False Exits on Data Gaps

**What goes wrong:**
ATR-Adaptive Trailing adjusts the trailing stop distance based on current ATR (volatility). This requires continuous price monitoring. If the WebSocket disconnects for 30 seconds (common during Binance maintenance), the next price received after reconnect might be significantly different from the last known price. The trailing stop logic sees this as a sudden price move and may:
1. Trigger a stop-loss exit because the gap "crosses" the trailing stop level
2. Tighten the trailing distance because ATR drops during the gap (no price movement = low ATR)

The existing `scheduleReconnect` in `WebSocketContext.jsx` uses exponential backoff (1s, 2s, 4s ... 30s). During a 30-second reconnect, the backend's `BinanceStreamManager` also disconnects from Binance streams. This means NO price data flows for potentially 30+ seconds.

The ATR calculation uses Wilder's Smoothing (the existing `compute_atr()` in `orderblock.py`), which requires continuous data. A gap of 30+ candles in a 1-minute timeframe invalidates the ATR smoothing and produces artificially low volatility readings upon resumption.

**Why it happens:**
Trailing stop implementations assume a continuous price feed. Real-world WebSocket connections have gaps (network issues, Binance maintenance, rate limiting). The algorithm works perfectly in backtesting (no gaps in historical data) but fails in live operation.

**How to avoid:**
1. Trailing stop must have a "staleness threshold": if last price update is older than 2x the expected update interval, freeze the trailing stop (do not move it in either direction) until fresh data arrives.
2. After a data gap, require N consecutive fresh data points (e.g., 5) before resuming trailing stop adjustments. This prevents gap-exit triggers.
3. ATR must be computed from historical klines (REST API fallback), not solely from the WebSocket stream. On reconnect, fetch the last 25 klines via REST to re-anchor the ATR.
4. Add a "data quality" flag to the trailing stop state: ACTIVE / FROZEN / RECALIBRATING. The Bot Dashboard should display this state.
5. Log every trailing stop adjustment with the data quality state for post-mortem analysis.

**Warning signs:**
- Trailing stops triggering during known Binance maintenance windows
- ATR values dropping to near-zero after WebSocket reconnection
- Trailing distance tightening rapidly after a disconnect (false volatility compression)

**Phase to address:**
Phase 3 (ATR-Adaptive Trailing) -- gap handling must be baked into the initial implementation. Use the existing `connected` state from WebSocketContext as a data quality input.

---

### Pitfall 8: Tick Data Processing Blocks the asyncio Event Loop

**What goes wrong:**
Lead-Lag Momentum Detection requires sub-second tick data (`@trade` stream). Each tick triggers: price update, rolling window update, correlation calculation, and potentially a signal emission. The current `_handle_execution_report` in `websocket_manager.py` uses `asyncio.create_task()` for DB operations (line 372), which correctly offloads to a thread pool. But if the new tick processing also involves DB writes (persisting tick data for analysis) or CPU-intensive calculations (rolling correlation over 500+ ticks), and these run synchronously in the event loop, they block ALL other WebSocket message processing.

The `@trade` stream for BTCEUR alone produces 50-200 messages per second during active trading. Processing each tick synchronously in the event loop means each tick handler must complete in under 5ms to keep up. Rolling window correlation over 500 data points takes 1-5ms in Python (depending on implementation) -- borderline. Adding logging or DB writes pushes it over.

**Why it happens:**
The existing WebSocket handler works with low-frequency events (ticker: ~1/sec, execution reports: rare). Developers add tick processing using the same pattern without benchmarking the throughput requirements.

**How to avoid:**
1. Tick data processing must happen in a SEPARATE asyncio task or thread, NOT in the WebSocket message handler. The handler should only: parse the tick, append to an in-memory ring buffer, and return immediately. A separate consumer task processes the buffer periodically (e.g., every 100ms).
2. Use `collections.deque` for tick buffers (maxlen=1000). Overflow drops oldest ticks automatically.
3. Correlation and Z-Score calculations should run in `asyncio.to_thread()` (like the existing `handle_fill_event` pattern) to avoid blocking the event loop.
4. Benchmark: 200 ticks/sec x 5ms/tick = 1 second of processing per second = 100% CPU, event loop starved. Target: < 0.5ms per tick in the handler, batch processing every 100ms.
5. Consider downsampling: instead of processing every tick, aggregate into 1-second OHLCV bars in-memory. This reduces processing from 200/sec to 1/sec while preserving the essential information.

**Warning signs:**
- Price updates in the frontend lagging by 2-5 seconds during active trading
- WebSocket heartbeat (ping/pong every 30s) timing out, triggering reconnects
- CPU usage of the backend process at 100% during active market hours

**Phase to address:**
Phase 2 (Multi-Factor Scoring Engine) -- the tick data architecture must be designed for throughput from the start. Do NOT add `@trade` stream handlers in the same pattern as the existing `@ticker` handler.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing Alpha Score factors in existing `user_settings` table as JSON blob | Avoids new migration, quick to implement | No schema validation, no queryability, settings table becomes a dumping ground | Never -- Alpha Score config deserves its own table or at minimum typed columns |
| Using `float` for Z-Score calculations instead of `Decimal` | Faster computation, simpler code | Inconsistent with project's Decimal-everywhere convention, subtle precision drift in rolling calculations over thousands of ticks | Acceptable for intermediate calculations (Z-Score, correlation), but final Alpha Score output and stored values must be Decimal |
| Sharing the existing `orderblock_data_service` kline cache for backtesting | Avoid building new cache infrastructure | 1-hour TTL designed for detection evicts historical data too quickly for backtesting; backtest runs during cache eviction fetch redundant data | Never for 24-month datasets -- build separate persistent cache |
| Dry-run writes decisions to production `orders` table with `is_dry_run=TRUE` | Reuses existing order infrastructure, appears in existing UI | Every production query must add filter, easy to forget, data contamination risk | Never -- use separate table or separate database |
| Using `time.sleep()` in rate limiter inside async code | Simple to implement | Blocks the entire event loop, freezes all WebSocket connections | Never in async context -- use `asyncio.sleep()` or token-bucket pattern |
| Hardcoding Alpha Score weights (40/30/20/10) as constants | Quick to ship, no UI needed | Cannot tune without code change, no A/B testing capability | Acceptable for MVP/dry-run phase, must move to user_settings before live execution |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Binance Combined WebSocket Stream | Adding depth20 as separate connection (hits 5-connection limit) | Use combined stream URL: `?streams=btceur@ticker/btceur@depth20/xrpbtc@trade` in single connection |
| Binance Klines API for Backtesting | Fetching 24 months in a single request (returns max 1000 candles, silently truncates) | Paginate with `startTime`/`endTime`, verify candle count matches expected: `24*30*24 = 17,280 for 1h candles` |
| Binance `@trade` stream | Assuming one message per trade (large orders produce multiple trade events with same orderId but different tradeIds) | Aggregate by orderId for order-level analysis, process each tradeId individually for tick-level analysis |
| Binance depth20 stream | Treating depth20 snapshot as incremental diff (it is a full snapshot each second, not a diff) | Replace entire local orderbook on each message, do NOT apply as delta |
| OKX Funding Rate (existing) | Assuming funding rate updates every message (OKX sends rate only every 8 hours) | Cache for 15 minutes (existing behavior), but do NOT increase polling frequency -- no new data will appear |
| XRPBTC on Binance | Assuming XRPBTC has same liquidity as BTCEUR (XRPBTC daily volume is ~50x lower) | Use wider slippage estimates (0.15% vs 0.05%), larger ATR multipliers, and lower confidence for orderbook signals |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Computing Alpha Score on every tick (200/sec) | CPU at 100%, price updates lag 5+ seconds | Batch ticks into 1-second bars, compute Alpha Score on bar close (1/sec) | > 50 ticks/sec per symbol |
| SQLite NullPool (existing) with concurrent backtest + live trading | "database is locked" errors during backtest writes | Use connection pooling with WAL mode, or separate backtest DB file | When backtest and sync_service write simultaneously |
| In-memory deque for all rolling windows (no disk persistence) | After restart, all scoring signals invalid for warmup period | Persist rolling window snapshots to DB every 5 minutes for fast recovery | After any restart |
| Broadcasting tick data to all frontend WebSocket clients | Backend saturated at 200 msgs/sec/client with 3 clients = 600 sends/sec | Downsample to 1-second bars before broadcasting; tick data stays backend-only | > 2 concurrent frontend clients during active trading |
| Fetching XRPBTC klines alongside BTCEUR/XRPEUR on startup | Triple the API calls, triple the cold-start time | Lazy-load: fetch XRPBTC data only when user selects XRPBTC symbol | On every application start |
| Backtesting with full-resolution 1m klines for 24 months | 1,051,200 candles per symbol, ~800MB in memory as Python dicts | Use 1h klines for backtesting (17,520 candles), reserve 1m for live signal generation only | > 6 months of 1m data |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Dry-run mode accepting real money orders if flag is misconfigured | Real money lost on untested strategy | Dry-run mode must have NO access to Binance API credentials (no `api_key` in its service constructor). Structural prevention, not flag-based. |
| Alpha Score logging raw Binance API responses (may contain IP/account info) | Information leakage in structured logs | Log only computed scores and decisions, never raw API payloads. Follow existing `error_sanitization` pattern. |
| Backtesting results accessible without authentication | Proprietary trading strategy exposure | Backtest results must be behind existing API key auth (`X-API-Key` header), same as all other endpoints. |
| XRPBTC orders placed without Max Order Value check in BTC terms | Large unintended BTC positions | Extend `max_order_value_eur` check to convert XRPBTC order value to EUR before validation: `qty * price_xrpbtc * price_btceur`. |
| WebSocket depth20 data exposure to frontend | Shows exact orderbook state, could be used for front-running | Keep depth20 data backend-only. Only send derived signals (Orderbook Imbalance score) to frontend, never raw depth data. |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing Alpha Score during warmup period | User sees extreme values (+5/-5), loses trust in the system | Show "Warming up (85%)" progress indicator until MIN_WINDOW_SIZE reached |
| Bot Dashboard shows all 4 scoring factors with equal visual weight | User overwhelmed, cannot quickly assess overall signal | Visual hierarchy: Alpha Score prominently on top, factor breakdown in collapsible section (like existing CombinedScore pattern) |
| Dry-run P&L shown alongside real P&L on Dashboard | User confuses simulated with real performance | Dry-run results ONLY on Bot Dashboard page, never on main Dashboard. Use distinct color scheme (e.g., dotted borders, "SIMULATION" watermark) |
| Backtest results showing raw numbers without context | "Hit rate 55%" -- is that good or bad? | Always show benchmark comparison: "55% hit rate vs 50% HODL baseline" and risk-adjusted metrics (Sharpe ratio) |
| Trailing stop parameters exposed as raw numbers (ATR multiplier 2.5) | Non-technical user has no intuition for what 2.5 means | Show translated labels: "Conservative (3.0x)", "Balanced (2.0x)", "Aggressive (1.5x)" with ATR multiplier as tooltip |
| XRPBTC appearing in symbol selector without clear distinction | User accidentally activates signals for a low-liquidity pair | Show liquidity warning badge next to XRPBTC: "Low liquidity -- wider spreads expected". Default to BTCEUR. |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **XRPBTC Symbol Registry addition:** Often missing -- testing that `parse_symbol("XRPBTC")` returns `TradingPair` with `quote_asset="BTC"`, and that all downstream code correctly identifies BTC as non-EUR quote. Verify: `get_quote_asset("XRPBTC") == "BTC"` and every P&L calculation converts to EUR.
- [ ] **Alpha Score API endpoint:** Often missing -- warmup status in response. Verify: response includes `warmup: boolean` and `quality: "full" | "partial" | "warming_up"` fields.
- [ ] **Combined Score Integration:** Often missing -- updated conflict detection for 3+ signals. Verify: `_detect_conflict` handles MacroSignal + Sentiment + Alpha permutations, not just 2-way.
- [ ] **Backtesting date range validation:** Often missing -- validation that `start_date` is not in the future and `end_date - start_date` does not exceed available data. Verify: meaningful error message instead of empty results.
- [ ] **Dry-Run table schema:** Often missing -- capturing the FULL scoring state (all 4 factor scores, trailing stop levels, current prices) at each decision point. Without this, dry-run analysis is impossible. Verify: decision log has enough data to reconstruct WHY each decision was made.
- [ ] **WebSocket stream reconnect for new streams:** Often missing -- reconnect logic for depth20 and trade streams. Verify: depth20 stream recovers within 30 seconds after Binance maintenance.
- [ ] **XRPBTC lot isolation from Pairing system:** Often missing -- explicit exclusion of XRPBTC lots from EUR-pair pairing suggestions. Verify: `suggest_pairings()` filters by quote_asset or excludes XRPBTC symbol.
- [ ] **Backtest slippage modeling:** Often missing -- backtests assume perfect fills at exact prices. Verify: backtest engine applies configurable slippage (default: 0.05% BTCEUR, 0.15% XRPBTC).
- [ ] **ATR gap handling:** Often missing -- trailing stop behavior during WebSocket disconnect. Verify: trailing stop freezes during data gaps and resumes after reconnect + N fresh data points.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| XRPBTC lots with wrong EUR P&L | MEDIUM | 1. Write backfill script to populate `cost_eur` from historical BTC/EUR rates. 2. Recalculate all affected sell_allocations. 3. Alembic migration to add `quote_to_eur_rate` column. Existing scripts/backfill_cost_eur.py is a template. |
| WebSocket connection limit exceeded | LOW | 1. Consolidate into combined streams (config change + restart). 2. No data loss -- missed ticks do not affect persisted state. |
| Combined Score thresholds miscalibrated after Alpha integration | MEDIUM | 1. Revert to pre-Alpha weights (feature flag). 2. Run score distribution analysis on historical data. 3. Recalibrate thresholds in new deployment. |
| Rate limiting during backtest | LOW | 1. Cancel running backtest. 2. Wait for rate limit window to reset (60 seconds). 3. Add rate limiter to BinancePublicClient. 4. Re-run backtest. No state corruption. |
| Z-Score cold start produced false signals | HIGH if orders were placed | 1. If dry-run: simply discard first N minutes of signals. 2. If live: cancel any open orders placed during warmup period. 3. Add MIN_WINDOW_SIZE guard. Recovery cost is HIGH because false signals may have triggered real orders. |
| Dry-run data in production tables | HIGH | 1. Identify all records with `is_dry_run=TRUE`. 2. Delete from orders, sell_allocations, trade_lots (cascading). 3. Recalculate portfolio state from remaining ledger events. 4. This is why separate tables prevent the issue entirely. |
| Tick data blocking event loop | LOW | 1. Restart application. 2. Move tick processing to `asyncio.to_thread()`. 3. Add 1-second bar downsampling. No persistent state corruption. |
| ATR false exit during data gap | HIGH if position was closed | 1. Reconciliation will detect the unexpected sell. 2. If automated: order was real and cannot be undone (this is why dry-run mode exists). 3. Prevention is the ONLY viable strategy here. |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| XRPBTC quote-currency assumption | Phase 1 (XRPBTC Re-Addition) | Unit tests: XRPBTC lot break-even in EUR, portfolio aggregation with mixed EUR/BTC lots, Pairing exclusion |
| WebSocket connection explosion | Phase 2 (Multi-Factor Scoring) | `get_stats()` shows exactly 2 connections (1 combined public + 1 user data), stress test with all streams active |
| Combined Score weight rebalancing | Phase 4 (Combined Score Integration) | Score distribution comparison: histogram of old vs new scores over 30-day test data, threshold validation |
| Kline rate limiting for backtesting | Phase 3 (Backtesting Engine) | Backtest of 24 months / 3 symbols completes in < 60 seconds without any 429 errors in logs |
| Z-Score cold start | Phase 2 (Multi-Factor Scoring) | Test: Alpha Score returns null/warmup status with < MIN_WINDOW_SIZE data points, no extreme values during warmup |
| Dry-run state divergence | Phase 4 (Dry-Run Mode) | Verify: production `trade_lots` and `orders` tables have zero dry-run records after 24-hour dry-run test |
| ATR trailing false exits | Phase 3 (ATR-Adaptive Trailing) | Integration test: simulate 60-second WebSocket gap, verify trailing stop is frozen and no exit triggered |
| Tick data event loop blocking | Phase 2 (Multi-Factor Scoring) | Load test: inject 200 ticks/sec, verify price broadcast latency stays < 500ms and heartbeat never times out |

## Sources

- Codebase analysis: `backend/app/services/websocket_manager.py` (connection architecture, existing stream management)
- Codebase analysis: `backend/app/domain/combined_score.py` (hardcoded weights, threshold system, conflict detection)
- Codebase analysis: `backend/alembic/versions/094dac6f695a_remove_xrpbtc_cross_pair_columns.py` (exact columns dropped)
- Codebase analysis: `backend/app/symbol_registry.py` (current KNOWN_PAIRS, only 3 EUR pairs)
- Codebase analysis: `backend/app/services/sentiment_data_service.py` (cold-start initialization pattern, cache TTL design)
- Codebase analysis: `backend/app/utils/retry.py` (retry/backoff behavior, rate limit handling)
- Codebase analysis: `backend/app/db/database.py` (NullPool SQLite config, check_same_thread)
- Codebase analysis: `backend/app/services/websocket_fill_handler.py` (asyncio.to_thread pattern for DB ops)
- Codebase analysis: `backend/app/services/binance_public_client.py` (request infrastructure, timeout, CachedValue pattern)
- Binance API documentation (connection limits, stream formats, kline pagination) -- HIGH confidence based on training data, verified against codebase implementation patterns
- PROJECT.md v3.0 milestone scope (XRPBTC re-addition constraints, no cross-pair pairing)

---
*Pitfalls research for: v3.0 Multi-Factor Omni-Bot addition to BTC/EUR Cashflow-Management*
*Researched: 2026-02-25*
