# Requirements: BTC/EUR Cashflow-Management — v3.0 Multi-Factor Omni-Bot

**Defined:** 2026-02-25
**Core Value:** Ledger-first, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System

## v3.0 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### XRPBTC Infrastructure

- [x] **INFRA-01**: User can see XRPBTC as available trading pair in Symbol Registry and frontend symbol selector
- [x] **INFRA-02**: User can sync XRPBTC fills from Binance and create lots from them
- [x] **INFRA-03**: XRPBTC lots display correct EUR-denominated break-even and P&L (via historical BTC/EUR rate at fill time)
- [x] **INFRA-04**: XRPBTC lots are excluded from EUR-pair pairing suggestions (no cross-pair pairing)

### Scoring Engine

- [x] **SCORE-01**: System computes Z-Score Mean Reversion on XRP/BTC ratio with configurable rolling window (default 60 periods)
- [x] **SCORE-02**: System computes Lead-Lag Momentum by detecting BTC price movements that XRP has not yet followed (cross-correlation with rolling window)
- [x] **SCORE-03**: System computes Orderbook Imbalance from Binance depth data (bid/ask volume differential within 1% of mid-price)
- [x] **SCORE-04**: System computes Funding Rate score from existing OKX data (reuses SentimentDataService cache)
- [ ] **SCORE-05**: System computes Global Alpha Score (-5 to +5) as weighted sum of 4 factors (Z-Score 40%, Lead-Lag 30%, Imbalance 20%, Funding 10%)
- [ ] **SCORE-06**: User can configure Alpha Score weights and trade threshold (default ±3.0) via Settings
- [x] **SCORE-07**: Alpha Score gracefully degrades when data sources are unavailable (partial score with quality indicator)
- [x] **SCORE-08**: Alpha Score returns warmup status during cold start (MIN_WINDOW_SIZE guard, no extreme values)
- [ ] **SCORE-09**: System detects market regime (trending vs mean-reverting) and adjusts Z-Score factor weight accordingly

### Exit Management

- [ ] **EXIT-01**: System computes ATR-Adaptive Trailing stop distances (ATR×2 for BTC, ATR×3 for XRP, configurable multipliers)
- [ ] **EXIT-02**: Trailing stops freeze during data gaps (WebSocket disconnect) and resume after N consecutive fresh data points

### Backtesting

- [x] **BT-01**: User can run backtests over configurable time period (up to 24 months) for any supported symbol
- [x] **BT-02**: Backtest computes performance metrics: net return, Sharpe ratio, max drawdown, trade count, win rate
- [x] **BT-03**: Backtest compares results against buy-and-hold benchmark (50/50 BTC/XRP HODL)
- [x] **BT-04**: Backtest includes realistic transaction costs (configurable fee rate, slippage modeling)
- [x] **BT-05**: Backtest results are persisted as immutable snapshots (config + metrics + trades)
- [x] **BT-06**: User can view backtest history with expandable run details
- [x] **BT-07**: User can run parameter sweep (grid search over Z-Score lookback, weights, thresholds) with CSV export

### Dry-Run Mode

- [x] **DRY-01**: User can activate dry-run mode that computes real-time signals without placing actual orders
- [x] **DRY-02**: Dry-run logs every decision with full context (all 4 factor scores, Alpha Score, trailing stop levels, prices, action, reason)
- [x] **DRY-03**: Dry-run tracks virtual portfolio (positions, P&L) in separate tables from production ledger
- [x] **DRY-04**: User can view dry-run decision log with filtering (date range, action type, symbol)
- [x] **DRY-05**: Dry-run mode has NO access to order-placing functionality (structural prevention, not flag-based)

### Combined Score Integration

- [x] **COMB-01**: Alpha Score feeds into Combined Score as optional 3rd signal (backward-compatible: when unavailable, existing 60/40 weights unchanged)
- [x] **COMB-02**: Combined Score dashboard shows Alpha Score contribution when available (factor breakdown in details)

### Bot Dashboard

