"""
Unit Tests für Lot-spezifische Sell Allocation

Testet die neue allocate_sell_to_lot Funktion:
- Sell an ein bestimmtes Lot (statt FIFO)
- Overflow: Sell > Lot qty → Rest via FIFO
- Edge Cases: Lot closed, Fees
"""

import pytest
from datetime import datetime
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
    allocate_sell_to_lot,
    allocate_sell_fifo,
    _compute_net_proceeds_per_btc,
)


def _make_buy_event(id, timestamp, amount, price, fee_asset=None, fee_amount=None):
    """Helper: Buy-Event erstellen"""
    return LedgerEvent(
        id=id,
        type=EventType.TRADE_FILL,
        timestamp=timestamp,
        asset="BTC",
        amount=amount,
        symbol="BTCEUR",
        price=price,
        side=TradeSide.BUY,
        fee_asset=fee_asset,
        fee_amount=fee_amount,
        source=EventSource.BINANCE,
    )


def _make_sell_event(id, timestamp, amount, price, fee_asset=None, fee_amount=None):
    """Helper: Sell-Event erstellen"""
    return LedgerEvent(
        id=id,
        type=EventType.TRADE_FILL,
        timestamp=timestamp,
        asset="BTC",
        amount=amount,
        symbol="BTCEUR",
        price=price,
        side=TradeSide.SELL,
        fee_asset=fee_asset,
        fee_amount=fee_amount,
        source=EventSource.BINANCE,
    )


def test_allocate_sell_to_specific_lot_full():
    """Sell exakt = Lot qty → Lot wird CLOSED"""
    lot = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_1", datetime(2024, 1, 1), Decimal("0.01"), Decimal("50000")
        )
    )

    sell = _make_sell_event(
        "sell_1", datetime(2024, 1, 5), Decimal("0.01"), Decimal("55000")
    )

    updated_lots, allocations = allocate_sell_to_lot(sell, lot, [])

    assert len(allocations) == 1
    assert allocations[0].trade_lot_id == lot.id
    assert allocations[0].qty_allocated == Decimal("0.01")
    # P&L = (55000 - 50000) * 0.01 = 50 EUR
    assert allocations[0].realized_pnl_eur == Decimal("50.00")

    target = next(l for l in updated_lots if l.id == lot.id)
    assert target.qty_base_open == Decimal("0")
    assert target.status == LotStatus.CLOSED


def test_allocate_sell_to_specific_lot_partial():
    """Sell < Lot qty → Lot wird PARTIAL_CLOSED"""
    lot = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_1", datetime(2024, 1, 1), Decimal("0.01"), Decimal("50000")
        )
    )

    sell = _make_sell_event(
        "sell_1", datetime(2024, 1, 5), Decimal("0.004"), Decimal("55000")
    )

    updated_lots, allocations = allocate_sell_to_lot(sell, lot, [])

    assert len(allocations) == 1
    assert allocations[0].qty_allocated == Decimal("0.004")
    # P&L = (55000 - 50000) * 0.004 = 20 EUR
    assert allocations[0].realized_pnl_eur == Decimal("20.00")

    target = next(l for l in updated_lots if l.id == lot.id)
    assert target.qty_base_open == Decimal("0.006")
    assert target.status == LotStatus.PARTIAL_CLOSED


