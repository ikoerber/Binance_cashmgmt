"""
Unit Tests für Pairing Logic

Testet virtuelle Lot-Bündelung für Netto-Zielmarge.
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
    PairingStatus,
)
from app.domain.lots import create_trade_lot_from_buy_fill
from app.domain.pairing import suggest_pairings, simulate_pairing


def _create_buy_event(event_id: str, qty: str, price: str, timestamp: datetime):
    """Helper: Erstellt Buy-Event"""
    return LedgerEvent(
        id=event_id,
        type=EventType.TRADE_FILL,
        timestamp=timestamp,
        asset="BTC",
        amount=Decimal(qty),
        symbol="BTCEUR",
        price=Decimal(price),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
    )


def test_pairing_single_winner_no_losers():
    """Test: Nur Gewinner, keine Verlierer → kein Pairing (Minimum 2 Lots)"""
    # Buy @ 50k
    buy_event = _create_buy_event("fill_1", "0.01", "50000", datetime(2024, 1, 1))
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Marktpreis: 55k (Gewinn!)
    market_price = Decimal("55000")

    pairings = suggest_pairings([lot], market_price, threshold_pct=Decimal("0.05"))

    # Erwartet: Kein Pairing — einzelnes Lot kann direkt per Sell-Order verkauft werden
    assert len(pairings) == 0


def test_pairing_no_winners():
    """Test: Nur Verlierer → keine Pairings möglich"""
    # Buy @ 50k
    buy_event = _create_buy_event("fill_1", "0.01", "50000", datetime(2024, 1, 1))
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Marktpreis: 45k (Verlust)
    market_price = Decimal("45000")

    pairings = suggest_pairings([lot], market_price)

    assert len(pairings) == 0


def test_pairing_one_winner_one_loser_not_combinable():
    """Test: Gewinner + Verlierer, aber kombiniert unter Threshold → kein Pairing"""
    # Lot 1: Buy @ 50k
    buy1 = _create_buy_event("fill_1", "0.01", "50000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy @ 60k (teurer)
    buy2 = _create_buy_event("fill_2", "0.01", "60000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    # Marktpreis: 55k
    # Lot1: +10% Gewinn, Lot2: -8.33% Verlust
    # Kombiniert: (550 + 550) - (500 + 600) = 0% → unter Threshold
    # Einzelnes Lot1 allein → kein Pairing (Minimum 2 Lots)
    market_price = Decimal("55000")

    pairings = suggest_pairings(
        [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
    )

    # Erwartet: Kein Pairing — Lot2 senkt den P&L% unter Threshold,
    # und ein einzelnes Lot ergibt kein Pairing
    assert len(pairings) == 0


def test_pairing_two_winners_no_losers():
    """Test: Zwei Gewinner, keine Verlierer → kein Pairing (kein Verlierer zum Kombinieren)"""
    # Lot 1: Buy @ 50k
    buy1 = _create_buy_event("fill_1", "0.01", "50000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy @ 52k (leicht teurer)
    buy2 = _create_buy_event("fill_2", "0.01", "52000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    # Marktpreis: 55k
    # Lot1: 10% Gewinn, Lot2: 5.77% Gewinn → beide profitabel, aber keine Verlierer
    market_price = Decimal("55000")

    pairings = suggest_pairings(
        [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
    )

    # Erwartet: Kein Pairing — einzelne profitable Lots direkt per Sell-Order verkaufbar
    # Minimum 2 Lots pro Pairing, aber keine Verlierer zum Kombinieren
    assert len(pairings) == 0


def test_pairing_multiple_losers():
    """Test: Ein Gewinner + mehrere Verlierer"""
    # Lot 1: Buy @ 40k (großer Gewinner)
    buy1 = _create_buy_event("fill_1", "0.01", "40000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy @ 55k (Verlierer)
    buy2 = _create_buy_event("fill_2", "0.005", "55000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    # Lot 3: Buy @ 58k (größerer Verlierer)
    buy3 = _create_buy_event("fill_3", "0.005", "58000", datetime(2024, 1, 3))
    lot3 = create_trade_lot_from_buy_fill(buy3)

    # Marktpreis: 50k
    # Lot1: +25% Gewinn
    # Lot2: -9.09% Verlust
    # Lot3: -13.79% Verlust
    market_price = Decimal("50000")

    pairings = suggest_pairings(
        [lot1, lot2, lot3], market_price, threshold_pct=Decimal("0.05")
    )

    # Erwartet: Ein Pairing mit allen 3 Lots
    # cost = 400 + 275 + 290 = 965
    # value = 0.01*50000 + 0.005*50000 + 0.005*50000 = 500 + 250 + 250 = 1000
    # pnl = 1000 - 965 = 35
    # pnl% = 35 / 965 ≈ 3.63%
    # Das ist < 5%, also kein Pairing

    # Aber vielleicht nur Lot1 + Lot2?
    # cost = 400 + 275 = 675
    # value = 500 + 250 = 750
    # pnl = 750 - 675 = 75
    # pnl% = 75 / 675 ≈ 11.11% → OK!

    assert len(pairings) >= 1
    # Finde Pairing mit lot1
    pairing_with_lot1 = next(
        (p for p in pairings if any(i.lot_id == lot1.id for i in p.items)), None
    )
    assert pairing_with_lot1 is not None
    assert pairing_with_lot1.net_pnl_pct(market_price) >= Decimal("0.05")


def test_pairing_simulation():
    """Test: Simulation eines Pairings mit Gewinner + Verlierer"""
    # Lot 1: Buy @ 40k (grosser Gewinner)
    buy1 = _create_buy_event("fill_1", "0.01", "40000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy @ 52k (leichter Verlierer)
    buy2 = _create_buy_event("fill_2", "0.01", "52000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    # Marktpreis: 50k
    # Lot1: +25%, Lot2: -3.85%
    # Kombiniert: (500+500)-(400+520) = 80, pnl% = 80/920 ≈ 8.7% → ueber 5%
    market_price = Decimal("50000")

    pairings = suggest_pairings(
        [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
    )
    assert len(pairings) >= 1

    pairing = pairings[0]
    assert len(pairing.items) >= 2

    # Simulation
    simulation = simulate_pairing(
        pairing, market_price, all_lots=[lot1, lot2], fee_pct=Decimal("0.001")
    )

    total_base_in_pairing = pairing.net_qty_base()
    assert simulation.total_base_to_sell == total_base_in_pairing

    # Affected lots = Items im Pairing
    assert len(simulation.affected_lots) == len(pairing.items)

    # P&L sollte positiv sein
    assert simulation.expected_realized_pnl_eur > 0


def test_pairing_simulation_with_losers():
    """Test: Simulation mit Gewinner + Verlierer (mehrere Lots)"""
    # Lot 1: Buy 0.02 BTC @ 40k (grosser Gewinner)
    buy1 = _create_buy_event("fill_1", "0.02", "40000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy 0.01 BTC @ 52k (leichter Verlierer)
    buy2 = _create_buy_event("fill_2", "0.01", "52000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    # Marktpreis: 50k
    # Lot1: +25%, Lot2: -3.85%
    # Kombiniert: (1000+500)-(800+520) = 180, pnl% = 180/1320 ≈ 13.6%
    market_price = Decimal("50000")

    pairings = suggest_pairings(
        [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
    )
    assert len(pairings) > 0

    pairing = pairings[0]
    assert len(pairing.items) >= 2

    simulation = simulate_pairing(
        pairing, market_price, all_lots=[lot1, lot2], fee_pct=Decimal("0.001")
    )

    # Total BTC zu verkaufen = alle Items im Pairing
    expected_base = sum(item.qty_base for item in pairing.items)
    assert simulation.total_base_to_sell == expected_base

    # Falls alle Lots komplett im Pairing:
    if simulation.total_base_to_sell == Decimal("0.03"):
        assert simulation.remaining_portfolio_base == Decimal("0")


def test_pairing_net_calculations():
    """Test: Netto-Berechnungen eines Pairings mit Gewinner + Verlierer"""
    # Lot 1: Buy @ 50k (Gewinner bei 56k → +12%)
    buy1 = _create_buy_event("fill_1", "0.01", "50000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy @ 56k (Verlierer bei 56k → ±0%)
    buy2 = _create_buy_event("fill_2", "0.01", "56000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    market_price = Decimal("56000")

    # Kombiniert: (560+560)-(500+560) = 60, pnl% = 60/1060 ≈ 5.66% → ueber 1%
    pairings = suggest_pairings(
        [lot1, lot2], market_price, threshold_pct=Decimal("0.01")
    )
    assert len(pairings) >= 1

    # Pairing muss mindestens 2 Lots enthalten
    pairing = next((p for p in pairings if len(p.items) >= 2), None)
    assert pairing is not None

    # Net cost
    actual_cost = pairing.net_cost()
    assert actual_cost > 0

    # Net qty
    actual_qty = pairing.net_qty_base()
    assert actual_qty > 0

    # Net value @ 56k
    actual_value = pairing.net_value(market_price)
    assert actual_value == actual_qty * market_price

    # Net P&L
    actual_pnl = pairing.net_pnl(market_price)
    assert actual_pnl == actual_value - actual_cost

    # Net P&L %
    actual_pnl_pct = pairing.net_pnl_pct(market_price)
    assert actual_pnl_pct == actual_pnl / actual_cost


def test_pairing_threshold_check_single_lot():
    """Test: Einzelnes Lot ergibt kein Pairing (Minimum 2 Lots)"""
    # Lot: Buy @ 50k
    buy_event = _create_buy_event("fill_1", "0.01", "50000", datetime(2024, 1, 1))
    lot = create_trade_lot_from_buy_fill(buy_event)

    # Marktpreis: 52.5k → genau 5% Gewinn, aber nur 1 Lot
    market_price = Decimal("52500")

    pairings = suggest_pairings([lot], market_price, threshold_pct=Decimal("0.05"))

    # Kein Pairing — einzelnes Lot direkt per Sell-Order verkaufbar
    assert len(pairings) == 0


def test_pairing_threshold_check_combined():
    """Test: Threshold-Pruefung mit Gewinner + Verlierer"""
    # Lot 1: Buy @ 40k (Gewinner)
    buy1 = _create_buy_event("fill_1", "0.01", "40000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy @ 48k (leichter Verlierer)
    buy2 = _create_buy_event("fill_2", "0.01", "48000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    # Marktpreis: 46.2k
    # Lot1: (46200-40000)/40000 = 15.5% Gewinn
    # Lot2: (46200-48000)/48000 = -3.75% Verlust
    # Kombiniert: (462+462)-(400+480) = 44, pnl% = 44/880 = 5% → genau Threshold
    market_price = Decimal("46200")

    pairings = suggest_pairings(
        [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
    )

    assert len(pairings) == 1
    pairing = pairings[0]
    assert len(pairing.items) == 2
    assert pairing.is_profitable(market_price)
    assert pairing.net_pnl_pct(market_price) >= Decimal("0.05")


def test_pairing_simulation_with_custom_sell_price():
    """Test: Simulation mit sell_price berechnet P&L basierend auf Verkaufspreis"""
    # Lot 1: Buy @ 40k (Gewinner)
    buy1 = _create_buy_event("fill_1", "0.01", "40000", datetime(2024, 1, 1))
    lot1 = create_trade_lot_from_buy_fill(buy1)

    # Lot 2: Buy @ 52k (Verlierer)
    buy2 = _create_buy_event("fill_2", "0.01", "52000", datetime(2024, 1, 2))
    lot2 = create_trade_lot_from_buy_fill(buy2)

    market_price = Decimal("50000")
    fee_pct = Decimal("0.001")

    pairings = suggest_pairings(
        [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
    )
    assert len(pairings) >= 1
    pairing = pairings[0]

    # Simulation ohne sell_price (Default: market_price)
    sim_default = simulate_pairing(pairing, market_price, [lot1, lot2], fee_pct)

    # Simulation mit hoeherem sell_price
    custom_sell_price = Decimal("51000")
    sim_custom = simulate_pairing(
        pairing, market_price, [lot1, lot2], fee_pct, sell_price=custom_sell_price
    )

    # P&L muss bei hoeherem Verkaufspreis hoeher sein
    assert sim_custom.expected_realized_pnl_eur > sim_default.expected_realized_pnl_eur

    # Erloese pruefen: total_base * sell_price - fees
    total_base = pairing.net_qty_base()
    expected_gross = total_base * custom_sell_price
    expected_fee = expected_gross * fee_pct
    expected_proceeds = expected_gross - expected_fee
    assert sim_custom.expected_proceeds_eur == expected_proceeds

    # market_price bleibt unveraendert (fuer Display)
    assert sim_custom.market_price == market_price
