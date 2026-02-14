"""
Order Tracking Service - Order State Management

Trackt alle Orders mit vollständigem Lifecycle:
PENDING → SUBMITTED → OPEN → PARTIALLY_FILLED → FILLED
oder PENDING/SUBMITTED/OPEN → CANCELLED/REJECTED/EXPIRED
"""
from decimal import Decimal
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
import uuid

from app.db.models import OrderDB, OrderStatusEnum, TradeSideEnum
from app.domain.models import utcnow
from app.services.binance import BinanceService


class OrderTrackingService:
    """
    Order Tracking Service - Verwaltet Order State Lifecycle

    Idempotenz via client_order_id sichergestellt.
    """

    def __init__(self, binance_service: Optional[BinanceService] = None):
        self.binance_service = binance_service

    def create_order_record(
        self,
        db: Session,
        user_id: str,
        client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        linked_lot_id: Optional[str] = None,
        linked_pairing_id: Optional[str] = None
    ) -> str:
        """
        Erstellt OrderDB Entry mit Status PENDING

        Wird aufgerufen BEFORE Binance API Call.

        Args:
            db: Database Session
            user_id: User ID
            client_order_id: Idempotent client order ID
            symbol: Trading pair (z.B. "BTCEUR")
            side: BUY oder SELL
            order_type: LIMIT, MARKET, STOP_LIMIT
            quantity: Order quantity
            price: Limit price (None für MARKET)
            linked_lot_id: Optional linked TradeLot
            linked_pairing_id: Optional linked Pairing

        Returns:
            order_id (UUID)

        Raises:
            ValueError: Wenn client_order_id bereits existiert
        """
        # Check for existing order (idempotency)
        existing = self.check_idempotency(db, client_order_id)
        if existing:
            raise ValueError(f"Order with client_order_id {client_order_id} already exists")

        order_id = str(uuid.uuid4())
        order_db = OrderDB(
            id=order_id,
            user_id=user_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=TradeSideEnum[side],
            type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            status=OrderStatusEnum.PENDING,
            linked_lot_id=linked_lot_id,
            linked_pairing_id=linked_pairing_id,
            created_at=utcnow(),
            updated_at=utcnow()
        )

        db.add(order_db)
        db.flush()
        db.refresh(order_db)

        return order_id

    def update_order_status(
        self,
        db: Session,
        order_id: str,
        status: str,
        binance_order_id: Optional[str] = None,
        error_message: Optional[str] = None,
        raw_response: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Updated Order Status nach Binance Response

        Args:
            db: Database Session
            order_id: Internal order ID
            status: New status (SUBMITTED, OPEN, FILLED, REJECTED, etc.)
            binance_order_id: Binance order ID (wenn vorhanden)
            error_message: Error message (bei REJECTED)
            raw_response: Full Binance response

        Returns:
            Updated order as dict

        Raises:
            ValueError: Wenn Order nicht gefunden
        """
        order_db = db.query(OrderDB).filter(OrderDB.id == order_id).first()

        if not order_db:
            raise ValueError(f"Order {order_id} not found")

        # Update status
        order_db.status = OrderStatusEnum[status]
        order_db.updated_at = utcnow()

        if binance_order_id:
            order_db.binance_order_id = binance_order_id

        if error_message:
            order_db.error_message = error_message

        if raw_response:
            order_db.raw_response = raw_response

        db.flush()
        db.refresh(order_db)

        return self._order_to_dict(order_db)

    def check_idempotency(
        self,
        db: Session,
        client_order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Prüft ob client_order_id bereits existiert

        Args:
            db: Database Session
            client_order_id: Client order ID

        Returns:
            Existing order dict or None
        """
        order_db = db.query(OrderDB).filter(
            OrderDB.client_order_id == client_order_id
        ).first()

        if order_db:
            return self._order_to_dict(order_db)

        return None

    def sync_order_status(
        self,
        db: Session,
        order_id: str
    ) -> Dict[str, Any]:
        """
        Fetches order status from Binance und updated DB

        Args:
            db: Database Session
            order_id: Internal order ID

        Returns:
            Updated order dict

        Raises:
            ValueError: Wenn Order nicht gefunden oder kein binance_order_id
        """
        order_db = db.query(OrderDB).filter(OrderDB.id == order_id).first()

        if not order_db:
            raise ValueError(f"Order {order_id} not found")

        if not order_db.binance_order_id:
            raise ValueError(f"Order {order_id} has no binance_order_id, cannot sync")

        if not self.binance_service:
            raise ValueError("BinanceService not initialized")

        # Fetch from Binance
        try:
            binance_order = self.binance_service.client.get_order(
                symbol=order_db.symbol,
                orderId=order_db.binance_order_id
            )

            # Map Binance status to internal status
            binance_status = binance_order["status"]
            status_map = {
                "NEW": "OPEN",
                "PARTIALLY_FILLED": "PARTIALLY_FILLED",
                "FILLED": "FILLED",
                "CANCELED": "CANCELLED",
                "REJECTED": "REJECTED",
                "EXPIRED": "EXPIRED"
            }

            new_status = status_map.get(binance_status, "OPEN")

            # Update status
            order_db.status = OrderStatusEnum[new_status]
            order_db.raw_response = binance_order
            order_db.updated_at = utcnow()

            db.flush()
            db.refresh(order_db)

            return self._order_to_dict(order_db)

        except Exception as e:
            raise ValueError(f"Failed to sync order from Binance: {str(e)}")

    def get_orders_for_user(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        lot_id: Optional[str] = None,
        pairing_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Query orders with filters

        Args:
            db: Database Session
            user_id: User ID
            status: Optional status filter
            symbol: Optional symbol filter
            lot_id: Optional lot filter
            pairing_id: Optional pairing filter
            limit: Max results
            offset: Pagination offset

        Returns:
            List of order dicts
        """
        query = db.query(OrderDB).filter(OrderDB.user_id == user_id)

        if status:
            query = query.filter(OrderDB.status == OrderStatusEnum[status])

        if symbol:
            query = query.filter(OrderDB.symbol == symbol)

        if lot_id:
            query = query.filter(OrderDB.linked_lot_id == lot_id)

        if pairing_id:
            query = query.filter(OrderDB.linked_pairing_id == pairing_id)

        orders_db = query.order_by(OrderDB.created_at.desc()).limit(limit).offset(offset).all()

        return [self._order_to_dict(order_db) for order_db in orders_db]

    def get_order_by_client_id(
        self,
        db: Session,
        client_order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Finds order by unique client_order_id

        Args:
            db: Database Session
            client_order_id: Client order ID

        Returns:
            Order dict or None
        """
        order_db = db.query(OrderDB).filter(
            OrderDB.client_order_id == client_order_id
        ).first()

        if order_db:
            return self._order_to_dict(order_db)

        return None

    def get_order_by_id(
        self,
        db: Session,
        order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Finds order by internal order_id

        Args:
            db: Database Session
            order_id: Internal order ID

        Returns:
            Order dict or None
        """
        order_db = db.query(OrderDB).filter(OrderDB.id == order_id).first()

        if order_db:
            return self._order_to_dict(order_db)

        return None

    def import_external_orders(
        self,
        db: Session,
        user_id: str,
        symbol: str = "BTCEUR"
    ) -> Dict[str, Any]:
        """
        Importiert externe Orders von Binance in lokale DB

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading symbol

        Returns:
            Import report
        """
        if not self.binance_service:
            raise ValueError("BinanceService not initialized")

        report = {
            "imported": 0,
            "skipped": 0,
            "errors": []
        }

        try:
            # Hole offene Orders von Binance
            binance_orders = self.binance_service.client.get_open_orders(symbol=symbol)

            for binance_order in binance_orders:
                client_order_id = binance_order["clientOrderId"]

                # Check ob bereits vorhanden
                existing = self.check_idempotency(db, client_order_id)
                if existing:
                    report["skipped"] += 1
                    continue

                # Importiere Order
                order_id = str(uuid.uuid4())

                # Map Binance status
                binance_status = binance_order["status"]
                status_map = {
                    "NEW": "OPEN",
                    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
                    "FILLED": "FILLED",
                    "CANCELED": "CANCELLED",
                    "REJECTED": "REJECTED",
                    "EXPIRED": "EXPIRED"
                }
                status = status_map.get(binance_status, "OPEN")

                order_db = OrderDB(
                    id=order_id,
                    user_id=user_id,
                    client_order_id=client_order_id,
                    binance_order_id=str(binance_order["orderId"]),
                    symbol=binance_order["symbol"],
                    side=TradeSideEnum[binance_order["side"]],
                    type=binance_order["type"],
                    quantity=Decimal(str(binance_order["origQty"])),
                    price=Decimal(str(binance_order["price"])) if binance_order.get("price") else None,
                    status=OrderStatusEnum[status],
                    raw_response=binance_order,
                    created_at=utcnow(),
                    updated_at=utcnow()
                )

                db.add(order_db)
                report["imported"] += 1

            db.flush()

        except Exception as e:
            report["errors"].append(str(e))

        return report

    def _order_to_dict(self, order_db: OrderDB) -> Dict[str, Any]:
        """Konvertiert OrderDB zu Dict"""
        return {
            "id": order_db.id,
            "user_id": order_db.user_id,
            "client_order_id": order_db.client_order_id,
            "binance_order_id": order_db.binance_order_id,
            "symbol": order_db.symbol,
            "side": order_db.side.value,
            "type": order_db.type,
            "quantity": str(order_db.quantity),
            "price": str(order_db.price) if order_db.price else None,
            "stop_price": str(order_db.stop_price) if order_db.stop_price else None,
            "status": order_db.status.value,
            "linked_lot_id": order_db.linked_lot_id,
            "linked_pairing_id": order_db.linked_pairing_id,
            "error_message": order_db.error_message,
            "created_at": order_db.created_at.isoformat(),
            "updated_at": order_db.updated_at.isoformat(),
        }
