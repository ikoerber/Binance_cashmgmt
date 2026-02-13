"""
Integration Tests für Order Lifecycle

Testet:
- Order Creation (PENDING → SUBMITTED → OPEN)
- Order Status Updates
- Idempotenz via client_order_id
- Order Tracking Service
- Cancel Order mit DB-Update
"""
import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock, patch
import uuid

from app.db.database import Base
from app.db.models import (
    User, TradeLotDB, OrderDB, OrderStatusEnum, LotStatusEnum,
    LedgerEventDB, EventTypeEnum, EventSourceEnum, TradeSideEnum
)
from app.services.order_tracking_service import OrderTrackingService
from app.services.order_service import OrderService


@pytest.fixture
def db_session():
    """Creates test database session"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def test_user(db_session):
    """Creates test user"""
    user = User(
        id="test-user-1",
        email="test@example.com"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_lot(db_session, test_user):
    """Creates test lot"""
    # Create fill event first
    fill_event = LedgerEventDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        type=EventTypeEnum.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 10, 0, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("50000.00"),
        side=TradeSideEnum.BUY,
        source=EventSourceEnum.BINANCE,
        source_id="binance-fill-1"
    )
    db_session.add(fill_event)

    lot = TradeLotDB(
        id="lot-1",
        user_id=test_user.id,
        created_from_fill_id=fill_event.id,
        qty_btc_initial=Decimal("0.01"),
        qty_btc_open=Decimal("0.01"),
        cost_eur=Decimal("500.50"),
        status=LotStatusEnum.OPEN,
        target_margin_pct=Decimal("0.05")
    )
    db_session.add(lot)
    db_session.commit()
    return lot


def test_create_order_record(db_session, test_user, test_lot):
    """Test: Order Creation mit PENDING Status"""
    service = OrderTrackingService()

    client_order_id = f"{test_user.id}_lot-1_55000.00_0.01_v1"
    order_id = service.create_order_record(
        db_session,
        user_id=test_user.id,
        client_order_id=client_order_id,
        symbol="BTCEUR",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        linked_lot_id=test_lot.id
    )

    # Verify
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db is not None
    assert order_db.status == OrderStatusEnum.PENDING
    assert order_db.client_order_id == client_order_id
    assert order_db.linked_lot_id == test_lot.id
    assert order_db.quantity == Decimal("0.01")
    assert order_db.price == Decimal("55000.00")


def test_idempotency_check(db_session, test_user, test_lot):
    """Test: Idempotenz - Duplikat-Order wird verhindert"""
    service = OrderTrackingService()

    client_order_id = f"{test_user.id}_lot-1_55000.00_0.01_v1"

    # Create first order
    service.create_order_record(
        db_session,
        user_id=test_user.id,
        client_order_id=client_order_id,
        symbol="BTCEUR",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        linked_lot_id=test_lot.id
    )

    # Try to create duplicate - should raise ValueError
    with pytest.raises(ValueError, match="already exists"):
        service.create_order_record(
            db_session,
            user_id=test_user.id,
            client_order_id=client_order_id,  # Same client_order_id
            symbol="BTCEUR",
            side="SELL",
            order_type="LIMIT",
            quantity=Decimal("0.01"),
            price=Decimal("55000.00"),
            linked_lot_id=test_lot.id
        )


def test_update_order_status(db_session, test_user, test_lot):
    """Test: Order Status Update PENDING → OPEN"""
    service = OrderTrackingService()

    # Create order
    client_order_id = f"{test_user.id}_lot-1_55000.00_0.01_v1"
    order_id = service.create_order_record(
        db_session,
        user_id=test_user.id,
        client_order_id=client_order_id,
        symbol="BTCEUR",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        linked_lot_id=test_lot.id
    )

    # Update to SUBMITTED
    service.update_order_status(
        db_session,
        order_id=order_id,
        status="SUBMITTED",
        binance_order_id="12345678"
    )

    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.SUBMITTED
    assert order_db.binance_order_id == "12345678"

    # Update to OPEN
    service.update_order_status(
        db_session,
        order_id=order_id,
        status="OPEN"
    )

    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.OPEN


def test_order_lifecycle_full(db_session, test_user, test_lot):
    """Test: Vollständiger Order Lifecycle PENDING → SUBMITTED → OPEN → FILLED"""
    service = OrderTrackingService()

    client_order_id = f"{test_user.id}_lot-1_55000.00_0.01_v1"

    # 1. Create (PENDING)
    order_id = service.create_order_record(
        db_session,
        user_id=test_user.id,
        client_order_id=client_order_id,
        symbol="BTCEUR",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        linked_lot_id=test_lot.id
    )
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.PENDING

    # 2. Submit to Binance (SUBMITTED)
    service.update_order_status(
        db_session,
        order_id=order_id,
        status="SUBMITTED",
        binance_order_id="12345678"
    )
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.SUBMITTED

    # 3. Accepted by Binance (OPEN)
    service.update_order_status(
        db_session,
        order_id=order_id,
        status="OPEN"
    )
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.OPEN

    # 4. Filled
    service.update_order_status(
        db_session,
        order_id=order_id,
        status="FILLED",
        raw_response={"status": "FILLED", "executedQty": "0.01"}
    )
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.FILLED
    assert order_db.raw_response is not None


def test_get_orders_for_user(db_session, test_user, test_lot):
    """Test: Get Orders with Filters"""
    service = OrderTrackingService()

    # Create multiple orders
    for i in range(3):
        client_order_id = f"{test_user.id}_lot-1_5{i}000.00_0.01_v{i}"
        order_id = service.create_order_record(
            db_session,
            user_id=test_user.id,
            client_order_id=client_order_id,
            symbol="BTCEUR",
            side="SELL",
            order_type="LIMIT",
            quantity=Decimal("0.01"),
            price=Decimal(f"5{i}000.00"),
            linked_lot_id=test_lot.id
        )

        # Update status
        if i == 0:
            service.update_order_status(db_session, order_id, "OPEN", binance_order_id=f"binance-{i}")
        elif i == 1:
            service.update_order_status(db_session, order_id, "FILLED", binance_order_id=f"binance-{i}")

    # Get all orders
    orders = service.get_orders_for_user(db_session, test_user.id)
    assert len(orders) == 3

    # Filter by PENDING
    pending_orders = service.get_orders_for_user(db_session, test_user.id, status="PENDING")
    assert len(pending_orders) == 1

    # Filter by OPEN
    open_orders = service.get_orders_for_user(db_session, test_user.id, status="OPEN")
    assert len(open_orders) == 1

    # Filter by FILLED
    filled_orders = service.get_orders_for_user(db_session, test_user.id, status="FILLED")
    assert len(filled_orders) == 1

    # Filter by lot
    lot_orders = service.get_orders_for_user(db_session, test_user.id, lot_id=test_lot.id)
    assert len(lot_orders) == 3


def test_order_rejection(db_session, test_user, test_lot):
    """Test: Order Rejection (PENDING → REJECTED)"""
    service = OrderTrackingService()

    client_order_id = f"{test_user.id}_lot-1_55000.00_0.01_v1"
    order_id = service.create_order_record(
        db_session,
        user_id=test_user.id,
        client_order_id=client_order_id,
        symbol="BTCEUR",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        linked_lot_id=test_lot.id
    )

    # Reject
    service.update_order_status(
        db_session,
        order_id=order_id,
        status="REJECTED",
        error_message="Insufficient balance"
    )

    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.REJECTED
    assert order_db.error_message == "Insufficient balance"


def test_get_order_by_client_id(db_session, test_user, test_lot):
    """Test: Find Order by client_order_id"""
    service = OrderTrackingService()

    client_order_id = f"{test_user.id}_lot-1_55000.00_0.01_v1"
    service.create_order_record(
        db_session,
        user_id=test_user.id,
        client_order_id=client_order_id,
        symbol="BTCEUR",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        linked_lot_id=test_lot.id
    )

    # Find by client_order_id
    order = service.get_order_by_client_id(db_session, client_order_id)
    assert order is not None
    assert order["client_order_id"] == client_order_id
    assert order["status"] == "PENDING"


def test_cancel_order_updates_db(db_session, test_user, test_lot):
    """Test: Cancel Order aktualisiert lokale DB auf CANCELLED"""
    tracking_service = OrderTrackingService()

    # 1. Order erstellen und auf OPEN setzen
    client_order_id = f"{test_user.id}_lot-1_55000.00_0.01_v1"
    order_id = tracking_service.create_order_record(
        db_session,
        user_id=test_user.id,
        client_order_id=client_order_id,
        symbol="BTCEUR",
        side="SELL",
        order_type="TAKE_PROFIT_LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        stop_price=Decimal("55000.00"),
        linked_lot_id=test_lot.id
    )

    binance_order_id = "99887766"
    tracking_service.update_order_status(
        db_session,
        order_id=order_id,
        status="OPEN",
        binance_order_id=binance_order_id
    )

    # Verify OPEN
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.OPEN

    # 2. Mock BinanceService und cancel_order aufrufen
    mock_binance = MagicMock()
    mock_binance.client.cancel_order.return_value = {
        "orderId": int(binance_order_id),
        "symbol": "BTCEUR",
        "status": "CANCELED"
    }

    order_service = OrderService(mock_binance)
    result = order_service.cancel_order(db_session, "BTCEUR", int(binance_order_id))

    # 3. Verify: Binance API aufgerufen
    mock_binance.client.cancel_order.assert_called_once_with(
        symbol="BTCEUR",
        orderId=int(binance_order_id)
    )

    # 4. Verify: Lokale DB auf CANCELLED aktualisiert
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order_id).first()
    assert order_db.status == OrderStatusEnum.CANCELLED
    assert result["status"] == "cancelled"


def test_verify_order_on_binance_after_timeout(db_session, test_user, test_lot):
    """Test: Order existiert auf Binance trotz lokalem Timeout → DB wird korrigiert"""

    # 1. Mock: create_order wirft Timeout, aber get_order findet Order auf Binance
    mock_binance = MagicMock()
    mock_binance.client.create_order.side_effect = Exception("Read timed out")
    mock_binance.client.get_order.return_value = {
        "orderId": 12345678,
        "status": "NEW",
        "symbol": "BTCEUR",
    }

    order_service = OrderService(mock_binance)
    result = order_service.create_limit_sell_for_lot(
        db_session, test_user.id, test_lot.id
    )

    # 2. Verify: Status ist success (nicht REJECTED)
    assert result["status"] == "success"
    assert "warning" in result

    # 3. Verify: DB zeigt OPEN (nicht REJECTED)
    order_db = db_session.query(OrderDB).filter(
        OrderDB.linked_lot_id == test_lot.id
    ).first()
    assert order_db is not None
    assert order_db.status == OrderStatusEnum.OPEN
    assert order_db.binance_order_id == "12345678"


def test_verify_order_not_on_binance_marks_rejected(db_session, test_user, test_lot):
    """Test: Order existiert NICHT auf Binance → wird korrekt als REJECTED markiert"""
    # 1. Mock: create_order UND get_order schlagen fehl
    mock_binance = MagicMock()
    mock_binance.client.create_order.side_effect = Exception("Insufficient balance")
    mock_binance.client.get_order.side_effect = Exception("Order does not exist")

    order_service = OrderService(mock_binance)

    # 2. Aufruf sollte ValueError raisen
    with pytest.raises(ValueError, match="Failed to create order"):
        order_service.create_limit_sell_for_lot(
            db_session, test_user.id, test_lot.id
        )

    # 3. Verify: DB zeigt REJECTED
    order_db = db_session.query(OrderDB).filter(
        OrderDB.linked_lot_id == test_lot.id
    ).first()
    assert order_db is not None
    assert order_db.status == OrderStatusEnum.REJECTED
    assert "Insufficient balance" in order_db.error_message
