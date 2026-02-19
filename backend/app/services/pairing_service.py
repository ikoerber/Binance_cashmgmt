"""Pairing Service - DB Integration für Pairing-Management"""
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import uuid

from app.domain.pairing import suggest_pairings, simulate_pairing
from app.domain.models import TradeLot as DomainLot, Pairing as DomainPairing, PairingItem, PairingStatus, utcnow
from app.domain.orders import compute_pairing_order_params
from app.db.models import TradeLotDB, LotStatusEnum, PairingDB, PairingItemDB, PairingStatusEnum, UserSettingsDB
from app.services.lot_service import _lot_db_to_domain


def get_pairing_suggestions(
    db: Session,
    user_id: str,
    market_price: Decimal,
    threshold_pct: Decimal = Decimal("0.05"),
    symbol: str = "BTCEUR",
) -> List[dict]:
    """
    Holt Pairing-Vorschläge für User

    Args:
        db: Database Session
        user_id: User ID
        market_price: Aktueller Marktpreis
        threshold_pct: Zielmarge (z.B. 0.05 für 5%)
        symbol: Trading Pair (z.B. "BTCEUR")

    Returns:
        Liste von Pairing-Vorschlägen
    """
    # Hole offene Lots fuer das Symbol
    lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.symbol == symbol,
            TradeLotDB.qty_base_open > 0
        )
        .order_by(TradeLotDB.created_at.asc())
        .all()
    )

    # Zu Domain Models konvertieren
    lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]

    # Pairing-Vorschläge generieren
    pairings = suggest_pairings(lots_domain, market_price, threshold_pct)

    # Zu Dicts konvertieren
    return [_pairing_to_dict(pairing, market_price) for pairing in pairings]


def simulate_pairing_execution(
    db: Session,
    user_id: str,
    pairing_id: str,
    market_price: Decimal,
    fee_pct: Decimal = Decimal("0.001"),
    fee_buffer_pct: Decimal = Decimal("0.002"),
    custom_sell_price: Decimal | None = None,
) -> dict:
    """
    Simuliert Pairing-Ausfuehrung inkl. geplanter Binance-Order-Parameter

    Args:
        db: Database Session
        user_id: User ID
        pairing_id: Pairing ID (von Suggestion)
        market_price: Aktueller Marktpreis
        fee_pct: Trading Fee (z.B. 0.001 fuer 0.1%)
        fee_buffer_pct: Fee-Puffer fuer Zielpreis (z.B. 0.002 fuer 0.2%)
        custom_sell_price: Optionaler benutzerdefinierter Verkaufspreis

    Returns:
        Simulation-Details inkl. planned_orders
    """
    # Pairing aus DB laden
    pairing = get_pairing_by_id(db, user_id, pairing_id)
    if not pairing:
        raise ValueError("No pairing found")

    # Hole offene Lots für Simulation (Portfolio-Kontext, gleiches Symbol)
    lots_db = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.user_id == user_id,
            TradeLotDB.qty_base_open > 0
        )
        .all()
    )

    lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]

    # Effektiven Verkaufspreis berechnen (fuer P&L-Berechnung)
    if custom_sell_price is not None:
        effective_sell_price = custom_sell_price
    else:
        effective_sell_price = market_price * (Decimal("1") + fee_buffer_pct)

    # Simulation durchführen (mit effektivem Verkaufspreis fuer korrekte P&L)
    simulation = simulate_pairing(pairing, market_price, lots_domain, fee_pct,
                                   sell_price=effective_sell_price)

    # Aggregierte Binance-Order-Parameter berechnen (eine Order fuer alle Lots)
    settings = db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
    max_value = Decimal(str(settings.max_order_value_eur)) if settings else Decimal("1000")

    aggregated_order = compute_pairing_order_params(
        pairing_id=pairing.id,
        user_id=user_id,
        items=pairing.items,
        market_price=market_price,
        fee_buffer_pct=fee_buffer_pct,
        max_order_value_eur=max_value,
        custom_sell_price=custom_sell_price,
    )

    has_max_value_violation = aggregated_order["exceeds_max_order_value"]

    return {
        "pairing_id": pairing.id,
        "market_price": str(market_price),
        "total_base_to_sell": str(simulation.total_base_to_sell),
        "expected_proceeds_eur": str(simulation.expected_proceeds_eur),
        "expected_costs_eur": str(simulation.expected_costs_eur),
        "expected_realized_pnl_eur": str(simulation.expected_realized_pnl_eur),
        "affected_lots": simulation.affected_lots,
        "remaining_portfolio_base": str(simulation.remaining_portfolio_base),
        "remaining_portfolio_cost_eur": str(simulation.remaining_portfolio_cost_eur),
        "estimated_fee_eur": str(simulation.estimated_fee_eur),
        "fee_pct": str(simulation.fee_pct),
        "fee_buffer_pct": str(fee_buffer_pct),
        "planned_orders": [aggregated_order],
        "has_max_value_violation": has_max_value_violation,
        "max_order_value_eur": str(max_value),
    }


