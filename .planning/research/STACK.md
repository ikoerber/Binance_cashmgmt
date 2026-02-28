# Stack Research: v3.1 Hardening + Monitoring

**Domain:** Health-Check System, Status Dashboard, Telegram Notifications, WebSocket Recovery for crypto trading app
**Researched:** 2026-02-28
**Confidence:** HIGH (Telegram via python-telegram-bot, WebSocket recovery patterns), HIGH (Health-Check: no library needed), HIGH (Status Dashboard: no new frontend deps)

## Existing Stack (DO NOT add -- already present)

These are validated and working. Listed to prevent redundant additions:

| Technology | Version | Already Used For |
|------------|---------|-----------------|
| Python 3.13 | 3.13.x | Backend runtime |
| FastAPI | 0.128.7 | REST API, lifespan hooks |
| SQLAlchemy 2 | 2.0.46 | ORM, session management |
| aiohttp | 3.13.3 | Binance WebSocket streams (BinanceStreamManager) |
| httpx | 0.28.1 | Test client (httpx in requirements.txt) |
| requests | 2.32.5 | REST calls (sentiment, macro data) |
| React 19 | 19.2.0 | Frontend |
| TanStack Query | 5.90.20 | Data fetching, polling, cache invalidation |
| Recharts | 3.7.0 | Bar/line charts |
| plain CSS | — | All styling, CSS Custom Properties for dark mode |
| AlertEventDB | via SQLAlchemy | Persistent alert storage, existing alert pipeline |
| BinanceStreamManager | custom service | WebSocket hub, already has exponential backoff (5→60s) |
| WebSocketContext | React context | Frontend WS client, already has reconnect logic |

## Recommended Stack Additions

### Backend: Telegram Notifications

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| python-telegram-bot | 22.6 | Send alert notifications to Telegram chat | Official Python Telegram Bot API wrapper. v22.6 is fully async (asyncio-native), released January 24, 2026. Used as standalone `Bot` (no Application/polling/webhook needed -- we only push notifications). Integrates cleanly with FastAPI's asyncio event loop via `async with bot: await bot.send_message(...)`. Only required dependency is httpx >=0.27,<0.29 -- project already has httpx==0.28.1 which is within this range. Zero dependency conflict. |

**Why python-telegram-bot over direct httpx calls to Telegram REST API:**
python-telegram-bot provides automatic retry on rate limits (429), proper error handling, and correct message formatting (Markdown v2 escaping). Direct httpx calls require re-implementing these. The library's standalone `Bot` class (no Application needed) adds ~2MB and removes ~50 lines of error-handling boilerplate. The httpx dependency is already installed -- no new transitive dependencies introduced.

**Why NOT aiogram:** aiogram is excellent but heavier (full framework with middleware, routers, FSM). We only send outbound notifications -- we never receive messages. python-telegram-bot's standalone `Bot` is the minimal API for this use case.

**Why NOT pyTelegramBotAPI (telebot):** pyTelegramBotAPI is sync by default. The async version (AsyncTeleBot) is available but the library is less maintained than python-telegram-bot. python-telegram-bot has 100% Telegram Bot API 9.3 coverage and active maintenance (22.6 released February 2026).

### Backend: Health-Check Endpoints

**No new library needed.** FastAPI + existing SQLAlchemy is sufficient.

The health check system is 8 custom GET endpoints (one per service) returning structured JSON. No framework abstraction adds value here -- the check logic is business-specific (can we execute `SELECT 1` on SQLite? Is the WebSocket stream `_running`? Is the dry-run loop active?).

| Service | Check Method | Implementation |
|---------|-------------|----------------|
| Backend | Always healthy (if endpoint responds) | `GET /api/health` → `{"status": "healthy"}` |
| Database | `db.execute(text("SELECT 1"))` in try/except | SQLAlchemy session from existing `get_db()` |
| WebSocket | `stream_manager.get_stats()["running"]` | Existing `get_stats()` method on BinanceStreamManager |
| Dry-Run Loop | `dry_run_service.is_running()` or loop timestamp | Expose last-tick timestamp from existing DryRunService |
| Alpha Score | Last computation timestamp from alpha_score_service | Freshness check: now - last_computed < threshold |
| Sentiment | Last fetch timestamp from SentimentDataService singleton | Existing `_last_fetch` pattern already in service |
| Macro | Last fetch timestamp from MacroDataService | Same pattern as Sentiment |
| Binance REST | `binance_client.ping()` or `get_server_time()` with timeout | python-binance client, wrap in asyncio.wait_for() timeout |

**Pattern (pure FastAPI, no library):**

