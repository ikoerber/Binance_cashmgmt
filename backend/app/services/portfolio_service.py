"""Portfolio Service - Verbindet Domain Logic mit DB"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session

from app.domain.models import LedgerEvent, PortfolioState, EventType, EventSource, TradeSide
from app.domain.portfolio import compute_portfolio_from_ledger, compute_daily_performance
from app.db.models import LedgerEventDB, TradeLotDB
from app.services.binance import BinanceService
from app.symbol_registry import get_base_asset

logger = logging.getLogger(__name__)


def get_portfolio_state(
    db: Session,
    user_id: str,
    market_price: Decimal,
    binance_service: Optional[BinanceService] = None,
    symbol: str = "BTCEUR",
) -> dict:
    """
    Holt Portfolio-Zustand für einen User

    BINANCE ALS SINGLE SOURCE OF TRUTH:
    - Base/Quote Balance kommt direkt von Binance
    - Break-even nur für getrackte Lots
    - "Alte" Base-Asset (vor App-Start) haben keinen Break-even

    Args:
        db: Database Session
        user_id: User ID
        market_price: Aktueller Marktpreis fuer das Symbol
        binance_service: Optional - für Live Balance von Binance
        symbol: Trading Pair (z.B. "BTCEUR")

    Returns:
        Dict mit Portfolio-KPIs
    """
    base_asset = get_base_asset(symbol)

    # 1. BINANCE BALANCE (Single Source of Truth)
    if binance_service:
        try:
            account = binance_service.client.get_account()
            binance_balances = {
                balance["asset"]: Decimal(balance["free"]) + Decimal(balance["locked"])
                for balance in account["balances"]
            }
            base_qty_binance = binance_balances.get(base_asset, Decimal("0"))
            eur_available_binance = binance_balances.get("EUR", Decimal("0"))
        except Exception:
            logger.warning("Failed to fetch Binance balances, falling back to ledger")
            base_qty_binance = None
            eur_available_binance = None
    else:
        base_qty_binance = None
        eur_available_binance = None

    # 2. GETRACKTE LOTS (für Break-even Berechnung)
    tracked_lots = db.query(TradeLotDB).filter(
        TradeLotDB.user_id == user_id,
        TradeLotDB.symbol == symbol,
        TradeLotDB.qty_base_open > 0
    ).all()

    tracked_base_qty = sum((lot.qty_base_open for lot in tracked_lots), Decimal("0"))
    tracked_cost_eur = sum((lot.cost_eur * (lot.qty_base_open / lot.qty_base_initial) for lot in tracked_lots), Decimal("0"))

    # Break-even nur für getrackte Lots
    tracked_break_even = tracked_cost_eur / tracked_base_qty if tracked_base_qty > 0 else None

    # 3. REALIZED P&L aus Ledger
    events_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.user_id == user_id)
        .order_by(LedgerEventDB.timestamp.asc())
        .all()
    )
    events = [_db_event_to_domain(e) for e in events_db]
    portfolio = compute_portfolio_from_ledger(events, symbol=symbol)

    # 4. FINAL VALUES (Binance > Ledger)
    base_qty_final = base_qty_binance if base_qty_binance is not None else portfolio.base_qty
    eur_final = eur_available_binance if eur_available_binance is not None else portfolio.eur_available

    # Zielpreis für getrackte Lots (inkl. Sell-Fee-Puffer)
    target_margin_pct = Decimal("0.05")
    fee_buffer_pct = Decimal("0.00075")  # 0,075% Binance Spot Fee mit BNB-Rabatt
    target_price = tracked_break_even * (Decimal("1") + target_margin_pct) * (Decimal("1") + fee_buffer_pct) if tracked_break_even else None

    # Unrealized P&L nur für getrackte Lots
    tracked_unrealized = (market_price * tracked_base_qty) - tracked_cost_eur if tracked_base_qty > 0 else Decimal("0")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "base_asset": base_asset,
        "base_qty": str(base_qty_final),  # ← Binance Balance
        "base_qty_tracked": str(tracked_base_qty),  # ← Nur getrackte Lots
        "base_cost_basis_eur": str(tracked_cost_eur),  # ← Nur getrackte Lots
        "break_even": str(tracked_break_even) if tracked_break_even else None,  # ← Nur getrackte
        "eur_available": str(eur_final),  # ← Binance Balance
        "market_price": str(market_price),
        "market_value_eur": str(base_qty_final * market_price),  # ← Gesamtwert
        "market_value_tracked_eur": str(tracked_base_qty * market_price),  # ← Nur getrackte
        "unrealized_pnl_eur": str(tracked_unrealized),  # ← Nur getrackte
        "realized_pnl_eur": str(portfolio.realized_pnl_eur),
        "external_net_eur": str(portfolio.external_net_eur),
        "target_price": str(target_price) if target_price else None,
        "target_margin_pct": str(target_margin_pct),
        "source": "binance" if base_qty_binance is not None else "ledger",
    }


def get_daily_performance(
    db: Session,
    user_id: str,
    market_price: Decimal,
    symbol: str = "BTCEUR",
) -> dict:
    """Holt Tages-Performance für einen User."""
    events_db = (
        db.query(LedgerEventDB)
        .filter(LedgerEventDB.user_id == user_id)
        .order_by(LedgerEventDB.timestamp.asc())
        .all()
    )
    events = [_db_event_to_domain(e) for e in events_db]

    daily = compute_daily_performance(events, market_price, symbol=symbol)

    return {
        "date": daily.date.isoformat(),
        "realized_pnl_today_eur": str(daily.realized_pnl_today_eur),
        "buys_count_today": daily.buys_count_today,
        "buys_volume_base_today": str(daily.buys_volume_base_today),
        "buys_volume_eur_today": str(daily.buys_volume_eur_today),
        "sells_count_today": daily.sells_count_today,
        "sells_volume_base_today": str(daily.sells_volume_base_today),
        "sells_volume_eur_today": str(daily.sells_volume_eur_today),
        "unrealized_pnl_start_of_day_eur": str(daily.unrealized_pnl_start_of_day_eur),
        "unrealized_pnl_current_eur": str(daily.unrealized_pnl_current_eur),
        "unrealized_pnl_change_eur": str(daily.unrealized_pnl_change_eur),
    }


def _db_event_to_domain(event_db: LedgerEventDB) -> LedgerEvent:
    """Konvertiert DB Model zu Domain Model"""
    return LedgerEvent(
        id=event_db.id,
        type=EventType[event_db.type.value],
        timestamp=event_db.timestamp,
        asset=event_db.asset,
        amount=event_db.amount,
        symbol=event_db.symbol,
        price=event_db.price,
        side=TradeSide[event_db.side.value] if event_db.side else None,
        fee_asset=event_db.fee_asset,
        fee_amount=event_db.fee_amount,
        fee_eur_value=event_db.fee_eur_value,
        source=EventSource[event_db.source.value],
        source_id=event_db.source_id,
        note=event_db.note,
        raw_payload=event_db.raw_payload,
    )
