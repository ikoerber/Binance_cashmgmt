"""Pairing Service - DB Integration für Pairing-Management"""
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import uuid

from app.domain.pairing import suggest_pairings, simulate_pairing, compute_dual_route_comparison
from app.domain.models import TradeLot as DomainLot, Pairing as DomainPairing, PairingItem, PairingStatus, utcnow
from app.symbol_registry import get_symbols_for_base_asset
from app.domain.orders import compute_pairing_order_params
from app.db.models import TradeLotDB, LotStatusEnum, PairingDB, PairingItemDB, PairingStatusEnum, UserSettingsDB
from app.services.lot_service import _lot_db_to_domain


def get_pairing_suggestions(
    db: Session,
    user_id: str,
    market_price: Decimal,
    threshold_pct: Decimal = Decimal("0.05"),
    symbol: str = "BTCEUR",
    base_asset: str | None = None,
) -> List[dict]:
    """
    Holt Pairing-Vorschläge für User

    Args:
        db: Database Session
        user_id: User ID
        market_price: Aktueller Marktpreis (EUR wenn base_asset gesetzt)
        threshold_pct: Zielmarge (z.B. 0.05 für 5%)
        symbol: Trading Pair (z.B. "BTCEUR")
        base_asset: Base-Asset fuer Cross-Pair (z.B. "XRP"). Wenn gesetzt,
                    werden Lots aller Symbols dieses Base-Assets geladen.

    Returns:
        Liste von Pairing-Vorschlägen
    """
    if base_asset is not None:
        # Cross-pair mode: Load lots from all symbols for this base asset
        symbols = get_symbols_for_base_asset(base_asset)
        lots_db = (
            db.query(TradeLotDB)
            .filter(
                TradeLotDB.user_id == user_id,
                TradeLotDB.symbol.in_(symbols),
                TradeLotDB.qty_base_open > 0,
            )
            .order_by(TradeLotDB.created_at.asc())
            .all()
        )

        lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]

        # Validate all lots have cost_eur (required for EUR-normalized P&L)
        for lot in lots_domain:
            if lot.cost_eur is None:
                raise ValueError(
                    f"Lot {lot.id} hat kein cost_eur -- EUR-Kostenumrechnung erforderlich"
                )

        # EUR-normalized pairing suggestions
        pairings = suggest_pairings(lots_domain, market_price, threshold_pct, use_eur_cost=True)
    else:
        # Single-pair mode: existing behavior unchanged
        lots_db = (
            db.query(TradeLotDB)
            .filter(
                TradeLotDB.user_id == user_id,
                TradeLotDB.symbol == symbol,
                TradeLotDB.qty_base_open > 0,
            )
            .order_by(TradeLotDB.created_at.asc())
            .all()
        )

        lots_domain = [_lot_db_to_domain(lot_db) for lot_db in lots_db]

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
    xrpbtc_price: Decimal | None = None,
    btceur_price: Decimal | None = None,
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
        xrpbtc_price: XRPBTC-Preis fuer Dual-Route-Vergleich (optional)
        btceur_price: BTCEUR-Preis fuer Dual-Route-Vergleich (optional)

    Returns:
        Simulation-Details inkl. planned_orders (und dual_route_comparison wenn Preise gegeben)
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

    result = {
        "pairing_id": pairing.id,
        "market_price": str(market_price),
        "total_base_to_sell": str(simulation.total_base_to_sell),
        "expected_proceeds_quote": str(simulation.expected_proceeds_quote),
        "expected_costs_quote": str(simulation.expected_costs_quote),
        "expected_realized_pnl_quote": str(simulation.expected_realized_pnl_quote),
        "affected_lots": simulation.affected_lots,
        "remaining_portfolio_base": str(simulation.remaining_portfolio_base),
        "remaining_portfolio_cost_quote": str(simulation.remaining_portfolio_cost_quote),
        "estimated_fee_quote": str(simulation.estimated_fee_quote),
        "fee_pct": str(simulation.fee_pct),
        "fee_buffer_pct": str(fee_buffer_pct),
        "planned_orders": [aggregated_order],
        "has_max_value_violation": has_max_value_violation,
        "max_order_value_eur": str(max_value),
    }

    # Dual-route comparison for cross-pair pairings
    if xrpbtc_price is not None and btceur_price is not None and pairing.base_asset is not None:
        drc = compute_dual_route_comparison(
            total_base=simulation.total_base_to_sell,
            xrpeur_price=market_price,
            xrpbtc_price=xrpbtc_price,
            btceur_price=btceur_price,
            fee_pct=fee_pct,
        )
        result["dual_route_comparison"] = {
            "route_direct": {
                "symbol": drc.route_direct.symbol,
                "sell_price": str(drc.route_direct.sell_price),
                "gross_proceeds_eur": str(drc.route_direct.gross_proceeds_eur),
                "fees_eur": str(drc.route_direct.fees_eur),
                "net_proceeds_eur": str(drc.route_direct.net_proceeds_eur),
                "conversion_rate": str(drc.route_direct.conversion_rate) if drc.route_direct.conversion_rate is not None else None,
                "fee_steps": drc.route_direct.fee_steps,
            },
            "route_indirect": {
                "symbol": drc.route_indirect.symbol,
                "sell_price": str(drc.route_indirect.sell_price),
                "gross_proceeds_eur": str(drc.route_indirect.gross_proceeds_eur),
                "fees_eur": str(drc.route_indirect.fees_eur),
                "net_proceeds_eur": str(drc.route_indirect.net_proceeds_eur),
                "conversion_rate": str(drc.route_indirect.conversion_rate) if drc.route_indirect.conversion_rate is not None else None,
                "fee_steps": drc.route_indirect.fee_steps,
            },
            "recommended_route": drc.recommended_route,
            "eur_difference": str(drc.eur_difference),
        }

    return result


