"""
Unit Tests für Portfolio Break-even Berechnung

Testet die Kern-Business-Logik ohne DB/API.
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
from app.domain.portfolio import compute_portfolio_from_ledger, calculate_target_price


def test_portfolio_empty_ledger():
    """Test: Leeres Ledger ergibt Null-Portfolio"""
    portfolio = compute_portfolio_from_ledger([])

    assert portfolio.base_qty == Decimal("0")
    assert portfolio.base_cost_basis_eur == Decimal("0")
    assert portfolio.eur_available == Decimal("0")
    assert portfolio.realized_pnl_eur == Decimal("0")
    assert portfolio.break_even is None


def test_portfolio_single_buy_no_fee():
    """Test: Einfacher Buy ohne Fee"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),  # Gekaufte BTC
            symbol="BTCEUR",
            price=Decimal("50000.00"),  # 50k EUR pro BTC
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        )
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet: 0.01 BTC für 500 EUR gekauft
    assert portfolio.base_qty == Decimal("0.01")
    assert portfolio.base_cost_basis_eur == Decimal("500.00")
    assert portfolio.break_even == Decimal("50000.00")
    assert portfolio.eur_available == Decimal("-500.00")  # EUR ausgegeben


def test_portfolio_buy_with_eur_fee():
    """Test: Buy mit EUR Fee"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            symbol="BTCEUR",
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            fee_asset="EUR",
            fee_amount=Decimal("1.00"),  # 1 EUR Fee
            source=EventSource.BINANCE,
        )
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet: 0.01 BTC, Kosten = 500 + 1 = 501 EUR
    assert portfolio.base_qty == Decimal("0.01")
    assert portfolio.base_cost_basis_eur == Decimal("501.00")
    assert portfolio.break_even == Decimal("50100.00")  # 501 / 0.01


def test_portfolio_buy_with_btc_fee():
    """Test: Buy mit BTC Fee - qty ist BRUTTO, Fee wird abgezogen"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),  # BRUTTO von Binance (VOR Fee-Abzug)
            symbol="BTCEUR",
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            fee_asset="BTC",
            fee_amount=Decimal("0.00001"),  # BTC Fee
            source=EventSource.BINANCE,
        )
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet:
    # - qty = 0.01 - 0.00001 = 0.00999 (BRUTTO minus Fee)
    # - Kosten = 50000 * 0.01 = 500.00 EUR (nur EUR tatsächlich bezahlt)
    # - Break-even = 500 / 0.00999 ≈ 50050.05
    assert portfolio.base_qty == Decimal("0.00999")
    assert portfolio.base_cost_basis_eur == Decimal("500.00")
    expected_be = Decimal("500.00") / Decimal("0.00999")
    assert abs(portfolio.break_even - expected_be) < Decimal("0.01")


