"""
WebSocket Manager - Binance Stream Hub

Verwaltet persistente Verbindungen zu Binance WebSocket Streams und
broadcastet Echtzeit-Updates an authentifizierte Frontend-Clients.

Architektur:
- Separater AsyncClient (nur fuer WebSocket Streams)
- Bestehender sync Client in binance.py bleibt unveraendert
- Singleton-Pattern: Ein Binance-Stream bedient alle Frontend-Clients

Migration (Phase 21 / WSRC-01):
- Legacy userDataStream.start/ping/stop entfernt (Binance deprecated 2026-02-20)
- Ersetzt durch userDataStream.subscribe.signature (HMAC-SHA256 signed)
- Post-reconnect fill reconciliation mit 60s Debounce
- User data freshness tracking fuer Health Check (WSRC-02)
"""

import asyncio
import hashlib
import hmac as hmac_mod
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional, Set
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure function — subscribe.signature message builder (WSRC-01)
# ---------------------------------------------------------------------------


def _build_subscribe_message(api_key: str, api_secret: str) -> dict:
    """
    Build a userDataStream.subscribe.signature request for Binance ws-api/v3.

    The params are signed with HMAC-SHA256 of alphabetically-sorted
    URL-encoded params (apiKey before timestamp).

    Returns a dict ready to be sent as JSON over the WebSocket.
    """
    timestamp = int(time.time() * 1000)
    params = {"apiKey": api_key, "timestamp": timestamp}

    # Alphabetically-sorted query string for signing
    query_string = urlencode(sorted(params.items()))
    signature = hmac_mod.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    params["signature"] = signature

    return {
        "id": str(uuid4()),
        "method": "userDataStream.subscribe.signature",
        "params": params,
    }


