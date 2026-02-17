"""
WebSocket Manager - Binance Stream Hub

Verwaltet persistente Verbindungen zu Binance WebSocket Streams und
broadcastet Echtzeit-Updates an authentifizierte Frontend-Clients.

Architektur:
- Separater AsyncClient (nur fuer WebSocket Streams)
- Bestehender sync Client in binance.py bleibt unveraendert
- Singleton-Pattern: Ein Binance-Stream bedient alle Frontend-Clients
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class BinanceStreamManager:
    """
    Singleton Manager fuer Binance WebSocket Streams.

    Phase 1: Oeffentlicher Ticker Stream (BTC/EUR Preis)
    Phase 2: User Data Stream (Orders + Balances)
    """

    def __init__(self):
        self._running = False
        self._tasks: Set[asyncio.Task] = set()

        # Phase 1: Price Stream
        self.price_subscribers: Set[WebSocket] = set()
        self.current_prices: Dict[str, str] = {}

        # Phase 2: User Data Stream
        self.user_data_subscribers: Dict[str, Set[WebSocket]] = {}
        self._user_stream_tasks: Dict[str, asyncio.Task] = {}
        self._listen_keys: Dict[str, str] = {}

        # Binance async client (Phase 2)
        self._async_client = None

    async def start(self):
        """Startet den Price Stream. Aufgerufen in FastAPI Lifespan."""
        if self._running:
            return

        self._running = True

        # Phase 1: Public Price Stream (kein API-Key noetig)
        task = asyncio.create_task(self._price_stream_loop())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        logger.info("BinanceStreamManager gestartet")

    async def start_user_data_stream(self):
        """
        Initialisiert den Binance AsyncClient fuer User Data Streams (Phase 2).
        Aufgerufen separat, da API Keys benoetigt werden.
        """
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")

        if not api_key or not api_secret:
            logger.warning("Keine Binance API Keys konfiguriert — User Data Stream deaktiviert")
            return

        try:
            from binance import AsyncClient
            testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"
            self._async_client = await AsyncClient.create(api_key, api_secret, testnet=testnet)
            logger.info("Binance AsyncClient fuer User Data Stream initialisiert")
        except Exception as e:
            logger.error(f"AsyncClient-Initialisierung fehlgeschlagen: {e}")

    async def stop(self):
        """Stoppt alle Streams und schliesst Verbindungen."""
        self._running = False

        # Alle Tasks canceln
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._user_stream_tasks.values()):
            task.cancel()

        all_tasks = list(self._tasks) + list(self._user_stream_tasks.values())
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)

        # AsyncClient schliessen
        if self._async_client:
            await self._async_client.close_connection()

        self._tasks.clear()
        self._user_stream_tasks.clear()
        self.price_subscribers.clear()
        self.user_data_subscribers.clear()

        logger.info("BinanceStreamManager gestoppt")

    # ─── Phase 1: Public Price Stream ───

    async def _price_stream_loop(self):
        """
        Verbindet sich zum Binance Public Ticker Stream fuer BTCEUR.
        Reconnected automatisch mit Exponential Backoff.
        """
        backoff = 5
        max_backoff = 60

        while self._running:
            try:
                await self._run_price_stream()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Price Stream Fehler: {e}")
                if self._running:
                    logger.info(f"Reconnect in {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)

    async def _run_price_stream(self):
        """Einzelne WebSocket-Session zum Binance Ticker Stream."""
        import aiohttp

        testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"
        if testnet:
            ws_url = "wss://testnet.binance.vision/ws/btceur@ticker"
        else:
            ws_url = "wss://stream.binance.com:9443/ws/btceur@ticker"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                logger.info(f"Verbunden mit Binance Ticker Stream: {ws_url}")

                async for msg in ws:
                    if not self._running:
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("e") == "24hrTicker":
                            symbol = data["s"]
                            price = data["c"]  # Close/Current price

                            self.current_prices[symbol] = price

                            await self._broadcast_price(symbol, price)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

    async def _broadcast_price(self, symbol: str, price: str):
        """Sendet Preis-Update an alle verbundenen Clients."""
        if not self.price_subscribers:
            return

        message = {
            "type": "price_update",
            "symbol": symbol,
            "price": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        disconnected = set()
        for ws in self.price_subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)

        self.price_subscribers -= disconnected

    async def subscribe_price(self, websocket: WebSocket):
        """Client zum Price-Broadcast hinzufuegen. Sendet Initial-Snapshot."""
        self.price_subscribers.add(websocket)

        # Sofort aktuellen Preis senden (falls vorhanden)
        if "BTCEUR" in self.current_prices:
            try:
                await websocket.send_json({
                    "type": "price_update",
                    "symbol": "BTCEUR",
                    "price": self.current_prices["BTCEUR"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                self.price_subscribers.discard(websocket)

    async def unsubscribe_price(self, websocket: WebSocket):
        """Client vom Price-Broadcast entfernen."""
        self.price_subscribers.discard(websocket)

    # ─── Phase 2: User Data Stream ───

    async def subscribe_user_data(self, user_id: str, websocket: WebSocket):
        """
        Client fuer User-spezifische Updates (Orders, Balances) registrieren.
        Startet User Data Stream falls noch nicht aktiv.
        """
        if not self._async_client:
            logger.warning("User Data Stream nicht verfuegbar (kein AsyncClient)")
            return

        if user_id not in self.user_data_subscribers:
            self.user_data_subscribers[user_id] = set()

        self.user_data_subscribers[user_id].add(websocket)

        # Stream starten falls noch nicht aktiv
        if user_id not in self._user_stream_tasks:
            task = asyncio.create_task(self._user_data_stream_loop(user_id))
            self._user_stream_tasks[user_id] = task
            task.add_done_callback(lambda t: self._user_stream_tasks.pop(user_id, None))

    async def unsubscribe_user_data(self, user_id: str, websocket: WebSocket):
        """Client von User Data Stream entfernen."""
        if user_id in self.user_data_subscribers:
            self.user_data_subscribers[user_id].discard(websocket)

            # Stream beenden wenn keine Subscriber mehr
            if not self.user_data_subscribers[user_id]:
                del self.user_data_subscribers[user_id]
                task = self._user_stream_tasks.pop(user_id, None)
                if task:
                    task.cancel()

                # Listen Key schliessen
                listen_key = self._listen_keys.pop(user_id, None)
                if listen_key and self._async_client:
                    try:
                        await self._async_client.stream_close(listen_key)
                    except Exception:
                        pass

    async def _user_data_stream_loop(self, user_id: str):
        """User Data Stream mit Reconnection."""
        backoff = 5
        max_backoff = 60

        while self._running and user_id in self.user_data_subscribers:
            try:
                await self._run_user_data_stream(user_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"User Data Stream Fehler (user={user_id}): {e}")
                if self._running and user_id in self.user_data_subscribers:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)

    async def _run_user_data_stream(self, user_id: str):
        """Einzelne User Data Stream Session."""
        import aiohttp

        if not self._async_client:
            return

        # Listen Key erstellen
        listen_key = await self._async_client.stream_get_listen_key()
        self._listen_keys[user_id] = listen_key

        # Keepalive Task starten (alle 30 Minuten)
        keepalive_task = asyncio.create_task(self._keepalive_listen_key(user_id))

        testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"
        if testnet:
            ws_url = f"wss://testnet.binance.vision/ws/{listen_key}"
        else:
            ws_url = f"wss://stream.binance.com:9443/ws/{listen_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    logger.info(f"User Data Stream verbunden: user={user_id}")

                    async for msg in ws:
                        if not self._running:
                            break
                        if user_id not in self.user_data_subscribers:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            event_type = data.get("e")

                            if event_type == "executionReport":
                                await self._handle_execution_report(user_id, data)
                            elif event_type == "outboundAccountPosition":
                                await self._handle_account_update(user_id, data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
        finally:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass

    async def _keepalive_listen_key(self, user_id: str):
        """Haelt den Listen Key aktiv (Binance Requirement: alle 30 Minuten)."""
        while self._running:
            await asyncio.sleep(1800)  # 30 Minuten
            try:
                listen_key = self._listen_keys.get(user_id)
                if listen_key and self._async_client:
                    await self._async_client.stream_keepalive(listen_key)
                    logger.debug(f"Listen Key Keepalive: user={user_id}")
            except Exception as e:
                logger.error(f"Listen Key Keepalive fehlgeschlagen: {e}")

    async def _handle_execution_report(self, user_id: str, data: dict):
        """Verarbeitet Order-Status-Updates von Binance."""
        message = {
            "type": "order_update",
            "symbol": data.get("s"),
            "orderId": data.get("i"),
            "clientOrderId": data.get("c"),
            "status": data.get("X"),
            "side": data.get("S"),
            "price": data.get("p"),
            "quantity": data.get("q"),
            "executedQty": data.get("z"),
            "cumulativeQuoteQty": data.get("Z"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self._broadcast_to_user(user_id, message)

        # DB-Update async ausfuehren
        from app.services.websocket_event_handler import handle_order_update
        asyncio.create_task(handle_order_update(user_id, message))

    async def _handle_account_update(self, user_id: str, data: dict):
        """Verarbeitet Balance-Updates von Binance."""
        balances = {}
        for b in data.get("B", []):
            asset = b["a"]
            free = b["f"]
            locked = b["l"]
            balances[asset] = {
                "free": free,
                "locked": locked,
                "total": str(Decimal(free) + Decimal(locked)),
            }

        message = {
            "type": "balance_update",
            "balances": balances,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self._broadcast_to_user(user_id, message)

    async def _broadcast_to_user(self, user_id: str, message: dict):
        """Sendet Nachricht an alle Clients eines Users."""
        subscribers = self.user_data_subscribers.get(user_id, set())
        if not subscribers:
            return

        disconnected = set()
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)

        if disconnected:
            self.user_data_subscribers[user_id] -= disconnected

    # ─── Status ───

    def get_stats(self) -> dict:
        """Gibt Verbindungsstatistiken zurueck."""
        return {
            "running": self._running,
            "price_subscribers": len(self.price_subscribers),
            "user_data_streams": len(self.user_data_subscribers),
            "active_tasks": len(self._tasks) + len(self._user_stream_tasks),
            "current_prices": dict(self.current_prices),
            "has_async_client": self._async_client is not None,
        }


# ─── Singleton ───

_stream_manager: Optional[BinanceStreamManager] = None


def get_stream_manager() -> BinanceStreamManager:
    """Gibt die globale BinanceStreamManager-Instanz zurueck."""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = BinanceStreamManager()
    return _stream_manager
