# Phase 21: WebSocket Recovery + Listen Key Hardening - Research

**Researched:** 2026-02-28
**Domain:** Binance WebSocket User Data Stream lifecycle, reconnect recovery, health monitoring
**Confidence:** HIGH

## Summary

This phase addresses four requirements around making the WebSocket User Data Stream resilient: automatic post-reconnect reconciliation (WSRC-01), listen key freshness tracking in the health endpoint (WSRC-02), immediate reconnect on keepalive failure (WSRC-03), and frontend reconnect state exposure (WSRC-04).

**CRITICAL DISCOVERY:** The project's current User Data Stream implementation uses the legacy `userDataStream.start` / `userDataStream.ping` / `userDataStream.stop` WebSocket API methods, which were **removed from Binance production on 2026-02-20 07:00 UTC** (8 days ago). This means the User Data Stream is currently non-functional. This phase MUST migrate to the new `userDataStream.subscribe.signature` method as a prerequisite to all other work. The new method uses HMAC-SHA256 signed requests on the `wss://ws-api.binance.com:443/ws-api/v3` endpoint and eliminates the need for listen keys entirely -- subscriptions are managed per-session with a `subscriptionId`.

The migration actually simplifies several requirements: without listen keys, there is no "listen key expiry" to detect. Instead, freshness tracking (WSRC-02) shifts to monitoring the last-received user data message timestamp. The keepalive concern (WSRC-03) transforms from "ping failed, reconnect" to "no message received for N seconds, reconnect." Post-reconnect reconciliation (WSRC-01) remains unchanged in concept but becomes more reliable since the new subscription method provides explicit connection lifecycle events.

**Primary recommendation:** Migrate `BinanceStreamManager._run_user_data_stream()` from legacy `userDataStream.start` + listen key + separate stream connection to a single persistent `ws-api/v3` connection with `userDataStream.subscribe.signature`. Add `_last_user_data_message_at` timestamp tracking, post-reconnect fill reconciliation, and expose reconnect state to the frontend.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WSRC-01 | Post-Reconnect Reconciliation: automatic orders reconciliation after WebSocket reconnect | ReconciliationService.reconcile_fills() already exists with `trigger` parameter support. After reconnect, call `reconcile_fills()` with `start_time` set to disconnect timestamp. Run in asyncio.to_thread to avoid blocking the event loop. |
| WSRC-02 | Listen Key Freshness Tracking: Health DEGRADED when User Data Stream >90s without message | Add `_last_user_data_message_at: Optional[datetime]` to BinanceStreamManager. Update on every executionReport/outboundAccountPosition. HealthCheckService._check_websocket() compares age against 90s threshold. With new API, this replaces listen key monitoring entirely. |
| WSRC-03 | Keepalive-Failure triggers immediate Reconnect | With legacy API removal, this transforms: the new `subscribe.signature` method uses a persistent WebSocket connection. If the connection drops or receives no messages for >90s, trigger immediate reconnect instead of waiting. The old keepalive ping loop becomes unnecessary. |
| WSRC-04 | Frontend reconnect state (reconnecting, attempts, error) in WebSocketContext | WebSocketContext already tracks `reconnectAttempts.current` and `connected`. Add `reconnecting` (boolean), `reconnectAttempts` (number), and `lastError` (string) to the context value. These are derived from existing `ws.onclose` / `ws.onerror` / `scheduleReconnect()` flow. |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiohttp | (existing) | WebSocket client for Binance streams | Already used in project for both price and user data streams |
| asyncio | (stdlib) | Async coordination, task management | Project pattern for all async operations |
| hmac + hashlib | (stdlib) | HMAC-SHA256 signature generation | Required for `userDataStream.subscribe.signature` |
| urllib.parse | (stdlib) | URL-encoding params for signature | Binance requires alphabetically-sorted URL-encoded params |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | (existing) | Async test support | Testing async reconnect and health check logic |
| unittest.mock | (stdlib) | Mocking WebSocket connections | All tests -- no real Binance connections in unit tests |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| aiohttp WebSocket | websockets library | aiohttp already in project, switching adds dependency |
| Manual HMAC signing | python-binance library | python-binance uses sync Client, project uses async aiohttp for streams -- mixing would complicate architecture |

