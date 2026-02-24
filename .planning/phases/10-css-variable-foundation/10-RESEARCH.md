# Phase 10: CSS Variable Foundation - Research

**Researched:** 2026-02-24
**Domain:** CSS Custom Properties migration -- extracting hardcoded colors from 12 CSS files and 9+ JSX inline styles into CSS variables
**Confidence:** HIGH

## Summary

Phase 10 is a mechanical, zero-visual-change refactoring: every hardcoded hex color value in component CSS files and JSX inline styles must be replaced with `var()` references to CSS Custom Properties defined in `index.css`. The app must look pixel-identical after the conversion. Additionally, a `[data-theme="dark"]` block must be defined in `index.css` with the dark mode palette values -- inactive by default (no toggle yet), but ready for Phase 11 activation.

The codebase already has a partial CSS variable system in `index.css` `:root` with 22 semantic tokens (profit, loss, text hierarchy, borders, backgrounds, accents). These cover roughly 30% of color usage. The remaining 70% -- approximately 391 hardcoded hex values across 12 CSS files plus 53 `rgba()` values plus 9+ JSX inline color references -- must be converted. The most heavily-hardcoded files are `Orderblock.css` (83 hex), `PairingPanel.css` (65 hex), `LotsTable.css` (68 hex), and `Reconciliation.css` (49 hex).

**Primary recommendation:** Work file-by-file from most-hardcoded to least. For each file: (1) identify unique colors, (2) map each to an existing variable or define a new one, (3) replace all occurrences, (4) verify visually. Resolve the two existing `!important` usages. Convert all `linear-gradient()` hardcoded pairs to variable form. Convert JSX inline styles to CSS classes or `var()` references. The success criterion is that `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` returns zero matches outside the `:root` variable definitions in `index.css`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DARK-01 | CSS Custom Property System vervollstaendigen (alle hardcoded Hex-Werte in Variablen) | Complete inventory of 421 hex + 53 rgba() values across 12 CSS files + 9 JSX inline styles. Variable naming taxonomy defined. File-by-file conversion strategy with verification command. |
| DARK-02 | Dark Mode Farbpalette definieren (Slate-950 Background, WCAG AA Kontrast) | Full dark palette from prior research (FEATURES.md): 5-level surface hierarchy, text hierarchy, semantic colors with WCAG AA/AAA contrast ratios verified, feedback states, shadows. Ready to write as `[data-theme="dark"]` block. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| CSS Custom Properties | Native | Color theming via `var()` | Zero-runtime-cost, full browser support, already partially used in index.css |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None | - | - | No new dependencies needed for this phase |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CSS Custom Properties | CSS-in-JS (styled-components) | Project convention is Plain CSS, component-scoped. CSS-in-JS would be a fundamental architecture change. |
| CSS Custom Properties | Tailwind CSS | Explicitly out of scope per REQUIREMENTS.md |
| Manual variable extraction | PostCSS plugin | Over-engineered for a one-time migration. Manual is safer for precision. |

## Architecture Patterns

### Recommended Token Architecture

All color tokens live EXCLUSIVELY in `index.css`. Component CSS files contain ZERO `[data-theme]` selectors and ZERO hardcoded hex values.

