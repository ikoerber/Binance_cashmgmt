"""
Tests for EUR Cost Basis Domain Logic

Tests that every EUR-quoted TradeLot gets a deterministic EUR cost basis:
- EUR-quoted lots: cost_eur = cost_quote (auto-detected)
- break_even_eur property
- Fee handling combined with EUR cost basis
- Backward compatibility
"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.domain.models import (
    LedgerEvent,
    EventType,
    TradeSide,
    EventSource,
    TradeLot,
    LotStatus,
)
from app.domain.lots import create_trade_lot_from_buy_fill


# --- Helpers ----------------------------------------------------------------


def _buy_fill(
    symbol: str = "BTCEUR",
    price: str = "90000",
    amount: str = "0.01",
    fee_asset: str | None = None,
    fee_amount: str | None = None,
    fee_quote_value: str | None = None,
    fill_id: str = "fill_1",
) -> LedgerEvent:
    """Create a buy fill LedgerEvent for testing."""
    return LedgerEvent(
        id=fill_id,
        type=EventType.TRADE_FILL,
        timestamp=datetime(2025, 6, 15, 12, 0, 0),
        asset="BTC",
        amount=Decimal(amount),
        symbol=symbol,
        price=Decimal(price),
        side=TradeSide.BUY,
        fee_asset=fee_asset,
        fee_amount=Decimal(fee_amount) if fee_amount else None,
        fee_quote_value=Decimal(fee_quote_value) if fee_quote_value else None,
        source=EventSource.BINANCE,
    )


# --- EUR-quoted lots (auto-detect cost_eur) ---------------------------------


class TestEurQuotedLots:
    """EUR-quoted lots should auto-compute cost_eur = cost_quote."""

    def test_btceur_auto_detects_eur(self):
        """BTCEUR lot: cost_eur = cost_quote."""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.cost_eur == Decimal("900.00")

    def test_xrpeur_auto_detects_eur(self):
        """XRPEUR lot: cost_eur = cost_quote."""
        fill = _buy_fill(symbol="XRPEUR", price="2.50", amount="100")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.cost_eur == Decimal("250.00")

    def test_eur_quoted_break_even_eur(self):
        """break_even_eur equals break_even for EUR-quoted lots."""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.break_even_eur == Decimal("90000")

    def test_eur_quoted_no_rate_param_needed(self):
        """EUR-quoted lots do NOT require any extra parameter for cost_eur."""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.cost_eur is not None


# --- break_even_eur edge cases ----------------------------------------------


class TestBreakEvenEurEdgeCases:
    """Edge cases for break_even_eur property."""

    def test_break_even_eur_with_zero_qty(self):
        """break_even_eur = None when qty_base_initial == 0."""
        lot = TradeLot(
            id="lot_test",
            created_from_fill_id="fill_test",
            created_at=datetime(2025, 6, 15),
            qty_base_initial=Decimal("0"),
            qty_base_open=Decimal("0"),
            cost_quote=Decimal("100"),
            cost_eur=Decimal("100"),
            status=LotStatus.CLOSED,
        )
        assert lot.break_even_eur is None

    def test_break_even_eur_with_none_cost_eur(self):
        """break_even_eur = None when cost_eur is None."""
        lot = TradeLot(
            id="lot_test",
            created_from_fill_id="fill_test",
            created_at=datetime(2025, 6, 15),
            qty_base_initial=Decimal("100"),
            qty_base_open=Decimal("100"),
            cost_quote=Decimal("0.003"),
            cost_eur=None,
            status=LotStatus.OPEN,
        )
        assert lot.break_even_eur is None


# --- Fee handling combined with EUR cost basis -------------------------------


class TestFeeHandlingWithEurCostBasis:
    """Fee handling correctly reflects in cost_eur for EUR-quoted lots."""

    def test_eur_quoted_with_bnb_fee(self):
        """BTCEUR with BNB fee: cost_eur includes fee in cost_quote."""
        fill = _buy_fill(
            symbol="BTCEUR",
            price="90000",
            amount="0.01",
            fee_asset="BNB",
            fee_amount="0.001",
            fee_quote_value="0.70",
        )
        lot = create_trade_lot_from_buy_fill(fill)

        # cost_quote = 90000 * 0.01 + 0.70 (BNB fee in EUR) = 900.70
        assert lot.cost_quote == Decimal("900.70")
        assert lot.cost_eur == Decimal("900.70")


# --- Backward compatibility -------------------------------------------------


class TestBackwardCompatibility:
    """Existing callers without extra params still work."""

    def test_existing_btceur_call_unchanged(self):
        """Existing BTCEUR lot creation (no new param) still works."""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        lot = create_trade_lot_from_buy_fill(fill)

        # All existing fields still correct
        assert lot.cost_quote == Decimal("900.00")
        assert lot.qty_base_initial == Decimal("0.01")
        assert lot.break_even == Decimal("90000")
        assert lot.status == LotStatus.OPEN
        # cost_eur populated automatically for EUR-quoted
        assert lot.cost_eur is not None

    def test_existing_btceur_with_fee_conversion_rates(self):
        """Existing call with fee_conversion_rates still works."""
        fill = _buy_fill(
            symbol="BTCEUR",
            price="90000",
            amount="0.01",
            fee_asset="BNB",
            fee_amount="0.001",
        )
        lot = create_trade_lot_from_buy_fill(
            fill, fee_conversion_rates={"BNB": Decimal("700")}
        )

        # cost_quote = 900 + 0.70 = 900.70
        assert lot.cost_quote == Decimal("900.70")
        # EUR-quoted -> cost_eur = cost_quote
        assert lot.cost_eur == Decimal("900.70")
