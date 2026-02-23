# Stack Research: Dark Mode, 3-Section Navigation, XRPBTC Removal

**Domain:** Frontend Redesign (CSS Theming + Navigation Restructuring)
**Researched:** 2026-02-23
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

No new dependencies. This milestone is a pure CSS + JSX restructuring project.

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| CSS Custom Properties (`:root`) | Native | Dark Mode theming, color system | Already in use (`index.css`). No build tool needed, no runtime cost, full browser support since 2017. The codebase already defines 30+ custom properties — extending to dark mode is the natural path. |
| `prefers-color-scheme` media query | Native | System-preference dark mode detection | Native CSS, zero JS for initial theme. Combined with `[data-theme]` attribute for manual toggle. |
| `[data-theme="dark"]` attribute | Native | Manual theme override on `<html>` | Standard pattern for user-controlled toggle. Overrides `prefers-color-scheme` when user explicitly chooses. |
| React Router v7 nested routes | ^7.13.0 (current) | 3-section navigation with layout routes | Already installed. Nested `<Route>` + `<Outlet>` pattern already used for `SymbolLayout`. Extend for section-level layouts. |

### Supporting Libraries

No new libraries needed.

| Library | Already Installed | Purpose | Dark Mode Impact |
|---------|-------------------|---------|-----------------|
| lightweight-charts | ^5.1.0 | Candlestick chart | Has built-in dark theme options via `layout.background` and `textColor`. Already used in `OrderblockChart.jsx` — needs theme-reactive options. |
| Recharts | ^3.7.0 | Bar/line charts | Hardcoded colors in `Orderblock.jsx` (e.g., `stroke="#e2e8f0"`). Must be refactored to read CSS custom properties or accept theme-aware props. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Browser DevTools | Theme testing | Chrome/Firefox: Application tab > Rendering > `prefers-color-scheme` emulation. Essential for testing both modes without OS toggle. |
| CSS nesting (native) | Reduce dark-mode selector verbosity | Supported in all modern browsers since 2024. Can use `[data-theme="dark"] &` nesting instead of repeated selectors. Optional but cleaner. |

## No Installation Required

```bash
# No new packages needed.
# This is a CSS-only + JSX restructuring milestone.
```

## Dark Mode Implementation Pattern

### 1. Color System Architecture

**Current state:** `index.css` defines ~30 CSS custom properties in `:root`, but 12 CSS files also contain ~200 hardcoded hex colors (e.g., `#f8fafc`, `#334155`, `#1e293b`, `background: white`).

**Target state:** ALL colors via custom properties. Two themes: light (default) and dark.

```css
/* ─── Light Theme (default) ─── */
:root {
  /* Surfaces */
  --color-bg-page: #f5f7fa;
  --color-bg-card: #ffffff;
  --color-bg-subtle: #f8fafc;
  --color-bg-muted: #f1f5f9;
  --color-bg-elevated: #ffffff;

  /* Text */
  --color-text-primary: #1e293b;
  --color-text-secondary: #64748b;
  --color-text-muted: #94a3b8;
  --color-text-heading: #1a1a2e;

  /* Borders */
  --color-border: #e2e8f0;
  --color-border-light: #f1f5f9;

  /* Semantic */
  --color-profit: #16a34a;
  --color-loss: #dc2626;

  /* Shadows */
  --shadow-card: 0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.06);
  --shadow-hover: 0 6px 16px rgba(0,0,0,0.12);

  /* Tables */
  --color-table-header-bg: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  --color-table-row-even: #fafbfd;
  --color-table-row-hover: #f8fafc;

  /* Charts */
  --color-chart-grid: #f1f5f9;
  --color-chart-text: #64748b;
  --color-chart-bg: #ffffff;
}

/* ─── Dark Theme ─── */
[data-theme="dark"] {
  /* Surfaces — Slate-900 base, card slightly elevated */
  --color-bg-page: #0f172a;
  --color-bg-card: #1e293b;
  --color-bg-subtle: #1e293b;
  --color-bg-muted: #334155;
  --color-bg-elevated: #334155;

  /* Text — flipped contrast */
  --color-text-primary: #f1f5f9;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;
  --color-text-heading: #f8fafc;

  /* Borders */
  --color-border: #334155;
  --color-border-light: #1e293b;

  /* Semantic — slightly lighter for dark backgrounds */
  --color-profit: #4ade80;
  --color-loss: #f87171;

  /* Shadows — darker, more prominent */
  --shadow-card: 0 1px 3px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.25);
  --shadow-hover: 0 6px 16px rgba(0,0,0,0.4);

  /* Tables */
  --color-table-header-bg: #1e293b;
  --color-table-row-even: #1a2536;
  --color-table-row-hover: #334155;

  /* Charts */
  --color-chart-grid: #334155;
  --color-chart-text: #94a3b8;
  --color-chart-bg: #1e293b;
}

/* System preference fallback (for users without manual toggle) */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    /* Same as [data-theme="dark"] above */
  }
}
```