**Installation:**
No new packages required. All dependencies are already in the project.

## Architecture Patterns

### Recommended Changes to Existing Structure

```
backend/app/services/
├── websocket_manager.py          # MODIFY: Replace listen key flow with subscribe.signature,
│                                 #   add _last_user_data_message_at tracking,
│                                 #   add _reconnect_count tracking,
│                                 #   add post-reconnect reconciliation trigger
├── websocket_event_handler.py    # UNCHANGED
├── websocket_fill_handler.py     # UNCHANGED
├── health_check_service.py       # MODIFY: _check_websocket() adds user data freshness check
└── reconciliation_service.py     # UNCHANGED (already has reconcile_fills with start_time)

frontend/src/contexts/
└── WebSocketContext.jsx           # MODIFY: Expose reconnecting, reconnectAttempts, lastError
```

### Pattern 1: Subscribe.Signature Authentication (replaces listen key)

**What:** Single persistent WebSocket connection to `wss://ws-api.binance.com:443/ws-api/v3` that subscribes to user data via HMAC-signed request.
**When to use:** Every time the user data stream needs to be established or re-established.
**Example:**

```python
# Source: https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/user-data-stream-requests
import hashlib
import hmac
import time
from urllib.parse import urlencode
from uuid import uuid4

def _build_subscribe_message(api_key: str, api_secret: str) -> dict:
    """Build userDataStream.subscribe.signature request."""
    timestamp = int(time.time() * 1000)
    params = {
        "apiKey": api_key,
        "timestamp": timestamp,
    }
    # Signature: HMAC-SHA256 of alphabetically-sorted URL-encoded params
    query_string = urlencode(sorted(params.items()))
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    params["signature"] = signature

    return {
        "id": str(uuid4()),
        "method": "userDataStream.subscribe.signature",
        "params": params,
    }
```

### Pattern 2: Message Freshness Tracking

**What:** Track `_last_user_data_message_at` timestamp on every received user data message. Health check compares this against a 90-second threshold.
**When to use:** Every `executionReport` and `outboundAccountPosition` message updates the timestamp.
**Example:**

```python
# In BinanceStreamManager
self._last_user_data_message_at: Optional[datetime] = None

# In message handler
if msg.type == aiohttp.WSMsgType.TEXT:
    data = json.loads(msg.data)
    event_type = data.get("e")
    if event_type in ("executionReport", "outboundAccountPosition"):
        self._last_user_data_message_at = datetime.now(timezone.utc)
```

### Pattern 3: Post-Reconnect Fill Reconciliation

**What:** After a successful reconnect, automatically run `reconcile_fills()` to recover any fills that arrived during the disconnect gap.
**When to use:** Every time `_run_user_data_stream()` successfully establishes a new connection (except the first time).
**Example:**

```python
# In _user_data_stream_loop after successful reconnect
if reconnect_count > 0:
    disconnect_time_iso = disconnect_at.isoformat() if disconnect_at else None
    asyncio.create_task(
        self._post_reconnect_reconciliation(user_id, disconnect_time_iso)
    )

async def _post_reconnect_reconciliation(self, user_id: str, start_time: str):
    """Run fill reconciliation in thread pool after reconnect."""
    try:
        await asyncio.to_thread(
            self._sync_reconcile_fills, user_id, start_time
        )
        logger.info("Post-reconnect reconciliation completed: user=%s", user_id)
    except Exception:
        logger.exception("Post-reconnect reconciliation failed: user=%s", user_id)
```

### Pattern 4: Frontend Reconnect State

**What:** Expose `reconnecting`, `reconnectAttempts`, and `lastError` from WebSocketContext.
**When to use:** UI components that need to display connection status (StatusDashboard in Phase 22).
**Example:**

