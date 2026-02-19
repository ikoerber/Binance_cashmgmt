"""
Unit Tests für TradeLot-Logik und FIFO Sell Allocation

Testet die Kern-Business-Logik für Lot-Management.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.models import (
    EventType,
    EventSource,
    LedgerEvent,
    TradeSide,
    LotStatus,
)
from app.domain.lots import (
    create_trade_lot_from_buy_fill,
    allocate_sell_fifo,
    calculate_lot_target_price,
)


def test_create_lot_from_buy_simple():
    """Test: TradeLot aus einfachem Buy-Fill erstellen"""
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )

    lot = create_trade_lot_from_buy_fill(buy_event)

    assert lot.id == "lot_fill_1"
    assert lot.created_from_fill_id == "fill_1"
    assert lot.qty_base_initial == Decimal("0.01")
    assert lot.qty_base_open == Decimal("0.01")
    assert lot.cost_eur == Decimal("500.00")  # 0.01 * 50000
    assert lot.break_even == Decimal("50000.00")
    assert lot.status == LotStatus.OPEN


def test_create_lot_with_eur_fee():
    """Test: TradeLot mit EUR Fee"""
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        fee_asset="EUR",
        fee_amount=Decimal("1.00"),
        source=EventSource.BINANCE,
    )

    lot = create_trade_lot_from_buy_fill(buy_event)

    # Kosten = 500 + 1 = 501 EUR
    assert lot.cost_eur == Decimal("501.00")
    assert lot.break_even == Decimal("50100.00")  # 501 / 0.01


def test_create_lot_with_btc_fee():
    """Test: TradeLot mit BTC Fee - qty ist BRUTTO, Fee wird abgezogen"""
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),  # BRUTTO von Binance (VOR Fee-Abzug)
        symbol="BTCEUR",
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        fee_asset="BTC",
        fee_amount=Decimal("0.00001"),
        source=EventSource.BINANCE,
    )

    lot = create_trade_lot_from_buy_fill(buy_event)

    # qty_net = 0.01 - 0.00001 = 0.00999 (BRUTTO minus Fee)
    # cost = 0.01 * 50000 = 500.00 EUR (tatsächlich bezahlt, KEINE Fee-Addition)
    # break_even = 500.00 / 0.00999 = 50050.05
    assert lot.qty_base_initial == Decimal("0.00999")
    assert lot.qty_base_open == Decimal("0.00999")
    assert lot.cost_eur == Decimal("500.00")
    expected_be = Decimal("500.00") / Decimal("0.00999")
    assert abs(lot.break_even - expected_be) < Decimal("0.01")


def test_create_lot_from_sell_fails():
    """Test: Sell-Fill darf kein Lot erstellen"""
    sell_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("50000.00"),
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
    )

    with pytest.raises(ValueError, match="side must be BUY"):
        create_trade_lot_from_buy_fill(sell_event)


def test_fifo_allocation_single_lot_full():
    """Test: FIFO - Ein Lot wird vollständig geschlossen"""
    # Buy: 0.01 BTC @ 50k
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Sell: 0.01 BTC @ 55k (Gewinn!)
    sell_event = LedgerEvent(
        id="fill_2",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 2, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("55000.00"),
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
    )

    updated_lots, allocations = allocate_sell_fifo(sell_event, [lot])

    # Prüfungen
    assert len(allocations) == 1
    assert len(updated_lots) == 1

    allocation = allocations[0]
    assert allocation.sell_fill_id == "fill_2"
    assert allocation.trade_lot_id == lot.id
    assert allocation.qty_allocated == Decimal("0.01")
    # P&L = (55000 - 50000) * 0.01 = 50 EUR
    assert allocation.realized_pnl_eur == Decimal("50.00")

    updated_lot = updated_lots[0]
    assert updated_lot.qty_base_open == Decimal("0")
    assert updated_lot.status == LotStatus.CLOSED


def test_fifo_allocation_single_lot_partial():
    """Test: FIFO - Lot wird teilweise geschlossen"""
    # Buy: 0.01 BTC @ 50k
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Sell: nur 0.005 BTC @ 55k
    sell_event = LedgerEvent(
        id="fill_2",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 2, 12, 0),
        asset="BTC",
        amount=Decimal("0.005"),
        price=Decimal("55000.00"),
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
    )

    updated_lots, allocations = allocate_sell_fifo(sell_event, [lot])

    # Prüfungen
    allocation = allocations[0]
    assert allocation.qty_allocated == Decimal("0.005")
    # P&L = (55000 - 50000) * 0.005 = 25 EUR
    assert allocation.realized_pnl_eur == Decimal("25.00")

    updated_lot = updated_lots[0]
    assert updated_lot.qty_base_open == Decimal("0.005")
    assert updated_lot.status == LotStatus.PARTIAL_CLOSED


def test_fifo_allocation_multiple_lots():
    """Test: FIFO - Sell schließt mehrere Lots (ältestes zuerst)"""
    # Buy 1: 0.01 BTC @ 50k (älter)
    buy1 = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Buy 2: 0.01 BTC @ 60k (neuer)
    buy2 = LedgerEvent(
        id="fill_2",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 2, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("60000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot2 = create_trade_lot_from_buy_fill(buy2)

    # Sell: 0.015 BTC @ 55k (schließt lot1 voll + lot2 halb)
    sell_event = LedgerEvent(
        id="fill_3",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 3, 12, 0),
        asset="BTC",
        amount=Decimal("0.015"),
        price=Decimal("55000.00"),
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
    )

    # Unsortierte Liste (Lot2 zuerst, aber FIFO sollte Lot1 zuerst nehmen)
    updated_lots, allocations = allocate_sell_fifo(sell_event, [lot2, lot1])

    # Prüfungen
    assert len(allocations) == 2

    # Erste Allocation: Lot1 (älter) wird voll geschlossen
    alloc1 = next(a for a in allocations if a.trade_lot_id == lot1.id)
    assert alloc1.qty_allocated == Decimal("0.01")
    # P&L = (55000 - 50000) * 0.01 = 50 EUR Gewinn
    assert alloc1.realized_pnl_eur == Decimal("50.00")

    # Zweite Allocation: Lot2 wird halb geschlossen
    alloc2 = next(a for a in allocations if a.trade_lot_id == lot2.id)
    assert alloc2.qty_allocated == Decimal("0.005")
    # P&L = (55000 - 60000) * 0.005 = -25 EUR Verlust
    assert alloc2.realized_pnl_eur == Decimal("-25.00")

    # Lot-Status prüfen
    updated_lot1 = next(l for l in updated_lots if l.id == lot1.id)
    assert updated_lot1.qty_base_open == Decimal("0")
    assert updated_lot1.status == LotStatus.CLOSED

    updated_lot2 = next(l for l in updated_lots if l.id == lot2.id)
    assert updated_lot2.qty_base_open == Decimal("0.005")
    assert updated_lot2.status == LotStatus.PARTIAL_CLOSED


def test_fifo_allocation_with_fee():
    """Test: FIFO - Sell mit EUR Fee"""
    # Buy: 0.01 BTC @ 50k
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Sell: 0.01 BTC @ 55k, Fee 1 EUR
    sell_event = LedgerEvent(
        id="fill_2",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 2, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("55000.00"),
        side=TradeSide.SELL,
        fee_asset="EUR",
        fee_amount=Decimal("1.00"),
        source=EventSource.BINANCE,
    )

    updated_lots, allocations = allocate_sell_fifo(sell_event, [lot])

    allocation = allocations[0]
    # Erlös brutto = 550 EUR
    # Fee = 1 EUR
    # Erlös netto = 549 EUR
    # Kosten = 500 EUR
    # P&L = 549 - 500 = 49 EUR
    assert allocation.realized_pnl_eur == Decimal("49.00")


def test_fifo_allocation_insufficient_lots():
    """Test: FIFO - Nicht genug offene Lots wirft Fehler"""
    # Buy: 0.01 BTC
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Sell: 0.02 BTC (mehr als verfügbar!)
    sell_event = LedgerEvent(
        id="fill_2",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 2, 12, 0),
        asset="BTC",
        amount=Decimal("0.02"),
        price=Decimal("55000.00"),
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
    )

    with pytest.raises(ValueError, match="Not enough open lots"):
        allocate_sell_fifo(sell_event, [lot])


def test_calculate_lot_target_price():
    """Test: Zielpreis-Berechnung für Lot"""
    # Lot mit Break-even 50k
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Target: 5% Margin
    target = calculate_lot_target_price(lot, Decimal("0.05"))
    assert target == Decimal("52500.00")  # 50k * 1.05

    # Mit Fee-Buffer (0.2%)
    target_with_buffer = calculate_lot_target_price(
        lot, Decimal("0.05"), fee_buffer_pct=Decimal("0.002")
    )
    expected = Decimal("50000") * Decimal("1.05") * Decimal("1.002")
    assert abs(target_with_buffer - expected) < Decimal("0.01")


def test_lot_unrealized_pnl():
    """Test: Unrealisierte P&L eines Lots"""
    # Buy: 0.01 BTC @ 50k
    buy_event = LedgerEvent(
        id="fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 1, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Marktpreis steigt auf 55k
    market_price = Decimal("55000.00")
    unrealized = lot.unrealized_pnl(market_price)

    # Erwartet: (55000 * 0.01) - (50000 * 0.01) = 50 EUR Gewinn
    assert unrealized == Decimal("50.00")

    # Unrealisiert %
    unrealized_pct = lot.unrealized_pnl_pct(market_price)
    assert unrealized_pct == Decimal("0.1")  # 10%
