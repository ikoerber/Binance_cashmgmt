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
    allocate_sell_to_lot,
    calculate_lot_target_price,
    _compute_net_proceeds_per_btc,
    _allocate_qty_to_lots,
)
from app.domain.models import LotStatus, TradeLot as DomainLot
from app.db.models import TradeLotDB, SellAllocationDB, LedgerEventDB, LotStatusEnum, OrderDB, PairingItemDB

logger = logging.getLogger(__name__)
from app.services.portfolio_service import _db_event_to_domain


def get_lots_for_user(
    db: Session,
    user_id: str,
    status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
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

    if from_date:
        query = query.filter(TradeLotDB.created_at >= from_date)

    if to_date:
        query = query.filter(TradeLotDB.created_at <= to_date)

    lots_db = (
        query
        .order_by(desc(TradeLotDB.created_at))
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [_lot_db_to_dict(lot_db, db) for lot_db in lots_db]


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
            "realized_pnl_eur": str(alloc.realized_pnl_eur),
            "created_at": alloc.created_at.isoformat(),
        }
        for alloc in allocations_db
    ]

    return lot_dict


def create_lot_from_buy_fill(
    db: Session,
    user_id: str,
    fill_event_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> dict:
    """
    Erstellt TradeLot aus Buy-Fill Event

    Args:
        db: Database Session
        user_id: User ID
        fill_event_id: Fill Event ID (LedgerEvent)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR
                             z.B. {"BNB": Decimal("700.00")} für BNB/EUR-Preis

    Returns:
        Erstelltes Lot als Dict

    Raises:
        ValueError: Wenn Event nicht gefunden oder kein Buy-Fill
    """
    # Event aus DB holen
    event_db = (
        db.query(LedgerEventDB)
        .filter(
            LedgerEventDB.id == fill_event_id,
            LedgerEventDB.user_id == user_id
        )
        .first()
    )

    if not event_db:
        raise ValueError(f"Event {fill_event_id} not found")

    # Zu Domain Model konvertieren
    event_domain = _db_event_to_domain(event_db)

    # TradeLot erstellen (Domain-Logik)
    lot_domain = create_trade_lot_from_buy_fill(event_domain, fee_conversion_rates)

    # In DB persistieren
    lot_db = TradeLotDB(
        id=lot_domain.id,
        user_id=user_id,
        created_from_fill_id=lot_domain.created_from_fill_id,
        created_at=lot_domain.created_at,
        qty_btc_initial=lot_domain.qty_btc_initial,
        qty_btc_open=lot_domain.qty_btc_open,
        cost_eur=lot_domain.cost_eur,
        status=LotStatusEnum[lot_domain.status.value],
        target_margin_pct=lot_domain.target_margin_pct,
    )

    db.add(lot_db)
    db.flush()
    db.refresh(lot_db)

    return _lot_db_to_dict(lot_db)


def process_sell_fill_fifo(
    db: Session,
    user_id: str,
    sell_event_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> dict:
    """
    Verarbeitet Sell-Fill mit FIFO Allocation

    Args:
        db: Database Session
        user_id: User ID
        sell_event_id: Sell Event ID (LedgerEvent)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR
                             z.B. {"BNB": Decimal("700.00")} für BNB/EUR-Preis

    Returns:
        Dict mit updated_lots und allocations

    Raises:
        ValueError: Wenn Event nicht gefunden oder nicht genug offene Lots
    """
    # Sell Event holen
    sell_event_db = (
        db.query(LedgerEventDB)
        .filter(
            LedgerEventDB.id == sell_event_id,
            LedgerEventDB.user_id == user_id
        )
        .first()
    )

    if not sell_event_db:
        raise ValueError(f"Sell event {sell_event_id} not found")

    sell_event_domain = _db_event_to_domain(sell_event_db)

    # Offene Lots holen (chronologisch sortiert für FIFO)
    lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_btc_open > 0
        )
        .order_by(TradeLotDB.created_at.asc())
        .all()
    )

    # Zu Domain Models konvertieren
    lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]

    # FIFO Allocation (Domain-Logik)
    updated_lots_domain, allocations_domain = allocate_sell_fifo(
        sell_event_domain,
        lots_domain,
        fee_conversion_rates
    )

    # In DB persistieren
    updated_lot_dicts = []
    for updated_lot in updated_lots_domain:
        # Lot in DB aktualisieren
        lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == updated_lot.id).first()
        if lot_db:
            lot_db.qty_btc_open = updated_lot.qty_btc_open
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
            realized_pnl_eur=allocation.realized_pnl_eur,
            created_at=allocation.created_at,
        )
        db.add(alloc_db)
        allocation_dicts.append({
            "id": allocation.id,
            "sell_fill_id": allocation.sell_fill_id,
            "trade_lot_id": allocation.trade_lot_id,
            "qty_allocated": str(allocation.qty_allocated),
            "realized_pnl_eur": str(allocation.realized_pnl_eur),
        })

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
    fee_conversion_rates: dict[str, Decimal] | None = None
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
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR

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

    # Ziel-Lot holen
    target_lot_db = (
        db.query(TradeLotDB)
        .filter(TradeLotDB.id == target_lot_id, TradeLotDB.user_id == user_id)
        .first()
    )
    if not target_lot_db:
        raise ValueError(f"Target lot {target_lot_id} not found")

    target_lot_domain = _lot_db_to_domain(target_lot_db)

    # Restliche offene Lots für Overflow (FIFO)
    remaining_lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_btc_open > 0,
            TradeLotDB.id != target_lot_id
        )
        .order_by(TradeLotDB.created_at.asc())
        .all()
    )
    remaining_lots_domain = [_lot_db_to_domain(lot_db) for lot_db in remaining_lots_db]

    # Lot-spezifische Allocation (Domain-Logik)
    updated_lots_domain, allocations_domain = allocate_sell_to_lot(
        sell_event_domain,
        target_lot_domain,
        remaining_lots_domain,
        fee_conversion_rates
    )

    # In DB persistieren
    updated_lot_dicts = []
    for updated_lot in updated_lots_domain:
        lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == updated_lot.id).first()
        if lot_db:
            lot_db.qty_btc_open = updated_lot.qty_btc_open
            lot_db.status = LotStatusEnum[updated_lot.status.value]
            updated_lot_dicts.append(_lot_db_to_dict(lot_db))

    allocation_dicts = []
    for allocation in allocations_domain:
        alloc_db = SellAllocationDB(
            id=allocation.id,
            sell_fill_id=allocation.sell_fill_id,
            trade_lot_id=allocation.trade_lot_id,
            qty_allocated=allocation.qty_allocated,
            realized_pnl_eur=allocation.realized_pnl_eur,
            created_at=allocation.created_at,
        )
        db.add(alloc_db)
        allocation_dicts.append({
            "id": allocation.id,
            "sell_fill_id": allocation.sell_fill_id,
            "trade_lot_id": allocation.trade_lot_id,
            "qty_allocated": str(allocation.qty_allocated),
            "realized_pnl_eur": str(allocation.realized_pnl_eur),
        })

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
    fee_conversion_rates: dict[str, Decimal] | None = None
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
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR

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

    # Pairing Items holen
    pairing_items = (
        db.query(PairingItemDB)
        .filter(PairingItemDB.pairing_id == pairing_id)
        .all()
    )

    if not pairing_items:
        logger.warning(
            "No pairing items found for pairing %s — falling back to FIFO",
            pairing_id
        )
        return process_sell_fill_fifo(db, user_id, sell_event_id, fee_conversion_rates)

    # Pairing-Lot-IDs extrahieren
    pairing_lot_ids = [item.lot_id for item in pairing_items]

    # Pairing-Lots laden (nur offene)
    pairing_lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.id.in_(pairing_lot_ids),
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_btc_open > 0
        )
        .all()
    )

    # Sortierung beibehalten wie im Pairing definiert
    lot_order = {lot_id: i for i, lot_id in enumerate(pairing_lot_ids)}
    pairing_lots_db.sort(key=lambda lot: lot_order.get(lot.id, 999))

    pairing_lots_domain = [_lot_db_to_domain(lot_db) for lot_db in pairing_lots_db]

    # Restliche offene Lots fuer Overflow (FIFO, Pairing-Lots ausgeschlossen)
    remaining_lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_btc_open > 0,
            ~TradeLotDB.id.in_(pairing_lot_ids)
        )
        .order_by(TradeLotDB.created_at.asc())
        .all()
    )
    remaining_lots_domain = [_lot_db_to_domain(lot_db) for lot_db in remaining_lots_db]

    # Pairing-Lots zuerst, dann Overflow-Lots (FIFO)
    all_lots = pairing_lots_domain + remaining_lots_domain

    net_proceeds_per_btc = _compute_net_proceeds_per_btc(sell_event_domain, fee_conversion_rates)

    updated_lots_domain, allocations_domain, remaining = _allocate_qty_to_lots(
        sell_event_domain, all_lots, sell_event_domain.amount, net_proceeds_per_btc
    )

    if remaining > Decimal("0.00000001"):
        raise ValueError(
            f"Not enough open lots to allocate sell. Remaining: {remaining} BTC"
        )

    # In DB persistieren
    updated_lot_dicts = []
    for updated_lot in updated_lots_domain:
        lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == updated_lot.id).first()
        if lot_db:
            lot_db.qty_btc_open = updated_lot.qty_btc_open
            lot_db.status = LotStatusEnum[updated_lot.status.value]
            updated_lot_dicts.append(_lot_db_to_dict(lot_db))

    allocation_dicts = []
    for allocation in allocations_domain:
        alloc_db = SellAllocationDB(
            id=allocation.id,
            sell_fill_id=allocation.sell_fill_id,
            trade_lot_id=allocation.trade_lot_id,
            qty_allocated=allocation.qty_allocated,
            realized_pnl_eur=allocation.realized_pnl_eur,
            created_at=allocation.created_at,
        )
        db.add(alloc_db)
        allocation_dicts.append({
            "id": allocation.id,
            "sell_fill_id": allocation.sell_fill_id,
            "trade_lot_id": allocation.trade_lot_id,
            "qty_allocated": str(allocation.qty_allocated),
            "realized_pnl_eur": str(allocation.realized_pnl_eur),
        })

    db.flush()

    logger.info(
        "Pairing %s: allocated sell %s to %d lots (%d from pairing)",
        pairing_id, sell_event_id, len(allocation_dicts), len(pairing_lots_domain)
    )

    return {
        "updated_lots": updated_lot_dicts,
        "allocations": allocation_dicts,
    }


