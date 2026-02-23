# Architecture Patterns: Dark Mode + Navigation Redesign + XRPBTC Removal

**Domain:** Frontend redesign + backend cleanup for BTC/EUR Cashflow-Management App
**Researched:** 2026-02-23
**Confidence:** HIGH (based on direct codebase analysis, no external research needed)

## Recommended Architecture

Three independent workstreams that intersect at well-defined points:

```
[1] XRPBTC Removal (Backend-first)
    |
    +-- Symbol Registry cleanup
    +-- Domain model simplification
    +-- DB migration (soft-delete XRPBTC data)
    +-- Test cleanup
    |
[2] Dark Mode (CSS-first, independent)
    |
    +-- CSS custom property system expansion
    +-- Dark theme token set in index.css
    +-- Theme toggle + persistence
    +-- Component CSS migration (hardcoded -> var())
    |
[3] Navigation Restructuring (Router + Layout)
    |
    +-- New AppShell layout component
    +-- 3-section router restructure
    +-- Combined Score dashboard integration
    +-- API Docs removal
```

### Intersection Points

| Point | Components Involved | Dependency |
|-------|---------------------|------------|
| Symbol pills in navbar | [1] + [3] | XRPBTC removal affects GlobalNav symbol list |
| Overview.jsx BTC-quote logic | [1] + [3] | XRPBTC removal simplifies Overview aggregation |
| CSS variable system | [2] + [3] | Navigation redesign needs dark-mode-aware colors |
| PairingPanel cross-pair toggle | [1] + [3] | Removing XRPBTC eliminates `hasMultipleSymbols` for XRP |

## Component Boundaries

### New Components

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `AppShell.jsx` | Top-level layout: sidebar/topbar + content area | App.jsx, all route components |
| `ThemeProvider.jsx` (or context) | Theme state (dark/light), persists to localStorage | AppShell, all CSS via `:root` |
| `SidebarNav.jsx` (or `TopNav.jsx`) | 3-section navigation: Trading / Orderblocks / Admin | React Router, SymbolContext |

### Modified Components (Frontend)

| Component | What Changes | Why |
|-----------|-------------|-----|
| `App.jsx` | Route restructure: remove `/s/:symbol/combined`, add Combined to Dashboard layout, remove API Docs route | 3-section nav + Combined Score integration |
| `GlobalNav.jsx` | Remove XRPBTC from symbol pills, restructure to 3-section nav | Nav redesign + XRPBTC removal |
| `SymbolLayout.jsx` | Remove Combined Score subnav link, remove XRPBTC from KNOWN_PAIRS redirect | Nav restructure + cleanup |
| `Dashboard.jsx` | Integrate CombinedScore component inline (below or beside KPI cards) | Combined Score moves to dashboard |
| `Overview.jsx` | Remove `toEur()` BTC-quote conversion, remove deduplication comment about "XRPEUR + XRPBTC", simplify `binanceValueByBase` | XRPBTC removal eliminates all non-EUR quote paths |
| `PairingPanel.jsx` | Remove cross-pair toggle (`hasMultipleSymbols` becomes false for all assets once XRPBTC is gone) | XRPBTC removal |
| `PairingExistingTab.jsx` | Remove XRPBTC price fetching in simulation, remove routing_decision display, remove cross-pair label | XRPBTC removal |
| `SimulationModal.jsx` | Remove `dual_route_comparison` section entirely | XRPBTC removal |
| `index.css` | Add dark theme tokens as `[data-theme="dark"]` override | Dark Mode |
| `App.css` | Convert remaining hardcoded colors to CSS vars; navbar colors for dark mode | Dark Mode + Nav redesign |
| All component `.css` files | Audit for hardcoded colors, convert to `var()` references | Dark Mode |
| `symbolRegistry.js` | Remove XRPBTC entry from KNOWN_PAIRS | XRPBTC removal |

### Modified Components (Backend)