- [x] **BOT-01**: New "Bot" section in navigation (4th area: Trading/Analyse/Bot/Admin)
- [x] **BOT-02**: Bot dashboard shows current Alpha Score with factor breakdown (visual bars per factor)
- [x] **BOT-03**: Bot dashboard shows signal history (recent Alpha Score values over time, chart)
- [x] **BOT-04**: Bot dashboard shows dry-run status (active/inactive, current virtual positions, virtual P&L)
- [x] **BOT-05**: Bot dashboard shows backtest results (most recent run summary, link to full history)
- [x] **BOT-06**: Bot dashboard shows regime indicator (trending/mean-reverting with confidence)

## Future Requirements

Deferred to follow-up milestones. Tracked but not in current roadmap.

### Live Execution

- **EXEC-01**: System places real Binance orders based on Alpha Score signals
- **EXEC-02**: Circuit breakers (max daily loss, max position size, kill switch)
- **EXEC-03**: Order execution with existing TAKE_PROFIT_LIMIT pattern

### Tax Optimization

- **TAX-01**: German 365-day holding period check before automated sells
- **TAX-02**: Tax simulation in backtesting (26.375% Abgeltungssteuer + Soli)
- **TAX-03**: Tax-free gain tracking per lot

### Advanced Features

- **ADV-01**: Conviction-weighted position sizing (Alpha Score intensity modulates size)
- **ADV-02**: Signal correlation monitoring (factor agreement as confidence multiplier)
- **ADV-03**: Telegram/Discord notifications for signal events

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Live order execution | Requires hardening milestone (circuit breakers, max loss limits). Ship dry-run first. |
| Machine learning optimization | Overfits on 24-month dataset. Grid search sufficient at this data scale. |
| Sub-second signal computation | 0.1% maker/taker fees make sub-second timing negligible. 1-5s refresh sufficient. |
| Multiple strategy profiles | Single-user app, one active config. Backtest sweep for comparison. |
| Auto-adjusting factor weights | Online learning is unstable in financial markets. Manual tuning via Settings. |
| Cross-pair pairing for XRPBTC | Removed in v2.0, complexity not justified for analysis-only re-addition. |
| Tax simulation in v3.0 | Deferred to live execution milestone where tax compliance is critical. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 13 | Complete |
| INFRA-02 | Phase 13 | Complete |
| INFRA-03 | Phase 13 | Complete |
| INFRA-04 | Phase 13 | Complete |
| SCORE-01 | Phase 14 | Complete |
| SCORE-02 | Phase 14 | Complete |
| SCORE-03 | Phase 14 | Complete |
| SCORE-04 | Phase 14 | Complete |
| SCORE-05 | Phase 14 | Pending |
| SCORE-06 | Phase 14 | Pending |
| SCORE-07 | Phase 14 | Complete |
| SCORE-08 | Phase 14 | Complete |
| SCORE-09 | Phase 14 | Pending |
| EXIT-01 | Phase 14 | Pending |
| EXIT-02 | Phase 14 | Pending |
| BT-01 | Phase 15 | Complete |
| BT-02 | Phase 15 | Complete |
| BT-03 | Phase 15 | Complete |
| BT-04 | Phase 15 | Complete |
| BT-05 | Phase 15 | Complete |
| BT-06 | Phase 15 | Complete |
| BT-07 | Phase 15 | Complete |
| DRY-01 | Phase 16 | Complete |
| DRY-02 | Phase 16 | Complete |
| DRY-03 | Phase 16 | Complete |
| DRY-04 | Phase 16 | Complete |
| DRY-05 | Phase 16 | Complete |
| BOT-01 | Phase 16 | Complete |
| BOT-02 | Phase 16 | Complete |
| BOT-03 | Phase 16 | Complete |
| BOT-04 | Phase 16 | Complete |
| BOT-05 | Phase 16 | Complete |
| BOT-06 | Phase 16 | Complete |
| COMB-01 | Phase 17 | Complete |
| COMB-02 | Phase 17 | Complete |

**Coverage:**
- v3.0 requirements: 35 total
- Mapped to phases: 35
- Unmapped: 0

---
*Requirements defined: 2026-02-25*
*Last updated: 2026-02-25 after roadmap creation (traceability populated)*