```python
# api/routes/health.py
from fastapi import APIRouter
from sqlalchemy.orm import Session
from sqlalchemy import text
import asyncio

router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("")
async def health_overall(db: Session = Depends(get_db)):
    """Aggregate health: all 8 services, parallel checks."""
    checks = await asyncio.gather(
        _check_db(db),
        _check_websocket(),
        _check_dry_run(),
        _check_alpha_score(),
        _check_sentiment(),
        _check_macro(),
        _check_binance_rest(),
        return_exceptions=True
    )
    # Build response from checks
    ...

@router.get("/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"service": "db", "status": "healthy"}
```

**Why not fastapi-health or fastapi-healthchecks libraries:**
Both libraries are wrappers that add no value for custom service state checks. `fastapi-health` uses a condition list pattern that doesn't map cleanly to our 8 heterogeneous services. The pure implementation is 40 lines and fully transparent.

### Frontend: Status Dashboard

**No new library needed.** Existing TanStack Query + Recharts + plain CSS handles the Status Dashboard completely.

| UI Element | Implementation |
|-----------|---------------|
| Service status cards (8 cards) | TanStack Query polling `/api/health` every 30s, plain CSS status indicator (green/yellow/red dot) |
| Last-active timestamps | `formatDate` / `formatTime` from existing `utils/formatters.js` |
| Freshness indicators | CSS custom properties, same pattern as quality badges in CombinedScore |
| Auto-refresh badge | Existing pattern from AlertBanner (30s polling) |

**Why no react-health-dashboard or similar:** These are unmaintained packages (last update 2-3 years ago). The Status Dashboard is a simple read-only display of 8 service states -- a TanStack Query fetch + 8 CSS cards takes 60 lines of JSX.

### Frontend: WebSocket Recovery Enhancement

**No new library needed.** The existing `WebSocketContext.jsx` already has exponential backoff (1s → 2s → 4s → ... → 30s max) and reconnect scheduling. The v3.1 enhancement adds:

1. **Jitter** to prevent thundering-herd: `delay * (0.8 + Math.random() * 0.4)` -- adds ±20% randomization
2. **Max-attempt cap** before giving up (surface error to user via status indicator)
3. **Channel re-subscription on reconnect**: After reconnect, re-send `{ action: 'subscribe', channel: 'user_data' }` -- this is already done in `ws.onopen` but needs to be explicit in the reconnect path
4. **Connection state exposed** in the Status Dashboard: `connected`, `reconnectAttempts`, `lastConnectedAt`

The reconnect logic is already in `WebSocketContext.jsx:191-201`. The enhancement is surgical -- ~15 lines of changes to an existing file.

**Why not reconnecting-websocket npm package:** The package adds 4KB for a feature the existing codebase already implements. The existing implementation is simpler and tailored to the project's auth pattern (first-message auth, channel subscription).

## Integration Points

### Telegram Notification Integration with Existing Alert System

The existing `AlertEventDB` pipeline already fires `create_alert()` in `reconciliation_service.py`. The Telegram notification layer sits **above** the existing alert pipeline:

```
reconciliation_service.py → create_alert() → AlertEventDB (existing)
                                            ↓
                                     TelegramNotifier (NEW)
                                     sends Telegram message if configured
```

**Not a webhook listener -- push-only.** The `TelegramNotifier` is a thin service class with one method: `async def notify(message: str, severity: str)`. It is called after `create_alert()` for `critical` and `warning` severity events. Configuration via `.env`: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

**Graceful degradation:** If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is not set, `TelegramNotifier.notify()` is a no-op. No exceptions propagate. Existing alert flow is unaffected.

### Health-Check Integration with BinanceStreamManager

`BinanceStreamManager.get_stats()` already returns `{"running": bool, "price_subscribers": int, ...}`. The health check endpoint calls this directly -- no new code in BinanceStreamManager.

### Telegram Config via Existing .env Pattern

```bash
# backend/.env (additions)
TELEGRAM_BOT_TOKEN=           # From @BotFather -- empty = notifications disabled
TELEGRAM_CHAT_ID=             # Target chat ID (user or group) -- empty = notifications disabled
TELEGRAM_ALERT_MIN_SEVERITY=warning  # Minimum severity to notify (warning/critical)
```

## Installation

