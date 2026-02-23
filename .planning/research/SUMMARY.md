# Project Research Summary

**Project:** v2.0 Frontend Redesign — Dark Mode + Navigation Restructuring + XRPBTC Removal
**Domain:** Frontend CSS theming, React Router restructuring, feature removal (financial trading app)
**Researched:** 2026-02-23
**Confidence:** HIGH

## Executive Summary

This milestone is a purely structural frontend upgrade: no new backend features, no new dependencies, and no algorithm changes. The three workstreams — XRPBTC symbol removal, dark mode theming, and navigation restructuring — are largely independent but intersect at the symbol list, the navbar CSS, and the Combined Score routing. The recommended execution order is XRPBTC removal first (highest risk due to live financial data), dark mode CSS foundation in parallel, navigation restructuring last (depends on a clean symbol list and dark-mode tokens being ready).

The dark mode migration is the highest-effort work: 12 CSS files contain approximately 444 hardcoded hex color values that must be systematically replaced with CSS custom properties before any theme-switching logic is added. The correct approach is CSS custom properties on `:root` with a `[data-theme="dark"]` override block — no new libraries, no CSS-in-JS, no per-component theme overrides. This preserves the existing "plain CSS" project convention while enabling clean theme switching. The key risk is partial migration: leaving even one component un-converted creates a jarring "half-themed" UI, and chart libraries (lightweight-charts, Recharts) require dedicated programmatic theme integration since they render outside the CSS cascade.

The XRPBTC removal carries the highest financial risk: live orders on Binance, open lots in the database, and ledger events must be handled before code is deleted. Removing the symbol registry entry first (causing explicit failures) is the right approach, but only after confirming no open positions or orders exist. Navigation restructuring is pure UX work — grouping 7 flat tabs into 3 sections (Trading, Orderblocks, Admin) with the Combined Score hero embedded in Dashboard. All research points to keeping the existing horizontal top-nav pattern rather than introducing a sidebar.

## Key Findings

### Recommended Stack

No new dependencies are needed for any part of this milestone. CSS Custom Properties (`:root` / `[data-theme]`) is the correct theming mechanism — already partially used in `index.css` with ~30 tokens defined. The codebase's existing React Router v7 nested routes and `<Outlet>` pattern extend naturally to 3-section navigation. For chart theming, lightweight-charts v5's `applyOptions()` API handles live theme updates without chart recreation, and Recharts accepts theme-aware colors via props read through `getComputedStyle()`.

**Core technologies:**
- CSS Custom Properties (`[data-theme="dark"]`) — dark mode theming; extends existing partial token system in `index.css`, zero runtime cost, full browser support
- `useTheme` hook + `localStorage` — theme persistence; 15-line custom hook replaces any library, sufficient for single-user SPA
- Inline blocking script in `index.html` — prevents Flash of Wrong Theme (FOWT); must run synchronously before React initializes
- React Router v7 nested routes — 3-section navigation; already used for `SymbolLayout`, extend to section-level layouts
- lightweight-charts `applyOptions()` — chart dark mode; programmatic theme update without chart recreation
- `getComputedStyle()` + Recharts props — Recharts theme; read CSS vars in JS, pass to SVG rendering props

### Expected Features

**Must have (table stakes) — v2.0 launch:**
- Dark background with high-contrast text (WCAG AA minimum 4.5:1) — industry expectation for any trading app
- Profit green / loss red on dark backgrounds with brighter variants (`#22c55e` / `#ef4444`) — universal financial convention
- Readable data tables, form controls, cards, and modals in dark theme — 5 table components, 15+ card variants, 2 overlays
- 3-section navigation: Trading / Orderblocks / Admin with symbol selector always in navbar
- Combined Score hero widget embedded in Dashboard (removed as standalone route)
- XRPBTC removal from symbol registry, frontend, backend, and test suite
- Dark navbar replacing current purple gradient with flat dark surface
- Dark candlestick chart via lightweight-charts native dark config
- API Docs link removed from navbar

