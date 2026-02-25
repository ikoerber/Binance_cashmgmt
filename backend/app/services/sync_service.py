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
from app.domain.sync_result import SyncResult, FillResult, FillOutcome
from app.utils.fee_conversion import compute_fee_quote_value
from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum, TradeSideEnum, TradeLotDB
from app.symbol_registry import get_base_asset, get_quote_asset, is_eur_quoted


def persist_ledger_event(
    db: Session,
    user_id: str,
    event: LedgerEvent,
    fee_quote_value: Decimal | None = None,
) -> LedgerEventDB:
    """
    Persistiert ein LedgerEvent (Domain Model) als LedgerEventDB in der Datenbank.

    Gemeinsam genutzt von SyncService und CSV-Import.

    Args:
        db: Database Session
        user_id: User ID
        event: LedgerEvent (Domain Model)
        fee_quote_value: Vorberechneter Quote-Currency-Wert der Fee

    Returns:
        Persistiertes LedgerEventDB
    """
    event_db = LedgerEventDB(
        id=f"{user_id}_{event.id}",
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
        fee_quote_value=fee_quote_value,
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

        Returns a backward-compatible dict with additional per-fill tracking
        fields (fills_processed, fills_failed, fills_skipped_fifo,
        last_synced_source_id, fifo_aborted, fill_details).

        Args:
            db: Database Session
            user_id: User ID
            symbol: Trading Pair (Default: BTCEUR)
            start_time: Optional - nur Fills nach diesem Zeitpunkt

        Returns:
            Sync-Report Dict (via SyncResult.to_dict())
        """
        # 1. Fills von Binance holen
        fills = self.binance_service.fetch_trades(symbol, start_time)

        # 2. Bereits vorhandene Fills filtern (Idempotenz)
        new_fills = self._filter_new_fills(db, user_id, fills)

        if not new_fills:
            return SyncResult(
                fills_total=len(fills),
                fills_new=0,
            ).to_dict()

        # 3. Historische Fee-Konvertierungsraten pro Fill abrufen
        per_fill_rates = self._get_per_fill_fee_conversion_rates(new_fills, symbol)

        # 4. Ledger Events persistieren (mit fee_quote_value)
        quote_asset = get_quote_asset(symbol)
        # Track (event_db, fill_rates, original_fill) for per-fill result building
        created_events: List[tuple] = []
        for fill in new_fills:
            fill_rates = per_fill_rates.get(fill.id, {})
            fee_quote_value = compute_fee_quote_value(
                fill.fee_amount, fill.fee_asset, fill.price,
                fill_rates if fill_rates else None,
                quote_asset=quote_asset,
                base_asset=get_base_asset(symbol),
            )
            event_db = self._persist_ledger_event(db, user_id, fill, fee_quote_value=fee_quote_value)
            created_events.append((event_db, fill_rates, fill))

        db.flush()

        # 5. TradeLots und Allocations erstellen with per-fill tracking
        # WICHTIG: Erst ALLE Buy-Lots erstellen, dann Sells allokieren.
        # Grund: Sells können chronologisch vor Buys im gleichen Batch liegen
        # (z.B. Limit-Sell gefüllt um 03:00, Buy um 09:00), brauchen aber
        # die Lots aus diesen Buys für die FIFO Allocation.
        new_lots_count = 0
        allocations_count = 0
        fill_results: List[FillResult] = []

        # Minuten-Cache fuer historische BTC/EUR Raten (non-EUR-quoted pairs)
        btceur_minute_cache: Dict[str, Decimal] = {}

        # Phase 1: Alle Buy-Lots erstellen
        for event_db, fill_rates, original_fill in created_events:
            if event_db.side == TradeSideEnum.BUY:
                try:
                    create_lot_from_buy_fill(db, user_id, event_db.id, fill_rates)
                    new_lots_count += 1

                    # Fuer non-EUR-quoted Pairs: Historische BTC/EUR Rate abrufen
                    # und cost_eur + quote_to_eur_rate auf dem Lot setzen
                    if not is_eur_quoted(symbol):
                        self._enrich_lot_with_eur_rate(
                            db, event_db, symbol, btceur_minute_cache
                        )

                    fill_results.append(FillResult(
                        source_id=original_fill.source_id,
                        fill_id=event_db.id,
                        side="BUY",
                        outcome=FillOutcome.PROCESSED,
                        timestamp=original_fill.timestamp,
                    ))
                except Exception as e:
                    fill_results.append(FillResult(
                        source_id=original_fill.source_id,
                        fill_id=event_db.id,
                        side="BUY",
                        outcome=FillOutcome.FAILED,
                        error=f"Error creating lot from buy fill {event_db.id}: {e}",
                        timestamp=original_fill.timestamp,
                    ))

        # Phase 2: Sell-Fills chronologisch allokieren (FIFO)
        # WICHTIG: Bei Fehler ABBRECHEN — weitermachen wuerde FIFO-Invariante verletzen,
        # da nachfolgende Sells auf falschen Lots allokiert wuerden.
        sell_events = sorted(
            [(e, r, f) for e, r, f in created_events if e.side == TradeSideEnum.SELL],
            key=lambda triple: triple[0].timestamp
        )
        fifo_aborted = False
        for idx, (event_db, fill_rates, original_fill) in enumerate(sell_events):
            try:
                result = process_sell_fill(db, user_id, event_db.id, fill_rates)
                allocations_count += len(result["allocations"])
                fill_results.append(FillResult(
                    source_id=original_fill.source_id,
                    fill_id=event_db.id,
                    side="SELL",
                    outcome=FillOutcome.PROCESSED,
                    timestamp=original_fill.timestamp,
                ))
            except Exception as e:
                fill_results.append(FillResult(
                    source_id=original_fill.source_id,
                    fill_id=event_db.id,
                    side="SELL",
                    outcome=FillOutcome.FAILED,
                    error=f"Error processing sell fill {event_db.id}: {e}",
                    timestamp=original_fill.timestamp,
                ))
                logger.error(
                    "FIFO allocation aborted: sell fill %s failed for user=%s. "
                    "Remaining sells skipped to preserve FIFO invariant.",
                    event_db.id, user_id
                )
                fifo_aborted = True
                # Mark remaining sells as SKIPPED_FIFO
                for remaining_event_db, _, remaining_fill in sell_events[idx + 1:]:
                    fill_results.append(FillResult(
                        source_id=remaining_fill.source_id,
                        fill_id=remaining_event_db.id,
                        side="SELL",
                        outcome=FillOutcome.SKIPPED_FIFO,
                        timestamp=remaining_fill.timestamp,
                    ))
                break  # FIFO-Invariante schuetzen: nicht weitermachen

        # Build SyncResult with per-fill tracking
        fills_processed = sum(1 for fr in fill_results if fr.outcome == FillOutcome.PROCESSED)
        fills_failed = sum(1 for fr in fill_results if fr.outcome == FillOutcome.FAILED)
        fills_skipped_fifo = sum(1 for fr in fill_results if fr.outcome == FillOutcome.SKIPPED_FIFO)

        sync_result = SyncResult(
            fills_total=len(fills),
            fills_new=len(new_fills),
            fills_processed=fills_processed,
            fills_failed=fills_failed,
            fills_skipped_fifo=fills_skipped_fifo,
            new_lots=new_lots_count,
            allocations=allocations_count,
            fill_results=fill_results,
            fifo_aborted=fifo_aborted,
        )

        return sync_result.to_dict()

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
        quote_asset = get_quote_asset(symbol)
        fills_needing_conversion = [
            f for f in fills
            if f.fee_asset and f.fee_asset not in [quote_asset, base_asset]
        ]

        if not fills_needing_conversion:
            return {}

        # Minuten-Cache: (asset, minute_key) -> price
        minute_cache: Dict[tuple, Decimal] = {}
        per_fill_rates: Dict[str, Dict[str, Decimal]] = {}

        for fill in fills_needing_conversion:
            asset = fill.fee_asset
            fee_pair = f"{asset}{quote_asset}"
            minute_key = fill.timestamp.strftime("%Y-%m-%d %H:%M")
            cache_key = (asset, minute_key)

            if cache_key not in minute_cache:
                try:
                    price = self.binance_service.get_historical_price(fee_pair, fill.timestamp)
                    minute_cache[cache_key] = price
                    logger.info(
                        "Historical %s/%s price at %s: %s",
                        asset, quote_asset, minute_key, price
                    )
                except Exception as e:
                    logger.warning(
                        "Could not fetch historical %s/%s price at %s: %s. Trying current price.",
                        asset, quote_asset, minute_key, e
                    )
                    try:
                        price = self.binance_service.get_current_price(fee_pair)
                        minute_cache[cache_key] = price
                        logger.info("Fallback: current %s/%s price: %s", asset, quote_asset, price)
                    except Exception as e2:
                        logger.error(
                            "Fee-Konvertierung fehlgeschlagen fuer %s/%s bei %s "
                            "(historisch + aktuell). fee_quote_value wird None — "
                            "Fee geht in Portfolio-Berechnung verloren. Fill: %s",
                            asset, quote_asset, minute_key, fill.id,
                        )
                        continue

            if cache_key in minute_cache:
                per_fill_rates[fill.id] = {asset: minute_cache[cache_key]}

        return per_fill_rates

    def _enrich_lot_with_eur_rate(
        self,
        db: Session,
        event_db: LedgerEventDB,
        symbol: str,
        minute_cache: Dict[str, Decimal],
    ) -> None:
        """
        Fuer non-EUR-quoted Pairs: Holt historische BTC/EUR Rate und setzt
        cost_eur + quote_to_eur_rate auf dem Lot.

        Verwendet Minuten-Cache um redundante API-Calls zu vermeiden.
        Graceful Fallback: Bei Fehler wird nur gewarnt, Lot bleibt mit
        cost_eur=None (kann spaeter via Backfill-Script nachgeholt werden).

        Args:
            db: Database Session
            event_db: Das LedgerEvent des Buy-Fills
            symbol: Trading Pair (z.B. "XRPBTC")
            minute_cache: Cache fuer (minute_key -> btceur_rate)
        """
        from app.services.binance_public_client import get_binance_public_client

        # Lot fuer diesen Fill finden
        lot_db = (
            db.query(TradeLotDB)
            .filter(TradeLotDB.created_from_fill_id == event_db.id)
            .first()
        )
        if not lot_db:
            logger.warning(
                "No lot found for fill %s during EUR rate enrichment", event_db.id
            )
            return

        fill_timestamp = event_db.timestamp
        minute_key = fill_timestamp.strftime("%Y-%m-%d %H:%M")

        if minute_key not in minute_cache:
            try:
                client = get_binance_public_client()
                ts_ms = int(fill_timestamp.timestamp() * 1000)
                klines = client.get_klines("BTCEUR", "1m", limit=1, start_time=ts_ms)
                if klines:
                    btceur_rate = Decimal(str(klines[0][4]))  # Close price
                    minute_cache[minute_key] = btceur_rate
                    logger.info(
                        "Historical BTCEUR rate at %s: %s (for %s fill %s)",
                        minute_key, btceur_rate, symbol, event_db.id,
                    )
                else:
                    logger.warning(
                        "No BTCEUR kline data at %s for fill %s. "
                        "cost_eur will remain None (backfill later).",
                        minute_key, event_db.id,
                    )
                    return
            except Exception as e:
                logger.warning(
                    "Failed to fetch historical BTCEUR rate at %s for fill %s: %s. "
                    "cost_eur will remain None (backfill later).",
                    minute_key, event_db.id, e,
                )
                return

        if minute_key in minute_cache:
            btceur_rate = minute_cache[minute_key]
            lot_db.cost_eur = lot_db.cost_quote * btceur_rate
            lot_db.quote_to_eur_rate = btceur_rate
            logger.info(
                "Lot %s: cost_eur = %s * %s = %s",
                lot_db.id, lot_db.cost_quote, btceur_rate, lot_db.cost_eur,
            )

    def _persist_ledger_event(
        self,
        db: Session,
        user_id: str,
        event: LedgerEvent,
        fee_quote_value: Decimal | None = None,
    ) -> LedgerEventDB:
        """Delegiert an die modul-level persist_ledger_event Funktion."""
        return persist_ledger_event(db, user_id, event, fee_quote_value)
