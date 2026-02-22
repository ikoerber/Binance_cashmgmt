"""
Integration Tests für Reconciliation Service

Testet:
- Order Status Reconciliation
- Balance Reconciliation
- Fill Reconciliation
- Full Reconciliation

Note: Diese Tests verwenden Mocks für Binance API Calls
"""

import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, patch
import uuid

from app.db.database import Base
from app.db.models import (
    User,
    OrderDB,
    OrderStatusEnum,
    LedgerEventDB,
    EventTypeEnum,
    EventSourceEnum,
    TradeSideEnum,
)
from app.services.reconciliation_service import ReconciliationService
from app.services.binance import BinanceService


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
    user = User(id="test-user-1", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def mock_binance_service():
    """Mocked BinanceService"""
    service = Mock(spec=BinanceService)
    return service


@pytest.fixture
def reconciliation_service(mock_binance_service):
    """ReconciliationService with mocked Binance"""
    return ReconciliationService(mock_binance_service)


def test_reconcile_orders_no_changes(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Reconciliation wenn keine Änderungen"""
    # Create open order in DB
    order = OrderDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        client_order_id="test-order-1",
        binance_order_id="12345678",
        symbol="BTCEUR",
        side=TradeSideEnum.SELL,
        type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        status=OrderStatusEnum.OPEN,
    )
    db_session.add(order)
    db_session.commit()

    # Mock Binance response - order still open
    mock_binance_service.get_open_orders.return_value = [
        {"orderId": 12345678, "status": "NEW"}
    ]

    # Reconcile
    report = reconciliation_service.reconcile_orders(db_session, test_user.id, "BTCEUR")

    assert report["synced"] == 1
    assert report["status_updated"] == 0
    assert len(report["discrepancies"]) == 0


def test_reconcile_orders_status_update(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Order Status wird von Binance updated"""
    # Create open order in DB
    order = OrderDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        client_order_id="test-order-1",
        binance_order_id="12345678",
        symbol="BTCEUR",
        side=TradeSideEnum.SELL,
        type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        status=OrderStatusEnum.OPEN,
    )
    db_session.add(order)
    db_session.commit()

    # Mock Binance response - order not in open orders (filled)
    mock_binance_service.get_open_orders.return_value = []
    mock_binance_service.get_order.return_value = {
        "orderId": 12345678,
        "status": "FILLED",
        "executedQty": "0.01",
    }

    # Reconcile
    report = reconciliation_service.reconcile_orders(db_session, test_user.id, "BTCEUR")

    assert report["synced"] == 1
    assert report["status_updated"] == 1

    # Verify status updated
    order_db = db_session.query(OrderDB).filter(OrderDB.id == order.id).first()
    assert order_db.status == OrderStatusEnum.FILLED


def test_reconcile_orders_discrepancy(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Discrepancy wenn Order nicht auf Binance gefunden"""
    # Create open order in DB
    order = OrderDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        client_order_id="test-order-1",
        binance_order_id="12345678",
        symbol="BTCEUR",
        side=TradeSideEnum.SELL,
        type="LIMIT",
        quantity=Decimal("0.01"),
        price=Decimal("55000.00"),
        status=OrderStatusEnum.OPEN,
    )
    db_session.add(order)
    db_session.commit()

    # Mock Binance response - order not found
    mock_binance_service.get_open_orders.return_value = []
    mock_binance_service.get_order.side_effect = Exception("Order not found")

    # Reconcile
    report = reconciliation_service.reconcile_orders(db_session, test_user.id, "BTCEUR")

    assert report["synced"] == 1
    assert len(report["discrepancies"]) == 1
    assert (
        "Order-Details konnten nicht von Binance abgerufen werden"
        in report["discrepancies"][0]["issue"]
    )


def test_reconcile_balances_within_tolerance(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Balance Reconciliation innerhalb Toleranz"""
    # Create initial EUR deposit
    deposit = LedgerEventDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        type=EventTypeEnum.DEPOSIT,
        timestamp=datetime(2024, 1, 1, 9, 0, 0),
        asset="EUR",
        amount=Decimal("1500.00"),
        source=EventSourceEnum.BINANCE,
    )
    db_session.add(deposit)

    # Create BTC buy fill (spends 500 EUR)
    event1 = LedgerEventDB(
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
    )
    db_session.add(event1)
    db_session.commit()

    # Mock Binance balance - matching calculated: BTC=0.01, EUR=1500-500=1000
    mock_binance_service.get_account.return_value = {
        "balances": [
            {"asset": "BTC", "free": "0.01", "locked": "0"},
            {"asset": "EUR", "free": "1000.00", "locked": "0"},
        ]
    }

    # Reconcile
    report = reconciliation_service.reconcile_balances(db_session, test_user.id)

    assert report["within_tolerance"] is True
    assert report["base"]["within_tolerance"] is True


def test_reconcile_balances_outside_tolerance(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Balance Reconciliation außerhalb Toleranz"""
    # Create ledger events
    event1 = LedgerEventDB(
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
    )
    db_session.add(event1)
    db_session.commit()

    # Mock Binance balance - significantly different BTC
    mock_binance_service.get_account.return_value = {
        "balances": [
            {"asset": "BTC", "free": "0.02", "locked": "0"},  # 0.01 difference
            {"asset": "EUR", "free": "0", "locked": "0"},
        ]
    }

    # Reconcile with tight tolerance
    report = reconciliation_service.reconcile_balances(
        db_session, test_user.id, tolerance_base=Decimal("0.0001")
    )

    assert report["base"]["within_tolerance"] is False
    assert Decimal(report["base"]["diff"]) == Decimal("0.01")


def test_reconcile_balances_with_fees(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Balance Reconciliation berücksichtigt BTC Fees"""
    # Create initial EUR deposit
    deposit = LedgerEventDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        type=EventTypeEnum.DEPOSIT,
        timestamp=datetime(2024, 1, 1, 9, 0, 0),
        asset="EUR",
        amount=Decimal("1500.00"),
        source=EventSourceEnum.BINANCE,
    )
    db_session.add(deposit)

    # Create buy fill with BTC fee
    event1 = LedgerEventDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        type=EventTypeEnum.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 10, 0, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("50000.00"),
        side=TradeSideEnum.BUY,
        fee_asset="BTC",
        fee_amount=Decimal("0.0001"),
        source=EventSourceEnum.BINANCE,
    )
    db_session.add(event1)
    db_session.commit()

    # Mock Binance balance: BTC=0.01-0.0001=0.0099, EUR=1500-500=1000
    mock_binance_service.get_account.return_value = {
        "balances": [
            {"asset": "BTC", "free": "0.0099", "locked": "0"},
            {"asset": "EUR", "free": "1000.00", "locked": "0"},
        ]
    }

    # Reconcile
    report = reconciliation_service.reconcile_balances(db_session, test_user.id)

    assert report["within_tolerance"] is True
    assert Decimal(report["base"]["calculated"]) == Decimal("0.0099")