```javascript
// In WebSocketContext
const [reconnecting, setReconnecting] = useState(false);
const [lastError, setLastError] = useState(null);

// In ws.onclose handler
setConnected(false);
setReconnecting(true);

// In ws.onopen handler (after auth)
setConnected(true);
setReconnecting(false);
setLastError(null);
reconnectAttempts.current = 0;

// In ws.onerror handler
setLastError(error.message || 'WebSocket connection error');

// Exposed value
const value = {
    connected,
    reconnecting,
    reconnectAttempts: reconnectAttempts.current,
    lastError,
    // ... existing fields
};
```

### Anti-Patterns to Avoid

- **Polling for freshness instead of tracking on message receipt:** Do not make periodic REST API calls to check if the stream is alive. Track last-message time passively.
- **Blocking the event loop with reconciliation:** Reconciliation involves DB queries and Binance REST API calls. Always run via `asyncio.to_thread()`.
- **Creating a new WebSocket connection per subscribe:** The `subscribe.signature` method works on the same `ws-api/v3` connection. Do not open a separate connection for the user data stream -- subscribe on the existing connection.
- **Reconnecting on every transient error:** Use exponential backoff (already implemented). Do not reconnect immediately on every error -- only on keepalive failure / connection close.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fill gap recovery | Custom diff algorithm comparing WS vs DB | ReconciliationService.reconcile_fills(start_time) | Already handles idempotent fill import with FIFO allocation, respects user strategy |
| HMAC signing | Custom crypto implementation | stdlib hmac + hashlib | Standard, audited, used by Binance official examples |
| WebSocket reconnection | Custom state machine | Existing backoff loop in _user_data_stream_loop | Already works, just needs disconnect timestamp tracking added |
| Health status aggregation | New health check mechanism | Existing HealthCheckService pattern | Just extend _check_websocket() with freshness check |

**Key insight:** All four requirements can be implemented by extending existing patterns. No new services or modules are needed.

## Common Pitfalls

### Pitfall 1: Subscribe.Signature Param Ordering

**What goes wrong:** Signature validation fails because params are not alphabetically sorted before signing.
**Why it happens:** Binance requires params sorted alphabetically for signature computation. URL encoding without explicit sorting produces platform-dependent ordering.
**How to avoid:** Always use `urlencode(sorted(params.items()))` when building the signature payload.
**Warning signs:** HTTP 401 / signature mismatch errors from Binance WebSocket API.

### Pitfall 2: Reconciliation Flooding on Flaky Connection

**What goes wrong:** Repeated rapid disconnects/reconnects trigger multiple concurrent reconciliation runs, causing DB contention and duplicate processing.
**Why it happens:** Each reconnect triggers `reconcile_fills()`, and if reconnects happen every few seconds, reconciliations pile up.
**How to avoid:** Add a minimum interval between reconciliation runs (e.g., 60 seconds). Track `_last_reconciliation_at` and skip if too recent. Also: reconciliation is idempotent (fill handler checks `source_id` for duplicates), so flooding causes performance issues, not data corruption.
**Warning signs:** Multiple "Post-reconnect reconciliation" log entries within seconds of each other.

### Pitfall 3: Race Between Reconnect and Old Message Processing

**What goes wrong:** Fill handler is still processing a fill from the old connection when reconnect reconciliation starts, causing duplicate lot creation attempts.
**Why it happens:** `asyncio.create_task()` for fill processing runs concurrently with reconnect logic.
**How to avoid:** Fill handler is already idempotent (checks `source_id` for duplicates). No additional synchronization needed -- but do not add non-idempotent side effects to the fill handler.
**Warning signs:** "Fill bereits verarbeitet" debug logs appearing during reconnect (this is expected and safe).

### Pitfall 4: Testnet vs Production WebSocket API URL

**What goes wrong:** Using production URL on testnet or vice versa.
**Why it happens:** The `ws-api` endpoint differs between testnet and production.
**How to avoid:** Keep the existing testnet detection pattern: `wss://testnet.binance.vision/ws-api/v3` for testnet, `wss://ws-api.binance.com:443/ws-api/v3` for production.
**Warning signs:** Connection timeouts or auth failures in development/testing.