def _pairing_to_dict(pairing: DomainPairing, market_price: Decimal) -> dict:
    """Konvertiert Pairing zu Dict"""
    result = {
        "id": pairing.id,
        "symbol": pairing.symbol,
        "base_asset": pairing.base_asset,
        "is_cross_pair": pairing.is_cross_pair,
        "threshold_pct": str(pairing.threshold_pct),
        "status": pairing.status.value,
        "created_at": pairing.created_at.isoformat() if pairing.created_at else None,
        "items": [
            {
                "lot_id": item.lot_id,
                "qty_base": str(item.qty_base),
                "cost_quote": str(item.cost_quote),
                "cost_eur": str(item.cost_eur) if item.cost_eur is not None else None,
                "lot_symbol": item.lot_symbol,
            }
            for item in pairing.items
        ],
        "net_cost": str(pairing.net_cost()),
        "net_qty_base": str(pairing.net_qty_base()),
        "net_value": str(pairing.net_value(market_price)),
        "net_pnl_quote": str(pairing.net_pnl(market_price)),
        "net_pnl_pct": str(pairing.net_pnl_pct(market_price)),
        "is_profitable": pairing.is_profitable(market_price),
    }

    # Include net_cost_eur for cross-pair pairings
    net_cost_eur = pairing.net_cost_eur()
    if net_cost_eur is not None:
        result["net_cost_eur"] = str(net_cost_eur)

    return result


# ============================================================================
# Pairing Persistence Functions
# ============================================================================


def _pairing_db_to_domain(pairing_db: PairingDB) -> DomainPairing:
    """Konvertiert PairingDB zu Domain Pairing"""
    items = [
        PairingItem(
            lot_id=item.lot_id,
            qty_base=item.qty_base,
            cost_quote=item.cost_quote,
            cost_eur=item.cost_eur,
            lot_symbol=item.lot_symbol,
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
        base_asset=pairing_db.base_asset,
    )


def create_pairing(
    db: Session,
    user_id: str,
    items: List[dict],
    threshold_pct: Decimal,
    symbol: str = "BTCEUR",
    base_asset: str | None = None,
) -> dict:
    """
    Erstellt und persistiert ein Pairing

    Args:
        db: Database Session
        user_id: User ID
        items: Liste von {lot_id, qty_base}
        threshold_pct: Zielmarge (z.B. 0.05 für 5%)
        symbol: Trading Pair (z.B. "BTCEUR")
        base_asset: Base-Asset fuer Cross-Pair (z.B. "XRP"), None fuer Single-Pair

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
        base_asset=base_asset,
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
            cost_quote = (lot_db.cost_quote / lot_db.qty_base_initial) * qty_base
        else:
            cost_quote = Decimal("0")

        # Cross-pair: Berechne cost_eur anteilig und speichere lot_symbol
        cost_eur = None
        lot_symbol = None
        if base_asset is not None:
            lot_symbol = lot_db.symbol
            if lot_db.cost_eur is not None and lot_db.qty_base_initial > 0:
                cost_eur = (lot_db.cost_eur / lot_db.qty_base_initial) * qty_base

        pairing_item = PairingItemDB(
            id=str(uuid.uuid4()),
            pairing_id=pairing_id,
            lot_id=item["lot_id"],
            qty_base=qty_base,
            cost_quote=cost_quote,
            cost_eur=cost_eur,
            lot_symbol=lot_symbol,
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
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    base_asset: str | None = None,
) -> List[dict]:
    """
    Listet alle Pairings für User

    Args:
        db: Database Session
        user_id: User ID
        status: Optional status filter (DRAFT, LOCKED, EXECUTED)
        symbol: Optional symbol filter (z.B. BTCEUR)
        base_asset: Optional base asset filter (z.B. XRP) -- filtert Cross-Pair Pairings

    Returns:
        Liste von Pairing dicts
    """
    query = db.query(PairingDB).filter(PairingDB.user_id == user_id)

    if status:
        query = query.filter(PairingDB.status == PairingStatusEnum[status])

    if symbol:
        query = query.filter(PairingDB.symbol == symbol)

    if base_asset:
        query = query.filter(PairingDB.base_asset == base_asset)

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
