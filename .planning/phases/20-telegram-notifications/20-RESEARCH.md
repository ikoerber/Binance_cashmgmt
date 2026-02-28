# Phase 20: Telegram Notifications - Research

**Researched:** 2026-02-28
**Domain:** Telegram Bot API integration for out-of-band health alerting with state-transition detection
**Confidence:** HIGH

## Summary

Phase 20 adds a `TelegramNotifier` service that sends Telegram messages when a monitored service transitions from healthy to DOWN. The service consumes health check results from Phase 19's `HealthCheckService`, detects state transitions in-memory, and calls the Telegram Bot API via `python-telegram-bot==22.6` (standalone `Bot` class, no polling/webhook). When `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is not configured, the notifier is a complete no-op -- no API calls attempted, no startup errors.

The key architectural decision is **alert routing separation**: health-related events route exclusively through Telegram and the Status Dashboard (Phase 22). They do NOT create `AlertEventDB` rows and do NOT appear in the frontend `AlertBanner`. The existing alert system (`AlertEventDB` + `AlertBanner`) remains exclusively for reconciliation/business alerts.

**Primary recommendation:** Build a `TelegramNotifier` singleton service with in-memory previous-state tracking. Integrate it into the health check cycle so that after each `_run_all_checks()` completes, the notifier compares current vs. previous state per service and fires a Telegram message on healthy-to-DOWN transitions only. Keep recovery notifications (TELE-04) and cooldown/deduplication (TELE-05) explicitly out of scope per REQUIREMENTS.md v3.2 deferral.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TELE-01 | TelegramNotifier Service sendet Nachricht bei Service-Ausfall (DOWN) | `python-telegram-bot==22.6` standalone `Bot` class with `async with bot: await bot.send_message(chat_id, text)`. State transition detection via in-memory `dict[str, str]` tracking previous service status. DOWN = status in `{"error", "unavailable"}` based on `compute_overall_status()` logic. |
| TELE-02 | Graceful No-Op wenn TELEGRAM_BOT_TOKEN/CHAT_ID nicht konfiguriert | Constructor checks `os.getenv("TELEGRAM_BOT_TOKEN")` and `os.getenv("TELEGRAM_CHAT_ID")`. If either is empty/None, set `self._enabled = False`. All public methods return immediately when disabled. No Bot instance created, no httpx connections opened. |
| TELE-03 | Alert-Routing trennt Health-Events von AlertBanner (keine AlertEventDB-Eintraege fuer Health) | Health state transitions are detected within the `HealthCheckService` / `TelegramNotifier` loop. They never call `db.add(AlertEventDB(...))`. The `AlertBanner.jsx` only queries `AlertEventDB` rows -- since no health rows exist there, health alerts never appear in the banner. Separation is structural, not filter-based. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-telegram-bot | 22.6 | Async Telegram Bot API wrapper for sending notifications | Official Python wrapper. v22.6 (released 2026-01-24) is fully async (asyncio-native). Standalone `Bot` class requires no Application/polling/webhook infrastructure. Only dependency: httpx>=0.27,<0.29 -- project already has httpx==0.28.1 (within range). Zero new transitive dependencies. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.28.1 (existing) | HTTP transport for python-telegram-bot | Already installed. python-telegram-bot uses it internally for `Bot.send_message()`. No action needed. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-telegram-bot 22.6 | Direct httpx POST to `api.telegram.org/bot{token}/sendMessage` | Saves ~2MB disk. Loses automatic retry on 429, proper error types, and message formatting helpers. Adds ~50 lines of manual error handling. Not recommended -- httpx dependency already shared, net code reduction with library. |
| python-telegram-bot 22.6 | aiogram 3.x | Full framework with middleware, FSM, routers. Massive overkill for one-way push notifications. Only justified if receiving commands from Telegram (not in scope). |
| python-telegram-bot 22.6 | pyTelegramBotAPI (telebot) | Sync-first library. Async mode (AsyncTeleBot) less maintained. python-telegram-bot has 100% Telegram Bot API coverage and active maintenance. |

**Installation:**
```bash
cd backend
pip install python-telegram-bot==22.6
# Add to requirements.txt under new section:
# Telegram Notifications
# python-telegram-bot==22.6
```

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── services/
│   ├── health_check_service.py       # EXISTING — add notification hook after _run_all_checks()
│   └── telegram_notifier.py          # NEW — TelegramNotifier singleton
├── api/routes/
│   └── health.py                     # EXISTING — unchanged
└── main.py                           # MODIFIED — start/stop TelegramNotifier in lifespan
```

### Pattern 1: Singleton TelegramNotifier with Graceful No-Op
**What:** A singleton service class that wraps `telegram.Bot` and tracks per-service previous state. When disabled (no credentials), all methods are no-ops.
**When to use:** Always -- this is the core pattern for TELE-01 and TELE-02.
**Example:**
```python
# Source: python-telegram-bot v22.6 docs + project singleton pattern
import logging
import os
import threading
from typing import Optional

