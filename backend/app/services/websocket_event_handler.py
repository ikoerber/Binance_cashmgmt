"""
WebSocket Event Handler - DB-Updates

Verarbeitet Echtzeit-Events vom Binance User Data Stream
und aktualisiert die lokale Datenbank.

Async DB-Operations: Blockieren nicht den WebSocket-Loop.
"""
import logging
from datetime import datetime, timezone

from app.constants import BINANCE_ORDER_STATUS_MAP
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


async def handle_order_update(user_id: str, order_data: dict):
    """
    Aktualisiert OrderDB basierend auf Binance executionReport.

    Mapped Binance Status auf interne OrderStatusEnum:
    - NEW -> OPEN
    - PARTIALLY_FILLED -> PARTIALLY_FILLED
    - FILLED -> FILLED
    - CANCELED -> CANCELLED
    - REJECTED -> REJECTED
    - EXPIRED -> EXPIRED
    """
    import asyncio

    # DB-Operation in Thread ausfuehren (blockiert nicht den Event Loop)
    await asyncio.to_thread(_sync_handle_order_update, user_id, order_data)


def _sync_handle_order_update(user_id: str, order_data: dict):
    """Synchrone DB-Operation fuer Order-Update."""
    from app.db.models import OrderDB, OrderStatusEnum

    client_order_id = order_data.get("clientOrderId")
    binance_status = order_data.get("status")
    binance_order_id = order_data.get("orderId")

    if not client_order_id:
        return

    internal_status = BINANCE_ORDER_STATUS_MAP.get(binance_status)
    if not internal_status:
        logger.warning("Unbekannter Binance Order Status: %s", binance_status)
        return

    db = SessionLocal()
    try:
        # Order in DB suchen und aktualisieren
        order = db.query(OrderDB).filter(
            OrderDB.client_order_id == client_order_id,
            OrderDB.user_id == user_id,
        ).first()

        if order:
            # Idempotenz: Nur updaten wenn Status sich aendert
            if order.status.value != internal_status:
                order.status = OrderStatusEnum[internal_status]
                if binance_order_id:
                    order.binance_order_id = str(binance_order_id)
                db.commit()
                logger.info("Order aktualisiert via WebSocket: %s -> %s", client_order_id, internal_status)
            else:
                logger.debug("Order %s bereits im Status %s, kein Update noetig", client_order_id, internal_status)
        else:
            logger.debug("Order nicht in DB gefunden: %s", client_order_id)

    except Exception:
        logger.exception("DB Order-Update fehlgeschlagen fuer user=%s, order=%s", user_id, client_order_id)
        db.rollback()
    finally:
        db.close()