```
index.css
├── :root {                          # Light theme (current appearance)
│   ├── /* Semantic Palette */
│   │   ├── --color-profit: #16a34a
│   │   ├── --color-loss: #dc2626
│   │   └── ...
│   ├── /* Text Hierarchy */
│   │   ├── --color-text-primary: #1e293b
│   │   ├── --color-text-secondary: #64748b
│   │   └── ...
│   ├── /* Surface Hierarchy */
│   │   ├── --color-bg-page: #f5f7fa
│   │   ├── --color-bg-card: #ffffff
│   │   ├── --color-bg-subtle: #f8fafc
│   │   ├── --color-bg-muted: #f1f5f9
│   │   ├── --color-bg-hover: #f1f5f9
│   │   ├── --color-bg-selected: #eef2ff
│   │   └── ...
│   ├── /* Borders */
│   │   ├── --color-border: #e2e8f0
│   │   ├── --color-border-light: #f1f5f9
│   │   ├── --color-border-input: #d1d5db
│   │   └── ...
│   ├── /* Feedback Colors */
│   │   ├── --color-success-bg, --color-success-text, --color-success-border
│   │   ├── --color-error-bg, --color-error-text, --color-error-border
│   │   ├── --color-warning-bg: #fef3c7, --color-warning-text: #92400e, --color-warning-border: #fcd34d
│   │   ├── --color-info-bg: #eff6ff, --color-info-text: #1e40af, --color-info-border: #bfdbfe
│   │   └── ...
│   ├── /* Accents */
│   │   ├── --color-accent-navbar-start, --color-accent-navbar-end
│   │   ├── --color-accent-sync, --color-accent-pairing, --color-accent-recon, --color-accent-orderblock
│   │   └── ...
│   ├── /* Component-Specific Semantic Tokens */
│   │   ├── --color-table-header-bg: ...
│   │   ├── --color-table-row-even: ...
│   │   ├── --color-table-row-hover: ...
│   │   └── ...
│   ├── /* Gradient Endpoints */
│   │   ├── --color-gradient-section-start: #f8fafc
│   │   ├── --color-gradient-section-end: #f1f5f9
│   │   └── ...
│   └── /* Shadows */
│       └── --shadow-card, --shadow-hover, --shadow-sm
│
└── [data-theme="dark"] {            # Dark theme (defined but not active)
    ├── /* Same token names, different values */
    ├── --color-bg-page: #0f1117
    ├── --color-bg-card: #161822
    ├── --color-text-primary: #e2e8f0
    └── ...
}
```

### Token Naming Convention

Use the existing naming pattern from `index.css` and extend it:

```
--color-{category}-{variant}

Categories:
  text     - Text colors (primary, secondary, muted, heading)
  bg       - Background colors (page, card, subtle, muted, hover, selected)
  border   - Border colors (default, light, input, focus)
  accent   - Brand/section accent colors (pairing, recon, sync, orderblock, navbar-start/end)
  success  - Success feedback (bg, text, border)
  error    - Error feedback (bg, text, border)
  warning  - Warning feedback (bg, text, border)
  info     - Info feedback (bg, text, border)
  profit   - Financial positive (single token)
  loss     - Financial negative (single token)
  gradient - Gradient endpoints (section-start, section-end, success-start, success-end)
  shadow   - Box shadows (card, hover, sm)
```

### Pattern: Gradient Variable Conversion

15+ `linear-gradient()` occurrences use hardcoded hex pairs. Convert to:

```css
/* BEFORE */
background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);

/* AFTER */
background: linear-gradient(135deg, var(--color-gradient-section-start) 0%, var(--color-gradient-section-end) 100%);
```

This enables dark mode to simply redefine `--color-gradient-section-start: #1e2030` and `--color-gradient-section-end: #252838`.

### Pattern: Resolving `!important`

Two existing `!important` usages must be resolved:

1. **LotsTable.css line 417**: `.order-row-warning { background: #fffbeb !important; }`
   - Fix: Create `--color-bg-warning-row: #fffbeb` and use it without `!important`. If specificity is the issue, increase selector specificity by one level instead of using `!important`.

2. **PairingPanel.css line 356**: `.summary-profit .summary-value { color: var(--color-profit) !important; }`
   - Fix: Already uses a variable, but the `!important` must go. Increase specificity if needed: `.pairing-panel .summary-profit .summary-value { color: var(--color-profit); }`.

### Pattern: JSX Inline Style Conversion

9+ JSX files have hardcoded color strings in inline `style={}` props. Two approaches:

**Approach A (CSS classes -- preferred for static mappings):**
```jsx
// BEFORE
style={{ color: data.size_multiplier > 1 ? '#16a34a' : '#dc2626' }}

// AFTER (add CSS classes)
className={data.size_multiplier > 1 ? 'color-profit' : 'color-loss'}
```

**Approach B (CSS variable in inline style -- for dynamic values):**
```jsx
// BEFORE (CombinedScore.jsx line 110)
style={{ backgroundColor: data.action_color }}

// AFTER (action_color comes from backend API -- keep as-is for Phase 10,
// convert in Phase 11 when chart theme integration addresses dynamic colors)
```

**Decision for Phase 10:** Convert static color references to CSS classes. Leave dynamic `action_color` (computed by backend) for Phase 11. Document all deferred inline styles explicitly.