**Should have — complete in same milestone:**
- Blocking script in `index.html` for FOWT prevention
- Dark-adapted AlertBanner and FillNotification components
- Theme toggle accessible from GlobalNav (not buried in Settings)
- Old URL redirects (`/s/:symbol/combined` → Dashboard)
- Cross-pair CSS artifacts fully removed from PairingPanel.css

**Defer to v2.x+:**
- Light/Dark mode toggle (dark-only is the explicit ask; add toggle only if user requests it later)
- Animated page transitions between sections
- Custom accent color picker in Settings
- Mobile responsive redesign
- Multiple color themes beyond dark

### Architecture Approach

Three independent workstreams with defined intersection points. Phase 1 (XRPBTC removal) simplifies the symbol list and eliminates ~400 lines of cross-pair domain code, dead data models, and cross-pair frontend components. Phase 2 (CSS variable foundation) is CSS-only: convert all 12 CSS files from hardcoded hex to custom properties, add `[data-theme="dark"]` override block to `index.css`. Phase 3 (dark mode activation) adds the dark token set and wires up the theme toggle with chart library integration. Phase 4 (navigation restructuring) creates the new section layout, restructures React Router routes, and integrates CombinedScore into Dashboard. No changes to backend business logic, domain models, or database schema beyond optional Alembic migration to close orphaned XRPBTC lots.

**Major components:**
1. `index.css` — Single source of truth for all color tokens; light theme in `:root`, dark theme in `[data-theme="dark"]`; all 12 component CSS files reference only custom properties
2. `useTheme` hook + `AppShell.jsx` — Theme state, localStorage persistence, `data-theme` DOM attribute management, 3-section layout container
3. `GlobalNav.jsx` (refactored) — 3-section tabs (Trading/Orderblocks/Admin), symbol pills on right, theme toggle icon, XRPBTC pill removed
4. `Dashboard.jsx` (extended) — Absorbs CombinedScore hero widget above KPI grid; combined score detail section toggleable below
5. `OrderblockChart.jsx` + `Orderblock.jsx` — Chart theme reactivity via `applyOptions()` and `useChartTheme()` hook
6. Backend `symbol_registry.py` + ~10 backend files — XRPBTC purge: `RouteDetails`, `DualRouteComparison`, `RoutingDecision` models removed; `compute_dual_route_comparison()`, satoshi encoding, BTC-quote routing block removed

### Critical Pitfalls

1. **Partial dark mode migration (444 hardcoded colors)** — Audit ALL 12 CSS files before writing any dark theme code. Replace every hardcoded hex with a `var()` reference first, verify light mode is unchanged, then add dark theme. Verification: `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` returns zero results outside `:root` definitions.

2. **Chart libraries not themed (lightweight-charts canvas + Recharts SVG)** — Both render outside the CSS cascade. lightweight-charts: store chart ref, call `chart.applyOptions()` when theme changes via `useEffect`. Recharts: create `useChartTheme()` hook that reads CSS vars via `getComputedStyle()`, pass to all `stroke`/`fill`/`contentStyle` props.

3. **Orphaned XRPBTC data after symbol removal** — Before removing any code, query the DB for open lots (`status != 'CLOSED'`), live orders (`status IN ('NEW', 'PARTIALLY_FILLED')`), active pairings. Cancel any live Binance orders. Close open lots via ADJUSTMENT ledger events. DO NOT drop historical columns — keep `base_asset`, `routing_decision_json`, `cost_eur` for audit integrity.

4. **Flash of Wrong Theme on page load** — Add inline blocking script to `index.html` (runs before CSS evaluation): reads `localStorage.getItem('theme')` or `prefers-color-scheme`, sets `document.documentElement.setAttribute('data-theme', theme)` synchronously. Never rely on React state for initial theme application.