| Component | What Changes | Why |
|-----------|-------------|-----|
| `symbol_registry.py` | Remove XRPBTC from KNOWN_PAIRS | Core removal |
| `domain/models.py` | Remove `RouteDetails`, `DualRouteComparison`, `RoutingDecision` dataclasses | Dead code after XRPBTC removal |
| `domain/pairing.py` | Remove `compute_dual_route_comparison()` function | Dead code |
| `domain/orders.py` | Remove Satoshi encoding branch (`target_price_rounded < 1`), simplify `price_enc` | No sub-1 prices without BTC-quoted pairs |
| `services/order_service.py` | Remove cross-pair routing block (lines 334-374), remove `routing_decision` persistence, simplify `_verify_order_on_binance` default symbol | Cross-pair routing eliminated |
| `services/pairing_service.py` | Remove `base_asset` parameter from functions, remove `use_eur_cost=True` code paths, remove dual-route comparison in simulation | Cross-pair eliminated |
| `services/lot_service.py` | Remove `quote_to_eur_rate` parameter documentation for XRPBTC | Comment cleanup |
| `services/sync_service.py` | Remove historical quote-to-EUR rate fetching for BTC-quoted fills | No more BTC-quoted fills |
| `api/routes/pairing.py` | Remove `base_asset` query parameter from suggestions/create/list, remove `xrpbtc_price`/`btceur_price` from simulate | API simplification |
| `db/models.py` | Keep `base_asset`, `routing_decision_json`, `cost_eur`, `lot_symbol` columns (historical data) but stop populating for new records. Consider nullable annotations | Backward compat for existing data |

### Test Files to Modify or Delete

| File | Action | Reason |
|------|--------|--------|
| `test_sell_routing.py` | **DELETE** | Tests XRPBTC sell routing exclusively |
| `test_cross_pair_pairing.py` | **DELETE** | Tests cross-pair pairing with XRPBTC |
| `test_portfolio_cross_pair.py` | **DELETE** | Tests portfolio with XRPBTC lots |
| `test_sell_allocation_isolation.py` | **MODIFY** | Remove XRPBTC-specific test cases, keep EUR-pair isolation tests |
| `test_eur_cost_basis.py` | **MODIFY** | Remove XRPBTC backfill tests, keep EUR-pair cost basis tests |
| `test_order_filters.py` | **MODIFY** | Remove XRPBTC filter tests if any |
| `test_pairing.py` | **REVIEW** | May have cross-pair test cases to remove |

### Database Migration

| Action | Detail | Risk |
|--------|--------|------|
| **DO NOT** delete XRPBTC lots/events | Historical data must remain queryable | None (read-only) |
| **DO NOT** drop `base_asset`, `routing_decision_json`, `cost_eur` columns | Existing rows reference these | None (backward compat) |
| **DO** mark XRPBTC lots as CLOSED | Prevents them appearing in active queries | Low (reversible) |
| **CONSIDER** Alembic migration to close open XRPBTC lots | Set `status = CLOSED`, `qty_base_open = 0` for XRPBTC lots | Medium (needs review of actual XRPBTC lot count) |

## Data Flow

### Current (with XRPBTC)

```
GlobalNav → getAllSymbols() → [BTCEUR, ETHEUR, XRPEUR, XRPBTC]
                                                         ↑
                                                    Remove this

Overview → portfolioQueries per symbol → toEur() for BTC-quoted → dedup by base
                                              ↑
                                         Remove this branch

PairingPanel → crossPairMode → base_asset=XRP → loads XRPEUR + XRPBTC lots
                                                                    ↑
                                                              Remove this

OrderService → routing_decision → fetch XRPBTC + BTCEUR prices → compare routes
                                        ↑
                                   Remove entire block
```

### After (EUR-only)

```
GlobalNav → getAllSymbols() → [BTCEUR, ETHEUR, XRPEUR]

Overview → portfolioQueries per symbol → all EUR-quoted → simple sum (no conversion)

PairingPanel → single-pair mode only (crossPairMode always false, toggle hidden)

OrderService → single-pair execution (no routing decision needed)
```

### Dark Mode Data Flow

```
User clicks toggle → ThemeProvider sets data-theme on <html>
                   → localStorage.setItem('theme', 'dark')
                   → CSS :root variables override via [data-theme="dark"] selector
                   → All components pick up changes automatically via var() references
```

## Patterns to Follow

### Pattern 1: CSS Custom Properties for Theming

**What:** Define all colors as CSS custom properties in `:root`, override in `[data-theme="dark"]`
**When:** All color references in component CSS files
**Why:** The codebase already uses this pattern partially (index.css has 30+ CSS vars). Extend it to cover ALL colors.

**Current state:** `index.css` defines `--color-profit`, `--color-loss`, `--color-text-*`, `--color-bg-*`, `--color-accent-*`. But many component CSS files still use hardcoded hex values (e.g., `#1e293b`, `#64748b` in App.css).

