"""
Backfill fee_eur_value fuer bestehende Ledger Events.

Die Migration 56a67fbefa2b hat die Spalte fee_eur_value hinzugefuegt,
aber bestehende BNB-Fee Events wurden nicht backgefuellt.

Dieses Script:
1. Findet alle TRADE_FILL Events mit BNB-Fee OHNE fee_eur_value
2. Holt historische BNB/EUR Preise via Binance Klines API (1min)
3. Berechnet fee_eur_value = fee_amount * historischer_preis
4. Aktualisiert die Events in der DB

Minuten-Cache: Fills in derselben Minute teilen sich den Kline-Preis.

Usage:
    python scripts/backfill_fee_eur_value.py              # Dry-run (default)
    python scripts/backfill_fee_eur_value.py --commit     # Tatsaechlich schreiben
    python scripts/backfill_fee_eur_value.py --db sqlite  # SQLite statt PostgreSQL
"""
import argparse
import logging
import os
import sys
import time
from decimal import Decimal

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_historical_price(symbol: str, timestamp_str: str) -> Decimal:
    """
    Holt historischen Preis via Binance Klines API (public, kein API Key noetig).

    Args:
        symbol: z.B. "BNBEUR"
        timestamp_str: ISO datetime string (naive UTC)

    Returns:
        Close-Preis als Decimal
    """
    from datetime import datetime
    ts = datetime.fromisoformat(timestamp_str)
    ts_ms = int(ts.timestamp() * 1000)

    resp = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={
            "symbol": symbol,
            "interval": "1m",
            "startTime": ts_ms,
            "limit": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    klines = resp.json()

    if not klines:
        raise ValueError(f"No kline data for {symbol} at {timestamp_str}")

    return Decimal(str(klines[0][4]))  # Close price


def main():
    parser = argparse.ArgumentParser(description="Backfill fee_eur_value")
    parser.add_argument("--commit", action="store_true", help="Tatsaechlich in DB schreiben")
    parser.add_argument("--db", choices=["pg", "sqlite"], default="pg", help="Welche DB (default: pg)")
    args = parser.parse_args()

    if args.db == "pg":
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            logger.error("DATABASE_URL nicht gesetzt")
            sys.exit(1)
    else:
        db_url = "sqlite:///./cashmgnt.db"

    logger.info("DB: %s", db_url[:50] + "...")
    logger.info("Mode: %s", "COMMIT" if args.commit else "DRY-RUN")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # 1. Alle Events mit BNB-Fee ohne fee_eur_value finden
        result = db.execute(text("""
            SELECT id, fee_asset, fee_amount, timestamp, price
            FROM ledger_events
            WHERE fee_asset IS NOT NULL
              AND fee_asset NOT IN ('EUR', 'BTC')
              AND fee_eur_value IS NULL
              AND fee_amount IS NOT NULL
              AND fee_amount > 0
            ORDER BY timestamp ASC
        """))
        rows = result.fetchall()

        if not rows:
            logger.info("Keine Events zum Backfill gefunden.")
            return

        logger.info("Gefunden: %d Events mit fehlender fee_eur_value", len(rows))

        # 2. Minuten-Cache: (asset, minute_key) -> price
        minute_cache: dict[tuple, Decimal] = {}
        updated = 0
        skipped = 0
        errors = 0

        for i, row in enumerate(rows):
            event_id, fee_asset, fee_amount, timestamp, fill_price = row
            symbol = f"{fee_asset}EUR"
            minute_key = str(timestamp)[:16]  # "YYYY-MM-DD HH:MM"
            cache_key = (fee_asset, minute_key)

            if cache_key not in minute_cache:
                try:
                    price = get_historical_price(symbol, str(timestamp))
                    minute_cache[cache_key] = price
                    logger.info(
                        "[%d/%d] Historical %s/EUR at %s: %s",
                        i + 1, len(rows), fee_asset, minute_key, price
                    )
                    # Rate limit: Binance public API erlaubt 1200 req/min
                    time.sleep(0.1)
                except Exception as e:
                    logger.warning(
                        "[%d/%d] Fehler fuer %s at %s: %s",
                        i + 1, len(rows), symbol, minute_key, e
                    )
                    errors += 1
                    continue

            if cache_key not in minute_cache:
                skipped += 1
                continue

            historical_price = minute_cache[cache_key]
            fee_eur_value = Decimal(str(fee_amount)) * historical_price

            if args.commit:
                db.execute(
                    text("UPDATE ledger_events SET fee_eur_value = :val WHERE id = :id"),
                    {"val": float(fee_eur_value), "id": event_id}
                )

            updated += 1

            if (i + 1) % 50 == 0:
                logger.info("Progress: %d/%d verarbeitet", i + 1, len(rows))

        if args.commit:
            db.commit()
            logger.info("COMMIT: %d Events aktualisiert, %d uebersprungen, %d Fehler", updated, skipped, errors)
        else:
            logger.info("DRY-RUN: %d wuerden aktualisiert, %d uebersprungen, %d Fehler", updated, skipped, errors)

        logger.info("Unique Minuten-Preise gecacht: %d", len(minute_cache))

    except Exception as e:
        db.rollback()
        logger.exception("Backfill fehlgeschlagen: %s", e)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
