# Project Research Summary

**Project:** Multi-Factor Omni-Bot (v3.0) — BTC/EUR Cashflow-Management App
**Domain:** Multi-factor crypto scoring engine with backtesting and dry-run mode
**Researched:** 2026-02-25
**Confidence:** HIGH (backend architecture), MEDIUM (WebSocket stream specifics, lead-lag behavior)

---

## Executive Summary

This milestone adds a multi-factor Alpha Scoring Engine to an existing, mature FastAPI + React codebase. The existing app is production-quality with a strict 3-layer architecture (Routes -> Services -> pure Domain), established patterns for singleton services with TTL caches, WebSocket stream management, and a Combined Score that fuses MacroSignal with Sentiment. The v3.0 Omni-Bot builds on this foundation by introducing four quantitative factors (Z-Score Mean Reversion, Lead-Lag Momentum, Orderbook Imbalance, Funding Rate) into an Alpha Score (-5 to +5), plus backtesting and dry-run mode. The key insight from research: almost every piece of infrastructure needed already exists — the work is extension and composition, not greenfield development.

The recommended approach is phased addition that respects the hard dependency graph: XRPBTC must be re-added first (it was removed in v2.0 and is required for Z-Score and Lead-Lag), then the scoring engine and data service, then backtesting, then dry-run and the Bot Dashboard, and finally Combined Score integration. One new backend dependency is warranted (numpy 2.2.6) for vectorized rolling-window math over 17k+ candles; everything else in the existing stack covers all needs. No new frontend dependencies are needed. The Decimal/numpy boundary pattern (Decimal in, numpy compute, Decimal out) preserves the project's financial precision invariant.

The three highest-risk areas are: (1) XRPBTC re-addition silently breaking EUR-denominated P&L calculations because the v2.0 migration stripped quote-currency abstraction infrastructure — this must be handled with a forward migration restoring `quote_to_eur_rate` before any scoring logic touches XRPBTC lots; (2) WebSocket connection explosion if depth20 and kline streams are added as separate connections rather than combined into the existing stream URL; and (3) the Combined Score weight rebalancing problem — adding Alpha Score as a third input shifts the score distribution and breaks users' calibrated mental model of thresholds, which argues for creating a standalone Bot Score rather than modifying the existing Combined Score.

---

## Key Findings

### Recommended Stack

The existing stack is sufficient for all v3.0 needs with one targeted addition. The project runs Python 3.13 + FastAPI 0.128.7 + SQLAlchemy 2.0.46 + React 19 + TanStack Query + Recharts + lightweight-charts. All of these are validated and working. The only justified new dependency is **numpy 2.2.6** for vectorized batch math in the backtesting engine — at 17,520 candles (24 months of 1h data) per symbol, pure Python with Decimal loops is 50-100x too slow for rolling Z-Score and Sharpe computation.

**Core technologies:**
- **numpy 2.2.6** — vectorized rolling Z-Score, Sharpe ratio, max drawdown, equity curve; the only new dependency; pandas and scipy are explicitly excluded (60-80 MB each, architectural mismatch with List[dataclass] pattern)
- **aiohttp 3.13.3** (existing) — extend BinanceStreamManager combined stream URL to include depth20@100ms and kline_1m; no new connection, no new library
- **SQLite + SQLAlchemy 2** (existing) — two new tables (DryRunLogDB, AlphaBacktestRunDB) follow the existing BacktestRunDB JSON-snapshot pattern; no new DB technology needed at this data volume (~4,320 signal rows/day)
- **Recharts 3.7.0** (existing) — equity curve (LineChart) and drawdown (AreaChart) use components already in use; no new charting library needed
- **Decimal/numpy boundary** — Decimal in, numpy float64 for batch ops, Decimal out; financial amounts (prices, quantities, P&L) never touch numpy

### Expected Features

**Must have (table stakes for v3.0):**
- XRPBTC symbol re-addition — hard prerequisite for Z-Score and Lead-Lag; was removed in v2.0 and must be re-added without restoring cross-pair pairing columns
- Z-Score Mean Reversion (Factor A, 40% weight) — core signal; 50-period rolling window on price ratio, contrarian scoring
- Lead-Lag Momentum (Factor B, 30%) — cross-correlation of BTC and XRP klines with lag detection at 1m/5m granularity
- Orderbook Imbalance from depth20 WebSocket (Factor C, 20%) — real-time bid/ask asymmetry; dramatically faster than the existing 1-min REST polling in SentimentDataService
- Funding Rate scoring adapted for Alpha Score range (Factor D, 10%) — reuses existing OKX data source, no new API credentials
- Alpha Score computation (-5 to +5, weighted, graceful degradation when factors unavailable)
- ATR-Adaptive Trailing stop engine — reuses existing `compute_atr()` from `domain/orderblock.py`
- Backtesting Engine — 24-month walk-forward simulation, Sharpe ratio, max drawdown, HODL benchmark, fee modeling
- Dry-Run Mode — real-time signals, decision logging in separate tables, virtual portfolio, zero real orders
- Decision logging with full factor context (append-only, all 4 scores captured per decision)
- Bot Dashboard — status card, current Alpha Score, signal history chart, virtual P&L display
- Combined Score integration — Alpha Score as optional third input
- Settings extension — alpha threshold, factor weights, trailing stop multipliers configurable per user

