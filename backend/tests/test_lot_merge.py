"""
Unit Tests fuer Lot Merge: Partial Fills zusammenfassen

Testet die Domain-Logik (pure) und Service-Integration (mit DB).
"""

from datetime import datetime
from decimal import Decimal

from app.domain.models import (
    LotStatus,
    TradeLot,
)
from app.domain.lot_merge import (
    validate_merge,
    compute_merge,
)

# ============================================================
# Helpers
# ============================================================


def _make_lot(
    lot_id="lot_1",
    fill_id="fill_1",
    qty=Decimal("0.01"),
    cost=Decimal("500.00"),
    status=LotStatus.OPEN,
    created_at=None,
):
    return TradeLot(
        id=lot_id,
        created_from_fill_id=fill_id,
        created_at=created_at or datetime(2024, 1, 1, 12, 0),
        qty_base_initial=qty,
        qty_base_open=qty,
        cost_eur=cost,
        status=status,
    )


# ============================================================
# Domain: validate_merge
# ============================================================


class TestValidateMerge:
    def test_success_two_lots(self):
        """Zwei OPEN Lots, gleiche Order, keine Constraints -> valid"""
        lot_a = _make_lot("lot_a", created_at=datetime(2024, 1, 1, 12, 0))
        lot_b = _make_lot("lot_b", created_at=datetime(2024, 1, 1, 12, 1))

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "123", "lot_b": "123"},
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is True
        assert result.errors == []
        assert result.keeper_lot_id == "lot_a"  # aeltester
        assert result.merged_lot_ids == ["lot_b"]

    def test_success_three_lots(self):
        """Drei OPEN Lots, gleiche Order -> valid"""
        lots = [
            _make_lot("lot_c", created_at=datetime(2024, 1, 1, 12, 2)),
            _make_lot("lot_a", created_at=datetime(2024, 1, 1, 12, 0)),
            _make_lot("lot_b", created_at=datetime(2024, 1, 1, 12, 1)),
        ]

        result = validate_merge(
            lots=lots,
            binance_order_ids={"lot_a": "99", "lot_b": "99", "lot_c": "99"},
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is True
        assert result.keeper_lot_id == "lot_a"
        assert set(result.merged_lot_ids) == {"lot_b", "lot_c"}

    def test_fails_single_lot(self):
        """Nur 1 Lot -> invalid"""
        lot = _make_lot("lot_a")
        result = validate_merge(
            lots=[lot],
            binance_order_ids={"lot_a": "123"},
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is False
        assert any("Mindestens 2" in e for e in result.errors)

    def test_fails_not_open(self):
        """PARTIAL_CLOSED Lot -> invalid"""
        lot_a = _make_lot("lot_a", status=LotStatus.OPEN)
        lot_b = _make_lot("lot_b", status=LotStatus.PARTIAL_CLOSED)

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "123", "lot_b": "123"},
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is False
        assert any("OPEN" in e for e in result.errors)

    def test_fails_different_orders(self):
        """Verschiedene binance_order_ids -> invalid"""
        lot_a = _make_lot("lot_a")
        lot_b = _make_lot("lot_b")

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "111", "lot_b": "222"},
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is False
        assert any("verschiedenen" in e for e in result.errors)

    def test_fails_missing_order_id(self):
        """Fehlende binance_order_id -> invalid"""
        lot_a = _make_lot("lot_a")
        lot_b = _make_lot("lot_b")

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "123"},  # lot_b fehlt
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is False
        assert any("fehlt" in e for e in result.errors)

    def test_fails_with_allocations(self):
        """Lot mit Sell Allocations -> invalid"""
        lot_a = _make_lot("lot_a")
        lot_b = _make_lot("lot_b")

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "123", "lot_b": "123"},
            lots_with_orders=set(),
            lots_with_allocations={"lot_a"},
            lots_in_pairings=set(),
        )

        assert result.valid is False
        assert any("Allocations" in e for e in result.errors)

    def test_fails_with_orders(self):
        """Lot mit offener Order -> invalid"""
        lot_a = _make_lot("lot_a")
        lot_b = _make_lot("lot_b")

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "123", "lot_b": "123"},
            lots_with_orders={"lot_b"},
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is False
        assert any("Orders" in e for e in result.errors)

    def test_fails_with_pairings(self):
        """Lot in aktivem Pairing -> invalid"""
        lot_a = _make_lot("lot_a")
        lot_b = _make_lot("lot_b")

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "123", "lot_b": "123"},
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings={"lot_a"},
        )

        assert result.valid is False
        assert any("Pairings" in e for e in result.errors)

    def test_keeper_is_earliest(self):
        """Keeper ist immer das aelteste Lot"""
        lot_a = _make_lot("lot_a", created_at=datetime(2024, 1, 2))
        lot_b = _make_lot("lot_b", created_at=datetime(2024, 1, 1))  # aelter

        result = validate_merge(
            lots=[lot_a, lot_b],
            binance_order_ids={"lot_a": "123", "lot_b": "123"},
            lots_with_orders=set(),
            lots_with_allocations=set(),
            lots_in_pairings=set(),
        )

        assert result.valid is True
        assert result.keeper_lot_id == "lot_b"  # aelterer ist Keeper
        assert result.merged_lot_ids == ["lot_a"]


