"""
Lot Merge Domain Logic - Pure Functions (kein I/O)

Validiert und berechnet Merge-Operationen fuer TradeLots.
Nur Partial Fills derselben Binance-Order koennen zusammengefasst werden.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from .models import TradeLot, LotStatus


@dataclass
class MergeValidationResult:
    """Ergebnis der Merge-Validierung"""

    valid: bool
    errors: List[str]
    keeper_lot_id: Optional[str] = None
    merged_lot_ids: List[str] = field(default_factory=list)


@dataclass
class MergeResult:
    """Ergebnis einer Merge-Berechnung"""

    keeper_lot_id: str
    new_qty_base_initial: Decimal
    new_qty_base_open: Decimal
    new_cost_quote: Decimal
    new_break_even: Decimal
    merged_lot_ids: List[str] = field(default_factory=list)


def validate_merge(
    lots: List[TradeLot],
    binance_order_ids: dict,
    lots_with_orders: set,
    lots_with_allocations: set,
    lots_in_pairings: set,
) -> MergeValidationResult:
    """
    Validiert ob die gegebenen Lots zusammengefasst werden koennen.

    Regeln:
    1. Mindestens 2 Lots erforderlich
    2. Alle Lots muessen OPEN sein
    3. Alle Lots muessen die gleiche binance_order_id haben
    4. Kein Lot darf Sell-Allocations haben
    5. Kein Lot darf verknuepfte Orders haben
    6. Kein Lot darf in einem nicht-EXECUTED Pairing sein
    """
    errors = []

    if len(lots) < 2:
        errors.append("Mindestens 2 Lots fuer Merge erforderlich")
        return MergeValidationResult(valid=False, errors=errors)

    # Alle OPEN
    non_open = [lot for lot in lots if lot.status != LotStatus.OPEN]
    if non_open:
        ids = [lot.id for lot in non_open]
        errors.append(f"Lots muessen Status OPEN haben: {ids}")

    # Gleiche binance_order_id
    order_ids = set()
    missing_order_id = []
    for lot in lots:
        oid = binance_order_ids.get(lot.id)
        if not oid:
            missing_order_id.append(lot.id)
        else:
            order_ids.add(oid)

    if missing_order_id:
        errors.append(f"Binance Order ID fehlt fuer Lots: {missing_order_id}")
    if len(order_ids) > 1:
        errors.append(f"Lots gehoeren zu verschiedenen Binance Orders: {order_ids}")

    # Keine Sell-Allocations
    with_allocs = [lot.id for lot in lots if lot.id in lots_with_allocations]
    if with_allocs:
        errors.append(f"Lots haben Sell Allocations: {with_allocs}")

    # Keine verknuepften Orders
    with_orders = [lot.id for lot in lots if lot.id in lots_with_orders]
    if with_orders:
        errors.append(f"Lots haben offene Orders: {with_orders}")

    # Keine aktiven Pairings
    in_pairings = [lot.id for lot in lots if lot.id in lots_in_pairings]
    if in_pairings:
        errors.append(f"Lots sind in aktiven Pairings: {in_pairings}")

    if errors:
        return MergeValidationResult(valid=False, errors=errors)

    # Keeper = aeltestes Lot
    keeper = min(lots, key=lambda lot: lot.created_at)
    merged_ids = [lot.id for lot in lots if lot.id != keeper.id]

    return MergeValidationResult(
        valid=True,
        errors=[],
        keeper_lot_id=keeper.id,
        merged_lot_ids=merged_ids,
    )


def compute_merge(
    keeper: TradeLot,
    to_merge: List[TradeLot],
) -> MergeResult:
    """
    Berechnet das Ergebnis des Merges.
    Pure Berechnung, keine Seiteneffekte.
    """
    new_qty_initial = keeper.qty_base_initial + sum(
        lot.qty_base_initial for lot in to_merge
    )
    new_qty_open = keeper.qty_base_open + sum(lot.qty_base_open for lot in to_merge)
    new_cost = keeper.cost_quote + sum(lot.cost_quote for lot in to_merge)
    new_break_even = new_cost / new_qty_initial if new_qty_initial > 0 else Decimal("0")

    return MergeResult(
        keeper_lot_id=keeper.id,
        new_qty_base_initial=new_qty_initial,
        new_qty_base_open=new_qty_open,
        new_cost_quote=new_cost,
        new_break_even=new_break_even,
        merged_lot_ids=[lot.id for lot in to_merge],
    )
