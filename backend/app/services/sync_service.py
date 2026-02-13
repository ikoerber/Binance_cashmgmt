"""
Sync Service - Binance Fills → Ledger + TradeLots

Herzstück der Automation:
- Holt Fills von Binance
- Persistiert als Ledger Events
- Erstellt automatisch TradeLots (1 Fill = 1 Lot)
- Führt FIFO Allocation für Sells durch
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.services.binance import BinanceService
from app.services.lot_service import create_lot_from_buy_fill, process_sell_fill
from app.domain.models import LedgerEvent, TradeSide, EventType
from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum, TradeSideEnum


class SyncService:
    """
    Synchronisiert Binance Fills mit lokalem Ledger + TradeLots

    Idempotent: Doppelte Fills werden erkannt und übersprungen.
    """

    def __init__(self, binance_service: BinanceService):
        self.binance_service = binance_service

    def sync_fills(
        self,
        db: Session,
        user_id: str,
        symbol: str = "BTCEUR",
        start_time: datetime | None = None
    ) -> Dict[str, Any]:
        """
        Synchronisiert Fills von Binance

        Process:
        1. Hole Fills von Binance (ab start_time)
        2. Filtere bereits gesyncte Fills (Idempotenz)
        3. Persistiere neue Fills als Ledger Events
        4. Erstelle TradeLots für Buy-Fills
        5. Führe FIFO Allocation für Sell-Fills durch

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading Pair (Default: BTCEUR)
            start_time: Optional - nur Fills nach diesem Zeitpunkt

        Returns:
            Sync-Report Dict
        """
        # 1. Fills von Binance holen
        fills = self.binance_service.fetch_trades(symbol, start_time)

        # 2. Bereits vorhandene Fills filtern (Idempotenz)
        new_fills = self._filter_new_fills(db, user_id, fills)

        if not new_fills:
            return {
                "status": "success",
                "new_fills": 0,
                "new_lots": 0,
                "allocations": 0,
                "message": "No new fills to sync"
            }

        # 3. BNB-Preis für Fee-Konvertierung abrufen (falls BNB-Fees vorhanden)
        fee_conversion_rates = self._get_fee_conversion_rates(new_fills)

        # 4. Ledger Events persistieren
        created_events = []
        for fill in new_fills:
            event_db = self._persist_ledger_event(db, user_id, fill)
            created_events.append(event_db)

        db.commit()

        # 5. TradeLots und Allocations erstellen
        # WICHTIG: Erst ALLE Buy-Lots erstellen, dann Sells allokieren.
        # Grund: Sells können chronologisch vor Buys im gleichen Batch liegen
        # (z.B. Limit-Sell gefüllt um 03:00, Buy um 09:00), brauchen aber
        # die Lots aus diesen Buys für die FIFO Allocation.
        new_lots_count = 0
        allocations_count = 0
        errors = []

        # Phase 1: Alle Buy-Lots erstellen
        for event_db in created_events:
            if event_db.side == TradeSideEnum.BUY:
                try:
                    create_lot_from_buy_fill(db, user_id, event_db.id, fee_conversion_rates)
                    new_lots_count += 1
                except Exception as e:
                    errors.append(f"Error creating lot from buy fill {event_db.id}: {e}")

        # Phase 2: Sell-Fills chronologisch allokieren (FIFO)
        sell_events = sorted(
            [e for e in created_events if e.side == TradeSideEnum.SELL],
            key=lambda e: e.timestamp
        )
        for event_db in sell_events:
            try:
                result = process_sell_fill(db, user_id, event_db.id, fee_conversion_rates)
                allocations_count += len(result["allocations"])
            except Exception as e:
                errors.append(f"Error processing sell fill {event_db.id}: {e}")

        status = "success" if not errors else "partial_success"
        return {
            "status": status,
            "new_fills": len(new_fills),
            "new_lots": new_lots_count,
            "allocations": allocations_count,
            "errors": errors,
            "message": f"Synced {len(new_fills)} fills, created {new_lots_count} lots, {allocations_count} allocations"
                       + (f", {len(errors)} errors" if errors else "")
        }

    def sync_fiat(
        self,
        db: Session,
        user_id: str,
        begin_time: datetime | None = None,
    ) -> Dict[str, Any]:
        """
        Synchronisiert Fiat-Deposits und -Withdrawals (EUR SEPA) von Binance.

        Idempotent: Bereits vorhandene Events werden übersprungen (via source_id).

        Args:
            db: Database Session
            user_id: User ID
            begin_time: Optional - nur Events nach diesem Zeitpunkt

        Returns:
            Sync-Report Dict
        """
        # 1. Fiat-Events von Binance holen
        deposits = self.binance_service.fetch_fiat_deposit_history(begin_time=begin_time)
        withdrawals = self.binance_service.fetch_fiat_withdrawal_history(begin_time=begin_time)
        all_fiat = deposits + withdrawals

        # 2. Bereits vorhandene filtern (Idempotenz)
        new_events = self._filter_new_fills(db, user_id, all_fiat)

        if not new_events:
            return {
                "new_deposits": 0,
                "new_withdrawals": 0,
                "message": "No new fiat transactions"
            }

        # 3. Persistieren
        new_deposit_count = 0
        new_withdrawal_count = 0
        for event in new_events:
            self._persist_ledger_event(db, user_id, event)
            if event.amount >= 0:
                new_deposit_count += 1
            else:
                new_withdrawal_count += 1

        db.commit()

        logger.info(
            "Fiat sync for %s: %d deposits, %d withdrawals",
            user_id, new_deposit_count, new_withdrawal_count
        )

        return {
            "new_deposits": new_deposit_count,
            "new_withdrawals": new_withdrawal_count,
            "message": f"Synced {new_deposit_count} deposits, {new_withdrawal_count} withdrawals"
        }

    def _filter_new_fills(
        self,
        db: Session,
        user_id: str,
        fills: List[LedgerEvent]
    ) -> List[LedgerEvent]:
        """
        Filtert bereits gesyncte Fills (Idempotenz)

        Args:
            db: Database Session
            user_id: User ID
            fills: Liste von Fills

        Returns:
            Nur neue Fills
        """
        # Hole bereits vorhandene source_ids
        existing_source_ids = set(
            row[0] for row in
            db.query(LedgerEventDB.source_id)
            .filter(
                LedgerEventDB.user_id == user_id,
                LedgerEventDB.source_id.isnot(None)
            )
            .all()
        )

        # Filtere
        new_fills = [
            fill for fill in fills
            if fill.source_id not in existing_source_ids
        ]

        return new_fills

    def _get_fee_conversion_rates(self, fills: List[LedgerEvent]) -> Dict[str, Decimal]:
        """
        Holt Konvertierungsraten für Fee-Assets

        Prüft alle Fills und holt Preise für nicht-EUR Fee-Assets.

        Args:
            fills: Liste von Fills

        Returns:
            Dict mit Konvertierungsraten, z.B. {"BNB": Decimal("700.00")}
        """
        fee_assets = set()
        for fill in fills:
            if fill.fee_asset and fill.fee_asset not in ["EUR", "BTC"]:
                fee_assets.add(fill.fee_asset)

        rates = {}
        for asset in fee_assets:
            try:
                # Hole aktuellen Preis für Asset/EUR
                # HINWEIS: Dies ist eine Näherung, da wir den historischen Preis
                # zum Zeitpunkt des Trades bräuchten. Für v1 akzeptabel, da:
                # 1. Fees sind klein (~0.1% des Trade-Volumens)
                # 2. BNB-Preis ist relativ stabil
                # 3. Fehler ist minimal (~0.01% des Break-even)
                # TODO v2: Historische Preise verwenden
                symbol = f"{asset}EUR"
                price = self.binance_service.get_current_price(symbol)
                rates[asset] = price
                logger.info("Using current %s/EUR price: %s for fee conversion", asset, price)
            except Exception as e:
                logger.warning("Could not fetch %s/EUR price: %s", asset, e)
                # Fallback: Keine Konvertierung für dieses Asset
                continue

        return rates

    def _persist_ledger_event(
        self,
        db: Session,
        user_id: str,
        event: LedgerEvent
    ) -> LedgerEventDB:
        """
        Persistiert LedgerEvent in DB

        Args:
            db: Database Session
            user_id: User ID
            event: LedgerEvent (Domain Model)

        Returns:
            Persistiertes LedgerEventDB
        """
        event_db = LedgerEventDB(
            id=event.id,
            user_id=user_id,
            type=EventTypeEnum[event.type.value],
            timestamp=event.timestamp,
            asset=event.asset,
            amount=event.amount,
            symbol=event.symbol,
            price=event.price,
            side=TradeSideEnum[event.side.value] if event.side else None,
            fee_asset=event.fee_asset,
            fee_amount=event.fee_amount,
            source=EventSourceEnum[event.source.value],
            source_id=event.source_id,
            note=event.note,
            raw_payload=event.raw_payload,
        )

        db.add(event_db)
        return event_db
