"""
WebSocket API Endpoint

Authentifizierte WebSocket-Verbindung fuer Echtzeit-Streaming.

Channels:
- price: Live BTC/EUR Preis (Binance Public Ticker Stream)
- user_data: Order-Status + Balance-Updates (Binance User Data Stream)

Auth: First-Message-Auth — Client sendet {"action": "auth", "api_key": "..."} als erste Nachricht.
"""
import asyncio
import hmac
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import get_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Timeout fuer Auth-Nachricht nach Connect (Sekunden)
_AUTH_TIMEOUT_SECONDS = 10


@router.websocket("/ws/{user_id}/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
):
    """
    WebSocket Endpoint fuer Echtzeit-Updates.

    Protokoll:
    - Client -> Server: {"action": "auth", "api_key": "..."} (MUSS erste Nachricht sein)
    - Client -> Server: {"action": "subscribe", "channel": "price"|"user_data"}
    - Client -> Server: {"action": "unsubscribe", "channel": "price"|"user_data"}
    - Client -> Server: {"action": "ping"}
    - Server -> Client: {"type": "auth_ok"}
    - Server -> Client: {"type": "price_update", "symbol": "...", "price": "...", "timestamp": "..."}
    - Server -> Client: {"type": "order_update", ...}
    - Server -> Client: {"type": "balance_update", ...}
    - Server -> Client: {"type": "pong"}
    """
    expected_key = os.getenv("API_SECRET_KEY")

    if expected_key:
        # First-Message-Auth: Accept, dann auf Auth-Nachricht warten
        await websocket.accept()
        try:
            data = await asyncio.wait_for(
                websocket.receive_json(), timeout=_AUTH_TIMEOUT_SECONDS
            )
            received_key = data.get("api_key", "")
            if data.get("action") != "auth" or not received_key or not hmac.compare_digest(received_key, expected_key):
                await websocket.send_json({"type": "auth_error", "detail": "Invalid API key"})
                await websocket.close(code=4001, reason="Invalid API key")
                return
            await websocket.send_json({"type": "auth_ok"})
            logger.info("WebSocket verbunden (Message-Auth): user=%s", user_id)
        except asyncio.TimeoutError:
            await websocket.close(code=4001, reason="Auth timeout")
            return
    else:
        # Kein API_SECRET_KEY konfiguriert — kein Auth noetig (dev mode)
        await websocket.accept()
        logger.warning("WebSocket verbunden (no auth — dev mode): user=%s", user_id)

    stream_manager = get_stream_manager()

    # Automatisch Price-Channel subscriben
    await stream_manager.subscribe_price(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "subscribe":
                channel = data.get("channel")
                if channel == "price":
                    await stream_manager.subscribe_price(websocket)
                elif channel == "user_data":
                    await stream_manager.subscribe_user_data(user_id, websocket)

            elif action == "unsubscribe":
                channel = data.get("channel")
                if channel == "price":
                    await stream_manager.unsubscribe_price(websocket)
                elif channel == "user_data":
                    await stream_manager.unsubscribe_user_data(user_id, websocket)

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("WebSocket getrennt: user=%s", user_id)
    except Exception:
        logger.exception("WebSocket Fehler fuer user=%s", user_id)
    finally:
        # Alle Subscriptions aufraeumen
        await stream_manager.unsubscribe_price(websocket)
        await stream_manager.unsubscribe_user_data(user_id, websocket)
