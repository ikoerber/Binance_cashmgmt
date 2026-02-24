# Project Research Summary

**Project:** Cashflow Management App — v2.0 Frontend Redesign
**Domain:** Crypto trading dashboard — dark mode migration, navigation restructuring, XRPBTC removal
**Researched:** 2026-02-23
**Confidence:** HIGH

## Executive Summary

This milestone is a purely structural frontend/backend upgrade with no new dependencies and no new business logic. The work decomposes into three independent but intersecting workstreams: (1) removing the XRPBTC trading pair from the full stack, (2) migrating the CSS color system to CSS custom properties enabling dark mode, and (3) restructuring navigation from 7 flat tabs into a 3-section layout. All three workstreams rely exclusively on tools already installed — CSS Custom Properties, React Router nested routes, and the lightweight-charts/Recharts libraries in use today. No library installations are required.

The recommended execution order is sequential with one allowed parallelism: XRPBTC removal runs first and is the highest-risk operation due to live Binance orders and historical database data that must be resolved before any code is deleted. The CSS variable foundation work is purely additive and can run in parallel with XRPBTC backend removal on a separate branch. Dark mode activation depends on the variable foundation being complete. Navigation restructuring runs last, as it depends on a clean 3-symbol list and dark-mode-aware CSS tokens. The critical technical insight is that dark mode requires converting approximately 444 hardcoded hex values across 12 CSS files to `var()` references — this variable extraction must be completed and verified (light mode visually unchanged) before any `[data-theme="dark"]` override block is added. Attempting both steps together produces a half-themed result that is worse than the starting state and is difficult to debug.

The three primary risks are: (1) XRPBTC data in the database — open lots, active Binance orders, and historical pairings must be inventoried and resolved before code removal begins; (2) hardcoded colors in component CSS that survive an incomplete migration and produce broken visuals in specific components or states (hover, selected rows, gradients); and (3) chart libraries that are fully decoupled from the CSS cascade and require explicit programmatic re-theming via `chart.applyOptions()` and `getComputedStyle()`. All three risks are preventable with the specific strategies documented in the research and are recoverable with low-to-medium effort if they occur.

## Key Findings

### Recommended Stack

No new packages are needed for any part of this milestone. The implementation uses CSS Custom Properties (already partially used in `index.css` with ~30 tokens), React Router v7 (already used for `SymbolLayout` nested routes), `lightweight-charts` v5.1 (already integrated; `applyOptions()` handles live chart re-theming without recreating the instance), and Recharts v3.7 (already integrated; colors accepted as props, read from CSS variables via `getComputedStyle()`).

**Core technologies:**
- CSS Custom Properties (`[data-theme="dark"]` override on `<html>`) — dark mode theming; extends the existing partial token system in `index.css` to ~80 tokens; zero runtime cost, full browser support
- `useTheme` hook + `localStorage` — theme persistence; 15-line custom hook is sufficient for a single-user SPA; no external library needed
- Blocking inline script in `index.html` `<head>` — prevents Flash of Wrong Theme (FOWT); must run synchronously before React initializes and before CSS is evaluated
- React Router v7 nested routes (`<Outlet>`) — 3-section navigation; pattern already used for `SymbolLayout`, extended to section-level layouts
- `lightweight-charts` v5 `applyOptions()` — live chart re-theming; do NOT recreate the chart on theme toggle (causes visible flicker and loses scroll position)
- `getComputedStyle()` + Recharts props — Recharts is SVG-based and does not read CSS variables natively; read resolved token values in JS and pass to `stroke`/`fill`/`contentStyle` props

### Expected Features

