"""TradeLot Service - DB Integration für Lot-Management"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

import logging

from app.domain.lots import (
    create_trade_lot_from_buy_fill,
    allocate_sell_fifo,
    allocate_sell_with_strategy,
    allocate_sell_to_lot,
    calculate_lot_target_price,
    _compute_net_proceeds_per_base,
    _allocate_qty_to_lots,
    _sort_lots_by_strategy,
)
from app.domain.models import LotStatus, TradeLot as DomainLot, AllocationStrategy
from app.db.models import (
    TradeLotDB,
    SellAllocationDB,
    LedgerEventDB,
    LotStatusEnum,
    OrderDB,
    OrderStatusEnum,
    PairingItemDB,
    PairingDB,
    PairingStatusEnum,
    EventTypeEnum,
    EventSourceEnum,
    UserSettingsDB,
)
from app.domain.lot_merge import validate_merge, compute_merge
from app.symbol_registry import (
    get_base_asset,
    get_quote_asset,
)

logger = logging.getLogger(__name__)
from app.services.portfolio_service import _db_event_to_domain


def _get_base_symbols_for_sell_event(sell_event_db: LedgerEventDB) -> list[str]:
    """Returns the symbol list for a sell event's lot filtering.

    With EUR-only pairs (1:1 base-to-symbol mapping), returns the single
    sell event symbol. Falls back to BTCEUR for legacy events without symbol.
    """
    sell_symbol = sell_event_db.symbol or "BTCEUR"
    return [sell_symbol]


def get_lots_for_user(
    db: Session,
    user_id: str,
    status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    symbol: Optional[str] = None,
) -> List[dict]:
    """
    Holt TradeLots für einen User

    Args:
        db: Database Session
        user_id: User ID
        status: Optional - Filter nach Status (OPEN/PARTIAL_CLOSED/CLOSED)
        from_date: Optional - Nur Lots ab diesem Datum
        to_date: Optional - Nur Lots bis zu diesem Datum
        limit: Max Anzahl Lots
        offset: Offset für Pagination

    Returns:
        Liste von Lot-Dicts
    """
    query = db.query(TradeLotDB).filter(TradeLotDB.user_id == user_id)

    if status:
        query = query.filter(TradeLotDB.status == LotStatusEnum[status])
    else:
        # Default: MERGED Lots ausblenden
        query = query.filter(TradeLotDB.status != LotStatusEnum.MERGED)

    if from_date:
        query = query.filter(TradeLotDB.created_at >= from_date)

    if to_date:
        query = query.filter(TradeLotDB.created_at <= to_date)

    if symbol:
        query = query.filter(TradeLotDB.symbol == symbol)

    lots_db = (
        query.order_by(desc(TradeLotDB.created_at)).limit(limit).offset(offset).all()
    )

    # Batch-Load Fill-Events (vermeidet N+1 Queries)
    fill_ids = [lot.created_from_fill_id for lot in lots_db if lot.created_from_fill_id]
    fill_events = (
        db.query(LedgerEventDB).filter(LedgerEventDB.id.in_(fill_ids)).all()
        if fill_ids
        else []
    )
    fill_map = {e.id: e for e in fill_events}

    return [
        _lot_db_to_dict(
            lot_db, db, fill_event=fill_map.get(lot_db.created_from_fill_id)
        )
        for lot_db in lots_db
    ]


def get_lot_detail(db: Session, user_id: str, lot_id: str) -> Optional[dict]:
    """
    Holt Lot-Details inkl. Allocations

    Args:
        db: Database Session
        user_id: User ID
        lot_id: Lot ID

    Returns:
        Lot-Dict mit Allocations oder None
    """
    lot_db = (
        db.query(TradeLotDB)
        .filter(TradeLotDB.id == lot_id, TradeLotDB.user_id == user_id)
        .first()
    )

    if not lot_db:
        return None

    # Allocations holen
    allocations_db = (
        db.query(SellAllocationDB)
        .filter(SellAllocationDB.trade_lot_id == lot_id)
        .order_by(SellAllocationDB.created_at.asc())
        .all()
    )

    lot_dict = _lot_db_to_dict(lot_db, db)
    lot_dict["allocations"] = [
        {
            "id": alloc.id,
            "sell_fill_id": alloc.sell_fill_id,
            "qty_allocated": str(alloc.qty_allocated),
            "realized_pnl_quote": str(alloc.realized_pnl_quote),
            "created_at": alloc.created_at.isoformat(),
        }
        for alloc in allocations_db
    ]

    return lot_dict


def create_lot_from_buy_fill(
    db: Session,
    user_id: str,
    fill_event_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> dict:
    """
    Erstellt TradeLot aus Buy-Fill Event

    Args:
        db: Database Session
        user_id: User ID
        fill_event_id: Fill Event ID (LedgerEvent)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency
                             z.B. {"BNB": Decimal("700.00")} fuer BNB/Quote-Preis

    Returns:
        Erstelltes Lot als Dict

    Raises:
        ValueError: Wenn Event nicht gefunden oder kein Buy-Fill
    """
    # Event aus DB holen
    event_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.id == fill_event_id, LedgerEventDB.user_id == user_id)
        .first()
    )

    if not event_db:
        raise ValueError(f"Event {fill_event_id} not found")

    # Zu Domain Model konvertieren
    event_domain = _db_event_to_domain(event_db)

    # TradeLot erstellen (Domain-Logik)
    lot_domain = create_trade_lot_from_buy_fill(
        event_domain, fee_conversion_rates
    )

    # Safety-Check: Lot existiert bereits (z.B. nach Merge)?
    existing = db.query(TradeLotDB).filter(TradeLotDB.id == lot_domain.id).first()
    if existing:
        logger.info(
            "Lot %s already exists (status=%s), skipping creation",
            lot_domain.id,
            existing.status.value,
        )
        return _lot_db_to_dict(existing, db)

    # In DB persistieren
    lot_db = TradeLotDB(
        id=lot_domain.id,
        user_id=user_id,
        symbol=lot_domain.symbol,
        created_from_fill_id=lot_domain.created_from_fill_id,
        created_at=lot_domain.created_at,
        qty_base_initial=lot_domain.qty_base_initial,
        qty_base_open=lot_domain.qty_base_open,
        cost_quote=lot_domain.cost_quote,
        cost_eur=lot_domain.cost_eur,
        status=LotStatusEnum[lot_domain.status.value],
        target_margin_pct=lot_domain.target_margin_pct,
        # EUR-quoted lots: rate = 1.0; BTC-quoted: None (set by sync_service after rate fetch)
        quote_to_eur_rate=Decimal("1") if lot_domain.cost_eur is not None else None,
    )

    db.add(lot_db)
    db.flush()
    db.refresh(lot_db)

    return _lot_db_to_dict(lot_db)


def process_sell_fill_fifo(
    db: Session,
    user_id: str,
    sell_event_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> dict:
    """
    Verarbeitet Sell-Fill mit FIFO Allocation

    Args:
        db: Database Session
        user_id: User ID
        sell_event_id: Sell Event ID (LedgerEvent)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency
                             z.B. {"BNB": Decimal("700.00")} fuer BNB/Quote-Preis

    Returns:
        Dict mit updated_lots und allocations

    Raises:
        ValueError: Wenn Event nicht gefunden oder nicht genug offene Lots
    """
    # Sell Event holen
    sell_event_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.id == sell_event_id, LedgerEventDB.user_id == user_id)
        .first()
    )

    if not sell_event_db:
        raise ValueError(f"Sell event {sell_event_id} not found")

    sell_event_domain = _db_event_to_domain(sell_event_db)
    base_symbols = _get_base_symbols_for_sell_event(sell_event_db)

    # Offene Lots holen (chronologisch sortiert für FIFO)
    # Row-Level Lock: verhindert Race Conditions bei konkurrierenden Sell-Fills
    lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_base_open > 0,
            TradeLotDB.symbol.in_(base_symbols),
        )
        .order_by(TradeLotDB.created_at.asc())
        .with_for_update()
        .all()
    )

    # Zu Domain Models konvertieren
    lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]

    # FIFO Allocation (Domain-Logik)
    updated_lots_domain, allocations_domain = allocate_sell_fifo(
        sell_event_domain, lots_domain, fee_conversion_rates
    )

    # In DB persistieren
    updated_lot_dicts = []
    for updated_lot in updated_lots_domain:
        # Lot in DB aktualisieren
        lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == updated_lot.id).first()
        if lot_db:
            lot_db.qty_base_open = updated_lot.qty_base_open
            lot_db.status = LotStatusEnum[updated_lot.status.value]
            updated_lot_dicts.append(_lot_db_to_dict(lot_db))

    # Allocations in DB speichern
    allocation_dicts = []
    for allocation in allocations_domain:
        alloc_db = SellAllocationDB(
            id=allocation.id,
            sell_fill_id=allocation.sell_fill_id,
            trade_lot_id=allocation.trade_lot_id,
            qty_allocated=allocation.qty_allocated,
            realized_pnl_quote=allocation.realized_pnl_quote,
            created_at=allocation.created_at,
        )
        db.add(alloc_db)
        allocation_dicts.append(
            {
                "id": allocation.id,
                "sell_fill_id": allocation.sell_fill_id,
                "trade_lot_id": allocation.trade_lot_id,
                "qty_allocated": str(allocation.qty_allocated),
                "realized_pnl_quote": str(allocation.realized_pnl_quote),
            }
        )

    db.flush()

    return {
        "updated_lots": updated_lot_dicts,
        "allocations": allocation_dicts,
    }


def process_sell_fill_lot_specific(
    db: Session,
    user_id: str,
    sell_event_id: str,
    target_lot_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> dict:
    """
    Verarbeitet Sell-Fill mit lot-spezifischer Allocation

    Allokiert den Sell primär an das Ziel-Lot.
    Overflow wird via FIFO an restliche offene Lots verteilt.

    Args:
        db: Database Session
        user_id: User ID
        sell_event_id: Sell Event ID (LedgerEvent)
        target_lot_id: ID des Ziel-Lots
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency

    Returns:
        Dict mit updated_lots und allocations
    """
    # Sell Event holen
    sell_event_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.id == sell_event_id, LedgerEventDB.user_id == user_id)
        .first()
    )
    if not sell_event_db:
        raise ValueError(f"Sell event {sell_event_id} not found")

    sell_event_domain = _db_event_to_domain(sell_event_db)
    base_symbols = _get_base_symbols_for_sell_event(sell_event_db)

    # Ziel-Lot holen
    # Row-Level Lock: verhindert Race Conditions bei konkurrierenden Sell-Fills
    target_lot_db = (
        db.query(TradeLotDB)
        .filter(TradeLotDB.id == target_lot_id, TradeLotDB.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not target_lot_db:
        raise ValueError(f"Target lot {target_lot_id} not found")

    target_lot_domain = _lot_db_to_domain(target_lot_db)

    # Restliche offene Lots für Overflow (FIFO)
    # Row-Level Lock: konsistent mit Target-Lot Lock
    remaining_lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_base_open > 0,
            TradeLotDB.id != target_lot_id,
            TradeLotDB.symbol.in_(base_symbols),
        )
        .order_by(TradeLotDB.created_at.asc())
        .with_for_update()
        .all()
    )
    remaining_lots_domain = [_lot_db_to_domain(lot_db) for lot_db in remaining_lots_db]

    # Lot-spezifische Allocation (Domain-Logik)
    updated_lots_domain, allocations_domain = allocate_sell_to_lot(
        sell_event_domain,
        target_lot_domain,
        remaining_lots_domain,
        fee_conversion_rates,
    )

    # In DB persistieren
    updated_lot_dicts = []
    for updated_lot in updated_lots_domain:
        lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == updated_lot.id).first()
        if lot_db:
            lot_db.qty_base_open = updated_lot.qty_base_open
            lot_db.status = LotStatusEnum[updated_lot.status.value]
            updated_lot_dicts.append(_lot_db_to_dict(lot_db))

    allocation_dicts = []
    for allocation in allocations_domain:
        alloc_db = SellAllocationDB(
            id=allocation.id,
            sell_fill_id=allocation.sell_fill_id,
            trade_lot_id=allocation.trade_lot_id,
            qty_allocated=allocation.qty_allocated,
            realized_pnl_quote=allocation.realized_pnl_quote,
            created_at=allocation.created_at,
        )
        db.add(alloc_db)
        allocation_dicts.append(
            {
                "id": allocation.id,
                "sell_fill_id": allocation.sell_fill_id,
                "trade_lot_id": allocation.trade_lot_id,
                "qty_allocated": str(allocation.qty_allocated),
                "realized_pnl_quote": str(allocation.realized_pnl_quote),
            }
        )

    db.flush()

    return {
        "updated_lots": updated_lot_dicts,
        "allocations": allocation_dicts,
    }


def process_sell_fill_for_pairing(
    db: Session,
    user_id: str,
    sell_event_id: str,
    pairing_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> dict:
    """
    Verarbeitet Sell-Fill mit Pairing-spezifischer Allocation.

    Allokiert den Sell an die spezifischen Lots des Pairings (priorisiert).
    Overflow wird via FIFO an restliche offene Lots verteilt.

    Args:
        db: Database Session
        user_id: User ID
        sell_event_id: Sell Event ID (LedgerEvent)
        pairing_id: Pairing ID (aus linked_pairing_id der Order)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency

    Returns:
        Dict mit updated_lots und allocations
    """
    # Sell Event holen
    sell_event_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.id == sell_event_id, LedgerEventDB.user_id == user_id)
        .first()
    )
    if not sell_event_db:
        raise ValueError(f"Sell event {sell_event_id} not found")

    sell_event_domain = _db_event_to_domain(sell_event_db)
    base_symbols = _get_base_symbols_for_sell_event(sell_event_db)

    # Pairing Items holen
    pairing_items = (
        db.query(PairingItemDB).filter(PairingItemDB.pairing_id == pairing_id).all()
    )

    if not pairing_items:
        logger.warning(
            "No pairing items found for pairing %s — falling back to FIFO", pairing_id
        )
        return process_sell_fill_fifo(db, user_id, sell_event_id, fee_conversion_rates)

    # Pairing-Lot-IDs extrahieren
    pairing_lot_ids = [item.lot_id for item in pairing_items]

    # Pairing-Lots laden (nur offene)
    # Row-Level Lock: verhindert Race Conditions bei konkurrierenden Sell-Fills
    pairing_lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.id.in_(pairing_lot_ids),
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_base_open > 0,
        )
        .with_for_update()
        .all()
    )

    # Sortierung beibehalten wie im Pairing definiert
    lot_order = {lot_id: i for i, lot_id in enumerate(pairing_lot_ids)}
    pairing_lots_db.sort(key=lambda lot: lot_order.get(lot.id, 999))

    pairing_lots_domain = [_lot_db_to_domain(lot_db) for lot_db in pairing_lots_db]

    # Restliche offene Lots fuer Overflow (nach User-Strategie sortiert, Pairing-Lots ausgeschlossen)
    # Row-Level Lock: konsistent mit Pairing-Lots Lock
    remaining_lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_base_open > 0,
            ~TradeLotDB.id.in_(pairing_lot_ids),
            TradeLotDB.symbol.in_(base_symbols),
        )
        .with_for_update()
        .all()
    )
    remaining_lots_domain = [_lot_db_to_domain(lot_db) for lot_db in remaining_lots_db]

    # Overflow-Lots nach User-Strategie sortieren
    overflow_strategy = _get_user_allocation_strategy(db, user_id)
    remaining_lots_domain = _sort_lots_by_strategy(
        remaining_lots_domain, overflow_strategy
    )

    # Pairing-Lots zuerst, dann Overflow-Lots (nach User-Strategie)
    all_lots = pairing_lots_domain + remaining_lots_domain

    net_proceeds_per_base = _compute_net_proceeds_per_base(
        sell_event_domain, fee_conversion_rates
    )

    updated_lots_domain, allocations_domain, remaining = _allocate_qty_to_lots(
        sell_event_domain, all_lots, sell_event_domain.amount, net_proceeds_per_base
    )

    from app.symbol_registry import get_min_base_precision

    min_prec = get_min_base_precision(sell_event_domain.symbol or "BTCEUR")
    if remaining > min_prec:
        raise ValueError(
            f"Not enough open lots to allocate sell. Remaining: {remaining}"
        )

    # In DB persistieren
    updated_lot_dicts = []
    for updated_lot in updated_lots_domain:
        lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == updated_lot.id).first()
        if lot_db:
            lot_db.qty_base_open = updated_lot.qty_base_open
            lot_db.status = LotStatusEnum[updated_lot.status.value]
            updated_lot_dicts.append(_lot_db_to_dict(lot_db))

    allocation_dicts = []
    for allocation in allocations_domain:
        alloc_db = SellAllocationDB(
            id=allocation.id,
            sell_fill_id=allocation.sell_fill_id,
            trade_lot_id=allocation.trade_lot_id,
            qty_allocated=allocation.qty_allocated,
            realized_pnl_quote=allocation.realized_pnl_quote,
            created_at=allocation.created_at,
        )
        db.add(alloc_db)
        allocation_dicts.append(
            {
                "id": allocation.id,
                "sell_fill_id": allocation.sell_fill_id,
                "trade_lot_id": allocation.trade_lot_id,
                "qty_allocated": str(allocation.qty_allocated),
                "realized_pnl_quote": str(allocation.realized_pnl_quote),
            }
        )

    db.flush()

    logger.info(
        "Pairing %s: allocated sell %s to %d lots (%d from pairing)",
        pairing_id,
        sell_event_id,
        len(allocation_dicts),
        len(pairing_lots_domain),
    )

    return {
        "updated_lots": updated_lot_dicts,
        "allocations": allocation_dicts,
    }


def _get_user_allocation_strategy(db: Session, user_id: str) -> AllocationStrategy:
    """Laedt die bevorzugte Sell-Allocation-Strategie des Users aus den Settings."""
    settings = (
        db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
    )

    if settings and settings.sell_allocation_strategy:
        try:
            return AllocationStrategy(settings.sell_allocation_strategy)
        except ValueError:
            logger.warning(
                "Invalid strategy '%s' for user %s, falling back to FIFO",
                settings.sell_allocation_strategy,
                user_id,
            )
    return AllocationStrategy.FIFO


def process_sell_fill_with_strategy(
    db: Session,
    user_id: str,
    sell_event_id: str,
    strategy: AllocationStrategy = AllocationStrategy.FIFO,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> dict:
    """
    Verarbeitet Sell-Fill mit konfigurierbarer Allocation Strategy.

    Args:
        db: Database Session
        user_id: User ID
        sell_event_id: Sell Event ID (LedgerEvent)
        strategy: Allocation Strategy (FIFO, LIFO, HIGHEST_COST)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency

    Returns:
        Dict mit updated_lots und allocations
    """
    sell_event_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.id == sell_event_id, LedgerEventDB.user_id == user_id)
        .first()
    )

    if not sell_event_db:
        raise ValueError(f"Sell event {sell_event_id} not found")

    sell_event_domain = _db_event_to_domain(sell_event_db)
    base_symbols = _get_base_symbols_for_sell_event(sell_event_db)

    # Row-Level Lock: verhindert Race Conditions bei konkurrierenden Sell-Fills
    lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_base_open > 0,
            TradeLotDB.symbol.in_(base_symbols),
        )
        .with_for_update()
        .all()
    )

    lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]

    updated_lots_domain, allocations_domain = allocate_sell_with_strategy(
        sell_event_domain, lots_domain, strategy, fee_conversion_rates
    )

    # In DB persistieren
    updated_lot_dicts = []
    for updated_lot in updated_lots_domain:
        lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == updated_lot.id).first()
        if lot_db:
            lot_db.qty_base_open = updated_lot.qty_base_open
            lot_db.status = LotStatusEnum[updated_lot.status.value]
            updated_lot_dicts.append(_lot_db_to_dict(lot_db))

    allocation_dicts = []
    for allocation in allocations_domain:
        alloc_db = SellAllocationDB(
            id=allocation.id,
            sell_fill_id=allocation.sell_fill_id,
            trade_lot_id=allocation.trade_lot_id,
            qty_allocated=allocation.qty_allocated,
            realized_pnl_quote=allocation.realized_pnl_quote,
            created_at=allocation.created_at,
        )
        db.add(alloc_db)
        allocation_dicts.append(
            {
                "id": allocation.id,
                "sell_fill_id": allocation.sell_fill_id,
                "trade_lot_id": allocation.trade_lot_id,
                "qty_allocated": str(allocation.qty_allocated),
                "realized_pnl_quote": str(allocation.realized_pnl_quote),
            }
        )

    db.flush()

    return {
        "updated_lots": updated_lot_dicts,
        "allocations": allocation_dicts,
    }


def process_sell_fill(
    db: Session,
    user_id: str,
    sell_event_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> dict:
    """
    Routing-Funktion: Entscheidet ob lot-spezifisch, pairing-spezifisch oder User-Strategie

    Prüft ob der Sell-Fill zu einer Order gehört:
    1. Order mit linked_lot_id → lot-spezifische Allocation
    2. Order mit linked_pairing_id → pairing-spezifische Allocation
    3. Sonst → FIFO Allocation (Default)

    Args:
        db: Database Session
        user_id: User ID
        sell_event_id: Sell Event ID (LedgerEvent)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu Quote-Currency

    Returns:
        Dict mit updated_lots und allocations
    """
    # Sell Event holen um orderId aus raw_payload zu extrahieren
    sell_event_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.id == sell_event_id, LedgerEventDB.user_id == user_id)
        .first()
    )

    if not sell_event_db:
        raise ValueError(f"Sell event {sell_event_id} not found")

    # Versuche orderId aus raw_payload zu extrahieren und Order finden
    linked_lot_id = None
    linked_pairing_id = None
    if sell_event_db.raw_payload and "orderId" in sell_event_db.raw_payload:
        binance_order_id = str(sell_event_db.raw_payload["orderId"])

        # Suche passende Order (mit lot_id ODER pairing_id)
        order_db = (
            db.query(OrderDB)
            .filter(
                OrderDB.binance_order_id == binance_order_id,
                OrderDB.user_id == user_id,
            )
            .first()
        )

        if order_db:
            linked_lot_id = order_db.linked_lot_id
            linked_pairing_id = order_db.linked_pairing_id

    # Priority 1: Lot-spezifische Allocation
    if linked_lot_id:
        target_lot_db = (
            db.query(TradeLotDB)
            .filter(TradeLotDB.id == linked_lot_id, TradeLotDB.user_id == user_id)
            .first()
        )

        if target_lot_db and target_lot_db.qty_base_open > 0:
            logger.info(
                "Sell %s linked to lot %s via order — using lot-specific allocation",
                sell_event_id,
                linked_lot_id,
            )
            return process_sell_fill_lot_specific(
                db, user_id, sell_event_id, linked_lot_id, fee_conversion_rates
            )
        else:
            logger.warning(
                "Sell %s linked to lot %s but lot is already closed — falling back to FIFO",
                sell_event_id,
                linked_lot_id,
            )

    # Priority 2: Pairing-spezifische Allocation
    if linked_pairing_id:
        logger.info(
            "Sell %s linked to pairing %s via order — using pairing-specific allocation",
            sell_event_id,
            linked_pairing_id,
        )
        return process_sell_fill_for_pairing(
            db, user_id, sell_event_id, linked_pairing_id, fee_conversion_rates
        )

    # Default: User-konfigurierte Strategie (Fallback: FIFO)
    strategy = _get_user_allocation_strategy(db, user_id)
    return process_sell_fill_with_strategy(
        db, user_id, sell_event_id, strategy, fee_conversion_rates
    )


def update_auto_order(db: Session, user_id: str, lot_id: str, enabled: bool) -> dict:
    """
    Updated auto_order_enabled für ein TradeLot

    Args:
        db: Database Session
        user_id: User ID
        lot_id: Lot ID
        enabled: True/False für auto-order

    Returns:
        Updated Lot als Dict

    Raises:
        ValueError: Wenn Lot nicht gefunden
    """
    lot_db = (
        db.query(TradeLotDB)
        .filter(TradeLotDB.id == lot_id, TradeLotDB.user_id == user_id)
        .first()
    )

    if not lot_db:
        raise ValueError(f"Lot {lot_id} not found")

    lot_db.auto_order_enabled = enabled
    db.flush()
    db.refresh(lot_db)

    return _lot_db_to_dict(lot_db)


def sync_and_refresh_lots(
    db: Session,
    user_id: str,
    binance_service: "BinanceService",
    symbol: str = "BTCEUR",
    start_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Synchronisiert Fills von Binance und gibt aktualisierte TradeLots zurück.

    Kombiniert Sync + Lot-Abfrage in einem Aufruf:
    1. Holt neue Fills von Binance
    2. Erstellt TradeLots / FIFO-Allocations
    3. Gibt alle offenen Lots mit Sync-Report zurück

    Args:
        db: Database Session
        user_id: User ID
        binance_service: Initialisierter BinanceService
        symbol: Trading Pair (Default: BTCEUR)
        start_time: Optional - nur Fills nach diesem Zeitpunkt

    Returns:
        Dict mit sync_report und aktualisierter lots-Liste
    """
    from app.services.sync_service import SyncService

    sync_service = SyncService(binance_service)
    sync_report = sync_service.sync_fills(db, user_id, symbol, start_time)

    # Fiat-Deposits und -Withdrawals (EUR SEPA) synchronisieren
    try:
        fiat_report = sync_service.sync_fiat(db, user_id, begin_time=start_time)
    except Exception as e:
        logger.warning("Fiat sync failed: %s", e)
        fiat_report = {"new_deposits": 0, "new_withdrawals": 0, "error": str(e)}

    sync_report["fiat_deposits"] = fiat_report.get("new_deposits", 0)
    sync_report["fiat_withdrawals"] = fiat_report.get("new_withdrawals", 0)
    if "error" in fiat_report:
        sync_report.setdefault("errors", []).append(
            f"Fiat sync: {fiat_report['error']}"
        )
        sync_report["fills_failed"] = sync_report.get("fills_failed", 0) + 1
        sync_report.setdefault("fill_details", []).append(
            {
                "source_id": "fiat_sync",
                "fill_id": "fiat_sync",
                "side": "N/A",
                "outcome": "FAILED",
                "error": fiat_report["error"],
            }
        )

    # Auto-reconciliation after sync (RECON-01)
    try:
        from app.services.reconciliation_service import ReconciliationService

        recon_service = ReconciliationService(binance_service)
        recon_result = recon_service.run_and_persist(
            db, user_id, symbol, trigger="post_sync"
        )
        sync_report["reconciliation"] = recon_result
    except Exception:
        logger.warning(
            "Auto-reconciliation failed after sync for user=%s", user_id
        )
        sync_report["reconciliation"] = {
            "status": "failed",
            "error": "Auto-reconciliation fehlgeschlagen",
        }

    # Alle Lots nach Sync abrufen (neueste zuerst)
    lots = get_lots_for_user(db, user_id)

    return {
        "sync_report": sync_report,
        "lots": lots,
        "lots_count": len(lots),
    }