def test_portfolio_multiple_buys_wac():
    """Test: Mehrere Buys → Weighted Average Cost"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
        LedgerEvent(
            id="2",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 2, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("60000.00"),  # Teurer gekauft
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet:
    # - qty = 0.02 BTC
    # - Kosten = 500 + 600 = 1100 EUR
    # - Break-even = 1100 / 0.02 = 55000 EUR
    assert portfolio.base_qty == Decimal("0.02")
    assert portfolio.base_cost_basis_eur == Decimal("1100.00")
    assert portfolio.break_even == Decimal("55000.00")


def test_portfolio_buy_then_sell_partial():
    """Test: Buy dann Partial Sell → Realisierte P&L"""
    events = [
        # Buy: 0.01 BTC @ 50k
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
        # Sell: 0.005 BTC @ 55k (Gewinn!)
        LedgerEvent(
            id="2",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 2, 12, 0),
            asset="BTC",
            amount=Decimal("0.005"),
            price=Decimal("55000.00"),
            side=TradeSide.SELL,
            source=EventSource.BINANCE,
        ),
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet:
    # - Restliche qty = 0.005 BTC
    # - Break-even war 50k, verkauft zu 55k
    # - Erlös = 0.005 * 55000 = 275 EUR
    # - Kosten des Verkauften = 0.005 * 50000 = 250 EUR
    # - Realisierte P&L = 275 - 250 = 25 EUR
    # - Verbleibende Kostenbasis = 500 - 250 = 250 EUR
    assert portfolio.base_qty == Decimal("0.005")
    assert portfolio.base_cost_basis_eur == Decimal("250.00")
    assert portfolio.realized_pnl_eur == Decimal("25.00")
    assert portfolio.eur_available == Decimal("-225.00")  # -500 (buy) + 275 (sell)


def test_portfolio_buy_then_sell_with_fee():
    """Test: Sell mit EUR Fee"""
    events = [
        # Buy: 0.01 BTC @ 50k
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
        # Sell: 0.01 BTC @ 55k, Fee 1 EUR
        LedgerEvent(
            id="2",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 2, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("55000.00"),
            side=TradeSide.SELL,
            fee_asset="EUR",
            fee_amount=Decimal("1.00"),
            source=EventSource.BINANCE,
        ),
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet:
    # - Erlös brutto = 550 EUR
    # - Fee = 1 EUR
    # - Erlös netto = 549 EUR
    # - Kosten = 500 EUR
    # - P&L = 549 - 500 = 49 EUR
    assert portfolio.base_qty == Decimal("0")
    assert portfolio.realized_pnl_eur == Decimal("49.00")


def test_portfolio_external_cashflow():
    """Test: Externe Cashflows beeinflussen nicht BTC-Kostenbasis"""
    events = [
        # Buy: 0.01 BTC @ 50k
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
        # Externe Einzahlung: 1000 EUR von Bank
        LedgerEvent(
            id="2",
            type=EventType.EXTERNAL_CASHFLOW,
            timestamp=datetime(2024, 1, 2, 12, 0),
            asset="EUR",
            amount=Decimal("1000.00"),
            source=EventSource.EXTERNAL,
            note="Bank transfer in",
        ),
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet:
    # - BTC-Kostenbasis bleibt 500 EUR (unverändert)
    # - External Net = 1000 EUR
    assert portfolio.base_qty == Decimal("0.01")
    assert portfolio.base_cost_basis_eur == Decimal("500.00")
    assert portfolio.break_even == Decimal("50000.00")
    assert portfolio.external_net_eur == Decimal("1000.00")


def test_calculate_target_price():
    """Test: Zielpreis-Berechnung"""
    break_even = Decimal("50000.00")
    target_margin = Decimal("0.05")  # 5%

    # Ohne Fee-Buffer
    target = calculate_target_price(break_even, target_margin)
    assert target == Decimal("52500.00")  # 50k * 1.05

    # Mit Fee-Buffer (0.2%)
    target_with_buffer = calculate_target_price(
        break_even, target_margin, fee_buffer_pct=Decimal("0.002")
    )
    expected = Decimal("50000") * Decimal("1.05") * Decimal("1.002")
    assert abs(target_with_buffer - expected) < Decimal("0.01")


def test_portfolio_state_unrealized_pnl():
    """Test: Unrealisierte P&L Berechnung"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Marktpreis steigt auf 55k
    market_price = Decimal("55000.00")
    unrealized = portfolio.unrealized_pnl_eur(market_price)

    # Erwartet: (55000 * 0.01) - 500 = 50 EUR Gewinn
    assert unrealized == Decimal("50.00")

    # Marktpreis fällt auf 45k
    market_price_down = Decimal("45000.00")
    unrealized_loss = portfolio.unrealized_pnl_eur(market_price_down)

    # Erwartet: (45000 * 0.01) - 500 = -50 EUR Verlust
    assert unrealized_loss == Decimal("-50.00")


def test_portfolio_buy_with_bnb_fee():
    """Test: Buy mit BNB Fee - EUR-Wert der Fee erhoeht Kostenbasis"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            symbol="BTCEUR",
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            fee_asset="BNB",
            fee_amount=Decimal("0.001"),
            fee_eur_value=Decimal("0.70"),  # 0.001 BNB * 700 EUR/BNB
            source=EventSource.BINANCE,
        )
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erwartet:
    # - qty = 0.01 BTC (BNB fee reduziert BTC-Menge NICHT)
    # - cost = 500.00 + 0.70 = 500.70 EUR
    # - break_even = 500.70 / 0.01 = 50070.00
    assert portfolio.base_qty == Decimal("0.01")
    assert portfolio.base_cost_basis_eur == Decimal("500.70")
    assert portfolio.break_even == Decimal("50070.00")


def test_portfolio_buy_with_bnb_fee_no_eur_value():
    """Test: Buy mit BNB Fee ohne fee_eur_value - graceful degradation"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            symbol="BTCEUR",
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            fee_asset="BNB",
            fee_amount=Decimal("0.001"),
            # fee_eur_value ist None (historische Daten nicht verfuegbar)
            source=EventSource.BINANCE,
        )
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Ohne fee_eur_value wird BNB-Fee ignoriert (graceful degradation)
    assert portfolio.base_qty == Decimal("0.01")
    assert portfolio.base_cost_basis_eur == Decimal("500.00")


def test_portfolio_sell_with_bnb_fee():
    """Test: Sell mit BNB Fee - EUR-Wert der Fee reduziert Erloes"""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000.00"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
        LedgerEvent(
            id="2",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 2, 12, 0),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("55000.00"),
            side=TradeSide.SELL,
            fee_asset="BNB",
            fee_amount=Decimal("0.001"),
            fee_eur_value=Decimal("0.70"),
            source=EventSource.BINANCE,
        ),
    ]

    portfolio = compute_portfolio_from_ledger(events)

    # Erlos: 550.00 - 0.70 (BNB fee) = 549.30
    # Kosten: 500.00
    # P&L: 49.30
    assert portfolio.realized_pnl_eur == Decimal("49.30")