def _pairing_to_dict(pairing: DomainPairing, market_price: Decimal) -> dict:
    """Konvertiert Pairing zu Dict"""
    return {
        "id": pairing.id,
        "symbol": pairing.symbol,
        "threshold_pct": str(pairing.threshold_pct),
        "status": pairing.status.value,
        "created_at": pairing.created_at.isoformat() if pairing.created_at else None,
        "items": [
            {
                "lot_id": item.lot_id,
                "qty_base": str(item.qty_base),
                "cost_eur": str(item.cost_eur),
            }
            for item in pairing.items
        ],
        "net_cost": str(pairing.net_cost()),
        "net_qty_base": str(pairing.net_qty_base()),
        "net_value": str(pairing.net_value(market_price)),
        "net_pnl_eur": str(pairing.net_pnl(market_price)),
        "net_pnl_pct": str(pairing.net_pnl_pct(market_price)),
        "is_profitable": pairing.is_profitable(market_price),
    }


# ============================================================================
# Pairing Persistence Functions
# ============================================================================


def _pairing_db_to_domain(pairing_db: PairingDB) -> DomainPairing:
    """Konvertiert PairingDB zu Domain Pairing"""
    items = [
        PairingItem(
            lot_id=item.lot_id,
            qty_base=item.qty_base,
            cost_eur=item.cost_eur
        )
        for item in pairing_db.items
    ]

    return DomainPairing(
        id=pairing_db.id,
        threshold_pct=pairing_db.threshold_pct,
        items=items,
        status=PairingStatus(pairing_db.status.value),
        created_at=pairing_db.created_at,
        symbol=pairing_db.symbol,
    )