### 2. Theme Toggle Pattern (React)

No library needed. Simple `localStorage` + `data-theme` attribute:

```jsx
// hooks/useTheme.js
import { useState, useEffect } from 'react';

const getInitialTheme = () => {
  const saved = localStorage.getItem('theme');
  if (saved) return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

export const useTheme = () => {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark');
  return { theme, toggleTheme };
};
```

### 3. Trading App Dark Mode Color Conventions

Trading platforms (TradingView, Binance, Bybit, Kraken) consistently use these dark mode patterns:

| Element | Convention | Our Value |
|---------|-----------|-----------|
| Page background | Very dark blue/slate (NOT pure black) | `#0f172a` (Slate-950) |
| Card background | Slightly lighter than page | `#1e293b` (Slate-800) |
| Elevated surfaces | One step lighter | `#334155` (Slate-700) |
| Primary text | Near-white (NOT pure white, hurts eyes) | `#f1f5f9` (Slate-100) |
| Profit green | Brighter green on dark | `#4ade80` (Green-400) |
| Loss red | Softer red on dark | `#f87171` (Red-400) |
| Navbar | Dark solid or subtle gradient (not colorful) | `#0f172a` with subtle border |

**Key principle:** On dark backgrounds, semantic colors (profit/loss) shift ONE step lighter on the Tailwind scale to maintain WCAG AA contrast (4.5:1 minimum for text).

**Confidence:** HIGH — These are observable conventions across TradingView, Binance Pro, Bybit, Kraken Pro. Verified by direct usage.

## Hardcoded Color Audit

**Critical finding:** 12 CSS files contain approximately 200 hardcoded hex color references that bypass the custom property system. These MUST be converted to variables before dark mode can work.

| CSS File | Hardcoded Colors | Severity |
|----------|-----------------|----------|
| `Dashboard.css` | ~15 (e.g., `color: #1a1a1a`, `background: #f8f9fa`) | HIGH |
| `LotsTable.css` | ~25 (e.g., `background: #f8fafc`, `color: #334155`) | HIGH |
| `Orderblock.css` | ~40 (e.g., `background: #fffbeb`, `color: #92400e`) | HIGH |
| `CombinedScore.css` | ~30 (e.g., `background: #eef2ff`, `color: #475569`) | HIGH |
| `PairingPanel.css` | ~35 (e.g., `background: #f8fafc`, `color: #475569`) | HIGH |
| `Reconciliation.css` | ~20 | MEDIUM |
| `Overview.css` | ~15 (e.g., `background: white`, `color: #1e293b`) | MEDIUM |
| `Settings.css` | ~10 | LOW |
| `App.css` | ~10 | MEDIUM |
| `AlertBanner.css` | ~8 | LOW |
| `FillNotification.css` | ~5 | LOW |
| `index.css` | Body hardcoded colors (separate from `:root` vars) | LOW |

**Accent colors** (Amber `#d97706`, Indigo `#6366f1`, Sky `#0ea5e9`, Orange `#f7931a`) generally work on both light and dark backgrounds but need verified contrast. Some accent-background combos (e.g., `background: #fef3c7` amber-light) need dark equivalents (e.g., `background: rgba(217,119,6,0.15)`).

### Accent Color Dark Mode Strategy

Accent colors do NOT simply invert. Use these patterns:

| Light Mode | Dark Mode | Pattern |
|------------|-----------|---------|
| `background: #fef3c7` (amber tint) | `background: rgba(217,119,6,0.15)` | Use rgba with low opacity on dark |
| `background: #eef2ff` (indigo tint) | `background: rgba(99,102,241,0.15)` | Same pattern |
| `background: #ecfdf5` (success tint) | `background: rgba(22,163,74,0.15)` | Same pattern |
| `background: #fef2f2` (error tint) | `background: rgba(220,38,38,0.15)` | Same pattern |
| `border: 1px solid #fcd34d` | `border: 1px solid rgba(252,211,77,0.3)` | Desaturate border on dark |

This is the standard pattern: on dark mode, tinted backgrounds become semi-transparent overlays of the accent color. The accent color itself stays the same (or shifts one step brighter).

### Gradient Handling

Several components use `linear-gradient()` for backgrounds:

