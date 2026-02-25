# Phase 11: Dark Mode Activation + Charts - Research

**Researched:** 2026-02-24
**Domain:** Dark mode activation -- set `data-theme="dark"` on `<html>`, convert 60 deferred JSX chart hex values, integrate lightweight-charts and Recharts dark themes, prevent flash-of-wrong-theme
**Confidence:** HIGH

## Summary

Phase 11 is the activation phase for dark mode. Phase 10 completed the foundation: all 11 CSS files have zero hardcoded hex values (165 CSS custom properties in `:root`, matching 165 overrides in `[data-theme="dark"]`). What remains is: (1) setting `data-theme="dark"` on `<html>` so the dark palette takes effect, (2) converting 60 deferred hex values across 5 JSX files that pass colors to chart libraries (lightweight-charts and Recharts) and inline styles that cannot use `var()`, (3) preventing Flash of Wrong Theme (FOWT) via a blocking inline script in `index.html`, and (4) verifying that every component -- including loading states, empty states, error states, modals, and tooltips -- renders correctly against dark backgrounds.

The technical approach is well-defined. The CSS cascade handles 95% of the work automatically once `data-theme="dark"` is set -- all 11 component CSS files will immediately switch to dark values via their `var()` references. The remaining 5% is chart library code that operates outside the CSS cascade: lightweight-charts renders to `<canvas>` and accepts color strings in JavaScript config objects, Recharts renders SVG with colors passed as JSX props, and CombinedScore.jsx receives dynamic `action_color` hex strings from the backend API. The established pattern from Phase 10 (Overview.jsx's `getComputedStyle` bridge) provides the template: read resolved CSS variable values at render time and pass them as JS strings to chart config objects.

**Primary recommendation:** Create a shared `useChartTheme()` hook that reads all chart-relevant CSS custom properties via `getComputedStyle()` and returns a JS object. All 5 JSX files reference this hook instead of hardcoded hex values. For FOWT prevention, add a synchronous blocking `<script>` in `index.html` `<head>` that sets `document.documentElement.setAttribute('data-theme', 'dark')` before React loads. Since the project is dark-only (no toggle), this script is trivially simple.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DARK-03 | Alle 12 CSS-Dateien auf Dark-Mode-Variablen umstellen | Phase 10 COMPLETE: all 11 component CSS files already use var() references. Phase 11 activates them by setting data-theme="dark" on html element. Verification via visual inspection of all 12 pages/states. |
| DARK-04 | lightweight-charts Dark Theme Integration (via applyOptions()) | OrderblockChart.jsx has 23 hex values in createChart() config + candlestick/volume series + zone overlays/markers. Use chart.applyOptions() with dark colors at creation time. Pattern: getComputedStyle bridge hook. |
| DARK-05 | Recharts Dark Theme Integration (via JS Theme Hook) | Orderblock.jsx (14 lines), CombinedScore.jsx (13 lines + &#9888; entity), Overview.jsx (5 fallbacks), orderblockHelpers.jsx (4 gradient lines). Recharts accepts string props -- use getComputedStyle to read CSS vars at render time. |
| DARK-06 | Flash-of-Wrong-Theme Prevention (Blocking Script in index.html) | Synchronous inline script in index.html head: `document.documentElement.setAttribute('data-theme', 'dark')`. Dark-only design (no toggle) makes this a 3-line script. Must execute before any CSS is evaluated. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| CSS Custom Properties | Native | Dark theme activation via `[data-theme="dark"]` | Already fully prepared by Phase 10. Zero runtime cost. 165 tokens ready. |
| lightweight-charts | 5.1.0 | Candlestick chart (canvas-based) | Already installed. `applyOptions()` accepts dark layout/grid/series colors. |
| Recharts | 3.7.0 | Bar charts, Pie chart (SVG-based) | Already installed. Colors passed as JSX props -- use getComputedStyle bridge. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None | - | - | No new dependencies needed for this phase |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| getComputedStyle bridge | React Context theme provider | Over-engineered for dark-only mode. getComputedStyle is simpler, matches Overview.jsx established pattern. |
| Blocking script in index.html | next-themes / react-helmet | External dependency for a 3-line script. Not warranted. |
| Per-component chart colors | Centralized useChartTheme hook | Hook is preferred: single source of truth, consistent colors across all 5 files. |

## Architecture Patterns

### Pattern 1: Theme Activation (dark-only, no toggle)

**What:** Set `data-theme="dark"` on `<html>` element permanently. Since the project is dark-only (REQUIREMENTS.md: "v2.0 ist Dark-only. Toggle kann spaeter ergaenzt werden"), there is no toggle mechanism needed.

**Where it happens:** Two locations, both required:
1. `index.html` -- blocking script sets `data-theme="dark"` before CSS evaluates (FOWT prevention)
2. `main.jsx` or `App.jsx` -- ensure React does not override the attribute

**Example (index.html):**
```html
<head>
  <!-- ... existing head content ... -->
  <script>
    // FOWT prevention: set dark theme before any CSS evaluates
    document.documentElement.setAttribute('data-theme', 'dark');
  </script>
</head>
```

This is sufficient for dark-only. No localStorage, no `prefers-color-scheme` check, no toggle state management. If a toggle is added later, this script expands to check localStorage.

### Pattern 2: Chart Color Bridge (getComputedStyle)

**What:** A shared utility function (or hook) that reads CSS custom property values via `getComputedStyle()` and returns them as plain JS strings that chart libraries accept.

**When to use:** For any JSX file that passes color strings to lightweight-charts config objects, Recharts `fill`/`stroke`/`contentStyle` props, or inline `style={}` props.

**Established precedent:** Overview.jsx already uses this pattern (Phase 10):
```javascript
const getChartColors = () => {
  const style = getComputedStyle(document.documentElement);
  return [
    style.getPropertyValue('--color-chart-1').trim() || '#818cf8',
    style.getPropertyValue('--color-chart-2').trim() || '#fbbf24',
    // ...
  ];
};
```

**Extended pattern for Phase 11 -- shared hook:**
```javascript
// src/hooks/useChartTheme.js
const useChartTheme = () => {
  const style = getComputedStyle(document.documentElement);
  const get = (name, fallback) => style.getPropertyValue(name).trim() || fallback;

  return {
    // Layout
    bgCard: get('--color-bg-card', '#161822'),
    textSecondary: get('--color-text-secondary', '#94a3b8'),
    textMuted: get('--color-text-muted', '#64748b'),
    border: get('--color-border', '#2e3348'),
    borderLight: get('--color-border-light', '#252838'),

    // Semantic
    profit: get('--color-profit', '#22c55e'),
    loss: get('--color-loss', '#ef4444'),
    profitBright: get('--color-profit-bright', '#4ade80'),

    // Accents
    accentOrderblock: get('--color-accent-orderblock', '#fbbf24'),
    accentAmber: get('--color-accent-amber', '#fbbf24'),
    accentBlue: get('--color-accent-blue', '#60a5fa'),

    // Muted
    muted: get('--color-text-muted', '#64748b'),
  };
};
```

**Key constraint:** `getComputedStyle()` reads the resolved (computed) value, which automatically returns the dark-mode value when `[data-theme="dark"]` is active on `:root`. No theme-detection logic needed in the hook -- CSS does the work.

### Pattern 3: lightweight-charts Dark Theme (applyOptions)

**What:** Pass dark-mode-aware colors to `createChart()` initial config and to series `applyOptions()`.

**Key properties to set:**
```javascript
const chart = createChart(container, {
  layout: {
    background: { type: ColorType.Solid, color: theme.bgCard },
    textColor: theme.textSecondary,
    fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
  },
  grid: {
    vertLines: { color: theme.borderLight },
    horzLines: { color: theme.borderLight },
  },
  rightPriceScale: { borderColor: theme.border },
  timeScale: { borderColor: theme.border, timeVisible: true, secondsVisible: false },
  // ...
});
```

**Candlestick series:**
```javascript
chart.addSeries(CandlestickSeries, {
  upColor: theme.profit,
  downColor: theme.loss,
  borderUpColor: theme.profit,
  borderDownColor: theme.loss,
  wickUpColor: theme.profit,
  wickDownColor: theme.loss,
});
```

**Volume histogram:** The per-bar `color` property in the data array also needs theme-aware colors:
```javascript
adjusted.map(c => ({
  time: c.time,
  value: c.volume,
  color: c.close >= c.open
    ? `rgba(${hexToRgb(theme.profit)}, 0.25)`
    : `rgba(${hexToRgb(theme.loss)}, 0.25)`,
}))
```

Note: A `hexToRgb()` utility is needed to convert hex to RGB components for rgba() volume bar colors.

### Pattern 4: Recharts Dark Theme (JSX props)

**What:** Replace hardcoded hex in Recharts component props with theme values.

**CartesianGrid, Axis, Tooltip:**
```jsx
<CartesianGrid strokeDasharray="3 3" stroke={theme.borderLight} />
<XAxis dataKey="name" stroke={theme.textMuted} fontSize={12} />
<YAxis stroke={theme.textMuted} fontSize={12} />
<Tooltip contentStyle={{
  background: theme.bgCard,
  border: `1px solid ${theme.border}`,
  borderRadius: '8px',
  color: theme.textSecondary,
}} />
```

**Bar fills (semantic colors):**
```jsx
<Bar dataKey="Hits" fill={theme.profit} radius={[4, 4, 0, 0]} />
<Bar dataKey="Misses" fill={theme.loss} radius={[4, 4, 0, 0]} />
<Bar dataKey="Expired" fill={theme.textMuted} radius={[4, 4, 0, 0]} />
```

### Pattern 5: Dynamic Backend Colors (action_color)

**What:** `CombinedScore.jsx` receives `data.action_color` from the backend API (a hex string like `#22c55e`). These colors are hardcoded in `backend/app/domain/combined_score.py` as `ACTION_COLORS`.

**Problem:** The backend sends light-mode-optimized hex colors. In dark mode, some of these may lack sufficient contrast against dark backgrounds (e.g., `#64748b` HOLD color on `#161822` card background has ~3.8:1 contrast, below WCAG AA 4.5:1).

**Solution options:**

1. **Map backend colors to dark-appropriate CSS classes on the frontend (RECOMMENDED):** Instead of using `style={{ backgroundColor: data.action_color }}`, assign a CSS class based on `data.action` value (e.g., `.action-strong-buy`, `.action-hold`). Define colors in CSS variables that respect the dark theme. This decouples visual presentation from backend data.

2. **Add a dark_action_color field to the API (NOT RECOMMENDED):** Would require backend changes and couples the backend to frontend display concerns.

3. **Frontend color mapping overlay:** Map the 7 known `action_color` hex values to dark-mode-adjusted equivalents in a JS lookup. Pragmatic but creates a second source of truth.

**Recommendation:** Use approach 1 (CSS classes). The `data.action` field already provides the semantic name (`STRONG_BUY`, `BUY`, `LEAN_BUY`, `HOLD`, `LEAN_SELL`, `SELL`, `STRONG_SELL`). Map these to CSS classes that reference theme-aware variables.

### Pattern 6: Gradient Strings in JSX (CombinedScore + orderblockHelpers)

**What:** CombinedScore.jsx pillar bars and orderblockHelpers.jsx score gradients use inline `linear-gradient()` strings with hardcoded hex.

**Solution:** Add dedicated CSS custom properties for gradient endpoints:
```css
/* index.css :root */
--color-gradient-score-low-start: #94a3b8;
--color-gradient-score-low-end: #cbd5e1;
--color-gradient-score-mid-start: #60a5fa;
--color-gradient-score-mid-end: #3b82f6;
--color-gradient-score-high-start: #fbbf24;
--color-gradient-score-high-end: #d97706;
--color-gradient-score-top-start: #a855f7;
--color-gradient-score-top-end: #7c3aed;

/* Sentiment pillar gradients */
--color-gradient-pillar-fear-start: #dc2626;
--color-gradient-pillar-fear-end: #f97316;
--color-gradient-pillar-caution-start: #f97316;
--color-gradient-pillar-caution-end: #fb923c;
--color-gradient-pillar-neutral-start: #94a3b8;
--color-gradient-pillar-neutral-end: #64748b;
--color-gradient-pillar-greed-start: #4ade80;
--color-gradient-pillar-greed-end: #22c55e;
--color-gradient-pillar-extreme-start: #22c55e;
--color-gradient-pillar-extreme-end: #16a34a;
```

Read these via `getComputedStyle()` and construct the gradient string in JS:
```javascript
const gradient = `linear-gradient(90deg, ${theme.gradientScoreLowStart}, ${theme.gradientScoreLowEnd})`;
```

### Anti-Patterns to Avoid

- **Recreating lightweight-charts instance on theme change:** Use `chart.applyOptions()` instead. Recreating causes visible flicker and loses scroll/zoom position.
- **Scattering `[data-theme="dark"]` into component CSS files:** All dark overrides remain exclusively in `index.css`. Phase 10 established this invariant.
- **Using `matchMedia('prefers-color-scheme')` for a dark-only app:** Unnecessary complexity. Hard-set `data-theme="dark"` unconditionally.
- **Forgetting Recharts Tooltip contentStyle:** Tooltips render in a portal-like overlay. If their background/text colors are not explicitly set, they remain white-on-white in dark mode. Always pass `contentStyle` with theme-aware background and color.
- **Hardcoding dark-mode hex in JSX:** Replace existing light-mode hex with dark-mode hex. Instead, use CSS variables via getComputedStyle. This keeps the single-source-of-truth in index.css.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chart color management | Per-file hardcoded hex values | Shared `useChartTheme()` hook reading CSS variables | Single source of truth, automatic dark mode support |
| FOWT prevention | Complex JS theme detection | 3-line blocking script in index.html | Dark-only simplifies to a single setAttribute call |
| Theme state management | React Context + localStorage | Hard attribute on html element | Dark-only = no state to manage |
| Hex-to-RGB conversion | Manual string parsing | 3-line utility function | Needed for rgba() volume bars; reusable |

**Key insight:** Because the project is dark-only (no toggle), the entire "theme management" layer collapses to a single HTML attribute. The real work is in the 60 deferred JSX hex values, not in theme infrastructure.

## Common Pitfalls

### Pitfall 1: White Flash on Page Load (FOWT)
**What goes wrong:** User sees a white background for 100-300ms before React loads and the dark theme CSS takes effect.
**Why it happens:** Vite's module script loads asynchronously. By the time React renders, the browser has already painted the default (light) background.
**How to avoid:** Add a synchronous (non-module, non-deferred) `<script>` tag in `index.html` `<head>` BEFORE the `<link>` to CSS. Set `data-theme="dark"` on `document.documentElement`. Also set `background-color` on `<html>` in the script as a belt-and-suspenders measure: `document.documentElement.style.backgroundColor = '#0f1117'`.
**Warning signs:** Brief white flash visible on F5 page refresh, especially noticeable on fast connections.

### Pitfall 2: Recharts Tooltip White Background
**What goes wrong:** Recharts tooltips appear as white boxes with invisible text on dark backgrounds.
**Why it happens:** Recharts `<Tooltip>` has a default white background. The `contentStyle` prop must be explicitly set to dark values. This is easy to miss because tooltips only appear on hover.
**How to avoid:** Every `<Tooltip>` component must receive a `contentStyle` prop with dark background and light text. Grep for `<Tooltip` after conversion to verify none are missing.
**Warning signs:** Hovering over chart elements shows unreadable tooltips.

### Pitfall 3: Volume Bar Colors Still Use Light-Mode rgba()
**What goes wrong:** Volume histogram bars in OrderblockChart.jsx use `rgba(22,163,74,0.25)` (light green) and `rgba(220,38,38,0.25)` (light red). These are readable on white but invisible against dark backgrounds.
**Why it happens:** The rgba() colors are embedded in a `.map()` callback that generates per-bar data objects. Easy to overlook because they are data values, not config options.
**How to avoid:** Read the profit/loss hex from the theme hook, convert to RGB components, and construct rgba strings dynamically. Use brighter dark-mode colors (e.g., `rgba(34,197,94,0.35)` instead of `rgba(22,163,74,0.25)` -- slightly higher alpha for visibility on dark backgrounds).
**Warning signs:** Volume bars appear absent or extremely faint in the candlestick chart.

### Pitfall 4: Zone Overlay / Marker Colors Invisible
**What goes wrong:** Price lines and markers on the candlestick chart (zone borders, equilibrium, entry/stop/target levels, OB/BOS markers) use colors that lack contrast against the dark chart background.
**Why it happens:** Colors like `#d97706` (amber, used for equilibrium and OB/BOS markers) are fine on white but may blend into a dark brownish background. `#3b82f6` (blue, used for entry lines) is fine on dark backgrounds.
**How to avoid:** Use the brighter dark-mode accent variants from CSS variables (e.g., `--color-accent-orderblock` which resolves to `#fbbf24` in dark mode vs. `#d97706` in light mode). Test every zone overlay color against the dark chart background.
**Warning signs:** Price lines or markers are hard to see on the candlestick chart.

### Pitfall 5: action_color from Backend Mismatches Dark Theme
**What goes wrong:** The backend sends hardcoded hex colors for the Combined Score action banner (e.g., `#64748b` for HOLD). Used as `backgroundColor` on badges and `color` on text, some of these colors have insufficient contrast against dark card backgrounds.
**Why it happens:** `ACTION_COLORS` in `combined_score.py` was designed for light mode.
**How to avoid:** Replace inline `style={{ backgroundColor: data.action_color }}` with CSS classes that use theme-aware variables. Map `data.action` to class names (`.action-strong-buy`, etc.). Define appropriate dark-mode colors in index.css.
**Warning signs:** Combined Score badges are unreadable or look washed out.

### Pitfall 6: Untested Component States
**What goes wrong:** Loading spinners, empty states, error messages, or modal overlays remain light-themed.
**Why it happens:** These states are less visible during development because they are transient. The CSS variables handle them IF the CSS classes are correct, but any hardcoded colors in JSX for these states will not switch.
**How to avoid:** Systematically test all component states: loading, empty, error, hover, selected, expanded/collapsed details, modals (SimulationModal), notification banners.
**Warning signs:** Specific UI states flash white momentarily.

## Code Examples

### Example 1: Blocking Script for FOWT Prevention (index.html)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <script>
      // Dark-only: set theme before any CSS evaluates to prevent FOWT
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.style.backgroundColor = '#0f1117';
    </script>
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Cashflow Management</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

Source: [Preventing Theme Flash in React](https://dev.to/gaisdav/how-to-prevent-theme-flash-in-a-react-instant-dark-mode-switching-o20), adapted for dark-only (no localStorage needed).

### Example 2: useChartTheme Hook

```javascript
// src/hooks/useChartTheme.js

/**
 * Reads chart-relevant CSS custom properties via getComputedStyle.
 * Returns plain JS strings suitable for lightweight-charts config and Recharts props.
 * In dark mode, CSS resolves to [data-theme="dark"] values automatically.
 */
const useChartTheme = () => {
  const style = getComputedStyle(document.documentElement);
  const get = (name, fallback) => style.getPropertyValue(name).trim() || fallback;

  return {
    // Layout
    bgCard: get('--color-bg-card', '#161822'),
    bgPage: get('--color-bg-page', '#0f1117'),
    textSecondary: get('--color-text-secondary', '#94a3b8'),
    textMuted: get('--color-text-muted', '#64748b'),

    // Borders / Grid
    border: get('--color-border', '#2e3348'),
    borderLight: get('--color-border-light', '#252838'),

    // Semantic
    profit: get('--color-profit', '#22c55e'),
    loss: get('--color-loss', '#ef4444'),
    profitBright: get('--color-profit-bright', '#4ade80'),
    muted: get('--color-text-muted', '#64748b'),

    // Accents
    accentOrderblock: get('--color-accent-orderblock', '#fbbf24'),
    accentAmber: get('--color-accent-amber', '#fbbf24'),
    accentBlue: get('--color-accent-blue', '#60a5fa'),

    // Chart palette
    chart1: get('--color-chart-1', '#818cf8'),
    chart2: get('--color-chart-2', '#fbbf24'),
    chart3: get('--color-chart-3', '#34d399'),
    chart4: get('--color-chart-4', '#f87171'),
    chart5: get('--color-chart-5', '#a78bfa'),
  };
};

/**
 * Convert hex color to RGB components string for rgba() construction.
 * @param {string} hex - e.g. '#22c55e'
 * @returns {string} - e.g. '34, 197, 94'
 */
const hexToRgb = (hex) => {
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
};

export { useChartTheme, hexToRgb };
```

### Example 3: OrderblockChart.jsx Dark Integration

```javascript
import { useChartTheme, hexToRgb } from '../hooks/useChartTheme';

const OrderblockChart = ({ candles, zone, trade, isLoading }) => {
  const theme = useChartTheme();
  // ...

  useEffect(() => {
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: theme.bgCard },
        textColor: theme.textSecondary,
        fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
      },
      grid: {
        vertLines: { color: theme.borderLight },
        horzLines: { color: theme.borderLight },
      },
      rightPriceScale: { borderColor: theme.border },
      timeScale: { borderColor: theme.border, timeVisible: true, secondsVisible: false },
      // ...
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: theme.profit,
      downColor: theme.loss,
      borderUpColor: theme.profit,
      borderDownColor: theme.loss,
      wickUpColor: theme.profit,
      wickDownColor: theme.loss,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: theme.textMuted,
      // ...
    });
    // ...
  }, []);

  // Volume data with theme-aware rgba
  useEffect(() => {
    volumeSeriesRef.current.setData(
      adjusted.map(c => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open
          ? `rgba(${hexToRgb(theme.profit)}, 0.3)`
          : `rgba(${hexToRgb(theme.loss)}, 0.3)`,
      }))
    );
  }, [candles]);
};
```

### Example 4: Recharts Dark Tooltip + Axis (Orderblock.jsx)

```jsx
const Orderblock = () => {
  const theme = useChartTheme();
  // ...

  return (
    <BarChart data={stateChartData} barSize={48}>
      <CartesianGrid strokeDasharray="3 3" stroke={theme.borderLight} />
      <XAxis dataKey="name" stroke={theme.textMuted} fontSize={12} />
      <YAxis stroke={theme.textMuted} fontSize={12} allowDecimals={false} />
      <Tooltip contentStyle={{
        background: theme.bgCard,
        border: `1px solid ${theme.border}`,
        borderRadius: '8px',
        color: theme.textSecondary,
      }} />
      <Bar dataKey="count" radius={[6, 6, 0, 0]}>
        {stateChartData.map((entry) => (
          <Cell key={entry.name} fill={entry.fill} />
        ))}
      </Bar>
    </BarChart>
  );
};
```

### Example 5: CombinedScore action_color via CSS Classes

```jsx
// Instead of:
<span style={{ backgroundColor: data.action_color }}>...</span>

// Use:
const ACTION_CLASS_MAP = {
  'STARK LONG': 'action-strong-buy',
  'LONG': 'action-buy',
  'NEUTRAL': 'action-hold',
  'SHORT': 'action-sell',
  'STARK SHORT': 'action-strong-sell',
};

<span className={`combined-rec-badge ${ACTION_CLASS_MAP[data.direction.recommendation] || 'action-hold'}`}>
  {data.direction.recommendation}
</span>
```

With CSS in index.css:
```css
:root {
  --color-action-strong-buy: #16a34a;
  --color-action-buy: #22c55e;
  --color-action-lean-buy: #4ade80;
  --color-action-hold: #64748b;
  --color-action-lean-sell: #fb923c;
  --color-action-sell: #f97316;
  --color-action-strong-sell: #dc2626;
}
[data-theme="dark"] {
  --color-action-strong-buy: #22c55e;
  --color-action-buy: #4ade80;
  --color-action-lean-buy: #86efac;
  --color-action-hold: #94a3b8;
  --color-action-lean-sell: #fbbf24;
  --color-action-sell: #fb923c;
  --color-action-strong-sell: #ef4444;
}
```

## Detailed File Inventory (Deferred from Phase 10)

### OrderblockChart.jsx -- 23 hex values + 2 rgba values

| Line(s) | Current Value | Semantic Purpose | Maps To |
|---------|--------------|-----------------|---------|
| 29 | `#ffffff` | Chart background | `--color-bg-card` |
| 30 | `#64748b` | Axis text | `--color-text-secondary` |
| 34-35 | `#f1f5f9` | Grid lines | `--color-border-light` |
| 38, 40 | `#e2e8f0` | Scale borders | `--color-border` |
| 49, 51, 53 | `#16a34a` | Bullish candle | `--color-profit` |
| 50, 52, 54 | `#dc2626` | Bearish candle | `--color-loss` |
| 58 | `#94a3b8` | Default volume color | `--color-text-muted` |
| 98 | `rgba(22,163,74,0.25)` / `rgba(220,38,38,0.25)` | Volume bar colors | `rgba(profit, 0.3)` / `rgba(loss, 0.3)` |
| 123 | `#16a34a` / `#dc2626` | Zone border (conditional) | `--color-profit` / `--color-loss` |
| 146, 176, 187 | `#d97706` | Equilibrium + OB/BOS markers | `--color-accent-orderblock` |
| 159 | `#f59e0b` | Sweep level | `--color-accent-amber` |
| 199, 237 | `#3b82f6` | Entry line + marker | `--color-accent-blue` |
| 211 | `#dc2626` | Stop line | `--color-loss` |
| 223 | `#16a34a` | Target line | `--color-profit` |
| 247 | `#16a34a` / `#dc2626` | Exit marker (conditional) | `--color-profit` / `--color-loss` |

### Orderblock.jsx -- 14 hex values (on 14 lines)

| Line(s) | Current Value | Semantic Purpose | Maps To |
|---------|--------------|-----------------|---------|
| 191 | `#16a34a` | Unmitigated bar fill | `--color-profit` |
| 192 | `#94a3b8` | Mitigated bar fill | `--color-text-muted` |
| 193 | `#dc2626` | Invalid bar fill | `--color-loss` |
| 345, 363 | `#e2e8f0` | CartesianGrid stroke | `--color-border-light` |
| 346-347, 364-365 | `#64748b` | Axis stroke | `--color-text-muted` |
| 348, 366 | `#fff` + `#e2e8f0` | Tooltip contentStyle | `--color-bg-card` + `--color-border` |
| 368 | `#16a34a` | Hits bar fill | `--color-profit` |
| 369 | `#dc2626` | Misses bar fill | `--color-loss` |
| 370 | `#94a3b8` | Expired bar fill | `--color-text-muted` |

### CombinedScore.jsx -- 22 individual hex values on 13 lines

| Line(s) | Current Value | Semantic Purpose | Maps To |
|---------|--------------|-----------------|---------|
| 23-27 | 5 hex values | MACRO_REC_COLORS constant | CSS class approach (see Pattern 5) |
| 82 | 3 hex (ternary) | Multiplier text color | CSS class `.multiplier-positive`/`.negative`/`.neutral` |
| 140 | `#64748b` | Fallback badge color | CSS class `.action-hold` |
| 223 | 3 hex (ternary) | Sizing multiplier color | CSS class approach |
| 254-261 | 10 hex (gradient) | Pillar bar gradient (5 ranges) | `--color-gradient-pillar-*` CSS variables |

### Overview.jsx -- 5 hex values (fallbacks only)

| Line(s) | Current Value | Semantic Purpose | Maps To |
|---------|--------------|-----------------|---------|
| 21-25 | 5 hex | getChartColors fallbacks | Update fallbacks to dark-mode values |

### orderblockHelpers.jsx -- 8 hex values (4 gradient strings)

| Line(s) | Current Value | Semantic Purpose | Maps To |
|---------|--------------|-----------------|---------|
| 10 | `#94a3b8`, `#cbd5e1` | Score 0-25 gradient | `--color-gradient-score-low-*` |
| 11 | `#60a5fa`, `#3b82f6` | Score 25-50 gradient | `--color-gradient-score-mid-*` |
| 12 | `#fbbf24`, `#d97706` | Score 50-75 gradient | `--color-gradient-score-high-*` |
| 13 | `#a855f7`, `#7c3aed` | Score 75-100 gradient | `--color-gradient-score-top-*` |

### Summary

| File | Hex Values | rgba Values | Total Color Instances |
|------|-----------|-------------|----------------------|
| OrderblockChart.jsx | 23 | 2 | 25 |
| CombinedScore.jsx | 22 | 0 | 22 |
| Orderblock.jsx | 14 | 0 | 14 |
| orderblockHelpers.jsx | 8 | 0 | 8 |
| Overview.jsx | 5 | 0 | 5 |
| **Total** | **72** | **2** | **74** |

**Note:** Phase 10 summary documented "60 hex values" but undercounted CombinedScore.jsx (per-line count vs. per-hex count) and orderblockHelpers.jsx (4 lines with 8 hex). Actual total is 74 color instances across 5 files.

## New CSS Variables Needed

The following new CSS custom properties must be added to `index.css` in both `:root` and `[data-theme="dark"]`:

### Action Colors (CombinedScore)
```css
--color-action-strong-buy
--color-action-buy
--color-action-lean-buy
--color-action-hold
--color-action-lean-sell
--color-action-sell
--color-action-strong-sell
```

### Score Gradient Endpoints (orderblockHelpers + CombinedScore pillar bars)
```css
--color-gradient-score-low-start / -end
--color-gradient-score-mid-start / -end
--color-gradient-score-high-start / -end
--color-gradient-score-top-start / -end

--color-gradient-pillar-fear-start / -end
--color-gradient-pillar-caution-start / -end
--color-gradient-pillar-neutral-start / -end
--color-gradient-pillar-greed-start / -end
--color-gradient-pillar-extreme-start / -end
```

**Estimated new token count:** ~27 new variables (7 action + 8 score gradient + 10 pillar gradient + 2 misc).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded hex in chart config | getComputedStyle bridge to CSS vars | Phase 10 (Overview.jsx) | Theme-aware chart colors from single source |
| White chart backgrounds assumed | Dark canvas backgrounds via applyOptions | lightweight-charts v4+ | First-class dark theme support |
| `prefers-color-scheme` media query only | `data-theme` attribute + blocking script | 2023+ community consensus | Eliminates FOWT, supports forced themes |

**Deprecated/outdated:**
- `filter: invert(1)`: Inverts all colors including charts and images. Completely unusable for a trading app.
- CSS-only dark mode via `@media (prefers-color-scheme: dark)`: Does not allow forced dark-only or persisted theme preference. Not suitable for this project.

## Open Questions

1. **Backend action_color field -- keep or ignore?**
   - What we know: Backend sends `action_color` hex string per API response. Frontend currently uses it directly in inline styles.
   - What's unclear: Whether to keep using the backend value at all, or fully replace with CSS-class-based approach.
   - Recommendation: Replace with CSS classes on frontend. The backend field becomes informational/unused for display. No backend changes needed -- the field can remain for API consumers who want it.

2. **Overview.jsx fallback values -- update to dark defaults?**
   - What we know: The getChartColors() fallbacks are light-mode hex values. Since dark mode is the only mode, fallbacks should be dark-mode values.
   - What's unclear: Whether the fallbacks ever trigger (they only fire if getComputedStyle fails to resolve the CSS variable).
   - Recommendation: Update fallbacks to dark-mode values from the `[data-theme="dark"]` block. They are safety nets, not primary paths.

3. **Volume bar alpha values for dark mode**
   - What we know: Current `rgba(22,163,74,0.25)` is 25% opacity. On dark backgrounds, this is very faint.
   - What's unclear: Optimal alpha value for dark backgrounds.
   - Recommendation: Increase to `0.30` or `0.35` for dark mode. Test visually -- volume bars should be clearly visible but not dominate the candlestick view.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: all 5 deferred JSX files fully read (2026-02-24)
- Phase 10 VERIFICATION.md: confirms 165 CSS tokens in `:root` and `[data-theme="dark"]`, all 11 CSS files at zero hardcoded hex
- Phase 10 03-SUMMARY.md: documents the 60 deferred values and the getComputedStyle pattern
- `index.css` `:root` and `[data-theme="dark"]` blocks: full token inventory verified (lines 1-447)
- `backend/app/domain/combined_score.py` ACTION_COLORS: 7 hardcoded hex values confirmed
- [Chart colors | Lightweight Charts](https://tradingview.github.io/lightweight-charts/tutorials/customization/chart-colors) -- layout, grid, series color configuration
- [Series colors | Lightweight Charts](https://tradingview.github.io/lightweight-charts/tutorials/customization/series) -- candlestick upColor/downColor/wick configuration

### Secondary (MEDIUM confidence)
- [Preventing Theme Flash in React](https://dev.to/gaisdav/how-to-prevent-theme-flash-in-a-react-instant-dark-mode-switching-o20) -- FOWT prevention pattern; verified against multiple sources
- [Recharts Tooltip customization](https://recharts.org/?p=%2Fen-US%2Fexamples%2FCustomContentOfTooltip) -- contentStyle prop for dark tooltip backgrounds
- [Light/dark mode: avoid flickering](https://dev.to/ayc0/light-dark-mode-avoid-flickering-on-reload-1567) -- blocking script approach confirmed

### Tertiary (LOW confidence)
- None -- all findings verified from direct codebase analysis and official documentation

## Metadata

**Confidence breakdown:**
- Theme activation (DARK-03): HIGH -- Phase 10 verified foundation; activation is a 3-line script
- lightweight-charts (DARK-04): HIGH -- existing codebase uses createChart/applyOptions; dark colors are straightforward config changes
- Recharts (DARK-05): HIGH -- established getComputedStyle pattern from Overview.jsx; Recharts props accept string colors
- FOWT prevention (DARK-06): HIGH -- well-documented pattern, trivially simple for dark-only

**Research date:** 2026-02-24
**Valid until:** No expiration -- all technologies are stable (CSS Custom Properties, lightweight-charts 5.x, Recharts 3.x). File inventory is accurate as of this date.
