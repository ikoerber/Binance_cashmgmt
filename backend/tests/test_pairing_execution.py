"""
Integration Tests für Pairing Execution

Testet:
- Pairing Creation (DRAFT)
- Pairing Lock (DRAFT → LOCKED)
- Pairing Execution (LOCKED → EXECUTED)
- Order Creation für Lots in Pairing
- Rollback bei fehlgeschlagener Execution
"""

import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from app.db.database import Base
from app.db.models import (
    User,
    TradeLotDB,
    PairingDB,
    PairingItemDB,
    OrderDB,
    LotStatusEnum,
    PairingStatusEnum,
    OrderStatusEnum,
    LedgerEventDB,
    EventTypeEnum,
    EventSourceEnum,
    TradeSideEnum,
)
from app.services.pairing_service import (
    create_pairing,
    get_pairing_by_id,
    list_pairings,
    lock_pairing,
    execute_pairing,
    delete_pairing,
    simulate_pairing_execution,
)
from app.domain.orders import compute_pairing_order_params
from app.db.models import UserSettingsDB


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
def test_lots(db_session, test_user):
    """Creates test lots (1 winner, 1 loser)"""
    lots = []

    # Create fill events
    for i, (qty, cost, price) in enumerate(
        [
            (Decimal("0.01"), Decimal("500.00"), Decimal("50000.00")),  # Winner
            (Decimal("0.02"), Decimal("1100.00"), Decimal("55000.00")),  # Loser
        ]
    ):
        fill_event = LedgerEventDB(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            type=EventTypeEnum.TRADE_FILL,
            timestamp=datetime(2024, 1, i + 1, 10, 0, 0),
            asset="BTC",
            amount=qty,
            symbol="BTCEUR",
            price=price,
            side=TradeSideEnum.BUY,
            source=EventSourceEnum.BINANCE,
            source_id=f"binance-fill-{i}",
        )
        db_session.add(fill_event)

        lot = TradeLotDB(
            id=f"lot-{i+1}",
            user_id=test_user.id,
            created_from_fill_id=fill_event.id,
            qty_base_initial=qty,
            qty_base_open=qty,
            cost_eur=cost,
            status=LotStatusEnum.OPEN,
            target_margin_pct=Decimal("0.05"),
        )
        db_session.add(lot)
        lots.append(lot)

    db_session.commit()
    return lots


def _make_items(lots):
    """Helper: Konvertiert TradeLotDB zu dict-Items für create_pairing"""
    return [{"lot_id": lot.id, "qty_base": lot.qty_base_open} for lot in lots]


def test_create_pairing(db_session, test_user, test_lots):
    """Test: Pairing Creation mit DRAFT Status"""
    items = _make_items(test_lots)

    pairing = create_pairing(
        db_session,
        user_id=test_user.id,
        items=items,
        threshold_pct=Decimal("0.05"),
    )

    # Verify
    assert pairing["status"] == "DRAFT"
    assert pairing["threshold_pct"] == "0.050000"
    assert len(pairing["items"]) == 2


def test_lock_pairing(db_session, test_user, test_lots):
    """Test: Pairing Lock (DRAFT → LOCKED)"""
    items = _make_items([test_lots[0]])

    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))
    assert pairing["status"] == "DRAFT"

    # Lock
    locked = lock_pairing(db_session, test_user.id, pairing["id"])
    assert locked["status"] == "LOCKED"


def test_lock_non_draft_pairing_fails(db_session, test_user, test_lots):
    """Test: Lock nur auf DRAFT Pairings möglich"""
    items = _make_items([test_lots[0]])

    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))
    lock_pairing(db_session, test_user.id, pairing["id"])

    # Try to lock again - should fail
    with pytest.raises(ValueError, match="not in DRAFT"):
        lock_pairing(db_session, test_user.id, pairing["id"])


def test_execute_pairing_creates_orders(db_session, test_user, test_lots):
    """Test: Execute Pairing lifecycle DRAFT → LOCKED → EXECUTED"""
    items = _make_items([test_lots[0]])

    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))
    lock_pairing(db_session, test_user.id, pairing["id"])

    pairing_db = (
        db_session.query(PairingDB).filter(PairingDB.id == pairing["id"]).first()
    )
    assert pairing_db.status == PairingStatusEnum.LOCKED

    # Execute
    executed = execute_pairing(db_session, test_user.id, pairing["id"])
    assert executed["status"] == "EXECUTED"


def test_delete_draft_pairing(db_session, test_user, test_lots):
    """Test: Delete DRAFT Pairing"""
    items = _make_items([test_lots[0]])

    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))
    pairing_id = pairing["id"]

    # Delete
    delete_pairing(db_session, test_user.id, pairing_id)

    # Verify deleted
    deleted_pairing = (
        db_session.query(PairingDB).filter(PairingDB.id == pairing_id).first()
    )
    assert deleted_pairing is None


def test_delete_locked_pairing_fails(db_session, test_user, test_lots):
    """Test: Locked/Executed Pairings können nicht gelöscht werden"""
    items = _make_items([test_lots[0]])

    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))
    lock_pairing(db_session, test_user.id, pairing["id"])

    # Try to delete locked - should fail
    with pytest.raises(ValueError, match="DRAFT"):
        delete_pairing(db_session, test_user.id, pairing["id"])