### Pitfall 5: Not Loading API_SECRET for WebSocket Manager

**What goes wrong:** `_build_subscribe_message()` fails because `api_secret` is None.
**Why it happens:** Current `BinanceStreamManager` only loads `BINANCE_API_KEY` in `start_user_data_stream()`. The new method also needs `BINANCE_API_SECRET`.
**How to avoid:** Load both `BINANCE_API_KEY` and `BINANCE_API_SECRET` in `start_user_data_stream()`. Store as `self._api_secret`.
**Warning signs:** TypeError or empty signature in subscribe request.

### Pitfall 6: Silent Connection State on ws-api/v3

**What goes wrong:** The `ws-api/v3` WebSocket connection stays open but the subscription silently expires or the server stops sending events.
**Why it happens:** Network issues, server-side cleanup, or subscription limits (max 1000 active subscriptions per session).
**How to avoid:** Track `_last_user_data_message_at` and trigger reconnect if no message for >90 seconds. The health endpoint surfaces this as DEGRADED to alert the user.
**Warning signs:** Health endpoint reports "websocket" as "degraded" with detail about user data stream silence.

## Code Examples

Verified patterns from official sources and existing codebase:

### HMAC-SHA256 Signature for Binance WebSocket API

```python
# Source: https://github.com/binance/binance-signature-examples/blob/master/python/websocket-api/websocket_api_client.py
import hashlib
import hmac
import time
from urllib.parse import urlencode
from uuid import uuid4

def _build_subscribe_message(api_key: str, api_secret: str) -> dict:
    """Build userDataStream.subscribe.signature request.

    Params MUST be alphabetically sorted before signing.
    """
    timestamp = int(time.time() * 1000)
    params = {
        "apiKey": api_key,
        "timestamp": timestamp,
    }
    query_string = urlencode(sorted(params.items()))
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    params["signature"] = signature

    return {
        "id": str(uuid4()),
        "method": "userDataStream.subscribe.signature",
        "params": params,
    }
```

### Post-Reconnect Reconciliation (using existing service)

```python
# Uses existing ReconciliationService.reconcile_fills()
# Source: backend/app/services/reconciliation_service.py (project codebase)
from app.db.database import SessionLocal
from app.services.binance import BinanceService
from app.services.reconciliation_service import ReconciliationService

def _sync_reconcile_fills(user_id: str, start_time: str):
    """Synchronous fill reconciliation for thread pool execution."""
    import os
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"

    binance_service = BinanceService(api_key, api_secret, testnet=testnet)
    recon_service = ReconciliationService(binance_service)

    db = SessionLocal()
    try:
        from app.symbol_registry import KNOWN_PAIRS
        for symbol in KNOWN_PAIRS:
            recon_service.reconcile_fills(db, user_id, symbol, start_time)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

### Health Check Freshness Extension

```python
# Extends existing _check_websocket() in health_check_service.py
# Source: backend/app/services/health_check_service.py (project codebase)

