---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - CODE_REVIEW.md
autonomous: true
requirements: ["REVIEW-01"]

must_haves:
  truths:
    - "Every backend Python file has been read and reviewed for quality issues"
    - "Every frontend JS/JSX file has been read and reviewed for quality issues"
    - "Findings are categorized by severity with file paths, line numbers, and fixes"
    - "Project invariants from CLAUDE.md are checked against actual implementation"
  artifacts:
    - path: "CODE_REVIEW.md"
      provides: "Comprehensive code review report"
      min_lines: 200
  key_links: []
---

<objective>
Perform a comprehensive, systematic code review of the entire codebase (backend + frontend), producing a detailed CODE_REVIEW.md report with findings categorized by severity.

Purpose: Identify bugs, anti-patterns, security concerns, tech debt, and invariant violations across ~35K lines of production code spanning 70+ files.
Output: CODE_REVIEW.md at project root with all findings, file paths, line numbers, and recommended fixes.
</objective>

<execution_context>
@/Users/ikoerber/.claude/get-shit-done/workflows/execute-plan.md
@/Users/ikoerber/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@CODE_REVIEW_2026_02_24.md

The prior review (Feb 24) was high-level and identified 4 action items. This review must go deeper — file by file, line by line — and produce a comprehensive audit covering the full codebase including all v3.0 additions (Alpha Score, Backtest, Dry-Run, Bot Dashboard, Combined Score integration).

<invariants_to_verify>
From CLAUDE.md "Kritische Invarianten" — check each against actual code:

1. Ledger append-only (no UPDATE/DELETE on ledger_events)
2. Decimal everywhere (no float for money/prices) — check domain, services, routes
3. 1 Fill = 1 Lot deterministic
4. Sell Allocation Strategy (FIFO/LIFO/HIGHEST_COST) + Abort-on-Error
5. Idempotent Orders (clientOrderId format)
6. Simulation before Execution (pairing lifecycle)
7. Pairing lifecycle DRAFT -> LOCKED -> EXECUTED
8. External cashflows do NOT affect BTC cost basis
9. TAKE_PROFIT_LIMIT orders (stopPrice = price = targetPrice)
10. Max Order Value check
11. Test isolation (TEST_BINANCE_API_KEY + testnet)
12. Sentiment scoring (correlation-based weights, no cliff effects)
13. Fee conversion (historical price, fallback)
14. Orderblock time consistency (confirmed_at_index + 1)
15. 5-phase validation (no phase skipping)
16. Conviction scoring (4 equal components)
17. Triple Barrier (3 exit conditions)
18. Config hierarchy (Request > User-Settings > Defaults)
19. Error sanitization (no stacktraces to client)
20. Pairing race protection (with_for_update)
</invariants_to_verify>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Backend Code Review (Domain + Services + Routes + DB)</name>
  <files>CODE_REVIEW.md</files>
  <action>
Systematically READ every backend Python file and review for quality issues. This is a READ-ONLY task — do not modify any source files. Take structured notes for the final report.

**Review order (dependency-aware):**

1. **DB/ORM layer** (~700 lines):
   - `backend/app/db/database.py` — session management, yield pattern, connection pooling
   - `backend/app/db/models.py` — ORM models, column types (Decimal vs Float), constraints, indexes
   - `backend/app/constants.py`, `backend/app/symbol_registry.py`

2. **Domain layer** (~8,350 lines — pure logic, no I/O):
   - `backend/app/domain/models.py` — dataclasses, type annotations
   - `backend/app/domain/portfolio.py` — WAC calculation, Decimal precision
   - `backend/app/domain/lots.py` — lot creation, sell allocation strategies
   - `backend/app/domain/pairing.py` — heuristic, simulation
   - `backend/app/domain/orders.py` — order creation logic
   - `backend/app/domain/macro_signal.py` — factor computation
   - `backend/app/domain/sentiment.py` — 6-pillar scoring
   - `backend/app/domain/combined_score.py` — unified scoring
   - `backend/app/domain/alpha_score.py` — factor computations, Decimal purity
   - `backend/app/domain/dry_run.py` — virtual trading
   - `backend/app/domain/backtest_engine.py` — backtesting
   - `backend/app/domain/orderblock/*.py` — detection, scoring, classification
   - `backend/app/domain/orderblock_backtest.py` — triple barrier
   - `backend/app/domain/lot_merge.py`, `reconciliation.py`, `sync_result.py`

