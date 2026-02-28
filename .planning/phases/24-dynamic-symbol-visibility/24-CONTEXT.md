# Phase 24: Dynamic Symbol Visibility - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Filter symbol pills in GlobalNav and cards in Overview to only show symbols the user actually holds (positive Binance balance). A backend endpoint returns which symbols have positive balances, and the frontend uses this to filter the static `getAllSymbols()` list.

</domain>

<decisions>
## Implementation Decisions

### XRPBTC handling
- Show XRPBTC when user holds XRP (regardless of BTC balance) — XRP holders want cross-pair visibility
- XRPBTC gets both a GlobalNav pill and an Overview card — consistent with EUR-quoted pairs
- Keep the `btc-quoted` CSS class distinction on XRPBTC pill — visual differentiation is helpful
- When user sells all XRP, XRPBTC disappears on the next balance refresh (not delayed to session end)
- If user is on XRPBTC page when it disappears, redirect to Overview

### Claude's Discretion
- Balance threshold (what counts as "holding" — any balance > 0 or a meaningful minimum to exclude dust)
- Backend endpoint design (new dedicated endpoint vs extending existing portfolio API)
- Update/refresh frequency for the active symbols list (polling interval, cache strategy)
- Fallback behavior when user holds zero assets (empty nav, always show BTCEUR, etc.)

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for the areas left to Claude's discretion.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BinanceService.fetch_account_balance()`: Already queries Binance account, returns `{asset: Decimal}` dict — can power the active-symbols endpoint
- `BinanceService.get_account()`: Raw account info including all balances (free + locked)
- `reconciliation_service.reconcile_balances()`: Already fetches and parses Binance balances for BTC/EUR comparison — pattern exists

### Established Patterns
- `getAllSymbols()` in `symbolRegistry.js`: Returns all 4 KNOWN_PAIRS keys — currently hardcoded, used by GlobalNav (line 73) and Overview (line 35)
- `useQueries` pattern in Overview.jsx: Parallel portfolio queries per symbol — needs to filter symbol list before querying
- `useQuery` pattern with `refetchInterval`: Used throughout for polling (health at 15s, portfolio at 30s staleTime)
- WebSocket balance events: `outboundAccountPosition` events already pushed to frontend via WebSocketContext

### Integration Points
- `GlobalNav.jsx` line 73: `getAllSymbols().map(sym => ...)` — replace with filtered list from active-symbols query
- `Overview.jsx` line 35: `const symbols = getAllSymbols()` — replace with filtered list
- `App.jsx`: SymbolRedirect component reads localStorage fallback — must handle case where fallback symbol is not in active list
- `SymbolLayout.jsx`: Currently renders for any symbol in URL — may need to handle navigation to a symbol that's no longer active

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 24-dynamic-symbol-visibility*
*Context gathered: 2026-02-28*
