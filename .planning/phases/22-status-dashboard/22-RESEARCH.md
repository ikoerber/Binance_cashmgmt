# Phase 22: Status Dashboard - Research

**Researched:** 2026-02-28
**Domain:** React frontend — status/health dashboard component + global navigation indicator
**Confidence:** HIGH

## Summary

Phase 22 is a pure frontend task that consumes two existing data sources: (1) the `GET /api/health/{user_id}` endpoint (Phase 19) returning structured per-service health with overall status, and (2) the WebSocketContext reconnect state fields (`reconnecting`, `reconnectAttempts`, `lastError`) added in Phase 21. No backend changes are needed.

The implementation consists of three deliverables: a `StatusDashboard.jsx` component rendering 8 service cards with color-coded status, an API client function (`getHealth`) to fetch health data, and a status dot in the `GlobalNav.jsx` component reflecting overall system health. The project already has comprehensive CSS variable foundations for success/warning/error states in both light and dark modes, a well-established card-based layout pattern (Dashboard.jsx), and TanStack Query for data fetching with auto-polling — all of which this phase reuses directly.

**Primary recommendation:** Build StatusDashboard.jsx as a top-level route (`/status`) following the existing Dashboard.jsx card grid pattern, poll `/api/health/{user_id}` every 10 seconds via TanStack Query, and add a small colored dot to GlobalNav that links to this page.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-01 | StatusDashboard.jsx im Admin-Bereich mit per-Service Status-Karten (gruen/amber/rot) | Card grid pattern from Dashboard.jsx/Dashboard.css, CSS variables for success/warning/error already defined in index.css, health API returns 8 services with structured status |
| DASH-02 | Last-Check Timestamps und Relative-Age-Anzeige pro Service | Health API returns `last_checked` as ISO 8601 per service and `checked_at` at top level; relative time computed client-side with simple `Date.now() - Date.parse(ts)` arithmetic |
| DASH-03 | WebSocket Reconnect-State Anzeige (attempts, error) aus WebSocketContext | WebSocketContext already exposes `reconnecting` (boolean), `reconnectAttempts` (number), `lastError` (string/null) via `useWebSocket()` hook |
| DASH-04 | Global Nav Status-Dot (gruen/amber/rot) mit Link zum Dashboard | GlobalNav.jsx currently has no right-side elements; `navbar-content` uses flexbox with `justify-content: space-between`; health polling query can be lifted to App level or duplicated in GlobalNav with long staleTime |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 19.2.0 | Component framework | Already in project |
| @tanstack/react-query | 5.90.20 | Data fetching, caching, polling | Already in project, used by every data component |
| react-router-dom | 7.13.0 | Routing (`/status` route, NavLink) | Already in project |
| axios | 1.13.5 | HTTP client (via `api/client.js`) | Already in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| vitest | 4.0.18 | Frontend unit tests | Test StatusDashboard rendering, status mapping logic |
| @testing-library/react | 16.3.2 | React component testing | Test card rendering, color logic |

### Alternatives Considered

None needed. This phase uses exclusively existing project dependencies.

**Installation:**
No new packages required.

## Architecture Patterns

### Recommended Project Structure

```
frontend/src/
├── components/
│   ├── StatusDashboard.jsx     # New: full-page status view
│   └── StatusDashboard.css     # New: component-scoped styles
├── api/
│   └── client.js               # Modified: add getHealth() function
└── App.jsx                     # Modified: add /status route
frontend/src/components/
└── GlobalNav.jsx               # Modified: add status dot with Link
```

### Pattern 1: TanStack Query Polling (from existing codebase)

**What:** Use `useQuery` with `refetchInterval` for periodic health checks
**When to use:** StatusDashboard needs fresh data every 10 seconds
**Example:**
```jsx
// Pattern already used in SymbolLayout.jsx (dry-run status polling)
const { data: health, isLoading, error } = useQuery({
  queryKey: ['health', userId],
  queryFn: () => getHealth(userId),
  refetchInterval: 10_000,  // 10s polling
  staleTime: 5_000,         // Match server-side 5s cache TTL
});
```

### Pattern 2: Card Grid Layout (from Dashboard.jsx)

**What:** CSS Grid with `auto-fit` and `minmax` for responsive service cards
**When to use:** Rendering the 8 service status cards
**Example:**
```css
/* Existing pattern from Dashboard.css */
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}
```

### Pattern 3: Status-to-Color Mapping

