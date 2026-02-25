# Phase 12: Navigation Restructure + Dashboard - Research

**Researched:** 2026-02-25
**Domain:** React Router v7 navigation architecture, component composition, CSS layout
**Confidence:** HIGH

## Summary

Phase 12 restructures the frontend navigation from a flat tab-based model (7 individual items in GlobalNav + SymbolLayout sub-nav) into a 3-area model (Trading, Orderblocks, Admin), integrates the Combined Score hero widget into the per-symbol Dashboard view, removes API Docs from the navbar, and ensures old URLs redirect correctly.

The current architecture is well-suited for this change. React Router v7.13.0 already provides all needed primitives (`Navigate`, nested `Route`, `Outlet`, `NavLink`). The existing 2-tier navigation pattern (GlobalNav for Tier-1 symbol selection, SymbolLayout sub-nav for Tier-2 page selection) maps cleanly onto the 3-area model. The Combined Score hero widget extraction requires lifting the action banner + score bar section from `CombinedScore.jsx` into a compact widget component, then embedding it in the per-symbol Dashboard (currently the orphaned `Dashboard.jsx`, which must be re-integrated into the routing).

No new libraries are needed. No backend changes are required. This is a frontend-only restructuring phase.

**Primary recommendation:** Restructure GlobalNav sub-nav links into 3 grouped areas, re-introduce Dashboard.jsx as the default per-symbol landing page with Combined Score hero widget embedded above KPI cards, add redirect routes for old URLs, and move API Docs link to the footer.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| NAV-01 | 3-Bereichs-Navigation implementieren (Trading, Orderblocks, Admin) | GlobalNav + SymbolLayout sub-nav restructuring. Current flat 4-tab sub-nav (TradeLots, Combined Score, Orderblock, Reconciliation) becomes grouped: Trading (Dashboard, TradeLots), Analysis (Combined Score, Orderblock), Admin (Reconciliation, Settings). Symbol selector stays in Tier-1 GlobalNav. |
| NAV-02 | Combined Score Hero-Widget ins Dashboard integrieren | Extract action banner + score bar from CombinedScore.jsx into CombinedScoreWidget.jsx. Embed in Dashboard.jsx above depot-flow KPIs. Dashboard.jsx becomes default route under SymbolLayout. |
| NAV-03 | API Docs aus Navbar entfernen (Footer-Link oder versteckt) | API Docs is currently NOT in the navbar (already removed in earlier iterations). Verify no residual references. If a link is desired, add to footer or Settings page. |
| NAV-04 | Router-Struktur anpassen (alte URLs redirecten) | Add `<Route path="combined" element={<Navigate to="../analysis/combined" replace />} />` etc. for old bookmark URLs. Test browser back/forward navigation. |
</phase_requirements>

## Standard Stack

### Core (already installed, no changes)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react-router-dom | 7.13.0 | Client-side routing, nested routes, redirects | Already in use. Provides Navigate, Route, Outlet, NavLink |
| @tanstack/react-query | 5.90.20 | Data fetching for Combined Score widget | Already used by CombinedScore.jsx |
| react | 19.2.0 | UI framework | Already in use |

### Supporting (no new dependencies)
No new libraries needed. All patterns use existing react-router-dom and React primitives.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual redirect routes | React Router loader redirects | Loader-based redirects are for framework mode (data routers); this project uses BrowserRouter with declarative Navigate -- stick with Navigate for consistency |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Current Route Structure
```
/                           → Overview.jsx (cross-symbol)
/s/:symbol                  → SymbolLayout.jsx (sub-nav + Outlet)
  /s/:symbol/lots           → LotsTable.jsx (default via Navigate)
  /s/:symbol/combined       → CombinedScore.jsx
  /s/:symbol/orderblock     → Orderblock.jsx
  /s/:symbol/reconciliation → Reconciliation.jsx
/settings                   → Settings.jsx
```

### Target Route Structure
```
/                                      → Overview.jsx (cross-symbol, unchanged)
/s/:symbol                             → SymbolLayout.jsx (restructured sub-nav)
  /s/:symbol/dashboard                 → Dashboard.jsx (with CombinedScoreWidget)  [DEFAULT]
  /s/:symbol/lots                      → LotsTable.jsx
  /s/:symbol/combined                  → CombinedScore.jsx (full detail page)
  /s/:symbol/orderblock                → Orderblock.jsx
  /s/:symbol/reconciliation            → Reconciliation.jsx
/settings                              → Settings.jsx

Redirects for old bookmarks:
  /s/:symbol (index) → /s/:symbol/dashboard (instead of /s/:symbol/lots)
```

