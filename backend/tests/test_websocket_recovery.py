"""Tests for WebSocket recovery — covers WSRC-01 and WSRC-03.

Tests the subscribe.signature migration, post-reconnect reconciliation,
user data freshness tracking, and API secret loading.
"""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlencode

import pytest


# ---------------------------------------------------------------------------
# Test 1: _build_subscribe_message structure and signature
# ---------------------------------------------------------------------------


def test_build_subscribe_message():
    """_build_subscribe_message produces a valid HMAC-SHA256 signed request."""
    from app.services.websocket_manager import _build_subscribe_message

    msg = _build_subscribe_message("test_key", "test_secret")

    assert msg["method"] == "userDataStream.subscribe.signature"
    assert "id" in msg
    assert "params" in msg

    params = msg["params"]
    assert params["apiKey"] == "test_key"
    assert isinstance(params["timestamp"], int)
    assert "signature" in params

    # Verify signature is a valid hex string (64 chars for SHA-256)
    sig = params["signature"]
    assert len(sig) == 64
    assert all(c in "0123456789abcdef" for c in sig)

    # Recompute and verify
    params_for_signing = {"apiKey": params["apiKey"], "timestamp": params["timestamp"]}
    query_string = urlencode(sorted(params_for_signing.items()))
    expected_sig = hmac.new(
        "test_secret".encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert sig == expected_sig


# ---------------------------------------------------------------------------
# Test 2: Parameter ordering for signature
# ---------------------------------------------------------------------------


def test_build_subscribe_message_param_ordering():
    """Signature is computed from alphabetically-sorted params (apiKey before timestamp)."""
    from app.services.websocket_manager import _build_subscribe_message

    msg = _build_subscribe_message("my_api_key", "my_secret")
    params = msg["params"]

    # apiKey comes before timestamp alphabetically
    params_for_signing = {"apiKey": params["apiKey"], "timestamp": params["timestamp"]}
    query_string = urlencode(sorted(params_for_signing.items()))

    # Verify the sorted order is apiKey first
    assert query_string.startswith("apiKey=")

    expected_sig = hmac.new(
        "my_secret".encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert params["signature"] == expected_sig


# ---------------------------------------------------------------------------
# Test 3: Post-reconnect reconciliation triggered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_reconnect_reconciliation_triggered():
    """After reconnect, _post_reconnect_reconciliation is called."""
    from app.services.websocket_manager import BinanceStreamManager

    manager = BinanceStreamManager()
    manager._api_key = "test_key"
    manager._api_secret = "test_secret"

    # Mock the sync reconcile
    manager._sync_reconcile_fills = MagicMock()

    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.return_value = None
        await manager._post_reconnect_reconciliation(
            "user_123", "2026-02-28T00:00:00+00:00"
        )

    mock_to_thread.assert_called_once_with(
        manager._sync_reconcile_fills, "user_123", "2026-02-28T00:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# Test 4: Reconciliation uses disconnect time
# ---------------------------------------------------------------------------


def test_reconciliation_uses_disconnect_time():
    """_sync_reconcile_fills passes start_time to reconcile_fills for each known pair."""
    from app.services.websocket_manager import BinanceStreamManager

    manager = BinanceStreamManager()

    mock_recon_service = MagicMock()
    mock_db = MagicMock()

    with (
        patch("app.services.websocket_manager.SessionLocal", return_value=mock_db),
        patch("app.services.websocket_manager.BinanceService") as mock_bs_cls,
        patch(
            "app.services.websocket_manager.ReconciliationService",
            return_value=mock_recon_service,
        ),
        patch.dict("os.environ", {
            "BINANCE_API_KEY": "k",
            "BINANCE_API_SECRET": "s",
            "BINANCE_TESTNET": "false",
        }),
    ):
        manager._sync_reconcile_fills("user_123", "2026-02-28T00:00:00+00:00")

    # Should have been called once per KNOWN_PAIRS symbol
    from app.symbol_registry import KNOWN_PAIRS

    assert mock_recon_service.reconcile_fills.call_count == len(KNOWN_PAIRS)
    for call_args in mock_recon_service.reconcile_fills.call_args_list:
        args, kwargs = call_args
        assert args[0] == mock_db  # db session
        assert args[1] == "user_123"  # user_id
        assert args[2] in KNOWN_PAIRS  # symbol
        assert args[3] == "2026-02-28T00:00:00+00:00"  # start_time


# ---------------------------------------------------------------------------
# Test 5: Reconciliation debounce
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconciliation_debounce():
    """If last reconciliation was < 60s ago, skip execution."""
    from app.services.websocket_manager import BinanceStreamManager

    manager = BinanceStreamManager()
    manager._api_key = "test_key"
    manager._api_secret = "test_secret"

    # Set last reconciliation to 30 seconds ago
    manager._last_reconciliation_at = datetime.now(timezone.utc) - timedelta(seconds=30)

    manager._sync_reconcile_fills = MagicMock()

    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        await manager._post_reconnect_reconciliation(
            "user_123", "2026-02-28T00:00:00+00:00"
        )

    # Should NOT have been called (debounced)
    mock_to_thread.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: _last_user_data_message_at updated on execution report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_user_data_message_updated_on_execution_report():
    """_handle_execution_report updates _last_user_data_message_at."""
    from app.services.websocket_manager import BinanceStreamManager

    manager = BinanceStreamManager()
    manager.user_data_subscribers = {"user_123": set()}

    assert manager._last_user_data_message_at is None

    mock_data = {
        "e": "executionReport",
        "s": "BTCEUR",
        "i": 12345,
        "c": "test_order",
        "X": "NEW",
        "S": "SELL",
        "p": "50000",
        "q": "0.001",
        "z": "0",
        "Z": "0",
        "t": 0,
    }

    with (
        patch(
            "app.services.websocket_manager.BinanceStreamManager._broadcast_to_user",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.websocket_manager.handle_order_update",
            new_callable=AsyncMock,
        ),
    ):
        await manager._handle_execution_report("user_123", mock_data)

    assert manager._last_user_data_message_at is not None
    # Should be within 1 second of now
    age = (datetime.now(timezone.utc) - manager._last_user_data_message_at).total_seconds()
    assert age < 1.0


# ---------------------------------------------------------------------------
# Test 7: _last_user_data_message_at updated on account update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_user_data_message_updated_on_account_update():
    """_handle_account_update updates _last_user_data_message_at."""
    from app.services.websocket_manager import BinanceStreamManager

    manager = BinanceStreamManager()
    manager.user_data_subscribers = {"user_123": set()}

    assert manager._last_user_data_message_at is None

    mock_data = {
        "e": "outboundAccountPosition",
        "B": [{"a": "BTC", "f": "1.0", "l": "0.0"}],
    }

    with patch(
        "app.services.websocket_manager.BinanceStreamManager._broadcast_to_user",
        new_callable=AsyncMock,
    ):
        await manager._handle_account_update("user_123", mock_data)

    assert manager._last_user_data_message_at is not None
    age = (datetime.now(timezone.utc) - manager._last_user_data_message_at).total_seconds()
    assert age < 1.0


# ---------------------------------------------------------------------------
# Test 8: Reconnect on connection drop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_on_connection_drop():
    """When ws-api/v3 connection closes, _run_user_data_stream exits for retry."""
    from app.services.websocket_manager import BinanceStreamManager

    manager = BinanceStreamManager()
    manager._api_key = "test_key"
    manager._api_secret = "test_secret"
    manager.user_data_subscribers = {"user_123": {MagicMock()}}
    manager._running = True

    import aiohttp

    # Create a mock WS that immediately sends a subscribe response then CLOSED
    mock_ws = AsyncMock()
    subscribe_response = MagicMock()
    subscribe_response.type = aiohttp.WSMsgType.TEXT
    subscribe_response.data = '{"id": "1", "result": null}'

    closed_msg = MagicMock()
    closed_msg.type = aiohttp.WSMsgType.CLOSED

    mock_ws.__aiter__ = MagicMock(
        return_value=iter([subscribe_response, closed_msg])
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.ws_connect = MagicMock(return_value=AsyncMock())
    mock_session.ws_connect.return_value.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_session.ws_connect.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("aiohttp.ClientSession", return_value=mock_session),
        patch.object(manager, "_post_reconnect_reconciliation", new_callable=AsyncMock),
    ):
        # Should complete without error (exits cleanly for retry)
        await manager._run_user_data_stream("user_123")

    # After exit, disconnect_at should be recorded
    assert "user_123" in manager._disconnect_at


# ---------------------------------------------------------------------------
# Test 9: API secret loaded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_secret_loaded():
    """After start_user_data_stream(), both _api_key and _api_secret are set."""
    from app.services.websocket_manager import BinanceStreamManager

    manager = BinanceStreamManager()

    with patch.dict(
        "os.environ",
        {"BINANCE_API_KEY": "my_key", "BINANCE_API_SECRET": "my_secret"},
    ):
        await manager.start_user_data_stream()

    assert manager._api_key == "my_key"
    assert manager._api_secret == "my_secret"