**Must have (table stakes) — v2.0 launch:**
- XRPBTC removal from symbol registry, backend domain/services/API, frontend components, and CSS — simplifies the codebase before visual work begins
- CSS custom property design system with `[data-theme="dark"]` token set in `index.css` — foundation for all dark mode features
- Dark mode applied to all 12 CSS files (~444 hardcoded hex values replaced with `var()` references)
- Dark navbar replacing the current purple gradient (`linear-gradient(135deg, #667eea, #764ba2)`) with a flat dark surface; gradients look garish in dark mode
- 3-section navigation (Trading / Orderblocks / Admin) with symbol selector pills permanently in the navbar right
- Combined Score hero widget integrated into Dashboard (above KPI grid); standalone `/s/:symbol/combined` route removed
- Dark-adapted lightweight-charts configuration (background, axis text, grid via `applyOptions()`)
- Dark form controls, dark tables with readable row alternation, dark modals, dark notification banners
- Profit/loss colors shifted one step brighter for dark backgrounds (`#22c55e` green, `#ef4444` red) to maintain WCAG AA contrast

**Should have — complete in same milestone:**
- Blocking inline script in `index.html` for FOWT prevention
- `useChartTheme()` hook providing consistent theme colors to both lightweight-charts and Recharts
- Old URL redirect rules: `/s/:symbol/combined` → `/s/:symbol` via React Router `<Navigate>`
- Cross-pair CSS artifacts fully purged from `PairingPanel.css` (`.dual-route-section`, `.cross-pair-toggle`, `.pair-origin-badge` classes)
- API Docs link removed from navbar

**Defer to v2.x+:**
- Light/dark mode toggle (user requested dark mode — ship dark-only; add toggle only if explicitly requested)
- Animated page transitions between sections
- Custom accent color picker in Settings
- Mobile responsive redesign

### Architecture Approach

Three workstreams with well-defined intersection points. XRPBTC removal is backend-first: removing the `symbol_registry.py` entry causes all dependent code to surface as explicit failures; fix each consumer in turn. Dark mode is CSS-first: expand the `index.css` token set, convert all 12 component CSS files one at a time, then add the `[data-theme="dark"]` block. Navigation restructure is router+layout-first: new `AppShell.jsx` with 3-section nav, restructured `App.jsx` routes, `Dashboard.jsx` extended to absorb the Combined Score hero. The key architectural constraint is that component CSS files must contain zero `[data-theme="dark"]` selectors — all theming lives exclusively in `index.css`. This guarantees a single source of truth for theme values and eliminates specificity conflicts between component selectors and theme overrides.

**Major components:**
1. `index.css` — Single source of truth for all color tokens; light theme in `:root`, dark overrides in `[data-theme="dark"]`; all 12 component CSS files reference only `var()` names, never raw hex values
2. `useTheme` hook + blocking `index.html` script — Theme state, `localStorage` persistence, `data-theme` attribute on `<html>`, FOWT prevention
3. `AppShell.jsx` + redesigned `GlobalNav.jsx` — 3-section top navigation with symbol pills and theme toggle; horizontal layout, not sidebar (data-dense trading app needs full viewport width)
4. `Dashboard.jsx` (extended) — Absorbs CombinedScore hero widget above KPI grid; combined score detail section collapsible below
5. `OrderblockChart.jsx` + `useChartTheme()` hook — Chart theme reactivity: lightweight-charts via `applyOptions()`, Recharts via resolved CSS variable props
6. Backend `symbol_registry.py` + ~10 backend service/domain files — XRPBTC purge: `RouteDetails`, `DualRouteComparison`, `RoutingDecision` models removed; cross-pair routing block, satoshi encoding, and BTC-quote cost paths removed

**Key patterns to follow:**
- Variables-only in component CSS: never add a `[data-theme]` selector inside a component file; only `index.css` defines theme variants
- Feature removal via registry: remove from Symbol Registry first, collect all cascading failures, fix each consumer systematically
- Chart re-theming via live `applyOptions()`/`getComputedStyle()` — never recreate chart instances on theme change

### Critical Pitfalls

1. **Partial dark mode migration — 444 hardcoded hex values across 12 CSS files.** The worst offenders are `PairingPanel.css` (88 values), `Orderblock.css` (83), `LotsTable.css` (68), `Reconciliation.css` (49), `CombinedScore.css` (40). Additionally 9 inline style occurrences in JSX files. Approach: audit ALL files with `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` before writing any dark theme code; target zero matches outside `:root` variable definitions before proceeding to Phase 3.

