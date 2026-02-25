"""
Backfill cost_eur for existing BTC-quoted lots (e.g., XRPBTC).

The Alembic migration "add EUR cost basis columns to trade_lots" backfills EUR-quoted
lots (BTCEUR, ETHEUR, XRPEUR) via SQL. BTC-quoted lots need historical API data that
cannot be computed in migration.

For each BTC-quoted lot with cost_eur IS NULL:
1. Looks up the fill timestamp from ledger_events
2. Fetches historical BTC/EUR price at that timestamp via Binance Klines API
3. Computes cost_eur = cost_quote * btceur_rate
4. Updates cost_eur and quote_to_eur_rate on the lot

Minute-caching: Fills in the same minute share one API call.
Rate limiting: 0.1s between unique API calls.

Usage:
    python scripts/backfill_cost_eur.py              # Dry-run
    python scripts/backfill_cost_eur.py --commit     # Write to DB
    python scripts/backfill_cost_eur.py --db sqlite  # SQLite statt PostgreSQL
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

# EUR-quoted symbols that are already backfilled by the Alembic migration
EUR_QUOTED_SYMBOLS = ("BTCEUR", "ETHEUR", "XRPEUR")

# Mapping: quote_asset -> rate_pair for EUR conversion
# For XRPBTC: quote_asset=BTC, rate_pair=BTCEUR
QUOTE_TO_EUR_PAIRS = {
    "BTC": "BTCEUR",
    "ETH": "ETHEUR",
}


def get_quote_asset_for_symbol(symbol: str) -> str:
    """Extracts quote asset from symbol. Simple heuristic for known pairs."""
    known = {
        "XRPBTC": "BTC",
        "ETHBTC": "BTC",
        "BTCEUR": "EUR",
        "ETHEUR": "EUR",
        "XRPEUR": "EUR",
    }
    if symbol in known:
        return known[symbol]
    # Fallback: assume last 3 chars are quote
    return symbol[-3:]


def get_historical_price(symbol: str, timestamp_str: str) -> Decimal:
    """
    Holt historischen Preis via Binance Klines API (public, kein API Key noetig).

    Args:
        symbol: z.B. "BTCEUR"
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
    parser = argparse.ArgumentParser(description="Backfill cost_eur for BTC-quoted lots")
    parser.add_argument("--commit", action="store_true", help="Tatsaechlich in DB schreiben")
    parser.add_argument("--db", choices=["pg", "sqlite"], default="sqlite", help="Welche DB (default: sqlite)")
    args = parser.parse_args()

    if args.db == "pg":
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            logger.error("DATABASE_URL nicht gesetzt")
            sys.exit(1)
    else:
        db_url = os.getenv("DB_URL", "sqlite:///./cashmgnt.db")

    logger.info("DB: %s", db_url[:50] + "...")
    logger.info("Mode: %s", "COMMIT" if args.commit else "DRY-RUN")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # 1. Find all BTC-quoted lots with cost_eur IS NULL
        # Join with ledger_events to get fill timestamp
        result = db.execute(text("""
            SELECT tl.id, tl.symbol, tl.cost_quote, le.timestamp
            FROM trade_lots tl
            JOIN ledger_events le ON tl.created_from_fill_id = le.id
            WHERE tl.cost_eur IS NULL
              AND tl.symbol NOT IN ('BTCEUR', 'ETHEUR', 'XRPEUR')
            ORDER BY le.timestamp ASC
        """))
        rows = result.fetchall()

        if not rows:
            logger.info("Keine BTC-quoted Lots zum Backfill gefunden.")
            return

        logger.info("Gefunden: %d BTC-quoted Lots mit fehlender cost_eur", len(rows))

        # 2. Minuten-Cache: (rate_pair, minute_key) -> price
        minute_cache: dict[tuple, Decimal] = {}
        updated = 0
        skipped = 0
        errors = 0

        for i, row in enumerate(rows):
            lot_id, symbol, cost_quote, timestamp = row
            quote_asset = get_quote_asset_for_symbol(symbol)
            rate_pair = QUOTE_TO_EUR_PAIRS.get(quote_asset)

            if not rate_pair:
                logger.warning(
                    "[%d/%d] Unbekanntes Quote-Asset '%s' fuer Symbol '%s', ueberspringe Lot %s",
                    i + 1, len(rows), quote_asset, symbol, lot_id,
                )
                skipped += 1
                continue

            minute_key = str(timestamp)[:16]  # "YYYY-MM-DD HH:MM"
            cache_key = (rate_pair, minute_key)

            if cache_key not in minute_cache:
                try:
                    price = get_historical_price(rate_pair, str(timestamp))
                    minute_cache[cache_key] = price
                    logger.info(
                        "[%d/%d] Historical %s at %s: %s",
                        i + 1, len(rows), rate_pair, minute_key, price,
                    )
                    # Rate limit: Binance public API erlaubt 1200 req/min
                    time.sleep(0.1)
                except Exception as e:
                    logger.warning(
                        "[%d/%d] Fehler fuer %s at %s: %s (Lot %s)",
                        i + 1, len(rows), rate_pair, minute_key, e, lot_id,
                    )
                    errors += 1
                    continue

            if cache_key not in minute_cache:
                skipped += 1
                continue

            btceur_rate = minute_cache[cache_key]
            cost_eur = Decimal(str(cost_quote)) * btceur_rate

            if args.commit:
                db.execute(
                    text("""
                        UPDATE trade_lots
                        SET cost_eur = :cost_eur,
                            quote_to_eur_rate = :rate
                        WHERE id = :lot_id
                    """),
                    {"cost_eur": str(cost_eur), "rate": str(btceur_rate), "lot_id": lot_id},
                )

            logger.info(
                "[%d/%d] Lot %s (%s): cost_quote=%s * %s = cost_eur=%s",
                i + 1, len(rows), lot_id, symbol, cost_quote, btceur_rate, cost_eur,
            )
            updated += 1

            if (i + 1) % 50 == 0:
                logger.info("Progress: %d/%d verarbeitet", i + 1, len(rows))

        if args.commit:
            db.commit()
            logger.info(
                "COMMIT: %d Lots aktualisiert, %d uebersprungen, %d Fehler",
                updated, skipped, errors,
            )
        else:
            logger.info(
                "DRY-RUN: %d wuerden aktualisiert, %d uebersprungen, %d Fehler",
                updated, skipped, errors,
            )

        logger.info("Unique Minuten-Preise gecacht: %d", len(minute_cache))

    except Exception as e:
        db.rollback()
        logger.exception("Backfill fehlgeschlagen: %s", e)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
