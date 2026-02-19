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
from app.domain.lots import compute_fee_eur_value
from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum, TradeSideEnum
from app.symbol_registry import get_base_asset, is_known_symbol


def persist_ledger_event(
    db: Session,
    user_id: str,
    event: LedgerEvent,
    fee_eur_value: Decimal | None = None,
) -> LedgerEventDB:
    """
    Persistiert ein LedgerEvent (Domain Model) als LedgerEventDB in der Datenbank.

    Gemeinsam genutzt von SyncService und CSV-Import.

    Args:
        db: Database Session
        user_id: User ID
        event: LedgerEvent (Domain Model)
        fee_eur_value: Vorberechneter EUR-Wert der Fee

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
        fee_eur_value=fee_eur_value,
        source=EventSourceEnum[event.source.value],
        source_id=event.source_id,
        note=event.note,
        raw_payload=event.raw_payload,
    )

    db.add(event_db)
    return event_db


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

        # 3. Historische Fee-Konvertierungsraten pro Fill abrufen
        per_fill_rates = self._get_per_fill_fee_conversion_rates(new_fills, symbol)

        # 4. Ledger Events persistieren (mit fee_eur_value)
        created_events = []
        for fill in new_fills:
            fill_rates = per_fill_rates.get(fill.id, {})
            fee_eur_value = compute_fee_eur_value(
                fill.fee_amount, fill.fee_asset, fill.price, fill_rates if fill_rates else None
            )
            event_db = self._persist_ledger_event(db, user_id, fill, fee_eur_value=fee_eur_value)
            created_events.append((event_db, fill_rates))

        db.flush()

        # 5. TradeLots und Allocations erstellen
        # WICHTIG: Erst ALLE Buy-Lots erstellen, dann Sells allokieren.
        # Grund: Sells können chronologisch vor Buys im gleichen Batch liegen
        # (z.B. Limit-Sell gefüllt um 03:00, Buy um 09:00), brauchen aber
        # die Lots aus diesen Buys für die FIFO Allocation.
        new_lots_count = 0
        allocations_count = 0
        errors = []

        # Phase 1: Alle Buy-Lots erstellen
        for event_db, fill_rates in created_events:
            if event_db.side == TradeSideEnum.BUY:
                try:
                    create_lot_from_buy_fill(db, user_id, event_db.id, fill_rates)
                    new_lots_count += 1
                except Exception as e:
                    errors.append(f"Error creating lot from buy fill {event_db.id}: {e}")

        # Phase 2: Sell-Fills chronologisch allokieren (FIFO)
        # WICHTIG: Bei Fehler ABBRECHEN — weitermachen wuerde FIFO-Invariante verletzen,
        # da nachfolgende Sells auf falschen Lots allokiert wuerden.
        sell_events = sorted(
            [(e, r) for e, r in created_events if e.side == TradeSideEnum.SELL],
            key=lambda pair: pair[0].timestamp
        )
        fifo_aborted = False
        for event_db, fill_rates in sell_events:
            try:
                result = process_sell_fill(db, user_id, event_db.id, fill_rates)
                allocations_count += len(result["allocations"])
            except Exception as e:
                errors.append(f"Error processing sell fill {event_db.id}: {e}")
                logger.error(
                    "FIFO allocation aborted: sell fill %s failed for user=%s. "
                    "Remaining sells skipped to preserve FIFO invariant.",
                    event_db.id, user_id
                )
                fifo_aborted = True
                break  # FIFO-Invariante schuetzen: nicht weitermachen

        if fifo_aborted:
            status = "fifo_error"
        elif errors:
            status = "partial_success"
        else:
            status = "success"
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

        db.flush()

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

    def _get_per_fill_fee_conversion_rates(
        self, fills: List[LedgerEvent], symbol: str = "BTCEUR"
    ) -> Dict[str, Dict[str, Decimal]]:
        """
        Holt historische Konvertierungsraten fuer Fee-Assets pro Fill.

        Fuer jeden Fill mit nicht-EUR/BTC Fee-Asset wird der historische
        Preis zum Fill-Zeitpunkt abgerufen. Fills innerhalb derselben
        Minute werden zusammengefasst (gleicher Kline-Preis).

        Args:
            fills: Liste von Fills

        Returns:
            Dict[fill_id, Dict[asset, Decimal]] - Per-fill conversion rates
        """
        base_asset = get_base_asset(symbol)
        fills_needing_conversion = [
            f for f in fills
            if f.fee_asset and f.fee_asset not in ["EUR", base_asset]
        ]

        if not fills_needing_conversion:
            return {}

        # Minuten-Cache: (asset, minute_key) -> price
        minute_cache: Dict[tuple, Decimal] = {}
        per_fill_rates: Dict[str, Dict[str, Decimal]] = {}

        for fill in fills_needing_conversion:
            asset = fill.fee_asset
            symbol = f"{asset}EUR"
            minute_key = fill.timestamp.strftime("%Y-%m-%d %H:%M")
            cache_key = (asset, minute_key)

            if cache_key not in minute_cache:
                try:
                    price = self.binance_service.get_historical_price(symbol, fill.timestamp)
                    minute_cache[cache_key] = price
                    logger.info(
                        "Historical %s/EUR price at %s: %s",
                        asset, minute_key, price
                    )
                except Exception as e:
                    logger.warning(
                        "Could not fetch historical %s/EUR price at %s: %s. Trying current price.",
                        asset, minute_key, e
                    )
                    try:
                        price = self.binance_service.get_current_price(symbol)
                        minute_cache[cache_key] = price
                        logger.info("Fallback: current %s/EUR price: %s", asset, price)
                    except Exception as e2:
                        logger.error(
                            "Fee-Konvertierung fehlgeschlagen fuer %s/EUR bei %s "
                            "(historisch + aktuell). fee_eur_value wird None — "
                            "Fee geht in Portfolio-Berechnung verloren. Fill: %s",
                            asset, minute_key, fill.id,
                        )
                        continue

            if cache_key in minute_cache:
                per_fill_rates[fill.id] = {asset: minute_cache[cache_key]}

        return per_fill_rates

    def _persist_ledger_event(
        self,
        db: Session,
        user_id: str,
        event: LedgerEvent,
        fee_eur_value: Decimal | None = None,
    ) -> LedgerEventDB:
        """Delegiert an die modul-level persist_ledger_event Funktion."""
        return persist_ledger_event(db, user_id, event, fee_eur_value)
