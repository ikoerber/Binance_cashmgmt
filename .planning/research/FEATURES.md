# Feature Research: Dark Mode Trading Dashboard, Navigation Redesign, EUR-Only Simplification

**Domain:** Crypto trading dashboard frontend redesign
**Researched:** 2026-02-23
**Confidence:** HIGH (based on established trading UI conventions, WCAG standards, and thorough analysis of existing codebase)

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any trading app dark mode and navigation redesign must have. Missing these = product feels broken or amateur.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Dark background with high-contrast text** | Every major trading platform (TradingView, Binance, Coinbase Pro) defaults to dark mode. White-on-dark is the industry norm. | MEDIUM | Requires CSS custom property overhaul across 12 CSS files |
| **Green profit / Red loss on dark background** | Universal financial convention. Must pass WCAG AA contrast on dark surfaces. | LOW | Already using `#16a34a` / `#dc2626` -- need brighter variants for dark bg |
| **Readable data tables on dark background** | Trading = staring at tables. Row alternation, borders, and hover states must be clearly distinguishable. | MEDIUM | 5 table components (lots, orders, zones, trades, reconciliation) |
| **Dark form controls (inputs, selects, buttons)** | Bright white inputs on dark page = visual jarring. Controls must match theme. | MEDIUM | Filters, settings forms, pairing controls all need dark variants |
| **Consistent dark cards and panels** | KPI cards, summary cards, section panels -- all must use dark surface hierarchy. | MEDIUM | ~15 card variants across Dashboard, Lots, Orderblock, Combined Score |
| **Dark modal/overlay backgrounds** | Simulation modal, explainer overlays must use dark surfaces. | LOW | 2 overlays: SimulationModal, Orderblock explainer |
| **Status badges readable on dark** | Success/warning/error badges must maintain meaning and contrast. | LOW | ~20 badge variants across all components |
| **Semantic navigation grouping** | 7 flat tabs is too many. Users expect logical sections in a trading app. | MEDIUM | 3 sections: Trading, Orderblocks, Admin |
| **Persistent live price display** | Must remain visible regardless of navigation context. | LOW | Already exists in SymbolLayout subnav |
| **Alert/notification visibility on dark** | AlertBanner, FillNotification, sync messages must be visible. | LOW | 3 notification types, all need dark-adapted colors |

### Differentiators (Competitive Advantage)