def _lot_db_to_dict(lot_db: TradeLotDB, db: Session = None, fill_event=None) -> dict:
    """Konvertiert DB Model zu Dict, inkl. Binance Order ID und Import-Quelle aus raw_payload.

    Args:
        lot_db: TradeLotDB instance
        db: Optional DB Session (Fallback fuer Einzelabrufe)
        fill_event: Optional vorgeladenes LedgerEventDB (Batch-Load-Modus, vermeidet N+1)
    """
    binance_order_id = None
    import_source = None
    _fill = fill_event
    if _fill is None and db:
        _fill = (
            db.query(LedgerEventDB)
            .filter(LedgerEventDB.id == lot_db.created_from_fill_id)
            .first()
        )
    if _fill and _fill.raw_payload:
        binance_order_id = str(_fill.raw_payload.get("orderId", "")) or None
        import_source = _fill.raw_payload.get("import_source")

    return {
        "id": lot_db.id,
        "symbol": lot_db.symbol,
        "created_from_fill_id": lot_db.created_from_fill_id,
        "created_at": lot_db.created_at.isoformat(),
        "qty_base_initial": str(lot_db.qty_base_initial),
        "qty_base_open": str(lot_db.qty_base_open),
        "cost_quote": str(lot_db.cost_quote),
        "cost_eur": str(lot_db.cost_eur) if lot_db.cost_eur is not None else None,
        "break_even": (
            str(lot_db.cost_quote / lot_db.qty_base_initial)
            if lot_db.qty_base_initial
            else "0"
        ),
        "break_even_eur": (
            str(lot_db.cost_eur / lot_db.qty_base_initial)
            if lot_db.cost_eur is not None and lot_db.qty_base_initial
            else None
        ),
        "quote_to_eur_rate": str(lot_db.quote_to_eur_rate) if lot_db.quote_to_eur_rate else None,
        "status": lot_db.status.value,
        "target_margin_pct": (
            str(lot_db.target_margin_pct) if lot_db.target_margin_pct else None
        ),
        "auto_order_enabled": bool(lot_db.auto_order_enabled),
        "binance_order_id": binance_order_id,
        "import_source": import_source,
    }