3. **Services layer** (~12,150 lines — DB + external API integration):
   - `backend/app/services/binance.py` — API client, error handling
   - `backend/app/services/binance_public_client.py` — public endpoints
   - `backend/app/services/sync_service.py` — fill import, FIFO abort
   - `backend/app/services/lot_service.py` — lot CRUD, row locking
   - `backend/app/services/order_service.py` — order creation
   - `backend/app/services/order_tracking_service.py` — lifecycle
   - `backend/app/services/pairing_service.py` — race protection
   - `backend/app/services/portfolio_service.py` — portfolio state
   - `backend/app/services/reconciliation_service.py` — balance/order reconciliation
   - `backend/app/services/csv_import_service.py` — CSV validation
   - `backend/app/services/macro_data_service.py` — klines, F&G
   - `backend/app/services/sentiment_data_service.py` — singleton, TTL cache
   - `backend/app/services/alpha_score_data_service.py` — mixed refresh
   - `backend/app/services/backtest_data_service.py` — paginated fetch
   - `backend/app/services/dry_run_service.py` — evaluation loop, asyncio lock
   - `backend/app/services/orderblock_data_service.py` — TTL cache
   - `backend/app/services/orderblock_persistence_service.py` — upsert, cleanup
   - `backend/app/services/orderblock_config_service.py` — 3-tier resolution
   - `backend/app/services/combined_score_service.py`
   - `backend/app/services/cashflow_service.py`
   - `backend/app/services/websocket_manager.py` — WS management
   - `backend/app/services/websocket_event_handler.py` — event dispatch
   - `backend/app/services/websocket_fill_handler.py` — fill processing
   - `backend/app/utils/fee_conversion.py`, `backend/app/utils/retry.py`

4. **API Routes layer** (~2,500 lines — thin HTTP):
   - All files in `backend/app/api/routes/` — check: error sanitization, input validation, auth dependency, response models, Decimal-string transport
   - `backend/app/api/auth.py` — API key validation
   - `backend/app/api/dependencies.py`
   - `backend/app/main.py` — app setup, CORS, startup/shutdown

**For each file, check:**
- [ ] Float usage where Decimal is required (money, prices, quantities)
- [ ] Missing error handling (bare except, swallowed exceptions)
- [ ] SQL injection risks (raw queries, f-string SQL)
- [ ] Race conditions (missing locks, non-atomic operations)
- [ ] Resource leaks (unclosed connections, files, sessions)
- [ ] Missing input validation (API parameters)
- [ ] Error messages leaking internals (stacktraces to client)
- [ ] Unused imports, dead code, unreachable branches
- [ ] Type annotation gaps or incorrect types
- [ ] Missing null/None checks before attribute access
- [ ] Hardcoded values that should be configurable
- [ ] Inconsistent error handling patterns across routes
- [ ] N+1 query patterns in service layer
- [ ] Missing index hints for common queries
- [ ] Singleton thread safety issues
- [ ] async/await correctness (missing await, blocking in async)
- [ ] Invariant violations per CLAUDE.md list (all 20 items)

Do NOT write the final report yet — collect findings as structured notes for Task 3.
  </action>
  <verify>
    <automated>echo "Backend review complete — findings collected for report"</automated>
  </verify>
  <done>Every backend Python file (~26K lines across ~65 files) has been read and reviewed. Findings collected with file paths and line numbers.</done>
</task>

<task type="auto">
  <name>Task 2: Frontend Code Review (Components + Hooks + Contexts + Utils)</name>
  <files>CODE_REVIEW.md</files>
  <action>
Systematically READ every frontend JS/JSX file and review for quality issues. This is a READ-ONLY task — do not modify any source files.

**Review order:**

1. **Infrastructure** (~300 lines):
   - `frontend/src/main.jsx` — entry point, providers
   - `frontend/src/App.jsx` — routing, layout
   - `frontend/src/api/client.js` — Axios config, interceptors, API functions

2. **Contexts** (~400 lines):
   - `frontend/src/contexts/WebSocketContext.jsx` — WS provider, reconnect, validation
   - `frontend/src/contexts/SymbolContext.jsx` — symbol state
   - `frontend/src/contexts/UserContext.jsx` — user state

3. **Hooks** (~300 lines):
   - `frontend/src/hooks/useLotsData.js` — data fetching
   - `frontend/src/hooks/useChartTheme.js` — chart theming
   - `frontend/src/hooks/useNotification.js` — notification state

4. **Utils** (~200 lines):
   - `frontend/src/utils/formatters.js` — shared formatters
   - `frontend/src/utils/orderblockHelpers.jsx` — OB helpers
   - `frontend/src/utils/symbolRegistry.js` — frontend symbol config

5. **Components** (~7,300 lines):
   - `Dashboard.jsx`, `LotsTable.jsx`, `LotFilters.jsx`, `LotSummaryCards.jsx`
   - `OpenOrdersPanel.jsx`, `PairingPanel.jsx`, `PairingExistingTab.jsx`, `SimulationModal.jsx`
   - `CombinedScore.jsx`, `CombinedScoreWidget.jsx`
   - `Orderblock.jsx`, `OrderblockChart.jsx`, `OrderblockFilters.jsx`, `OrderblockKPIs.jsx`, `OrderblockZoneTable.jsx`, `OrderblockTradeTable.jsx`
   - `Reconciliation.jsx`, `Settings.jsx`
   - `Backtest.jsx`, `BotDashboard.jsx`, `DecisionLog.jsx`
   - `Overview.jsx`, `SymbolLayout.jsx`, `GlobalNav.jsx`
   - `FillNotification.jsx`, `AlertBanner.jsx`

