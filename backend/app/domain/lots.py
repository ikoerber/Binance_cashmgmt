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

from .models import (
    LedgerEvent,
    TradeLot,
    SellAllocation,
    EventType,
    TradeSide,
    LotStatus,
    AllocationStrategy,
)
from app.constants import MIN_BTC_PRECISION  # Fallback fuer Code-Pfade ohne Symbol-Kontext
from app.symbol_registry import get_base_asset, get_quote_asset, get_min_base_precision
from app.utils.fee_conversion import compute_fee_quote_value  # noqa: F401 — Re-Export fuer Abwaertskompatibilitaet


def create_trade_lot_from_buy_fill(
    fill_event: LedgerEvent,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> TradeLot:
    """
    Erstellt ein TradeLot aus einem Buy-Fill Event

    1 Fill = 1 Lot (deterministisch)

    Args:
        fill_event: Buy TRADE_FILL Event
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency
                             z.B. {"BNB": Decimal("700.00")} fuer BNB/Quote-Preis

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
    # - Base-Asset Fee: qty reduzieren, cost = price * amount (Quote tatsaechlich bezahlt)
    # - Quote-Asset Fee: cost += fee (zusaetzliche Quote-Currency-Kosten)
    # - BNB Fee: cost += bnb_fee_quote (zusaetzliche Kosten in Quote-Currency umgerechnet)
    cost_quote = fill_event.price * fill_event.amount
    qty_net = fill_event.amount

    # Base-Asset und Quote-Asset aus Symbol ableiten
    symbol = fill_event.symbol or "BTCEUR"
    base_asset = get_base_asset(symbol)
    quote_asset = get_quote_asset(symbol)

    if fill_event.fee_asset == base_asset and fill_event.fee_amount and fill_event.price:
        # Fee in Base-Asset: Menge reduzieren, KEINE zusaetzlichen Quote-Currency-Kosten
        # (die Fee wird von der erhaltenen Menge abgezogen, nicht extra bezahlt)
        qty_net = fill_event.amount - fill_event.fee_amount
    elif fill_event.fee_asset == quote_asset and fill_event.fee_amount:
        # Fee in Quote-Currency: zusaetzliche Quote-Currency-Kosten
        cost_quote += fill_event.fee_amount
    elif fill_event.fee_amount and fill_event.fee_asset:
        # Fee in BNB oder anderem Asset: Quote-Currency-Gegenwert zu Kosten addieren
        # Prioritaet: 1. Vorberechneter fee_quote_value (persistiert), 2. Konvertierungsraten
        fee_quote_value = fill_event.fee_quote_value
        if fee_quote_value is None:
            fee_quote_value = compute_fee_quote_value(
                fill_event.fee_amount, fill_event.fee_asset,
                fill_event.price, fee_conversion_rates,
                quote_asset=quote_asset,
                base_asset=base_asset,
            )
        if fee_quote_value is not None:
            cost_quote += fee_quote_value
        else:
            logger.warning(
                "BNB/other fee lost: fill=%s, fee=%s %s — no conversion rate available",
                fill_event.id, fill_event.fee_amount, fill_event.fee_asset,
            )

    # EUR Cost Basis: All remaining pairs are EUR-quoted, so cost_eur = cost_quote
    computed_cost_eur = cost_quote

    lot = TradeLot(
        id=f"lot_{fill_event.id}",
        created_from_fill_id=fill_event.id,
        created_at=fill_event.timestamp,
        qty_base_initial=qty_net,
        qty_base_open=qty_net,
        cost_quote=cost_quote,
        cost_eur=computed_cost_eur,
        status=LotStatus.OPEN,
        symbol=symbol,
    )

    return lot


def _compute_net_proceeds_per_base(
    sell_event: LedgerEvent,
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> Decimal:
    """
    Berechnet Netto-Erloes pro Base-Asset nach Fees

    Args:
        sell_event: Sell TRADE_FILL Event (muss price und amount haben)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency

    Returns:
        Netto-Erloes pro Base-Asset als Decimal
    """
    symbol = sell_event.symbol or "BTCEUR"
    quote_asset = get_quote_asset(symbol)
    sell_proceeds_per_base = sell_event.price

    # Fee vom Erloes abziehen
    total_fee_quote = Decimal("0")
    if sell_event.fee_asset == quote_asset and sell_event.fee_amount:
        total_fee_quote = sell_event.fee_amount
    elif sell_event.fee_asset == get_base_asset(symbol) and sell_event.fee_amount and sell_event.price:
        total_fee_quote = sell_event.fee_amount * sell_event.price
    elif sell_event.fee_amount and sell_event.fee_asset:
        # Prioritaet: 1. Vorberechneter fee_quote_value, 2. Konvertierungsraten
        fee_quote = sell_event.fee_quote_value
        if fee_quote is None:
            fee_quote = compute_fee_quote_value(
                sell_event.fee_amount, sell_event.fee_asset,
                sell_event.price, fee_conversion_rates,
                quote_asset=quote_asset,
                base_asset=get_base_asset(symbol),
            )
        if fee_quote is not None:
            total_fee_quote = fee_quote
        else:
            logger.warning(
                "BNB/other fee lost on sell: fill=%s, fee=%s %s — no conversion rate available",
                sell_event.id, sell_event.fee_amount, sell_event.fee_asset,
            )

    # Fee anteilig auf Base-Asset verteilen
    min_prec = get_min_base_precision(symbol)
    fee_per_unit = total_fee_quote / sell_event.amount if sell_event.amount > min_prec else Decimal("0")
    return sell_proceeds_per_base - fee_per_unit


def _allocate_qty_to_lots(
    sell_event: LedgerEvent,
    lots: List[TradeLot],
    qty_to_allocate: Decimal,
    net_proceeds_per_base: Decimal,
) -> Tuple[List[TradeLot], List[SellAllocation], Decimal]:
    """
    Allokiert eine Sell-Menge auf eine Liste von Lots (der Reihe nach).

    Args:
        sell_event: Sell TRADE_FILL Event (fuer IDs)
        lots: Lots in Allokations-Reihenfolge
        qty_to_allocate: Zu verkaufende Menge
        net_proceeds_per_base: Netto-Erloes pro Base-Asset

    Returns:
        Tuple[updated_lots, allocations, remaining_qty]
    """
    min_prec = get_min_base_precision(sell_event.symbol or "BTCEUR")
    allocations = []
    updated_lots = []

    for lot in lots:
        if qty_to_allocate <= min_prec:
            updated_lots.append(lot)
            continue

        qty_from_this_lot = min(qty_to_allocate, lot.qty_base_open)

        cost_per_unit = lot.break_even
        proceeds_this_allocation = net_proceeds_per_base * qty_from_this_lot
        cost_this_allocation = cost_per_unit * qty_from_this_lot
        realized_pnl = proceeds_this_allocation - cost_this_allocation

        allocation = SellAllocation(
            id=f"alloc_{sell_event.id}_{lot.id}",
            sell_fill_id=sell_event.id,
            trade_lot_id=lot.id,
            qty_allocated=qty_from_this_lot,
            realized_pnl_quote=realized_pnl,
            created_at=sell_event.timestamp,
        )
        allocations.append(allocation)

        new_qty_open = lot.qty_base_open - qty_from_this_lot

        if new_qty_open <= min_prec:
            new_qty_open = Decimal("0")
            new_status = LotStatus.CLOSED
        elif new_qty_open < lot.qty_base_initial:
            new_status = LotStatus.PARTIAL_CLOSED
        else:
            new_status = lot.status

        updated_lot = replace(lot, qty_base_open=new_qty_open, status=new_status)
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
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency

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

    net_proceeds_per_base = _compute_net_proceeds_per_base(sell_event, fee_conversion_rates)

    updated_lots, allocations, remaining = _allocate_qty_to_lots(
        sell_event, sorted_lots, sell_event.amount, net_proceeds_per_base
    )

    min_prec = get_min_base_precision(sell_event.symbol or "BTCEUR")
    if remaining > min_prec:
        raise ValueError(
            f"Not enough open lots to allocate sell. "
            f"Remaining: {remaining}"
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
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency
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

    min_prec = get_min_base_precision(sell_event.symbol or "BTCEUR")
    if target_lot.qty_base_open <= min_prec:
        raise ValueError(f"Target lot {target_lot.id} has no open quantity")

    net_proceeds_per_base = _compute_net_proceeds_per_base(sell_event, fee_conversion_rates)

    # Phase 1: Ziel-Lot allokieren
    target_updated, target_allocs, remaining = _allocate_qty_to_lots(
        sell_event, [target_lot], sell_event.amount, net_proceeds_per_base
    )

    # Phase 2: Overflow nach overflow_strategy auf restliche Lots
    if remaining > min_prec:
        overflow_lots = _sort_lots_by_strategy(
            [lot for lot in remaining_open_lots if lot.id != target_lot.id],
            overflow_strategy,
        )
        fifo_updated, fifo_allocs, still_remaining = _allocate_qty_to_lots(
            sell_event, overflow_lots, remaining, net_proceeds_per_base
        )

        if still_remaining > min_prec:
            raise ValueError(
                f"Not enough open lots to allocate sell. "
                f"Remaining: {still_remaining}"
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



# compute_fee_quote_value ist nach app.utils.fee_conversion verschoben.
# Re-Export via Import oben fuer Abwaertskompatibilitaet.
