# Pitfalls Research

**Domain:** Hardening + Monitoring additions to BTC/EUR Cashflow-Management Trading App — Health-Check System, Telegram Bot Notifications, WebSocket Auto-Reconnect, Status Dashboard
**Researched:** 2026-02-28
**Confidence:** HIGH (based on deep codebase analysis + verified against Binance API docs + Telegram API docs for current rate limits)

---

## Critical Pitfalls

### Pitfall 1: Health Checks That Return "Healthy" When Services Are Actually Broken

**What goes wrong:**
A health endpoint returns HTTP 200 with `{"status": "healthy"}` even when the services it claims to check are silently failing. This happens when health checks test the wrong thing:

- Database health check executes `SELECT 1` (always succeeds even if WAL checkpoint is stuck or disk is full)
- Binance REST health check tests connectivity to `api.binance.com` (succeeds even if rate limit is exhausted and all real requests are being rejected with 429)
- Sentiment service health check returns "healthy" because the `SentimentDataService` singleton initialized, but its TTL cache is 3 hours stale and returning degraded data
- WebSocket health check returns "connected" because `BinanceStreamManager._running == True`, but the actual aiohttp connection to Binance streams is silently dead and has been for 20 minutes

The current `BinanceStreamManager` has a `get_stats()` method that returns `current_prices` — but a price that was received 20 minutes ago looks identical to one received 2 seconds ago. The status dashboard would show "connected" with a stale price timestamp that is easy to miss.

**Why it happens:**
Developers proxy internal flags (`_running`, `__initialized`) to health endpoints instead of measuring actual service behavior. A service can be "running" (no exception thrown) while producing wrong or stale data. This is especially insidious for singleton services with TTL caches — they always appear initialized.

**How to avoid:**
1. Health checks must measure **freshness**, not just connectivity. Add `last_price_received_at` timestamp to `BinanceStreamManager.get_stats()`. Health is `DEGRADED` if price is older than 2x the expected update interval (ticker stream: updates every ~1 second, so stale if older than 5 seconds).
2. Database health check must also check write capability: `INSERT INTO health_pings (ts) VALUES (now()); DELETE FROM health_pings;` — but this writes to production DB. Better: check `last_successful_sync_at` from an existing table that has recent write activity.
3. For Binance REST: health check must issue a real lightweight request (`GET /api/v3/time`) and measure response time. If 429, mark as `DEGRADED`. Do NOT skip the actual request.
4. For Sentiment service: health is `DEGRADED` if any pillar's `quality == "stale"` (already computed by `SentimentDataService`). Expose this as health signal.
5. Use three-tier health status: `HEALTHY` / `DEGRADED` / `DOWN`. `DEGRADED` means service is running but output quality is compromised. The status dashboard should show amber for DEGRADED, not green.

**Warning signs:**
- Status dashboard shows all-green during a Binance API outage
- Health endpoint response time is < 1ms (it is not checking anything real — just reading flags)
- Telegram bot never fires "service down" alerts even during known outages

**Phase to address:**
Phase 1 (Health Check System) — the definition of "healthy" must be agreed before building endpoints. Do not build endpoints first and define healthy later.

---

### Pitfall 2: Telegram Bot Alert Spam Causing Alert Fatigue

**What goes wrong:**
A service that is flapping (going down and recovering in rapid succession) fires a Telegram notification on every state change. At 1 notification per event, a WebSocket that disconnects and reconnects 20 times in a minute generates 40 messages. The user stops reading Telegram alerts entirely.

Specific failure scenario for this codebase: the `BinanceStreamManager` already has exponential backoff for reconnects (5s, 10s, 20s, 40s, 60s). If each reconnect attempt triggers a "service degraded" Telegram notification, the user receives 5+ messages in the first 2 minutes alone. If Binance has a 30-minute maintenance window, that is potentially 10-15 alerts about the same issue.

