# Phase 23: Navigation Structure - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Move Settings, Status, and Backtest pages inside SymbolLayout so the sub-navigation (Trading/Analyse/Bot/Admin groups) is visible on every page. These pages are not symbol-specific, but they gain navigation context from being inside SymbolLayout.

</domain>

<decisions>
## Implementation Decisions

### Symbol context handling
- Live price ticker stays visible on all pages including Settings/Status/Backtest — consistent experience
- Settings remains purely global — symbol in URL is for nav context only, does not affect page content
- StatusDashboard remains purely system-wide — no symbol-specific highlighting or filtering
- When user switches symbol in GlobalNav while on Settings, stay on Settings page (buildSymbolUrl already handles this: /s/ETHEUR/settings)

### Backtest symbol sync
- Pre-select Backtest's symbol dropdown from URL symbol (/s/XRPEUR/backtest → XRP/EUR pre-selected)
- When user changes symbol in Backtest's dropdown, navigate to new URL (/s/BTCEUR/backtest) to keep URL and state in sync
- Keep the Backtest symbol dropdown as inline quick-switch — don't remove it in favor of GlobalNav only

### URL design & redirects
- Old bookmarked URLs (/settings, /status, /backtest) redirect to /s/{lastSymbol}/settings etc.
- Default symbol for redirects: last visited symbol, remembered via localStorage
- Fallback if no last symbol: BTCEUR
- Overview page (/) stays as the global landing page — not affected by symbol memory

### Sub-nav restructure
- Move Backtest link from Analyse group to Bot group (Backtest tests Alpha Score signals, logically belongs with Bot Dashboard and Decision Log)
- Remove API Docs link from sub-nav entirely — keep footer link only
- Highlight active link only (standard NavLink isActive pattern) — no group-level highlighting
- Updated Bot group: Bot Dashboard, Decision Log, Backtest
- Updated Admin group: Reconciliation, Settings, Status

### Claude's Discretion
- localStorage key naming for last-visited-symbol
- Exact redirect implementation (React Router Navigate vs useEffect)
- How Backtest component reads initial symbol from SymbolContext vs useParams

</decisions>

<specifics>
## Specific Ideas

No specific requirements — standard React Router restructuring with established patterns.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SymbolLayout.jsx`: Already provides SymbolProvider (symbol + marketPrice) + sub-nav + live price. Routes just need to be nested inside it.
- `GlobalNav.jsx`: `buildSymbolUrl()` already preserves sub-path when switching symbols — /s/BTCEUR/settings → /s/ETHEUR/settings works automatically.
- `useUser()` hook: Settings and StatusDashboard use this for userId — remains unchanged inside SymbolLayout.
- `useWebSocket()` hook: Used by StatusDashboard and Backtest — available globally, not affected by move.

### Established Patterns
- Symbol-scoped routing: All pages under /s/:symbol/* use `<Outlet />` inside SymbolLayout
- NavLink active state: `className={({ isActive }) => ...}` handles highlighting
- TanStack Query caching: Backtest uses queryKeys without symbol — will need symbol in key for URL sync

### Integration Points
- `App.jsx`: Routes need restructuring — move 3 routes from top-level into SymbolLayout's children
- `SymbolLayout.jsx`: Sub-nav links for Settings/Status need to change from absolute (/settings) to symbol-relative (/s/:symbol/settings)
- Backtest already has `SYMBOLS` constant + dropdown state — needs to read initial value from `useParams()` or SymbolContext
- React Router `<Navigate>` components for redirect routes (/settings → /s/{last}/settings)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 23-navigation-structure*
*Context gathered: 2026-02-28*
