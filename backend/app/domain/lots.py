"""
TradeLot Management Logic

1 Fill = 1 Lot (deterministisch)
FIFO Sell Allocation
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Tuple
from dataclasses import replace

logger = logging.getLogger(__name__)
import uuid

from .models import (
    LedgerEvent,
    TradeLot,
    SellAllocation,
    EventType,
    TradeSide,
    LotStatus,
    AllocationStrategy,
)


def create_trade_lot_from_buy_fill(
    fill_event: LedgerEvent,
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> TradeLot:
    """
    Erstellt ein TradeLot aus einem Buy-Fill Event

    1 Fill = 1 Lot (deterministisch)

    Args:
        fill_event: Buy TRADE_FILL Event
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR
                             z.B. {"BNB": Decimal("700.00")} für BNB/EUR-Preis

    Returns:
        TradeLot

    Raises:
        ValueError: Wenn Event kein Buy-Fill ist
    """
    if fill_event.type != EventType.TRADE_FILL:
        raise ValueError(f"Event type must be TRADE_FILL, got {fill_event.type}")

    if fill_event.side != TradeSide.BUY:
        raise ValueError(f"Event side must be BUY, got {fill_event.side}")

    if fill_event.price is None or fill_event.amount is None:
        raise ValueError("Buy fill must have price and amount")

    # Kosten und Netto-Menge berechnen
    # WICHTIG: qty von Binance ist BRUTTO (VOR Fee-Abzug)!
    # - BTC Fee: qty reduzieren, cost = price * amount (EUR tatsächlich bezahlt)
    # - EUR Fee: cost += fee (zusätzliche EUR-Kosten)
    # - BNB Fee: cost += bnb_fee_eur (zusätzliche Kosten in EUR umgerechnet)
    cost_eur = fill_event.price * fill_event.amount
    qty_net = fill_event.amount

    if fill_event.fee_asset == "BTC" and fill_event.fee_amount and fill_event.price:
        # Fee in BTC: Menge reduzieren, KEINE zusätzlichen EUR-Kosten
        # (die BTC-Fee wird von der erhaltenen Menge abgezogen, nicht extra bezahlt)
        qty_net = fill_event.amount - fill_event.fee_amount
    elif fill_event.fee_asset == "EUR" and fill_event.fee_amount:
        # Fee in EUR: zusätzliche EUR-Kosten
        cost_eur += fill_event.fee_amount
    elif fill_event.fee_asset == "BNB" and fill_event.fee_amount:
        # Fee in BNB: EUR-Gegenwert zu Kosten addieren
        if fee_conversion_rates and "BNB" in fee_conversion_rates:
            bnb_eur_price = fee_conversion_rates["BNB"]
            fee_eur_value = fill_event.fee_amount * bnb_eur_price
            cost_eur += fee_eur_value
        else:
            logger.warning("BNB fee detected but no conversion rate provided for fill %s", fill_event.id)
    elif fill_event.fee_amount and fill_event.fee_asset not in ["EUR", "BTC", "BNB"]:
        logger.warning("Unhandled fee asset %s for fill %s", fill_event.fee_asset, fill_event.id)

    lot = TradeLot(
        id=f"lot_{fill_event.id}",
        created_from_fill_id=fill_event.id,
        created_at=fill_event.timestamp,
        qty_btc_initial=qty_net,
        qty_btc_open=qty_net,
        cost_eur=cost_eur,
        status=LotStatus.OPEN,
    )

    return lot


def _compute_net_proceeds_per_btc(
    sell_event: LedgerEvent,
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> Decimal:
    """
    Berechnet Netto-Erlös pro BTC nach Fees

    Args:
        sell_event: Sell TRADE_FILL Event (muss price und amount haben)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR

    Returns:
        Netto-Erlös pro BTC als Decimal
    """
    sell_proceeds_per_btc = sell_event.price

    # Fee vom Erlös abziehen
    total_fee_eur = Decimal("0")
    if sell_event.fee_asset == "EUR" and sell_event.fee_amount:
        total_fee_eur = sell_event.fee_amount
    elif sell_event.fee_asset == "BTC" and sell_event.fee_amount and sell_event.price:
        total_fee_eur = sell_event.fee_amount * sell_event.price
    elif sell_event.fee_asset == "BNB" and sell_event.fee_amount:
        if fee_conversion_rates and "BNB" in fee_conversion_rates:
            bnb_eur_price = fee_conversion_rates["BNB"]
            total_fee_eur = sell_event.fee_amount * bnb_eur_price
        else:
            logger.warning("BNB fee detected but no conversion rate provided for sell %s", sell_event.id)

    # Fee anteilig auf BTC verteilen
    fee_per_btc = total_fee_eur / sell_event.amount if sell_event.amount > 0 else Decimal("0")
    return sell_proceeds_per_btc - fee_per_btc


def _allocate_qty_to_lots(
    sell_event: LedgerEvent,
    lots: List[TradeLot],
    qty_to_allocate: Decimal,
    net_proceeds_per_btc: Decimal,
) -> Tuple[List[TradeLot], List[SellAllocation], Decimal]:
    """
    Allokiert eine Sell-Menge auf eine Liste von Lots (der Reihe nach).

    Args:
        sell_event: Sell TRADE_FILL Event (für IDs)
        lots: Lots in Allokations-Reihenfolge
        qty_to_allocate: Zu verkaufende Menge
        net_proceeds_per_btc: Netto-Erlös pro BTC

    Returns:
        Tuple[updated_lots, allocations, remaining_qty]
    """
    allocations = []
    updated_lots = []

    for lot in lots:
        if qty_to_allocate <= Decimal("0.00000001"):
            updated_lots.append(lot)
            continue

        qty_from_this_lot = min(qty_to_allocate, lot.qty_btc_open)

        cost_per_btc = lot.break_even
        proceeds_this_allocation = net_proceeds_per_btc * qty_from_this_lot
        cost_this_allocation = cost_per_btc * qty_from_this_lot
        realized_pnl = proceeds_this_allocation - cost_this_allocation

        allocation = SellAllocation(
            id=f"alloc_{sell_event.id}_{lot.id}",
            sell_fill_id=sell_event.id,
            trade_lot_id=lot.id,
            qty_allocated=qty_from_this_lot,
            realized_pnl_eur=realized_pnl,
            created_at=sell_event.timestamp,
        )
        allocations.append(allocation)

        new_qty_open = lot.qty_btc_open - qty_from_this_lot

        if new_qty_open <= Decimal("0.00000001"):
            new_qty_open = Decimal("0")
            new_status = LotStatus.CLOSED
        elif new_qty_open < lot.qty_btc_initial:
            new_status = LotStatus.PARTIAL_CLOSED
        else:
            new_status = lot.status

        updated_lot = replace(lot, qty_btc_open=new_qty_open, status=new_status)
        updated_lots.append(updated_lot)

        qty_to_allocate -= qty_from_this_lot

    return updated_lots, allocations, qty_to_allocate


def _sort_lots_by_strategy(
    lots: List[TradeLot],
    strategy: AllocationStrategy,
) -> List[TradeLot]:
    """
    Sortiert Lots nach der gegebenen Allocation-Strategie.

    FIFO: created_at aufsteigend (aelteste zuerst)
    LIFO: created_at absteigend (neueste zuerst)
    HIGHEST_COST: break_even absteigend (teuerste zuerst), Tie-Break: created_at absteigend
    """
    if strategy == AllocationStrategy.FIFO:
        return sorted(lots, key=lambda lot: lot.created_at)
    elif strategy == AllocationStrategy.LIFO:
        return sorted(lots, key=lambda lot: lot.created_at, reverse=True)
    elif strategy == AllocationStrategy.HIGHEST_COST:
        # Hoechster Break-even zuerst; bei Gleichstand neueste zuerst (LIFO als Tie-Break)
        return sorted(lots, key=lambda lot: (lot.break_even, lot.created_at), reverse=True)
    else:
        raise ValueError(f"Unknown allocation strategy: {strategy}")


def allocate_sell_with_strategy(
    sell_event: LedgerEvent,
    open_lots: List[TradeLot],
    strategy: AllocationStrategy = AllocationStrategy.FIFO,
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> Tuple[List[TradeLot], List[SellAllocation]]:
    """
    Strategy-Aware Sell Allocation - Deterministisch

    Sortiert Lots nach der gegebenen Strategie und allokiert.

    Args:
        sell_event: Sell TRADE_FILL Event
        open_lots: Liste offener TradeLots
        strategy: Allocation Strategy (FIFO, LIFO, HIGHEST_COST)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR

    Returns:
        Tuple[updated_lots, allocations]

    Raises:
        ValueError: Wenn Event kein Sell-Fill ist oder nicht genug offene Lots
    """
    if sell_event.type != EventType.TRADE_FILL:
        raise ValueError(f"Event type must be TRADE_FILL, got {sell_event.type}")

    if sell_event.side != TradeSide.SELL:
        raise ValueError(f"Event side must be SELL, got {sell_event.side}")

    if sell_event.price is None or sell_event.amount is None:
        raise ValueError("Sell fill must have price and amount")

    sorted_lots = _sort_lots_by_strategy(open_lots, strategy)

    net_proceeds_per_btc = _compute_net_proceeds_per_btc(sell_event, fee_conversion_rates)

    updated_lots, allocations, remaining = _allocate_qty_to_lots(
        sell_event, sorted_lots, sell_event.amount, net_proceeds_per_btc
    )

    if remaining > Decimal("0.00000001"):
        raise ValueError(
            f"Not enough open lots to allocate sell. "
            f"Remaining: {remaining} BTC"
        )

    return updated_lots, allocations


def allocate_sell_fifo(
    sell_event: LedgerEvent,
    open_lots: List[TradeLot],
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> Tuple[List[TradeLot], List[SellAllocation]]:
    """
    FIFO Sell Allocation - Deterministisch (Wrapper)

    Schließt die ältesten offenen Lots zuerst.
    Delegiert an allocate_sell_with_strategy() mit FIFO.
    """
    return allocate_sell_with_strategy(
        sell_event, open_lots, AllocationStrategy.FIFO, fee_conversion_rates
    )


def allocate_sell_to_lot(
    sell_event: LedgerEvent,
    target_lot: TradeLot,
    remaining_open_lots: List[TradeLot],
    fee_conversion_rates: dict[str, Decimal] | None = None,
    overflow_strategy: AllocationStrategy = AllocationStrategy.FIFO,
) -> Tuple[List[TradeLot], List[SellAllocation]]:
    """
    Lot-spezifische Sell Allocation

    Allokiert den Sell zuerst an ein bestimmtes Lot.
    Overflow (sell > lot.qty_open) wird nach overflow_strategy an remaining_open_lots verteilt.

    Args:
        sell_event: Sell TRADE_FILL Event
        target_lot: Das Lot, dem der Sell zugeordnet werden soll
        remaining_open_lots: Weitere offene Lots fuer Overflow
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR
        overflow_strategy: Strategie fuer Overflow-Allokation (Default: FIFO)

    Returns:
        Tuple[updated_lots, allocations]

    Raises:
        ValueError: Wenn Event kein Sell-Fill oder target_lot keine offene Menge hat
    """
    if sell_event.type != EventType.TRADE_FILL:
        raise ValueError(f"Event type must be TRADE_FILL, got {sell_event.type}")

    if sell_event.side != TradeSide.SELL:
        raise ValueError(f"Event side must be SELL, got {sell_event.side}")

    if sell_event.price is None or sell_event.amount is None:
        raise ValueError("Sell fill must have price and amount")

    if target_lot.qty_btc_open <= Decimal("0"):
        raise ValueError(f"Target lot {target_lot.id} has no open quantity")

    net_proceeds_per_btc = _compute_net_proceeds_per_btc(sell_event, fee_conversion_rates)

    # Phase 1: Ziel-Lot allokieren
    target_updated, target_allocs, remaining = _allocate_qty_to_lots(
        sell_event, [target_lot], sell_event.amount, net_proceeds_per_btc
    )

    # Phase 2: Overflow nach overflow_strategy auf restliche Lots
    if remaining > Decimal("0.00000001"):
        overflow_lots = _sort_lots_by_strategy(
            [lot for lot in remaining_open_lots if lot.id != target_lot.id],
            overflow_strategy,
        )
        fifo_updated, fifo_allocs, still_remaining = _allocate_qty_to_lots(
            sell_event, overflow_lots, remaining, net_proceeds_per_btc
        )

        if still_remaining > Decimal("0.00000001"):
            raise ValueError(
                f"Not enough open lots to allocate sell. "
                f"Remaining: {still_remaining} BTC"
            )

        return target_updated + fifo_updated, target_allocs + fifo_allocs

    # Restliche Lots unverändert zurückgeben
    unchanged_lots = [lot for lot in remaining_open_lots if lot.id != target_lot.id]
    return target_updated + unchanged_lots, target_allocs


def calculate_lot_target_price(
    lot: TradeLot,
    target_margin_pct: Decimal,
    fee_buffer_pct: Decimal = Decimal("0")
) -> Decimal:
    """
    Berechnet Zielverkaufspreis für ein TradeLot

    Args:
        lot: TradeLot
        target_margin_pct: Zielmarge (z.B. 0.05 für 5%)
        fee_buffer_pct: Optional Fee-Puffer (z.B. 0.002 für 0.2%)

    Returns:
        Zielpreis
    """
    # Lot-spezifische Margin oder globale verwenden
    margin = lot.target_margin_pct if lot.target_margin_pct is not None else target_margin_pct

    return lot.break_even * (Decimal("1") + margin) * (Decimal("1") + fee_buffer_pct)
