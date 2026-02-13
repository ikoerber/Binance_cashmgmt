"""
Unit Tests für TradeLot Fee-Behandlung

Testet insbesondere BNB-Fee-Konvertierung
"""
import pytest
from datetime import datetime
from decimal import Decimal

from app.domain.models import (
    EventType,
    EventSource,
    LedgerEvent,
    TradeSide,
)
from app.domain.lots import create_trade_lot_from_buy_fill, allocate_sell_fifo


def test_lot_creation_with_bnb_fee():
    """Test: TradeLot mit BNB Fee wird korrekt berechnet"""
    # Buy: 0.01 BTC @ 57650 EUR, Fee: 0.00082344 BNB
    # BNB/EUR Preis: 700 EUR (angenommen)
    fill_event = LedgerEvent(
        id="test_fill_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2026, 2, 9, 19, 53),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("57650.00"),
        side=TradeSide.BUY,
        fee_asset="BNB",
        fee_amount=Decimal("0.00082344"),
        source=EventSource.BINANCE,
        source_id="167736655",
    )

    bnb_eur_price = Decimal("700.00")
    fee_conversion_rates = {"BNB": bnb_eur_price}

    lot = create_trade_lot_from_buy_fill(fill_event, fee_conversion_rates)

    # Erwartet:
    # - Base Cost: 0.01 * 57650 = 576.50 EUR
    # - Fee Cost: 0.00082344 * 700 = 0.576408 EUR
    # - Total Cost: 576.50 + 0.576408 = 577.076408 EUR
    expected_base_cost = Decimal("0.01") * Decimal("57650.00")
    expected_fee_cost = Decimal("0.00082344") * bnb_eur_price
    expected_total_cost = expected_base_cost + expected_fee_cost

    assert lot.qty_btc_initial == Decimal("0.01")
    assert lot.qty_btc_open == Decimal("0.01")
    assert abs(lot.cost_eur - expected_total_cost) < Decimal("0.01")

    # Break-even sollte höher sein als der Fill-Preis (wegen Fee)
    assert lot.break_even > Decimal("57650.00")
    # Break-even = 577.076408 / 0.01 = 57707.64 EUR
    expected_break_even = expected_total_cost / Decimal("0.01")
    assert abs(lot.break_even - expected_break_even) < Decimal("0.01")


def test_lot_creation_without_bnb_conversion_rate():
    """Test: TradeLot mit BNB Fee ohne Konvertierungsrate (Fallback)"""
    fill_event = LedgerEvent(
        id="test_fill_2",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2026, 2, 9, 12, 22),
        asset="BTC",
        amount=Decimal("0.0125"),
        symbol="BTCEUR",
        price=Decimal("58039.00"),
        side=TradeSide.BUY,
        fee_asset="BNB",
        fee_amount=Decimal("0.00103453"),
        source=EventSource.BINANCE,
        source_id="167647538",
    )

    # Kein Conversion Rate bereitgestellt
    lot = create_trade_lot_from_buy_fill(fill_event, fee_conversion_rates=None)

    # Erwartet: Base Cost ohne Fee (Fallback-Verhalten)
    # - Base Cost: 0.0125 * 58039 = 725.4875 EUR
    # - Fee Cost: 0 (keine Konvertierung)
    # - Total Cost: 725.4875 EUR
    expected_cost = Decimal("0.0125") * Decimal("58039.00")

    assert lot.qty_btc_initial == Decimal("0.0125")
    assert lot.cost_eur == expected_cost
    assert lot.break_even == Decimal("58039.00")  # Ohne Fee-Korrektur


def test_lot_creation_with_eur_fee():
    """Test: TradeLot mit EUR Fee (sollte bereits funktionieren)"""
    fill_event = LedgerEvent(
        id="test_fill_3",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2026, 2, 3, 20, 32),
        asset="BTC",
        amount=Decimal("0.0048"),
        symbol="BTCEUR",
        price=Decimal("64650.00"),
        side=TradeSide.SELL,
        fee_asset="EUR",
        fee_amount=Decimal("0.31032"),
        source=EventSource.BINANCE,
    )

    # Für Buy-Fill würde EUR-Fee zu Kosten addiert
    # Aber das ist ein Sell, also testen wir hier nur die Struktur
    # (Sell-Allocation wird separat getestet)
    pass


