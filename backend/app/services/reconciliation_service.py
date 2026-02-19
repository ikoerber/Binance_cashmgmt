"""
Reconciliation Service - Synct Binance mit lokaler DB

Kritisch für Production: Detektiert Diskrepanzen zwischen Binance und lokaler DB.
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.constants import BINANCE_ORDER_STATUS_MAP, map_binance_order_status
from app.db.models import OrderDB, OrderStatusEnum, EventTypeEnum, LedgerEventDB
from app.services.binance import BinanceService
from app.services.order_tracking_service import OrderTrackingService
from app.services.sync_service import SyncService
from app.symbol_registry import get_base_asset

logger = logging.getLogger(__name__)


class ReconciliationService:
    """
    Reconciliation Service - Synct und vergleicht Binance mit lokaler DB

    Detektiert:
    - Order Status Diskrepanzen
    - Balance Differenzen
    - Fehlende Fills
    """

    def __init__(self, binance_service: BinanceService):
        self.binance_service = binance_service
        self.order_tracking = OrderTrackingService(binance_service)
        self.sync_service = SyncService(binance_service)

    def reconcile_orders(
        self,
        db: Session,
        user_id: str,
        symbol: str = "BTCEUR"
    ) -> Dict[str, Any]:
        """
        Synct Order Status von Binance

        Vergleicht:
        - Open/Partially Filled orders in DB mit Binance
        - Updated Status wenn anders
        - Flagged Diskrepanzen

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading pair

        Returns:
            Reconciliation report
        """
        report = {
            "synced": 0,
            "status_updated": 0,
            "discrepancies": [],
            "errors": []
        }

        # 1. Fetch open orders from Binance
        try:
            binance_orders = self.binance_service.client.get_open_orders(symbol=symbol)
            binance_order_ids = {str(order["orderId"]) for order in binance_orders}
        except Exception:
            logger.exception("Failed to fetch Binance open orders for user=%s", user_id)
            report["errors"].append("Binance-Orders konnten nicht abgerufen werden")
            return report

        # 2. Get all open/partially filled orders from DB
        db_orders = db.query(OrderDB).filter(
            OrderDB.user_id == user_id,
            OrderDB.symbol == symbol,
            OrderDB.status.in_([OrderStatusEnum.OPEN, OrderStatusEnum.PARTIALLY_FILLED])
        ).all()

        # 3. Sync each order
        for order_db in db_orders:
            if not order_db.binance_order_id:
                continue

            report["synced"] += 1

            # Check if order still exists on Binance
            if order_db.binance_order_id not in binance_order_ids:
                # Order not in open orders - might be filled/cancelled
                try:
                    # Fetch full order details
                    binance_order = self.binance_service.client.get_order(
                        symbol=symbol,
                        orderId=int(order_db.binance_order_id)
                    )

                    # Map Binance status
                    binance_status = binance_order["status"]
                    new_status = map_binance_order_status(binance_status)
                    if new_status is None:
                        report["discrepancies"].append({
                            "order_id": order_db.id,
                            "client_order_id": order_db.client_order_id,
                            "binance_order_id": order_db.binance_order_id,
                            "issue": f"Unknown Binance status: {binance_status}"
                        })
                        continue

                    # Update if different
                    if order_db.status.value != new_status:
                        order_db.status = OrderStatusEnum[new_status]
                        order_db.raw_response = binance_order
                        report["status_updated"] += 1

                except Exception:
                    logger.exception(
                        "Failed to fetch order details from Binance: order_id=%s, binance_order_id=%s",
                        order_db.id, order_db.binance_order_id,
                    )
                    report["discrepancies"].append({
                        "order_id": order_db.id,
                        "client_order_id": order_db.client_order_id,
                        "binance_order_id": order_db.binance_order_id,
                        "issue": "Order-Details konnten nicht von Binance abgerufen werden"
                    })

        db.flush()

        return report

    def reconcile_balances(
        self,
        db: Session,
        user_id: str,
        symbol: str = "BTCEUR",
        tolerance_base: Decimal = Decimal("0.0001"),
        tolerance_eur: Decimal = Decimal("1.00")
    ) -> Dict[str, Any]:
        """
        Vergleicht Binance Balances mit berechneten Balances aus Ledger

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading Pair (Default: BTCEUR)
            tolerance_base: Acceptable base asset difference
            tolerance_eur: Acceptable EUR difference

        Returns:
            Balance reconciliation report
        """
        base_asset = get_base_asset(symbol)
        report = {
            "base_asset": base_asset,
            "base": {},
            "eur": {},
            "within_tolerance": True,
            "errors": []
        }

        # 1. Fetch Binance balances
        try:
            account = self.binance_service.client.get_account()
            binance_balances = {balance["asset"]: Decimal(balance["free"]) + Decimal(balance["locked"])
                               for balance in account["balances"]}

            base_binance = binance_balances.get(base_asset, Decimal("0"))
            eur_binance = binance_balances.get("EUR", Decimal("0"))

        except Exception:
            logger.exception("Failed to fetch Binance balances for user=%s", user_id)
            report["errors"].append("Binance-Balances konnten nicht abgerufen werden")
            return report

        # 2. Calculate balances from ledger
        # Base asset: Sum all base asset events (TRADE_FILL, DEPOSIT, WITHDRAWAL, ADJUSTMENT)
        ledger_events = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == base_asset
        ).all()

        base_calculated = Decimal("0")
        for event in ledger_events:
            if event.side:
                # TRADE_FILL
                if event.side.value == "BUY":
                    base_calculated += event.amount
                elif event.side.value == "SELL":
                    base_calculated -= event.amount
            elif event.type.value == "DEPOSIT":
                base_calculated += event.amount
            elif event.type.value == "WITHDRAWAL":
                base_calculated -= event.amount
            elif event.type.value == "ADJUSTMENT":
                # ADJUSTMENT: amount kann positiv oder negativ sein
                base_calculated += event.amount

            # Subtract base asset fees
            if event.fee_asset == base_asset:
                base_calculated -= event.fee_amount if event.fee_amount else Decimal("0")

        # EUR: Sum all EUR events + EUR from base asset trades
        # 1. Direct EUR events (DEPOSIT, WITHDRAWAL, EXTERNAL_CASHFLOW, ADJUSTMENT)
        ledger_events_eur = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == "EUR"
        ).all()

        eur_calculated = Decimal("0")
        for event in ledger_events_eur:
            if event.type.value == "DEPOSIT":
                eur_calculated += event.amount
            elif event.type.value == "WITHDRAWAL":
                eur_calculated -= event.amount
            elif event.type.value == "EXTERNAL_CASHFLOW":
                # EXTERNAL_CASHFLOW: positiv = Einzahlung, negativ = Auszahlung
                eur_calculated += event.amount
            elif event.type.value == "ADJUSTMENT":
                eur_calculated += event.amount

        # 2. EUR from base asset trades (BUY = spend EUR, SELL = receive EUR)
        base_trades = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == base_asset,
            LedgerEventDB.type == EventTypeEnum.TRADE_FILL
        ).all()

        for trade in base_trades:
            if trade.price and trade.amount:
                eur_value = trade.price * trade.amount
                if trade.side.value == "BUY":
                    eur_calculated -= eur_value  # Spent EUR
                elif trade.side.value == "SELL":
                    eur_calculated += eur_value  # Received EUR

        # 3. Subtract EUR fees (nur von TRADE_FILLs — bei Deposits/Withdrawals
        #    ist fee_amount ggf. bereits im amount enthalten)
        for trade in base_trades:
            if trade.fee_asset == "EUR" and trade.fee_amount:
                eur_calculated -= trade.fee_amount

        # 4. Compare
        base_diff = abs(base_binance - base_calculated)
        eur_diff = abs(eur_binance - eur_calculated)

        report["base"] = {
            "asset": base_asset,
            "binance": str(base_binance),
            "calculated": str(base_calculated),
            "diff": str(base_diff),
            "within_tolerance": base_diff <= tolerance_base
        }

        report["eur"] = {
            "binance": str(eur_binance),
            "calculated": str(eur_calculated),
            "diff": str(eur_diff),
            "within_tolerance": eur_diff <= tolerance_eur
        }

        report["within_tolerance"] = (
            report["base"]["within_tolerance"] and
            report["eur"]["within_tolerance"]
        )

        return report

    def reconcile_fills(
        self,
        db: Session,
        user_id: str,
        symbol: str = "BTCEUR",
        start_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synct Fills from Binance

        Holt neue Fills und updated TradeLots via FIFO allocation.

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading pair
            start_time: Optional start time ISO string

        Returns:
            Fill sync report
        """
        report = {
            "new_fills": 0,
            "new_lots": 0,
            "allocations": 0,
            "errors": []
        }

        try:
            # Convert start_time from string to datetime if provided
            start_time_dt = None
            if start_time:
                start_time_dt = datetime.fromisoformat(start_time)

            # Use SyncService
            sync_result = self.sync_service.sync_fills(db, user_id, symbol, start_time_dt)

            report["new_fills"] = sync_result["new_fills"]
            report["new_lots"] = sync_result["new_lots"]
            report["allocations"] = sync_result["allocations"]

        except Exception:
            logger.exception("Failed to sync fills for user=%s, symbol=%s", user_id, symbol)
            report["errors"].append("Fills konnten nicht synchronisiert werden")

        return report

    def full_reconciliation(
        self,
        db: Session,
        user_id: str,
        symbol: str = "BTCEUR"
    ) -> Dict[str, Any]:
        """
        Runs full reconciliation (orders + balances + fills)

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading pair

        Returns:
            Complete reconciliation report
        """
        return {
            "orders": self.reconcile_orders(db, user_id, symbol),
            "balances": self.reconcile_balances(db, user_id, symbol),
            "fills": self.reconcile_fills(db, user_id, symbol)
        }