5. **CSS specificity wars with complex selectors** — The codebase already has two `!important` usages (`LotsTable.css`, `PairingPanel.css`) and 15+ gradient backgrounds that will fight dark mode overrides. Resolution: extract all colors from complex selectors (`:nth-child`, `:hover`, `.selected`) into variables FIRST. Zero `[data-theme="dark"]` selectors in component files — only `index.css` defines theme variants.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: XRPBTC Removal (Backend + Frontend)

**Rationale:** Highest-risk work goes first. XRPBTC removal touches live financial data (open orders on Binance, open lots in DB, append-only ledger). Doing this before visual changes keeps the risk isolated and independently testable. Symbol registry change causes explicit failures that surface all cross-pair dependencies.
**Delivers:** Clean 3-symbol codebase (BTCEUR, ETHEUR, XRPEUR), ~400 lines of dead code removed from backend, ~150 lines removed from frontend, simplified pairing and order service paths, 3 test files deleted, remaining tests updated.
**Addresses:** XRPBTC pill in nav (gone), cross-pair toggle in PairingPanel (gone), dual-route comparison in SimulationModal (gone), Overview BTC-quote conversion (gone).
**Avoids:** Pitfall 3 (orphaned XRPBTC data), Pitfall 4 (broken test cascade). Must verify zero open XRPBTC positions before removing code.

Key tasks:
- DB inventory: query open lots, live orders, active pairings for XRPBTC before touching any code
- Cancel any live Binance XRPBTC orders if they exist
- Remove XRPBTC from `symbol_registry.py` + `symbolRegistry.js`, run full test suite to surface failures
- Fix failures by removing cross-pair code in domain (`RouteDetails`, `DualRouteComparison`, `RoutingDecision`, `compute_dual_route_comparison()`), services (routing block in `order_service.py`, `pairing_service.py`), API routes (remove `base_asset` params)
- Delete test files: `test_sell_routing.py`, `test_cross_pair_pairing.py`, `test_portfolio_cross_pair.py`
- Modify `test_order_filters.py`, `test_portfolio_cross_pair.py`, `test_sell_allocation_isolation.py`
- Alembic migration: close any open XRPBTC lots
- Frontend: remove cross-pair toggle, `dual_route_comparison` section in SimulationModal, cross-pair CSS in PairingPanel.css, `toEur()` in Overview.jsx

### Phase 2: CSS Variable Foundation

**Rationale:** Pure CSS refactoring with no visual change — all hardcoded hex values become custom properties, light theme remains pixel-identical. This is a prerequisite for dark mode activation: if any color is still hardcoded when the theme switch runs, it will remain light in dark mode. This phase is independently verifiable by checking the app looks identical after conversion.
**Delivers:** All 12 CSS files using only `var()` references for color, `index.css` with complete light-theme token set (~80 tokens), zero hardcoded colors in JSX inline styles (9 occurrences in CombinedScore.jsx, PairingExistingTab.jsx, GlobalNav.jsx, OrderblockKPIs.jsx converted to CSS classes or CSS vars).
**Uses:** CSS Custom Properties, no new libraries.
**Avoids:** Pitfall 1 (partial migration), Pitfall 6 (specificity wars — gradients and complex selectors converted to variables in this phase, not the dark mode phase).

Key tasks:
- Expand `index.css` `:root` token set to ~80 tokens covering surfaces, text, borders, semantic colors, accent colors, shadows, chart colors
- Convert all 12 CSS files: `App.css` (16 hardcoded), `LotsTable.css` (68), `PairingPanel.css` (88), `Orderblock.css` (83), `CombinedScore.css` (40), `Reconciliation.css` (49), `Overview.css` (24), `Dashboard.css` (15), `Settings.css` (12), `AlertBanner.css` (14), `FillNotification.css` (5)
- Convert 15+ gradient backgrounds to `linear-gradient(var(--x), var(--y))` form
- Convert 9 JSX inline style occurrences to CSS class-based or `var()` references
- Resolve the two existing `!important` usages before proceeding
- Verification: `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` returns zero outside `:root`