def test_full_reconciliation(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Full Reconciliation ruft alle Sub-Reconciliations auf"""
    # Mock all Binance responses
    mock_binance_service.get_open_orders.return_value = []
    mock_binance_service.get_account.return_value = {
        "balances": [
            {"asset": "BTC", "free": "0", "locked": "0"},
            {"asset": "EUR", "free": "0", "locked": "0"},
        ]
    }

    # Mock fetch_trades on the binance service (used by SyncService internally)
    mock_binance_service.fetch_trades.return_value = []

    # Run full reconciliation
    report = reconciliation_service.full_reconciliation(
        db_session, test_user.id, "BTCEUR"
    )

    assert "orders" in report
    assert "balances" in report
    assert "fills" in report


def test_reconcile_orders_error_handling(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Error Handling bei Binance API Fehler"""
    # Mock Binance error
    mock_binance_service.get_open_orders.side_effect = Exception("API Error")

    # Reconcile
    report = reconciliation_service.reconcile_orders(db_session, test_user.id, "BTCEUR")

    assert len(report["errors"]) > 0
    assert "Binance-Orders konnten nicht abgerufen werden" in report["errors"][0]


def test_reconcile_multiple_orders(
    db_session, test_user, reconciliation_service, mock_binance_service
):
    """Test: Reconcile mehrere Orders gleichzeitig"""
    # Create multiple orders
    for i in range(3):
        order = OrderDB(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            client_order_id=f"test-order-{i}",
            binance_order_id=str(12345678 + i),
            symbol="BTCEUR",
            side=TradeSideEnum.SELL,
            type="LIMIT",
            quantity=Decimal("0.01"),
            price=Decimal("55000.00"),
            status=OrderStatusEnum.OPEN,
        )
        db_session.add(order)
    db_session.commit()

    # Mock Binance - 1 still open, 2 filled
    mock_binance_service.get_open_orders.return_value = [
        {"orderId": 12345678, "status": "NEW"}
    ]
    mock_binance_service.get_order.side_effect = [
        {"orderId": 12345679, "status": "FILLED", "executedQty": "0.01"},
        {"orderId": 12345680, "status": "FILLED", "executedQty": "0.01"},
    ]

    # Reconcile
    report = reconciliation_service.reconcile_orders(db_session, test_user.id, "BTCEUR")

    assert report["synced"] == 3
    assert report["status_updated"] == 2  # 2 filled
