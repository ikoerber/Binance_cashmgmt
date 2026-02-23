"""
Tests fuer Binance Exchange Filter Validierung (LOT_SIZE, PRICE_FILTER, NOTIONAL).

Pure Domain-Tests -- kein I/O, keine Binance API Calls.
"""
from decimal import Decimal

import pytest

from app.domain.orders import (
    SymbolFilters,
    parse_symbol_filters,
    round_qty_to_step_size,
    round_price_to_tick_size,
    validate_order_filters,
)


# --- Fixtures ---


@pytest.fixture
def btceur_filters():
    """Typische BTCEUR Exchange Filters."""
    return SymbolFilters(
        min_qty=Decimal("0.00001"),
        max_qty=Decimal("9000"),
        step_size=Decimal("0.00001"),
        min_price=Decimal("0.01"),
        max_price=Decimal("1000000"),
        tick_size=Decimal("0.01"),
        min_notional=Decimal("5"),
    )


@pytest.fixture
def raw_binance_filters():
    """Rohe Binance exchangeInfo Filter-Liste."""
    return [
        {
            "filterType": "PRICE_FILTER",
            "minPrice": "0.01000000",
            "maxPrice": "1000000.00000000",
            "tickSize": "0.01000000",
        },
        {
            "filterType": "LOT_SIZE",
            "minQty": "0.00001000",
            "maxQty": "9000.00000000",
            "stepSize": "0.00001000",
        },
        {
            "filterType": "NOTIONAL",
            "minNotional": "5.00000000",
            "applyMinToMarket": True,
            "maxNotional": "9000000.00000000",
            "applyMaxToMarket": False,
            "avgPriceMins": 5,
        },
        {
            "filterType": "ICEBERG_PARTS",
            "limit": 10,
        },
    ]


# --- parse_symbol_filters ---


class TestParseSymbolFilters:
    def test_parses_all_fields(self, raw_binance_filters):
        filters = parse_symbol_filters(raw_binance_filters)
        assert filters.min_qty == Decimal("0.00001000")
        assert filters.max_qty == Decimal("9000.00000000")
        assert filters.step_size == Decimal("0.00001000")
        assert filters.min_price == Decimal("0.01000000")
        assert filters.max_price == Decimal("1000000.00000000")
        assert filters.tick_size == Decimal("0.01000000")
        assert filters.min_notional == Decimal("5.00000000")

    def test_handles_min_notional_filter_name(self):
        """Aeltere Binance Symbols verwenden MIN_NOTIONAL statt NOTIONAL."""
        filters_raw = [
            {"filterType": "LOT_SIZE", "minQty": "0.01", "maxQty": "100", "stepSize": "0.01"},
            {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "10000", "tickSize": "0.01"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"},
        ]
        filters = parse_symbol_filters(filters_raw)
        assert filters.min_notional == Decimal("10.00")

    def test_missing_notional_defaults_to_zero(self):
        """Kein NOTIONAL/MIN_NOTIONAL -> min_notional = 0."""
        filters_raw = [
            {"filterType": "LOT_SIZE", "minQty": "0.01", "maxQty": "100", "stepSize": "0.01"},
            {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "10000", "tickSize": "0.01"},
        ]
        filters = parse_symbol_filters(filters_raw)
        assert filters.min_notional == Decimal("0")

    def test_missing_lot_size_raises(self):
        with pytest.raises(ValueError, match="LOT_SIZE"):
            parse_symbol_filters([
                {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "10000", "tickSize": "0.01"},
            ])

    def test_missing_price_filter_raises(self):
        with pytest.raises(ValueError, match="PRICE_FILTER"):
            parse_symbol_filters([
                {"filterType": "LOT_SIZE", "minQty": "0.01", "maxQty": "100", "stepSize": "0.01"},
            ])


# --- round_qty_to_step_size ---


class TestRoundQtyToStepSize:
    def test_exact_multiple(self):
        assert round_qty_to_step_size(Decimal("0.01500"), Decimal("0.00001")) == Decimal("0.01500")

    def test_floors_down(self):
        """Floor-Rundung -- nie aufrunden, um verfuegbare Menge nicht zu ueberschreiten."""
        assert round_qty_to_step_size(Decimal("0.01999"), Decimal("0.001")) == Decimal("0.019")

    def test_floors_tiny_remainder(self):
        assert round_qty_to_step_size(Decimal("0.01509"), Decimal("0.00001")) == Decimal("0.01509")

    def test_step_size_one(self):
        """Ganzzahl-stepSize (z.B. fuer XRP)."""
        assert round_qty_to_step_size(Decimal("145.7"), Decimal("1")) == Decimal("145")

    def test_step_size_zero_returns_unchanged(self):
        """stepSize=0 bedeutet keine Einschraenkung."""
        qty = Decimal("0.123456789")
        assert round_qty_to_step_size(qty, Decimal("0")) == qty

    def test_very_small_btc_qty(self):
        assert round_qty_to_step_size(Decimal("0.00002345"), Decimal("0.00001")) == Decimal("0.00002")

    def test_large_qty(self):
        assert round_qty_to_step_size(Decimal("1234.56789"), Decimal("0.00001")) == Decimal("1234.56789")


# --- round_price_to_tick_size ---


class TestRoundPriceToTickSize:
    def test_exact_tick(self):
        assert round_price_to_tick_size(Decimal("57255.55"), Decimal("0.01")) == Decimal("57255.55")

    def test_rounds_half_up(self):
        assert round_price_to_tick_size(Decimal("57255.555"), Decimal("0.01")) == Decimal("57255.56")

    def test_high_precision(self):
        """High tick precision (8 decimal places)."""
        assert round_price_to_tick_size(
            Decimal("0.000023456"), Decimal("0.00000001")
        ) == Decimal("0.00002346")

    def test_tick_size_zero_returns_unchanged(self):
        price = Decimal("12345.6789")
        assert round_price_to_tick_size(price, Decimal("0")) == price


# --- validate_order_filters ---


class TestValidateOrderFilters:
    def test_valid_order(self, btceur_filters):
        errors = validate_order_filters(
            Decimal("0.01"), Decimal("57000"), btceur_filters
        )
        assert errors == []

    def test_qty_below_min(self, btceur_filters):
        errors = validate_order_filters(
            Decimal("0.000001"), Decimal("57000"), btceur_filters
        )
        assert any("unter Minimum" in e for e in errors)

    def test_qty_above_max(self, btceur_filters):
        errors = validate_order_filters(
            Decimal("10000"), Decimal("57000"), btceur_filters
        )
        assert any("ueber Maximum" in e for e in errors)

    def test_qty_not_step_multiple(self, btceur_filters):
        errors = validate_order_filters(
            Decimal("0.000012"), Decimal("57000"), btceur_filters
        )
        assert any("stepSize" in e for e in errors)

    def test_price_below_min(self, btceur_filters):
        errors = validate_order_filters(
            Decimal("0.01"), Decimal("0.001"), btceur_filters
        )
        assert any("Preis" in e and "unter Minimum" in e for e in errors)

    def test_notional_below_min(self, btceur_filters):
        """Orderwert (qty * price) unter minNotional."""
        errors = validate_order_filters(
            Decimal("0.00001"), Decimal("100"), btceur_filters
        )
        # 0.00001 * 100 = 0.001 EUR < 5 EUR
        assert any("minNotional" in e for e in errors)

    def test_multiple_violations(self, btceur_filters):
        errors = validate_order_filters(
            Decimal("0.000001"), Decimal("0.001"), btceur_filters
        )
        assert len(errors) >= 2  # qty below min + price below min + notional