**Should have (add after v3.0 validation):**
- Tax simulation in backtesting — German 365-day holding rule, Abgeltungssteuer modeling (26.375%)
- Backtesting parameter sweep — grid search over Z-Score lookback, weights, thresholds with CSV export
- Signal correlation monitoring — factor agreement as confidence multiplier (reuses existing pillar dispersion pattern)
- Conviction-weighted position sizing — Alpha Score intensity modulates position size linearly

**Defer to v4+:**
- Live execution mode — requires circuit breakers, max daily loss limits, position size limits; explicitly out of scope per PROJECT.md
- Regime detection (ADX/Hurst) — high-complexity differentiator, defer until dry-run validation confirms base signal quality
- Multi-strategy profiles — single-user app does not need simultaneous configurations
- ML-based weight optimization — with 24 months of 4-factor data, will overfit; grid search is sufficient

### Architecture Approach

The new components follow the existing 3-layer architecture without exception. New domain modules (`alpha_score.py`, `trailing_exit.py`, `alpha_backtest.py`) are pure functions with zero I/O, following the `macro_signal.py` / `sentiment.py` pattern. New services (`AlphaDataService`, `AlphaBacktestService`, `DryRunService`) are singletons with threading.Lock and CachedValue TTL, following the `SentimentDataService` pattern exactly. New API routes are thin — `asyncio.wait_for(asyncio.to_thread(...), timeout=30)` — following `api/routes/combined.py`. The combined WebSocket stream is extended in-place (not replaced) by adding depth20@100ms and kline_1m to the existing combined stream URL. All new DB tables use the JSON-snapshot pattern established by `BacktestRunDB`.

**Major new components:**
1. `domain/alpha_score.py` — pure scoring: 4 factors to Alpha Score with renormalization on missing data
2. `domain/trailing_exit.py` — pure ATR-adaptive trailing stop (immutable state machine, new state per candle)
3. `domain/alpha_backtest.py` — walk-forward backtest engine with equity curve and Sharpe computation
4. `services/alpha_data_service.py` — singleton data provider; fetches klines + depth, reuses OKX funding
5. `services/dry_run_service.py` — async real-time signal logging loop; separate tables from production
6. `DryRunLogDB` / `AlphaBacktestRunDB` — new tables following existing JSON-snapshot pattern
7. `components/AlphaScore.jsx`, `Backtest.jsx`, `DryRunLog.jsx` — Bot nav group (4th section in frontend)

**Key constraint:** Dry-run mode uses completely separate DB tables and has no structural access to Binance API credentials. This is enforced by the service constructor not receiving credentials, not by a boolean flag.

### Critical Pitfalls

1. **XRPBTC quote-currency assumption** — The v2.0 migration (`094dac6f695a`) dropped `quote_to_eur_rate` from `trade_lots`. Without this column, XRPBTC lots show break-even in BTC terms (~0.00002) instead of EUR (~0.50), and P&L aggregation silently produces wrong totals. Avoid by creating a forward migration adding `quote_to_eur_rate` back and auditing every domain function that reads `cost_quote` for EUR assumptions. XRPBTC lots must be explicitly excluded from EUR-pair Pairing suggestions.

2. **WebSocket connection explosion** — Binance enforces a 5-connection-per-IP limit. The current architecture uses 2 connections (ticker + user data). Adding depth20 and kline streams as separate connections hits the limit immediately. Avoid by extending the existing combined stream URL: all public data (ticker + depth20 + kline_1m for all symbols) in one combined connection, leaving the user data stream as the only second connection.

3. **Z-Score cold start produces false signals** — When the 50-period rolling window is incomplete on startup, Z-Score returns extreme values (+50 or -50), triggering maximum-confidence signals on near-random data. Avoid by defining `MIN_WINDOW_SIZE` (return `None` below threshold), pre-loading 60 minutes of klines on startup, and exposing a `warmup` status flag in the API response. The UI must show "Warming up" instead of displaying unreliable scores. Cold-start tests with 0, 5, 29, 30, and 50 data points are required.

