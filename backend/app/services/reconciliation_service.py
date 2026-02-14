"""
Reconciliation Service - Synct Binance mit lokaler DB

Kritisch für Production: Detektiert Diskrepanzen zwischen Binance und lokaler DB.
"""
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.models import OrderDB, OrderStatusEnum, EventTypeEnum, LedgerEventDB
from app.services.binance import BinanceService
from app.services.order_tracking_service import OrderTrackingService
from app.services.sync_service import SyncService


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
        except Exception as e:
            report["errors"].append(f"Failed to fetch Binance orders: {str(e)}")
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
                    status_map = {
                        "NEW": "OPEN",
                        "PARTIALLY_FILLED": "PARTIALLY_FILLED",
                        "FILLED": "FILLED",
                        "CANCELED": "CANCELLED",
                        "REJECTED": "REJECTED",
                        "EXPIRED": "EXPIRED"
                    }

                    new_status = status_map.get(binance_status, "OPEN")

                    # Update if different
                    if order_db.status.value != new_status:
                        order_db.status = OrderStatusEnum[new_status]
                        order_db.raw_response = binance_order
                        report["status_updated"] += 1

                except Exception as e:
                    report["discrepancies"].append({
                        "order_id": order_db.id,
                        "client_order_id": order_db.client_order_id,
                        "binance_order_id": order_db.binance_order_id,
                        "issue": f"Order in DB but fetch failed: {str(e)}"
                    })

        db.flush()

        return report

    def reconcile_balances(
        self,
        db: Session,
        user_id: str,
        tolerance_btc: Decimal = Decimal("0.0001"),
        tolerance_eur: Decimal = Decimal("1.00")
    ) -> Dict[str, Any]:
        """
        Vergleicht Binance Balances mit berechneten Balances aus Ledger

        Args:
            db: Database Session
            user_id: User ID
            tolerance_btc: Acceptable BTC difference
            tolerance_eur: Acceptable EUR difference

        Returns:
            Balance reconciliation report
        """
        report = {
            "btc": {},
            "eur": {},
            "within_tolerance": True,
            "errors": []
        }

        # 1. Fetch Binance balances
        try:
            account = self.binance_service.client.get_account()
            binance_balances = {balance["asset"]: Decimal(balance["free"]) + Decimal(balance["locked"])
                               for balance in account["balances"]}

            btc_binance = binance_balances.get("BTC", Decimal("0"))
            eur_binance = binance_balances.get("EUR", Decimal("0"))

        except Exception as e:
            report["errors"].append(f"Failed to fetch Binance balances: {str(e)}")
            return report

        # 2. Calculate balances from ledger
        # BTC: Sum all BTC events (TRADE_FILL, DEPOSIT, WITHDRAWAL)
        ledger_events = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == "BTC"
        ).all()

        btc_calculated = Decimal("0")
        for event in ledger_events:
            if event.side:
                # TRADE_FILL
                if event.side.value == "BUY":
                    btc_calculated += event.amount
                elif event.side.value == "SELL":
                    btc_calculated -= event.amount
            elif event.type.value in ["DEPOSIT"]:
                btc_calculated += event.amount
            elif event.type.value in ["WITHDRAWAL"]:
                btc_calculated -= event.amount

            # Subtract BTC fees
            if event.fee_asset == "BTC":
                btc_calculated -= event.fee_amount if event.fee_amount else Decimal("0")

        # EUR: Sum all EUR events + EUR from BTC trades
        # 1. Direct EUR deposits/withdrawals
        ledger_events_eur = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == "EUR"
        ).all()

        eur_calculated = Decimal("0")
        for event in ledger_events_eur:
            if event.type.value in ["DEPOSIT"]:
                eur_calculated += event.amount
            elif event.type.value in ["WITHDRAWAL"]:
                eur_calculated -= event.amount

        # 2. EUR from BTC trades (BUY = spend EUR, SELL = receive EUR)
        btc_trades = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == "BTC",
            LedgerEventDB.type == EventTypeEnum.TRADE_FILL
        ).all()

        for trade in btc_trades:
            if trade.price and trade.amount:
                eur_value = trade.price * trade.amount
                if trade.side.value == "BUY":
                    eur_calculated -= eur_value  # Spent EUR
                elif trade.side.value == "SELL":
                    eur_calculated += eur_value  # Received EUR

        # 3. Subtract EUR fees
        all_events_with_eur_fees = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.fee_asset == "EUR"
        ).all()

        for event in all_events_with_eur_fees:
            if event.fee_amount:
                eur_calculated -= event.fee_amount

        # 3. Compare
        btc_diff = abs(btc_binance - btc_calculated)
        eur_diff = abs(eur_binance - eur_calculated)

        report["btc"] = {
            "binance": str(btc_binance),
            "calculated": str(btc_calculated),
            "diff": str(btc_diff),
            "within_tolerance": btc_diff <= tolerance_btc
        }

        report["eur"] = {
            "binance": str(eur_binance),
            "calculated": str(eur_calculated),
            "diff": str(eur_diff),
            "within_tolerance": eur_diff <= tolerance_eur
        }

        report["within_tolerance"] = (
            report["btc"]["within_tolerance"] and
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

        except Exception as e:
            report["errors"].append(f"Failed to sync fills: {str(e)}")

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
            "balances": self.reconcile_balances(db, user_id),
            "fills": self.reconcile_fills(db, user_id, symbol)
        }
