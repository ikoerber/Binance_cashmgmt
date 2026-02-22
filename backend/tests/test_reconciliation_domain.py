"""
Tests for evaluate_discrepancies() pure domain function.

TDD RED phase: Tests written before implementation.
"""

from decimal import Decimal

import pytest

from app.domain.reconciliation import evaluate_discrepancies


class TestEvaluateDiscrepancies:
    """Tests for threshold-based discrepancy evaluation."""

    def test_no_discrepancies_within_tolerance(self):
        """Balance diffs within tolerance, no order discrepancies -> empty list."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "binance": "1.00010000",
                "calculated": "1.00005000",
                "diff": "0.00005000",
                "within_tolerance": True,
            },
            "quote": {
                "asset": "EUR",
                "binance": "5000.50",
                "calculated": "5000.00",
                "diff": "0.50",
                "within_tolerance": True,
            },
            "errors": [],
        }
        order_report = {
            "synced": 5,
            "status_updated": 0,
            "discrepancies": [],
            "errors": [],
        }
        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )
        assert result == []

    def test_base_balance_exceeds_tolerance(self):
        """Base diff > tolerance_base -> one BALANCE_DISCREPANCY alert."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "binance": "1.00100000",
                "calculated": "1.00000000",
                "diff": "0.00100000",
                "within_tolerance": False,
            },
            "quote": {
                "asset": "EUR",
                "binance": "5000.00",
                "calculated": "5000.00",
                "diff": "0.00",
                "within_tolerance": True,
            },
            "errors": [],
        }
        order_report = {"synced": 0, "status_updated": 0, "discrepancies": [], "errors": []}

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )

        assert len(result) == 1
        alert = result[0]
        assert alert["alert_type"] == "BALANCE_DISCREPANCY"
        assert alert["severity"] == "warning"
        assert "BTC" in alert["title"]
        assert alert["details_json"]["asset"] == "BTC"
        assert alert["details_json"]["diff"] == "0.00100000"
        assert alert["details_json"]["threshold"] == "0.0001"

    def test_quote_balance_exceeds_tolerance(self):
        """Quote diff > tolerance_quote -> one BALANCE_DISCREPANCY alert."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "binance": "1.00000000",
                "calculated": "1.00000000",
                "diff": "0.00000000",
                "within_tolerance": True,
            },
            "quote": {
                "asset": "EUR",
                "binance": "5015.00",
                "calculated": "5000.00",
                "diff": "15.00",
                "within_tolerance": False,
            },
            "errors": [],
        }
        order_report = {"synced": 0, "status_updated": 0, "discrepancies": [], "errors": []}

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )

        assert len(result) == 1
        alert = result[0]
        assert alert["alert_type"] == "BALANCE_DISCREPANCY"
        assert alert["severity"] == "critical"  # 15.00 > 1.00 * 10
        assert "EUR" in alert["title"]
        assert alert["details_json"]["asset"] == "EUR"

    def test_both_balances_exceed_tolerance(self):
        """Both diffs exceed -> two alerts."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "binance": "1.01000000",
                "calculated": "1.00000000",
                "diff": "0.01000000",
                "within_tolerance": False,
            },
            "quote": {
                "asset": "EUR",
                "binance": "5050.00",
                "calculated": "5000.00",
                "diff": "50.00",
                "within_tolerance": False,
            },
            "errors": [],
        }
        order_report = {"synced": 0, "status_updated": 0, "discrepancies": [], "errors": []}

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )

        assert len(result) == 2
        types = [a["alert_type"] for a in result]
        assert types.count("BALANCE_DISCREPANCY") == 2

    def test_order_discrepancies_generate_alerts(self):
        """Order report has non-empty discrepancies list -> one alert per discrepancy."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "diff": "0.00000000",
                "within_tolerance": True,
            },
            "quote": {
                "asset": "EUR",
                "diff": "0.00",
                "within_tolerance": True,
            },
            "errors": [],
        }
        order_report = {
            "synced": 3,
            "status_updated": 1,
            "discrepancies": [
                {
                    "order_id": "ord-1",
                    "client_order_id": "u1_lot1_80000_0.001_v1",
                    "binance_order_id": "12345",
                    "issue": "Unknown Binance status: PENDING_CANCEL",
                },
                {
                    "order_id": "ord-2",
                    "client_order_id": "u1_lot2_85000_0.002_v1",
                    "binance_order_id": "12346",
                    "issue": "Order-Details konnten nicht abgerufen werden",
                },
            ],
            "errors": [],
        }

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )

        assert len(result) == 2
        for alert in result:
            assert alert["alert_type"] == "ORDER_DISCREPANCY"
            assert alert["severity"] == "warning"
            assert alert["details_json"] is not None

    def test_balance_exactly_at_tolerance(self):
        """Diff == tolerance -> no alert (within tolerance, using > not >=)."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "diff": "0.00010000",
                "within_tolerance": True,
            },
            "quote": {
                "asset": "EUR",
                "diff": "1.00",
                "within_tolerance": True,
            },
            "errors": [],
        }
        order_report = {"synced": 0, "status_updated": 0, "discrepancies": [], "errors": []}

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )

        assert result == []

    def test_empty_reports(self):
        """Empty/missing sections -> empty list (graceful handling)."""
        # Completely empty dicts
        result = evaluate_discrepancies(
            balance_report={},
            order_report={},
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )
        assert result == []

        # Missing sub-keys
        result = evaluate_discrepancies(
            balance_report={"base": {}, "quote": {}},
            order_report={},
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )
        assert result == []

    def test_balance_errors_generate_alert(self):
        """Balance report has non-empty errors list -> BALANCE_CHECK_ERROR alert with severity critical."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "diff": "0.00000000",
                "within_tolerance": True,
            },
            "quote": {
                "asset": "EUR",
                "diff": "0.00",
                "within_tolerance": True,
            },
            "errors": ["Binance-Balances konnten nicht abgerufen werden"],
        }
        order_report = {"synced": 0, "status_updated": 0, "discrepancies": [], "errors": []}

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )

        assert len(result) == 1
        alert = result[0]
        assert alert["alert_type"] == "BALANCE_CHECK_ERROR"
        assert alert["severity"] == "critical"
        assert "error" in alert["title"].lower() or "fehler" in alert["title"].lower()

    def test_severity_warning_vs_critical(self):
        """diff > tolerance -> warning, diff > tolerance * 10 -> critical."""
        # Warning: diff = 0.0005, tolerance = 0.0001, ratio = 5 (< 10)
        balance_report = {
            "base": {
                "asset": "BTC",
                "diff": "0.00050000",
                "within_tolerance": False,
            },
            "quote": {
                "asset": "EUR",
                "diff": "0.00",
                "within_tolerance": True,
            },
            "errors": [],
        }
        order_report = {"synced": 0, "status_updated": 0, "discrepancies": [], "errors": []}

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )
        assert len(result) == 1
        assert result[0]["severity"] == "warning"

        # Critical: diff = 0.002, tolerance = 0.0001, ratio = 20 (> 10)
        balance_report["base"]["diff"] = "0.00200000"
        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )
        assert len(result) == 1
        assert result[0]["severity"] == "critical"

    def test_combined_balance_and_order_alerts(self):
        """Balance discrepancy + order discrepancy -> both appear in result."""
        balance_report = {
            "base": {
                "asset": "BTC",
                "diff": "0.01000000",
                "within_tolerance": False,
            },
            "quote": {
                "asset": "EUR",
                "diff": "0.00",
                "within_tolerance": True,
            },
            "errors": [],
        }
        order_report = {
            "synced": 1,
            "status_updated": 0,
            "discrepancies": [
                {
                    "order_id": "ord-1",
                    "client_order_id": "coid-1",
                    "binance_order_id": "99",
                    "issue": "Status mismatch",
                },
            ],
            "errors": [],
        }

        result = evaluate_discrepancies(
            balance_report=balance_report,
            order_report=order_report,
            tolerance_base=Decimal("0.0001"),
            tolerance_quote=Decimal("1.00"),
        )

        assert len(result) == 2
        alert_types = {a["alert_type"] for a in result}
        assert "BALANCE_DISCREPANCY" in alert_types
        assert "ORDER_DISCREPANCY" in alert_types
