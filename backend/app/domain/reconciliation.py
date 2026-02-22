"""
Reconciliation Domain Logic - Pure functions for threshold evaluation and alert generation.

No I/O. Takes reconciliation sub-reports and thresholds, returns alert dicts.
"""

from decimal import Decimal, InvalidOperation
from typing import List


def evaluate_discrepancies(
    balance_report: dict,
    order_report: dict,
    tolerance_base: Decimal,
    tolerance_quote: Decimal,
) -> List[dict]:
    """
    Evaluate reconciliation reports against thresholds and generate alert dicts.

    Pure function (no I/O). Deterministic: same inputs = same outputs.

    Args:
        balance_report: Balance reconciliation report dict (base, quote, errors sections)
        order_report: Order reconciliation report dict (discrepancies, errors sections)
        tolerance_base: Acceptable base asset difference threshold
        tolerance_quote: Acceptable quote asset difference threshold

    Returns:
        List of alert dicts, each with: alert_type, severity, title, details_json.
        Empty list if no discrepancies exceed thresholds.
    """
    alerts: List[dict] = []

    # 1. Check balance errors (critical — could not fetch data at all)
    balance_errors = balance_report.get("errors", [])
    for error_msg in balance_errors:
        alerts.append(
            {
                "alert_type": "BALANCE_CHECK_ERROR",
                "severity": "critical",
                "title": "Balance-Abgleich Fehler",
                "details_json": {"error": error_msg},
            }
        )

    # 2. Check base balance discrepancy
    base_section = balance_report.get("base", {})
    _check_balance_discrepancy(
        alerts=alerts,
        section=base_section,
        tolerance=tolerance_base,
    )

    # 3. Check quote balance discrepancy
    quote_section = balance_report.get("quote", {})
    _check_balance_discrepancy(
        alerts=alerts,
        section=quote_section,
        tolerance=tolerance_quote,
    )

    # 4. Check order discrepancies
    order_discrepancies = order_report.get("discrepancies", [])
    for disc in order_discrepancies:
        alerts.append(
            {
                "alert_type": "ORDER_DISCREPANCY",
                "severity": "warning",
                "title": f"Order-Diskrepanz: {disc.get('issue', 'Unbekannt')}",
                "details_json": disc,
            }
        )

    return alerts


def _check_balance_discrepancy(
    alerts: List[dict],
    section: dict,
    tolerance: Decimal,
) -> None:
    """
    Check a single balance section (base or quote) against its tolerance.

    Mutates alerts list in-place for efficiency.
    Uses > comparison (not >=): diff exactly at tolerance is considered within tolerance.
    """
    diff_str = section.get("diff")
    if diff_str is None:
        return

    try:
        diff = Decimal(diff_str)
    except (InvalidOperation, TypeError, ValueError):
        return

    # Strict greater-than: diff == tolerance is within tolerance
    if diff > tolerance:
        asset = section.get("asset", "Unknown")

        # Severity: critical if diff exceeds 10x tolerance
        if diff > tolerance * 10:
            severity = "critical"
        else:
            severity = "warning"

        alerts.append(
            {
                "alert_type": "BALANCE_DISCREPANCY",
                "severity": severity,
                "title": f"{asset} Balance-Diskrepanz",
                "details_json": {
                    "asset": asset,
                    "expected": section.get("calculated", ""),
                    "actual": section.get("binance", ""),
                    "diff": diff_str,
                    "threshold": str(tolerance),
                },
            }
        )