```bash
# Backend: One new dependency
cd backend
pip install python-telegram-bot==22.6

# Add to requirements.txt:
# Telegram Notifications
python-telegram-bot==22.6

# Frontend: No new dependencies
# WebSocketContext.jsx enhancements are code changes, not new packages
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| python-telegram-bot 22.6 (standalone Bot) | Direct httpx calls to Telegram REST API | Use direct httpx if you want zero additional dependencies and can accept manual retry/error handling (~50 extra lines). python-telegram-bot is cleaner given httpx is already installed. |
| python-telegram-bot 22.6 | aiogram 3.x | Use aiogram if you need to receive messages (commands, callbacks, FSM). For push-only notifications, aiogram is over-engineered. |
| python-telegram-bot 22.6 | Slack/Discord webhooks | Use if team is on Slack/Discord. Telegram is the stated requirement. |
| Pure FastAPI health endpoints | fastapi-health library | Use fastapi-health if you want Kubernetes-style `/live` + `/ready` probes with a declarative condition list. Not needed for this single-machine deployment. |
| Existing WebSocketContext.jsx + jitter | reconnecting-websocket npm | Use npm package if you want a drop-in WebSocket wrapper. Our implementation is simpler and already auth-aware. |
| TanStack Query polling (30s) | Server-Sent Events for health push | Use SSE if status must update in <1s. 30s polling is sufficient for a monitoring dashboard that humans check periodically. |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| fastapi-health / fastapi-healthchecks | Adds abstraction with no benefit for 8 custom service checks. The library's condition-list pattern doesn't map to "is this singleton running?" questions. | Pure FastAPI endpoints (40 lines) |
| aiogram | Full framework (middleware, FSM, router) for a feature that needs one method: `send_message()`. 10x the complexity needed. | python-telegram-bot 22.6 standalone Bot |
| Prometheus + Grafana | Operational monitoring stack designed for multi-service production environments. This is a single-user single-machine app -- full Prometheus setup is massive overkill. | Custom health endpoints + Status Dashboard |
| Sentry | Error tracking service. Useful in team production environments. The existing `logger.exception()` pattern + structured JSON logs already captures all errors locally. | Existing structured logging |
| websockets (npm/PyPI) | Redundant. aiohttp already provides WebSocket client (backend). Browser native WebSocket API is used in frontend. Two WebSocket implementations create conflicts. | aiohttp (backend), native WebSocket API (frontend) |
| Redis pub/sub for health state | Adds Redis dependency requirement (Redis server must be running). Health state is read directly from in-memory service singletons -- no pub/sub needed. | Direct singleton state inspection |
| react-query-devtools | Dev tool, not needed for this milestone. | N/A |

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| python-telegram-bot==22.6 | httpx==0.28.1 | python-telegram-bot 22.6 requires `httpx>=0.27,<0.29`. Project has `httpx==0.28.1` -- within range. Zero conflict. Verified via PyPI requirements. |
| python-telegram-bot==22.6 | aiohttp==3.13.3 | No interaction. python-telegram-bot uses httpx internally; aiohttp is used independently for Binance WebSocket streams. |
| python-telegram-bot==22.6 | FastAPI 0.128.7 | No interaction. `Bot.send_message()` is called from service layer, not from FastAPI route handlers directly (though it can be). |
| python-telegram-bot==22.6 | Python 3.13 | Requires Python >=3.10. Python 3.13 is fully supported. |
| TanStack Query 5.90.20 | Health polling (30s) | `refetchInterval: 30000` is the existing AlertBanner pattern -- identical approach for Status Dashboard. No version concern. |

## Sources

- PyPI python-telegram-bot 22.6: https://pypi.org/project/python-telegram-bot/ -- version 22.6 confirmed, httpx requirement `>=0.27,<0.29` confirmed, Python >=3.10 confirmed -- HIGH confidence
- python-telegram-bot official docs v22.6: https://docs.python-telegram-bot.org/telegram.bot.html -- Bot.send_message() async context manager pattern confirmed -- HIGH confidence
- GitHub issue #4819 (httpx update): https://github.com/python-telegram-bot/python-telegram-bot/issues/4819 -- httpx `>=0.27,<0.29` range confirmed as resolved/merged -- HIGH confidence
- Codebase analysis: `backend/requirements.txt` (httpx==0.28.1 confirmed in range), `backend/app/services/websocket_manager.py` (existing backoff: 5→60s, `get_stats()` method), `frontend/src/contexts/WebSocketContext.jsx` (existing reconnect logic at line 191-201) -- HIGH confidence
- WebSearch: "WebSocket reconnect exponential backoff jitter 2025" -- jitter pattern (±20%) confirmed as production best practice -- MEDIUM confidence (multiple sources agree)
- WebSearch: FastAPI health check patterns 2025 -- pure implementation confirmed as standard approach (no library needed) -- HIGH confidence (consistent across sources)
- FastAPI health check article: https://www.index.dev/blog/how-to-implement-health-check-in-python -- asyncio.gather() for parallel checks confirmed -- MEDIUM confidence

---
*Stack research for: v3.1 Hardening + Monitoring (Health-Check, Telegram, Status Dashboard, WebSocket Recovery)*
*Researched: 2026-02-28*