2. **Chart libraries decoupled from the CSS cascade.** `lightweight-charts` renders to `<canvas>` — CSS variables have zero effect. `Recharts` renders SVG but colors are set as JSX props, not CSS. Both must be re-themed programmatically. Use `chart.applyOptions()` in a `useEffect([theme])` dependency. Use a shared `useChartTheme()` hook for Recharts that calls `getComputedStyle(document.documentElement).getPropertyValue('--token-name')` to read resolved values.

3. **Orphaned XRPBTC data in the production database.** Before touching any code: query for open lots (`SELECT COUNT(*) FROM trade_lots WHERE symbol='XRPBTC' AND status!='CLOSED'`), live Binance orders (`status IN ('NEW','PARTIALLY_FILLED')`), and active pairings. Cancel any live Binance XRPBTC orders before deploying code removal. Run an Alembic migration to close any open XRPBTC lots. DO NOT drop historical columns (`base_asset`, `routing_decision_json`, `cost_eur`) — keep for audit integrity.

4. **CSS specificity wars with existing `!important` and complex selectors.** `LotsTable.css` already uses `!important` on `background` for warning rows; `PairingPanel.css` uses `!important` on `color`. These block clean theme overrides. Also 15+ `linear-gradient()` occurrences use hardcoded hex pairs. Resolution in Phase 2: extract colors from within complex selectors (`:nth-child`, `:hover`, `.selected`) into variables first; resolve all `!important` usage; convert gradients to `linear-gradient(var(--x), var(--y))` form.

5. **Flash of Wrong Theme on page load.** React-based theme switching happens after JS parses and React initializes — the browser renders light mode for 100-300ms first. Prevention: add a synchronous blocking `<script>` in `index.html` `<head>` (before any CSS) that reads `localStorage` or `prefers-color-scheme` and sets `document.documentElement.setAttribute('data-theme', theme)`. Must be part of the initial Phase 3 implementation, not an afterthought.

## Implications for Roadmap

Based on combined research, the suggested phase structure:

### Phase 1: XRPBTC Removal (Backend + Frontend)

**Rationale:** Highest-risk workstream due to live financial data. Must run before navigation restructuring (navigation depends on a clean 3-symbol list) and before CSS work touches `PairingPanel.css` (XRPBTC-specific selectors there should be deleted, not converted to variables). Backend-first: remove `symbol_registry.py` entry, run test suite, fix each cascading failure.
**Delivers:** Clean EUR-only codebase — 3 trading pairs (BTCEUR, ETHEUR, XRPEUR), simplified domain models (no `RouteDetails`/`DualRouteComparison`/`RoutingDecision`), simplified API endpoints (no `base_asset`/`xrpbtc_price` params), ~400 lines of backend code removed, ~150 lines of frontend code removed, 3 test files deleted, 3 test files modified.
**Addresses:** XRPBTC pill from nav, cross-pair toggle in PairingPanel, dual-route comparison in SimulationModal, `toEur()` conversion in Overview.jsx, BTC-quote routing block in order service.
**Avoids:** Pitfall 3 (orphaned DB data), Pitfall 4 (broken test cascade).

Pre-deployment checklist:
- Query production DB for open XRPBTC lots, live orders, active pairings before any code change
- Cancel live Binance XRPBTC orders if they exist
- Alembic migration: close any open XRPBTC lots (`status = CLOSED`, `qty_base_open = 0`)

### Phase 2: CSS Variable Foundation

**Rationale:** Pure CSS refactoring with no visual change — all hardcoded hex values become custom properties while the light theme remains pixel-identical. This is a prerequisite for dark mode activation: if any color remains hardcoded when the `[data-theme="dark"]` block is added, that component will be stuck in light mode. Keeping this step separate makes it independently verifiable.
**Delivers:** All 12 CSS files using only `var()` references for color; `index.css` expanded to ~80 light-theme tokens; zero hardcoded colors in component CSS and JSX inline styles; all `!important` usages resolved; all gradient backgrounds using variable-based color pairs.
**Uses:** CSS Custom Properties only — no new libraries.
**Avoids:** Pitfall 1 (partial migration), Pitfall 4 (specificity wars — gradients and complex selectors converted here, not during dark mode activation).