def test_sell_allocation_with_bnb_fee():
    """Test: Sell-Allocation mit BNB Fee"""
    # Buy: 0.01 BTC @ 50000 EUR (no fee for simplicity)
    buy_event = LedgerEvent(
        id="buy_1",
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

    # Sell: 0.01 BTC @ 55000 EUR, Fee: 0.001 BNB
    # BNB/EUR: 700 EUR
    sell_event = LedgerEvent(
        id="sell_1",
        type=EventType.TRADE_FILL,
        timestamp=datetime(2024, 1, 2, 12, 0),
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("55000.00"),
        side=TradeSide.SELL,
        fee_asset="BNB",
        fee_amount=Decimal("0.001"),
        source=EventSource.BINANCE,
    )

    bnb_eur_price = Decimal("700.00")
    fee_conversion_rates = {"BNB": bnb_eur_price}

    updated_lots, allocations = allocate_sell_fifo(
        sell_event,
        [lot],
        fee_conversion_rates
    )

    # Erwartet:
    # - Gross Proceeds: 0.01 * 55000 = 550 EUR
    # - Fee: 0.001 * 700 = 0.7 EUR
    # - Net Proceeds: 550 - 0.7 = 549.3 EUR
    # - Cost: 500 EUR
    # - Realized P&L: 549.3 - 500 = 49.3 EUR

    assert len(allocations) == 1
    allocation = allocations[0]

    expected_proceeds = Decimal("55000.00") * Decimal("0.01")
    expected_fee = Decimal("0.001") * bnb_eur_price
    expected_net_proceeds = expected_proceeds - expected_fee
    expected_cost = Decimal("50000.00") * Decimal("0.01")
    expected_pnl = expected_net_proceeds - expected_cost

    assert abs(allocation.realized_pnl_eur - expected_pnl) < Decimal("0.01")
    assert allocation.qty_allocated == Decimal("0.01")

    # Lot sollte geschlossen sein
    assert updated_lots[0].qty_btc_open == Decimal("0")


def test_multiple_fee_assets_in_batch():
    """Test: Batch mit verschiedenen Fee-Assets"""
    events = [
        # BNB Fee
        LedgerEvent(
            id="fill_1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            fee_asset="BNB",
            fee_amount=Decimal("0.001"),
            source=EventSource.BINANCE,
        ),
        # EUR Fee
        LedgerEvent(
            id="fill_2",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 2),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("51000.00"),
            side=TradeSide.BUY,
            fee_asset="EUR",
            fee_amount=Decimal("1.00"),
            source=EventSource.BINANCE,
        ),
        # BTC Fee
        LedgerEvent(
            id="fill_3",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 3),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("52000.00"),
            side=TradeSide.BUY,
            fee_asset="BTC",
            fee_amount=Decimal("0.00001"),
            source=EventSource.BINANCE,
        ),
    ]

    bnb_eur_price = Decimal("700.00")
    fee_conversion_rates = {"BNB": bnb_eur_price}

    lots = []
    for event in events:
        lot = create_trade_lot_from_buy_fill(event, fee_conversion_rates)
        lots.append(lot)

    # Alle Lots sollten erstellt sein mit korrekten Kosten
    assert len(lots) == 3

    # Lot 1 (BNB Fee): 500 + (0.001 * 700) = 500.7 EUR, qty = 0.01 (BNB-Fee betrifft BTC nicht)
    assert abs(lots[0].cost_eur - Decimal("500.70")) < Decimal("0.01")
    assert lots[0].qty_btc_initial == Decimal("0.01")

    # Lot 2 (EUR Fee): 510 + 1 = 511 EUR, qty = 0.01 (EUR-Fee betrifft BTC nicht)
    assert lots[1].cost_eur == Decimal("511.00")
    assert lots[1].qty_btc_initial == Decimal("0.01")

    # Lot 3 (BTC Fee): cost = 0.01 * 52000 = 520 EUR (KEINE Fee-Addition!)
    # qty = 0.01 - 0.00001 = 0.00999 (Fee von BTC-Menge abgezogen)
    assert lots[2].cost_eur == Decimal("520.00")
    assert lots[2].qty_btc_initial == Decimal("0.00999")
