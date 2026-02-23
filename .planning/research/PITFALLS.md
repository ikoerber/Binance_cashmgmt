# Pitfalls Research

**Domain:** Dark Mode migration for existing Plain CSS app, XRPBTC feature removal from working trading system, React navigation restructuring
**Researched:** 2026-02-23
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Hardcoded Colors Survive Dark Mode Migration (444 occurrences across 12 CSS files)

**What goes wrong:**
Dark Mode is implemented via CSS custom properties on `:root`, but hundreds of hardcoded hex values remain unchanged in component CSS files. Result: white cards on dark backgrounds, invisible text on same-color backgrounds, borders that vanish. The app looks "half-themed" -- some components dark, others blinding white.

Concrete inventory of the problem in this codebase:
- `index.css`: 30 hardcoded hex values (already has some CSS variables, but `body` background, link colors, button background still hardcoded)
- `LotsTable.css`: 68 hardcoded values (table row alternation `#fafbfd`, filter bar `#f8fafc`, sync feedback `#ecfdf5`, `#eff6ff`, etc.)
- `PairingPanel.css`: 88 hardcoded values (simulation overlay, route cards, cross-pair UI -- most heavily hardcoded file)
- `Orderblock.css`: 83 hardcoded values (explainer gradients `#fffbeb`, chart sections, action bar)
- `Reconciliation.css`: 49 hardcoded values
- `CombinedScore.css`: 40 hardcoded values (action banner gradient, conflict alert, pillar quality badges)
- `Overview.css`: 24 hardcoded values (`white` as background, `#1e293b` text, `#e2e8f0` borders)
- `Dashboard.css`: 15 hardcoded values (card `.value` colors, info-box backgrounds)
- `App.css`: 16 hardcoded values (footer `#1e293b`, subnav `#1e293b`)
- `AlertBanner.css`: 14 hardcoded values
- `Settings.css`: 12 hardcoded values
- `FillNotification.css`: 5 hardcoded values

Additionally, 9 inline style occurrences in JSX files (CombinedScore.jsx, PairingExistingTab.jsx, GlobalNav.jsx, OrderblockKPIs.jsx) with hardcoded colors.

**Why it happens:**
Developers convert `:root` variables and assume they are done, missing that most colors were written directly in component CSS (not via variables). The existing codebase uses CSS variables for some semantic tokens (`--color-profit`, `--color-loss`, `--color-bg-card`) but the majority of component styles bypass these.

**How to avoid:**
1. Before writing any Dark Mode code, audit ALL 12 CSS files systematically. Replace every hardcoded hex with a CSS custom property.
2. Create a complete Dark Mode variable set in `:root` and `[data-theme="dark"]`.
3. Target zero hardcoded colors in CSS. Inline styles in JSX must also use `var()` or be replaced with class-based approaches.
4. Audit checklist: `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` should return zero results after migration (except inside CSS variable definitions).

**Warning signs:**
- "Some components look fine but this one is still white" during visual testing
- Text becomes invisible (dark text on dark background) on specific components
- Gradients become jarring (light gradient on dark container)

**Phase to address:**
Phase 1 (CSS Variable Foundation) -- must be completed before any theme switching logic is added. Extract all hardcoded colors into CSS variables FIRST, verify light mode still looks identical, THEN add dark theme.

---

### Pitfall 2: Chart Library Theme Mismatch (lightweight-charts + Recharts)

**What goes wrong:**
CSS Dark Mode applies to the app shell, but chart libraries render on `<canvas>` (lightweight-charts) or `<svg>` (Recharts) with their own color systems. The chart remains white/light while everything around it goes dark. Worse: lightweight-charts background is set programmatically in JavaScript (`background: { type: ColorType.Solid, color: '#ffffff' }`), not via CSS, so CSS variable changes have zero effect.

Specific instances in this codebase:
- `OrderblockChart.jsx` line 29: `color: '#ffffff'` (canvas background)
- `OrderblockChart.jsx` line 30: `textColor: '#64748b'` (axis labels)
- `OrderblockChart.jsx` lines 34-35: Grid line colors `#f1f5f9`
- `OrderblockChart.jsx` lines 38-41: Scale border colors `#e2e8f0`
- `OrderblockChart.jsx` lines 49-54: Candlestick up/down colors (these stay the same in dark mode, but need verification)
- `OrderblockChart.jsx` line 58: Volume histogram color `#94a3b8`
- `OrderblockChart.jsx` line 98: Volume bar colors `rgba(22,163,74,0.25)` and `rgba(220,38,38,0.25)`
- `OrderblockChart.jsx` line 123: Zone border colors