### Pattern 1: 3-Area Sub-Navigation in SymbolLayout
**What:** Group the sub-nav links into visual sections with labels
**When to use:** SymbolLayout.jsx sub-nav rendering
**Example:**
```jsx
// SymbolLayout.jsx - restructured sub-nav
<div className="subnav-links">
  <div className="subnav-group">
    <span className="subnav-group-label">Trading</span>
    <NavLink to={`/s/${symbol}/dashboard`}>Dashboard</NavLink>
    <NavLink to={`/s/${symbol}/lots`}>TradeLots</NavLink>
  </div>
  <div className="subnav-group">
    <span className="subnav-group-label">Analyse</span>
    <NavLink to={`/s/${symbol}/combined`}>Combined Score</NavLink>
    <NavLink to={`/s/${symbol}/orderblock`}>Orderblocks</NavLink>
  </div>
  <div className="subnav-group">
    <span className="subnav-group-label">Admin</span>
    <NavLink to={`/s/${symbol}/reconciliation`}>Reconciliation</NavLink>
  </div>
</div>
```

### Pattern 2: Combined Score Hero Widget Extraction
**What:** Extract the action banner + score bar from CombinedScore into a standalone widget
**When to use:** Embedding in Dashboard.jsx
**Example:**
```jsx
// CombinedScoreWidget.jsx - compact version of hero banner
// Fetches combined score data independently (own useQuery)
// Renders: Action label + multiplier + score bar
// Clicking navigates to full /s/:symbol/combined page
const CombinedScoreWidget = () => {
  const { userId } = useUser();
  const { symbol } = useSymbol();
  // ... fetch combined score (same API as CombinedScore.jsx)
  return (
    <div className="combined-widget" onClick={() => navigate(`/s/${symbol}/combined`)}>
      {/* Action Banner (compact) */}
      {/* Score Bar */}
      {/* Click for details hint */}
    </div>
  );
};
```

### Pattern 3: Redirect Routes for Old URLs
**What:** Ensure old bookmark URLs still work after restructure
**When to use:** App.jsx route definitions
**Example:**
```jsx
// In SymbolLayout child routes:
<Route index element={<Navigate to="dashboard" replace />} />
<Route path="dashboard" element={<Dashboard />} />
<Route path="lots" element={<LotsTable />} />
<Route path="combined" element={<CombinedScore />} />
// ... etc.
```
Note: The old `/s/:symbol/combined` URL MUST continue to work (not redirect) since CombinedScore remains a full page. Only the default index route changes from `lots` to `dashboard`.

### Pattern 4: Footer API Docs Link
**What:** Move API Docs link (if needed) to footer
**When to use:** AppContent footer in App.jsx
**Example:**
```jsx
<footer className="app-footer">
  <span>Cashflow Management v0.1.0</span>
  <a href="/docs" target="_blank" rel="noopener noreferrer" className="footer-link">API Docs</a>
  {serverIpData?.ip && (
    <span className="footer-ip">Server IP: {serverIpData.ip}</span>
  )}
</footer>
```

### Recommended Component Structure (changes only)
```
src/
├── components/
│   ├── Dashboard.jsx              # REACTIVATE: per-symbol dashboard (KPIs + CombinedScoreWidget)
│   ├── CombinedScoreWidget.jsx    # NEW: compact hero widget (action + score bar)
│   ├── CombinedScore.jsx          # UNCHANGED: full detail page
│   ├── SymbolLayout.jsx           # MODIFY: 3-area sub-nav grouping
│   ├── GlobalNav.jsx              # MINOR: no API Docs to remove (already absent)
│   └── ...
├── App.jsx                        # MODIFY: add Dashboard route, change default
└── App.css                        # MODIFY: add subnav-group styling
```

### Anti-Patterns to Avoid
- **Duplicating CombinedScore data fetching logic:** Extract the hero widget as a separate component with its own useQuery call. Do NOT copy-paste the full CombinedScore into Dashboard.
- **Breaking existing URLs:** The `/s/:symbol/combined` route MUST remain functional. It is still a full page. Only the index redirect changes.
- **Removing SymbolContext dependency:** Dashboard.jsx uses `useSymbol()` -- it MUST remain a child of SymbolLayout (inside the SymbolProvider). This is already the case.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| URL redirects | Custom redirect logic with useEffect | `<Navigate to="..." replace />` | React Router's built-in Navigate handles all edge cases (replace vs push, relative paths) |
| Active link styling per area | Manual className logic | `NavLink` with `className` callback | Already used throughout the project; consistent pattern |
| Conditional rendering by route | Parsing location.pathname manually | React Router's nested Route + Outlet | Already the established pattern in SymbolLayout |

## Common Pitfalls