from telegram import Bot

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """
    Sends Telegram messages on health state transitions.

    Graceful no-op when TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set.
    In-memory previous-state tracking for transition detection.
    """

    def __init__(self):
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._enabled = bool(self._token and self._chat_id)
        self._bot: Optional[Bot] = None
        self._previous_states: dict[str, str] = {}  # service_name -> last known status

        if self._enabled:
            self._bot = Bot(token=self._token)
            logger.info("TelegramNotifier enabled (chat_id=%s)", self._chat_id)
        else:
            logger.info("TelegramNotifier disabled (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self):
        """Initialize the Bot (opens httpx connection pool)."""
        if self._bot:
            await self._bot.initialize()

    async def stop(self):
        """Shutdown the Bot (closes httpx connections)."""
        if self._bot:
            await self._bot.shutdown()

    async def send_message(self, text: str) -> bool:
        """Send a plain text message. Returns True on success, False on failure."""
        if not self._enabled or not self._bot:
            return False
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
            return True
        except Exception:
            logger.exception("Failed to send Telegram message")
            return False

    async def check_transitions(self, health_result: dict) -> None:
        """
        Compare current health with previous state. Send notification
        on transition to DOWN (error/unavailable).
        """
        if not self._enabled:
            return

        services = health_result.get("services", {})
        down_statuses = {"error", "unavailable"}

        for name, svc_data in services.items():
            current = svc_data.get("status", "ok")
            previous = self._previous_states.get(name)

            # Transition: was healthy (not down) -> now down
            if current in down_statuses and (previous is None or previous not in down_statuses):
                detail = svc_data.get("detail", "")
                msg = f"SERVICE DOWN: {name}\nStatus: {current}"
                if detail:
                    msg += f"\nDetail: {detail}"
                await self.send_message(msg)

            self._previous_states[name] = current


# Singleton
_notifier_instance: Optional[TelegramNotifier] = None
_notifier_lock = threading.Lock()

def get_telegram_notifier() -> TelegramNotifier:
    global _notifier_instance
    if _notifier_instance is None:
        with _notifier_lock:
            if _notifier_instance is None:
                _notifier_instance = TelegramNotifier()
    return _notifier_instance
```

### Pattern 2: Health Check Integration (Hook After Checks)
**What:** After `HealthCheckService._run_all_checks()` completes, call `TelegramNotifier.check_transitions(result)` to evaluate state changes and fire notifications.
**When to use:** Every health check cycle (every 5 seconds when cache expires, triggered by frontend polling).
**Example:**
```python
# In HealthCheckService._run_all_checks() or get_health()
async def _run_all_checks(self) -> dict:
    # ... existing parallel checks ...
    result = { "overall_status": overall, "services": ..., "checked_at": ... }

    # Notify on state transitions
    notifier = get_telegram_notifier()
    await notifier.check_transitions(result)

    return result
```

### Pattern 3: Lifespan Integration
**What:** Start/stop the TelegramNotifier in FastAPI's lifespan context manager, following the existing pattern for DryRunService and BinanceStreamManager.
**When to use:** App startup/shutdown.
**Example:**
```python
# In main.py lifespan()
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup ...

    # Telegram Notifier
    from app.services.telegram_notifier import get_telegram_notifier
    notifier = get_telegram_notifier()
    await notifier.start()

    yield

    # ... existing shutdown ...
    await notifier.stop()
```

### Pattern 4: .env Configuration
**What:** Two env vars control Telegram notifications. Both must be set for notifications to be active.
**When to use:** Deployment configuration.
**Example:**
```bash
# backend/.env (additions)
TELEGRAM_BOT_TOKEN=           # From @BotFather — empty = notifications disabled
TELEGRAM_CHAT_ID=             # Target chat ID (user or group) — empty = notifications disabled
```

### Anti-Patterns to Avoid
- **Creating AlertEventDB rows for health events:** This violates TELE-03. Health alerts route through Telegram only. The AlertBanner is for reconciliation/business alerts exclusively.
- **Using python-telegram-bot Application class:** The Application class starts a polling loop or webhook server. We only send outbound messages -- use standalone `Bot` class directly.
- **Sending on every health poll:** Without transition detection, the notifier would spam on sustained outages. Only send on state *transitions* (healthy -> DOWN).
- **Blocking health check on Telegram send failure:** If the Telegram API is slow or down, the health check response should not be delayed. The `send_message()` call should be fire-and-forget or have a short timeout. Since the health check result is cached for 5 seconds anyway, a brief delay is acceptable, but Telegram failures must never prevent health response delivery.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Telegram API HTTP calls | Custom httpx POST with retry logic, error parsing, rate limit handling | `python-telegram-bot==22.6` `Bot.send_message()` | Library handles 429 retry, connection pooling, proper error types. Manual implementation requires ~50 lines of boilerplate for what the library does in 1 line. httpx already installed -- zero new dependencies. |
| Health state transition detection | Complex event-driven pub/sub system | In-memory `dict[str, str]` comparing previous vs. current status | State machine is 15 lines of code. Previous state dict is reset on app restart (acceptable -- first check after restart establishes baseline, no spurious alerts). |
| Telegram message formatting | Manual MarkdownV2 escaping with special char handling | Plain text messages (no formatting) | TELE-06 (Markdown formatting) is explicitly deferred to v3.2. Plain text is sufficient for Phase 20. Avoids MarkdownV2 escaping pitfalls (11 special characters must be escaped). |

**Key insight:** The entire Phase 20 feature is ~80 lines of service code + ~10 lines of integration. The complexity is in getting the transition detection right and ensuring the no-op path is truly silent, not in the Telegram API call itself.

## Common Pitfalls

### Pitfall 1: Telegram Alert Spam on Sustained Outages
**What goes wrong:** Without transition detection, a service that stays in "error" status fires a Telegram message on every health check cycle (every 5 seconds when polled). A 30-minute Binance outage generates 360 messages.
**Why it happens:** Developers check "is service down?" instead of "did service just become down?"
**How to avoid:** Track previous state per service. Only send on transition from non-down to down. The `check_transitions()` method above implements this pattern.
**Warning signs:** More than 1 Telegram message per service per outage incident.

### Pitfall 2: Startup Crash When Token Is Invalid
**What goes wrong:** `Bot(token="invalid")` succeeds at construction but `bot.initialize()` may fail if the token is malformed. If this crashes the lifespan, the entire app fails to start.
**Why it happens:** The Bot constructor does not validate the token with Telegram's API -- validation happens on first API call.
**How to avoid:** Wrap `await notifier.start()` in try/except. On failure, log a warning and set `_enabled = False`. The app continues without Telegram notifications. Never let Telegram failures prevent app startup.
**Warning signs:** App crashes on startup when TELEGRAM_BOT_TOKEN is set to a typo.

### Pitfall 3: Spurious Alerts on App Restart
**What goes wrong:** After app restart, `_previous_states` is empty. The first health check finds a service in "error" state. Since there is no previous state, the transition detection interprets this as "was healthy, now down" and fires a Telegram message. If the service was already down before the restart, this is a false alert.
**Why it happens:** In-memory state is lost on restart. There is no persistent state to compare against.
**How to avoid:** On first health check after startup (when `_previous_states` is empty), populate `_previous_states` from the current check WITHOUT sending notifications. This establishes a baseline. Only subsequent checks trigger notifications. Implement by checking `if previous is None: store and skip`.
**Warning signs:** A Telegram message fires every time the app restarts, even when all services are healthy.

### Pitfall 4: Health Events Leaking into AlertEventDB
**What goes wrong:** A well-meaning developer adds health-down events to `AlertEventDB` "for consistency" or "so the AlertBanner shows them too." This violates TELE-03 and creates a dual-notification problem (Telegram + AlertBanner for the same event).
**Why it happens:** The existing alert pipeline (`reconciliation_service -> AlertEventDB -> AlertBanner`) is the established pattern. It feels natural to reuse it.
**How to avoid:** Structural separation: the `TelegramNotifier` is called from `HealthCheckService`, not from `reconciliation_service`. Health state transitions never touch `AlertEventDB`. Document this boundary clearly. The existing `reconciliation_service.py` code that creates `AlertEventDB` rows is for business alerts only and is not modified.
**Warning signs:** `AlertEventDB` table contains rows with `alert_type` values like "SERVICE_DOWN" or "HEALTH_CHECK".

### Pitfall 5: Bot.initialize()/shutdown() Not Called
**What goes wrong:** Creating a `Bot` instance and calling `send_message()` without `initialize()` first. In python-telegram-bot v22.x, the Bot must be initialized to set up the httpx connection pool. Forgetting `shutdown()` leaves open connections.
**Why it happens:** The v20+ async lifecycle is different from older synchronous versions. Developers copy pre-v20 examples.
**How to avoid:** Use the lifespan pattern: `start()` calls `bot.initialize()`, `stop()` calls `bot.shutdown()`. Both are wired into FastAPI's lifespan context manager. Alternatively, use `async with bot:` context manager for one-shot sends, but the lifespan pattern is better for a long-running service.
**Warning signs:** `RuntimeWarning: coroutine 'Bot.initialize' was never awaited` or httpx connection pool warnings on shutdown.

## Code Examples

Verified patterns from official sources:

### Standalone Bot Send (python-telegram-bot v22.6)
```python
# Source: https://docs.python-telegram-bot.org/telegram.bot.html
from telegram import Bot

bot = Bot(token="YOUR_TOKEN")

# Option A: Context manager (auto initialize/shutdown)
async with bot:
    await bot.send_message(chat_id="CHAT_ID", text="Service DOWN: websocket")

# Option B: Manual lifecycle (preferred for long-running services)
await bot.initialize()
try:
    await bot.send_message(chat_id="CHAT_ID", text="Service DOWN: websocket")
finally:
    await bot.shutdown()
```

### Graceful No-Op Pattern
```python
# Pattern used across this project (e.g., SentimentDataService graceful degradation)
class TelegramNotifier:
    def __init__(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._enabled = bool(token and chat_id)
        # No Bot created if disabled -- zero resource usage

    async def send_message(self, text: str) -> bool:
        if not self._enabled:
            return False  # Silent no-op
        # ... actual send logic ...
```

### State Transition Detection
```python
# DOWN statuses match the health check service's "critical" tier
DOWN_STATUSES = {"error", "unavailable"}

def _is_down(status: str) -> bool:
    return status in DOWN_STATUSES

async def check_transitions(self, health_result: dict) -> None:
    for name, svc_data in health_result.get("services", {}).items():
        current = svc_data.get("status", "ok")
        previous = self._previous_states.get(name)

        if previous is None:
            # First check after startup -- establish baseline, don't alert
            self._previous_states[name] = current
            continue

        was_down = _is_down(previous)
        is_down = _is_down(current)

        if is_down and not was_down:
            # Transition: healthy -> DOWN
            await self.send_message(f"SERVICE DOWN: {name}\nStatus: {current}")

        self._previous_states[name] = current
```

### .env Configuration
```bash
# backend/.env.example (additions)
# Telegram Notifications (both required, leave empty to disable)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-telegram-bot v13 (sync) | python-telegram-bot v20+ (fully async, httpx-based) | v20.0 (2023) | Must use `await bot.send_message()`, requires `initialize()`/`shutdown()` lifecycle |
| `Bot()` auto-ready | `Bot()` requires `initialize()` before first call | v20.0 (2023) | Forgetting initialize causes RuntimeError. Use lifespan pattern. |
| `requests` as HTTP backend | `httpx` as sole HTTP backend | v20.0 (2023) | httpx is the only transport. Aligns with project's existing httpx dependency. |

**Deprecated/outdated:**
- `telegram.Bot.sendMessage()` (camelCase): Deprecated since v20. Use `send_message()` (snake_case).
- Synchronous `bot.send_message()`: Not available in v20+. All methods are async.
- `telegram.ext.Updater`: Replaced by `telegram.ext.Application` in v20+. Not relevant for this phase (we don't use Application at all).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | None (uses default pytest discovery) |
| Quick run command | `cd backend && python -m pytest tests/test_telegram_notifier.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TELE-01 | TelegramNotifier sends message on service DOWN transition | unit | `pytest tests/test_telegram_notifier.py::test_sends_on_healthy_to_down_transition -x` | Wave 0 |
| TELE-01 | No message sent when service stays DOWN (sustained outage) | unit | `pytest tests/test_telegram_notifier.py::test_no_message_on_sustained_down -x` | Wave 0 |
| TELE-01 | No message sent when service is healthy | unit | `pytest tests/test_telegram_notifier.py::test_no_message_when_healthy -x` | Wave 0 |
| TELE-02 | Notifier is no-op when token not configured | unit | `pytest tests/test_telegram_notifier.py::test_noop_without_token -x` | Wave 0 |
| TELE-02 | Notifier is no-op when chat_id not configured | unit | `pytest tests/test_telegram_notifier.py::test_noop_without_chat_id -x` | Wave 0 |
| TELE-02 | App starts without error when Telegram not configured | unit | `pytest tests/test_telegram_notifier.py::test_start_stop_disabled -x` | Wave 0 |
| TELE-03 | check_transitions never creates AlertEventDB rows | unit | `pytest tests/test_telegram_notifier.py::test_no_alert_event_db_creation -x` | Wave 0 |
| TELE-03 | Health route response has no alert_event_id field | unit | `pytest tests/test_telegram_notifier.py::test_health_response_no_alert_ids -x` | Wave 0 |
| TELE-01 | First check after startup establishes baseline (no alert) | unit | `pytest tests/test_telegram_notifier.py::test_first_check_no_alert -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_telegram_notifier.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_telegram_notifier.py` -- covers TELE-01, TELE-02, TELE-03 (all 9 test cases)

*(No framework install needed -- pytest and pytest-asyncio already present)*

## Open Questions

1. **DOWN status definition: "error" + "unavailable" or also "stopped"?**
   - What we know: `compute_overall_status()` treats `error` and `unavailable` as "critical" (the worst tier). `stopped`, `stale`, and `degraded` are the "degraded" tier.
   - What's unclear: The phase description says "service transitions from healthy to DOWN" but does not define exactly which statuses constitute "DOWN." The success criteria says "a Telegram message arrives within one health-check cycle naming the failed service."
   - Recommendation: Define DOWN as `{"error", "unavailable"}` (the critical tier). `stopped`/`stale`/`degraded` services are not "down" -- they appear on the Status Dashboard (Phase 22) but do not trigger Telegram. This matches the 3-tier model from Phase 19.

2. **Telegram send failure handling**
   - What we know: Telegram API can be temporarily unreachable. `bot.send_message()` raises `telegram.error.TelegramError` on failure.
   - What's unclear: Should failed sends be retried? Queued? Silently dropped?
   - Recommendation: Log the failure via `logger.exception()` and move on. Do not retry -- the next health check cycle will detect the same transition if the previous state was not updated. Only update `_previous_states[name]` after a successful health check (always), not conditional on Telegram send success. This way, a failed Telegram send does not cause infinite retries on the next cycle -- the transition is "consumed" regardless of send success.

## Sources

### Primary (HIGH confidence)
- PyPI python-telegram-bot 22.6: https://pypi.org/project/python-telegram-bot/ -- version 22.6 confirmed (2026-01-24), httpx>=0.27,<0.29 confirmed, Python >=3.10 confirmed
- python-telegram-bot official docs v22.6 Bot class: https://docs.python-telegram-bot.org/telegram.bot.html -- `Bot.send_message()`, `Bot.initialize()`, `Bot.shutdown()`, async context manager pattern confirmed
- Codebase analysis: `backend/app/services/health_check_service.py` -- `HealthCheckService` singleton, `_run_all_checks()`, `compute_overall_status()`, `ServiceStatus` dataclass, 5s TTL cache
- Codebase analysis: `backend/app/api/routes/alerts.py` + `backend/app/db/models.py` -- `AlertEventDB` is exclusively for reconciliation alerts, `alert_type` values are "BALANCE_DISCREPANCY", "ORDER_DISCREPANCY", "SYNC_ERROR", "BALANCE_CHECK_ERROR"
- Codebase analysis: `backend/app/main.py` -- lifespan pattern for service start/stop, singleton getter pattern
- Codebase analysis: `backend/requirements.txt` -- httpx==0.28.1 confirmed within python-telegram-bot range
- Codebase analysis: `backend/tests/test_health_check.py` -- test patterns for mocking singletons and async testing

### Secondary (MEDIUM confidence)
- Telegram Bot API rate limits: https://core.telegram.org/bots/faq -- 1 msg/second per chat (burst allowed), 30 msg/second global per bot token. Phase 20 sends at most 8 messages per health check cycle (one per service), well within limits.
- Project research files: `.planning/research/STACK.md`, `.planning/research/PITFALLS.md`, `.planning/research/FEATURES.md` -- prior team research on Telegram integration patterns, alert spam prevention, architecture decisions

### Tertiary (LOW confidence)
- None. All findings verified against primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - python-telegram-bot==22.6 verified on PyPI, httpx compatibility confirmed against requirements.txt, Bot standalone usage confirmed in official docs
- Architecture: HIGH - Follows existing project singleton pattern (6+ services use same pattern), lifespan integration matches existing DryRunService/BinanceStreamManager pattern, transition detection is a well-understood state machine
- Pitfalls: HIGH - Alert spam prevention via transition detection verified against project pitfall research, startup crash handling verified against python-telegram-bot lifecycle docs, AlertEventDB separation verified against codebase analysis of reconciliation_service.py

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable -- python-telegram-bot 22.6 is recent, project architecture is established)
