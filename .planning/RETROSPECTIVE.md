# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v3.1 — Hardening + Monitoring

**Shipped:** 2026-02-28
**Phases:** 4 (19-22) | **Plans:** 8 | **Commits:** 38
**Requirements:** 16/16 satisfied

### What Was Built
- Health Check Foundation: 8 parallel service checks (asyncio.gather), in-memory CachedValue with 5s TTL, 3-tier overall status (healthy/degraded/critical)
- Telegram Notifications: TelegramNotifier singleton with state machine for healthy→DOWN transition detection, graceful no-op, structural separation from AlertEventDB
- WebSocket Recovery: subscribe.signature migration (HMAC-SHA256), post-reconnect fill reconciliation for all KNOWN_PAIRS, Listen Key freshness tracking (>90s = DEGRADED)
- Status Dashboard: 8 color-coded service cards with relative-age timestamps, WebSocket reconnect panel, pulsing red Global Nav status dot

### What Worked
- Fastest milestone yet (1 calendar day, ~31min total execution for 8 plans) — small scope + well-defined infrastructure patterns
- Singleton + thread-safe lock pattern reused consistently across HealthCheckService, TelegramNotifier — established in prior milestones
- In-memory health state (zero SQLite writes) eliminated lock-contention risk with trading writes
- Alert routing separation (Telegram for health, AlertBanner for business) kept both channels clean

### What Was Inefficient
- No milestone audit before completion — skipped in yolo mode, but health-check service had two real bugs (DB engine import binding, macro timezone mismatch) discovered during manual testing
- SUMMARY.md one-liner extraction still returns null — tool format standardization still pending from v3.0
- Phase 20 metrics missing from STATE.md performance table (only 19, 21, 22 recorded)

### Patterns Established
- **Module import for mutable globals**: `from app.db import database as _db` instead of `from app.db.database import engine` — Python rebinds module-level variables but the importing module keeps the old reference
- **Naive datetime consistency**: Services using `datetime.now().replace(tzinfo=None)` must be checked with same timezone awareness — mixing aware/naive causes runtime errors
- **Health-check as transition detector**: State machine tracks previous_states dict, only fires on state change, prevents alert spam during sustained outages

### Key Lessons
1. Import-time binding of mutable module variables is a Python gotcha that static analysis doesn't catch — health check appeared to work in tests but failed at runtime because engine was None at import time
2. Timezone awareness mismatches between services and health checks are silent until runtime — need consistent policy (all naive or all aware)
3. Small infrastructure milestones (4 phases) complete in a single day — good cadence for operational improvements between feature milestones
4. Telegram integration is trivial (python-telegram-bot + 2 env vars) but high-value for unattended operation

### Cost Observations
- Model mix: ~80% opus (executors), ~20% sonnet (verifiers)
- v3.1 completed in 1 calendar day (2026-02-28), ~31min total plan execution
- Notable: Bug fixes (engine import, timezone) found during user testing, not during phase verification — verifiers check code structure but not Python import semantics

---

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
| v3.1 | 4 | 8 | Module import gotcha pattern, timezone consistency, health as transition detector |

### Cumulative Quality

| Milestone | Backend Tests | Frontend Build | Zero-Gap Verifications |
|-----------|--------------|----------------|----------------------|
| v1.0 | ~200 | Clean | 4/4 |
| v1.1 | ~400 | Clean | 4/4 |
| v2.0 | ~655 | Clean | 4/4 |
| v3.0 | 799 | Clean | 6/6 (incl. gap closure) |
| v3.1 | 799+ | Clean | 4/4 |

### Top Lessons (Verified Across Milestones)

1. Wave-based execution with subagent delegation keeps orchestrator context lean and enables reliable parallel execution (verified v1.0-v3.0)
2. Research before planning consistently surfaces architectural decisions that save rework during execution (verified v2.0-v3.0)
3. Phase verification on first attempt correlates with thorough research and plan-checker loops (verified v1.1-v3.0)
4. Milestone audit as mandatory quality gate catches cross-phase integration issues invisible to per-phase verifiers (verified v3.0 — 4 integration bugs caught)
5. Python import-time binding of mutable globals is a recurring gotcha — use module imports for variables reassigned after init (verified v3.1 — health check engine was None)