| Current | Dark Mode Equivalent |
|---------|---------------------|
| `linear-gradient(135deg, #f8fafc, #f1f5f9)` | `linear-gradient(135deg, var(--color-bg-subtle), var(--color-bg-muted))` |
| `linear-gradient(135deg, #fffbeb, #fef3c7)` (amber section) | `linear-gradient(135deg, rgba(217,119,6,0.08), rgba(217,119,6,0.15))` |
| `linear-gradient(135deg, #f0fdf4, #ecfdf5)` (success section) | `linear-gradient(135deg, rgba(22,163,74,0.08), rgba(22,163,74,0.15))` |

These need dedicated custom properties or a consistent rgba-on-dark pattern.

## Chart Library Theme Integration

### lightweight-charts (Candlestick Chart)

The chart currently hardcodes light theme colors in `OrderblockChart.jsx`:

```javascript
// Current (hardcoded light)
layout: {
  background: { type: ColorType.Solid, color: '#ffffff' },
  textColor: '#64748b',
},
grid: {
  vertLines: { color: '#f1f5f9' },
  horzLines: { color: '#f1f5f9' },
},
```

**Dark mode approach:** Read from CSS custom properties via `getComputedStyle()`:

```javascript
const styles = getComputedStyle(document.documentElement);
const chartBg = styles.getPropertyValue('--color-chart-bg').trim();
const chartText = styles.getPropertyValue('--color-chart-text').trim();
const chartGrid = styles.getPropertyValue('--color-chart-grid').trim();
```

Then call `chart.applyOptions()` when theme changes. lightweight-charts v5 supports `applyOptions()` on live charts — no recreation needed.

**Confidence:** HIGH — `applyOptions()` is a core lightweight-charts API, confirmed from codebase usage (already used for resize).

### Recharts

Recharts in `Orderblock.jsx` hardcodes colors as JSX props:

```jsx
<CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
<XAxis dataKey="name" stroke="#64748b" fontSize={12} />
```

**Dark mode approach:** Recharts does NOT read CSS custom properties. Two options:

1. **Read from JS** (recommended): Use same `getComputedStyle()` pattern to read variables, pass as props.
2. **CSS class overrides**: Recharts renders SVG — can target via CSS selectors, but fragile.

Use option 1. Create a `useChartTheme()` hook that returns resolved color values.

**Confidence:** HIGH — Recharts is SVG-based, props are the intended styling mechanism.

## Navigation Architecture

### Current Navigation Structure

```
Tier-1 (GlobalNav):   [Cashflow Management] [Overview] [BTCEUR] [ETHEUR] [XRPEUR] [XRPBTC]  [Settings]
Tier-2 (SymbolLayout): [TradeLots] [Combined Score] [Orderblock] [Reconciliation]
```

7 symbol tabs + 4 sub-tabs per symbol = overwhelming.

### Target Navigation Structure

```
Section 1: Trading      → Dashboard (with Combined Score), TradeLots, Pairing
Section 2: Orderblocks   → Orderblock Analysis (per symbol)
Section 3: Admin          → Reconciliation, Settings
```

### Navigation Pattern: Top Nav with Section Tabs

**Use top navigation (horizontal), NOT sidebar.** Reasons:

1. **3 sections is too few for a sidebar** — Sidebars justify themselves at 6+ items. Three items in a sidebar wastes horizontal space.
2. **The app is data-dense** — Tables, charts, KPI grids all benefit from full viewport width. A sidebar steals 200-250px.
3. **Consistency with trading apps** — Binance, TradingView, Kraken all use horizontal navigation for top-level sections.
4. **Existing pattern** — The app already uses horizontal nav. Changing to sidebar is a bigger rewrite for no UX gain.

**Implementation:**

```
[Logo] [Trading] [Orderblocks] [Admin]          [BTC/EUR pill] [ETH/EUR pill] [XRP/EUR pill]  [Theme Toggle]
```

- Section tabs on the left (primary navigation)
- Symbol selector pills on the right (context switch)
- Theme toggle icon far right

**Route structure:**

```
/                         → Trading section, Dashboard (default)
/trading/lots             → TradeLots (within selected symbol context)
/trading/pairing          → Pairing (within selected symbol context)
/orderblocks              → Orderblock analysis (within selected symbol context)
/admin/reconciliation     → Reconciliation (within selected symbol context)
/admin/settings           → Settings (global, no symbol context)
```

### Symbol Context

Symbol selection stays in URL (current pattern: `/s/:symbol/...`). This is correct. The new section navigation wraps around it:

```
/trading/:symbol/dashboard
/trading/:symbol/lots
/orderblocks/:symbol
/admin/:symbol/reconciliation
/admin/settings
```

Or flatten to keep current pattern:

```
/s/:symbol/dashboard      (Trading section)
/s/:symbol/lots           (Trading section)
/s/:symbol/orderblock     (Orderblock section)
/s/:symbol/reconciliation (Admin section)
/settings                 (Admin section, no symbol)
```