**What:** Map backend status values to existing CSS variables
**When to use:** Color-coding service cards and the global nav dot

| Backend Status | Color Category | CSS Variable | Visual |
|---------------|----------------|-------------|--------|
| `ok` | success/green | `--color-profit` / `--color-success-*` | Green |
| `stale`, `degraded`, `stopped` | warning/amber | `--color-warning-*` / `--color-status-partial` | Amber |
| `error`, `unavailable` | error/red | `--color-loss` / `--color-error-*` | Red |

Overall status mapping:
| Overall | Dot Color |
|---------|-----------|
| `healthy` | green (`--color-profit`) |
| `degraded` | amber (`--color-status-partial`) |
| `critical` | red (`--color-loss`) |

### Pattern 4: Relative Time Display

**What:** Compute "X seconds ago" from ISO timestamp without external library
**When to use:** DASH-02 requires relative age indicator per service card
**Example:**
```jsx
function formatRelativeAge(isoTimestamp) {
  if (!isoTimestamp) return 'never';
  const seconds = Math.floor((Date.now() - new Date(isoTimestamp).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}
```

### Pattern 5: API Client Function (from existing codebase)

**What:** Add `getHealth` to `api/client.js` following existing patterns
**Example:**
```javascript
// Follows exact pattern of getSettings, getDryRunStatus, etc.
export const getHealth = async (userId) => {
  const response = await apiClient.get(`/api/health/${userId}`);
  return response.data;
};
```

### Pattern 6: Route Registration (from App.jsx)

**What:** Add `/status` as a top-level route (like `/settings` and `/backtest`)
**When to use:** StatusDashboard is symbol-independent — not nested under `/s/:symbol`
**Example:**
```jsx
// In App.jsx, alongside existing top-level routes
<Route path="/status" element={<StatusDashboard />} />
```

### Pattern 7: GlobalNav Status Dot

**What:** Small colored circle in the global navigation bar linking to `/status`
**When to use:** DASH-04 requires always-visible system health indicator
**Implementation approach:**
- Add `getHealth` query in GlobalNav with longer `staleTime` (30s) and `refetchInterval` (15s) to avoid excessive polling
- Render a small dot (8-10px circle) with background-color derived from `overall_status`
- Wrap in `<NavLink to="/status">` for navigation
- Position in right side of `navbar-content` (flexbox already supports this via `.global-nav-right` class which exists but is unused)

### Anti-Patterns to Avoid

- **Separate WebSocket channel for health data:** The backend health endpoint has a 5s server-side cache. Simple HTTP polling at 10s is efficient and matches the architecture. No need for a WebSocket health stream.
- **External date/time libraries for relative age:** A simple "X seconds/minutes ago" does not justify importing date-fns or dayjs. Plain arithmetic suffices.
- **Lifting health state into a global React Context:** Health data is only consumed in two places (StatusDashboard + GlobalNav). TanStack Query's built-in cache sharing via `queryKey: ['health', userId]` means both components share the same cached data automatically without a custom context.
- **Custom polling timer via setInterval:** TanStack Query's `refetchInterval` handles this correctly including cleanup, error retry, and focus management.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Data polling | Custom setInterval + fetch | TanStack Query `refetchInterval` | Handles cache, error retry, window focus, cleanup |
| Color theming | Inline color constants | CSS variables from index.css | Dark mode support already established |
| Relative time | date-fns / dayjs import | Simple arithmetic function | Only needs "Xs ago" / "Xm ago" — trivial |
| Card layout | Custom flex layout | CSS Grid `auto-fit` (Dashboard.css pattern) | Proven responsive pattern in project |
| Cache sharing | React Context for health data | TanStack Query queryKey dedup | Two consumers with same queryKey share cache automatically |

**Key insight:** This phase introduces no new patterns or libraries. Every pattern needed already exists in the codebase — the task is purely assembly and composition.

## Common Pitfalls

### Pitfall 1: Stale Relative Time Display
**What goes wrong:** The "12s ago" label becomes stale because the component only re-renders when health data refetches (every 10s), but the relative time should update more frequently.
**Why it happens:** React component doesn't re-render between TanStack Query refetches.
**How to avoid:** Use a separate `useEffect` with a 1-second `setInterval` to update a `now` state variable, which forces the relative time to recompute every second. Keep the health data polling at 10s.
**Warning signs:** Timestamp shows "5s ago" and stays frozen for 10 seconds until next data fetch.