### Pitfall 1: Breaking browser history with redirects
**What goes wrong:** Using `<Navigate>` without `replace` creates extra history entries. User presses Back and gets stuck in a redirect loop.
**Why it happens:** Default Navigate behavior is `push`, which adds to history stack.
**How to avoid:** Always use `replace` prop on redirect Navigate elements: `<Navigate to="dashboard" replace />`
**Warning signs:** Pressing Back button does not go to the expected page.

### Pitfall 2: CombinedScoreWidget fetching without SymbolContext
**What goes wrong:** CombinedScoreWidget calls `useSymbol()` but is rendered outside SymbolProvider.
**Why it happens:** Dashboard.jsx is a child route of SymbolLayout, which provides SymbolContext. If accidentally placed outside, it throws.
**How to avoid:** Keep Dashboard.jsx as a child route of SymbolLayout (inside the `<Outlet />`). Never render CombinedScoreWidget on the Overview page (which has no SymbolProvider).
**Warning signs:** "useSymbol must be used within SymbolProvider" error.

### Pitfall 3: Double data fetching for Combined Score
**What goes wrong:** Both CombinedScoreWidget (in Dashboard) and CombinedScore (full page) fetch the same API endpoint, causing duplicate requests when navigating.
**Why it happens:** Both use separate useQuery hooks with the same queryKey.
**How to avoid:** Use the same queryKey pattern: `['combined-score', symbol, userId, interval]`. TanStack Query automatically deduplicates and caches, so navigating from Dashboard to Combined Score page reuses cached data. The `staleTime` should be set to match the refetch interval.
**Warning signs:** Network tab shows duplicate API calls for the same combined score endpoint.

### Pitfall 4: Sub-nav group labels not aligning in dark mode
**What goes wrong:** New `.subnav-group-label` elements use hardcoded colors instead of CSS variables.
**Why it happens:** Copy-paste from light-mode designs without using the established token system.
**How to avoid:** Use only existing CSS custom properties (e.g., `var(--color-text-muted)` for labels). All new CSS MUST use the token system from index.css. No hardcoded hex values.
**Warning signs:** Labels invisible or wrong contrast in dark mode.

### Pitfall 5: Orphan Dashboard.jsx import path confusion
**What goes wrong:** Dashboard.jsx exists but is not currently imported anywhere. It uses `useSymbol()` and `useUser()` contexts, and imports `getDailyPerformance` API function. These are all still functional.
**Why it happens:** Dashboard was the original per-symbol view, later replaced by Overview for cross-symbol.
**How to avoid:** Verify that Dashboard.jsx still works by checking: (1) `getPortfolio` and `getDailyPerformance` API functions exist in client.js (they do), (2) SymbolContext and UserContext are available (they are, via SymbolLayout), (3) Dashboard.css is intact (it is). Then simply add the import and route.
**Warning signs:** Runtime errors about missing API functions or contexts.

## Code Examples

### Current GlobalNav Structure (to be modified)
```jsx
// Source: frontend/src/components/GlobalNav.jsx (current)
// Tier-1: App name | Symbol pills (Overview, BTCEUR, ETHEUR, XRPEUR) | Settings
// No API Docs link exists here currently -- NAV-03 is already satisfied
```

### Current SymbolLayout Sub-Nav (to be restructured)
```jsx
// Source: frontend/src/components/SymbolLayout.jsx (current)
<div className="subnav-links">
  <NavLink to={`/s/${symbol}/lots`}>TradeLots</NavLink>
  <NavLink to={`/s/${symbol}/combined`}>Combined Score</NavLink>
  <NavLink to={`/s/${symbol}/orderblock`}>Orderblock</NavLink>
  <NavLink to={`/s/${symbol}/reconciliation`}>Reconciliation</NavLink>
</div>
```

### CombinedScore Hero Section (to be extracted into widget)
```jsx
// Source: frontend/src/components/CombinedScore.jsx lines 89-132
// The "combined-action-banner" div contains:
// 1. combined-action-main: action label + multiplier
// 2. combined-score-bar-section: score bar with thresholds + indicator
// This section (~40 lines of JSX) becomes CombinedScoreWidget
```

### Dashboard.jsx (to be reactivated and enhanced)
```jsx
// Source: frontend/src/components/Dashboard.jsx (currently orphaned)
// Contains: depot-flow (Eingezahlt -> EUR + BTC = Performance)
// Contains: daily-performance grid (3 cards)
// NEEDS: CombinedScoreWidget added above depot-flow
// Import: import CombinedScoreWidget from './CombinedScoreWidget';
```

### App.jsx Route Changes (target)
```jsx
// Source: frontend/src/App.jsx (to be modified)
import Dashboard from './components/Dashboard';
// ...
<Route path="/s/:symbol" element={<SymbolLayout />}>
  <Route index element={<Navigate to="dashboard" replace />} />
  <Route path="dashboard" element={<Dashboard />} />
  <Route path="lots" element={<LotsTable />} />
  <Route path="combined" element={<CombinedScore />} />
  <Route path="orderblock" element={<Orderblock />} />
  <Route path="reconciliation" element={<Reconciliation />} />
</Route>
```