The existing `AlertBanner` system has no deduplication or cooldown. Alerts are created by `reconciliation_service.py` and stored in `AlertEventDB`. If Telegram is wired to forward all new alerts, it inherits this behavior.

**Why it happens:**
Developers wire Telegram to "on new alert in DB" without thinking about alert frequency. The alert system was designed for human-paced reconciliation events (1-2 per day), not for automated health monitoring (potentially 100s per day). Forwarding all reconciliation alerts directly to Telegram works in development (few events) but fails in production (continuous monitoring).

**How to avoid:**
1. **Alert state machine, not event stream**: Track service state as HEALTHY → DEGRADED → DOWN → RECOVERING → HEALTHY. Send Telegram only on state *transitions*, not on every health poll. One "WebSocket DOWN" message, then silence until state changes. One "WebSocket RECOVERED" when it recovers.
2. **Cooldown per alert type**: Do not re-send the same alert type for the same service within a cooldown window (15 minutes for DEGRADED, 1 hour for repeat DOWN). Store `last_notified_at` per `(service, alert_type)` in a new `telegram_notification_log` table or in memory as a singleton dict.
3. **Minimum severity filter**: Only send Telegram for CRITICAL and DOWN states. DEGRADED shows on the status dashboard but does not page the user. Let users configure their threshold.
4. **Respect Telegram's rate limit**: Telegram enforces 30 messages/second globally and per-chat limits enforced since February 2025 (per-chat granularity in layer 167). For a single-user bot, the practical limit is 1 message/second to the same chat. Implement an async queue with rate limiting: use `asyncio.sleep(1)` between sends if sending multiple queued messages.
5. **Test with flapping**: simulate a service cycling UP/DOWN at 1Hz for 60 seconds and verify Telegram receives exactly 2 messages (DOWN once, UP once after settling).

**Warning signs:**
- More than 3 Telegram messages in 5 minutes for the same service
- `telegram_notification_log` growing faster than 10 rows/hour in steady operation
- User mutes the Telegram bot (the ultimate alert fatigue indicator)

**Phase to address:**
Phase 2 (Telegram Bot) — alert state machine must be designed before any Telegram API calls are made. Connecting to Telegram first and adding deduplication later nearly always fails because "we'll add cooldown later" never happens.

---

### Pitfall 3: WebSocket Reconnect Causes Missed Fill Events or Duplicate Lot Creation

**What goes wrong:**
When the backend's `BinanceStreamManager` reconnects to the Binance User Data Stream, there is a gap between the last message received and the first message after reconnect. Any `executionReport` events (fills) that occurred during this gap are silently lost. The result: a sell order fills during the disconnect, no `fill_processed` event fires, and the corresponding Lot remains open in the database indefinitely.

The current implementation (`websocket_manager.py`, lines 270-315) simply reconnects and resumes listening — there is no mechanism to request missed events from Binance. Binance does not replay missed User Data Stream events.

The opposite risk also exists: if reconnect is too aggressive (retry without proper deduplication), the same `executionReport` can be processed twice if it arrives just before disconnect AND is re-sent after reconnect (this can happen near Binance maintenance boundaries). The existing fill handler (`websocket_fill_handler.py`) may not be idempotent — processing the same fill twice creates duplicate Lots.

**Why it happens:**
WebSocket reconnect is treated as "resume where you left off." But the Binance User Data Stream is not a durable queue — it does not store messages. A gap is permanent. Developers focus on reconnect latency (fast is good) without addressing the data gap itself.

