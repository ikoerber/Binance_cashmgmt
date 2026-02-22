"""
Reconciliation Service - Synct Binance mit lokaler DB

Kritisch für Production: Detektiert Diskrepanzen zwischen Binance und lokaler DB.
Persists reconciliation runs, creates alerts, provides history API.
"""
import json
import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.constants import BINANCE_ORDER_STATUS_MAP, map_binance_order_status
from app.db.models import (
    OrderDB,
    OrderStatusEnum,
    EventTypeEnum,
    LedgerEventDB,
    ReconciliationRunDB,
    AlertEventDB,
    UserSettingsDB,
)
from app.domain.reconciliation import evaluate_discrepancies
from app.services.binance import BinanceService
from app.services.order_tracking_service import OrderTrackingService
from app.services.sync_service import SyncService
from app.symbol_registry import get_base_asset, get_quote_asset

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
            binance_orders = self.binance_service.get_open_orders(symbol=symbol)
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
                    binance_order = self.binance_service.get_order(
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
        tolerance_quote: Decimal = Decimal("1.00")
    ) -> Dict[str, Any]:
        """
        Vergleicht Binance Balances mit berechneten Balances aus Ledger

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading Pair (Default: BTCEUR)
            tolerance_base: Acceptable base asset difference
            tolerance_quote: Acceptable quote asset difference

        Returns:
            Balance reconciliation report
        """
        base_asset = get_base_asset(symbol)
        quote_asset = get_quote_asset(symbol)
        report = {
            "base_asset": base_asset,
            "quote_asset": quote_asset,
            "base": {},
            "quote": {},
            "within_tolerance": True,
            "errors": []
        }

        # 1. Fetch Binance balances
        try:
            account = self.binance_service.get_account()
            binance_balances = {balance["asset"]: Decimal(balance["free"]) + Decimal(balance["locked"])
                               for balance in account["balances"]}

            base_binance = binance_balances.get(base_asset, Decimal("0"))
            quote_binance = binance_balances.get(quote_asset, Decimal("0"))

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

        # Quote: Sum all quote asset events + quote from base asset trades
        # 1. Direct quote asset events (DEPOSIT, WITHDRAWAL, EXTERNAL_CASHFLOW, ADJUSTMENT)
        ledger_events_quote = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == quote_asset
        ).all()

        quote_calculated = Decimal("0")
        for event in ledger_events_quote:
            if event.type.value == "DEPOSIT":
                quote_calculated += event.amount
            elif event.type.value == "WITHDRAWAL":
                quote_calculated -= event.amount
            elif event.type.value == "EXTERNAL_CASHFLOW":
                # EXTERNAL_CASHFLOW: positiv = Einzahlung, negativ = Auszahlung
                quote_calculated += event.amount
            elif event.type.value == "ADJUSTMENT":
                quote_calculated += event.amount

        # 2. Quote from base asset trades (BUY = spend quote, SELL = receive quote)
        base_trades = db.query(LedgerEventDB).filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.asset == base_asset,
            LedgerEventDB.type == EventTypeEnum.TRADE_FILL
        ).all()

        for trade in base_trades:
            if trade.price and trade.amount:
                quote_value = trade.price * trade.amount
                if trade.side.value == "BUY":
                    quote_calculated -= quote_value  # Spent quote
                elif trade.side.value == "SELL":
                    quote_calculated += quote_value  # Received quote

        # 3. Subtract quote fees (nur von TRADE_FILLs — bei Deposits/Withdrawals
        #    ist fee_amount ggf. bereits im amount enthalten)
        for trade in base_trades:
            if trade.fee_asset == quote_asset and trade.fee_amount:
                quote_calculated -= trade.fee_amount

        # 4. Compare
        base_diff = abs(base_binance - base_calculated)
        quote_diff = abs(quote_binance - quote_calculated)

        report["base"] = {
            "asset": base_asset,
            "binance": str(base_binance),
            "calculated": str(base_calculated),
            "diff": str(base_diff),
            "within_tolerance": base_diff <= tolerance_base
        }

        report["quote"] = {
            "asset": quote_asset,
            "binance": str(quote_binance),
            "calculated": str(quote_calculated),
            "diff": str(quote_diff),
            "within_tolerance": quote_diff <= tolerance_quote
        }

        report["within_tolerance"] = (
            report["base"]["within_tolerance"] and
            report["quote"]["within_tolerance"]
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

        Uses run_and_persist() for orders+balances (persisted),
        plus fills reconciliation separately (only manual full recon includes fills).

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading pair

        Returns:
            Complete reconciliation report (backward-compatible shape)
        """
        # Persist orders+balances via run_and_persist
        recon_result = self.run_and_persist(db, user_id, symbol, trigger="manual")

        # Fills reconciliation separately (only in manual full recon)
        fills_report = self.reconcile_fills(db, user_id, symbol)

        # Backward-compatible response shape
        report = recon_result.get("report", {})
        report["fills"] = fills_report

        return {
            "run_id": recon_result.get("run_id"),
            "orders": report.get("orders", {}),
            "balances": report.get("balances", {}),
            "fills": fills_report,
        }

    def run_and_persist(
        self,
        db: Session,
        user_id: str,
        symbol: str,
        trigger: str,
        tolerance_base: Optional[Decimal] = None,
        tolerance_quote: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Run reconciliation (balances + orders), persist as ReconciliationRunDB,
        create AlertEventDB rows for discrepancies.

        Auto-reconciliation should NEVER break the caller — all errors are caught
        and returned as a minimal error report.

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading pair
            trigger: "manual", "post_sync", "post_full_sync"
            tolerance_base: Base asset tolerance (None = load from settings or default)
            tolerance_quote: Quote asset tolerance (None = load from settings or default)

        Returns:
            Dict with run_id, trigger, status, has_discrepancies, alert_count, report
        """
        try:
            # Load thresholds from settings if not provided
            if tolerance_base is None or tolerance_quote is None:
                settings_base, settings_quote = self._load_user_thresholds(db, user_id)
                if tolerance_base is None:
                    tolerance_base = settings_base
                if tolerance_quote is None:
                    tolerance_quote = settings_quote

            # Run sub-reconciliations
            balance_report = self.reconcile_balances(
                db, user_id, symbol, tolerance_base, tolerance_quote
            )
            order_report = self.reconcile_orders(db, user_id, symbol)

            # Combine into report
            report = {
                "balances": balance_report,
                "orders": order_report,
            }

            # Evaluate discrepancies via domain function
            alerts = evaluate_discrepancies(
                balance_report, order_report, tolerance_base, tolerance_quote
            )

            # Determine status
            has_errors = bool(
                balance_report.get("errors") or order_report.get("errors")
            )
            status = "failed" if has_errors else "completed"
            has_discrepancies = len(alerts) > 0

            # Persist ReconciliationRunDB
            run_id = str(uuid.uuid4())
            run_db = ReconciliationRunDB(
                id=run_id,
                user_id=user_id,
                symbol=symbol,
                trigger=trigger,
                status=status,
                report_json=report,
                has_discrepancies=has_discrepancies,
            )
            db.add(run_db)

            # Persist AlertEventDB rows
            for alert in alerts:
                alert_db = AlertEventDB(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    reconciliation_run_id=run_id,
                    alert_type=alert["alert_type"],
                    severity=alert["severity"],
                    title=alert["title"],
                    details_json=alert.get("details_json"),
                )
                db.add(alert_db)

                # Structured JSON log for external monitoring (ELK, Datadog, etc.)
                logger.info(
                    "ALERT_EVENT %s",
                    json.dumps({
                        "event": "alert_created",
                        "alert_id": alert_db.id,
                        "user_id": user_id,
                        "alert_type": alert["alert_type"],
                        "severity": alert["severity"],
                        "title": alert["title"],
                        "details": alert.get("details_json"),
                        "reconciliation_run_id": run_id,
                        "timestamp": alert_db.created_at.isoformat() if alert_db.created_at else None,
                    }, default=str)
                )

            db.flush()

            # Structured JSON log for reconciliation run completion
            logger.info(
                "RECONCILIATION_RUN %s",
                json.dumps({
                    "event": "reconciliation_completed",
                    "run_id": run_id,
                    "user_id": user_id,
                    "trigger": trigger,
                    "status": status,
                    "has_discrepancies": has_discrepancies,
                    "alert_count": len(alerts),
                    "timestamp": run_db.created_at.isoformat() if run_db.created_at else None,
                }, default=str)
            )

            return {
                "run_id": run_id,
                "trigger": trigger,
                "status": status,
                "has_discrepancies": has_discrepancies,
                "alert_count": len(alerts),
                "report": report,
            }

        except Exception:
            logger.exception(
                "run_and_persist failed for user=%s, trigger=%s", user_id, trigger
            )
            return {
                "run_id": None,
                "trigger": trigger,
                "status": "failed",
                "has_discrepancies": False,
                "alert_count": 0,
                "report": {"error": "Reconciliation fehlgeschlagen"},
            }

    def get_reconciliation_history(
        self,
        db: Session,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Query past reconciliation runs for a user.

        Args:
            db: Database Session
            user_id: User ID
            limit: Max results (default 20)
            offset: Pagination offset

        Returns:
            Dict with 'runs' list and 'total' count
        """
        base_query = db.query(ReconciliationRunDB).filter(
            ReconciliationRunDB.user_id == user_id
        )

        total = base_query.count()

        runs_db = (
            base_query.order_by(ReconciliationRunDB.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        runs = []
        for run in runs_db:
            alert_count = (
                db.query(func.count(AlertEventDB.id))
                .filter(AlertEventDB.reconciliation_run_id == run.id)
                .scalar()
            )
            runs.append({
                "id": run.id,
                "symbol": run.symbol,
                "trigger": run.trigger,
                "status": run.status,
                "has_discrepancies": run.has_discrepancies,
                "alert_count": alert_count or 0,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            })

        return {"runs": runs, "total": total}

    def get_reconciliation_run(
        self, db: Session, user_id: str, run_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single reconciliation run with full report and alerts.

        IDOR-protected via user_id filter.

        Args:
            db: Database Session
            user_id: User ID
            run_id: Reconciliation run ID

        Returns:
            Dict with full run details or None if not found
        """
        run_db = (
            db.query(ReconciliationRunDB)
            .filter(
                ReconciliationRunDB.id == run_id,
                ReconciliationRunDB.user_id == user_id,
            )
            .first()
        )

        if not run_db:
            return None

        # Load associated alerts
        alerts_db = (
            db.query(AlertEventDB)
            .filter(AlertEventDB.reconciliation_run_id == run_id)
            .order_by(AlertEventDB.created_at.asc())
            .all()
        )

        alerts = [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "details_json": a.details_json,
                "acknowledged": a.acknowledged,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts_db
        ]

        return {
            "id": run_db.id,
            "user_id": run_db.user_id,
            "symbol": run_db.symbol,
            "trigger": run_db.trigger,
            "status": run_db.status,
            "has_discrepancies": run_db.has_discrepancies,
            "report_json": run_db.report_json,
            "alert_count": len(alerts),
            "alerts": alerts,
            "created_at": run_db.created_at.isoformat() if run_db.created_at else None,
        }

    @staticmethod
    def _load_user_thresholds(
        db: Session, user_id: str
    ) -> tuple[Decimal, Decimal]:
        """
        Load reconciliation tolerance thresholds from user settings.

        Returns (tolerance_base, tolerance_quote) with defaults if not configured.
        """
        default_base = Decimal("0.0001")
        default_quote = Decimal("1.00")

        settings = (
            db.query(UserSettingsDB)
            .filter(UserSettingsDB.user_id == user_id)
            .first()
        )

        if not settings:
            return default_base, default_quote

        tolerance_base = (
            settings.recon_tolerance_base
            if settings.recon_tolerance_base is not None
            else default_base
        )
        tolerance_quote = (
            settings.recon_tolerance_quote
            if settings.recon_tolerance_quote is not None
            else default_quote
        )

        return Decimal(str(tolerance_base)), Decimal(str(tolerance_quote))