class BinanceStreamManager:
    """
    Singleton Manager fuer Binance WebSocket Streams.

    Phase 1: Oeffentlicher Ticker Stream (BTC/EUR Preis)
    Phase 2: User Data Stream (Orders + Balances) — via subscribe.signature
    Phase 21: Migrated to subscribe.signature, post-reconnect reconciliation

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

        # Binance API credentials for User Data Stream (Phase 21: both key + secret)
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None

        # WSRC-01: Post-reconnect reconciliation state
        self._reconnect_count: Dict[str, int] = {}
        self._disconnect_at: Dict[str, Optional[datetime]] = {}
        self._last_reconciliation_at: Optional[datetime] = None

        # WSRC-03: User data freshness tracking
        self._last_user_data_message_at: Optional[datetime] = None

    @property
    def last_user_data_message_at(self) -> Optional[datetime]:
        """Expose freshness timestamp for health check (WSRC-02)."""
        return self._last_user_data_message_at

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
        Initialisiert die Binance API Keys fuer User Data Streams.
        Phase 21: Requires both API_KEY and API_SECRET for subscribe.signature.
        """
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")

        if not api_key or not api_secret:
            logger.warning(
                "Keine Binance API Keys konfiguriert — User Data Stream deaktiviert"
            )
            return

        self._api_key = api_key
        self._api_secret = api_secret
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

    # ─── Phase 2: User Data Stream (subscribe.signature) ───

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
        """
        Einzelne User Data Stream Session via subscribe.signature (WSRC-01).

        Connects to wss://ws-api.binance.com:443/ws-api/v3, sends a signed
        subscribe request, and processes executionReport / outboundAccountPosition
        events. On disconnect, records disconnect_at for post-reconnect reconciliation.
        """
        import aiohttp

        if not self._api_key or not self._api_secret:
            return

        testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"
        ws_url = (
            "wss://testnet.binance.vision/ws-api/v3"
            if testnet
            else "wss://ws-api.binance.com:443/ws-api/v3"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    # Send subscribe.signature request
                    subscribe_msg = _build_subscribe_message(
                        self._api_key, self._api_secret
                    )
                    await ws.send_json(subscribe_msg)
                    logger.info(
                        "User Data Stream subscribe.signature gesendet: user=%s",
                        user_id,
                    )

                    # Post-reconnect reconciliation (WSRC-01)
                    reconnect_count = self._reconnect_count.get(user_id, 0)
                    if reconnect_count > 0:
                        disconnect_time = self._disconnect_at.get(user_id)
                        start_time_iso = (
                            disconnect_time.isoformat() if disconnect_time else None
                        )
                        await self._post_reconnect_reconciliation(
                            user_id, start_time_iso
                        )

                    self._reconnect_count[user_id] = reconnect_count + 1

                    # Process messages
                    async for msg in ws:
                        if not self._running:
                            break
                        if user_id not in self.user_data_subscribers:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)

                            # Subscribe confirmation response
                            if "result" in data:
                                request_id = data.get("id", "?")
                                if data.get("result") is None:
                                    logger.info(
                                        "User Data Stream subscribe bestaetigt: "
                                        "user=%s, id=%s",
                                        user_id,
                                        request_id,
                                    )
                                else:
                                    logger.warning(
                                        "User Data Stream subscribe response: "
                                        "user=%s, result=%s",
                                        user_id,
                                        data["result"],
                                    )
                                continue

                            event_type = data.get("e")

                            if event_type == "executionReport":
                                self._last_user_data_message_at = datetime.now(
                                    timezone.utc
                                )
                                await self._handle_execution_report(user_id, data)
                            elif event_type == "outboundAccountPosition":
                                self._last_user_data_message_at = datetime.now(
                                    timezone.utc
                                )
                                await self._handle_account_update(user_id, data)
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
        finally:
            # Record disconnect time for next reconnect reconciliation
            self._disconnect_at[user_id] = datetime.now(timezone.utc)

    # ─── WSRC-01: Post-reconnect fill reconciliation ───

    async def _post_reconnect_reconciliation(
        self, user_id: str, start_time_iso: Optional[str]
    ):
        """
        Reconcile fills after a WebSocket reconnect.

        Debounce: skips if last reconciliation was < 60 seconds ago.
        Runs reconcile_fills in a thread (blocking DB operations).
        """
        now = datetime.now(timezone.utc)
        if self._last_reconciliation_at and (
            now - self._last_reconciliation_at
        ).total_seconds() < 60:
            logger.debug(
                "Post-reconnect reconciliation skipped (debounce): user=%s", user_id
            )
            return

        try:
            self._last_reconciliation_at = now
            await asyncio.to_thread(
                self._sync_reconcile_fills, user_id, start_time_iso
            )
            logger.info(
                "Post-reconnect reconciliation completed: user=%s", user_id
            )
        except Exception:
            logger.exception(
                "Post-reconnect reconciliation failed: user=%s", user_id
            )

    def _sync_reconcile_fills(
        self, user_id: str, start_time: Optional[str]
    ):
        """
        Synchronous wrapper for reconcile_fills — runs in thread pool.

        Reconciles fills for all KNOWN_PAIRS since the disconnect time.
        """
        from app.db.database import SessionLocal
        from app.services.binance import BinanceService
        from app.services.reconciliation_service import ReconciliationService
        from app.symbol_registry import KNOWN_PAIRS

        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"

        binance_service = BinanceService(api_key, api_secret, testnet=testnet)
        recon_service = ReconciliationService(binance_service)

        db = SessionLocal()
        try:
            for symbol in KNOWN_PAIRS:
                recon_service.reconcile_fills(db, user_id, symbol, start_time)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ─── Event Handlers ───

    async def _handle_execution_report(self, user_id: str, data: dict):
        """Verarbeitet Order-Status-Updates von Binance."""
        # WSRC-03: Track user data freshness
        self._last_user_data_message_at = datetime.now(timezone.utc)

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
        # WSRC-03: Track user data freshness
        self._last_user_data_message_at = datetime.now(timezone.utc)

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
            "has_api_credentials": self._api_key is not None
            and self._api_secret is not None,
            "last_user_data_message_at": (
                self._last_user_data_message_at.isoformat()
                if self._last_user_data_message_at
                else None
            ),
            "reconnect_counts": dict(self._reconnect_count),
        }


# ─── Singleton ───

_stream_manager: Optional[BinanceStreamManager] = None


def get_stream_manager() -> BinanceStreamManager:
    """Gibt die globale BinanceStreamManager-Instanz zurueck."""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = BinanceStreamManager()
    return _stream_manager