**How to avoid:**
1. **Mandatory reconciliation after reconnect**: After every User Data Stream reconnect, immediately trigger `reconciliation_service.run_orders_reconciliation()`. This REST-based check compares Binance's actual order states to the local DB and catches any fills that occurred during the gap. The reconciliation service already exists — wire it to post-reconnect.
2. **Idempotent fill processing**: The fill handler (`websocket_fill_handler.py`) must be idempotent. Check if a fill with `tradeId` already exists in `ledger_events` before creating a new Lot. The trade ID is available in `executionReport` as field `t`. Add a unique constraint on `(user_id, binance_trade_id)` to `ledger_events` if not already present.
3. **Listen Key management on reconnect**: When reconnecting, create a NEW Listen Key rather than reusing the expired one. The current implementation calls `userDataStream.stop` for the old key and creates a new one — verify this happens on every reconnect path, not just on initial connect.
4. **Gap detection**: Log `(reconnect_at, last_message_at)` pair on every reconnect. If the gap exceeds 30 seconds, emit a DEGRADED health event: "User Data Stream gap detected — manual reconciliation recommended."
5. **Reconnect counter in health endpoint**: Expose `reconnect_count_last_hour` in the health endpoint. A count > 5 should trigger a DEGRADED health state even if currently connected.

**Warning signs:**
- Lots with `status=OPEN` that have corresponding fill events in Binance history but not in local DB
- Reconciliation consistently finds 1-2 missed fills after every restart
- `reconnect_count` increasing during Binance maintenance windows (expected) but also during normal operation (unexpected, indicates unstable connection)

**Phase to address:**
Phase 3 (WebSocket Recovery) — reconnect strategy must include the post-reconnect reconciliation trigger. Do NOT ship "reconnect working" without also verifying fill gap handling.

---

### Pitfall 4: Status Dashboard Adds Write Load to SQLite, Causing Lock Contention

**What goes wrong:**
The status dashboard polls `/api/health` every few seconds to show live service states. If the health check writes its results to the SQLite database (e.g., `INSERT INTO health_checks (service, status, checked_at)`), and the dashboard polls every 5 seconds, this creates 12 writes per minute from the health system alone. Combined with the existing write paths:
- `DryRunService` writes decisions every 15 minutes
- `reconciliation_service` writes run results on each trigger
- `sync_service` writes Lot records on fill import
- AlertEventDB writes on new alerts

SQLite's single-writer model means these writes contend for the same lock. A health check write that blocks for 100ms delays the DryRunService decision write. More importantly, if the health check itself becomes slow (e.g., checking Binance REST takes 2 seconds), the SQLite write transaction is open during that 2 seconds, blocking ALL other writes.

The current `database.py` uses `NullPool` (one connection per request) which is correct for SQLite, but still subjects all writes to global serialization.

**Why it happens:**
Persisting health check results to DB feels like good engineering (history, audit trail). But health checks are a monitoring concern, not a business data concern. Health check history belongs in a time-series store or a separate file, not in the trading app's SQLite database.

**How to avoid:**
1. **In-memory health state only**: Do not write health check results to SQLite. Keep health state in a singleton dict in memory: `{"db": {"status": "healthy", "checked_at": ..., "latency_ms": ...}}`. The status dashboard reads this via the health endpoint, which reads from memory.
2. **If persistence is required**: Use a dedicated SQLite file (`health.db`) with WAL mode, completely separate from `cashmgnt.db`. This eliminates any write contention with production data.
3. **Health endpoint must NOT hold DB transactions open during external service checks**: Check Binance REST FIRST, THEN open DB connection for the DB health check. Never check Binance inside a DB transaction.
4. **Rate-limit the health endpoint itself**: Cache the health result for 5 seconds. If the status dashboard polls every 3 seconds, return the cached result rather than re-running all checks. This reduces health check load to 12 checks/minute instead of 20.
5. **Status dashboard should use WebSocket push, not polling**: Push health state changes via the existing `BinanceStreamManager.broadcast_message()` mechanism when state transitions occur. The dashboard reacts to pushes instead of polling. This eliminates all continuous polling load.

**Warning signs:**
- "database is locked" errors appearing in logs that correlate with health check timing
- Health endpoint taking > 500ms to respond (indicating it is waiting for DB lock)
- Dry-Run evaluation loop logging "write delayed" messages during health check windows

**Phase to address:**
Phase 1 (Health Check System) — in-memory state design must be decided before any persistence code is written. Adding persistence later requires removing it, which is harder than never adding it.