```css
/* index.css - existing light theme tokens */
:root {
  --color-bg-page: #f5f7fa;
  --color-bg-card: #ffffff;
  --color-text-primary: #1e293b;
  /* ... existing vars ... */
}

/* NEW: Dark theme override */
[data-theme="dark"] {
  --color-bg-page: #0f172a;
  --color-bg-card: #1e293b;
  --color-text-primary: #f1f5f9;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;
  --color-text-heading: #f8fafc;
  --color-border: #334155;
  --color-border-light: #1e293b;
  --color-bg-subtle: #1e293b;
  --color-bg-muted: #0f172a;
  --color-success-bg: rgba(22, 163, 74, 0.15);
  --color-success-text: #4ade80;
  --color-success-border: rgba(22, 163, 74, 0.3);
  --color-error-bg: rgba(220, 38, 38, 0.15);
  --color-error-text: #f87171;
  --color-error-border: rgba(220, 38, 38, 0.3);
  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.3), 0 4px 16px rgba(0, 0, 0, 0.2);
  --shadow-hover: 0 6px 16px rgba(0, 0, 0, 0.4);
  --color-accent-navbar-start: #4f46e5;
  --color-accent-navbar-end: #6d28d9;
}
```

### Pattern 2: Theme Toggle with localStorage Persistence

**What:** Simple context or hook that reads/writes theme preference
**When:** App initialization + user toggle interaction

```jsx
// ThemeProvider.jsx (or useTheme hook)
const getInitialTheme = () => {
  const stored = localStorage.getItem('theme');
  if (stored) return stored;
  // Respect OS preference
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

// On mount: document.documentElement.setAttribute('data-theme', theme);
// On toggle: update state + localStorage + data-theme attribute
```

### Pattern 3: Feature Removal via Symbol Registry

**What:** Remove XRPBTC from `KNOWN_PAIRS` dict, let cascading effects surface as errors
**When:** First step of XRPBTC removal
**Why:** Symbol Registry is the single source of truth. Removing the entry causes all consumers to fail explicitly rather than silently processing XRPBTC data.

```python
# symbol_registry.py - BEFORE
KNOWN_PAIRS = {
    "BTCEUR": TradingPair(...),
    "ETHEUR": TradingPair(...),
    "XRPEUR": TradingPair(...),
    "XRPBTC": TradingPair(...),  # REMOVE
}

# AFTER
KNOWN_PAIRS = {
    "BTCEUR": TradingPair(...),
    "ETHEUR": TradingPair(...),
    "XRPEUR": TradingPair(...),
}
```

Then fix all code that breaks. The `get_symbols_for_base_asset("XRP")` will return `["XRPEUR"]` instead of `["XRPEUR", "XRPBTC"]`, which means `hasMultipleSymbols` becomes false, cross-pair paths become dead code.

### Pattern 4: 3-Section Navigation Structure

**What:** Replace flat 7-tab nav with grouped sections
**When:** Router restructure

```
Trading (default section)
  ├── Overview (/)
  ├── /s/:symbol (Dashboard + CombinedScore integrated)
  ├── /s/:symbol/lots
  └── /s/:symbol/pairing (if separated)

Orderblocks
  └── /s/:symbol/orderblock

Admin
  ├── /s/:symbol/reconciliation
  └── /settings
```

**Navigation UI options:**
- **Option A: Horizontal section tabs + symbol pills** (keep current top-bar layout, add section grouping)
- **Option B: Sidebar with sections** (more app-like, better for dark mode trading aesthetic)

Recommendation: **Option A** -- less structural change, keeps the existing mental model. The 3 sections become top-level tabs, symbol pills stay in the header. Combined Score moves from subnav into Dashboard component.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Premature Column Deletion

**What:** Dropping DB columns (`base_asset`, `routing_decision_json`, `cost_eur`, `lot_symbol`, `quote_to_eur_rate`) because XRPBTC is removed
**Why bad:** Existing historical data references these columns. Pairings with `routing_decision_json` are audit records. Lots with `cost_eur` from XRPBTC purchases are valid historical data. Dropping columns would lose data and require complex migration.
**Instead:** Keep columns, stop populating them for new records. Add a comment marking them as legacy. `cost_eur` and `quote_to_eur_rate` remain useful for EUR-quoted lots too (they just equal `cost_quote` and `1.0`).