4. **Dry-run state divergence from production** — Adding `is_dry_run=TRUE` to production `orders` or `trade_lots` tables contaminates every production query that omits the filter. Avoid by using completely separate tables (`dry_run_decisions`, `dry_run_positions`) with no structural overlap with the real ledger. Dry-run P&L must appear only on the Bot Dashboard, never on the main Dashboard.

5. **Combined Score weight rebalancing** — Changing MacroSignal/Sentiment weights to accommodate Alpha Score shifts the Unified Score distribution, making previously reliable action thresholds wrong. Avoid by treating Alpha Score as a bounded modulating factor (+-15 point adjustment on existing score) or creating a separate "Bot Score" that leaves the existing Combined Score intact. A score distribution comparison (histogram of old vs. new over 30-day test data) is required before deployment.

---

## Implications for Roadmap

Based on the feature dependency graph, architecture constraints, and pitfall-to-phase mapping from research, the following phase structure is recommended:

### Phase 1: XRPBTC Re-Addition

**Rationale:** Hard prerequisite — Z-Score needs XRPBTC ratio data, Lead-Lag needs XRPBTC klines, and the quote-currency bug (Pitfall 1) must be resolved before any scoring logic touches XRPBTC. If deferred, all downstream phases produce wrong P&L data silently. This phase is low complexity (the symbol registry and sync patterns are well-known) but has the highest correctness risk if skipped.
**Delivers:** XRPBTC in Symbol Registry, `quote_to_eur_rate` forward migration on `trade_lots`, EUR-denominated P&L for XRPBTC lots, Pairing system isolation (XRPBTC lots excluded from EUR-pair suggestions), Binance Sync support for XRPBTC fills
**Addresses:** XRPBTC re-addition (FEATURES.md P1), symbol registry extension, sync service extension, Max Order Value check extended to convert XRPBTC order value to EUR before validation
**Avoids:** Pitfall 1 (quote-currency EUR assumption), Pitfall XRPBTC lot leaking into EUR-pair pairing
**Research flag:** LOW — pattern is well-known; removed column names are documented exactly in `094dac6f695a_remove_xrpbtc_cross_pair_columns.py`

### Phase 2: Multi-Factor Scoring Engine

**Rationale:** The four factors are the core of the milestone. They are independent of each other and can be built in parallel within the phase, converging at Alpha Score computation. The WebSocket stream extension (depth20 + kline_1m) and cold-start handling must be built here — both are significantly harder to retrofit than to build correctly from the start.
**Delivers:** `domain/alpha_score.py`, `domain/trailing_exit.py`, `services/alpha_data_service.py`, `api/routes/alpha.py`, numpy integration with Decimal boundary pattern, extended BinanceStreamManager combined stream URL, warmup status in API responses, Settings extension for alpha threshold and weights
**Uses:** numpy 2.2.6 (one new dependency), existing BinancePublicClient, existing SentimentDataService OKX funding rate, existing `compute_atr()` from `domain/orderblock.py`
**Implements:** Domain layer alpha scoring, service layer data provider, alpha score API endpoint, extended WebSocket stream
**Avoids:** Pitfall 2 (WebSocket connection explosion — combined stream URL from day one), Pitfall 5 (Z-Score cold start — MIN_WINDOW_SIZE guard and warmup flag), Pitfall 8 (tick data blocks event loop — tick processing via asyncio.Queue, not inline handler)
**Research flag:** MEDIUM — Z-Score rolling window initialization and Lead-Lag cross-correlation lag detection have subtle edge cases with synchronized timestamps across symbols; Binance stream format names for depth20@100ms and kline_1m need verification against current API docs before implementation

### Phase 3: Backtesting Engine

**Rationale:** Backtesting validates the scoring engine parameters before dry-run mode is built. Running backtest before dry-run is the correct order — it reveals parameter problems (threshold too aggressive, trailing stop too tight) that would make dry-run misleading if discovered only later. The HODL benchmark and Sharpe ratio are the primary trust-building metrics.
**Delivers:** `domain/alpha_backtest.py`, `services/alpha_backtest_service.py`, `api/routes/backtest.py`, `AlphaBacktestRunDB` table, equity curve and drawdown curves, HODL benchmark, 24-month historical kline fetching with centralized rate limiting, slippage modeling (0.05% BTCEUR, 0.15% XRPBTC)
**Uses:** numpy (vectorized equity curve, Sharpe, max drawdown), existing paginated kline fetcher from `orderblock_data_service.py`, existing BacktestRunDB JSON-snapshot pattern
**Avoids:** Pitfall 3 (ATR trailing false exits — REST fallback for ATR after WebSocket reconnect, gap-freeze logic built here), Pitfall 4 (rate limiting during historical data fetch — centralized token-bucket rate limiter in BinancePublicClient, 50-100ms inter-request delay)
**Research flag:** LOW — walk-forward backtest structure is proven by the existing `orderblock_backtest.py` template; numpy Sharpe and max drawdown are single-line vectorized operations with no ambiguity