**For each file, check:**
- [ ] XSS vulnerabilities (dangerouslySetInnerHTML, unsanitized user input in DOM)
- [ ] Memory leaks (missing cleanup in useEffect, unsubscribed event listeners)
- [ ] Stale closure bugs (missing deps in useEffect/useCallback/useMemo)
- [ ] Missing Error Boundary (global and component-level)
- [ ] Unhandled promise rejections in event handlers
- [ ] Missing loading/error states in data-fetching components
- [ ] Hardcoded user IDs, URLs, or config values
- [ ] Missing key props on mapped elements
- [ ] Excessive re-renders (inline object/function creation in JSX)
- [ ] Accessibility issues (missing aria-labels, keyboard navigation)
- [ ] Inconsistent state management patterns
- [ ] Missing prop validation (PropTypes or TypeScript)
- [ ] Large component files that should be split (>300 lines)
- [ ] API error handling gaps (network errors, 401/403, timeouts)
- [ ] WebSocket message validation
- [ ] Number precision issues (JavaScript Number vs BigInt for financial data)
- [ ] Missing null checks before .map() or property access on API responses
- [ ] CSS-in-JS vs CSS file inconsistencies

Do NOT write the final report yet — collect findings as structured notes for Task 3.
  </action>
  <verify>
    <automated>echo "Frontend review complete — findings collected for report"</automated>
  </verify>
  <done>Every frontend JS/JSX file (~8,500 lines across ~35 files) has been read and reviewed. Findings collected with file paths and line numbers.</done>
</task>

<task type="auto">
  <name>Task 3: Compile CODE_REVIEW.md Report</name>
  <files>CODE_REVIEW.md</files>
  <action>
Compile all findings from Tasks 1 and 2 into a comprehensive CODE_REVIEW.md at the project root.

**Report structure:**

```markdown
# Code Review Report: BTC/EUR Cashflow Management App
**Date:** 2026-02-28
**Scope:** Full codebase (backend + frontend, ~35K lines, 70+ files)
**Reviewer:** Claude (automated systematic review)

## Executive Summary
[2-3 paragraphs: overall health, biggest risks, comparison to Feb 24 review]

## Severity Definitions
- **Critical (P0):** Security vulnerabilities, data corruption risks, financial calculation errors
- **High (P1):** Bugs in production paths, invariant violations, race conditions
- **Medium (P2):** Code quality issues, missing error handling, tech debt
- **Low (P3):** Style issues, minor improvements, optimization opportunities

## Invariant Compliance Audit
[Table: each of the 20 invariants from CLAUDE.md, status (PASS/FAIL/PARTIAL), evidence (file:line)]

## Backend Findings

### Critical (P0)
[Each finding: file path, line number(s), description, code snippet, recommended fix]

### High (P1)
[...]

### Medium (P2)
[...]

### Low (P3)
[...]

## Frontend Findings

### Critical (P0)
[...]

### High (P1)
[...]

### Medium (P2)
[...]

### Low (P3)
[...]

## Architecture Observations
[Cross-cutting concerns: dependency patterns, coupling, test coverage gaps, consistency issues]

## Tech Debt Inventory
[Ranked list of tech debt items with estimated impact and effort]

## Comparison with Feb 24 Review
[Status of previously identified items: resolved, still open, regressed]

## Prioritized Action Items
[Top 10 actionable recommendations, ordered by risk * impact]
```

Write this report to `/Users/ikoerber/AIProjects/cashmgnt/CODE_REVIEW.md` (project root).

The report must:
- Include specific file paths and line numbers for every finding
- Include code snippets showing the issue
- Include a concrete recommended fix for each finding
- Be actionable — a developer should be able to fix issues directly from the report
- Cover ALL 20 invariants from CLAUDE.md with evidence
- Not repeat generic advice — every finding must be specific to THIS codebase
  </action>
  <verify>
    <automated>test -f /Users/ikoerber/AIProjects/cashmgnt/CODE_REVIEW.md && wc -l /Users/ikoerber/AIProjects/cashmgnt/CODE_REVIEW.md | awk '{if ($1 >= 200) print "PASS: " $1 " lines"; else print "FAIL: only " $1 " lines (need 200+)"}'</automated>
  </verify>
  <done>CODE_REVIEW.md exists at project root with 200+ lines, covering all backend and frontend files, with findings categorized by severity, including file paths, line numbers, code snippets, and recommended fixes. All 20 invariants audited.</done>
</task>

</tasks>

<verification>
- CODE_REVIEW.md exists at project root
- Report covers both backend (~65 files) and frontend (~35 files)
- All 20 invariants from CLAUDE.md are audited with PASS/FAIL/PARTIAL status
- Every finding has: file path, line number, severity, description, recommended fix
- Report is 200+ lines with structured sections
</verification>

<success_criteria>
- Comprehensive CODE_REVIEW.md produced at project root
- All backend Python files systematically reviewed
- All frontend JS/JSX files systematically reviewed
- Findings categorized as Critical/High/Medium/Low with specific evidence
- All 20 project invariants verified against actual implementation
- Actionable recommendations with file paths and line numbers
- Comparison with prior Feb 24 review included
</success_criteria>

<output>
After completion, create `.planning/quick/1-full-codebase-review-code-qualit-t-issue/1-SUMMARY.md`
</output>