### Phase 3: Dark Mode Activation + Theme Toggle

**Rationale:** With all colors as variables (Phase 2 complete), adding dark mode is a single `[data-theme="dark"]` block in `index.css` that overrides the token values. The theme toggle hook and FOWT prevention script are small additions. Chart library theming needs dedicated work but follows a clear pattern.
**Delivers:** Fully functional dark mode across all components, FOWT-free page load, persistent theme preference in localStorage, theme toggle in GlobalNav, chart libraries (lightweight-charts + Recharts) adapting to theme changes.
**Uses:** CSS Custom Properties (`[data-theme="dark"]`), `useTheme` hook, blocking script in `index.html`, `chart.applyOptions()`, `getComputedStyle()`.
**Implements:** Dark theme token set (~50 dark-variant overrides), `useTheme` hook, `useChartTheme` hook.
**Avoids:** Pitfall 2 (chart theme mismatch), Pitfall 5 (FOWT).

Key tasks:
- Add `[data-theme="dark"]` block to `index.css` with dark surface hierarchy (Slate-950/Slate-800/Slate-700 for page/card/elevated), brighter profit/loss colors (`#22c55e`/`#ef4444`), rgba accent tints for badge backgrounds
- Create `useTheme` hook: localStorage read/write, `data-theme` attribute, OS preference detection via `prefers-color-scheme`
- Add blocking script to `index.html` `<head>` for FOWT prevention
- Add theme toggle icon to `GlobalNav.jsx`
- Update `OrderblockChart.jsx`: read CSS vars via `getComputedStyle()`, call `chart.applyOptions()` in `useEffect([theme])`
- Create `useChartTheme()` hook; update `Orderblock.jsx` (12+ Recharts color props) and `Overview.jsx` (PieChart tooltip)
- Visual verification across all 12 components in dark mode

### Phase 4: Navigation Restructuring + Dashboard Integration

**Rationale:** Depends on Phase 1 (clean 3-symbol list), Phase 2/3 (dark-mode-aware CSS for new nav components). This phase changes the most component files and has the highest UX regression risk, so it comes last when the visual system is stable.
**Delivers:** 3-section navigation (Trading / Orderblocks / Admin), symbol selector persistently in navbar, Combined Score hero embedded in Dashboard, `/s/:symbol/combined` route removed, API Docs link removed, redirects for old URLs.
**Implements:** `AppShell.jsx` layout, React Router restructure in `App.jsx`, `Dashboard.jsx` extended with CombinedScore integration, `GlobalNav.jsx` redesign.
**Avoids:** UX pitfall of navigation state loss (filter/pairing state preserved across section switches), broken bookmarks via `<Navigate>` redirect rules.

Key tasks:
- Create `AppShell.jsx` with 3-section top nav and symbol pills on right
- Restructure `App.jsx` routes: group into Trading / Orderblocks / Admin, remove `/s/:symbol/combined`
- Extend `Dashboard.jsx`: extract CombinedScore hero widget (action banner + score bar) as reusable component, embed above KPI grid, add collapsible detail section
- Update `SymbolLayout.jsx`: remove Combined Score subnav link, remove XRPBTC from redirect logic
- Move theme toggle to permanent location in new GlobalNav
- Add `<Navigate>` redirects for `/s/:symbol/combined` → `/s/:symbol`
- Remove API Docs route entirely
- Verify: all sub-navigation links correct, symbol context preserved across section switches, browser back/forward works

### Phase Ordering Rationale

- **Phase 1 before all others** because financial data migration is the highest-risk operation and must be done in isolation where failures are immediately attributable
- **Phase 2 before Phase 3** because dark mode activation requires zero hardcoded colors — attempting activation before extraction causes partial-migration bugs that are expensive to diagnose
- **Phase 2 can run parallel with Phase 1** since CSS conversion is entirely independent of backend business logic
- **Phase 3 before Phase 4** because the new navigation components need dark-mode-aware CSS from the start, not patched after
- **Phase 4 last** because it touches the most component files, has the highest regression surface, and benefits from a stable visual system