### Anti-Patterns to Avoid
- **Scattering `[data-theme="dark"]` across component CSS files:** ALL dark overrides go in `index.css` only
- **Creating too many tokens:** Not every unique hex value needs its own token. Many values are the same semantic color used in different contexts (`#f8fafc` appears 10+ times -- it is `--color-bg-subtle`)
- **Using generic names:** `--color-1`, `--gray-light` -- use semantic names that describe purpose, not appearance
- **Converting `rgba()` opacity values to variables:** The opacity portion of `rgba(0,0,0,0.1)` does not need a separate variable. Use `rgba(var(--color-shadow-rgb), 0.1)` pattern only if the base color changes between themes. For Phase 10, many `rgba()` values are shadows that stay constant.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Color token system | Custom JS theming runtime | CSS Custom Properties in `:root` | Zero runtime cost, native browser support, already partially in use |
| Dark mode detection | Custom media query listener | `[data-theme="dark"]` attribute | Simpler, works with blocking script in Phase 11 |
| Variable naming | Ad-hoc per file | Consistent taxonomy (above) | Single source of truth, predictable names |

**Key insight:** This phase is purely mechanical CSS refactoring. No JavaScript is needed. No new files are created except expanding `index.css`. The complexity is in completeness (catching ALL 421+ occurrences), not in any single technical challenge.

## Common Pitfalls

### Pitfall 1: Incomplete Migration (the Big One)
**What goes wrong:** Some hardcoded values survive and produce broken visuals when dark mode activates in Phase 11.
**Why it happens:** File-by-file conversion misses values in complex selectors (`:nth-child(even):hover`), gradient shorthand, or `border` shorthand that embeds a color.
**How to avoid:** Run `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` after EACH file conversion. The total count must decrease monotonically toward zero (outside `:root`). Final verification: zero matches outside `index.css` `:root` and `[data-theme="dark"]` blocks.
**Warning signs:** grep count does not decrease after processing a file.

### Pitfall 2: Visual Regression During Conversion
**What goes wrong:** A CSS variable is misspelled, a fallback is missing, or a value is mapped to the wrong token. The light mode appearance changes.
**Why it happens:** Typos in variable names, confusing similar colors (`#f8fafc` vs `#f1f5f9` vs `#f8f9fa`).
**How to avoid:** After converting each file, visually inspect in the browser. Compare before/after screenshots of key screens: Dashboard, LotsTable (with filters, with pairing open), Orderblock (with chart, with zones), Reconciliation, CombinedScore, Settings. Run `npm run build` to catch any CSS syntax errors.
**Warning signs:** "Something looks slightly different but I cannot pinpoint it."

### Pitfall 3: Token Explosion
**What goes wrong:** Every unique hex value gets its own variable, resulting in 80+ tokens that are hard to maintain.
**Why it happens:** Treating this as a find-and-replace instead of a semantic mapping exercise.
**How to avoid:** Group colors into semantic categories first. Many hex values map to the same semantic concept:
- `#f8fafc`, `#f8f9fa`, `#fafbfd` are all "subtle background" -- use `--color-bg-subtle`
- `#334155`, `#374151`, `#475569` are all "dark text" variants -- evaluate if they are truly distinct or can unify to `--color-text-secondary` or similar
- `#e2e8f0` appears in both borders and gradient endpoints -- it is `--color-border`

### Pitfall 4: Forgetting rgba() and linear-gradient() Values
**What goes wrong:** All `#hex` values are converted but `rgba(0, 0, 0, 0.1)` shadow values and `linear-gradient(135deg, #f8fafc, #f1f5f9)` gradient values are left hardcoded.
**Why it happens:** grep for `#` does not catch `rgba()`. Gradient syntax has colors embedded inside a function call.
**How to avoid:** Run TWO greps: one for `#[0-9a-fA-F]` and one for `rgba?\(`. Shadow `rgba()` values with black/white bases (`rgba(0,0,0,...)`) can stay as-is or be converted to shadow variables. Gradient colors MUST be converted to variables.

