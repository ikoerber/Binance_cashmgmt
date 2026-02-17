"""
WebSocket API Endpoint

Authentifizierte WebSocket-Verbindung fuer Echtzeit-Streaming.

Channels:
- price: Live BTC/EUR Preis (Binance Public Ticker Stream)
- user_data: Order-Status + Balance-Updates (Binance User Data Stream)

Auth: X-API-Key als Query-Parameter (Browser-WebSocket unterstuetzt keine Custom-Headers)
"""
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.services.websocket_manager import get_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{user_id}/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    api_key: str = Query(None, alias="X-API-Key"),
):
    """
    WebSocket Endpoint fuer Echtzeit-Updates.

    Protokoll:
    - Client -> Server: {"action": "subscribe", "channel": "price"|"user_data"}
    - Client -> Server: {"action": "unsubscribe", "channel": "price"|"user_data"}
    - Client -> Server: {"action": "ping"}
    - Server -> Client: {"type": "price_update", "symbol": "...", "price": "...", "timestamp": "..."}
    - Server -> Client: {"type": "order_update", ...}
    - Server -> Client: {"type": "balance_update", ...}
    - Server -> Client: {"type": "pong"}
    """
    # Authentifizierung
    expected_key = os.getenv("API_SECRET_KEY")
    if expected_key and api_key != expected_key:
        await websocket.close(code=4001, reason="Invalid API key")
        return

    await websocket.accept()
    logger.info(f"WebSocket verbunden: user={user_id}")

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
        logger.info(f"WebSocket getrennt: user={user_id}")
    except Exception as e:
        logger.error(f"WebSocket Fehler: {e}")
    finally:
        # Alle Subscriptions aufraeumen
        await stream_manager.unsubscribe_price(websocket)
        await stream_manager.unsubscribe_user_data(user_id, websocket)