- `Orderblock.jsx` lines 345-370: Recharts `<CartesianGrid stroke>`, `<XAxis stroke>`, `<YAxis stroke>`, `<Tooltip contentStyle>`, `<Bar fill>` -- all hardcoded for light mode

- `Overview.jsx` line 154+: Recharts `<PieChart>` with `<Tooltip>` -- needs dark contentStyle

**Why it happens:**
Developers think "I turned on Dark Mode for the CSS, charts will follow." Canvas-based libraries (lightweight-charts) are completely decoupled from the DOM's CSS. SVG-based libraries (Recharts) partially inherit from CSS but most visual properties are set as props.

**How to avoid:**
1. **lightweight-charts**: Read the current theme from a React context or attribute, pass it to `createChart()` options. When theme changes, call `chart.applyOptions()` to update background, text color, grid colors, scale borders. The chart MUST be re-themed programmatically.
2. **Recharts**: Pass theme-aware colors to `stroke`, `fill`, `contentStyle` props. Either read from CSS variables via `getComputedStyle()` or maintain a JS theme object.
3. Create a single `chartTheme` object (light/dark variants) that both libraries consume. This prevents inconsistency between the two chart systems.
4. Test chart readability in dark mode specifically -- grid lines that are subtle in light mode may become invisible in dark mode.

**Warning signs:**
- Charts appear as white rectangles on a dark page
- Chart axis labels become unreadable (dark gray on dark background)
- Recharts tooltips have white backgrounds that look disconnected from the dark UI

**Phase to address:**
Phase 2 (Dark Mode Implementation) -- after CSS variable foundation. Charts need their own theme integration pass.

---

### Pitfall 3: Orphaned XRPBTC Data in Database After Removal

**What goes wrong:**
Code for XRPBTC is removed (Symbol Registry, routes, domain logic), but the database still contains:
- `ledger_events` with `symbol = 'XRPBTC'`
- `trade_lots` with `symbol = 'XRPBTC'` (qty_open may be > 0)
- `sell_allocations` referencing XRPBTC lots
- `pairing_items` with `lot_symbol = 'XRPBTC'`
- `pairings` with `routing_decision_json` containing XRPBTC route data
- `orders` placed on XRPBTC market (may have status NEW/PARTIALLY_FILLED on Binance)

After removal, queries filtering by `symbol IN (known_pairs)` silently exclude XRPBTC data. The user's portfolio appears to lose BTC/XRP inventory. Reconciliation shows balance discrepancies.

**Why it happens:**
Developers remove the feature code but forget that the append-only ledger and active positions contain XRPBTC data. "Remove from code" is not "remove from data."

**How to avoid:**
1. **Inventory XRPBTC data first**: Before removing any code, query the production DB:
   - `SELECT COUNT(*) FROM trade_lots WHERE symbol = 'XRPBTC' AND status != 'CLOSED'` (open positions!)
   - `SELECT COUNT(*) FROM orders WHERE symbol = 'XRPBTC' AND status IN ('NEW', 'PARTIALLY_FILLED')` (live Binance orders!)
   - `SELECT COUNT(*) FROM pairings WHERE status != 'EXECUTED' AND id IN (SELECT pairing_id FROM pairing_items WHERE lot_symbol = 'XRPBTC')` (active pairings!)
2. **Cancel live XRPBTC orders on Binance** before removing code that manages them
3. **Close or migrate open XRPBTC lots**: Either mark as CLOSED with an ADJUSTMENT ledger event, or convert to XRPEUR equivalent with documented audit trail
4. **Keep historical data readable**: The ledger is append-only. XRPBTC events must remain queryable for audit. Consider adding `symbol_registry.DEPRECATED_PAIRS` for display-only purposes.
5. **Migration script**: Alembic migration that handles data state, not just schema changes

**Warning signs:**
- Portfolio value drops unexpectedly after deployment
- Reconciliation shows balance discrepancies
- Historical P&L reports change retroactively
- "Unknown symbol" errors in logs

**Phase to address:**
Phase dedicated to XRPBTC removal -- must be executed BEFORE navigation restructuring and Dark Mode, because the data migration is the highest-risk operation.