### Pitfall 5: Breaking the Existing Variable References
**What goes wrong:** Some component CSS already uses `var(--color-bg-card)` etc. While adding new variables, the existing ones get renamed or broken.
**Why it happens:** Inconsistent naming between old and new tokens.
**How to avoid:** Keep ALL existing variable names exactly as they are. Only ADD new variables. The existing 22 tokens in `:root` are used correctly throughout the codebase and must not be renamed.

## Code Examples

### Example 1: Converting a Section Background

```css
/* BEFORE (Reconciliation.css) */
.recon-section {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid var(--color-border);   /* already uses variable */
  border-radius: var(--radius-lg);
  padding: 20px;
  margin-bottom: 16px;
}

/* AFTER */
.recon-section {
  background: linear-gradient(135deg, var(--color-gradient-section-start) 0%, var(--color-gradient-section-end) 100%);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  margin-bottom: 16px;
}
```

### Example 2: Converting Table Row Alternation

```css
/* BEFORE (LotsTable.css) */
.lots-table tbody tr:nth-child(even) {
  background: #fafbfd;
}
.lots-table tbody tr:nth-child(even):hover {
  background: #f1f5f9;
}

/* AFTER */
.lots-table tbody tr:nth-child(even) {
  background: var(--color-table-row-even);
}
.lots-table tbody tr:nth-child(even):hover {
  background: var(--color-bg-hover);
}
```

### Example 3: Converting Feedback Banners

```css
/* BEFORE (LotsTable.css) */
.sync-success {
  background: #ecfdf5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}
.sync-info {
  background: #eff6ff;
  color: #1e40af;
  border: 1px solid #bfdbfe;
}

/* AFTER */
.sync-success {
  background: var(--color-success-bg);
  color: var(--color-success-text);
  border: 1px solid var(--color-success-border);
}
.sync-info {
  background: var(--color-info-bg);
  color: var(--color-info-text);
  border: 1px solid var(--color-info-border);
}
```

### Example 4: Converting Badge Colors

```css
/* BEFORE (Orderblock.css) */
.ob-badge.conv-low            { background: #f1f5f9; color: var(--color-text-secondary); }
.ob-badge.conv-standard       { background: #dbeafe; color: #1e40af; }
.ob-badge.conv-high           { background: #fef3c7; color: #92400e; }
.ob-badge.conv-institutional  { background: #f3e8ff; color: #6b21a8; }

/* AFTER */
.ob-badge.conv-low            { background: var(--color-bg-muted); color: var(--color-text-secondary); }
.ob-badge.conv-standard       { background: var(--color-info-bg); color: var(--color-info-text); }
.ob-badge.conv-high           { background: var(--color-warning-bg); color: var(--color-warning-text); }
.ob-badge.conv-institutional  { background: var(--color-badge-purple-bg); color: var(--color-badge-purple-text); }
```

### Example 5: Dark Mode Palette Block (for index.css)

```css
/* Dark Mode — defined but not active until Phase 11 adds theme toggle */
[data-theme="dark"] {
  /* Surface Hierarchy */
  --color-bg-page: #0f1117;
  --color-bg-card: #161822;
  --color-bg-subtle: #1e2030;
  --color-bg-muted: #252838;
  --color-bg-hover: #252838;
  --color-bg-selected: #1e2448;

  /* Text Hierarchy */
  --color-text-primary: #e2e8f0;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;
  --color-text-heading: #f1f5f9;

  /* Borders */
  --color-border: #2e3348;
  --color-border-light: #252838;
  --color-border-input: #3e4458;

  /* Semantic (brighter for dark backgrounds) */
  --color-profit: #22c55e;
  --color-loss: #ef4444;

  /* Feedback States */
  --color-success-bg: #052e16;
  --color-success-text: #22c55e;
  --color-success-border: #166534;
  --color-error-bg: #2a0f0f;
  --color-error-text: #ef4444;
  --color-error-border: #991b1b;
  --color-warning-bg: #1c1408;
  --color-warning-text: #fbbf24;
  --color-warning-border: #92400e;
  --color-info-bg: #0c1929;
  --color-info-text: #38bdf8;
  --color-info-border: #0369a1;

  /* Accents (muted for dark) */
  --color-accent-navbar-start: #1e2030;
  --color-accent-navbar-end: #252838;
  --color-accent-pairing: #818cf8;
  --color-accent-recon: #38bdf8;
  --color-accent-orderblock: #fbbf24;

  /* Gradients */
  --color-gradient-section-start: #1e2030;
  --color-gradient-section-end: #252838;

  /* Shadows (darker for dark mode) */
  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.3), 0 4px 16px rgba(0, 0, 0, 0.2);
  --shadow-hover: 0 6px 16px rgba(0, 0, 0, 0.4);
  --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.3);
}
```