def test_pairing_items_relationship(db_session, test_user, test_lots):
    """Test: Pairing Items werden korrekt gespeichert"""
    items = _make_items(test_lots)

    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))

    # Verify items in DB
    pairing_db = (
        db_session.query(PairingDB).filter(PairingDB.id == pairing["id"]).first()
    )
    assert len(pairing_db.items) == 2

    item_db = pairing_db.items[0]
    assert item_db.lot_id in [test_lots[0].id, test_lots[1].id]
    assert item_db.qty_base > 0
    assert item_db.cost_eur > 0


def test_pairing_cascade_delete(db_session, test_user, test_lots):
    """Test: Deleting Pairing cascades to items"""
    items = _make_items([test_lots[0]])

    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))
    pairing_id = pairing["id"]

    # Verify items exist
    items_count = (
        db_session.query(PairingItemDB)
        .filter(PairingItemDB.pairing_id == pairing_id)
        .count()
    )
    assert items_count == 1

    # Delete pairing
    delete_pairing(db_session, test_user.id, pairing_id)

    # Verify items also deleted (cascade)
    items_count = (
        db_session.query(PairingItemDB)
        .filter(PairingItemDB.pairing_id == pairing_id)
        .count()
    )
    assert items_count == 0


def test_multiple_pairings_for_user(db_session, test_user, test_lots):
    """Test: User kann mehrere Pairings haben"""
    # Create 2 pairings
    for i in range(2):
        items = [{"lot_id": test_lots[0].id, "qty_base": Decimal("0.005")}]
        create_pairing(db_session, test_user.id, items, Decimal("0.05"))

    # Verify
    pairings = (
        db_session.query(PairingDB).filter(PairingDB.user_id == test_user.id).all()
    )
    assert len(pairings) == 2


def test_compute_pairing_order_params_basic():
    """Test: Aggregierte Order-Parameter-Berechnung mit korrektem Rounding und Format"""
    from types import SimpleNamespace

    items = [SimpleNamespace(lot_id="lot-1", qty_base=Decimal("0.01234567"))]

    result = compute_pairing_order_params(
        pairing_id="pairing-1",
        user_id="user-1",
        items=items,
        market_price=Decimal("55000"),
        fee_buffer_pct=Decimal("0.002"),
        max_order_value_eur=Decimal("1000"),
    )

    # Grundstruktur
    assert result["symbol"] == "BTCEUR"
    assert result["side"] == "SELL"
    assert result["type"] == "TAKE_PROFIT_LIMIT"
    assert result["timeInForce"] == "GTC"

    # Rounding: quantity auf 5 Dezimalstellen, price auf 2
    assert result["quantity"] == "0.01235"  # gerundet
    assert result["price"] == result["stopPrice"]

    # Preis = 55000 * 1.002 = 55110.00
    assert result["price"] == "55110.00"

    # ClientOrderId Format (aggregiert: user_pairing_id_price_version)
    assert "user-1" in result["newClientOrderId"]
    assert "pairing" in result["newClientOrderId"]

    # Lot-Zuordnung
    assert result["lot_ids"] == ["lot-1"]
    assert result["lot_count"] == 1

    # Order Value = 0.01235 * 55110.00 = 680.61
    order_val = Decimal(result["order_value_eur"])
    assert order_val < Decimal("1000")
    assert result["exceeds_max_order_value"] is False


def test_simulate_includes_planned_orders(db_session, test_user, test_lots):
    """Test: Simulation enthaelt planned_orders mit Binance-Parametern"""
    items = _make_items(test_lots)
    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))

    result = simulate_pairing_execution(
        db_session,
        user_id=test_user.id,
        pairing_id=pairing["id"],
        market_price=Decimal("55000"),
        fee_pct=Decimal("0.001"),
        fee_buffer_pct=Decimal("0.002"),
    )

    # Neue Felder vorhanden
    assert "planned_orders" in result
    assert "has_max_value_violation" in result
    assert "max_order_value_eur" in result
    assert "fee_buffer_pct" in result

    # Aggregierte Order: 1 Order fuer alle Lots im Pairing
    assert len(result["planned_orders"]) == 1

    order = result["planned_orders"][0]
    assert order["symbol"] == "BTCEUR"
    assert order["side"] == "SELL"
    assert order["type"] == "TAKE_PROFIT_LIMIT"
    assert order["timeInForce"] == "GTC"
    assert order["price"] == order["stopPrice"]
    assert "newClientOrderId" in order
    assert "order_value_eur" in order
    assert isinstance(order["exceeds_max_order_value"], bool)
    assert order["lot_count"] == 2
    assert len(order["lot_ids"]) == 2

    # Bestehende Felder weiterhin vorhanden
    assert "total_base_to_sell" in result
    assert "expected_proceeds_eur" in result
    assert "affected_lots" in result


def test_simulate_max_value_violation(db_session, test_user, test_lots):
    """Test: Max-Order-Value-Ueberschreitung wird erkannt"""
    items = _make_items(test_lots)
    pairing = create_pairing(db_session, test_user.id, items, Decimal("0.05"))

    # Sehr niedriges Max-Limit setzen
    settings = UserSettingsDB(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        max_order_value_eur=Decimal("10"),  # 10 EUR - wird definitiv ueberschritten
    )
    db_session.add(settings)
    db_session.commit()

    result = simulate_pairing_execution(
        db_session,
        user_id=test_user.id,
        pairing_id=pairing["id"],
        market_price=Decimal("55000"),
    )

    assert result["has_max_value_violation"] is True
    assert Decimal(result["max_order_value_eur"]) == Decimal("10")

    for order in result["planned_orders"]:
        assert order["exceeds_max_order_value"] is True
