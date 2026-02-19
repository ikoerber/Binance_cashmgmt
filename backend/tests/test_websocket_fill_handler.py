"""
Tests fuer WebSocket Phase 3: Fill-Verarbeitung

Tests:
1. Extraktion: BUY/SELL aus executionReport, Decimal-Praezision, Nicht-BTCEUR skip
2. Fee-Berechnung: EUR/BTC/BNB Pfade, Fehler-Fallback
3. Integration: Idempotenz, BUY erstellt Lot, SELL erstellt Allocation, Rollback
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.services.websocket_fill_handler import (
    _extract_fill_from_execution_report,
    _compute_realtime_fee_eur_value,
)

# ─── Test-Daten: Binance executionReport ───


def _make_execution_report(
    trade_id=12345,
    symbol="BTCEUR",
    side="BUY",
    qty="0.001",
    price="85000.00",
    fee="0.0000005",
    fee_asset="BTC",
    tx_time_ms=1700000000000,
    order_id=67890,
    status="FILLED",
):
    """Erzeugt ein Binance executionReport Dict fuer Tests."""
    return {
        "e": "executionReport",
        "s": symbol,
        "S": side,
        "o": "LIMIT",
        "q": qty,
        "p": price,
        "X": status,
        "i": order_id,
        "c": f"user_123_lot1_{price}_{qty}_v1",
        "l": qty,  # last_filled_qty
        "L": price,  # last_filled_price
        "n": fee,  # commission
        "N": fee_asset,  # commission asset
        "t": trade_id,  # trade_id
        "T": tx_time_ms,  # transaction time
        "z": qty,  # cumulative filled qty
        "Z": "85.00",  # cumulative quote qty
    }


# ─── Tests: _extract_fill_from_execution_report ───


class TestExtractFillFromExecutionReport:
    """Tests fuer das Parsen des Binance executionReport."""

    def test_extracts_buy_fill(self):
        data = _make_execution_report(side="BUY")
        result = _extract_fill_from_execution_report(data)

        assert result is not None
        assert result["trade_id"] == 12345
        assert result["symbol"] == "BTCEUR"
        assert result["side"] == "BUY"
        assert result["qty"] == Decimal("0.001")
        assert result["price"] == Decimal("85000.00")
        assert result["fee_amount"] == Decimal("0.0000005")
        assert result["fee_asset"] == "BTC"

    def test_extracts_sell_fill(self):
        data = _make_execution_report(side="SELL")
        result = _extract_fill_from_execution_report(data)

        assert result is not None
        assert result["side"] == "SELL"

    def test_returns_none_for_trade_id_zero(self):
        data = _make_execution_report(trade_id=0)
        result = _extract_fill_from_execution_report(data)

        assert result is None

    def test_returns_none_for_unknown_symbol(self):
        data = _make_execution_report(symbol="XYZUSD")
        result = _extract_fill_from_execution_report(data)

        assert result is None

    def test_accepts_known_non_btceur_symbol(self):
        data = _make_execution_report(symbol="ETHEUR")
        result = _extract_fill_from_execution_report(data)

        assert result is not None
        assert result["symbol"] == "ETHEUR"

    def test_returns_none_for_unknown_side(self):
        data = _make_execution_report(side="UNKNOWN")
        result = _extract_fill_from_execution_report(data)

        assert result is None

    def test_returns_none_for_zero_qty(self):
        data = _make_execution_report(qty="0")
        result = _extract_fill_from_execution_report(data)

        assert result is None

    def test_returns_none_for_zero_price(self):
        data = _make_execution_report(price="0")
        result = _extract_fill_from_execution_report(data)

        assert result is None

    def test_decimal_precision_preserved(self):
        data = _make_execution_report(qty="0.00012345", price="84999.99")
        result = _extract_fill_from_execution_report(data)

        assert result["qty"] == Decimal("0.00012345")
        assert result["price"] == Decimal("84999.99")

    def test_timestamp_conversion(self):
        """Timestamp: Millisekunden → naive UTC datetime."""
        tx_time_ms = 1700000000000  # 2023-11-14 22:13:20 UTC
        data = _make_execution_report(tx_time_ms=tx_time_ms)
        result = _extract_fill_from_execution_report(data)

        expected = datetime.fromtimestamp(tx_time_ms / 1000, tz=timezone.utc).replace(
            tzinfo=None
        )
        assert result["timestamp"] == expected
        # Naive UTC (kein tzinfo), konsistent mit binance.py:173
        assert result["timestamp"].tzinfo is None

    def test_handles_invalid_decimal(self):
        data = _make_execution_report(qty="not_a_number")
        result = _extract_fill_from_execution_report(data)

        assert result is None

    def test_handles_missing_fields(self):
        """Fehlende Felder fuehren zu None, nicht zu Crash."""
        result = _extract_fill_from_execution_report({})
        assert result is None


# ─── Tests: _compute_realtime_fee_eur_value ───


class TestComputeRealtimeFeeEurValue:
    """Tests fuer die vereinfachte Fee-EUR-Wert-Berechnung."""

    def test_eur_fee_passthrough(self):
        result = _compute_realtime_fee_eur_value(
            Decimal("0.50"), "EUR", Decimal("85000"), "BTC"
        )
        assert result == Decimal("0.50")

    def test_btc_fee_multiplied_by_price(self):
        result = _compute_realtime_fee_eur_value(
            Decimal("0.0000005"), "BTC", Decimal("85000"), "BTC"
        )
        assert result == Decimal("0.0000005") * Decimal("85000")

    @patch("app.services.websocket_fill_handler._fetch_current_price")
    def test_bnb_fee_fetches_current_price(self, mock_fetch):
        mock_fetch.return_value = Decimal("700.00")

        result = _compute_realtime_fee_eur_value(
            Decimal("0.001"), "BNB", Decimal("85000"), "BTC"
        )

        mock_fetch.assert_called_once_with("BNBEUR")
        assert result == Decimal("0.001") * Decimal("700.00")

    @patch("app.services.websocket_fill_handler._fetch_current_price")
    def test_bnb_fee_fallback_to_none(self, mock_fetch):
        mock_fetch.return_value = None

        result = _compute_realtime_fee_eur_value(
            Decimal("0.001"), "BNB", Decimal("85000"), "BTC"
        )

        assert result is None

    def test_zero_fee_returns_none(self):
        result = _compute_realtime_fee_eur_value(Decimal("0"), "BTC", Decimal("85000"), "BTC")
        assert result is None

    def test_none_fee_returns_none(self):
        result = _compute_realtime_fee_eur_value(None, "BTC", Decimal("85000"), "BTC")
        assert result is None

    def test_none_fee_asset_returns_none(self):
        result = _compute_realtime_fee_eur_value(
            Decimal("0.001"), None, Decimal("85000"), "BTC"
        )
        assert result is None

    @patch("app.services.websocket_fill_handler._fetch_current_price")
    def test_fetch_exception_returns_none(self, mock_fetch):
        mock_fetch.side_effect = Exception("Network error")

        result = _compute_realtime_fee_eur_value(
            Decimal("0.001"), "BNB", Decimal("85000"), "BTC"
        )

        assert result is None