def test_allocate_sell_to_specific_lot_with_overflow_fifo():
    """Sell > Target Lot qty → Rest via FIFO an andere Lots"""
    # Lot A: alt, teuer (FIFO wuerde dieses zuerst nehmen)
    lot_a = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_a", datetime(2024, 1, 1), Decimal("0.005"), Decimal("60000")
        )
    )
    # Lot B: neuer, guenstig (das wollen wir gezielt schliessen)
    lot_b = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_b", datetime(2024, 1, 5), Decimal("0.005"), Decimal("50000")
        )
    )

    # Sell 0.008 BTC @ 55k - Target: Lot B (0.005), Overflow: 0.003 via FIFO an Lot A
    sell = _make_sell_event(
        "sell_1", datetime(2024, 1, 10), Decimal("0.008"), Decimal("55000")
    )

    updated_lots, allocations = allocate_sell_to_lot(sell, lot_b, [lot_a])

    assert len(allocations) == 2

    # Allocation 1: Target Lot B - voll geschlossen
    alloc_b = next(a for a in allocations if a.trade_lot_id == lot_b.id)
    assert alloc_b.qty_allocated == Decimal("0.005")
    # P&L = (55000 - 50000) * 0.005 = 25 EUR
    assert alloc_b.realized_pnl_eur == Decimal("25.00")

    # Allocation 2: Overflow an Lot A (FIFO)
    alloc_a = next(a for a in allocations if a.trade_lot_id == lot_a.id)
    assert alloc_a.qty_allocated == Decimal("0.003")
    # P&L = (55000 - 60000) * 0.003 = -15 EUR
    assert alloc_a.realized_pnl_eur == Decimal("-15.00")

    # Lot B: CLOSED
    updated_b = next(l for l in updated_lots if l.id == lot_b.id)
    assert updated_b.status == LotStatus.CLOSED

    # Lot A: PARTIAL_CLOSED (0.005 - 0.003 = 0.002 offen)
    updated_a = next(l for l in updated_lots if l.id == lot_a.id)
    assert updated_a.qty_base_open == Decimal("0.002")
    assert updated_a.status == LotStatus.PARTIAL_CLOSED


def test_allocate_sell_to_specific_lot_already_closed():
    """Target-Lot hat keine offene Menge → ValueError"""
    lot = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_1", datetime(2024, 1, 1), Decimal("0.01"), Decimal("50000")
        )
    )

    # Lot manuell auf CLOSED setzen
    from dataclasses import replace

    closed_lot = replace(lot, qty_base_open=Decimal("0"), status=LotStatus.CLOSED)

    sell = _make_sell_event(
        "sell_1", datetime(2024, 1, 5), Decimal("0.01"), Decimal("55000")
    )

    with pytest.raises(ValueError, match="no open quantity"):
        allocate_sell_to_lot(sell, closed_lot, [])


def test_allocate_sell_to_specific_lot_skips_fifo_ordering():
    """Lot-spezifisch nimmt das Ziel-Lot, nicht das aelteste"""
    # 3 Lots: A (aeltestes), B (mittleres), C (neuestes)
    lot_a = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_a", datetime(2024, 1, 1), Decimal("0.01"), Decimal("60000")
        )
    )
    lot_b = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_b", datetime(2024, 1, 5), Decimal("0.01"), Decimal("55000")
        )
    )
    lot_c = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_c", datetime(2024, 1, 10), Decimal("0.01"), Decimal("50000")
        )
    )

    # Sell 0.01 BTC @ 56000 - Target: Lot C (neuestes, profitabel)
    sell = _make_sell_event(
        "sell_1", datetime(2024, 1, 15), Decimal("0.01"), Decimal("56000")
    )

    updated_lots, allocations = allocate_sell_to_lot(sell, lot_c, [lot_a, lot_b])

    # Nur Lot C bekommt die Allocation (nicht Lot A, das FIFO nehmen wuerde!)
    assert len(allocations) == 1
    assert allocations[0].trade_lot_id == lot_c.id
    assert allocations[0].qty_allocated == Decimal("0.01")
    # P&L = (56000 - 50000) * 0.01 = 60 EUR
    assert allocations[0].realized_pnl_eur == Decimal("60.00")

    # Lot C: CLOSED, Lots A und B: unveraendert
    updated_c = next(l for l in updated_lots if l.id == lot_c.id)
    assert updated_c.status == LotStatus.CLOSED

    updated_a = next(l for l in updated_lots if l.id == lot_a.id)
    assert updated_a.status == LotStatus.OPEN
    assert updated_a.qty_base_open == Decimal("0.01")

    updated_b = next(l for l in updated_lots if l.id == lot_b.id)
    assert updated_b.status == LotStatus.OPEN


def test_allocate_sell_to_specific_lot_with_eur_fee():
    """Lot-spezifisch mit EUR Fee"""
    lot = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_1", datetime(2024, 1, 1), Decimal("0.01"), Decimal("50000")
        )
    )

    sell = _make_sell_event(
        "sell_1",
        datetime(2024, 1, 5),
        Decimal("0.01"),
        Decimal("55000"),
        fee_asset="EUR",
        fee_amount=Decimal("1.00"),
    )

    updated_lots, allocations = allocate_sell_to_lot(sell, lot, [])

    # Erloes brutto = 550 EUR, Fee = 1 EUR, netto = 549 EUR
    # Kosten = 500 EUR → P&L = 49 EUR
    assert allocations[0].realized_pnl_eur == Decimal("49.00")


