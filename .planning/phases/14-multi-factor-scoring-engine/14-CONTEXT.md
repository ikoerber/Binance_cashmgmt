# Phase 14: Multi-Factor Scoring Engine - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Real-time Alpha Score (-5 to +5) composed of four independent quantitative factors (Z-Score Mean Reversion, Lead-Lag Momentum, Orderbook Imbalance, Funding Rate) plus ATR-adaptive trailing stop levels. Backend computation engine with API endpoint. Bot Dashboard UI is Phase 16.

</domain>

<decisions>
## Implementation Decisions

### Signal Timeframe & Refresh
- Default candle interval: 15m (configurable: 5m/15m/1h in Settings)
- Z-Score and Lead-Lag refresh on candle close (15m cadence)
- Orderbook Imbalance and Funding Rate refresh independently between candle closes (more responsive)
- Mixed refresh model: candle-driven factors are synchronized, real-time factors update independently

### Regime Detection
- Method: Hurst exponent via Rescaled Range (R/S) Analysis
- Lookback window: 100-200 candles (15m)
- Thresholds: H > 0.55 = trending (reduce Z-Score weight progressively), H < 0.45 = mean-reverting (Z-Score gets full 40% weight), 0.45-0.55 = transitional (gradual blend)
- Effect: Gradual weight blend (not binary switch) — Z-Score weight scales down smoothly as H increases above 0.55
- Freed weight redistribution: Lead-Lag 60%, Imbalance 30%, Funding 10% of freed Z-Score weight
- Regime indicator visible in API response (label + Hurst value + confidence)

### Settings & Configurability
- Grouped layout: essential settings visible by default, advanced section collapsed
- Essential settings: factor weights (4), trade threshold (±3.0), candle interval (5m/15m/1h)
- Advanced settings (collapsed): rolling windows (Z-Score, Lead-Lag), ATR multipliers, Hurst lookback, regime thresholds, trailing stop resume threshold
- Changes take effect immediately on save (next score computation), consistent with existing Settings behavior
- "Reset to defaults" button for all Alpha Score settings
- Weight normalization: Claude's discretion on whether to enforce sum-to-100% or auto-normalize arbitrary values

### Trailing Stop Semantics
- Hybrid model: trailing ratchet (only moves in favorable direction) + ATR floor (never closer than ATR × multiplier)
- Per-symbol ATR multipliers: ATR×2 for BTC, ATR×3 for XRP (configurable in Settings)
- Portfolio-aware: combined BTC + XRP exposure considered for stop tightening when both positions are correlated
- Freeze during data gaps (WebSocket disconnect): stops hold last known value
- Resume after N consecutive fresh data points (configurable in Settings, default 5)
- Frozen state explicitly visible in API: `frozen: true`, `frozen_since: timestamp`, `data_points_needed: N`

### Claude's Discretion
- Orderbook Imbalance data source approach (snapshot frequency vs rolling average)
- Weight input UX (enforce sum-to-100% vs auto-normalize)
- Internal caching strategy for factor computations
- API endpoint structure and response shape
- Exact Hurst exponent implementation details within R/S framework

</decisions>

<specifics>
## Specific Ideas

- Hurst exponent implementation should use Rescaled Range (R/S) Analysis specifically (not DFA or other methods)
- Regime redistribution ratios are intentional: Lead-Lag 60% (main trend factor), Imbalance 30% (trend quality validation), Funding 10% (overheating protection) — maintains balanced risk profile even in full trend mode
- User wants to see performance curve and tax implications once backtesting is available (Phase 15 + deferred tax milestone)

</specifics>

<deferred>
## Deferred Ideas

- Backtesting with performance curves — Phase 15
- Tax simulation (26.375% Abgeltungssteuer + Soli) — deferred to live execution milestone (explicitly out of scope for v3.0)
- Conviction-weighted position sizing based on Alpha Score intensity — future milestone (ADV-01)

</deferred>

---

*Phase: 14-multi-factor-scoring-engine*
*Context gathered: 2026-02-25*