---

### Pitfall 4: Broken Tests After XRPBTC Removal (6+ test files directly affected)

**What goes wrong:**
Removing XRPBTC from `symbol_registry.py` causes cascading test failures. Tests that explicitly create XRPBTC lots, test cross-pair pairing, test sell routing, or test EUR cost basis for BTC-quoted lots all break. If tests are "fixed" by just deleting them, coverage for the remaining sell-allocation-isolation and EUR-cost-basis logic drops silently.

Directly affected test files (6):
- `test_sell_routing.py` -- Tests XRPBTC-specific sell routing (likely needs complete removal or major rewrite)
- `test_cross_pair_pairing.py` -- Tests cross-pair pairing logic (complete removal)
- `test_portfolio_cross_pair.py` -- Tests cross-pair portfolio calculations (complete removal)
- `test_order_filters.py` -- References XRPBTC in order creation tests
- `test_eur_cost_basis.py` -- Tests BTC-quoted lot EUR cost basis
- `test_sell_allocation_isolation.py` -- Tests base-asset filtering across symbols

Indirectly affected (domain code removal triggers import errors):
- Any test importing from `domain/models.py` classes like `DualRouteComparison`, `RouteDetails`, `RoutingDecision`
- Any test using `pairing.compare_dual_routes()`

**Why it happens:**
XRPBTC is deeply integrated: it is not just a registry entry but has dedicated domain logic (dual-route comparison, satoshi-encoding for clientOrderId, BTC-quote sell allocation), dedicated data models (RouteDetails, DualRouteComparison, RoutingDecision), and dedicated frontend components (route cards, pair-origin badges, cross-pair toggle).

**How to avoid:**
1. **Map test dependencies before deleting code**: For each XRPBTC-related domain function/model being removed, identify which tests import or use it.
2. **Categorize tests into three buckets**:
   - DELETE: Tests exclusively for XRPBTC functionality (sell routing, cross-pair pairing, dual-route comparison)
   - MODIFY: Tests that use XRPBTC as one of several test cases (remove XRPBTC cases, keep EUR-pair cases)
   - KEEP: Tests unrelated to XRPBTC
3. **Run full test suite after each removal step** -- not just at the end
4. **Verify coverage does not drop** for sell-allocation and portfolio logic after removing cross-pair tests

**Warning signs:**
- More than 20 tests fail after removal (indicates cascading dependency)
- Test count drops significantly without replacement tests
- `pytest --cov` shows coverage drops in `domain/lots.py`, `domain/pairing.py`, `services/order_service.py`

**Phase to address:**
Same phase as XRPBTC code removal. Tests must be updated as part of each removal step, not as a separate follow-up.

---

### Pitfall 5: Flash of Wrong Theme (FOWT) on Page Load

**What goes wrong:**
User has Dark Mode preference stored (localStorage, system preference). On page load, the browser renders the default light CSS before JavaScript runs to apply the dark theme. Result: a visible flash of white/light-mode UI for 100-300ms before dark mode kicks in, especially jarring for users in dark rooms.

**Why it happens:**
React-based theme switching happens after:
1. HTML is parsed
2. CSS is loaded (default `:root` = light theme)
3. JavaScript bundles load
4. React initializes
5. Theme context reads preference
6. DOM updates with `data-theme="dark"`

Steps 1-4 render with light theme. Step 6 triggers repaint.

**How to avoid:**
1. **Inline blocking script in `index.html`** (before any CSS or React):
   ```html
   <script>
     const theme = localStorage.getItem('theme') ||
       (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
     document.documentElement.setAttribute('data-theme', theme);
   </script>
   ```
   This runs synchronously before CSS is evaluated, so the correct theme variables are active from the first paint.
2. Set default to dark (since this is a trading app, dark is the expected default). This means the "flash" scenario is reversed -- only light-mode users would flash, and even then only if they explicitly chose light.
3. Never rely solely on React state for initial theme application.

**Warning signs:**
- White flash visible on page reload, especially on slow connections
- User complaints about "blinding" first paint
- More noticeable on mobile (slower JS parsing)

**Phase to address:**
Phase 2 (Dark Mode Implementation) -- the blocking script must be part of the initial Dark Mode implementation, not an afterthought.

---

### Pitfall 6: CSS Specificity Wars with Dark Mode Overrides

