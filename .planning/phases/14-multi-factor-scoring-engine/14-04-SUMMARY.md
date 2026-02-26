---
phase: 14-multi-factor-scoring-engine
plan: 04
subsystem: api
tags: [alpha-score, data-service, singleton, ttl-cache, api-routes, trailing-stop, ema, okx-funding]

# Dependency graph
requires:
  - phase: 14-multi-factor-scoring-engine
    plan: 01
    provides: "4 factor computation functions and AlphaFactorScore dataclass"
  - phase: 14-multi-factor-scoring-engine
    plan: 02
    provides: "14 alpha_score_* settings columns and Settings API validation"
  - phase: 14-multi-factor-scoring-engine
    plan: 03
    provides: "Hurst R/S, regime-adjusted weights, Alpha Score aggregation, trailing stops"
provides:
  - "AlphaScoreDataService singleton with TTL-cached multi-source data fetching"
  - "GET /api/alpha-score/{user_id}/score endpoint with factor breakdown and regime info"
  - "GET /api/alpha-score/{user_id}/trailing-stops endpoint with freeze/resume state"
  - "EMA-smoothed orderbook imbalance (alpha=0.4, 5-snapshot history)"
  - "Portfolio-aware trailing stop tightening (correlation > 0.7 triggers up to 15% ATR reduction)"
affects: [16-bot-dashboard-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [mixed-refresh-cadence, ema-smoothed-orderbook, portfolio-correlation-stop-tightening]

key-files:
  created:
    - backend/app/services/alpha_score_data_service.py
    - backend/app/api/routes/alpha_score.py
  modified:
    - backend/app/main.py

key-decisions:
  - "Own OKX funding rate cache (not shared with SentimentDataService) to avoid cross-service coupling"
  - "EMA-smoothed orderbook imbalance with alpha=0.4 over 5 snapshots to reduce noise from point-in-time depth snapshots"
  - "Portfolio correlation tightening formula: when corr > 0.7, ATR distance *= 1 - (corr - 0.7) * 0.5 (max 15% reduction)"
  - "XRPEUR trailing stop computed from XRPBTC ATR * BTCEUR price (no direct XRPEUR klines needed)"

patterns-established:
  - "Mixed refresh cadence: candle-driven data uses interval TTL, real-time data (orderbook 30s, funding 15min) independent"
  - "EMA smoothing pattern for noisy orderbook data: store N ratios in deque, compute EMA, override domain function output"
  - "Portfolio-aware stop tightening: rolling correlation between BTC and XRP returns drives ATR multiplier reduction"

requirements-completed: [SCORE-07, SCORE-08]

# Metrics
duration: 5min
completed: 2026-02-26
---

# Phase 14 Plan 04: Alpha Score Data Service + API Routes Summary

**AlphaScoreDataService singleton with mixed TTL caching, EMA-smoothed orderbook, portfolio-aware trailing stops, and two API endpoints for score/trailing-stop queries**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-26T05:54:16Z
- **Completed:** 2026-02-26T05:58:54Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments
- AlphaScoreDataService singleton bridges pure domain functions with real Binance/OKX data sources
- Mixed refresh cadences: candle-driven factors (Z-Score, Lead-Lag, Hurst) use interval TTL, real-time factors (Orderbook 30s, Funding 15min) update independently
- EMA-smoothed orderbook imbalance reduces noise from volatile depth snapshots (alpha=0.4, 5-snapshot rolling deque)
- Portfolio-aware trailing stop tightening when BTC/XRP correlation exceeds 0.7 (max 15% ATR distance reduction)
- Warmup detection returns explicit status (never partial scores from insufficient data)
- Graceful degradation: failed data sources get quality="unavailable", weights renormalized across available factors
- Two API endpoints: GET /score (full Alpha Score with factor breakdown) and GET /trailing-stops (per-symbol stop levels with freeze state)
- All 734 existing tests pass without regression

## Task Commits

Each task was committed atomically:

1. **Task 1: AlphaScoreDataService singleton** - `d4794b8` (feat) - Singleton with TTL cache, mixed refresh, EMA orderbook, trailing stops, warmup, degradation
2. **Task 2: API routes + main.py** - `225a43b` (feat) - Two API endpoints, route registration with API-key auth
3. **Formatting** - `75e04b6` (chore) - Black formatting applied to data service

## Files Created/Modified
- `backend/app/services/alpha_score_data_service.py` - Singleton data service: TTL-cached klines/orderbook/funding, EMA smoothing, trailing stop state, portfolio correlation, warmup detection, serialization (523 lines)
- `backend/app/api/routes/alpha_score.py` - Two API routes: GET /score and GET /trailing-stops, asyncio.to_thread, settings loading, error handling (105 lines)
- `backend/app/main.py` - Added alpha_score import and router registration with api_auth dependency

## Decisions Made
- Own OKX funding rate fetch rather than reusing SentimentDataService -- avoids cross-service coupling, each service owns its cache (per research anti-pattern guidance)
- EMA smoothing for orderbook: compute raw imbalance ratio, store in deque, apply EMA, then override domain function's sub_score with smoothed value. This avoids modifying the pure domain function.
- XRPEUR trailing stop computed from XRPBTC kline ATR converted to EUR via BTCEUR close price, avoiding extra API call for XRPEUR klines
- Portfolio correlation uses same Lead-Lag window for rolling Pearson correlation between BTC and XRP returns

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Alpha Score engine fully functional: domain (Plans 01+03), settings (Plan 02), data service + API (Plan 04)
- Phase 14 complete -- all 4 plans executed, all requirements met (SCORE-01 through SCORE-09, EXIT-01, EXIT-02)
- Ready for Phase 15 (Alpha Score Backtesting) and Phase 16 (Bot Dashboard UI)

## Self-Check: PASSED

- FOUND: backend/app/services/alpha_score_data_service.py
- FOUND: backend/app/api/routes/alpha_score.py
- FOUND: d4794b8 (Task 1 commit)
- FOUND: 225a43b (Task 2 commit)
- FOUND: 75e04b6 (formatting commit)

---
*Phase: 14-multi-factor-scoring-engine*
*Completed: 2026-02-26*