### Phase 4: Dry-Run Mode + Bot Dashboard

**Rationale:** Dry-run requires a working Alpha Score (Phase 2) and validated parameters from backtesting (Phase 3). The Bot Dashboard brings all signals together in a single new nav section. This phase is the trust-building step before any future live execution work — users must observe the signal behavior in paper trading before any capital risk.
**Delivers:** `services/dry_run_service.py` with structural separation from production (no Binance credentials in constructor), `DryRunLogDB` table capturing full scoring state at each decision, virtual portfolio tracking, Bot Dashboard (4th nav section) with AlphaScore.jsx + DryRunLog.jsx + Backtest.jsx, clear dry-run mode indicator (distinct color scheme, "SIMULATION" watermark)
**Avoids:** Pitfall 6 (dry-run state divergence — separate tables enforced structurally, DryRunService has no Binance credentials), ATR gap handling via frozen trailing stop during WebSocket disconnect (data quality flag: ACTIVE / FROZEN / RECALIBRATING)
**Research flag:** LOW for dry-run separation architecture (design decision is clear, no ambiguous patterns). MEDIUM for Bot Dashboard frontend (3 new components plus nav restructure introduces regression risk in existing components).

### Phase 5: Combined Score Integration

**Rationale:** Alpha Score integration into Combined Score is deliberately last. The existing Combined Score is user-facing and calibrated — changing its weights affects every user's mental model of the action thresholds. By doing this last, the Alpha Score has been validated through backtesting and dry-run before modifying a production-facing signal.
**Delivers:** Modified `domain/combined_score.py` accepting optional `AlphaInput` as third signal (backward-compatible), extended conflict detection for 3-way signal divergence, modified `CombinedScore.jsx` showing alpha as third sub-signal card, score distribution analysis validating threshold calibration
**Avoids:** Pitfall 3 (Combined Score weight rebalancing) — the research recommends treating Alpha Score as a bounded modulating factor (+-15 points) rather than changing existing weights; score distribution comparison over 30-day test data is required before deployment
**Research flag:** MEDIUM — the interaction between any weight changes and the 7-level action threshold system requires empirical validation with historical data; cannot be fully resolved through design alone

### Phase Ordering Rationale

- **Phase 1 must be first** — XRPBTC is a hard data dependency for Phases 2 and 3; the quote-currency bug would silently corrupt financial calculations in all later phases without any error signal
- **Phase 2 before Phase 3** — the backtesting engine simulates the same scoring logic used in real-time; building the scorer first ensures the backtest validates the real implementation rather than a separate reference implementation
- **Phase 3 before Phase 4** — dry-run with unvalidated parameters produces misleading results; backtesting should surface parameter problems before they pollute the dry-run log
- **Phase 5 is last** — Combined Score integration modifies a user-facing calibrated system; delaying it until Alpha Score is validated through phases 2-4 protects existing user trust in the Combined Score widget
- **Parallelism within Phase 2** — the four factors (Z-Score, Lead-Lag, Orderbook Imbalance, Funding Rate) are mutually independent and can be built concurrently, converging only at `compute_alpha_score()`

### Research Flags

Phases needing deeper research during planning:
- **Phase 2 (Scoring Engine):** Z-Score cold start initialization with synchronized timestamps across BTCEUR and XRPBTC windows; Binance stream format verification for `@depth20@100ms` and `@kline_1m` against current API documentation (research used training-data knowledge, not live API verification) — verify before writing BinanceStreamManager extension
- **Phase 5 (Combined Score Integration):** Score distribution shift analysis requires historical signal data to validate threshold calibration; cannot be designed without empirical data from Phase 2-4 operation