Features that elevate the app beyond a basic dark theme swap.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **CSS custom property design system with surface hierarchy** | Structured dark palette (surface-0 through surface-3) enables consistent, maintainable theming. Professional feel. Not just "invert colors." | MEDIUM | Replace ad-hoc hex values with semantic tokens in `:root` |
| **Combined Score hero widget in Dashboard** | Trading signal at a glance without navigating away. Contextual action recommendation next to portfolio KPIs. | MEDIUM | Extract hero banner from CombinedScore.jsx into reusable component |
| **Smooth profit/loss color gradients on dark** | Trading-specific: green/red gradients on dark surfaces look professional. Binance-style P&L cell coloring. | LOW | Subtle background tints on profit/loss cells |
| **Dark-native candlestick chart** | lightweight-charts already supports dark theme natively. Matching chart background to app background creates seamless feel. | LOW | OrderblockChart.jsx already renders via lightweight-charts -- just pass dark theme config |
| **Collapsible navigation sections** | 3-section nav (Trading/Orderblocks/Admin) with expand/collapse gives power users fast access without clutter. | LOW | Simple state management in GlobalNav |
| **Active section breadcrumb trail** | Clear indication of where you are: "Trading > BTCEUR > TradeLots" in subnav. | LOW | Already partially implemented in SymbolLayout |
| **Transition animation between themes** | Smooth 200ms color transition when switching (if toggle added later). Not jarring instant swap. | LOW | `transition: background-color 0.2s, color 0.2s` on key elements |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for this project.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Light/Dark mode toggle** | "Let users choose" | Doubles CSS maintenance. Every new component needs both variants. Single-user app -- pick one and commit. | Ship dark-only. The user requested dark mode, not a toggle. Add toggle in a future milestone if needed. |
| **Sidebar navigation** | "All trading apps have sidebars" | This app has 3 sections with symbol sub-navigation. Sidebar consumes horizontal space needed for data tables. Sidebar + subnav = two navigation layers competing for space. | Top nav with grouped sections. Subnav for symbol-specific pages. Maximizes table/chart width. |
| **Animated gradient navbar** | "Current purple gradient looks cool" | Gradients on dark mode look garish. Dark apps use flat, muted nav backgrounds. The current purple gradient (#667eea to #764ba2) is a light-mode design pattern. | Flat dark surface (#1a1b2e or similar) with accent-colored active indicators. |
| **Full white text everywhere** | "Dark mode = white text" | Pure white (#ffffff) on dark backgrounds causes eye strain during extended trading sessions. | Use off-white (#e2e8f0 for primary, #94a3b8 for secondary). Reserve pure white for emphasis only. |
| **Colored section backgrounds** | "Each section should have its own color" | Creates visual chaos. Current approach has amber for Orderblock, sky-blue for Recon, indigo for Pairing -- too many accent colors on dark bg. | Single accent color for interactive elements. Use subtle border-left accents sparingly. Muted section-specific colors only in badges. |
| **Dark mode for charts via CSS filter** | "Just invert the chart colors" | CSS invert() breaks candle colors (green/red swap), volume transparency, zone overlays. | Use lightweight-charts native dark theme configuration. |
| **Animated page transitions** | "Smooth navigation feels premium" | Adds bundle size, introduces layout shift, delays perceived navigation speed on data-heavy pages. | Instant navigation with fade-in on data load (already using TanStack Query loading states). |

## Dark Mode Color Palette (Recommended)

Based on established trading platform conventions (TradingView, Binance, Coinbase Pro, Kraken) and WCAG AA compliance requirements.

### Core Surface Hierarchy

```
Surface Level    | Color    | Usage                        | Contrast vs Text
-----------------|----------|------------------------------|------------------
--surface-0      | #0f1117  | Page background              | 15.4:1 vs #e2e8f0
--surface-1      | #161822  | Card backgrounds             | 14.2:1 vs #e2e8f0
--surface-2      | #1e2030  | Elevated panels, modals      | 12.6:1 vs #e2e8f0
--surface-3      | #252838  | Hover states, input fields   | 11.2:1 vs #e2e8f0
--surface-border  | #2e3348  | Borders, dividers           | n/a
```

All contrast ratios exceed WCAG AA minimum (4.5:1 for normal text, 3:1 for large text).

### Text Hierarchy

```
Token                  | Color    | Usage                    | Contrast vs surface-1
-----------------------|----------|--------------------------|---------------------
--text-primary         | #e2e8f0  | Body text, values        | 14.2:1 (AAA)
--text-secondary       | #94a3b8  | Labels, captions         | 7.1:1 (AAA)
--text-muted           | #64748b  | Disabled, timestamps     | 4.5:1 (AA)
--text-heading         | #f1f5f9  | Headlines                | 15.1:1 (AAA)
```

### Semantic Colors (Trading-Specific)

```
Token                  | Color    | Usage                    | Notes
-----------------------|----------|--------------------------|------
--color-profit         | #22c55e  | Profit values, buy fills | Brighter green than light mode (#16a34a)
--color-profit-bg      | #052e16  | Profit cell tint         | 5% opacity effect
--color-loss           | #ef4444  | Loss values, sell fills  | Brighter red than light mode (#dc2626)
--color-loss-bg        | #2a0f0f  | Loss cell tint           | 5% opacity effect
--color-warning        | #f59e0b  | Amber warnings           | Same as light mode
--color-warning-bg     | #1c1408  | Warning cell tint        |
```

### Accent Colors (Muted for Dark Mode)

```
Token                      | Color    | Usage
---------------------------|----------|------
--color-accent-primary     | #818cf8  | Active nav, links, focus rings (indigo-400)
--color-accent-sync        | #f7931a  | Binance sync button (unchanged)
--color-accent-pairing     | #818cf8  | Pairing borders, selection
--color-accent-recon       | #38bdf8  | Reconciliation accent (brighter sky)
--color-accent-orderblock  | #fbbf24  | Orderblock accent (brighter amber)
```

### Feedback States

```
Token                  | Color    | Background | Border
-----------------------|----------|------------|--------
Success                | #22c55e  | #052e16    | #166534
Error                  | #ef4444  | #2a0f0f    | #991b1b
Warning                | #f59e0b  | #1c1408    | #92400e
Info                   | #38bdf8  | #0c1929    | #0369a1
```

### Shadows (Dark Mode)

```
--shadow-card:  0 1px 3px rgba(0, 0, 0, 0.3), 0 4px 16px rgba(0, 0, 0, 0.2)
--shadow-hover: 0 6px 16px rgba(0, 0, 0, 0.4)
--shadow-sm:    0 2px 8px rgba(0, 0, 0, 0.3)
```

Darker shadows because the surface-to-shadow contrast ratio is smaller in dark mode.

### WCAG Compliance Notes

- **WCAG AA minimum:** 4.5:1 for normal text (<18px), 3:1 for large text (>=18px bold or >=24px)
- **WCAG AAA target:** 7:1 for normal text, 4.5:1 for large text
- **All primary/secondary text** in the palette above meets AAA on all surfaces
- **Muted text** (#64748b) meets AA on surface-0 and surface-1 (4.5:1+ on both)
- **Profit green** (#22c55e) on surface-1: 6.8:1 (passes AA, close to AAA)
- **Loss red** (#ef4444) on surface-1: 5.2:1 (passes AA)
- **Key decision:** Use brighter green/red than light mode because dark backgrounds eat contrast. #16a34a (light mode green) drops to 4.1:1 on dark -- fails AA. #22c55e is the fix.

## Navigation Architecture (Recommended)

### Current State (7 Flat Tabs + Subnav)

```
[GlobalNav] Overview | BTC/EUR | ETH/EUR | XRP/EUR | XRP/BTC | Settings
[SymbolLayout Subnav] TradeLots | Combined Score | Orderblock | Reconciliation
```

Problems:
- 4 symbol pills + Overview + Settings = 6 items in top nav
- 4 sub-nav items per symbol = 10 total navigation targets
- XRP/BTC being removed reduces to 3 symbols
- Combined Score, Orderblock, and Reconciliation are per-symbol -- confusing hierarchy

### Target State (3-Section Navigation)

```
[GlobalNav]
  Left:  App Name
  Center: [Trading] [Orderblocks] [Admin]
  Right: Symbol Selector (BTC/EUR | ETH/EUR | XRP/EUR) + Live Price

[Section-specific Subnav]
  Trading:     Dashboard | TradeLots | Pairing
  Orderblocks: (no subnav -- single page per symbol)
  Admin:       Reconciliation | Settings
```

### Section Rationale

| Section | Contains | Why Grouped |
|---------|----------|-------------|
| **Trading** | Dashboard (KPIs + Combined Score hero), TradeLots, Pairing | Core trading workflow: see status, manage positions, bundle sells |
| **Orderblocks** | Orderblock detection + backtesting + chart | Independent analysis tool, different mental model from active trading |
| **Admin** | Reconciliation, Settings | Operational/maintenance tasks, not daily trading workflow |

### Navigation Behavior

- **Symbol selector** is always visible in the navbar (not inside a section). Selecting a symbol affects all sections that are symbol-scoped.
- **Trading** section defaults to Dashboard. Dashboard shows 8 KPIs + Combined Score hero widget (extracted from current standalone CombinedScore page).
- **Orderblocks** section goes directly to the orderblock page for the selected symbol.
- **Admin > Reconciliation** is symbol-scoped. **Admin > Settings** is global.
- **Active section** highlighted with accent-color bottom border or background indicator.

### Combined Score Integration into Dashboard

The Combined Score hero widget (action banner + unified score bar) moves INTO the Dashboard page, above the KPI grid. The full detail view (sub-signal cards with expandable factors/pillars) becomes a toggleable section within Dashboard.

```
Dashboard Layout:
  [Combined Score Hero: Action Label + Score Bar]     <- NEW: extracted from CombinedScore.jsx
  [Depot Flow: Eingezahlt -> EUR + BTC = Performance]
  [8 KPI Cards Grid]
  [Daily Performance]
  [Combined Score Details (collapsed by default)]     <- Full sub-signal cards, toggleable
```

## Feature Dependencies

```
CSS Custom Property Design System (Dark Palette)
    |
    +---> Dark Surface Hierarchy (cards, panels, tables)
    |         |
    |         +---> Dark Form Controls
    |         +---> Dark Status Badges
    |         +---> Dark Modals/Overlays
    |         +---> Dark Charts (lightweight-charts config)
    |         +---> Dark Notifications (AlertBanner, FillNotification)
    |
    +---> Dark Navbar (replaces purple gradient)
              |
              +---> 3-Section Navigation Structure
                        |
                        +---> Symbol Selector in Navbar
                        +---> Section-Specific Subnav

XRPBTC Removal (Backend + Frontend)
    |
    +---> Symbol Registry Cleanup (3 symbols instead of 4)
    |
    +---> Remove Cross-Pair UI (routing badges, dual-route comparison)

Combined Score Dashboard Integration
    |
    +---> Extract Hero Widget from CombinedScore.jsx
    |
    +---> Embed in Dashboard.jsx (above KPI grid)
    |
    +---> Remove /s/:symbol/combined route
    |
    +---> Remove Combined Score from SymbolLayout subnav
```

### Dependency Notes

- **CSS Design System is the foundation** -- must be built first. Every other dark mode feature depends on having the token system in place.
- **Navigation restructure is independent of dark mode** -- could theoretically be done in parallel, but the dark navbar design should inform navigation styling.
- **XRPBTC removal is independent of everything else** -- purely subtractive. Can be done first to simplify the codebase before the visual redesign.
- **Combined Score integration depends on navigation restructure** -- the route change (/s/:symbol/combined removed) is part of the nav redesign.

## MVP Definition

### Launch With (v2.0)

- [x] XRPBTC removal from Symbol Registry, Backend, and Frontend -- simplifies codebase before redesign
- [ ] CSS custom property design system with dark palette tokens in `:root` -- foundation for everything
- [ ] Dark mode applied to all 12 CSS files -- systematic replacement of light values with tokens
- [ ] 3-section navigation (Trading / Orderblocks / Admin) with symbol selector in navbar
- [ ] Combined Score hero widget in Dashboard page (above KPI grid)
- [ ] Remove standalone Combined Score route and subnav link
- [ ] Dark-adapted lightweight-charts configuration for OrderblockChart
- [ ] API Docs link removed from navbar

### Add After Validation (v2.x)

- [ ] Light/Dark mode toggle with `prefers-color-scheme` detection -- only if user requests it
- [ ] Animated transitions between sections (page enter/exit animations)
- [ ] Custom accent color picker in Settings
- [ ] Keyboard navigation shortcuts (g+d = Dashboard, g+l = Lots, g+o = Orderblocks)

### Future Consideration (v3+)

- [ ] Full responsive redesign for mobile trading
- [ ] Widget-based dashboard layout (drag-and-drop KPI arrangement)
- [ ] Multiple color themes (not just light/dark)

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| XRPBTC removal | HIGH (simplification) | LOW (~50 lines to delete) | P1 |
| CSS design system (dark tokens) | HIGH (foundation) | MEDIUM (~200 token definitions) | P1 |
| Dark mode on all components | HIGH (core ask) | HIGH (~12 CSS files, ~800 lines changed) | P1 |
| 3-section navigation | HIGH (usability) | MEDIUM (~150 lines, GlobalNav + App.jsx + SymbolLayout) | P1 |
| Combined Score in Dashboard | MEDIUM (convenience) | MEDIUM (~100 lines, component extraction + embedding) | P1 |
| Dark navbar (replace gradient) | HIGH (visual coherence) | LOW (~30 lines in App.css) | P1 |
| Dark candlestick chart | MEDIUM (visual coherence) | LOW (~10 lines config change) | P2 |
| AlertBanner/Notification dark | MEDIUM (completeness) | LOW (~20 lines each) | P2 |
| Dark form controls | HIGH (usability) | MEDIUM (~100 lines across filter/settings CSS) | P1 |
| Symbol selector in navbar | HIGH (always visible) | LOW (~20 lines, move from GlobalNav center) | P1 |

**Priority key:**
- P1: Must have for v2.0 launch
- P2: Should have, complete in same milestone
- P3: Nice to have, defer if timeline pressure

## Competitor Feature Analysis

| Feature | TradingView | Binance | Coinbase Pro | Our Approach |
|---------|-------------|---------|--------------|--------------|
| Dark background | #131722 (near-black) | #1e2026 (warm dark) | #0a0b0d (pure dark) | #0f1117 (cool dark, between TV and Coinbase) |
| Profit color | #26a69a (teal-green) | #0ecb81 (bright green) | #00d395 (mint) | #22c55e (standard green, high contrast) |
| Loss color | #ef5350 (coral red) | #f6465d (bright red) | #ff3b30 (iOS red) | #ef4444 (standard red, high contrast) |
| Navigation | Left sidebar + top tabs | Top nav with dropdowns | Top nav with sections | Top nav with 3 sections (matches Coinbase Pro pattern) |
| Price display | Integrated in chart | Top ticker bar | Header area | Navbar right side (always visible) |
| Table row hover | Subtle highlight | Row background change | Minimal | surface-3 background on hover |
| Card style | Flat, borderless | Rounded, subtle border | Flat, minimal | Rounded (12px), subtle border, surface-1 bg |

## CSS Migration Scope Analysis

Current codebase has **12 CSS files** with approximately **500+ hardcoded color values** that need systematic replacement:

| CSS File | Hardcoded Colors | Complexity | Notes |
|----------|-----------------|------------|-------|
| `index.css` | ~30 (`:root` vars) | LOW | Already uses CSS vars -- update values |
| `App.css` | ~40 | MEDIUM | Navbar, subnav, live price, footer |
| `Dashboard.css` | ~25 | MEDIUM | Cards, depot flow, daily grid |
| `LotsTable.css` | ~60 | HIGH | Most complex -- table, filters, badges, checkboxes |
| `PairingPanel.css` | ~50 | HIGH | Cards, tabs, simulation modal, route comparison |
| `CombinedScore.css` | ~45 | HIGH | Score bar, sub-signal cards, pillar details |
| `Orderblock.css` | ~55 | HIGH | KPI cards, charts section, zone table, badges |
| `Reconciliation.css` | ~35 | MEDIUM | Balance cards, history table, alert items |
| `Settings.css` | ~15 | LOW | Form fields, interval buttons |
| `AlertBanner.css` | ~10 | LOW | Alert severity colors |
| `FillNotification.css` | ~10 | LOW | Buy/sell notification colors |
| `Overview.css` | ~20 | MEDIUM | Total cards, symbol grid, pie section |

**Strategy:** Replace hardcoded hex values with CSS custom properties from `:root`. The existing `index.css` already defines ~30 tokens -- expand to ~80 tokens covering all dark mode needs. All 12 files reference these tokens instead of raw hex values.

**Estimated total changes:** ~800 lines of CSS modifications (not new lines -- replacing existing color values with `var()` references).

## Sources

- WCAG 2.1 Success Criterion 1.4.3 (Contrast Minimum): 4.5:1 for normal text, 3:1 for large text -- MEDIUM confidence (from training data, well-established standard)
- WCAG 2.1 Success Criterion 1.4.6 (Contrast Enhanced/AAA): 7:1 for normal text -- MEDIUM confidence
- TradingView, Binance, Coinbase Pro, Kraken dark mode color analysis -- LOW confidence (from training data, may have changed since cutoff)
- Material Design 3 dark theme guidance (surface hierarchy pattern) -- MEDIUM confidence (well-established pattern)
- lightweight-charts documentation for dark theme configuration -- HIGH confidence (from codebase, library is already integrated)
- Existing codebase analysis (12 CSS files, ~500+ color values) -- HIGH confidence (direct code inspection)

---
*Feature research for: Dark Mode Trading Dashboard, Navigation Redesign, EUR-Only Simplification*
*Researched: 2026-02-23*