def _lot_db_to_domain(lot_db: TradeLotDB) -> DomainLot:
    """Konvertiert DB Model zu Domain Model"""
    return DomainLot(
        id=lot_db.id,
        created_from_fill_id=lot_db.created_from_fill_id,
        created_at=lot_db.created_at,
        qty_base_initial=lot_db.qty_base_initial,
        qty_base_open=lot_db.qty_base_open,
        cost_quote=lot_db.cost_quote,
        cost_eur=lot_db.cost_eur,
        quote_to_eur_rate=lot_db.quote_to_eur_rate,
        status=LotStatus[lot_db.status.value],
        target_margin_pct=lot_db.target_margin_pct,
        symbol=lot_db.symbol,
    )


# ============================================================
# Lot Merge
# ============================================================


def _utcnow():
    """Naive UTC now."""
    from datetime import timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_mergeable_groups(db: Session, user_id: str) -> List[dict]:
    """
    Gibt Gruppen von OPEN Lots zurueck, die zusammengefasst werden koennen
    (gleiche binance_order_id, keine Orders/Allocations/Pairings).
    """
    from collections import defaultdict

    # 1. Alle OPEN Lots laden
    open_lots = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.status == LotStatusEnum.OPEN,
        )
        .all()
    )

    if not open_lots:
        return []

    # 2. Batch-Load Fill-Events fuer binance_order_id
    fill_ids = [lot.created_from_fill_id for lot in open_lots]
    fill_events = db.query(LedgerEventDB).filter(LedgerEventDB.id.in_(fill_ids)).all()
    fill_map = {e.id: e for e in fill_events}

    # 3. Nach binance_order_id gruppieren
    groups = defaultdict(list)
    for lot in open_lots:
        fill = fill_map.get(lot.created_from_fill_id)
        if fill and fill.raw_payload:
            order_id = str(fill.raw_payload.get("orderId", "")) or None
            if order_id:
                groups[order_id].append(lot)

    # 4. Constraint-Check: Lots mit Orders, Allocations, Pairings ausschliessen
    lot_ids = [lot.id for lot in open_lots]

    # Aktive Orders (nicht CANCELLED/REJECTED/EXPIRED)
    terminal_statuses = [
        OrderStatusEnum.CANCELLED,
        OrderStatusEnum.REJECTED,
        OrderStatusEnum.EXPIRED,
    ]
    lots_with_orders = set(
        row[0]
        for row in db.query(OrderDB.linked_lot_id)
        .filter(
            OrderDB.linked_lot_id.in_(lot_ids),
            ~OrderDB.status.in_(terminal_statuses),
        )
        .all()
    )

    lots_with_allocations = set(
        row[0]
        for row in db.query(SellAllocationDB.trade_lot_id)
        .filter(SellAllocationDB.trade_lot_id.in_(lot_ids))
        .all()
    )

    lots_in_pairings = set(
        row[0]
        for row in db.query(PairingItemDB.lot_id)
        .filter(PairingItemDB.lot_id.in_(lot_ids))
        .join(PairingDB)
        .filter(PairingDB.status != PairingStatusEnum.EXECUTED)
        .all()
    )

    # 5. Nur eligible Gruppen mit 2+ Lots
    result = []
    for order_id, lot_list in groups.items():
        eligible = [
            lot
            for lot in lot_list
            if lot.id not in lots_with_orders
            and lot.id not in lots_with_allocations
            and lot.id not in lots_in_pairings
        ]
        if len(eligible) >= 2:
            result.append(
                {
                    "binance_order_id": order_id,
                    "lots": [
                        _lot_db_to_dict(
                            lot, db, fill_event=fill_map.get(lot.created_from_fill_id)
                        )
                        for lot in eligible
                    ],
                    "total_qty_base": str(
                        sum(lot.qty_base_initial for lot in eligible)
                    ),
                    "total_cost_quote": str(sum(lot.cost_quote for lot in eligible)),
                }
            )

    return result


