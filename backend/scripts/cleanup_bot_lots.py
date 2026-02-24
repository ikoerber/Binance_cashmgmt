"""
Cleanup-Script: Entfernt alle Trading Bot (Grid Bot) CSV-importierten Daten.

Bot-Trades sind identifizierbar ueber:
- LedgerEvent.source_id LIKE 'bot_%'
- TradeLot.created_from_fill_id → referenziert Bot-Events

Loeschreihenfolge (FK-Constraints beachten):
1. Orders (linked_lot_id → bot lots)
2. PairingItems (lot_id → bot lots)
3. SellAllocations (trade_lot_id → bot lots ODER sell_fill_id → bot events)
4. TradeLots (created_from_fill_id → bot events)
5. LedgerEvents (source_id LIKE 'bot_%')

Usage:
    cd backend
    python scripts/cleanup_bot_lots.py              # Dry-run (nur zaehlen)
    python scripts/cleanup_bot_lots.py --execute     # Tatsaechlich loeschen
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.db.database import init_db
from app.db.models import (
    LedgerEventDB,
    TradeLotDB,
    SellAllocationDB,
    OrderDB,
    PairingItemDB,
    PairingDB,
)
from sqlalchemy.orm import sessionmaker


def main():
    execute = "--execute" in sys.argv
    db_url = os.getenv("DATABASE_URL", "sqlite:///./cashmgnt.db")

    init_db(db_url)
    from app.db.database import SessionLocal

    db = SessionLocal()

    try:
        # 1. Bot LedgerEvents identifizieren
        bot_events = (
            db.query(LedgerEventDB)
            .filter(LedgerEventDB.source_id.like("bot_%"))
            .order_by(LedgerEventDB.timestamp)
            .all()
        )

        bot_event_ids = [e.id for e in bot_events]

        print(f"\n=== Bot-Trade Cleanup {'(DRY RUN)' if not execute else '(EXECUTING)'} ===\n")
        print(f"Bot LedgerEvents gefunden: {len(bot_events)}")

        if not bot_events:
            print("Keine Bot-Trades vorhanden. Nichts zu tun.")
            return

        buys = [e for e in bot_events if e.side and e.side.value == "BUY"]
        sells = [e for e in bot_events if e.side and e.side.value == "SELL"]
        symbols = set(e.symbol for e in bot_events if e.symbol)
        print(f"  Buys: {len(buys)}, Sells: {len(sells)}")
        print(f"  Symbole: {', '.join(symbols)}")
        print(f"  Zeitraum: {bot_events[0].timestamp} bis {bot_events[-1].timestamp}")

        # 2. Bot TradeLots identifizieren
        bot_lots = (
            db.query(TradeLotDB)
            .filter(TradeLotDB.created_from_fill_id.in_(bot_event_ids))
            .all()
        )
        bot_lot_ids = [lot.id for lot in bot_lots]

        print(f"\nBot TradeLots gefunden: {len(bot_lots)}")
        if bot_lots:
            statuses = {}
            for lot in bot_lots:
                s = lot.status.value if lot.status else "UNKNOWN"
                statuses[s] = statuses.get(s, 0) + 1
            print(f"  Status: {statuses}")

        # 3. Abhaengige Daten zaehlen
        orders_count = 0
        pairing_items_count = 0
        alloc_by_lot = 0
        alloc_by_fill = 0

        if bot_lot_ids:
            orders_count = db.query(OrderDB).filter(OrderDB.linked_lot_id.in_(bot_lot_ids)).count()
            pairing_items_count = db.query(PairingItemDB).filter(PairingItemDB.lot_id.in_(bot_lot_ids)).count()
            alloc_by_lot = db.query(SellAllocationDB).filter(SellAllocationDB.trade_lot_id.in_(bot_lot_ids)).count()

        if bot_event_ids:
            alloc_by_fill = db.query(SellAllocationDB).filter(SellAllocationDB.sell_fill_id.in_(bot_event_ids)).count()

        print(f"\nAbhaengige Datensaetze:")
        print(f"  Orders:          {orders_count}")
        print(f"  PairingItems:    {pairing_items_count}")
        print(f"  SellAllocations: {alloc_by_lot} (by lot) + {alloc_by_fill} (by fill)")

        total = len(bot_events) + len(bot_lots) + orders_count + pairing_items_count + alloc_by_lot + alloc_by_fill
        print(f"\n  GESAMT zu loeschen: {total} Datensaetze")

        if not execute:
            print(f"\n>>> Dry-run abgeschlossen. Zum Loeschen: python scripts/cleanup_bot_lots.py --execute")
            return

        # === EXECUTE ===
        print(f"\nLoesche...")

        if bot_lot_ids:
            n = db.query(OrderDB).filter(OrderDB.linked_lot_id.in_(bot_lot_ids)).delete(synchronize_session=False)
            print(f"  Orders:          {n} geloescht")

            n = db.query(PairingItemDB).filter(PairingItemDB.lot_id.in_(bot_lot_ids)).delete(synchronize_session=False)
            print(f"  PairingItems:    {n} geloescht")

            n = db.query(SellAllocationDB).filter(SellAllocationDB.trade_lot_id.in_(bot_lot_ids)).delete(synchronize_session=False)
            print(f"  SellAlloc (lot): {n} geloescht")

        if bot_event_ids:
            n = db.query(SellAllocationDB).filter(SellAllocationDB.sell_fill_id.in_(bot_event_ids)).delete(synchronize_session=False)
            print(f"  SellAlloc (fill):{n} geloescht")

        if bot_lot_ids:
            n = db.query(TradeLotDB).filter(TradeLotDB.id.in_(bot_lot_ids)).delete(synchronize_session=False)
            print(f"  TradeLots:       {n} geloescht")

        if bot_event_ids:
            n = db.query(LedgerEventDB).filter(LedgerEventDB.id.in_(bot_event_ids)).delete(synchronize_session=False)
            print(f"  LedgerEvents:    {n} geloescht")

        # Verwaiste Pairings aufraeumen (Pairings ohne Items)
        orphaned_ids = [
            p.id for p in db.query(PairingDB).all()
            if db.query(PairingItemDB).filter(PairingItemDB.pairing_id == p.id).count() == 0
        ]
        if orphaned_ids:
            n = db.query(PairingDB).filter(PairingDB.id.in_(orphaned_ids)).delete(synchronize_session=False)
            print(f"  Verwaiste Pairings: {n} geloescht")

        db.commit()
        print(f"\n=== Cleanup abgeschlossen ===")

    except Exception as e:
        db.rollback()
        print(f"\nFEHLER: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