Priority file order (most hardcoded to least): `PairingPanel.css` (88), `Orderblock.css` (83), `LotsTable.css` (68), `Reconciliation.css` (49), `CombinedScore.css` (40), `Overview.css` (24), `App.css` (16), `Dashboard.css` (15), `AlertBanner.css` (14), `Settings.css` (12), `FillNotification.css` (5).

### Phase 3: Dark Mode Activation + Theme Toggle

**Rationale:** With all colors as variables (Phase 2 complete), adding dark mode is adding a single `[data-theme="dark"]` block to `index.css`. Chart library theming and FOWT prevention are the remaining non-trivial work.
**Delivers:** Fully functional dark mode across all components; FOWT-free page load; persistent theme preference in `localStorage`; theme toggle icon in GlobalNav; lightweight-charts and Recharts adapting dynamically to theme changes.
**Uses:** CSS Custom Properties (`[data-theme="dark"]`), `useTheme` hook, blocking `index.html` script, `chart.applyOptions()`, `getComputedStyle()`.
**Avoids:** Pitfall 2 (chart theme mismatch), Pitfall 5 (FOWT).

Dark palette summary: page background `#0f172a`, card background `#1e293b`, elevated surface `#334155`, primary text `#f1f5f9`, profit `#22c55e` (brighter than light mode for WCAG AA), loss `#ef4444`, accent backgrounds via `rgba(color, 0.15)` pattern instead of light-mode tint colors.

### Phase 4: Navigation Restructure + Dashboard Integration

**Rationale:** Depends on Phase 1 (clean 3-symbol list), Phase 3 (dark-mode-aware CSS tokens available for new nav components). Last because it touches the most component files and has the highest UX regression risk — stability of the visual system from earlier phases reduces debugging scope.
**Delivers:** 3-section top navigation (Trading / Orderblocks / Admin), symbol selector pills permanently in navbar, Combined Score hero embedded in Dashboard above KPI grid, `/s/:symbol/combined` route removed, API Docs link removed, redirect rules for bookmarked old URLs.
**Implements:** `AppShell.jsx` layout component, restructured `App.jsx` routes, `Dashboard.jsx` extended with CombinedScore hero extraction.
**Avoids:** Navigation state loss (filter selections, pairing panel state preserved across section switches), broken bookmarks (`<Navigate>` redirect rules).

### Phase Ordering Rationale

- **Phase 1 before all others:** XRPBTC data migration is the only operation that can cause irreversible financial data issues if mis-sequenced; isolating it first makes any failure immediately attributable and independently testable
- **Phase 2 before Phase 3:** Variable extraction and dark theme activation are distinct, independently verifiable steps; mixing them makes visual regressions unattributable
- **Phases 1 and 2 can run in parallel:** CSS conversion is entirely independent of backend business logic; a separate branch is viable if bandwidth allows
- **Phase 3 before Phase 4:** New navigation components need dark-mode-aware tokens from the start; retro-fitting dark mode onto newly-written navigation components would be a second pass of Phase 2 work
- **Phase 4 last:** Touches the most component files; benefits from a stable visual system and a clean symbol list

### Research Flags

All four phases have well-documented patterns and complete file inventories — no phases require `/gsd:research-phase` during planning:

