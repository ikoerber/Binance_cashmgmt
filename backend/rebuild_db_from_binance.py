#!/usr/bin/env python3
"""
Rebuild Database from Binance

Erstellt die Datenbank komplett neu basierend auf Binance-Daten:
1. Loescht die alte DB
2. Erstellt eine neue DB mit allen Tabellen
3. Synchronisiert alle Daten von Binance:
   - Trades/Fills (BTC/EUR) - Multi-Batch fuer >1000 Trades
   - Deposits (EUR -> EXTERNAL_CASHFLOW, BTC -> DEPOSIT)
   - Withdrawals (EUR -> EXTERNAL_CASHFLOW, BTC -> WITHDRAWAL)
4. Importiert Bot-Trades aus CSV (Grid Bot)
5. Erstellt TradeLots und FIFO-Allocations
6. Verifiziert BTC-Balance gegen Binance
"""
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from app.db.models import Base, User
from app.services.binance import BinanceService
from app.services.sync_service import SyncService
from app.db.database import get_db


def main():
    """Main rebuild function"""
    print("=" * 80)
    print("DATABASE REBUILD FROM BINANCE")
    print("=" * 80)
    print()

    # Configuration
    DB_PATH = "cashmgnt.db"
    USER_ID = "user_123"
    BOT_CSV_PATH = os.getenv("BOT_CSV_PATH", "../trading-bots.csv")

    # Binance API Credentials (aus Environment Variables)
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
    USE_TESTNET = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("ERROR: Binance API credentials not found!")
        print()
        print("Please set environment variables:")
        print("  export BINANCE_API_KEY='your_api_key'")
        print("  export BINANCE_API_SECRET='your_api_secret'")
        print("  export BINANCE_TESTNET='false'  # or 'true' for testnet")
        print()
        sys.exit(1)

    # Step 1: Delete old database
    print("Step 1: Delete old database")
    print("-" * 80)
    if os.path.exists(DB_PATH):
        print(f"Deleting old database: {DB_PATH}")
        os.remove(DB_PATH)
        print("Old database deleted")
    else:
        print(f"No old database found at {DB_PATH}")
    print()

    # Step 2: Create new database
    print("Step 2: Create new database")
    print("-" * 80)
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(DATABASE_URL, echo=False)

    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("All tables created")
    print()

    # Step 3: Create default user
    print("Step 3: Create default user")
    print("-" * 80)
    with Session(engine) as db:
        user = User(
            id=USER_ID,
            email="user@example.com",
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        print(f"User created: {USER_ID}")
    print()

    # Step 4: Initialize Binance Service
    print("Step 4: Initialize Binance Service")
    print("-" * 80)
    print(f"Using Testnet: {USE_TESTNET}")
    binance_service = BinanceService(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        testnet=USE_TESTNET
    )
    sync_service = SyncService(binance_service)
    print("Binance Service initialized")
    print()

    # Step 5: Sync Trades/Fills - Multi-Batch
    print("Step 5: Sync Trades/Fills (BTC/EUR) - Multi-Batch")
    print("-" * 80)
    total_fills = 0
    total_lots = 0
    total_allocs = 0
    all_errors = []

    with Session(engine) as db:
        # Starte weit in der Vergangenheit und arbeite vorwaerts
        # get_my_trades mit startTime liefert max 1000 Trades
        start_dt = datetime(2024, 1, 1)
        batch_num = 0
        max_batches = 20  # Safety limit

        while batch_num < max_batches:
            batch_num += 1
            print(f"  Batch {batch_num}: Fetching from {start_dt.isoformat()}...")

            try:
                result = sync_service.sync_fills(
                    db=db,
                    user_id=USER_ID,
                    symbol="BTCEUR",
                    start_time=start_dt
                )

                new_fills = result['new_fills']
                total_fills += new_fills
                total_lots += result['new_lots']
                total_allocs += result['allocations']

                if result.get('errors'):
                    all_errors.extend(result['errors'])

                print(f"    -> {new_fills} new fills, {result['new_lots']} lots, {result['allocations']} allocs")

                if new_fills == 0:
                    print("    -> No more new fills, stopping.")
                    break

                # Naechster Batch: ab dem letzten Timestamp + 1ms
                # Hole den letzten Timestamp der neuen Fills
                from app.db.models import LedgerEventDB, EventTypeEnum
                latest = (
                    db.query(func.max(LedgerEventDB.timestamp))
                    .filter(LedgerEventDB.user_id == USER_ID, LedgerEventDB.type == EventTypeEnum.TRADE_FILL)
                    .scalar()
                )
                if latest:
                    start_dt = latest + timedelta(milliseconds=1)
                else:
                    break

            except Exception as e:
                print(f"    ERROR in batch {batch_num}: {e}")
                import traceback
                traceback.print_exc()
                break

    print(f"  TOTAL: {total_fills} fills, {total_lots} lots, {total_allocs} allocations")
    if all_errors:
        print(f"  ERRORS: {len(all_errors)}")
        for err in all_errors[:5]:
            print(f"    - {err}")
    print()

    # Step 6: Import Bot-Trades from CSV
    print("Step 6: Import Bot-Trades from CSV")
    print("-" * 80)
    bot_csv_full_path = os.path.join(os.path.dirname(__file__), BOT_CSV_PATH)
    if os.path.exists(bot_csv_full_path):
        with Session(engine) as db:
            try:
                from app.services.csv_import_service import import_trading_bots_csv

                with open(bot_csv_full_path, 'r', encoding='utf-8-sig') as f:
                    csv_content = f.read()

                result = import_trading_bots_csv(db, USER_ID, csv_content)
                print(f"  Status: {result['status']}")
                print(f"  Total rows: {result['total_rows']}")
                print(f"  New fills: {result['new_fills']}")
                print(f"  Skipped duplicates: {result['skipped_duplicates']}")
                print(f"  New lots: {result['new_lots']}")
                print(f"  Allocations: {result['allocations']}")
                if result.get('errors'):
                    print(f"  Errors: {len(result['errors'])}")
                    for err in result['errors'][:5]:
                        print(f"    - {err}")
            except Exception as e:
                print(f"  ERROR importing bot CSV: {e}")
                import traceback
                traceback.print_exc()
    else:
        print(f"  No bot CSV found at {bot_csv_full_path}")
        print(f"  Set BOT_CSV_PATH env var or place trading-bots.csv in parent directory")
    print()

    # Step 7: Sync Fiat Deposits (EUR SEPA -> EXTERNAL_CASHFLOW)
    print("Step 7: Sync Fiat Deposits (EUR SEPA -> EXTERNAL_CASHFLOW)")
    print("-" * 80)
    with Session(engine) as db:
        try:
            from datetime import timezone as tz
            from app.db.models import LedgerEventDB, EventTypeEnum, EventSourceEnum

            begin = datetime(2024, 1, 1, tzinfo=tz.utc)
            fiat_deposits = binance_service.fetch_fiat_deposit_history(begin_time=begin)
            print(f"Found {len(fiat_deposits)} EUR SEPA deposits")

            btc_deposits = binance_service.fetch_deposit_history(coin="BTC")
            print(f"Found {len(btc_deposits)} BTC crypto deposits")

            all_deposits = fiat_deposits + btc_deposits
            for deposit in all_deposits:
                event_db = LedgerEventDB(
                    id=deposit.id,
                    user_id=USER_ID,
                    type=EventTypeEnum[deposit.type.value],
                    timestamp=deposit.timestamp,
                    asset=deposit.asset,
                    amount=deposit.amount,
                    fee_asset=deposit.fee_asset,
                    fee_amount=deposit.fee_amount,
                    source=EventSourceEnum[deposit.source.value],
                    source_id=deposit.source_id,
                    note=deposit.note,
                    raw_payload=deposit.raw_payload,
                )
                db.add(event_db)

            db.commit()
            print(f"Synced {len(all_deposits)} deposits total")
        except Exception as e:
            print(f"ERROR syncing deposits: {e}")
            import traceback
            traceback.print_exc()
    print()

    # Step 8: Sync Fiat Withdrawals (EUR SEPA -> EXTERNAL_CASHFLOW)
    print("Step 8: Sync Fiat Withdrawals (EUR SEPA -> EXTERNAL_CASHFLOW)")
    print("-" * 80)
    with Session(engine) as db:
        try:
            fiat_withdrawals = binance_service.fetch_fiat_withdrawal_history(begin_time=begin)
            print(f"Found {len(fiat_withdrawals)} EUR SEPA withdrawals")

            btc_withdrawals = binance_service.fetch_withdrawal_history(coin="BTC")
            print(f"Found {len(btc_withdrawals)} BTC crypto withdrawals")

            all_withdrawals = fiat_withdrawals + btc_withdrawals
            for withdrawal in all_withdrawals:
                event_db = LedgerEventDB(
                    id=withdrawal.id,
                    user_id=USER_ID,
                    type=EventTypeEnum[withdrawal.type.value],
                    timestamp=withdrawal.timestamp,
                    asset=withdrawal.asset,
                    amount=withdrawal.amount,
                    fee_asset=withdrawal.fee_asset,
                    fee_amount=withdrawal.fee_amount,
                    source=EventSourceEnum[withdrawal.source.value],
                    source_id=withdrawal.source_id,
                    note=withdrawal.note,
                    raw_payload=withdrawal.raw_payload,
                )
                db.add(event_db)

            db.commit()
            print(f"Synced {len(all_withdrawals)} withdrawals total")
        except Exception as e:
            print(f"ERROR syncing withdrawals: {e}")
            import traceback
            traceback.print_exc()
    print()

    # Step 9: Verify and Report
    print("Step 9: Verify and Report")
    print("-" * 80)
    with Session(engine) as db:
        from app.db.models import LedgerEventDB, TradeLotDB, SellAllocationDB

        total_events = db.query(LedgerEventDB).count()
        trade_fills = db.query(LedgerEventDB).filter(
            LedgerEventDB.type == EventTypeEnum.TRADE_FILL
        ).count()
        deposits = db.query(LedgerEventDB).filter(
            LedgerEventDB.type == EventTypeEnum.DEPOSIT
        ).count()
        withdrawals = db.query(LedgerEventDB).filter(
            LedgerEventDB.type == EventTypeEnum.WITHDRAWAL
        ).count()
        external_cashflows = db.query(LedgerEventDB).filter(
            LedgerEventDB.type == EventTypeEnum.EXTERNAL_CASHFLOW
        ).count()

        db_total_lots = db.query(TradeLotDB).count()
        open_lots = db.query(TradeLotDB).filter(
            TradeLotDB.qty_btc_open > 0
        ).count()

        total_allocations = db.query(SellAllocationDB).count()

        print("Database Contents:")
        print(f"  Total Events: {total_events}")
        print(f"    - Trade Fills: {trade_fills}")
        print(f"    - Deposits: {deposits}")
        print(f"    - Withdrawals: {withdrawals}")
        print(f"    - External Cashflows: {external_cashflows}")
        print(f"  Total Lots: {db_total_lots}")
        print(f"    - Open Lots: {open_lots}")
        print(f"  Total Sell Allocations: {total_allocations}")
    print()

    # Step 10: Balance Verification
    print("Step 10: Balance Verification (Lots vs Binance)")
    print("-" * 80)
    try:
        balances = binance_service.fetch_account_balance()
        binance_btc = Decimal("0")
        print("Current Binance Balances:")
        for asset, balance_info in balances.items():
            if asset in ["BTC", "EUR", "BNB"]:
                print(f"  {asset}: {balance_info['total']} "
                      f"(free: {balance_info['free']}, locked: {balance_info['locked']})")
                if asset == "BTC":
                    binance_btc = balance_info['total']

        # BTC aus Lots berechnen
        with Session(engine) as db:
            from app.db.models import TradeLotDB
            lots_btc = db.query(func.sum(TradeLotDB.qty_btc_open)).filter(
                TradeLotDB.user_id == USER_ID
            ).scalar() or Decimal("0")

            print()
            print(f"  BTC in Open Lots:    {lots_btc}")
            print(f"  BTC on Binance:      {binance_btc}")
            diff = lots_btc - binance_btc
            print(f"  Differenz:           {diff}")
            if abs(diff) < Decimal("0.00001"):
                print("  -> OK (Differenz < 0.00001 BTC)")
            else:
                print(f"  -> WARNUNG: Differenz von {diff} BTC!")
                print("     Moegliche Ursachen: offene Orders (locked BTC), "
                      "fehlende Bot-CSV-Trades, oder Deposits/Withdrawals")

    except Exception as e:
        print(f"Could not fetch balances: {e}")
    print()

    print("=" * 80)
    print("DATABASE REBUILD COMPLETE!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Verify data: sqlite3 cashmgnt.db")
    print("2. Start API server: uvicorn app.main:app --reload")
    print("3. Check portfolio: http://localhost:8000/api/portfolio")
    print()


if __name__ == "__main__":
    main()