## Detailed File Inventory

Hardcoded color occurrences per file (from grep analysis):

| File | Hex Values | rgba() Values | Total | Priority |
|------|-----------|---------------|-------|----------|
| `Orderblock.css` | 83 | 3 | 86 | 1 (largest) |
| `LotsTable.css` | 68 | 7 | 75 | 2 |
| `PairingPanel.css` | 65 | 6 | 71 | 3 |
| `Reconciliation.css` | 49 | 3 | 52 | 4 |
| `CombinedScore.css` | 40 | 2 | 42 | 5 |
| `index.css` | 30 (22 are variable defs) | 3 | 33 (8 actual) | 6 |
| `Overview.css` | 24 | 4 | 28 | 7 |
| `App.css` | 16 | 17 | 33 | 8 |
| `Dashboard.css` | 15 | 3 | 18 | 9 |
| `AlertBanner.css` | 14 | 1 | 15 | 10 |
| `Settings.css` | 12 | 3 | 15 | 11 |
| `FillNotification.css` | 5 | 1 | 6 | 12 |
| **JSX inline styles** | ~30+ | - | ~30+ | 13 |
| **TOTAL** | ~421 CSS + ~30 JSX | 53 | ~504 | - |

### Color Deduplication Map

Many hardcoded values map to the same semantic token. Key groupings:

| Hex Value(s) | Occurrences | Maps To |
|-------------|-------------|---------|
| `#f8fafc` | ~15 | `--color-bg-subtle` (already exists) |
| `#f1f5f9` | ~20 | `--color-bg-muted` / `--color-border-light` (already exists) |
| `#e2e8f0` | ~15 | `--color-border` (already exists) |
| `#334155` | ~10 | `--color-text-dark` (new, or evaluate if `--color-text-primary` suffices) |
| `#475569` | ~12 | `--color-text-body` (new, between primary and secondary) |
| `#d1d5db` | ~8 | `--color-border-input` (new) |
| `#64748b` | ~8 | `--color-text-secondary` (already exists) |
| `#92400e` | ~10 | `--color-warning-text` (new) |
| `#fef3c7` | ~6 | `--color-warning-bg` (new) |
| `#818cf8` | ~6 | `--color-accent-indigo` (new) |
| `#6366f1` | ~8 | `--color-accent-pairing` (already exists) |
| `#22c55e` | ~4 | `--color-profit-bright` (new, or extend `--color-profit`) |
| `#d97706` | ~10 | `--color-accent-orderblock` (already exists) |
| `#1e40af` | ~4 | `--color-info-text` (new) |
| `#bfdbfe` | ~4 | `--color-info-border` (new) |
| `#ecfdf5` / `#f0fdf4` | ~4 | Maps to `--color-success-bg` (approximate match) |
| `#065f46` | ~4 | Maps to `--color-success-text` (approximate match, existing is `#166534`) |
| `#a7f3d0` | ~4 | Maps to `--color-success-border` (approximate match, existing is `#bbf7d0`) |

**Token estimate:** ~50-60 new variables needed beyond the existing 22, for a total of ~72-82 tokens in `:root`. This aligns with the prior research estimate of ~80 tokens.

### Existing Variable Usage (Already Converted)

The following variables are already in use across component CSS files and must NOT be changed:

- `var(--color-bg-card)` -- 15+ usages
- `var(--color-border)` -- 20+ usages
- `var(--color-border-light)` -- 8+ usages
- `var(--color-text-primary)` -- 10+ usages
- `var(--color-text-secondary)` -- 20+ usages
- `var(--color-text-muted)` -- 10+ usages
- `var(--color-text-heading)` -- 4+ usages
- `var(--color-profit)` -- 8+ usages
- `var(--color-loss)` -- 8+ usages
- `var(--color-success-bg/text/border)` -- 10+ usages
- `var(--color-error-bg/text/border)` -- 10+ usages
- `var(--radius-sm/md/lg/xl)` -- 30+ usages
- `var(--shadow-card/hover/sm)` -- 5+ usages
- `var(--font-mono)` -- 3+ usages

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded hex in component CSS | CSS Custom Properties in `:root` | CSS Variables: 2017+ (all browsers) | Enables theming, design tokens, runtime changes |
| `[data-theme]` scattering across files | Single source of truth in `index.css` | Community best practice 2020+ | Eliminates specificity conflicts, single audit point |
| `!important` for override | Proper specificity management | Always | Prevents cascade conflicts with theme variables |

