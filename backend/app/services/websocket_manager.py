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

    Dry-Run message types (Phase 16):
    - dry_run_decision: New decision logged (factor scores, action, price)
    - dry_run_status: Dry-run toggled on/off
    - dry_run_portfolio_update: Virtual portfolio changed (buy/sell/reset)
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

        # Binance API Key for User Data Stream API (Phase 2)
        self._api_key = None

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
        Initialisiert die Binance API Keys fuer User Data Streams (Phase 2).
        Aufgerufen separat, da API Keys benoetigt werden.
        """
        api_key = os.getenv("BINANCE_API_KEY")

        if not api_key:
            logger.warning(
                "Keine Binance API Keys konfiguriert — User Data Stream deaktiviert"
            )
            return

        self._api_key = api_key
        logger.info("Binance API Keys fuer User Data Stream bereit")

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
        """Einzelne WebSocket-Session zum Binance Combined Ticker Stream (Multi-Pair)."""
        import aiohttp
        from app.symbol_registry import KNOWN_PAIRS

        # Combined Stream fuer alle bekannten Paare
        streams = "/".join(f"{sym.lower()}@ticker" for sym in KNOWN_PAIRS)

        testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"
        if testnet:
            ws_url = f"wss://testnet.binance.vision/stream?streams={streams}"
        else:
            ws_url = f"wss://stream.binance.com:9443/stream?streams={streams}"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                logger.info(f"Verbunden mit Binance Combined Ticker Stream: {ws_url}")

                async for msg in ws:
                    if not self._running:
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(msg.data)
                        # Combined Stream Format: {"stream": "btceur@ticker", "data": {...}}
                        data = payload.get("data", payload)
                        if data.get("e") == "24hrTicker":
                            symbol = data["s"]
                            price = data["c"]  # Close/Current price

                            self.current_prices[symbol] = price

                            await self._broadcast_price(symbol, price)
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
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
        """Client zum Price-Broadcast hinzufuegen. Sendet Initial-Snapshot fuer alle bekannten Paare."""
        self.price_subscribers.add(websocket)

        # Sofort aktuelle Preise senden (fuer alle bekannten Paare)
        for symbol, price in self.current_prices.items():
            try:
                await websocket.send_json(
                    {
                        "type": "price_update",
                        "symbol": symbol,
                        "price": price,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception:
                self.price_subscribers.discard(websocket)
                break

    async def unsubscribe_price(self, websocket: WebSocket):
        """Client vom Price-Broadcast entfernen."""
        self.price_subscribers.discard(websocket)

    # ─── Phase 2: User Data Stream ───

    async def subscribe_user_data(self, user_id: str, websocket: WebSocket):
        """
        Client fuer User-spezifische Updates (Orders, Balances) registrieren.
        Startet User Data Stream falls noch nicht aktiv.
        """
        if not self._api_key:
            logger.warning(
                "User Data Stream nicht verfuegbar (keine API Keys konfiguriert)"
            )
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
                if listen_key and self._api_key:
                    try:
                        await self._ws_api_request("userDataStream.stop", listen_key)
                    except Exception as e:
                        logger.warning(f"Fehler beim Schliessen des Listen Keys: {e}")

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

        if not self._api_key:
            return

        # Listen Key erstellen (via Websocket API)
        listen_key = await self._ws_api_request("userDataStream.start")
        if not listen_key:
            raise RuntimeError("Konnte keinen Listen Key via WebSocket API abrufen")

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
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
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
                if listen_key and self._api_key:
                    await self._ws_api_request("userDataStream.ping", listen_key)
                    logger.debug(f"Listen Key Keepalive: user={user_id}")
            except Exception as e:
                logger.error(f"Listen Key Keepalive fehlgeschlagen: {e}")

    async def _ws_api_request(
        self, method: str, listen_key: Optional[str] = None
    ) -> Optional[str]:
        """Hilfsmethode fuer Binance WebSocket API (statt REST API) um Listen Keys zu verwalten."""
        import aiohttp
        from uuid import uuid4

        if not self._api_key:
            return None

        testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"
        url = (
            "wss://testnet.binance.vision/ws-api/v3"
            if testnet
            else "wss://ws-api.binance.com:443/ws-api/v3"
        )

        params = {"apiKey": self._api_key}
        if listen_key:
            params["listenKey"] = listen_key

        message = {"id": str(uuid4()), "method": method, "params": params}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    await ws.send_json(message)
                    response_str = await ws.receive_str()
                    data = json.loads(response_str)

                    if "result" in data and "listenKey" in data["result"]:
                        return data["result"]["listenKey"]
                    return None
        except Exception as e:
            logger.error(f"WebSocket API request fail for {method}: {e}")
            return None

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

        # Phase 2: DB-Update async ausfuehren
        from app.services.websocket_event_handler import handle_order_update

        asyncio.create_task(handle_order_update(user_id, message))

        # Phase 3: Fill-Verarbeitung bei Trade-Ausfuehrung
        trade_id = data.get("t", 0)
        order_status = data.get("X", "")
        if trade_id and trade_id > 0 and order_status in ("FILLED", "PARTIALLY_FILLED"):
            asyncio.create_task(self._process_fill_and_broadcast(user_id, data))

    async def _process_fill_and_broadcast(self, user_id: str, data: dict):
        """
        Phase 3: Verarbeitet Fill und broadcastet Ergebnis.

        Der Fill Handler laeuft im Thread-Pool (non-blocking).
        Bei Fehler wird nur geloggt — WebSocket laeuft weiter.
        """
        from app.services.websocket_fill_handler import handle_fill_event

        try:
            result = await handle_fill_event(user_id, data)

            if result:
                fill_message = {
                    "type": "fill_processed",
                    "data": result,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await self._broadcast_to_user(user_id, fill_message)
        except Exception as e:
            logger.error("Phase 3 Fill-Verarbeitung fehlgeschlagen: %s", e)

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

    async def broadcast_message(self, user_id: str, message: dict):
        """Public broadcast method for external services (e.g., DryRunService)."""
        await self._broadcast_to_user(user_id, message)

    # ─── Status ───

    def get_stats(self) -> dict:
        """Gibt Verbindungsstatistiken zurueck."""
        return {
            "running": self._running,
            "price_subscribers": len(self.price_subscribers),
            "user_data_streams": len(self.user_data_subscribers),
            "active_tasks": len(self._tasks) + len(self._user_stream_tasks),
            "current_prices": dict(self.current_prices),
            "has_async_client": self._api_key is not None,
        }


# ─── Singleton ───

_stream_manager: Optional[BinanceStreamManager] = None


def get_stream_manager() -> BinanceStreamManager:
    """Gibt die globale BinanceStreamManager-Instanz zurueck."""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = BinanceStreamManager()
    return _stream_manager
