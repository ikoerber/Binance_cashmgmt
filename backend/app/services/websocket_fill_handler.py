"""
WebSocket Fill Handler - Echtzeit Fill-Verarbeitung (Phase 3)

Verarbeitet Trade-Ausfuehrungen aus dem Binance User Data Stream in Echtzeit:
- Erstellt LedgerEventDB aus executionReport
- Erstellt TradeLotDB fuer BUY-Fills
- Fuehrt Sell-Allocation fuer SELL-Fills durch (respektiert User-Strategie)
- Gibt Ergebnis-Dict fuer WebSocket-Broadcast zurueck

Nutzt dieselbe Domain-Logik wie sync_service.py fuer Konsistenz.
Idempotent: Doppelte trade_ids werden uebersprungen.
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any

import requests

from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


async def handle_fill_event(user_id: str, raw_data: dict) -> Optional[dict]:
    """
    Async Entry Point fuer Fill-Verarbeitung aus dem WebSocket.

    Fuehrt die synchrone DB-Operation in einem Thread-Pool aus,
    um den WebSocket Event Loop nicht zu blockieren.

    Args:
        user_id: User ID
        raw_data: Roher Binance executionReport Dict

    Returns:
        Fill-Ergebnis-Dict fuer Broadcast, oder None wenn uebersprungen/Fehler
    """
    return await asyncio.to_thread(_sync_handle_fill_event, user_id, raw_data)


def _sync_handle_fill_event(user_id: str, raw_data: dict) -> Optional[dict]:
    """
    Synchrone Fill-Verarbeitung mit eigener DB-Session.

    Schritte:
    1. Fill-Daten aus executionReport extrahieren
    2. Idempotenz pruefen (source_id = trade_id)
    3. LedgerEventDB erstellen (mit fee_quote_value)
    4. BUY: create_lot_from_buy_fill()
       SELL: process_sell_fill() (Strategy-Routing)
    5. Ergebnis-Dict zurueckgeben

    Alles in einer Transaktion (commit/rollback).
    """
    from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum, TradeSideEnum
    from app.services.lot_service import create_lot_from_buy_fill, process_sell_fill

    # 1. Fill-Daten extrahieren
    fill_data = _extract_fill_from_execution_report(raw_data)
    if not fill_data:
        return None

    trade_id = fill_data["trade_id"]
    source_id = str(trade_id)
    symbol = fill_data["symbol"]
    side = fill_data["side"]
    qty = fill_data["qty"]
    price = fill_data["price"]
    fee_amount = fill_data["fee_amount"]
    fee_asset = fill_data["fee_asset"]
    timestamp = fill_data["timestamp"]

    db = SessionLocal()
    try:
        # 2. Idempotenz-Check
        existing = (
            db.query(LedgerEventDB.id)
            .filter(
                LedgerEventDB.user_id == user_id,
                LedgerEventDB.source_id == source_id,
            )
            .first()
        )

        if existing:
            logger.debug("Fill bereits verarbeitet (trade_id=%s), ueberspringe", trade_id)
            return None

        # 3. Fee Quote-Wert berechnen
        from app.symbol_registry import get_base_asset, get_quote_asset
        base_asset = get_base_asset(symbol)
        quote_asset = get_quote_asset(symbol)
        fee_quote_value = _compute_realtime_fee_quote_value(fee_amount, fee_asset, price, base_asset, quote_asset)

        # 4. raw_payload normalisieren fuer process_sell_fill Kompatibilitaet
        # process_sell_fill (lot_service.py:673) sucht raw_payload["orderId"]
        # Binance REST API: "orderId", WebSocket executionReport: "i"
        normalized_payload = dict(raw_data)
        normalized_payload["orderId"] = raw_data.get("i")

        # 5. LedgerEventDB erstellen

        event_id = f"binance_{symbol}_{source_id}"
        event_db = LedgerEventDB(
            id=event_id,
            user_id=user_id,
            type=EventTypeEnum.TRADE_FILL,
            timestamp=timestamp,
            asset=base_asset,
            amount=qty,
            symbol=symbol,
            price=price,
            side=TradeSideEnum[side],
            fee_asset=fee_asset if fee_amount and fee_amount > 0 else None,
            fee_amount=fee_amount if fee_amount and fee_amount > 0 else None,
            fee_quote_value=fee_quote_value,
            source=EventSourceEnum.BINANCE,
            source_id=source_id,
            raw_payload=normalized_payload,
        )
        db.add(event_db)
        db.flush()

        # 6. Fee-Konvertierungsraten fuer lot_service rekonstruieren
        fee_conversion_rates = None
        if fee_asset and fee_asset not in (quote_asset, base_asset) and fee_quote_value and fee_amount and fee_amount > 0:
            fee_conversion_rates = {fee_asset: fee_quote_value / fee_amount}

        # 7. Lot erstellen oder Sell allokieren
        result = {
            "side": side,
            "qty": str(qty),
            "price": str(price),
            "fee": str(fee_amount) if fee_amount else "0",
            "fee_asset": fee_asset or "",
            "trade_id": source_id,
            "symbol": symbol,
        }

        if side == "BUY":
            # Fetch quote-to-EUR rate for non-EUR-quoted symbols
            quote_to_eur_rate = None
            if quote_asset != "EUR":
                try:
                    rate_pair = f"{quote_asset}EUR"
                    from app.services.binance import BinanceService
                    binance_svc = BinanceService()
                    quote_to_eur_rate = binance_svc.get_historical_price(rate_pair, timestamp)
                    if quote_to_eur_rate is None:
                        quote_to_eur_rate = binance_svc.get_current_price(rate_pair)
                except Exception as e:
                    logger.warning(
                        "Could not fetch %sEUR rate for WebSocket fill: %s",
                        quote_asset, e,
                    )
                    # quote_to_eur_rate stays None — lot gets cost_eur=NULL, can backfill later

            lot_dict = create_lot_from_buy_fill(db, user_id, event_id, fee_conversion_rates, quote_to_eur_rate=quote_to_eur_rate)
            result["action"] = "lot_created"
            result["lot_id"] = lot_dict.get("id")
        elif side == "SELL":
            sell_result = process_sell_fill(db, user_id, event_id, fee_conversion_rates)
            result["action"] = "sell_allocated"
            result["allocations_count"] = len(sell_result.get("allocations", []))
            result["updated_lots_count"] = len(sell_result.get("updated_lots", []))

        db.commit()

        logger.info(
            "Fill verarbeitet via WebSocket: trade_id=%s, side=%s, qty=%s, price=%s",
            source_id,
            side,
            qty,
            price,
        )
        return result

    except Exception as e:
        logger.exception("Fill-Verarbeitung fehlgeschlagen (trade_id=%s): %s", trade_id, e)
        db.rollback()
        return None
    finally:
        db.close()


def _extract_fill_from_execution_report(raw_data: dict) -> Optional[Dict[str, Any]]:
    """
    Extrahiert fill-relevante Felder aus dem Binance executionReport.

    Binance executionReport Felder:
    - "t": trade_id (0 = kein Trade, >0 = Fill)
    - "s": symbol (z.B. "BTCEUR")
    - "S": side ("BUY" oder "SELL")
    - "l": last_filled_qty (Menge dieses Fills)
    - "L": last_filled_price (Preis dieses Fills)
    - "n": commission_amount
    - "N": commission_asset
    - "T": transaction_time (Millisekunden)

    Returns:
        Normalisiertes Dict oder None wenn kein gültiger Fill
    """
    trade_id = raw_data.get("t", 0)
    if not trade_id or trade_id <= 0:
        return None

    from app.symbol_registry import is_known_symbol
    symbol = raw_data.get("s", "")
    if not is_known_symbol(symbol):
        logger.debug("Ueberspringe unbekanntes Symbol Fill: %s", symbol)
        return None

    side = raw_data.get("S", "")
    if side not in ("BUY", "SELL"):
        logger.warning("Unbekannte Seite in executionReport: %s", side)
        return None

    try:
        qty = Decimal(str(raw_data.get("l", "0")))
        price = Decimal(str(raw_data.get("L", "0")))
        fee_amount = Decimal(str(raw_data.get("n", "0")))
    except (InvalidOperation, TypeError) as e:
        logger.warning("Ungueltige Decimal-Werte in executionReport: %s", e)
        return None

    if qty <= 0 or price <= 0:
        logger.debug("Fill mit qty=%s, price=%s uebersprungen", qty, price)
        return None

    fee_asset = raw_data.get("N", "")

    # Timestamp: Millisekunden → naive UTC datetime (konsistent mit binance.py:173)
    tx_time_ms = raw_data.get("T", 0)
    timestamp = datetime.fromtimestamp(tx_time_ms / 1000, tz=timezone.utc).replace(tzinfo=None)

    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "fee_amount": fee_amount,
        "fee_asset": fee_asset,
        "timestamp": timestamp,
    }


def _compute_realtime_fee_quote_value(
    fee_amount: Optional[Decimal],
    fee_asset: Optional[str],
    fill_price: Decimal,
    base_asset: str,
    quote_asset: str = "EUR",
) -> Optional[Decimal]:
    """
    Vereinfachte Fee-Quote-Wert-Berechnung fuer Echtzeit-Fills.

    Strategie:
    - Quote-Asset Fee: as-is
    - Base-Asset Fee: x fill_price (Base/Quote Preis zum Trade-Zeitpunkt)
    - BNB/andere: Aktueller Preis via Binance Public API
      (akzeptable Approximation; Reconciliation faengt Diskrepanzen)

    Returns:
        Quote-Asset-Wert der Fee, oder None bei Fehler
    """
    if not fee_amount or fee_amount <= 0:
        return None

    if not fee_asset:
        return None

    if fee_asset == quote_asset:
        return fee_amount

    if fee_asset == base_asset:
        return fee_amount * fill_price

    # BNB/andere: Aktuellen Preis von Binance Public API holen
    try:
        price = _fetch_current_price(f"{fee_asset}{quote_asset}")
        if price:
            return fee_amount * price
    except Exception as e:
        logger.warning("Fee-Konvertierung fehlgeschlagen fuer %s: %s", fee_asset, e)

    return None


def _fetch_current_price(symbol: str) -> Optional[Decimal]:
    """
    Holt aktuellen Preis von der Binance Public API (kein API-Key noetig).

    Args:
        symbol: Trading Pair (z.B. "BNBEUR")

    Returns:
        Aktueller Preis als Decimal, oder None bei Fehler
    """
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=5,
        )
        resp.raise_for_status()
        return Decimal(str(resp.json()["price"]))
    except Exception as e:
        logger.warning("Preis-Abruf fehlgeschlagen fuer %s: %s", symbol, e)
        return None