def process_sell_fill(
    db: Session,
    user_id: str,
    sell_event_id: str,
    fee_conversion_rates: dict[str, Decimal] | None = None
) -> dict:
    """
    Routing-Funktion: Entscheidet ob lot-spezifisch, pairing-spezifisch oder FIFO

    Prüft ob der Sell-Fill zu einer Order gehört:
    1. Order mit linked_lot_id → lot-spezifische Allocation
    2. Order mit linked_pairing_id → pairing-spezifische Allocation
    3. Sonst → FIFO Allocation (Default)

    Args:
        db: Database Session
        user_id: User ID
        sell_event_id: Sell Event ID (LedgerEvent)
        fee_conversion_rates: Optional dict mit Konvertierungsraten zu EUR

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

        if target_lot_db and target_lot_db.qty_btc_open > 0:
            logger.info(
                "Sell %s linked to lot %s via order — using lot-specific allocation",
                sell_event_id, linked_lot_id
            )
            return process_sell_fill_lot_specific(
                db, user_id, sell_event_id, linked_lot_id, fee_conversion_rates
            )
        else:
            logger.warning(
                "Sell %s linked to lot %s but lot is already closed — falling back to FIFO",
                sell_event_id, linked_lot_id
            )

    # Priority 2: Pairing-spezifische Allocation
    if linked_pairing_id:
        logger.info(
            "Sell %s linked to pairing %s via order — using pairing-specific allocation",
            sell_event_id, linked_pairing_id
        )
        return process_sell_fill_for_pairing(
            db, user_id, sell_event_id, linked_pairing_id, fee_conversion_rates
        )

    # Default: FIFO
    return process_sell_fill_fifo(db, user_id, sell_event_id, fee_conversion_rates)


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
        sync_report.setdefault("errors", []).append(f"Fiat sync: {fiat_report['error']}")

    # Alle Lots nach Sync abrufen (neueste zuerst)
    lots = get_lots_for_user(db, user_id)

    return {
        "sync_report": sync_report,
        "lots": lots,
        "lots_count": len(lots),
    }


def _lot_db_to_dict(lot_db: TradeLotDB, db: Session = None) -> dict:
    """Konvertiert DB Model zu Dict, inkl. Binance Order ID aus raw_payload"""
    binance_order_id = None
    if db:
        fill_event = (
            db.query(LedgerEventDB)
            .filter(LedgerEventDB.id == lot_db.created_from_fill_id)
            .first()
        )
        if fill_event and fill_event.raw_payload:
            binance_order_id = str(fill_event.raw_payload.get("orderId", "")) or None

    return {
        "id": lot_db.id,
        "created_from_fill_id": lot_db.created_from_fill_id,
        "created_at": lot_db.created_at.isoformat(),
        "qty_btc_initial": str(lot_db.qty_btc_initial),
        "qty_btc_open": str(lot_db.qty_btc_open),
        "cost_eur": str(lot_db.cost_eur),
        "break_even": str(lot_db.cost_eur / lot_db.qty_btc_initial) if lot_db.qty_btc_initial else "0",
        "status": lot_db.status.value,
        "target_margin_pct": str(lot_db.target_margin_pct) if lot_db.target_margin_pct else None,
        "auto_order_enabled": bool(lot_db.auto_order_enabled),
        "binance_order_id": binance_order_id,
    }


def _lot_db_to_domain(lot_db: TradeLotDB) -> DomainLot:
    """Konvertiert DB Model zu Domain Model"""
    return DomainLot(
        id=lot_db.id,
        created_from_fill_id=lot_db.created_from_fill_id,
        created_at=lot_db.created_at,
        qty_btc_initial=lot_db.qty_btc_initial,
        qty_btc_open=lot_db.qty_btc_open,
        cost_eur=lot_db.cost_eur,
        status=LotStatus[lot_db.status.value],
        target_margin_pct=lot_db.target_margin_pct,
    )