Phases with standard patterns (skip research-phase):
- **Phase 1 (XRPBTC):** Symbol registry pattern, Alembic forward migration, and sync extension are all well-established in the codebase; removed column names documented exactly in the Alembic version file
- **Phase 3 (Backtesting):** Walk-forward backtest engine follows the existing `orderblock_backtest.py` structural template; numpy Sharpe and drawdown are single-function computations
- **Phase 4 (Dry-Run):** Architectural separation of dry-run from production ledger is a clear design decision with no domain-specific unknowns

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All existing technologies verified against working codebase. numpy 2.2.6 verified available in project venv. Exclusion of pandas/scipy is well-reasoned (architectural mismatch, no benefit at this scale). Recharts and lightweight-charts cover all visualization needs without new dependencies. |
| Features | MEDIUM | Core features (Z-Score, backtesting, dry-run) are well-established quantitative finance patterns with strong academic foundation. Lead-lag lag detection specifics (5-30 minute typical lag for XRP/BTC) are from training data, not live market observation. German tax simulation rates need verification before shipping. |
| Architecture | HIGH | Based on direct inspection of 20+ source files. All integration patterns verified against working code. New component boundaries follow exact existing patterns (SentimentDataService, MacroSignal, CombinedScore). Component inventory and modification surface are precisely mapped. |
| Pitfalls | HIGH | All 8 pitfalls identified from direct codebase analysis — specific migration file names (`094dac6f695a`), exact column names (`quote_to_eur_rate`), real code paths (BinanceStreamManager connection architecture). The 5-connection Binance limit and XRPBTC column removal are verified facts, not inferred risks. |

**Overall confidence:** HIGH

### Gaps to Address

- **Binance stream format verification:** The depth20@100ms and kline_1m stream formats are from training data knowledge of the Binance API. Verify against current Binance API documentation before Phase 2 implementation. Fallback: `@depth20@1000ms` (1-second updates) if 100ms proves problematic in practice.
- **Lead-lag lag window tuning:** The 1-5 candle lag window for BTC->XRP momentum is a research finding, not a calibrated constant for this specific symbol pair. The backtesting parameter sweep (v3.x) should validate the optimal window. For initial Phase 2 implementation, 5 candles at 1m granularity is a reasonable starting point.
- **German tax rates:** The 26.375% Abgeltungssteuer + Soli rate cited in research should be verified before implementing the tax simulation feature (v3.x scope, not v3.0).
- **XRPBTC liquidity characteristics:** XRPBTC daily volume on Binance is approximately 50x lower than BTCEUR. The wider slippage estimates (0.15% vs 0.05%) used in backtesting should be validated against actual market depth before any live execution considerations arise.

---

## Sources

### Primary (HIGH confidence)

- Codebase analysis: `backend/app/services/websocket_manager.py`, `backend/app/domain/macro_signal.py`, `backend/app/domain/sentiment.py`, `backend/app/domain/combined_score.py`, `backend/app/services/combined_score_service.py`, `backend/app/services/sentiment_data_service.py`, `backend/app/services/binance_public_client.py`, `backend/app/domain/orderblock_backtest.py`, `backend/alembic/versions/094dac6f695a_remove_xrpbtc_cross_pair_columns.py`, `backend/app/db/models.py` — all patterns verified by direct inspection of source files
- Python 3.13 `statistics` module — runtime verified: `mean`, `stdev`, `NormalDist`, `correlation`, `linear_regression`, `quantiles` all present; scipy excluded on this basis
- numpy 2.2.6 — verified available via `pip index versions numpy` in project venv

### Secondary (MEDIUM confidence)

- Z-Score mean reversion: Gatev, Goetzmann, Rouwenhorst (2006) "Pairs Trading: Performance of a Relative Value Arbitrage Rule" — established academic foundation for pairs signal
- Pairs trading statistical framework: Vidyamurthy (2004) "Pairs Trading: Quantitative Methods and Analysis"
- ATR trailing stops: Wilder (1978) "New Concepts in Technical Trading Systems" — foundational; ATR already implemented in codebase
- Orderbook imbalance as signal: Cont, Stoikov, Talreja (2010) "A Stochastic Model for Order Book Dynamics"
- Binance WebSocket stream formats (`@depth20@100ms`, `@kline_1m`) — training data knowledge of Binance API; verify against official docs before implementation
- Lead-lag characteristics (5-30 minute BTC->altcoin lag) — crypto market microstructure literature consensus; specific timing varies by market regime

### Tertiary (LOW confidence)

- German crypto tax rates (26.375% Abgeltungssteuer + Soli) — verify before implementing tax simulation; rates may have changed since knowledge cutoff
- XRPBTC volume characteristics (~50x lower than BTCEUR) — rough estimate from training data; verify with current Binance exchange data before using slippage assumptions in live execution

---

*Research completed: 2026-02-25*
*Ready for roadmap: yes*
