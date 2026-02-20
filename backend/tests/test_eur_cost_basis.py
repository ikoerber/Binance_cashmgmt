"""
Tests for EUR Cost Basis Domain Logic

Tests that every TradeLot gets a deterministic EUR cost basis:
- EUR-quoted lots: cost_eur = cost_quote, rate = 1.0
- BTC-quoted lots with rate: cost_eur = cost_quote * rate
- BTC-quoted lots without rate: cost_eur = None (needs backfill)
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


# ─── Helpers ────────────────────────────────────────────────────────────


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


# ─── EUR-quoted lots (auto-detect cost_eur) ────────────────────────────


class TestEurQuotedLots:
    """EUR-quoted lots should auto-compute cost_eur = cost_quote, rate = 1.0"""

    def test_btceur_auto_detects_eur(self):
        """BTCEUR lot: cost_eur = cost_quote, rate = Decimal('1')"""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.cost_eur == Decimal("900.00")
        assert lot.quote_to_eur_rate == Decimal("1")

    def test_xrpeur_auto_detects_eur(self):
        """XRPEUR lot: cost_eur = cost_quote, rate = Decimal('1')"""
        fill = _buy_fill(symbol="XRPEUR", price="2.50", amount="100")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.cost_eur == Decimal("250.00")
        assert lot.quote_to_eur_rate == Decimal("1")

    def test_eur_quoted_break_even_eur(self):
        """break_even_eur equals break_even for EUR-quoted lots."""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.break_even_eur == Decimal("90000")

    def test_eur_quoted_no_rate_param_needed(self):
        """EUR-quoted lots do NOT require quote_to_eur_rate parameter."""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        # Call without quote_to_eur_rate -- should still set cost_eur
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.cost_eur is not None
        assert lot.quote_to_eur_rate == Decimal("1")


# ─── BTC-quoted lots with provided rate ─────────────────────────────────


class TestBtcQuotedLotsWithRate:
    """BTC-quoted lots with quote_to_eur_rate should compute cost_eur correctly."""

    def test_xrpbtc_with_rate(self):
        """XRPBTC lot with rate: cost_eur = cost_quote * rate"""
        fill = _buy_fill(symbol="XRPBTC", price="0.00003", amount="100")
        lot = create_trade_lot_from_buy_fill(fill, quote_to_eur_rate=Decimal("90000"))

        # cost_quote = 0.00003 * 100 = 0.003 BTC
        # cost_eur = 0.003 * 90000 = 270.00
        assert lot.cost_eur == Decimal("270.000")
        assert lot.quote_to_eur_rate == Decimal("90000")

    def test_xrpbtc_break_even_eur(self):
        """break_even_eur for BTC-quoted lot with rate."""
        fill = _buy_fill(symbol="XRPBTC", price="0.00003", amount="100")
        lot = create_trade_lot_from_buy_fill(fill, quote_to_eur_rate=Decimal("90000"))

        # break_even_eur = cost_eur / qty_base_initial = 270 / 100 = 2.70
        assert lot.break_even_eur == Decimal("2.700")


# ─── BTC-quoted lots without rate (needs backfill) ──────────────────────


class TestBtcQuotedLotsWithoutRate:
    """BTC-quoted lots without rate should have cost_eur = None."""

    def test_xrpbtc_no_rate(self):
        """XRPBTC lot without rate: cost_eur = None, rate = None"""
        fill = _buy_fill(symbol="XRPBTC", price="0.00003", amount="100")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.cost_eur is None
        assert lot.quote_to_eur_rate is None

    def test_xrpbtc_no_rate_break_even_eur_is_none(self):
        """break_even_eur = None when cost_eur is None."""
        fill = _buy_fill(symbol="XRPBTC", price="0.00003", amount="100")
        lot = create_trade_lot_from_buy_fill(fill)

        assert lot.break_even_eur is None


# ─── break_even_eur edge cases ──────────────────────────────────────────


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
            quote_to_eur_rate=Decimal("1"),
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
            quote_to_eur_rate=None,
            status=LotStatus.OPEN,
        )
        assert lot.break_even_eur is None


# ─── Fee handling combined with EUR cost basis ──────────────────────────


class TestFeeHandlingWithEurCostBasis:
    """Fee handling correctly reflects in cost_eur."""

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
        assert lot.quote_to_eur_rate == Decimal("1")

    def test_btc_quoted_with_base_asset_fee(self):
        """XRPBTC with XRP fee: qty reduced, cost_eur based on reduced qty."""
        fill = _buy_fill(
            symbol="XRPBTC",
            price="0.00003",
            amount="100",
            fee_asset="XRP",
            fee_amount="0.10",
        )
        lot = create_trade_lot_from_buy_fill(fill, quote_to_eur_rate=Decimal("90000"))

        # qty_net = 100 - 0.10 = 99.90
        assert lot.qty_base_initial == Decimal("99.90")
        # cost_quote = 0.00003 * 100 = 0.003 BTC (full amount at price)
        assert lot.cost_quote == Decimal("0.00300")
        # cost_eur = 0.003 * 90000 = 270.00
        assert lot.cost_eur == Decimal("270.000")
        assert lot.quote_to_eur_rate == Decimal("90000")

    def test_btc_quoted_with_bnb_fee_and_rate(self):
        """XRPBTC with BNB fee and rate: cost_eur includes BNB fee converted to BTC then EUR."""
        fill = _buy_fill(
            symbol="XRPBTC",
            price="0.00003",
            amount="100",
            fee_asset="BNB",
            fee_amount="0.001",
            fee_quote_value="0.0000005",  # BNB fee in BTC (quote currency for XRPBTC)
        )
        lot = create_trade_lot_from_buy_fill(fill, quote_to_eur_rate=Decimal("90000"))

        # cost_quote = 0.00003 * 100 + 0.0000005 = 0.0030005 BTC
        assert lot.cost_quote == Decimal("0.0030005")
        # cost_eur = 0.0030005 * 90000 = 270.045
        assert lot.cost_eur == Decimal("270.0450000")
        assert lot.quote_to_eur_rate == Decimal("90000")


# ─── Backward compatibility ─────────────────────────────────────────────


class TestBackwardCompatibility:
    """Existing callers without quote_to_eur_rate param still work."""

    def test_existing_btceur_call_unchanged(self):
        """Existing BTCEUR lot creation (no new param) still works."""
        fill = _buy_fill(symbol="BTCEUR", price="90000", amount="0.01")
        lot = create_trade_lot_from_buy_fill(fill)

        # All existing fields still correct
        assert lot.cost_quote == Decimal("900.00")
        assert lot.qty_base_initial == Decimal("0.01")
        assert lot.break_even == Decimal("90000")
        assert lot.status == LotStatus.OPEN
        # New fields populated automatically for EUR-quoted
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
