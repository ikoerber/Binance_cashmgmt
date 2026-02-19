"""
Order Service - Automatische Order-Erstellung

Erstellt Limit-Sell-Orders auf Binance basierend auf Zielpreisen.
"""
import logging
import re
from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.constants import BINANCE_ORDER_STATUS_MAP
from app.services.binance import BinanceService
from app.services.order_tracking_service import OrderTrackingService
from app.services.pairing_service import get_pairing_by_id, lock_pairing, execute_pairing
from app.db.models import TradeLotDB, UserSettingsDB, OrderDB
from app.domain.lots import calculate_lot_target_price
from app.symbol_registry import get_base_precision, get_price_precision


# Re-Export aus Domain fuer Backward-Kompatibilitaet
from app.domain.orders import compute_pairing_order_params  # noqa: F401


class OrderService:
    """
    Automatische Order-Erstellung

    Idempotent: clientOrderId verhindert Doppel-Orders
    """

    def __init__(self, binance_service: BinanceService):
        self.binance_service = binance_service
        self.order_tracking = OrderTrackingService(binance_service)

    def create_limit_sell_for_lot(
        self,
        db: Session,
        user_id: str,
        lot_id: str,
        target_margin_pct: Decimal = Decimal("0.05"),
        fee_buffer_pct: Decimal = Decimal("0.002")
    ) -> Dict[str, Any]:
        """
        Erstellt Limit-Sell-Order für TradeLot mit vollständigem Tracking

        Args:
            db: Database Session
            user_id: User ID
            lot_id: TradeLot ID
            target_margin_pct: Zielmarge (z.B. 0.05 für 5%)
            fee_buffer_pct: Fee-Puffer (z.B. 0.002 für 0.2%)

        Returns:
            Order-Details with tracking

        Raises:
            ValueError: Wenn Lot nicht gefunden oder nicht genug BTC oder Duplikat
        """
        # Lot aus DB holen
        lot_db = (
            db.query(TradeLotDB)
            .filter(
                TradeLotDB.id == lot_id,
                TradeLotDB.user_id == user_id
            )
            .first()
        )

        if not lot_db:
            raise ValueError(f"Lot {lot_id} not found")

        if lot_db.qty_base_open <= 0:
            raise ValueError(f"Lot {lot_id} has no open quantity")

        if not lot_db.qty_base_initial or lot_db.qty_base_initial <= 0:
            raise ValueError(f"Lot {lot_id} has invalid initial quantity")

        # Symbol aus Lot lesen
        symbol = lot_db.symbol

        # Zielpreis berechnen
        break_even = lot_db.cost_eur / lot_db.qty_base_initial

        # Lot-spezifische Margin oder global
        margin = lot_db.target_margin_pct if lot_db.target_margin_pct else target_margin_pct

        target_price = break_even * (Decimal("1") + margin) * (Decimal("1") + fee_buffer_pct)

        # Binance Order Parameter validieren
        qty_base = lot_db.qty_base_open

        # Runde auf Binance-konforme Werte (aus Symbol Registry)
        price_prec = get_price_precision(symbol)
        base_prec = get_base_precision(symbol)
        price_quant = Decimal(10) ** -price_prec
        base_quant = Decimal(10) ** -base_prec
        target_price_rounded = target_price.quantize(price_quant)
        qty_base_rounded = qty_base.quantize(base_quant)

        # Client Order ID (idempotent!)
        # Format: {userId}_{lotId}_{targetPrice}_{qty}_{version}
        # Binance erlaubt nur: a-zA-Z0-9-_
        version = "v1"
        safe_user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id)
        safe_lot_id = re.sub(r'[^a-zA-Z0-9_-]', '', lot_id)
        client_order_id = f"{safe_user_id}_{safe_lot_id}_{int(target_price)}_{int(qty_base_rounded * Decimal('100000'))}_{version}"[:36]  # Max 36 chars

        # 1. Max Order Value pruefen
        order_value = qty_base_rounded * target_price_rounded
        settings = db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
        max_value = Decimal(str(settings.max_order_value_eur)) if settings else Decimal("1000")
        if order_value > max_value:
            raise ValueError(
                f"Order-Wert {order_value:.2f} EUR ueberschreitet Maximum von {max_value:.2f} EUR"
            )

        # 2. Check idempotency
        existing = self.order_tracking.check_idempotency(db, client_order_id)
        if existing:
            return {
                "status": "duplicate",
                "message": "Order with this client_order_id already exists",
                "order": existing
            }

        # 3. Create PENDING order record
        order_id = self.order_tracking.create_order_record(
            db,
            user_id=user_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side="SELL",
            order_type="TAKE_PROFIT_LIMIT",
            quantity=qty_base_rounded,
            price=target_price_rounded,
            stop_price=target_price_rounded,
            linked_lot_id=lot_id
        )

        # 3. Call Binance API
        try:
            binance_response = self.binance_service.client.create_order(
                symbol=symbol,
                side="SELL",
                type="TAKE_PROFIT_LIMIT",
                timeInForce="GTC",  # Good Till Cancel
                quantity=str(qty_base_rounded),
                price=str(target_price_rounded),
                stopPrice=str(target_price_rounded),
                newClientOrderId=client_order_id
            )

            # 4. Update to SUBMITTED/OPEN
            order = self.order_tracking.update_order_status(
                db,
                order_id=order_id,
                status="OPEN",
                binance_order_id=str(binance_response["orderId"]),
                raw_response=binance_response
            )

            return {
                "status": "success",
                "order": order,
                "lot_id": lot_id,
                "break_even": str(break_even),
                "target_margin_pct": str(margin),
            }

        except Exception as e:
            # 5. Verifikation: Existiert die Order trotzdem auf Binance?
            try:
                verified = self._verify_order_on_binance(db, order_id, client_order_id, symbol=symbol)
            except Exception:
                verified = None

            if verified:
                return {
                    "status": "success",
                    "warning": "Order verified on Binance after local error",
                    "order": verified,
                    "lot_id": lot_id,
                    "break_even": str(break_even),
                    "target_margin_pct": str(margin),
                }

            # Order existiert nicht auf Binance → REJECTED + Rollback
            try:
                self.order_tracking.update_order_status(
                    db,
                    order_id=order_id,
                    status="REJECTED",
                    error_message=f"Binance API error: {type(e).__name__}"
                )
            except Exception:
                logger.exception("Failed to mark order %s as REJECTED", order_id)
                db.rollback()
            logger.error("Order creation failed for lot %s: %s", lot_id, e)
            raise ValueError("Order-Erstellung auf Binance fehlgeschlagen")

    def create_limit_sell_for_pairing(
        self,
        db: Session,
        user_id: str,
        pairing_id: str,
        market_price: Decimal,
        fee_buffer_pct: Decimal = Decimal("0.002"),
        custom_sell_price: Decimal | None = None,
    ) -> Dict[str, Any]:
        """
        Erstellt eine aggregierte Limit-Sell-Order fuer ein Pairing.

        Alle Lots im Pairing werden zu einer einzigen Binance-Order zusammengefasst,
        da der Zielpreis (market_price + fee_buffer) fuer alle identisch ist.

        Args:
            db: Database Session
            user_id: User ID
            pairing_id: Pairing ID
            market_price: Aktueller Marktpreis (fuer sell price)
            fee_buffer_pct: Fee-Puffer (z.B. 0.002 fuer 0.2%)
            custom_sell_price: Optionaler benutzerdefinierter Verkaufspreis

        Returns:
            Dict mit erstellter Order

        Raises:
            ValueError: Bei Fehlern
        """
        # 0. Validate custom_sell_price
        if custom_sell_price is not None:
            if custom_sell_price.is_nan() or custom_sell_price.is_infinite():
                raise ValueError("custom_sell_price darf nicht NaN oder Infinity sein")
            if custom_sell_price <= 0:
                raise ValueError("custom_sell_price muss groesser als 0 sein")

        # 1. Load pairing
        pairing_domain = get_pairing_by_id(db, user_id, pairing_id)
        if not pairing_domain:
            raise ValueError(f"Pairing {pairing_id} not found")

        # 2. Lock pairing if still DRAFT (skip if already LOCKED)
        from app.db.models import PairingDB, PairingStatusEnum as _PSE
        pairing_db = db.query(PairingDB).filter(
            PairingDB.id == pairing_id, PairingDB.user_id == user_id
        ).first()
        if not pairing_db:
            raise ValueError(f"Pairing {pairing_id} not found in DB")
        if pairing_db.status == _PSE.DRAFT:
            try:
                lock_pairing(db, user_id, pairing_id)
            except ValueError as e:
                raise ValueError(f"Failed to lock pairing: {str(e)}")
        elif pairing_db.status != _PSE.LOCKED:
            raise ValueError(
                f"Pairing {pairing_id} must be DRAFT or LOCKED (current: {pairing_db.status.value})"
            )

        # 3. Validiere alle Lots und bestimme Symbol
        symbol = pairing_db.symbol
        for item in pairing_domain.items:
            lot_db = db.query(TradeLotDB).filter(TradeLotDB.id == item.lot_id).first()
            if not lot_db:
                raise ValueError(f"Lot {item.lot_id} not found")

        # 4. Berechne aggregierte Order-Parameter
        price_prec = get_price_precision(symbol)
        base_prec = get_base_precision(symbol)
        price_quant = Decimal(10) ** -price_prec
        base_quant = Decimal(10) ** -base_prec

        if custom_sell_price is not None:
            target_price_rounded = custom_sell_price.quantize(price_quant)
        else:
            target_price = market_price * (Decimal("1") + fee_buffer_pct)
            target_price_rounded = target_price.quantize(price_quant)

        total_qty = sum(item.qty_base for item in pairing_domain.items)
        total_qty_rounded = total_qty.quantize(base_quant)

        # Max Order Value pruefen
        order_value = total_qty_rounded * target_price_rounded
        settings = db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
        max_value = Decimal(str(settings.max_order_value_eur)) if settings else Decimal("1000")
        if order_value > max_value:
            raise ValueError(
                f"Order-Wert {order_value:.2f} EUR ueberschreitet Maximum von {max_value:.2f} EUR"
            )

        # 5. Client Order ID (idempotent, pro Pairing)
        version = "v1"
        safe_pairing_id = re.sub(r'[^a-zA-Z0-9_-]', '', pairing_id)[:12]
        client_order_id = f"{user_id}_pairing_{safe_pairing_id}_{int(target_price_rounded)}_{version}"[:36]

        # Check idempotency
        existing = self.order_tracking.check_idempotency(db, client_order_id)
        if existing:
            return {
                "status": "success",
                "pairing_id": pairing_id,
                "order": existing,
                "count": 1,
                "note": "Order already exists (idempotent)"
            }

        # 6. Create PENDING order record
        order_id = self.order_tracking.create_order_record(
            db,
            user_id=user_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side="SELL",
            order_type="TAKE_PROFIT_LIMIT",
            quantity=total_qty_rounded,
            price=target_price_rounded,
            stop_price=target_price_rounded,
            linked_pairing_id=pairing_id
        )

        # 7. Call Binance API
        try:
            binance_response = self.binance_service.client.create_order(
                symbol=symbol,
                side="SELL",
                type="TAKE_PROFIT_LIMIT",
                timeInForce="GTC",
                quantity=str(total_qty_rounded),
                price=str(target_price_rounded),
                stopPrice=str(target_price_rounded),
                newClientOrderId=client_order_id
            )

            # Update to OPEN
            order = self.order_tracking.update_order_status(
                db,
                order_id=order_id,
                status="OPEN",
                binance_order_id=str(binance_response["orderId"]),
                raw_response=binance_response
            )

        except Exception as e:
            # Verifikation: Existiert die Order trotzdem auf Binance?
            verified = self._verify_order_on_binance(db, order_id, client_order_id, symbol=symbol)
            if verified:
                order = verified
            else:
                # Order existiert nicht auf Binance → REJECTED
                self.order_tracking.update_order_status(
                    db,
                    order_id=order_id,
                    status="REJECTED",
                    error_message=f"Binance API error: {type(e).__name__}"
                )
                logger.error("Pairing order creation failed for pairing %s: %s", pairing_id, e)
                raise ValueError("Order-Erstellung auf Binance fehlgeschlagen")

        # 8. Mark pairing as EXECUTED
        try:
            execute_pairing(db, user_id, pairing_id)
        except Exception as e:
            logger.warning("Order placed but pairing status update failed: %s", e)

        return {
            "status": "success",
            "pairing_id": pairing_id,
            "order": order,
            "count": 1,
            "total_qty_base": str(total_qty_rounded),
            "lot_count": len(pairing_domain.items),
        }

    def _verify_order_on_binance(
        self,
        db: Session,
        order_id: str,
        client_order_id: str,
        symbol: str = "BTCEUR"
    ) -> Dict[str, Any] | None:
        """
        Prueft ob eine Order trotz Exception auf Binance existiert.

        Wird im Error-Pfad aufgerufen, BEVOR eine Order als REJECTED markiert wird.
        Verhindert, dass live auf Binance platzierte Orders faelschlicherweise
        als REJECTED in der lokalen DB landen.

        Args:
            db: Database Session
            order_id: Interne Order ID
            client_order_id: Idempotente Client Order ID
            symbol: Trading Pair

        Returns:
            Order-Dict wenn auf Binance gefunden, sonst None
        """
        try:
            binance_order = self.binance_service.client.get_order(
                symbol=symbol,
                origClientOrderId=client_order_id
            )

            binance_status = binance_order.get("status", "")
            internal_status = BINANCE_ORDER_STATUS_MAP.get(binance_status)

            if not internal_status:
                return None

            # Order existiert auf Binance - DB korrigieren
            logger.warning(
                "Order %s existiert auf Binance (Status: %s) trotz lokalem Fehler - korrigiere DB",
                client_order_id, binance_status
            )

            order = self.order_tracking.update_order_status(
                db,
                order_id=order_id,
                status=internal_status,
                binance_order_id=str(binance_order["orderId"]),
                raw_response=binance_order
            )
            return order

        except Exception as verify_err:
            logger.debug(
                "Verifikation fuer %s fehlgeschlagen: %s", client_order_id, verify_err
            )
            return None

    def cancel_order(
        self,
        db: Session,
        symbol: str,
        order_id: int
    ) -> Dict[str, Any]:
        """
        Cancelt eine Order auf Binance und aktualisiert lokale DB

        Args:
            db: Database Session
            symbol: Trading Pair
            order_id: Binance Order ID

        Returns:
            Cancel-Result
        """
        try:
            result = self.binance_service.client.cancel_order(
                symbol=symbol,
                orderId=order_id
            )

            # Lokale DB aktualisieren
            order_db = db.query(OrderDB).filter(
                OrderDB.binance_order_id == str(order_id)
            ).first()

            if order_db:
                self.order_tracking.update_order_status(
                    db,
                    order_id=order_db.id,
                    status="CANCELLED",
                    raw_response=result
                )

            return {
                "status": "cancelled",
                "order_id": result["orderId"],
                "symbol": result["symbol"]
            }
        except Exception as e:
            logger.error("Failed to cancel order %s: %s", order_id, e)
            raise ValueError("Order-Stornierung auf Binance fehlgeschlagen")

    def get_open_orders(
        self,
        symbol: str = "BTCEUR"
    ) -> list:
        """
        Holt alle offenen Orders

        Args:
            symbol: Trading Pair

        Returns:
            Liste offener Orders
        """
        try:
            orders = self.binance_service.client.get_open_orders(symbol=symbol)
            return orders
        except Exception as e:
            logger.error("Failed to get open orders for symbol %s: %s", symbol, e)
            raise ValueError("Offene Orders konnten nicht abgerufen werden")