## Key Findings

### NAV-03 (API Docs removal) is already done
API Docs does NOT appear in GlobalNav or anywhere in the current navigation. The current nav has: App name | Overview pill | Symbol pills | Settings pill. No "API Docs" link exists. This requirement is pre-satisfied. The planner should verify this and optionally add a footer link to `/docs` (FastAPI's auto-generated Swagger UI).

### Dashboard.jsx is an orphan ready for reactivation
Dashboard.jsx exists at `frontend/src/components/Dashboard.jsx` with full functionality (portfolio KPIs, daily performance). It uses `useSymbol()` and `useUser()` contexts correctly. It was the original per-symbol landing page before Overview was created. Dashboard.css is also intact. Reactivation requires only: (1) import in App.jsx, (2) add route, (3) add CombinedScoreWidget.

### Sub-nav grouping is CSS-only
The 3-area grouping (Trading, Analyse, Admin) is achievable with CSS flexbox grouping and small label elements. No JavaScript logic changes needed beyond the JSX structure in SymbolLayout.

### Settings page stays at /settings (not inside SymbolLayout)
Settings is symbol-agnostic. It remains at `/settings` in GlobalNav Tier-1. Reconciliation moves conceptually into "Admin" area within the per-symbol sub-nav, which is logical since reconciliation is per-symbol.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat sub-nav (4 tabs) | 3-area grouped sub-nav | Phase 12 (this phase) | Better information architecture, clearer mental model |
| No per-symbol dashboard | Dashboard with Combined Score widget | Phase 12 | Key trading signal visible immediately on symbol selection |
| Dashboard.jsx orphaned | Dashboard.jsx as default symbol route | Phase 12 | Per-symbol KPIs + daily performance visible again |

## Open Questions

1. **Exact area naming: "Analyse" vs "Analysis" vs "Signals"**
   - What we know: Phase description says "Trading, Orderblocks, Admin"
   - What's unclear: "Orderblocks" as an area name only covers one page (Orderblock). Combined Score is also analysis. Perhaps "Analyse" (German) is better as a group name containing both Combined Score and Orderblocks.
   - Recommendation: Use "Trading" (Dashboard + TradeLots), "Analyse" (Combined Score + Orderblocks), "Admin" (Reconciliation). This matches the phase description's intent while being semantically accurate.

2. **Should the Overview page also get the Combined Score widget?**
   - What we know: The phase description says "Dashboard" which in context means per-symbol Dashboard.
   - What's unclear: Overview currently has per-symbol cards with quick links. Adding aggregated Combined Score there could be valuable.
   - Recommendation: Do NOT add to Overview in this phase. Overview is cross-symbol and would need Combined Score for each symbol -- too complex. Keep phase scope tight.

3. **CombinedScoreWidget click behavior**
   - What we know: Widget should be clickable to see full details.
   - What's unclear: Navigate to `/s/:symbol/combined` or expand inline?
   - Recommendation: Navigate to combined page on click. Simpler, maintains current page architecture.

## Sources

### Primary (HIGH confidence)
- Project source code: `frontend/src/App.jsx`, `frontend/src/components/GlobalNav.jsx`, `frontend/src/components/SymbolLayout.jsx`, `frontend/src/components/Dashboard.jsx`, `frontend/src/components/CombinedScore.jsx`, `frontend/src/components/Overview.jsx`
- Project CSS: `frontend/src/index.css` (CSS custom property system), `frontend/src/App.css` (nav + subnav styles), `frontend/src/components/CombinedScore.css`, `frontend/src/components/Dashboard.css`
- react-router-dom 7.13.0 installed in `frontend/node_modules/`
- `.planning/ROADMAP.md` for phase description and success criteria
- `.planning/REQUIREMENTS.md` for NAV-01 through NAV-04 definitions

### Secondary (MEDIUM confidence)
- [React Router v7 Redirect patterns](https://www.robinwieruch.de/react-router-redirect/) - Navigate component usage confirmed
- [React Router v7 Nested Routes](https://www.robinwieruch.de/react-router-nested-routes/) - Outlet pattern confirmed

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries, all patterns already in use
- Architecture: HIGH - Straightforward restructuring of existing patterns (nested routes, sub-nav CSS)
- Pitfalls: HIGH - Well-understood domain (React Router redirects, component extraction, CSS variables)
- NAV-03 status: HIGH - Verified via source code that API Docs is already absent from navigation

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable -- no moving dependencies)
