# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v3.0 — Multi-Factor Omni-Bot

**Shipped:** 2026-02-28
**Phases:** 6 (13-18) | **Plans:** 17 | **Commits:** 66
**Requirements:** 35/35 satisfied

### What Was Built
- Multi-factor Alpha Score engine with 4 quantitative factors, regime detection (Hurst exponent), and ATR-adaptive trailing stops
- Walk-forward backtesting engine with 24-month simulation, Sharpe/drawdown metrics, HODL benchmark, parameter sweep with CSV export
- Real-time dry-run paper trading with wall-clock-aligned evaluation loop, structural isolation from production orders (DRY-05)
- Bot Dashboard with Alpha Score hero, signal history chart, factor bars, regime badge, trailing stop display with freeze state, and dry-run controls
- Decision Log with filterable table, expandable factor detail rows, and pagination
- Combined Score integration with Alpha Score as backward-compatible third signal (50/30/20 weights, 60/40 fallback)
- XRPBTC re-addition with EUR-denominated P&L via historical BTC/EUR conversion

### What Worked
- TDD approach for domain-heavy plans (14-01, 14-03, 15-01, 17-01) caught design issues early and ensured backward compatibility
- Wave-based execution with sequential dependencies kept phases clean — each wave built on verified output from the previous
- Structural isolation for dry-run (import-level prohibition, not flags) provided strong safety guarantees verified automatically
- Research phase before planning consistently identified critical patterns (e.g., Hurst exponent for regime, Bouchaud square root law pitfall avoidance)
- Milestone audit caught 4 real integration bugs (field name mismatches, envelope shape, orphaned endpoint) that phase-level verifiers missed — cross-phase integration checking is essential
- Gap closure cycle (audit → plan → execute → verify) completed in a single session with zero manual intervention

### What Was Inefficient
- 5 requirement traceability checkboxes (SCORE-05/06/09, EXIT-01/02) were stale after Phase 14 execution — traceability updates should be atomic with phase completion
- Phase 17 had no CONTEXT.md (discuss-phase was skipped) — this worked for a small scope but would risk misalignment on larger phases
- SUMMARY.md one-liner extraction via `summary-extract` returned N/A for all files — tool may need format standardization
- v3.0 phase-level verifiers all passed, yet milestone audit found 4 integration gaps — verifiers checked code structure but not runtime API response shapes. Future verifiers should validate API response fields match frontend consumption.
- Milestone initially marked complete (v3.0 shipped 2026-02-27) before audit discovered gaps — audit should be mandatory gate before completion

### Patterns Established
- **DRY-05 pattern**: Structural isolation via import prohibition is more reliable than runtime flags for safety-critical boundaries
- **Wall-clock evaluation loop**: `asyncio.sleep` to next interval boundary instead of fixed sleep — prevents drift and enables idempotent restart
- **AlphaInput optional parameter pattern**: Extending `compute_combined_score(direction, sizing, alpha=None)` preserves backward compatibility while enabling new signals
- **4-group navigation**: Trading/Analyse/Bot/Admin provides clear mental model for feature categorization
- **Milestone audit as quality gate**: Cross-phase integration checking catches field-name/shape mismatches invisible to per-phase verifiers

### Key Lessons
1. Domain-heavy phases (scoring, backtesting) benefit most from TDD — the RED/GREEN cycle catches edge cases that pure execute plans miss
2. Backward compatibility tests should be written first (before any new code) to lock in existing behavior
3. Phase research consistently pays off — it surfaces architectural decisions (e.g., regime detection, trailing stop state machine) that would be expensive to discover during execution
4. Traceability tables need automated updates tied to phase completion, not manual maintenance
5. Milestone audit is not optional — v3.0 would have shipped with 4 broken frontend integrations without it. API response shapes must be validated against consumers, not just code structure.

### Cost Observations
- Model mix: ~70% opus (executors), ~25% sonnet (verifiers, checkers), ~5% haiku
- v3.0 completed in 4 calendar days (2026-02-25 to 2026-02-28), including gap closure
- Notable: Phases 16 and 17 were planned and executed in single sessions each — context window management via wave-based subagents kept orchestrator lean
- Gap closure (Phase 18): 2 tasks, 3 commits, ~5min total execution — minimal overhead for catching 4 real bugs

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 4 | 8 | Established GSD workflow, wave-based execution |
| v1.1 | 4 | 9 | API hardening patterns, reconciliation automation |
| v2.0 | 4 | 12 | CSS variable foundation, dark mode, nav restructure |
| v3.0 | 6 | 17 | TDD for domain-heavy plans, structural isolation, regime detection, milestone audit as quality gate |

### Cumulative Quality

| Milestone | Backend Tests | Frontend Build | Zero-Gap Verifications |
|-----------|--------------|----------------|----------------------|
| v1.0 | ~200 | Clean | 4/4 |
| v1.1 | ~400 | Clean | 4/4 |
| v2.0 | ~655 | Clean | 4/4 |
| v3.0 | 799 | Clean | 6/6 (incl. gap closure) |

### Top Lessons (Verified Across Milestones)

1. Wave-based execution with subagent delegation keeps orchestrator context lean and enables reliable parallel execution (verified v1.0-v3.0)
2. Research before planning consistently surfaces architectural decisions that save rework during execution (verified v2.0-v3.0)
3. Phase verification on first attempt correlates with thorough research and plan-checker loops (verified v1.1-v3.0)
4. Milestone audit as mandatory quality gate catches cross-phase integration issues invisible to per-phase verifiers (verified v3.0 — 4 integration bugs caught)