### Pitfall 2: Double Health Polling (GlobalNav + StatusDashboard)
**What goes wrong:** Both GlobalNav and StatusDashboard fire separate HTTP requests to `/api/health/{user_id}`.
**Why it happens:** Two `useQuery` hooks with identical queryKey and different refetchIntervals.
**How to avoid:** TanStack Query deduplicates queries with the same key automatically. The shorter `refetchInterval` wins. If GlobalNav uses 15s and StatusDashboard uses 10s, the effective interval when both are mounted is 10s. When StatusDashboard unmounts, it falls back to 15s. This is correct and efficient.
**Warning signs:** Network tab shows double requests at the same time (would indicate different queryKeys).

### Pitfall 3: Missing Dark Mode Support
**What goes wrong:** Status colors look correct in light mode but are invisible or wrong in dark mode.
**Why it happens:** Using hardcoded hex colors instead of CSS variables.
**How to avoid:** Exclusively use CSS variables from index.css. Both `:root` and `[data-theme="dark"]` sections already define matching success/warning/error variables.
**Warning signs:** Any hex color (`#16a34a`) directly in the component CSS instead of `var(--color-*)`.

### Pitfall 4: WebSocket Context Not Available Outside SymbolLayout
**What goes wrong:** Attempting to use `useWebSocket()` in StatusDashboard throws "useWebSocket muss innerhalb von WebSocketProvider verwendet werden".
**Why it happens:** Misunderstanding the component tree. Actually, WebSocketProvider wraps the entire AppContent (see App.jsx line 79), so it IS available everywhere including `/status` route.
**How to avoid:** Verify the provider hierarchy: `BrowserRouter > QueryClientProvider > WebSocketProvider > UserProvider > AppContent > Routes`. StatusDashboard at `/status` is inside WebSocketProvider.
**Warning signs:** None — this is NOT a real issue. WebSocketProvider is at the top level.

### Pitfall 5: Health Endpoint Requires Auth
**What goes wrong:** Health endpoint returns 401/403 when API key is missing.
**Why it happens:** The route is registered with `api_auth_with_user` dependency.
**How to avoid:** The `apiClient` in `api/client.js` already includes `X-API-Key` header on every request. Using `apiClient.get()` for health will work.
**Warning signs:** 401 responses in dev console when health polling starts.

## Code Examples

Verified patterns from the actual project codebase:

### Health API Response Structure (from health_check_service.py)
```json
{
  "overall_status": "healthy",
  "services": {
    "backend": { "name": "backend", "status": "ok", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "" },
    "db": { "name": "db", "status": "ok", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "" },
    "websocket": { "name": "websocket", "status": "ok", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "" },
    "dry_run": { "name": "dry_run", "status": "stopped", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "Dry run service not running" },
    "alpha_score": { "name": "alpha_score", "status": "ok", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "" },
    "sentiment": { "name": "sentiment", "status": "ok", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "" },
    "macro": { "name": "macro", "status": "ok", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "" },
    "binance_rest": { "name": "binance_rest", "status": "ok", "last_checked": "2026-02-28T10:00:00+00:00", "detail": "" }
  },
  "checked_at": "2026-02-28T10:00:00+00:00"
}
```

### WebSocket Reconnect State (from WebSocketContext.jsx)
```javascript
// Available via useWebSocket() hook:
const {
  connected,           // boolean — WebSocket currently connected
  reconnecting,        // boolean — currently in reconnect backoff
  reconnectAttempts,   // number — attempts since last disconnect (0 when connected)
  lastError,           // string|null — last error/close reason (null when connected)
} = useWebSocket();
```

### Service Display Names Map
```javascript
// Human-readable names for the 8 backend services
const SERVICE_LABELS = {
  backend: 'Backend',
  db: 'Database',
  websocket: 'WebSocket',
  dry_run: 'Dry Run',
  alpha_score: 'Alpha Score',
  sentiment: 'Sentiment',
  macro: 'Macro Signal',
  binance_rest: 'Binance REST',
};
```

### Valid Status Values (from health_check_service.py)
```
ok          → green  (service fully functional)
stale       → amber  (cache expired, data may be outdated)
degraded    → amber  (partial functionality)
stopped     → amber  (intentionally not running, e.g. dry_run when disabled)
unavailable → red    (cannot reach service / no data at all)
error       → red    (unexpected failure)
```