def create_pairing(
    db: Session,
    user_id: str,
    items: List[dict],
    threshold_pct: Decimal,
    symbol: str = "BTCEUR",
) -> dict:
    """
    Erstellt und persistiert ein Pairing

    Args:
        db: Database Session
        user_id: User ID
        items: Liste von {lot_id, qty_base}
        threshold_pct: Zielmarge (z.B. 0.05 für 5%)
        symbol: Trading Pair (z.B. "BTCEUR")

    Returns:
        Pairing dict

    Raises:
        ValueError: Wenn Lots nicht existieren oder qty unzureichend
    """
    # Validierung mit Row-Level Lock: Verhindert Race Conditions bei
    # konkurrierenden Pairing-Erstellungen auf denselben Lots.
    lot_ids = [item["lot_id"] for item in items]
    locked_lots = (
        db.query(TradeLotDB)
        .filter(
            TradeLotDB.id.in_(lot_ids),
            TradeLotDB.user_id == user_id,
        )
        .with_for_update()
        .all()
    )
    lots_map = {lot.id: lot for lot in locked_lots}

    for item in items:
        lot_db = lots_map.get(item["lot_id"])
        if not lot_db:
            raise ValueError(f"Lot {item['lot_id']} not found")
        if lot_db.qty_base_open < item["qty_base"]:
            raise ValueError(f"Lot {item['lot_id']} has insufficient qty_base_open")

    # Symbol aus erstem Lot ableiten (falls nicht explizit uebergeben)
    if locked_lots:
        symbol = locked_lots[0].symbol

    # Erstelle Pairing
    pairing_id = str(uuid.uuid4())
    pairing_db = PairingDB(
        id=pairing_id,
        user_id=user_id,
        symbol=symbol,
        threshold_pct=threshold_pct,
        status=PairingStatusEnum.DRAFT,
        created_at=utcnow()
    )
    db.add(pairing_db)

    # Erstelle Pairing Items (Lots bereits gelocked und validiert)
    for item in items:
        lot_db = lots_map[item["lot_id"]]
        qty_base = Decimal(str(item["qty_base"]))

        # Anteilige Kosten berechnen
        if lot_db.qty_base_initial > 0:
            cost_eur = (lot_db.cost_eur / lot_db.qty_base_initial) * qty_base
        else:
            cost_eur = Decimal("0")

        pairing_item = PairingItemDB(
            id=str(uuid.uuid4()),
            pairing_id=pairing_id,
            lot_id=item["lot_id"],
            qty_base=qty_base,
            cost_eur=cost_eur
        )
        db.add(pairing_item)

    db.flush()
    db.refresh(pairing_db)

    # Konvertiere zu Domain und dann zu Dict
    domain_pairing = _pairing_db_to_domain(pairing_db)
    return _pairing_to_dict(domain_pairing, Decimal("0"))  # market_price irrelevant für DRAFT


def get_pairing_by_id(
    db: Session,
    user_id: str,
    pairing_id: str
) -> Optional[DomainPairing]:
    """
    Lädt Pairing aus DB

    Args:
        db: Database Session
        user_id: User ID
        pairing_id: Pairing ID

    Returns:
        Domain Pairing or None
    """
    pairing_db = db.query(PairingDB).filter(
        PairingDB.id == pairing_id,
        PairingDB.user_id == user_id
    ).first()

    if not pairing_db:
        return None

    return _pairing_db_to_domain(pairing_db)


def list_pairings(
    db: Session,
    user_id: str,
    status: Optional[str] = None
) -> List[dict]:
    """
    Listet alle Pairings für User

    Args:
        db: Database Session
        user_id: User ID
        status: Optional status filter (DRAFT, LOCKED, EXECUTED)

    Returns:
        Liste von Pairing dicts
    """
    query = db.query(PairingDB).filter(PairingDB.user_id == user_id)

    if status:
        query = query.filter(PairingDB.status == PairingStatusEnum[status])

    pairings_db = query.order_by(PairingDB.created_at.desc()).all()

    # Konvertiere zu Domain und dann zu Dict
    result = []
    for pairing_db in pairings_db:
        domain_pairing = _pairing_db_to_domain(pairing_db)
        result.append(_pairing_to_dict(domain_pairing, Decimal("0")))

    return result