**What goes wrong:**
Component CSS uses highly specific selectors (`.lots-table tbody tr:nth-child(even):hover`, `.ob-table tbody tr.ob-zone-row-selected`). Dark Mode overrides with `[data-theme="dark"] .lots-table tbody tr` get overridden by the more specific light-mode rules. Developers add `!important` to fix it, creating an unwinnable specificity cascade.

This codebase already has instances that will cause problems:
- `LotsTable.css`: `.order-row-warning { background: #fffbeb !important; }` and `:hover` variant (already using `!important`)
- `PairingPanel.css`: `.summary-profit .summary-value { color: var(--color-profit) !important; }` (already using `!important`)
- Multi-level specificity: `.lots-table tbody tr:nth-child(even):hover { background: #f1f5f9; }` requires equally specific dark override
- Gradient backgrounds: `linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)` appears in 15+ places across component CSS files -- each needs a dark variant

**Why it happens:**
Original CSS was written for a single theme. Complex selectors were needed for visual hierarchy (alternating rows, hover states, active states). Adding a theme dimension multiplies selector complexity.

**How to avoid:**
1. **Extract colors from complex selectors into variables FIRST**: Replace `background: #f1f5f9` in complex selectors with `background: var(--color-bg-hover)`. The variable changes with theme; the selector stays the same.
2. **Zero `[data-theme="dark"]` overrides in component CSS**: If all colors are variables, component CSS files need NO theme-specific rules. Only `index.css` (or a `theme.css`) defines the two sets of variables.
3. **Eliminate existing `!important` before Dark Mode**: The two `!important` usages must be resolved first. They will block clean theme overrides.
4. **Gradients use variable-based colors**: `linear-gradient(135deg, var(--color-bg-gradient-start), var(--color-bg-gradient-end))`.

**Warning signs:**
- Dark mode works for most components but specific states (hover, active, selected, warning) still show light colors
- Developers start adding `!important` to dark mode overrides
- Some components need both `[data-theme="dark"]` AND `:hover` in the same selector

**Phase to address:**
Phase 1 (CSS Variable Foundation) -- variable extraction must handle ALL selectors including complex hover/active/nth-child states. This is the single most time-consuming part of the migration.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Soft-delete XRPBTC code (comment out, feature-flag) instead of removing | Faster, reversible | Dead code accumulates, confuses future developers, routing logic branching remains | Never -- commit to removal. Archived milestone docs preserve intent. |
| Dark Mode with `filter: invert(1)` CSS hack | Instant "dark mode" without touching any CSS | Images invert, charts become unreadable, semantic colors flip (profit green becomes loss-looking) | Never -- trading apps need precise color semantics. |
| Keep `[data-theme="dark"]` overrides per component file | Quick wins, file-scoped | 12+ files with dark overrides, impossible to maintain consistency, 200+ override rules | Never -- use variable-only approach. |
| Leave hardcoded colors in JSX inline styles | "Only 9 occurrences" | Each is a Dark Mode bug. Inline styles beat CSS variables. | Never -- convert to classes or use CSS variables. |
| Skip data migration for XRPBTC, just hide in UI | No Alembic migration needed | Phantom inventory, broken reconciliation, confusing audit trail | Never -- financial data must be clean. |
| Navigate by replacing URL directly instead of React Router | Works for simple cases | Loses React state, triggers full re-renders, breaks back-button expectations | Never in this app -- React Router already handles nested routes. |

## Integration Gotchas

Common mistakes when connecting to external services during this migration.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| lightweight-charts v5 theming | Calling `createChart()` once with hardcoded colors, no update mechanism | Store chart ref, call `chart.applyOptions()` when theme changes. Use `useEffect` with theme dependency. |
| Recharts Dark Mode | Passing hardcoded color strings as props | Create a theme-aware hook `useChartTheme()` that returns colors based on current theme. Pass to all Recharts props. |
| Binance open orders (XRPBTC) | Removing code without cancelling live orders first | Query and cancel all XRPBTC orders via API before deploying code removal. Add pre-deployment script. |
| React Router nested restructure | Moving routes without updating `<NavLink to="">` patterns in all components | Grep for all `to=` and `navigate()` calls. Create redirect rules for old URL patterns. |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-creating lightweight-charts on every theme toggle | Chart flickers, loses scroll position, 100ms+ lag on toggle | Use `chart.applyOptions()` instead of unmounting/remounting chart component | Immediately noticeable on first toggle |
| CSS Variable recalculation on 444 property changes | Theme toggle causes layout thrash, visible repaint | All 444 hex values should be variables, but browsers handle this efficiently. The risk is JavaScript-triggered reflows during toggle, not CSS variable count. | Not a real issue -- CSS variables are O(1) lookup. Only a trap if you trigger forced reflow in JS during toggle. |
| Full re-fetch of portfolio data after XRPBTC migration changes schema | API calls fail or return unexpected shape | Version the API response or ensure backward compatibility. Migration should not change API contract for EUR-only pairs. | First load after deployment |