### Anti-Pattern 2: Global CSS Reset for Dark Mode

**What:** Rewriting all CSS files from scratch for dark mode
**Why bad:** 12 CSS files with established patterns. Rewriting risks visual regressions.
**Instead:** Systematically convert hardcoded colors to `var()` references, one file at a time. The existing `index.css` already defines the token vocabulary. Most files already use `var()` (LotsTable.css, Dashboard.css, etc.) -- only `App.css` and some components have significant hardcoded values.

### Anti-Pattern 3: Removing Code Before Tests Pass

**What:** Deleting cross-pair domain logic, then deleting the tests that cover it
**Why bad:** No safety net. If something was missed, there is no test to catch it.
**Instead:** First update tests to reflect EUR-only behavior, verify they pass, then remove dead cross-pair code and their now-obsolete tests.

### Anti-Pattern 4: Mixing Theme Toggle with Navigation Restructure

**What:** Implementing dark mode and navigation changes in the same component edits
**Why bad:** Hard to debug which change caused a visual regression
**Instead:** Dark mode (CSS variables) and navigation (Router + layout) are independent workstreams. Merge them at the end.

## XRPBTC Removal: Complete File Inventory

### Files to DELETE (7 files)

| File | Lines | Reason |
|------|-------|--------|
| `backend/tests/test_sell_routing.py` | ~150 | XRPBTC sell routing tests |
| `backend/tests/test_cross_pair_pairing.py` | ~200 | Cross-pair pairing tests |
| `backend/tests/test_portfolio_cross_pair.py` | ~100 | Cross-pair portfolio tests |
| `backend/scripts/backfill_cost_eur.py` | ~50 | One-time migration script (already ran) |

### Files to MODIFY (Backend, ~20 files)

| File | Changes | Scope |
|------|---------|-------|
| `symbol_registry.py` | Remove XRPBTC entry, simplify `get_symbols_for_base_asset` docstring | 3 lines |
| `domain/models.py` | Remove `RouteDetails`, `DualRouteComparison`, `RoutingDecision` (lines 246-299) | ~55 lines removed |
| `domain/pairing.py` | Remove `compute_dual_route_comparison()` (~70 lines), remove `use_eur_cost` parameter and branches | ~100 lines removed |
| `domain/orders.py` | Remove Satoshi encoding branch, remove `btceur_rate` parameter | ~15 lines |
| `services/order_service.py` | Remove cross-pair routing block (lines 332-374), routing_decision persistence, BTC-quote order value calc | ~60 lines removed |
| `services/pairing_service.py` | Remove `base_asset` params, `use_eur_cost` code paths, dual-route simulation block | ~80 lines removed |
| `services/sync_service.py` | Remove historical quote-to-EUR fetching for BTC-quoted fills | ~20 lines |
| `services/lot_service.py` | Remove XRPBTC docstring reference | 1 line |
| `api/routes/pairing.py` | Remove `base_asset` params, `xrpbtc_price`/`btceur_price` params | ~30 lines |
| `db/models.py` | Add comments marking `base_asset`, `routing_decision_json` as legacy | Comments only |

### Files to MODIFY (Frontend, ~10 files)

| File | Changes | Scope |
|------|---------|-------|
| `utils/symbolRegistry.js` | Remove XRPBTC entry | 1 line |
| `components/Overview.jsx` | Remove `toEur()`, dedup-by-base logic, BTC-quote display branches | ~30 lines simplified |
| `components/PairingPanel.jsx` | Remove cross-pair toggle, `crossPairMode` state, `hasMultipleSymbols` check | ~20 lines |
| `components/PairingExistingTab.jsx` | Remove XRPBTC price fetch, routing_decision display, cross-pair label | ~30 lines |
| `components/SimulationModal.jsx` | Remove entire `dual_route_comparison` section (lines 89-134) | ~45 lines |
| `components/PairingPanel.css` | Remove `.cross-pair-toggle`, `.cross-pair-label` styles | ~30 lines |
| `api/client.js` | Remove `xrpbtcPrice`/`btceurPrice` params from `simulatePairing`, remove `baseAsset` from `createPairing`/`getPairingSuggestions` | ~10 lines |

### CSS Files Requiring Dark Mode Audit