### Research Flags

All phases have well-documented patterns — no phases need `/gsd:research-phase` during planning:

- **Phase 1 (XRPBTC Removal):** Architecture research provides a complete file inventory (50+ files catalogued). Test strategy is clear. DB migration pattern is established (Alembic with `render_as_batch=True`).
- **Phase 2 (CSS Variable Foundation):** Pure mechanical conversion. Pitfalls research provides exact line counts per file. Verification command is known.
- **Phase 3 (Dark Mode Activation):** Color palette fully specified in FEATURES.md with WCAG contrast ratios. lightweight-charts and Recharts integration patterns confirmed from codebase analysis.
- **Phase 4 (Navigation):** Route structure and component responsibilities fully mapped in ARCHITECTURE.md. React Router pattern already used for `SymbolLayout`.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies already installed; patterns confirmed from direct codebase analysis. Zero speculation. |
| Features | HIGH | Based on thorough codebase audit (12 CSS files, 444 color values counted via grep) and established trading platform conventions. Color values specified with WCAG contrast ratios. |
| Architecture | HIGH | Based on direct file analysis of 50+ files across backend and frontend. Component inventories and line counts are precise, not estimated. |
| Pitfalls | HIGH | All pitfalls identified from direct codebase grep results (444 hardcoded colors counted, 9 inline style occurrences located, 6 test files identified). Not theoretical — specific to this codebase. |

**Overall confidence:** HIGH

### Gaps to Address

- **Actual XRPBTC data state in production DB:** The key unknown before Phase 1 begins. Run the inventory queries before touching any code: `SELECT COUNT(*) FROM trade_lots WHERE symbol = 'XRPBTC' AND status != 'CLOSED'` (and same for orders and pairings). If open positions exist, a data migration plan is needed before code removal begins.
- **CombinedScore hero component extraction scope:** The exact extraction boundary from `CombinedScore.jsx` for embedding in `Dashboard.jsx` was not fully mapped. Brief read of `CombinedScore.jsx` at Phase 4 planning time is needed to determine the cleanest split point.
- **Light mode toggle decision:** Research recommends dark-only for v2.0. If a toggle is required, Phase 3 scope expands (two full theme sets, toggle button, FOWT script covers both directions). Confirm intent before Phase 3 planning.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis — 12 CSS files audited, 444 hardcoded hex values counted via `grep`
- `OrderblockChart.jsx` — lightweight-charts API usage confirmed (`createChart`, `applyOptions`, `ColorType.Solid`)
- `Orderblock.jsx` lines 344-370 — Recharts inline color props confirmed
- `App.jsx`, `GlobalNav.jsx`, `SymbolLayout.jsx` — current navigation structure confirmed
- `index.css` — existing 30+ CSS custom properties confirmed
- `package.json` — dependency versions confirmed (lightweight-charts ^5.1.0, Recharts ^3.7.0, React Router ^7.13.0)
- Backend `symbol_registry.py`, `domain/models.py`, `services/order_service.py`, `services/pairing_service.py` — cross-pair code surface confirmed
- XRPBTC grep across full repository — 51 files referencing XRPBTC

### Secondary (MEDIUM confidence)
- WCAG 2.1 Success Criterion 1.4.3 (4.5:1 contrast minimum) and 1.4.6 (7:1 AAA) — well-established standard
- Trading platform dark mode conventions (TradingView, Binance, Coinbase Pro, Kraken) — color palette illustrative, consistent across sources from training data
- Material Design 3 surface hierarchy pattern — established convention, matches observed trading app patterns
- FOWT blocking script pattern — well-documented in web development community, standard mitigation

### Tertiary (LOW confidence)
- Current TradingView/Binance exact hex values — may have changed since training data cutoff; palette values in FEATURES.md are guidelines, not binding

---
*Research completed: 2026-02-23*
*Ready for roadmap: yes*
