"""
Reparatur-Skript: Sell-Allocations komplett neu ableiten

Problem: Pairing-Orders (linked_pairing_id) wurden per FIFO an die falschen Lots allokiert.
Lösung: Alle Allocations löschen, Lots zurücksetzen, Sells chronologisch neu verarbeiten.

Ledger-first: Die Ledger-Events bleiben unverändert. Nur die abgeleiteten
Daten (Allocations + Lot-Status) werden neu berechnet.

Usage:
    cd backend
    python scripts/repair_allocations.py [--dry-run]
"""
import sys
import os
import argparse
from decimal import Decimal

# App-Pfad hinzufügen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import app.db.database as db_module
from app.db.models import (
    TradeLotDB,
    SellAllocationDB,
    LedgerEventDB,
    LotStatusEnum,
    TradeSideEnum,
)
from app.services.lot_service import process_sell_fill


def repair_allocations(dry_run: bool = False):
    # DB initialisieren
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./cashmgnt.db")
    db_module.init_db(database_url)

    db = db_module.SessionLocal()
    try:
        user_id = db.query(TradeLotDB.user_id).distinct().first()
        if not user_id:
            print("Keine Lots gefunden.")
            return
        user_id = user_id[0]
        print(f"User: {user_id}")

        # 1. Aktuellen Zustand anzeigen
        open_lots = (
            db.query(TradeLotDB)
            .filter(TradeLotDB.user_id == user_id, TradeLotDB.qty_btc_open > 0)
            .count()
        )
        total_allocs = db.query(SellAllocationDB).count()
        print(f"\nVOR Reparatur:")
        print(f"  Offene Lots: {open_lots}")
        print(f"  Sell-Allocations: {total_allocs}")

        total_open_btc = (
            db.query(TradeLotDB)
            .filter(TradeLotDB.user_id == user_id, TradeLotDB.qty_btc_open > 0)
            .with_entities(db.query(TradeLotDB.qty_btc_open).filter(
                TradeLotDB.user_id == user_id
            ).subquery())
        )

        # Einfacher: Alle offenen Lots summieren
        lots_all = db.query(TradeLotDB).filter(TradeLotDB.user_id == user_id).all()
        total_open = sum(lot.qty_btc_open for lot in lots_all)
        total_initial = sum(lot.qty_btc_initial for lot in lots_all)
        print(f"  BTC offen: {total_open}")
        print(f"  BTC initial (alle Lots): {total_initial}")

        if dry_run:
            print("\n--- DRY RUN: Keine Änderungen werden geschrieben ---\n")

        # 2. Alle Sell-Allocations löschen
        alloc_count = db.query(SellAllocationDB).count()
        print(f"\nSchritt 1: Lösche {alloc_count} Sell-Allocations...")
        if not dry_run:
            db.query(SellAllocationDB).delete()
            db.flush()

        # 3. Alle Lots zurücksetzen: qty_btc_open = qty_btc_initial, status = OPEN
        all_lots = db.query(TradeLotDB).filter(TradeLotDB.user_id == user_id).all()
        reset_count = 0
        for lot in all_lots:
            if lot.qty_btc_open != lot.qty_btc_initial or lot.status != LotStatusEnum.OPEN:
                if not dry_run:
                    lot.qty_btc_open = lot.qty_btc_initial
                    lot.status = LotStatusEnum.OPEN
                reset_count += 1
        print(f"Schritt 2: {reset_count} Lots zurückgesetzt auf OPEN (qty_open = qty_initial)")
        if not dry_run:
            db.flush()

        # 4. Alle Sell-Fills chronologisch holen
        sell_events = (
            db.query(LedgerEventDB)
            .filter(
                LedgerEventDB.user_id == user_id,
                LedgerEventDB.type == "TRADE_FILL",
                LedgerEventDB.side == TradeSideEnum.SELL,
            )
            .order_by(LedgerEventDB.timestamp.asc())
            .all()
        )
        print(f"\nSchritt 3: Verarbeite {len(sell_events)} Sell-Fills chronologisch...")

        # 5. Sell-Fills neu verarbeiten (jetzt mit Pairing-Awareness!)
        total_new_allocs = 0
        errors = []
        for i, event in enumerate(sell_events):
            order_id = event.raw_payload.get("orderId", "?") if event.raw_payload else "?"
            try:
                if not dry_run:
                    result = process_sell_fill(db, user_id, event.id)
                    alloc_count = len(result["allocations"])
                    total_new_allocs += alloc_count
                    # Welcher Pfad wurde genommen?
                    lot_ids = [a["trade_lot_id"] for a in result["allocations"]]
                    print(f"  [{i+1}/{len(sell_events)}] Fill {event.source_id} "
                          f"(Order {order_id}, {event.amount} BTC) → {alloc_count} allocations "
                          f"→ {lot_ids}")
                else:
                    print(f"  [{i+1}/{len(sell_events)}] Fill {event.source_id} "
                          f"(Order {order_id}, {event.amount} BTC) → [dry-run]")
            except Exception as e:
                errors.append(f"Fill {event.source_id}: {e}")
                print(f"  [{i+1}/{len(sell_events)}] FEHLER Fill {event.source_id}: {e}")

        # 6. Ergebnis anzeigen
        print(f"\n{'='*60}")
        print(f"NACH Reparatur:")
        if not dry_run:
            db.flush()
            lots_after = db.query(TradeLotDB).filter(TradeLotDB.user_id == user_id).all()
            open_after = [l for l in lots_after if l.qty_btc_open > 0]
            total_open_after = sum(l.qty_btc_open for l in lots_after)
            closed_after = [l for l in lots_after if l.status == LotStatusEnum.CLOSED]

            print(f"  Offene Lots: {len(open_after)}")
            print(f"  Geschlossene Lots: {len(closed_after)}")
            print(f"  BTC offen: {total_open_after}")
            print(f"  Neue Allocations: {total_new_allocs}")
            if errors:
                print(f"  Fehler: {len(errors)}")
                for err in errors:
                    print(f"    - {err}")

            # Commit
            confirm = input("\nÄnderungen committen? [y/N] ")
            if confirm.lower() == "y":
                db.commit()
                print("Committed!")
            else:
                db.rollback()
                print("Rollback - keine Änderungen gespeichert.")
        else:
            print(f"  [dry-run] {len(sell_events)} Fills würden neu verarbeitet")
            if errors:
                print(f"  Fehler: {len(errors)}")

    except Exception as e:
        db.rollback()
        print(f"\nFEHLER: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sell-Allocations neu ableiten")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts ändern")
    args = parser.parse_args()
    repair_allocations(dry_run=args.dry_run)