- **Phase 1 (XRPBTC Removal):** ARCHITECTURE.md provides a complete file inventory (50+ files catalogued with specific line counts). Test strategy is fully specified. Only unknown is the actual production DB state — addressed by the pre-deployment query checklist.
- **Phase 2 (CSS Variable Foundation):** Mechanical conversion. PITFALLS.md provides exact hardcoded value counts per file. Verification command known.
- **Phase 3 (Dark Mode Activation):** Complete dark palette specified in FEATURES.md and STACK.md with WCAG contrast ratios. lightweight-charts and Recharts integration patterns confirmed from direct codebase analysis.
- **Phase 4 (Navigation):** Route structure and component responsibilities fully mapped in ARCHITECTURE.md and STACK.md. React Router `<Outlet>` pattern already in use.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies already installed and in active use. Patterns confirmed via direct codebase inspection. Zero speculation. |
| Features | HIGH | Based on thorough codebase audit (12 CSS files, 444 hardcoded values counted via `grep`, 9 JSX inline styles located). Color palette derived from WCAG math, not copied from competitor training data. |
| Architecture | HIGH | Based on direct file analysis of 50+ files across backend and frontend. Component inventories and line counts are precise, not estimated. Cross-pair code surface confirmed via `grep` (51 files referencing XRPBTC). |
| Pitfalls | HIGH | All pitfalls identified from direct codebase grep results, not theoretical. Two existing `!important` usages located. Six test files directly affected by XRPBTC removal confirmed. chart API verified from existing code. |

**Overall confidence:** HIGH

### Gaps to Address

- **Actual XRPBTC data state in production DB:** The most important unknown before Phase 1 begins. Run inventory queries before touching any code. If open XRPBTC positions or live orders exist, a data migration sub-plan is needed (the approach is clear from PITFALLS.md; only the specific counts are unknown).
- **CombinedScore hero extraction boundary:** The exact split point from `CombinedScore.jsx` for embedding in `Dashboard.jsx` was not mapped in detail. A brief read of `CombinedScore.jsx` at Phase 4 planning time will determine the cleanest component boundary.
- **Dynamic inline styles in JSX:** `CombinedScore.jsx` uses a dynamic `action_color` variable as an inline style (the color is computed at runtime from signal data). Converting this to CSS variables is not straightforward. Decision needed at Phase 2/3: either a `useChartTheme()`-style JS theme object that maps signal states to dark-mode-aware colors, or a CSS class per signal state (e.g., `.action-bullish`, `.action-bearish`) with colors defined in `index.css`.
- **Light/dark toggle scope:** Research recommends dark-only for v2.0. If a toggle is required, Phase 3 scope increases significantly (full light theme token set must be explicitly maintained; FOWT script must handle both directions; toggle UI needs design). Confirm intent before Phase 3 planning.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis — 12 CSS files audited, 444 hardcoded hex values counted via `grep`; 50+ backend and frontend files inspected
- `OrderblockChart.jsx` — lightweight-charts API usage (`createChart`, `applyOptions`, `ColorType.Solid`) confirmed from existing code
- `Orderblock.jsx` lines 344-370 — Recharts inline color props confirmed
- `App.jsx`, `GlobalNav.jsx`, `SymbolLayout.jsx` — current navigation structure and route patterns confirmed
- `index.css` — existing 30+ CSS custom properties confirmed
- `package.json` — dependency versions confirmed (lightweight-charts ^5.1.0, Recharts ^3.7.0, React Router ^7.13.0)
- Backend `symbol_registry.py`, `domain/models.py`, `services/order_service.py`, `services/pairing_service.py` — cross-pair code surface confirmed via grep (51 files referencing XRPBTC)

### Secondary (MEDIUM confidence)
- WCAG 2.1 Success Criterion 1.4.3 (contrast minimum 4.5:1) and 1.4.6 (AAA 7:1) — well-established standard; used to derive dark mode profit/loss color shifts
- Material Design 3 surface hierarchy pattern — established convention matching observed trading platform patterns
- FOWT blocking script pattern — well-documented in web development community; standard mitigation

### Tertiary (LOW confidence)
- TradingView, Binance, Coinbase Pro, Kraken dark mode color values — from training data, not live-verified; used for orientation only. Palette values in FEATURES.md are WCAG-derived, not copied from competitors.

---
*Research completed: 2026-02-23*
*Ready for roadmap: yes*