---

### Pitfall 5: Binance Listen Key Expiry Causing Silent User Data Stream Death

**What goes wrong:**
Binance User Data Stream Listen Keys expire after 60 minutes if not refreshed via keepalive ping. The current implementation (`_keepalive_listen_key` in `websocket_manager.py`, line 323) sends a keepalive every 1800 seconds (30 minutes), which is correct for the intended frequency. However, there is no confirmation that the keepalive succeeded.

The `_ws_api_request` method (line 335) sends the keepalive via WebSocket API and reads the response. If the WebSocket API connection itself fails (the method has a bare `except Exception` that logs and returns `None`), the keepalive silently fails. After 60 minutes from the LAST successful keepalive, the Listen Key expires. The `_user_data_stream_loop` will not detect this — Binance simply stops sending events without sending an explicit expiration notification (documented behavior: "There is no listenKeyExpired event on userDataStream websocket for Spot").

The stream appears "connected" (no WebSocket disconnect) but receives no messages. The health endpoint reports `_running == True` and the `_user_stream_tasks` dict still contains the task entry. Everything looks healthy. All fills during this silent death window are lost.

**Why it happens:**
Binance's lack of an explicit expiration event means no reconnect is triggered. The stream is alive at the TCP level but dead at the application level. Without a message freshness check, there is no way to detect this from inside the stream loop.