async def _check_websocket(self) -> ServiceStatus:
    """Check BinanceStreamManager state + user data freshness."""
    now_iso = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)
    try:
        manager = get_stream_manager()
        stats = manager.get_stats()

        if not stats.get("running"):
            return ServiceStatus(
                name="websocket", status="stopped", last_checked=now_iso,
                detail="Stream manager not running",
            )

        if not stats.get("current_prices"):
            return ServiceStatus(
                name="websocket", status="degraded", last_checked=now_iso,
                detail="Running but no prices received",
            )

        # WSRC-02: User data stream freshness
        last_msg = manager.last_user_data_message_at
        if last_msg is not None:
            age_seconds = (now - last_msg).total_seconds()
            if age_seconds > 90:
                return ServiceStatus(
                    name="websocket", status="degraded", last_checked=now_iso,
                    detail=f"User data stream silent for {int(age_seconds)}s",
                )

        return ServiceStatus(name="websocket", status="ok", last_checked=now_iso)
    except Exception as e:
        return ServiceStatus(
            name="websocket", status="error", last_checked=now_iso, detail=str(e),
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Listen key via REST/WS API (`userDataStream.start/ping/stop`) | `userDataStream.subscribe.signature` on ws-api/v3 | 2025-08-12 (added), 2026-02-20 (old removed) | **BREAKING**: Legacy methods removed from production 2026-02-20. Project MUST migrate. |
| Separate data stream connection (`wss://stream.binance.com/ws/{listenKey}`) | Single ws-api/v3 connection with subscription | 2025-04-07 (deprecated) | Simplified architecture: one connection serves both API requests and data stream |
| No `listenKeyExpired` event on Spot | `listenKeyExpired` event added (moot with new API) | 2024-04-02 | Was the original pain point, but migration to subscribe.signature eliminates the issue entirely |
| 30-min keepalive pings for listen key | Subscription managed by server, no client keepalive needed | 2025-08-12 | Eliminates keepalive failure mode entirely |

**Deprecated/outdated:**
- `userDataStream.start`: Removed from production 2026-02-20. Replaced by `userDataStream.subscribe.signature`.
- `userDataStream.ping`: Removed. No keepalive needed with new subscription model.
- `userDataStream.stop`: Removed. Use `userDataStream.unsubscribe` instead.
- Listen key concept: Deprecated. Subscriptions are now session-scoped via signed requests.

## Architectural Decision: Unified vs Separate WebSocket Connection

The new `userDataStream.subscribe.signature` method works on the `ws-api/v3` endpoint. This means user data events arrive on the same WebSocket connection used for API requests, not on a separate stream connection.

**Current architecture (broken):**
1. Price stream: `wss://stream.binance.com:9443/stream?streams=...` (public, works)
2. User data: `wss://stream.binance.com:9443/ws/{listenKey}` (BROKEN -- listen key API removed)

**New architecture:**
1. Price stream: `wss://stream.binance.com:9443/stream?streams=...` (public, unchanged)
2. User data: `wss://ws-api.binance.com:443/ws-api/v3` with `subscribe.signature` (new)

The user data connection changes from a passive stream to an interactive API session. Messages arrive as responses and subscription events on the same connection. The response format wraps events differently:
- Old: Raw event JSON `{"e": "executionReport", ...}`
- New: Still raw event JSON for subscription events (same format after subscription confirmation)

The subscribe response includes a `subscriptionId` that can be used for targeted unsubscribe.

## Open Questions

1. **Response format after subscribe.signature**
   - What we know: The subscribe call returns `{"status": 200, "result": {"subscriptionId": 0}}`. After that, user data events flow on the same connection.
   - What's unclear: Whether events are wrapped in an envelope or arrive as raw JSON (like the old stream). The Binance docs suggest they arrive as raw events, same format as before.
   - Recommendation: Implement and test. The event handler already parses `data.get("e")` which should work either way. Add a fallback parser if events arrive wrapped.

2. **Testnet support for subscribe.signature**
   - What we know: Testnet added this method earlier than production. The endpoint is `wss://testnet.binance.vision/ws-api/v3`.
   - What's unclear: Whether testnet has fully removed the legacy methods yet (testnet removal was 2026-02-04).
   - Recommendation: Test against testnet. If legacy methods still work there, the migration can be tested incrementally.

3. **Connection persistence without keepalive**
   - What we know: The old model required 30-min keepalive pings. The new model manages subscriptions server-side.
   - What's unclear: Whether the ws-api/v3 connection itself has an idle timeout that requires periodic pings.
   - Recommendation: Keep the aiohttp WebSocket connection's default ping/pong mechanism. Add application-level heartbeat if testing reveals idle disconnects.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | backend/pytest.ini (if exists) or pyproject.toml |
| Quick run command | `cd backend && python -m pytest tests/test_websocket_recovery.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -x` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WSRC-01 | Post-reconnect reconciliation triggers after reconnect | unit | `pytest tests/test_websocket_recovery.py::test_post_reconnect_reconciliation_triggered -x` | Wave 0 |
| WSRC-01 | Reconciliation uses disconnect timestamp as start_time | unit | `pytest tests/test_websocket_recovery.py::test_reconciliation_uses_disconnect_time -x` | Wave 0 |
| WSRC-01 | Reconciliation skipped if too recent (debounce) | unit | `pytest tests/test_websocket_recovery.py::test_reconciliation_debounce -x` | Wave 0 |
| WSRC-02 | Health returns DEGRADED when user data >90s silent | unit | `pytest tests/test_health_check.py::test_websocket_user_data_degraded_90s -x` | Wave 0 |
| WSRC-02 | Health returns OK when user data recent | unit | `pytest tests/test_health_check.py::test_websocket_user_data_ok -x` | Wave 0 |
| WSRC-02 | Health OK when no user data subscribers (no stream expected) | unit | `pytest tests/test_health_check.py::test_websocket_no_user_data_subscribers_ok -x` | Wave 0 |
| WSRC-03 | Subscribe.signature message is correctly built (HMAC, sorted params) | unit | `pytest tests/test_websocket_recovery.py::test_build_subscribe_message -x` | Wave 0 |
| WSRC-03 | Reconnect triggered when connection drops | unit | `pytest tests/test_websocket_recovery.py::test_reconnect_on_connection_drop -x` | Wave 0 |
| WSRC-04 | WebSocketContext exposes reconnecting, reconnectAttempts, lastError | manual-only | Manual: verify in browser devtools that context value includes new fields | N/A |
| WSRC-04 | reconnecting=true during reconnect, false after connect | manual-only | Manual: disconnect backend, verify UI shows reconnecting state | N/A |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_websocket_recovery.py tests/test_health_check.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_websocket_recovery.py` -- covers WSRC-01, WSRC-03 (new file)
- [ ] `tests/test_health_check.py` -- covers WSRC-02 (extend existing file with 3 new tests)

*(WSRC-04 is frontend-only and tested manually)*

## Sources

### Primary (HIGH confidence)
- [Binance Spot API Changelog](https://developers.binance.com/docs/binance-spot-api-docs) - Confirmed `userDataStream.start/ping/stop` removed from production 2026-02-20 07:00 UTC
- [Binance WebSocket API User Data Stream Requests](https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/user-data-stream-requests) - `userDataStream.subscribe.signature` method specification, added 2025-08-12
- [Binance Signature Examples (Python)](https://github.com/binance/binance-signature-examples/blob/master/python/websocket-api/websocket_api_client.py) - Official HMAC-SHA256 signing implementation
- [Binance Spot Testnet Changelog](https://developers.binance.com/docs/binance-spot-api-docs/testnet) - Legacy methods removed from testnet 2026-02-04
- Project codebase: `backend/app/services/websocket_manager.py` - Current implementation using deprecated methods
- Project codebase: `backend/app/services/health_check_service.py` - Existing health check patterns
- Project codebase: `backend/app/services/reconciliation_service.py` - Existing reconciliation with `start_time` support

### Secondary (MEDIUM confidence)
- [Binance Dev Community: How to detect listenKey expiration on Spot](https://dev.binance.vision/t/how-to-detect-listenkey-expiration-on-userdatastream-websocket-for-spot/1370) - Confirmed no listenKeyExpired on Spot historically, now moot with API migration
- [CCXT Issue #26858: listenKey deprecation](https://github.com/ccxt/ccxt/issues/26858) - Community confirmation of migration path, resolved Sep 2025

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All tools are stdlib or already in project
- Architecture: HIGH - Extends existing patterns, Binance migration path is well-documented
- Pitfalls: HIGH - Based on official changelog and direct codebase analysis
- Migration urgency: HIGH - Legacy API already removed from production 8 days ago

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable -- Binance API changes are infrequent once released)
