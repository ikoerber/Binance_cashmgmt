"""
CSV Import Service - Importiert Trading Bot Trades aus Binance CSV-Export

Da Binance Spot Grid Bot Trades NICHT über die Standard-API (get_my_trades)
abrufbar sind, müssen sie per CSV-Export importiert werden.

Unterstütztes Format (Binance Trading Bots CSV):
- Date(UTC): Timestamp
- Pair: z.B. "BTCEUR"
- Side: "BUY" oder "SELL"
- Price: Trading Price
- Executed: Menge mit Asset-Suffix, z.B. "0.0080100000BTC"
- Amount: EUR-Betrag mit Suffix, z.B. "624.37950000EUR"
- Fee: Fee mit Asset-Suffix, z.B. "0.6243795000EUR" oder "0.0000080100BTC"
"""
import csv
import hashlib
import io
import re
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from app.domain.models import LedgerEvent, EventType, EventSource, TradeSide
from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum, TradeSideEnum
from app.services.lot_service import create_lot_from_buy_fill, process_sell_fill_fifo


def parse_amount_with_asset(value: str) -> tuple[Decimal, str]:
    """
    Parst einen Betrag mit Asset-Suffix.

    z.B. "0.0080100000BTC" → (Decimal("0.0080100000"), "BTC")
         "624.37950000EUR" → (Decimal("624.37950000"), "EUR")

    Args:
        value: String mit Betrag und Asset-Suffix

    Returns:
        Tuple (amount, asset)
    """
    match = re.match(r'^([0-9.]+)([A-Z]+)$', value.strip())
    if not match:
        raise ValueError(f"Cannot parse amount with asset: '{value}'")
    return Decimal(match.group(1)), match.group(2)


def generate_bot_trade_source_id(row: dict, row_index: int) -> str:
    """
    Generiert eine deterministische Source-ID für einen Bot-Trade.

    Da die CSV keine Trade-ID enthält, wird ein Hash aus den
    eindeutigen Trade-Attributen + Zeilenindex erzeugt.
    Der Zeilenindex ist nötig, da identische Fills vorkommen können
    (gleicher Timestamp, Preis, Menge, Fee bei Grid-Bot-Trades).

    Args:
        row: CSV-Zeile als Dict
        row_index: Zeilenindex in der CSV (0-basiert)

    Returns:
        Deterministische Source-ID
    """
    key = f"{row['Date(UTC)']}_{row['Side']}_{row['Price']}_{row['Executed']}_{row['Fee']}_{row_index}"
    hash_hex = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"bot_{hash_hex}"


def parse_trading_bots_csv(csv_content: str) -> List[LedgerEvent]:
    """
    Parst Binance Trading Bots CSV und konvertiert zu LedgerEvents.

    Args:
        csv_content: CSV-Inhalt als String

    Returns:
        Liste von LedgerEvents (chronologisch sortiert)
    """
    # BOM entfernen falls vorhanden
    if csv_content.startswith('\ufeff'):
        csv_content = csv_content[1:]

    reader = csv.DictReader(io.StringIO(csv_content))
    events = []

    for row_index, row in enumerate(reader):
        event = _row_to_ledger_event(row, row_index)
        events.append(event)

    # Chronologisch sortieren (älteste zuerst)
    events.sort(key=lambda e: e.timestamp)
    return events