def merge_lots(db: Session, user_id: str, lot_ids: List[str]) -> dict:
    """
    Fasst die gegebenen Lots zu einem Keeper-Lot zusammen.

    1. Validiert Merge-Berechtigung (Domain-Logik)
    2. Berechnet aggregierte Werte (Domain-Logik)
    3. Aktualisiert Keeper-Lot
    4. Setzt gemergte Lots auf Status MERGED mit merged_into_lot_id
    5. Erstellt ADJUSTMENT LedgerEvent fuer Audit-Trail
    """
    import uuid

    # Lots laden
    lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.id.in_(lot_ids),
            TradeLotDB.user_id == user_id,
        )
        .all()
    )

    if len(lots_db) != len(lot_ids):
        found_ids = {lot.id for lot in lots_db}
        missing = set(lot_ids) - found_ids
        raise ValueError(f"Lots nicht gefunden: {missing}")

    # binance_order_ids aus Fill-Events extrahieren
    fill_ids = [lot.created_from_fill_id for lot in lots_db]
    fill_events = db.query(LedgerEventDB).filter(LedgerEventDB.id.in_(fill_ids)).all()
    fill_map = {e.id: e for e in fill_events}

    binance_order_ids = {}
    for lot in lots_db:
        fill = fill_map.get(lot.created_from_fill_id)
        if fill and fill.raw_payload:
            binance_order_ids[lot.id] = str(fill.raw_payload.get("orderId", "")) or None

    # Constraint-Check
    terminal_statuses = [
        OrderStatusEnum.CANCELLED,
        OrderStatusEnum.REJECTED,
        OrderStatusEnum.EXPIRED,
    ]
    lots_with_orders = set(
        row[0]
        for row in db.query(OrderDB.linked_lot_id)
        .filter(
            OrderDB.linked_lot_id.in_(lot_ids),
            ~OrderDB.status.in_(terminal_statuses),
        )
        .all()
    )
    lots_with_allocations = set(
        row[0]
        for row in db.query(SellAllocationDB.trade_lot_id)
        .filter(SellAllocationDB.trade_lot_id.in_(lot_ids))
        .all()
    )
    lots_in_pairings = set(
        row[0]
        for row in db.query(PairingItemDB.lot_id)
        .filter(PairingItemDB.lot_id.in_(lot_ids))
        .join(PairingDB)
        .filter(PairingDB.status != PairingStatusEnum.EXECUTED)
        .all()
    )

    # Domain-Validierung
    lots_domain = [_lot_db_to_domain(lot) for lot in lots_db]
    validation = validate_merge(
        lots_domain,
        binance_order_ids,
        lots_with_orders,
        lots_with_allocations,
        lots_in_pairings,
    )

    if not validation.valid:
        raise ValueError(f"Merge nicht moeglich: {'; '.join(validation.errors)}")

    # Domain-Berechnung
    keeper_domain = next(
        lot for lot in lots_domain if lot.id == validation.keeper_lot_id
    )
    to_merge_domain = [
        lot for lot in lots_domain if lot.id in validation.merged_lot_ids
    ]
    merge_result = compute_merge(keeper_domain, to_merge_domain)

    # Persistieren: Keeper aktualisieren
    keeper_db = next(lot for lot in lots_db if lot.id == validation.keeper_lot_id)
    keeper_db.qty_base_initial = merge_result.new_qty_base_initial
    keeper_db.qty_base_open = merge_result.new_qty_base_open
    keeper_db.cost_quote = merge_result.new_cost_quote

    # Persistieren: Gemergte Lots markieren
    now = _utcnow()
    for lot_db in lots_db:
        if lot_db.id in validation.merged_lot_ids:
            lot_db.status = LotStatusEnum.MERGED
            lot_db.merged_into_lot_id = validation.keeper_lot_id
            lot_db.merged_at = now
            lot_db.qty_base_open = Decimal("0")

    # Audit-Trail: ADJUSTMENT LedgerEvent
    binance_oid = next((v for v in binance_order_ids.values() if v), None)
    adjustment_event = LedgerEventDB(
        id=f"merge_{validation.keeper_lot_id}_{uuid.uuid4().hex[:8]}",
        user_id=user_id,
        type=EventTypeEnum.ADJUSTMENT,
        timestamp=now,
        asset=get_base_asset(keeper_domain.symbol),
        amount=Decimal("0"),
        source=EventSourceEnum.ADJUSTMENT,
        note=f"Lot merge: {validation.merged_lot_ids} -> {validation.keeper_lot_id}",
        raw_payload={
            "action": "LOT_MERGE",
            "keeper_lot_id": validation.keeper_lot_id,
            "merged_lot_ids": validation.merged_lot_ids,
            "binance_order_id": binance_oid,
            "before": {
                "keeper": {
                    "qty_initial": str(keeper_domain.qty_base_initial),
                    "qty_open": str(keeper_domain.qty_base_open),
                    "cost_quote": str(keeper_domain.cost_quote),
                },
                "merged": [
                    {
                        "lot_id": lot.id,
                        "qty_initial": str(lot.qty_base_initial),
                        "qty_open": str(lot.qty_base_open),
                        "cost_quote": str(lot.cost_quote),
                    }
                    for lot in to_merge_domain
                ],
            },
            "after": {
                "qty_initial": str(merge_result.new_qty_base_initial),
                "qty_open": str(merge_result.new_qty_base_open),
                "cost_quote": str(merge_result.new_cost_quote),
                "break_even": str(merge_result.new_break_even),
            },
        },
    )
    db.add(adjustment_event)
    db.flush()

    return {
        "keeper": _lot_db_to_dict(keeper_db, db),
        "merged_lot_ids": validation.merged_lot_ids,
        "merged_count": len(validation.merged_lot_ids),
    }