def lock_pairing(
    db: Session,
    user_id: str,
    pairing_id: str
) -> dict:
    """
    Sperrt Pairing für Execution (DRAFT → LOCKED)

    Args:
        db: Database Session
        user_id: User ID
        pairing_id: Pairing ID

    Returns:
        Updated pairing dict

    Raises:
        ValueError: Wenn Pairing nicht DRAFT oder Lots nicht mehr verfügbar
    """
    pairing_db = db.query(PairingDB).filter(
        PairingDB.id == pairing_id,
        PairingDB.user_id == user_id
    ).first()

    if not pairing_db:
        raise ValueError(f"Pairing {pairing_id} not found")

    if pairing_db.status != PairingStatusEnum.DRAFT:
        raise ValueError(f"Pairing {pairing_id} is not in DRAFT status")

    # Validiere dass Lots noch verfügbar sind (mit Row-Level Lock)
    lot_ids = [item.lot_id for item in pairing_db.items]
    locked_lots = (
        db.query(TradeLotDB)
        .filter(TradeLotDB.id.in_(lot_ids), TradeLotDB.user_id == user_id)
        .with_for_update()
        .all()
    )
    lots_map = {lot.id: lot for lot in locked_lots}

    for item in pairing_db.items:
        lot_db = lots_map.get(item.lot_id)
        if not lot_db or lot_db.qty_base_open < item.qty_base:
            raise ValueError(f"Lot {item.lot_id} no longer has sufficient qty_base_open")

    # Lock
    pairing_db.status = PairingStatusEnum.LOCKED
    pairing_db.locked_at = utcnow()
    db.flush()
    db.refresh(pairing_db)

    domain_pairing = _pairing_db_to_domain(pairing_db)
    return _pairing_to_dict(domain_pairing, Decimal("0"))


def unlock_pairing(
    db: Session,
    user_id: str,
    pairing_id: str
) -> dict:
    """
    Entsperrt Pairing (LOCKED → DRAFT)
    """
    pairing_db = db.query(PairingDB).filter(
        PairingDB.id == pairing_id,
        PairingDB.user_id == user_id
    ).first()

    if not pairing_db:
        raise ValueError(f"Pairing {pairing_id} not found")

    if pairing_db.status != PairingStatusEnum.LOCKED:
        raise ValueError(f"Pairing {pairing_id} is not in LOCKED status")

    pairing_db.status = PairingStatusEnum.DRAFT
    pairing_db.locked_at = None
    db.flush()
    db.refresh(pairing_db)

    domain_pairing = _pairing_db_to_domain(pairing_db)
    return _pairing_to_dict(domain_pairing, Decimal("0"))


def execute_pairing(
    db: Session,
    user_id: str,
    pairing_id: str
) -> dict:
    """
    Markiert Pairing als EXECUTED (LOCKED → EXECUTED)

    Wird aufgerufen NACH erfolgreicher Order-Platzierung.

    Args:
        db: Database Session
        user_id: User ID
        pairing_id: Pairing ID

    Returns:
        Updated pairing dict

    Raises:
        ValueError: Wenn Pairing nicht LOCKED
    """
    pairing_db = db.query(PairingDB).filter(
        PairingDB.id == pairing_id,
        PairingDB.user_id == user_id
    ).first()

    if not pairing_db:
        raise ValueError(f"Pairing {pairing_id} not found")

    if pairing_db.status != PairingStatusEnum.LOCKED:
        raise ValueError(f"Pairing {pairing_id} is not in LOCKED status")

    # Execute
    pairing_db.status = PairingStatusEnum.EXECUTED
    pairing_db.executed_at = utcnow()
    db.flush()
    db.refresh(pairing_db)

    domain_pairing = _pairing_db_to_domain(pairing_db)
    return _pairing_to_dict(domain_pairing, Decimal("0"))


def delete_pairing(
    db: Session,
    user_id: str,
    pairing_id: str
) -> None:
    """
    Löscht ein Pairing (nur DRAFT Status)

    Args:
        db: Database Session
        user_id: User ID
        pairing_id: Pairing ID

    Raises:
        ValueError: Wenn Pairing nicht DRAFT
    """
    pairing_db = db.query(PairingDB).filter(
        PairingDB.id == pairing_id,
        PairingDB.user_id == user_id
    ).first()

    if not pairing_db:
        raise ValueError(f"Pairing {pairing_id} not found")

    if pairing_db.status != PairingStatusEnum.DRAFT:
        raise ValueError(f"Can only delete DRAFT pairings (current status: {pairing_db.status.value})")

    # Items werden via cascade delete automatisch gelöscht
    db.delete(pairing_db)
    db.flush()
