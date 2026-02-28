"""
TelegramNotifier — Sends Telegram messages on health state transitions.

TELE-01: Detects healthy->DOWN transitions, suppresses sustained outage alerts.
TELE-02: Complete no-op when TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.
TELE-03: Never imports or creates alert event DB rows (structural separation).
"""

import logging
import os
import threading
from typing import Optional

from telegram import Bot

logger = logging.getLogger(__name__)

# Statuses considered "DOWN" (critical tier from HealthCheckService)
DOWN_STATUSES = {"error", "unavailable"}


class TelegramNotifier:
    """Singleton service for Telegram health notifications.

    - Sends a message when a service transitions from healthy to DOWN.
    - Does NOT send on sustained outage (service stays DOWN).
    - First check after startup establishes baseline without alerts.
    - Complete no-op when env vars are missing.
    """

    def __init__(self):
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._enabled = bool(self._token and self._chat_id)
        self._bot: Optional[Bot] = None
        self._previous_states: dict[str, str] = {}

        if self._enabled:
            self._bot = Bot(token=self._token)
            logger.info("TelegramNotifier enabled (chat_id=%s)", self._chat_id)
        else:
            logger.info(
                "TelegramNotifier disabled (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set)"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self):
        """Initialize the Bot connection pool. Safe to call when disabled."""
        if self._bot:
            try:
                await self._bot.initialize()
            except Exception:
                logger.exception("TelegramNotifier failed to initialize — disabling")
                self._enabled = False
                self._bot = None

    async def stop(self):
        """Shutdown the Bot connection pool. Safe to call when disabled."""
        if self._bot:
            try:
                await self._bot.shutdown()
            except Exception:
                logger.exception("TelegramNotifier failed to shutdown")

    async def send_message(self, text: str) -> bool:
        """Send a message via Telegram. Returns False if disabled or on error."""
        if not self._enabled or not self._bot:
            return False
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
            return True
        except Exception:
            logger.exception("Failed to send Telegram message")
            return False

    async def check_transitions(self, health_result: dict) -> None:
        """Compare current health state with previous and send alerts on DOWN transitions.

        - First call per service establishes baseline (no alert).
        - Subsequent calls: alert only on healthy->DOWN transition.
        - Sustained outage (DOWN->DOWN) does NOT trigger additional alerts.
        - State is always updated regardless of send success.
        """
        if not self._enabled:
            return

        services = health_result.get("services", {})

        for name, svc_data in services.items():
            current = svc_data.get("status", "ok")
            previous = self._previous_states.get(name)

            if previous is None:
                # First check — establish baseline, no alert
                self._previous_states[name] = current
                continue

            was_down = previous in DOWN_STATUSES
            is_down = current in DOWN_STATUSES

            if is_down and not was_down:
                detail = svc_data.get("detail", "")
                msg = f"SERVICE DOWN: {name}\nStatus: {current}"
                if detail:
                    msg += f"\nDetail: {detail}"
                await self.send_message(msg)

            # Always update state (prevents infinite retry on Telegram failure)
            self._previous_states[name] = current


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_notifier_instance: Optional[TelegramNotifier] = None
_notifier_lock = threading.Lock()


def get_telegram_notifier() -> TelegramNotifier:
    """Return the singleton TelegramNotifier instance."""
    global _notifier_instance
    if _notifier_instance is None:
        with _notifier_lock:
            if _notifier_instance is None:
                _notifier_instance = TelegramNotifier()
    return _notifier_instance