| File | Current var() Usage | Hardcoded Colors to Convert |
|------|--------------------|-----------------------------|
| `index.css` | Defines all vars | Add `[data-theme="dark"]` override block |
| `App.css` | Partial (navbar uses vars) | `#f5f7fa` body bg, `#1e293b` footer, `#334155` borders, `#94a3b8` footer text, symbol-pill hardcoded colors |
| `LotsTable.css` | Heavy var() usage | Minimal hardcoded remaining |
| `Dashboard.css` | Uses vars | Some hardcoded flow-arrow colors |
| `CombinedScore.css` | Uses vars | Action-color inline styles (dynamic, handled differently) |
| `Orderblock.css` | Uses vars | Score gradient colors (dynamic) |
| `PairingPanel.css` | Mixed | Several hardcoded hex values in route-card, sim sections |
| `Reconciliation.css` | Uses vars | Minimal |
| `Settings.css` | Uses vars | Minimal |
| `Overview.css` | Uses vars | Some hardcoded |
| `AlertBanner.css` | Uses vars | Minimal |
| `FillNotification.css` | Uses vars | Minimal |

## Scalability Considerations

Not applicable for this redesign (no new data volume, no new API calls, no new backend compute). This is purely structural cleanup and CSS theming.

## Suggested Build Order

### Phase 1: XRPBTC Backend Removal (no frontend changes needed)

**Rationale:** Backend-first because the Symbol Registry is the source of truth. Removing XRPBTC from the registry causes all dependent code paths to surface explicitly. Backend changes are independently testable.

1. Remove XRPBTC from `symbol_registry.py` (both backend and frontend)
2. Run full test suite -- collect all failures
3. Fix failures by removing cross-pair code paths in domain, services, API routes
4. Delete test files: `test_sell_routing.py`, `test_cross_pair_pairing.py`, `test_portfolio_cross_pair.py`
5. Modify remaining test files that reference XRPBTC
6. Alembic migration: close any open XRPBTC lots (if they exist)
7. Verify: full test suite green, API docs show simplified endpoints

### Phase 2: Dark Mode CSS System (independent of Phase 1)

**Rationale:** Pure CSS work, no component logic changes. Can be done in parallel with Phase 1.

1. Add `[data-theme="dark"]` token set to `index.css`
2. Create `ThemeProvider` context (or `useTheme` hook) with localStorage persistence
3. Add theme toggle button to nav (temporary placement)
4. Audit and convert `App.css` hardcoded colors to `var()` references
5. Audit and convert all 12 component CSS files (one commit per file for reviewability)
6. Test: every component renders correctly in both light and dark mode
7. Handle edge cases: inline styles (CombinedScore `action_color`, Orderblock score gradients), lightweight-charts theme

### Phase 3: Navigation Restructure (after Phase 1 for clean symbol list)

**Rationale:** Depends on Phase 1 (XRPBTC gone from symbol list) and Phase 2 (dark-mode-aware CSS for new nav components).

1. Create `AppShell.jsx` layout component with 3-section navigation
2. Restructure React Router in `App.jsx`: group routes into Trading/Orderblocks/Admin sections
3. Integrate CombinedScore into Dashboard.jsx (remove standalone route `/s/:symbol/combined`)
4. Remove API Docs link from navigation
5. Update `SymbolLayout.jsx` subnav to reflect new structure (remove Combined Score link)
6. Adapt `GlobalNav.jsx` -> new `SidebarNav.jsx` or redesigned top nav
7. Move theme toggle to permanent location in new nav
8. Frontend cleanup: remove unused imports, dead code from cross-pair UI

### Phase ordering rationale:

- **Phase 1 before Phase 3** because the navigation depends on a clean symbol list (3 pairs, not 4)
- **Phase 2 parallel with Phase 1** because CSS custom properties are independent of business logic
- **Phase 3 last** because it touches the most component files and benefits from both Phase 1 (clean data model) and Phase 2 (dark mode tokens available)

## Sources

- Direct codebase analysis of 50+ files across backend and frontend
- Existing CSS variable system in `index.css` (30+ tokens already defined)
- Existing cross-pair code in `order_service.py`, `pairing_service.py`, `pairing.py` (domain)
- XRPBTC grep across full repository (51 files reference XRPBTC)
- Current router structure in `App.jsx`, `GlobalNav.jsx`, `SymbolLayout.jsx`

---

*Generated: 2026-02-23*