**Recommendation:** Keep the `/s/:symbol/` URL pattern but change the nav visuals to show 3 sections. This minimizes route restructuring.

## XRPBTC Removal: No Stack Impact

XRPBTC removal is a pure code removal task. It affects:

1. `symbolRegistry.js` — Remove `XRPBTC` entry
2. `GlobalNav.jsx` — Already filtered by `getAllSymbols()`
3. `PairingPanel.css` — Remove cross-pair-specific styles (`.pair-origin-badge.pair-btc`, `.cross-pair-toggle`, `.dual-route-section`)
4. Backend `symbol_registry.py` — Remove XRPBTC entry
5. Backend routing logic — Remove BTC-quote routing paths

No new dependencies or patterns needed.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| CSS Custom Properties | CSS-in-JS (styled-components, Emotion) | If you need component-level scoping and dynamic styles. NOT here — the app uses plain CSS by design, 12 CSS files work fine. Adding CSS-in-JS would be a rewrite. |
| `[data-theme]` attribute | CSS class on `<body>` (`.dark-mode`) | Functionally identical. `data-theme` is semantically cleaner and is the community convention (MDN recommends it). |
| Top horizontal nav | Sidebar navigation | If section count grows to 6+, or if individual sections have deep nested navigation. Not the case here. |
| `localStorage` for theme | Server-synced preference | Only relevant for multi-device apps with user accounts. This is a single-user local tool. |
| Manual toggle only | System-preference only | A toggle that also respects system preference is strictly better. Users get smart defaults and manual override. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Tailwind CSS | Project constraint: "Kein UI-Framework." Adding Tailwind to 12 existing CSS files means rewriting everything. The custom property approach achieves the same result with zero migration. | CSS Custom Properties (already started in `index.css`) |
| CSS Modules | Would require renaming all `.css` files to `.module.css`, changing all imports, and refactoring all `className` strings. Huge migration for no dark-mode benefit. | Keep current component-scoped `.css` files |
| styled-components / Emotion | Runtime CSS-in-JS adds bundle weight and breaks the existing CSS file pattern. | Plain CSS with custom properties |
| color-scheme CSS property alone | `color-scheme: dark` only affects UA-rendered elements (scrollbars, form controls). It does NOT theme your custom CSS. | `[data-theme]` + custom properties + `color-scheme` on `:root` for form control hints |
| Separate dark mode CSS files | Doubles CSS file count, creates sync nightmare. Any color change needs updating in two places. | Single file with custom properties overridden by `[data-theme="dark"]` selector |
| Third-party theme libraries (next-themes, etc.) | Designed for Next.js/SSR. This is a Vite SPA — `useTheme` hook is 15 lines. No library needed. | Custom `useTheme` hook (see above) |

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| CSS Custom Properties | All modern browsers | Supported since 2017. Safari 9.1+, Chrome 49+, Firefox 31+. No polyfill needed. |
| `prefers-color-scheme` | All modern browsers | Supported since 2019. Safari 12.1+, Chrome 76+, Firefox 67+. |
| lightweight-charts ^5.1.0 | `applyOptions()` theme updates | Confirmed: `applyOptions()` works on live chart instances. |
| Recharts ^3.7.0 | Props-based color theming | SVG-based rendering, colors via props. No CSS custom property integration. |
| React Router ^7.13.0 | Nested layout routes | `<Outlet>` pattern already used for `SymbolLayout`. |

## Key Quantities (Scope Estimation)

| Metric | Count |
|--------|-------|
| CSS files to modify | 12 |
| Estimated hardcoded colors to convert | ~200 |
| Custom properties to add (dark variants) | ~40-50 |
| JSX files to modify for navigation | 3-5 (App, GlobalNav, SymbolLayout, Overview) |
| Chart components needing theme reactivity | 2 (OrderblockChart, Orderblock) |
| XRPBTC references to remove | ~10-15 files (frontend + backend) |

## Sources

- Codebase analysis: `index.css` (existing custom properties), all 12 CSS files (hardcoded color audit)
- `OrderblockChart.jsx` (lightweight-charts API usage: `createChart`, `applyOptions`)
- `Orderblock.jsx` (Recharts color props)
- `package.json` (current dependency versions)
- `GlobalNav.jsx`, `SymbolLayout.jsx`, `App.jsx` (current navigation structure)
- MDN CSS Custom Properties documentation — HIGH confidence (well-established standard)
- Trading platform observation (TradingView, Binance Pro) — MEDIUM confidence (training data, not live-verified for this session)
- lightweight-charts v5 `applyOptions()` — HIGH confidence (confirmed from codebase usage pattern)

---
*Stack research for: v2.0 Frontend Redesign (Dark Mode + Navigation + XRPBTC Removal)*
*Researched: 2026-02-23*