**Deprecated/outdated:**
- CSS preprocessor variables (Sass `$var`): Compile-time only, cannot change at runtime. CSS Custom Properties are strictly superior for theming.
- `filter: invert(1)`: Inverts all colors including images and charts. Unusable for a trading app with precise color semantics.

## Open Questions

1. **Success/info feedback color variants**
   - What we know: Multiple similar-but-not-identical greens are used for success: `#ecfdf5`, `#f0fdf4`, `#dcfce7` (existing variable), `#065f46`, `#166534` (existing variable). Similarly for info blues.
   - What's unclear: Whether the subtle differences between `#ecfdf5` and `#f0fdf4` and `#dcfce7` are intentional design choices or accumulated drift.
   - Recommendation: Normalize to the existing variable values (`--color-success-bg: #dcfce7`). The visual difference between these greens is imperceptible. If a slightly different tint is truly needed, add `--color-success-bg-light` as a variant.

2. **Footer and subnav dark colors**
   - What we know: `App.css` has `.app-footer { background: #1e293b }` and `.symbol-subnav { background: #1e293b }` -- these are already "dark" elements in the light theme.
   - What's unclear: Whether these should use a variable or keep their current dark values.
   - Recommendation: Convert to `--color-bg-footer` and `--color-bg-subnav`. In dark mode these will use the same surface hierarchy as cards.

3. **Dynamic `action_color` from backend API**
   - What we know: `CombinedScore.jsx` receives `data.action_color` from the backend and applies it as an inline style.
   - What's unclear: Whether the backend returns a hex string that would need to change for dark mode.
   - Recommendation: Defer to Phase 11. This is a runtime-computed color, not a static CSS value.

## Verification Strategy

### Per-File Verification
After each CSS file conversion:
```bash
# Count remaining hardcoded hex values (should be zero for converted files)
grep -cn '#[0-9a-fA-F]' frontend/src/components/[ConvertedFile].css
```

### Final Verification (Phase Complete)
```bash
# Must return ONLY lines from :root {} and [data-theme="dark"] {} in index.css
grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css

# Check rgba() values (shadow/overlay values OK, gradient colors NOT OK)
grep -rn 'rgba\?' frontend/src/**/*.css

# Visual: App looks identical in browser (compare screenshots)
npm run build  # Verify no CSS syntax errors
```

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: 12 CSS files fully read and audited (2026-02-24)
- `grep -rn '#[0-9a-fA-F]' frontend/src/**/*.css` -- 421 total hex occurrences counted
- `grep -rn 'rgba' frontend/src/**/*.css` -- 53 total rgba() occurrences counted
- `grep '#[0-9a-fA-F]' frontend/src/**/*.jsx` -- ~30+ inline style color references identified
- Prior research: `.planning/research/SUMMARY.md`, `FEATURES.md`, `PITFALLS.md` (2026-02-23) -- dark palette, pitfall inventory, architecture patterns

### Secondary (MEDIUM confidence)
- WCAG 2.1 Success Criterion 1.4.3 (contrast ratios for dark palette) -- well-established standard
- CSS Custom Properties specification -- fully supported in all modern browsers since 2017

### Tertiary (LOW confidence)
- None -- all findings verified from direct codebase analysis

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries, CSS Custom Properties are native and already partially in use
- Architecture: HIGH - Single-source-of-truth pattern from prior research, confirmed by codebase audit
- Pitfalls: HIGH - All 421+ hardcoded values located and counted via grep; conversion strategy verified against existing codebase patterns

**Research date:** 2026-02-24
**Valid until:** No expiration -- CSS Custom Properties are a stable web standard. The codebase file inventory is accurate as of this date.