## Security Mistakes

Domain-specific security issues for this migration.

| Mistake | Risk | Prevention |
|---------|------|------------|
| XRPBTC orders left active on Binance after code removal | Fills arrive with no code to process them. Fill events via WebSocket for unknown symbols could cause unhandled exceptions. Funds stuck in limbo. | Pre-deployment: cancel all XRPBTC orders. Post-deployment: WebSocket handler must gracefully ignore unknown symbols (log + skip, not crash). |
| Theme preference stored in localStorage without validation | XSS could inject arbitrary `data-theme` attribute values, potentially breaking CSS selectors if used carelessly | Validate theme value against allowed list (`['light', 'dark']`) before applying to DOM attribute |
| Navigation restructure exposes admin routes | Reconciliation and Settings previously behind symbol context. New flat `/admin/*` routes might lack auth checks if restructured carelessly | Verify API-Key authentication covers all route handlers regardless of frontend URL structure (backend auth is server-side, so this is low-risk, but verify) |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No theme toggle -- only system preference | User wants dark in browser but light in this app (or vice versa), no control | Provide explicit toggle (sun/moon icon in navbar). Respect system preference as default, allow override. Store in localStorage. |
| Theme toggle in Settings page (buried) | User must navigate away from trading view to switch themes | Put toggle in GlobalNav (always accessible). Settings can have the "full" theme configuration. |
| Navigation labels change without redirect | User has bookmarked `/s/BTCEUR/combined`. After restructure, URL 404s. | Keep old URL patterns working via redirect rules (React Router `<Navigate>` for old paths). |
| XRPBTC lots disappear from view without explanation | User had XRPBTC positions, after update they see fewer lots, lower portfolio value | Show migration notification: "XRPBTC has been removed. X lots were closed/migrated. See details." |
| Dark Mode breaks familiar color associations | User trained that green=profit, red=loss. Dark Mode inverts or mutes these. | Keep profit/loss colors identical in both themes. Only change backgrounds, surfaces, borders, text. Semantic colors (profit, loss, warning) stay constant. |
| Navigation grouping loses discoverability | 7 visible tabs becomes 3 areas -- Reconciliation and Combined Score are now "hidden" inside sub-navigation | Ensure sub-navigation is always visible when in a section. Consider breadcrumbs or persistent sidebar for the Trading area. |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Dark Mode CSS variables:** All 12 CSS files converted -- verify with `grep '#[0-9a-fA-F]' frontend/src/**/*.css` returns zero matches outside variable definitions
- [ ] **Dark Mode gradients:** `linear-gradient()` values (15+ occurrences) use CSS variables, not hardcoded hex pairs
- [ ] **Dark Mode shadows:** `box-shadow: rgba(0,0,0,...)` values adjusted for dark theme (shadows need to be darker/more opaque on dark backgrounds to be visible)
- [ ] **Dark Mode `<input>` / `<select>` / `<option>`:** Browser defaults render white backgrounds in form controls -- must be explicitly styled in dark mode
- [ ] **lightweight-charts dark theme:** `chart.applyOptions()` called on theme change -- not just on init
- [ ] **Recharts dark tooltips:** `contentStyle` prop updated dynamically, not hardcoded to `{ background: '#fff' }`
- [ ] **Recharts axis text:** `stroke` prop on `<XAxis>` and `<YAxis>` is theme-aware (currently `#64748b`)
- [ ] **XRPBTC live orders cancelled:** No open XRPBTC orders on Binance before code deployment
- [ ] **XRPBTC open lots resolved:** All XRPBTC `trade_lots` with `status != CLOSED` have been migrated or closed
- [ ] **XRPBTC test cleanup:** Removed test files do not cause coverage regression in non-XRPBTC code paths
- [ ] **Navigation old URLs redirect:** Bookmarked URLs like `/s/BTCEUR/combined` still work after restructure
- [ ] **Navigation state preserved on toggle:** Switching between Trading/Orderblocks/Admin does not lose in-progress state (selected lots, pairing panel open state, filter selections)
- [ ] **Cross-pair CSS artifacts removed:** PairingPanel.css still has `.dual-route-section`, `.route-card`, `.cross-pair-toggle`, `.pair-origin-badge` classes (100+ lines) that should be deleted
- [ ] **Domain model cleanup:** `RouteDetails`, `DualRouteComparison`, `RoutingDecision` dataclasses removed from `domain/models.py`
- [ ] **Backend cross-pair code paths removed:** `compare_dual_routes()`, satoshi-encoding in `orders.py`, BTC-quote branch in `lots.py` `compute_realized_pnl_for_allocation()`

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Hardcoded colors missed (some components still light in dark mode) | LOW | Iterative: find-and-replace remaining hardcoded values. No data loss, purely visual. |
| Chart libraries not themed | LOW | Add `chart.applyOptions()` call with dark theme. Recharts: update props. No data impact. |
| Orphaned XRPBTC data causing wrong portfolio | HIGH | Requires forensic analysis of current data state, creation of corrective ADJUSTMENT ledger events, re-reconciliation. Must not simply delete ledger events (append-only). |
| XRPBTC orders still active on Binance | MEDIUM | Use Binance API to cancel remaining orders. Then reconcile. If fills arrived during gap: manually process via ADJUSTMENT events. |
| Flash of wrong theme | LOW | Add blocking script to `index.html`. Single file change, no testing needed. |
| CSS specificity wars | MEDIUM | Requires systematic refactor of component CSS to use variables consistently. May need to simplify overly-specific selectors. Time-consuming but not risky. |
| Navigation breaks existing bookmarks | LOW | Add `<Navigate>` redirect rules. Can be done incrementally. |
| Tests broken in bulk | MEDIUM | Requires careful categorization of which tests to delete vs. modify vs. keep. Cannot skip -- must be done before merging. |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| P1: Hardcoded colors (444 occurrences) | Phase 1: CSS Variable Foundation | `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` returns zero outside `:root` definitions |
| P2: Chart library theme mismatch | Phase 2: Dark Mode Implementation | Visual comparison of both charts in dark mode screenshot |
| P3: Orphaned XRPBTC data | Phase: XRPBTC Removal (run BEFORE UI phases) | `SELECT COUNT(*) FROM trade_lots WHERE symbol='XRPBTC' AND status!='CLOSED'` returns 0 |
| P4: Broken tests after removal | Phase: XRPBTC Removal | `pytest` passes, `pytest --cov` shows no coverage regression in domain/lots.py, domain/pairing.py |
| P5: Flash of wrong theme (FOWT) | Phase 2: Dark Mode Implementation | Manual test: set dark preference, hard-reload page, no white flash visible |
| P6: CSS specificity wars | Phase 1: CSS Variable Foundation | Zero `!important` in component CSS. Zero `[data-theme="dark"]` selectors in component CSS files. |
| P7: Navigation state loss | Phase: Navigation Restructure | Tab switching preserves filter selections, pairing panel state, selected lots |
| P8: Cross-pair CSS artifacts remain | Phase: XRPBTC Removal | PairingPanel.css has zero `.dual-route-*`, `.cross-pair-*`, `.pair-origin-*` selectors |

## Sources

- Codebase audit: Direct analysis of 12 CSS files, 444 hardcoded hex values counted via `grep`
- lightweight-charts v5 API: Verified `applyOptions()` method existence from codebase imports (`createChart`, `ColorType.Solid`)
- Recharts theming: Verified inline prop-based color system from `Orderblock.jsx` lines 344-370
- XRPBTC code surface: `grep` across backend/app (10 files), backend/tests (6 files), frontend/src (4 files)
- React Router behavior: Verified from existing `App.jsx` nested route structure
- FOWT pattern: Well-documented in web development community, standard mitigation is blocking `<script>` in `<head>`

---
*Pitfalls research for: v2.0 Frontend Redesign -- Dark Mode + XRPBTC Removal + Navigation Restructuring*
*Researched: 2026-02-23*
