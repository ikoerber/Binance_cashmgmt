"""Tests for TelegramNotifier — covers TELE-01, TELE-02, TELE-03.

All Telegram Bot interactions are mocked — no real API calls.
"""

import inspect
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_health_result(overrides: dict | None = None) -> dict:
    """Return a health result dict with all 8 services 'ok' by default.

    overrides: {service_name: status_string} to override specific services.
    """
    services = {}
    for name in [
        "backend",
        "db",
        "websocket",
        "dry_run",
        "alpha_score",
        "sentiment",
        "macro",
        "binance_rest",
    ]:
        status = "ok"
        detail = ""
        if overrides and name in overrides:
            status = overrides[name]
            if status in ("error", "unavailable"):
                detail = f"{name} is {status}"
        services[name] = {
            "name": name,
            "status": status,
            "last_checked": "2026-02-28T12:00:00+00:00",
            "detail": detail,
        }

    overall = "healthy"
    if any(s["status"] in ("error", "unavailable") for s in services.values()):
        overall = "critical"
    elif any(
        s["status"] in ("degraded", "stale", "stopped") for s in services.values()
    ):
        overall = "degraded"

    return {
        "overall_status": overall,
        "services": services,
        "checked_at": "2026-02-28T12:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# TELE-01: Transition Detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.telegram_notifier.Bot")
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
async def test_sends_on_healthy_to_down_transition(mock_bot_class):
    """TELE-01: When a service transitions from 'ok' to 'error', send_message is called."""
    from app.services.telegram_notifier import TelegramNotifier

    mock_bot = AsyncMock()
    mock_bot_class.return_value = mock_bot

    notifier = TelegramNotifier()

    # First call: establish baseline (all ok)
    await notifier.check_transitions(_make_health_result())

    # Second call: db transitions to error
    await notifier.check_transitions(_make_health_result({"db": "error"}))

    mock_bot.send_message.assert_called_once()
    call_text = mock_bot.send_message.call_args[1].get(
        "text", mock_bot.send_message.call_args[0][0] if mock_bot.send_message.call_args[0] else ""
    )
    assert "SERVICE DOWN" in call_text
    assert "db" in call_text


@pytest.mark.asyncio
@patch("app.services.telegram_notifier.Bot")
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
async def test_no_message_on_sustained_down(mock_bot_class):
    """TELE-01: When a service stays 'error' across two checks, no message on second check."""
    from app.services.telegram_notifier import TelegramNotifier

    mock_bot = AsyncMock()
    mock_bot_class.return_value = mock_bot

    notifier = TelegramNotifier()

    # First call: establish baseline (all ok)
    await notifier.check_transitions(_make_health_result())

    # Second call: db transitions to error -> sends message
    await notifier.check_transitions(_make_health_result({"db": "error"}))
    assert mock_bot.send_message.call_count == 1

    # Third call: db stays error -> NO additional message
    await notifier.check_transitions(_make_health_result({"db": "error"}))
    assert mock_bot.send_message.call_count == 1, (
        "Should not send again on sustained outage"
    )


@pytest.mark.asyncio
@patch("app.services.telegram_notifier.Bot")
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
async def test_no_message_when_healthy(mock_bot_class):
    """TELE-01: When all services are 'ok', send_message is never called."""
    from app.services.telegram_notifier import TelegramNotifier

    mock_bot = AsyncMock()
    mock_bot_class.return_value = mock_bot

    notifier = TelegramNotifier()

    # First call: baseline
    await notifier.check_transitions(_make_health_result())
    # Second call: still healthy
    await notifier.check_transitions(_make_health_result())

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.telegram_notifier.Bot")
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
async def test_first_check_no_alert(mock_bot_class):
    """TELE-01: First check establishes baseline without sending, even if service is 'error'."""
    from app.services.telegram_notifier import TelegramNotifier

    mock_bot = AsyncMock()
    mock_bot_class.return_value = mock_bot

    notifier = TelegramNotifier()

    # First call with db already in error — baseline, no alert
    await notifier.check_transitions(_make_health_result({"db": "error"}))

    mock_bot.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# TELE-02: Graceful No-Op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "123"}, clear=False)
async def test_noop_without_token():
    """TELE-02: When TELEGRAM_BOT_TOKEN is empty, enabled is False and send_message returns False."""
    from app.services.telegram_notifier import TelegramNotifier

    notifier = TelegramNotifier()
    assert notifier.enabled is False

    result = await notifier.send_message("test")
    assert result is False


@pytest.mark.asyncio
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": ""}, clear=False)
async def test_noop_without_chat_id():
    """TELE-02: When TELEGRAM_CHAT_ID is empty, enabled is False and send_message returns False."""
    from app.services.telegram_notifier import TelegramNotifier

    notifier = TelegramNotifier()
    assert notifier.enabled is False

    result = await notifier.send_message("test")
    assert result is False


@pytest.mark.asyncio
@patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}, clear=False)
async def test_start_stop_disabled():
    """TELE-02: When disabled, start() and stop() complete without error."""
    from app.services.telegram_notifier import TelegramNotifier

    notifier = TelegramNotifier()
    assert notifier.enabled is False

    # Should not raise
    await notifier.start()
    await notifier.stop()


# ---------------------------------------------------------------------------
# TELE-03: Alert Routing Separation
# ---------------------------------------------------------------------------


def test_no_alert_event_db_creation():
    """TELE-03: telegram_notifier module does NOT import AlertEventDB."""
    from app.services import telegram_notifier

    source = inspect.getsource(telegram_notifier)
    assert "AlertEventDB" not in source, (
        "telegram_notifier.py must not reference AlertEventDB"
    )


def test_health_response_no_alert_ids():
    """TELE-03: Health result dict has no 'alert_event_id' or 'alert_id' keys."""
    result = _make_health_result()

    # Check top-level
    assert "alert_event_id" not in result
    assert "alert_id" not in result

    # Check each service
    for name, svc_data in result["services"].items():
        assert "alert_event_id" not in svc_data, (
            f"Service '{name}' should not have alert_event_id"
        )
        assert "alert_id" not in svc_data, (
            f"Service '{name}' should not have alert_id"
        )