**How to avoid:**
1. **Heartbeat detection**: Track `last_user_data_message_at` timestamp per user. If no message received in 90 seconds, the stream is likely stale (User Data Streams send at minimum a keepalive ping every ~20 seconds from Binance's side during quiet periods). Log a warning and force a reconnect.
2. **Keepalive failure handling**: If `_ws_api_request("userDataStream.ping")` returns `None` (failure), immediately schedule a reconnect — do NOT wait for the next keepalive interval. The current code only logs the error.
3. **Listen Key refresh strategy**: Create a NEW Listen Key every 45 minutes (not just ping the old one). This gives a 15-minute safety margin before expiry. The new Listen Key stream starts before the old one is closed, ensuring continuity.
4. **Expose stream message age in health**: `health_endpoint` should return `user_data_stream_last_message_age_seconds`. DEGRADED if > 90 seconds, DOWN if > 300 seconds.
5. **Post-listen-key-refresh reconciliation**: After creating a new Listen Key (full reconnect), trigger reconciliation to catch any events missed during the Listen Key rotation.

**Warning signs:**
- User Data Stream task is running but `last_user_data_message_at` shows > 120 seconds ago during active market hours
- Fill events not arriving during known active trading periods (open orders filling on Binance but not in local DB)
- Keepalive task logs "Fehler" but stream task log shows no reconnect

**Phase to address:**
Phase 3 (WebSocket Recovery) — Listen Key lifecycle management must be explicitly addressed. The current 30-minute ping is necessary but not sufficient.

---

### Pitfall 6: Integration With Existing AlertBanner Creates Two Competing Notification Systems

**What goes wrong:**
The existing system has a persistent `AlertBanner` component that polls `/api/alerts/{user_id}` every 30 seconds and shows in-app notifications for reconciliation alerts. The new Telegram bot adds a second notification channel. Without explicit coordination:

1. A reconciliation CRITICAL alert gets stored in `AlertEventDB`, shown in the frontend AlertBanner, AND sent to Telegram. The user acknowledges it in the frontend (clicks dismiss), but Telegram already sent the message — no way to retroactively "dismiss" a Telegram message.
2. The new health check system creates its own alert types (`SERVICE_DOWN`, `DEGRADED`). If these are written to `AlertEventDB`, they appear in the frontend AlertBanner. A status dashboard already shows this information. The user now sees: AlertBanner (top of every page) + Status Dashboard (Admin area) + Telegram (phone). Three channels for the same information.
3. The AlertBanner is designed for reconciliation alerts (1-2 per day, manual dismiss). Health alerts can fire much more frequently. If `SERVICE_DOWN` events accumulate in `AlertEventDB` faster than users dismiss them, the AlertBanner shows a growing unacknowledged count that never clears, training users to ignore it.

**Why it happens:**
The health monitoring milestone adds new alert types to an existing alert system designed for a different cadence. "Use the existing AlertEventDB" is the path of least resistance, but the existing system was not designed for automated, high-frequency monitoring events.

**How to avoid:**
1. **Separate alert categories**: Define two alert categories in `AlertEventDB.alert_type` or as a new `alert_category` column: `BUSINESS` (reconciliation, balance discrepancy — shown in AlertBanner) and `OPERATIONAL` (service health — shown only in Status Dashboard and Telegram, NOT in AlertBanner). The AlertBanner should only show `BUSINESS` alerts.
2. **Or**: Do not write health alerts to `AlertEventDB` at all. Keep health state in-memory (see Pitfall 4). The Status Dashboard reads from the health endpoint. Telegram reads from the same health state machine. AlertBanner remains reconciliation-only.
3. **Telegram forwards only CRITICAL + DOWN transitions, never DEGRADED**: This matches the existing AlertBanner severity model (warning/critical) and avoids notification duplication for routine degradations.
4. **Auto-expire operational alerts**: If health alerts ARE written to `AlertEventDB`, add `auto_expire_at` column (health alerts expire after 24 hours if not acknowledged, reconciliation alerts never expire). This prevents stale operational alerts accumulating.

**Warning signs:**
- `AlertEventDB` growing faster than 10 rows/hour during normal operation
- Users reporting "I see the same alert on my phone and in the banner at the same time"
- Unacknowledged alert count permanently > 5 (users stopped dismissing)

**Phase to address:**
Phase 2 (Telegram Bot) — must design the alert routing strategy BEFORE building the Telegram integration. Retrofitting alert categorization after Telegram is wired is painful because existing alerts have no category field.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Writing health results to `cashmgnt.db` (production SQLite) | Audit trail, no new infrastructure | Write contention under load, health checks block trading writes | Never — use in-memory or separate health.db |
| Polling `/api/health` from status dashboard every 2-3 seconds | Simple implementation | 20-30 DB connections per minute just for monitoring, SQLite lock contention | Never — use WebSocket push for state changes |
| Reusing `AlertEventDB` for health monitoring events | No new table/migration needed | Alert fatigue, AlertBanner polluted with operational noise | Only if alert category filtering is added first |
| Telegram bot sending all `alert_type` events without deduplication | Complete coverage | Alert storm during incidents, user disables bot | Never — always deduplicate with state machine |
| Hardcoded Telegram chat ID and bot token in `.env` | Works immediately | Cannot change chat without restart, no multi-user support | Acceptable for single-user deployment (this app) |
| Health check with `try: db.execute("SELECT 1") except: return DOWN` | Simple write | Does not detect WAL checkpoint stuck, disk full, or slow queries — only detects total connection failure | Only as a last-resort fallback, not as primary health signal |
| Using `time.sleep()` inside Telegram send retry logic | Simple to write | Blocks the thread/event loop if called from async context | Never in async context — use `asyncio.sleep()` with retry |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Telegram Bot API | Using `requests.get()` synchronously in an async FastAPI handler | Use `httpx.AsyncClient` or `aiohttp` for async Telegram sends; never block the event loop |
| Telegram Bot API | Sending one message per health check cycle (every 30s) | Send only on state transitions; maintain `last_state` per service in memory |
| Telegram Bot API (2025) | Ignoring `retry_after` in 429 responses | Since Feb 2025 (layer 167), per-chat `retry_after` values are enforced; parse and respect the header |
| Binance User Data Stream | Treating keepalive response `None` as "keepalive failed gracefully" | `None` return from `_ws_api_request` means failure; schedule reconnect immediately, do not wait for next interval |
| Binance User Data Stream | Assuming listen key expiry triggers a WebSocket disconnect | Binance does NOT send a disconnect on key expiry; the connection remains open but receives no messages |
| FastAPI health endpoint | Not setting `Cache-Control: no-cache` header | HTTP caches (nginx, CDN, browser) may serve stale health status, masking real outages |
| SQLite WAL mode for health DB | Enabling WAL on existing `cashmgnt.db` mid-production | WAL mode change requires `PRAGMA journal_mode=WAL` with no concurrent writers; safe to add to health.db from creation, risky to change on production DB |
| Status Dashboard WebSocket | Pushing health updates through the existing user_data channel | Health updates should use the existing `broadcast_message()` method with a distinct `type: "health_update"` message type; do NOT mix health events into order/fill event flow |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Health check runs all service checks synchronously (DB, Binance REST, stream manager) | Health endpoint takes 2-3 seconds to respond | Run checks concurrently with `asyncio.gather(check_db(), check_binance(), check_streams())`, total latency = max(individual), not sum | Immediately if Binance REST check takes 1+ second |
| Status dashboard polls every 2 seconds (frontend `useInterval`) | 30 HTTP requests/minute to `/api/health` when dashboard is open | Cache health result for 5-10 seconds in memory; or use WebSocket push instead of polling | Single user with dashboard open all day = 43,200 requests/day to health endpoint |
| Health check for `SentimentDataService` initializes the singleton on first call | First health check takes 30-60 seconds (full history initialization), endpoint appears to hang | `SentimentDataService` is already initialized in lifespan; health check must only READ from the existing singleton, never initialize | On first request before lifespan initialization completes (startup race condition) |
| Telegram message queue growing unbounded during Binance outage | Bot eventually exceeds Telegram's per-chat rate limit, messages dropped | Cap queue at 10 pending messages; drop oldest if queue full; log dropped messages | During any outage lasting > 10 minutes with high alert frequency |
| Reconnect counter incremented on every attempt including intentional restarts | Counter triggers DEGRADED health alert after every deployment | Distinguish intentional stops (`_running = False`) from failures; only increment failure counter | On every deployment restart if not handled |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Exposing Telegram bot token in health endpoint response or logs | Bot token allows anyone to send messages as your bot and read all messages sent to it | Never log the bot token; store in `.env` as `TELEGRAM_BOT_TOKEN`, never expose in API responses |
| Health endpoint accessible without API key authentication | Internal service state exposed (DB latency, service versions, stream subscriber counts) | Apply existing `require_api_key` dependency to `/api/health` endpoint, same as all other routes |
| Telegram bot sending alert details that include trade data | Leaks portfolio state (positions, P&L) to Telegram (which may be stored by Telegram indefinitely) | Alerts must contain only operational status, never financial data: "Service DEGRADED" not "Your BTC position is losing 5%" |
| Health endpoint response reveals internal architecture | `{"services": {"database_path": "/home/user/cashmgnt.db", "api_key": "..."}}` | Sanitize health response: show status and latency only, never paths, keys, or connection strings |
| Telegram chat ID stored without validation | Wrong chat ID silently discards all alerts (attacker who knows the bot token could enumerate valid chat IDs) | Validate chat ID by sending a test message on startup and confirming delivery; log if test fails |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Status dashboard shows all services as green on first load while health checks are still initializing | User trusts a stale/empty "all green" state | Show `CHECKING` state (grey spinner) until all checks complete; never default to green |
| Health dashboard shows raw latency numbers without context ("DB: 45ms") | User does not know if 45ms is good or bad | Show relative indicator: green < 50ms, amber 50-200ms, red > 200ms, with a one-line explanation on hover |
| Telegram sends alert at 3am for a DEGRADED state that self-recovers by 3:05am | User woken up unnecessarily; stops trusting alerts | Only notify for states that persist > N minutes (configurable, default 5 min); suppress if service recovers before N minutes elapsed |
| WebSocket reconnect indicator shows in frontend only during reconnect attempt, then disappears | User has no persistent record that there was a connectivity issue | Show "last disconnect: 3 minutes ago, reconnected successfully" in status dashboard; keep last-disconnect timestamp visible |
| Status dashboard only accessible in Admin area (requires navigation) | During an incident, user cannot quickly check service health from Trading or Analyse areas | Add a small service status indicator in the nav bar (dot: green/amber/red) that links to the full Status Dashboard in Admin |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Health endpoint returns HEALTHY:** Often missing — freshness check for price data. Verify: disconnect Binance WebSocket, wait 30 seconds, confirm health endpoint reports DEGRADED (not HEALTHY).
- [ ] **Telegram bot integrated:** Often missing — alert deduplication. Verify: trigger the same service outage twice within 10 minutes and confirm Telegram receives exactly ONE notification (not two).
- [ ] **WebSocket auto-reconnect working:** Often missing — post-reconnect reconciliation. Verify: force disconnect during an active sell order fill, reconnect, confirm the fill is reconciled and the Lot status is updated correctly.
- [ ] **Status dashboard displays all 8 services:** Often missing — DryRunService and AlphaScoreDataService health status. Verify: each service card shows last-check timestamp and latency, not just a status label.
- [ ] **Listen Key keepalive:** Often missing — keepalive failure handling. Verify: simulate keepalive failure (mock `_ws_api_request` to return None), confirm a reconnect is scheduled within 60 seconds.
- [ ] **Health check response cached:** Often missing — cache header set. Verify: `/api/health` response includes `Cache-Control: no-cache` header so proxies do not serve stale results.
- [ ] **Alert routing by category:** Often missing — operational alerts excluded from AlertBanner. Verify: trigger a SERVICE_DOWN health event, confirm it appears in Status Dashboard and Telegram but NOT in the frontend AlertBanner.
- [ ] **Telegram rate limit handling:** Often missing — `retry_after` respected on 429. Verify: mock Telegram API to return 429 with `retry_after: 5`, confirm bot waits 5 seconds and retries rather than dropping the message or crashing.
- [ ] **Reconnect counter reset on intentional stop:** Often missing — deployment restarts inflate failure counter. Verify: restart the backend, confirm reconnect failure counter resets to 0 and does not trigger DEGRADED alert.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Health endpoint returning false-positive healthy | LOW | 1. Add freshness check (timestamp delta) to health logic. 2. Verify with Binance API disconnect test. No data loss, no DB migration. |
| Telegram alert storm (100+ messages in 10 minutes) | LOW | 1. Temporarily revoke bot token (Telegram BotFather: `/revoke`). 2. Add deduplication to code. 3. Issue new token. 4. Resume. Messages already sent cannot be recalled. |
| Missed fills during WebSocket gap | MEDIUM | 1. Run manual reconciliation: `POST /api/reconciliation/{user_id}/fills`. 2. The reconciliation service will detect and import any fills missed during gap. 3. The Lot will be updated to correct status. If the Lot was OPEN during the gap and a sell fill was missed, reconciliation creates the sell allocation retroactively. |
| SQLite lock contention from health writes | LOW | 1. Remove health write code. 2. Switch to in-memory health state. 3. Restart backend. No data loss — health history was not production-critical data. |
| Listen Key expiry with silent stream death | MEDIUM | 1. Identify time window of silence from logs (`last_user_data_message_at`). 2. Run reconciliation to catch missed fills during the window. 3. Implement freshness check and automatic reconnect. |
| AlertBanner flooded with health events | LOW | 1. Filter `alert_type IN ('SERVICE_DOWN', 'DEGRADED')` out of AlertBanner query in frontend. 2. Add `alert_category` field to `AlertEventDB` in next migration. 3. Existing alerts remain but new filter prevents future flooding. |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Stale health checks returning false-positive healthy | Phase 1 (Health Check System) | Disconnect Binance WebSocket — health endpoint must report DEGRADED within 10 seconds |
| Telegram alert spam / alert fatigue | Phase 2 (Telegram Bot) | Flapping test: cycle service UP/DOWN 10x in 60 seconds — Telegram receives exactly 2 messages |
| Missed fills on WebSocket reconnect | Phase 3 (WebSocket Recovery) | Force disconnect during known fill event — verify fill captured via post-reconnect reconciliation |
| SQLite lock contention from health writes | Phase 1 (Health Check System) | Health endpoint uses in-memory state only — verify zero writes to cashmgnt.db during health polling |
| Listen Key silent expiry | Phase 3 (WebSocket Recovery) | Mock keepalive failure — verify reconnect triggered within 60 seconds and reconciliation runs |
| Two competing notification systems (AlertBanner vs Telegram) | Phase 2 (Telegram Bot) | Trigger reconciliation CRITICAL alert — verify appears in AlertBanner AND Telegram, NOT duplicated in both; health-only alerts appear in dashboard only |
| Status dashboard polling adds load | Phase 4 (Status Dashboard) | Open status dashboard for 1 hour — verify zero new writes to cashmgnt.db from health polling |
| Health check blocks on Binance REST during rate limit | Phase 1 (Health Check System) | Mock Binance to return 429 — health check completes in < 500ms (does not wait for retries) and reports DEGRADED |

---

## Sources

- Codebase analysis: `backend/app/services/websocket_manager.py` — `_keepalive_listen_key` (30-min interval), `get_stats()` (no freshness timestamp), `_user_data_stream_loop` (no message-age monitoring)
- Codebase analysis: `frontend/src/contexts/WebSocketContext.jsx` — `scheduleReconnect` exponential backoff, heartbeat at 30s, no post-reconnect reconciliation trigger
- Codebase analysis: `backend/app/api/routes/alerts.py` — AlertEventDB structure, unacknowledged_count, no alert category field
- Codebase analysis: `backend/app/db/database.py` — NullPool SQLite, single-writer constraint relevant to health write load
- Codebase analysis: `backend/app/main.py` — lifespan initialization order, DryRunService start, stream manager startup sequence
- Codebase analysis: `backend/app/services/sentiment_data_service.py` — TTL cache structure, quality badges (live/cached/stale/unavailable) — existing freshness model to reuse for health
- Binance Developer Community: [Avoiding/Detecting stale websocket connections](https://dev.binance.vision/t/avoiding-detecting-stale-websocket-user-data-stream-connections/4248) — Listen Key expiry behavior, no explicit expiration event (MEDIUM confidence — official Binance dev community)
- Binance Developer Community: [How to detect listenKey expiration](https://dev.binance.vision/t/how-to-detect-listenkey-expiration-on-userdatastream-websocket-for-spot/1370) — confirmed: no `listenKeyExpired` event for Spot stream (HIGH confidence — official forum)
- Telegram Bot API: Rate limits — 30 msg/sec global, per-chat enforcement since layer 167 (Feb 2025), `retry_after` per-chat granularity (HIGH confidence — verified against [Telegram flood control docs](https://grammy.dev/advanced/flood))
- AWS Builder's Library: [Implementing health checks](https://aws.amazon.com/builders-library/implementing-health-checks/) — three-tier status, freshness-based health definition (MEDIUM confidence — general engineering practice)
- SQLite documentation: [Write-Ahead Logging](https://sqlite.org/wal.html) — single-writer constraint, WAL mode read-write concurrency behavior (HIGH confidence — official SQLite docs)
- Microsoft Q&A: [Missing pubsub messages between client disconnect and reconnect](https://learn.microsoft.com/en-us/answers/questions/482237/missing-pubsub-messages-between-client-disconnect) — WebSocket message gap behavior (MEDIUM confidence — platform-specific but pattern applies generally)

---
*Pitfalls research for: v3.1 Hardening + Monitoring — Health-Check, Telegram Bot, WebSocket Recovery, Status Dashboard*
*Researched: 2026-02-28*