def test_allocate_sell_to_specific_lot_with_bnb_fee():
    """Lot-spezifisch mit BNB Fee"""
    lot = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_1", datetime(2024, 1, 1), Decimal("0.01"), Decimal("50000")
        )
    )

    sell = _make_sell_event(
        "sell_1",
        datetime(2024, 1, 5),
        Decimal("0.01"),
        Decimal("55000"),
        fee_asset="BNB",
        fee_amount=Decimal("0.001"),
    )

    fee_rates = {"BNB": Decimal("700.00")}
    updated_lots, allocations = allocate_sell_to_lot(sell, lot, [], fee_rates)

    # Fee = 0.001 BNB * 700 = 0.70 EUR
    # Netto-Erloes = (55000 - 70) * 0.01 = 549.30 EUR
    # Kosten = 500 EUR → P&L = 49.30 EUR
    expected_fee_eur = Decimal("0.001") * Decimal("700")  # 0.70
    net_per_btc = Decimal("55000") - (expected_fee_eur / Decimal("0.01"))
    expected_pnl = (net_per_btc - Decimal("50000")) * Decimal("0.01")
    assert abs(allocations[0].realized_pnl_eur - expected_pnl) < Decimal("0.01")


def test_allocate_sell_to_specific_lot_overflow_insufficient():
    """Overflow: nicht genug Lots fuer den Rest → ValueError"""
    lot_target = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_1", datetime(2024, 1, 1), Decimal("0.005"), Decimal("50000")
        )
    )

    # Sell 0.02 BTC, aber Target hat nur 0.005 und keine weiteren Lots
    sell = _make_sell_event(
        "sell_1", datetime(2024, 1, 5), Decimal("0.02"), Decimal("55000")
    )

    with pytest.raises(ValueError, match="Not enough open lots"):
        allocate_sell_to_lot(sell, lot_target, [])


def test_compute_net_proceeds_helper_consistency():
    """Helper liefert gleiche Ergebnisse wie vorher inline"""
    sell = _make_sell_event(
        "sell_1",
        datetime(2024, 1, 5),
        Decimal("0.01"),
        Decimal("55000"),
        fee_asset="EUR",
        fee_amount=Decimal("1.00"),
    )

    net = _compute_net_proceeds_per_btc(sell)

    # 55000 - (1.00 / 0.01) = 55000 - 100 = 54900
    assert net == Decimal("54900")


def test_allocate_sell_to_lot_vs_fifo_different_result():
    """Beweist, dass lot-spezifisch ein anderes Ergebnis als FIFO liefert"""
    # Lot A: alt, Verlierer (BE = 60000)
    lot_a = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_a", datetime(2024, 1, 1), Decimal("0.01"), Decimal("60000")
        )
    )
    # Lot B: neu, Gewinner (BE = 50000)
    lot_b = create_trade_lot_from_buy_fill(
        _make_buy_event(
            "fill_b", datetime(2024, 1, 5), Decimal("0.01"), Decimal("50000")
        )
    )

    sell = _make_sell_event(
        "sell_1", datetime(2024, 1, 10), Decimal("0.01"), Decimal("55000")
    )

    # FIFO: nimmt Lot A (aeltestes) → Verlust
    _, fifo_allocs = allocate_sell_fifo(sell, [lot_a, lot_b])
    assert fifo_allocs[0].trade_lot_id == lot_a.id
    # P&L = (55000 - 60000) * 0.01 = -50 EUR
    assert fifo_allocs[0].realized_pnl_eur == Decimal("-50.00")

    # Lot-spezifisch: nimmt Lot B (Gewinner) → Gewinn
    _, specific_allocs = allocate_sell_to_lot(sell, lot_b, [lot_a])
    assert specific_allocs[0].trade_lot_id == lot_b.id
    # P&L = (55000 - 50000) * 0.01 = 50 EUR
    assert specific_allocs[0].realized_pnl_eur == Decimal("50.00")