def _row_to_ledger_event(row: dict, row_index: int) -> LedgerEvent:
    """
    Konvertiert eine CSV-Zeile zu einem LedgerEvent.

    Args:
        row: CSV-Zeile als Dict
        row_index: Zeilenindex in der CSV

    Returns:
        LedgerEvent
    """
    timestamp = datetime.strptime(row["Date(UTC)"].strip(), "%Y-%m-%d %H:%M:%S")
    pair = row["Pair"].strip()
    side_str = row["Side"].strip()
    price = Decimal(row["Price"].strip())

    # Executed: "0.0080100000BTC" → qty + asset
    qty, base_asset = parse_amount_with_asset(row["Executed"].strip())

    # Fee: "0.6243795000EUR" oder "0.0000080100BTC"
    fee_amount, fee_asset = parse_amount_with_asset(row["Fee"].strip())

    side = TradeSide.BUY if side_str == "BUY" else TradeSide.SELL

    # Symbol aus Pair ableiten (z.B. "BTCEUR" aus "BTCEUR")
    symbol = pair.replace("/", "")

    source_id = generate_bot_trade_source_id(row, row_index)

    return LedgerEvent(
        id=f"binance_bot_{symbol}_{source_id}",
        type=EventType.TRADE_FILL,
        timestamp=timestamp,
        asset=base_asset,
        amount=qty,
        symbol=symbol,
        price=price,
        side=side,
        fee_asset=fee_asset,
        fee_amount=fee_amount if fee_amount > 0 else None,
        source=EventSource.BINANCE,
        source_id=source_id,
        note="Trading Bot (Grid Bot) - CSV Import",
        raw_payload={
            "csv_row": {k: v for k, v in row.items()},
            "import_source": "trading_bots_csv",
        },
    )


def import_trading_bots_csv(
    db: Session,
    user_id: str,
    csv_content: str,
) -> Dict[str, Any]:
    """
    Importiert Trading Bot Trades aus CSV in Ledger + TradeLots.

    Idempotent: Bereits importierte Trades werden übersprungen (via source_id).

    Process:
    1. CSV parsen → LedgerEvents
    2. Gegen DB filtern (Duplikate entfernen)
    3. Ledger Events persistieren
    4. TradeLots für Buy-Fills erstellen
    5. FIFO Allocation für Sell-Fills durchführen

    Args:
        db: Database Session
        user_id: User ID
        csv_content: CSV-Inhalt als String

    Returns:
        Import-Report Dict
    """
    # 1. CSV parsen
    events = parse_trading_bots_csv(csv_content)

    if not events:
        return {
            "status": "success",
            "total_rows": 0,
            "new_fills": 0,
            "skipped_duplicates": 0,
            "new_lots": 0,
            "allocations": 0,
            "message": "CSV is empty or contains no valid trades",
        }

    total_rows = len(events)

    # 2. Bereits vorhandene source_ids filtern (Idempotenz)
    existing_source_ids = set(
        row[0] for row in
        db.query(LedgerEventDB.source_id)
        .filter(
            LedgerEventDB.user_id == user_id,
            LedgerEventDB.source_id.isnot(None)
        )
        .all()
    )

    new_events = [e for e in events if e.source_id not in existing_source_ids]
    skipped = total_rows - len(new_events)

    if not new_events:
        return {
            "status": "success",
            "total_rows": total_rows,
            "new_fills": 0,
            "skipped_duplicates": skipped,
            "new_lots": 0,
            "allocations": 0,
            "message": f"All {total_rows} trades already imported",
        }

    # 3. Ledger Events persistieren
    created_events = []
    for event in new_events:
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
        created_events.append(event_db)

    db.commit()

    # 4. TradeLots und Allocations erstellen
    # Gleiche Strategie wie SyncService: Erst alle Buy-Lots, dann Sells
    new_lots_count = 0
    allocations_count = 0
    errors = []

    # Phase 1: Alle Buy-Lots erstellen (chronologisch)
    buy_events = sorted(
        [e for e in created_events if e.side == TradeSideEnum.BUY],
        key=lambda e: e.timestamp
    )
    for event_db in buy_events:
        try:
            create_lot_from_buy_fill(db, user_id, event_db.id)
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
            result = process_sell_fill_fifo(db, user_id, event_db.id)
            allocations_count += len(result["allocations"])
        except Exception as e:
            errors.append(f"Error processing sell fill {event_db.id}: {e}")

    status = "success" if not errors else "partial_success"
    return {
        "status": status,
        "total_rows": total_rows,
        "new_fills": len(new_events),
        "skipped_duplicates": skipped,
        "new_lots": new_lots_count,
        "allocations": allocations_count,
        "errors": errors if errors else None,
        "message": (
            f"Imported {len(new_events)} bot trades "
            f"({skipped} duplicates skipped), "
            f"created {new_lots_count} lots, "
            f"{allocations_count} sell allocations"
            + (f", {len(errors)} errors" if errors else "")
        ),
    }