### Overall Status Values
```
healthy   → all services ok
degraded  → any service stale/degraded/stopped (but none error/unavailable)
critical  → any service error/unavailable
```

### GlobalNav Right Side (existing but unused CSS)
```css
/* Already in App.css */
.global-nav-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `/health` stub (always returns healthy) | `GET /api/health/{user_id}` with 8 real service checks | Phase 19 (2026-02-28) | Dashboard can now consume real health data |
| No WebSocket reconnect visibility | `reconnecting`, `reconnectAttempts`, `lastError` in context | Phase 21 (2026-02-28) | Dashboard can show WS connection state |

**Deprecated/outdated:**
- Old `/health` stub at line 150-153 of main.py still exists for backward compatibility but returns a simple `{"status": "healthy"}`. The dashboard must use `/api/health/{user_id}` instead.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | vitest 4.0.18 + @testing-library/react 16.3.2 |
| Config file | `frontend/vitest.config.js` (exists, jsdom environment, globals: true) |
| Quick run command | `cd frontend && npx vitest run --reporter=verbose` |
| Full suite command | `cd frontend && npx vitest run` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | StatusDashboard renders 8 service cards with correct color classes | unit | `cd frontend && npx vitest run src/components/__tests__/StatusDashboard.test.jsx -x` | Wave 0 |
| DASH-02 | Each card shows last-checked timestamp and relative age | unit | `cd frontend && npx vitest run src/components/__tests__/StatusDashboard.test.jsx -x` | Wave 0 |
| DASH-03 | WebSocket reconnect state displayed when reconnecting | unit | `cd frontend && npx vitest run src/components/__tests__/StatusDashboard.test.jsx -x` | Wave 0 |
| DASH-04 | GlobalNav renders status dot with correct color and link | unit | `cd frontend && npx vitest run src/components/__tests__/GlobalNav.test.jsx -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd frontend && npx vitest run --reporter=verbose`
- **Per wave merge:** `cd frontend && npx vitest run && cd ../backend && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `frontend/src/components/__tests__/StatusDashboard.test.jsx` -- covers DASH-01, DASH-02, DASH-03
- [ ] `frontend/src/components/__tests__/GlobalNav.test.jsx` -- covers DASH-04

## Open Questions

1. **StatusDashboard route path: `/status` or nested under `/s/:symbol`?**
   - What we know: Health status is symbol-independent (checks all 8 services globally). Settings and Backtest are already top-level routes (`/settings`, `/backtest`).
   - Recommendation: Use `/status` as a top-level route, consistent with other cross-cutting admin pages.

2. **Where to place Status Dashboard link in navigation?**
   - What we know: SymbolLayout has an "Admin" subnav group containing Reconciliation, Settings, and API Docs. GlobalNav only has symbol pills and the app title.
   - Recommendation: The status dot in GlobalNav (DASH-04) serves as the primary navigation entry point. Additionally, add a "Status" link in the SymbolLayout Admin subnav group for discoverability when inside a symbol context.

## Sources

### Primary (HIGH confidence)
- `backend/app/services/health_check_service.py` — HealthCheckService implementation, ServiceStatus dataclass, compute_overall_status
- `backend/app/api/routes/health.py` — Health route endpoint structure
- `backend/tests/test_health_check.py` — Response structure verification
- `frontend/src/contexts/WebSocketContext.jsx` — reconnecting/reconnectAttempts/lastError fields
- `frontend/src/components/Dashboard.jsx` + `Dashboard.css` — Card grid layout pattern
- `frontend/src/App.jsx` — Route structure, provider hierarchy
- `frontend/src/components/GlobalNav.jsx` — Current nav structure
- `frontend/src/components/SymbolLayout.jsx` — Subnav pattern, Admin group
- `frontend/src/index.css` — Full CSS variable system (light + dark mode)
- `frontend/src/api/client.js` — API client patterns
- `frontend/package.json` — Library versions
- `.planning/phases/19-health-check-foundation/19-VERIFICATION.md` — Health endpoint verification
- `.planning/phases/21-websocket-recovery-listen-key-hardening/21-02-SUMMARY.md` — WebSocket reconnect state

### Secondary (MEDIUM confidence)
None needed — all information sourced from project codebase.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries needed, all versions verified from package.json
- Architecture: HIGH — all patterns directly observed in existing codebase components
- Pitfalls: HIGH — identified from actual code analysis (provider hierarchy, query dedup behavior, CSS variable system)

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable — no external dependencies or API changes expected)