# ============================================================
# Domain: compute_merge
# ============================================================


class TestComputeMerge:
    def test_aggregates_two_lots(self):
        """Zwei Lots korrekt aggregiert"""
        keeper = _make_lot(
            "lot_a",
            qty=Decimal("0.5"),
            cost=Decimal("25000.00"),
        )
        to_merge = [
            _make_lot(
                "lot_b",
                qty=Decimal("0.3"),
                cost=Decimal("15000.00"),
            )
        ]

        result = compute_merge(keeper, to_merge)

        assert result.keeper_lot_id == "lot_a"
        assert result.new_qty_base_initial == Decimal("0.8")
        assert result.new_qty_base_open == Decimal("0.8")
        assert result.new_cost_eur == Decimal("40000.00")
        assert result.new_break_even == Decimal("50000.00")
        assert result.merged_lot_ids == ["lot_b"]

    def test_aggregates_three_lots(self):
        """Drei Lots korrekt aggregiert"""
        keeper = _make_lot("lot_a", qty=Decimal("0.01"), cost=Decimal("500"))
        to_merge = [
            _make_lot("lot_b", qty=Decimal("0.02"), cost=Decimal("1000")),
            _make_lot("lot_c", qty=Decimal("0.03"), cost=Decimal("1500")),
        ]

        result = compute_merge(keeper, to_merge)

        assert result.new_qty_base_initial == Decimal("0.06")
        assert result.new_cost_eur == Decimal("3000")
        assert result.new_break_even == Decimal("50000")

    def test_decimal_precision(self):
        """Decimal-Praezision bleibt erhalten"""
        keeper = _make_lot(
            "lot_a",
            qty=Decimal("0.00123456"),
            cost=Decimal("61.7280"),
        )
        to_merge = [
            _make_lot(
                "lot_b",
                qty=Decimal("0.00234567"),
                cost=Decimal("117.2835"),
            )
        ]

        result = compute_merge(keeper, to_merge)

        assert result.new_qty_base_initial == Decimal("0.00358023")
        assert result.new_cost_eur == Decimal("179.0115")

    def test_break_even_weighted(self):
        """Break-even ist gewichteter Durchschnitt"""
        keeper = _make_lot(
            "lot_a",
            qty=Decimal("1.0"),
            cost=Decimal("50000"),
        )
        to_merge = [
            _make_lot(
                "lot_b",
                qty=Decimal("1.0"),
                cost=Decimal("60000"),
            )
        ]

        result = compute_merge(keeper, to_merge)

        assert result.new_qty_base_initial == Decimal("2.0")
        assert result.new_cost_eur == Decimal("110000")
        assert result.new_break_even == Decimal("55000")  # Gewichteter Durchschnitt
