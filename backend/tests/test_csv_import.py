"""
Unit Tests für CSV Import Service - Trading Bot Trades

Testet das Parsen der Binance Trading Bots CSV und die Konvertierung
zu LedgerEvents ohne DB-Abhängigkeit.
"""
import pytest
from datetime import datetime
from decimal import Decimal

from app.services.csv_import_service import (
    parse_amount_with_asset,
    generate_bot_trade_source_id,
    parse_trading_bots_csv,
)
from app.domain.models import EventType, EventSource, TradeSide


# === parse_amount_with_asset ===

def test_parse_btc_amount():
    """Parst BTC-Betrag korrekt"""
    amount, asset = parse_amount_with_asset("0.0080100000BTC")
    assert amount == Decimal("0.0080100000")
    assert asset == "BTC"


def test_parse_eur_amount():
    """Parst EUR-Betrag korrekt"""
    amount, asset = parse_amount_with_asset("624.37950000EUR")
    assert amount == Decimal("624.37950000")
    assert asset == "EUR"


def test_parse_bnb_amount():
    """Parst BNB-Betrag korrekt"""
    amount, asset = parse_amount_with_asset("0.00082344BNB")
    assert amount == Decimal("0.00082344")
    assert asset == "BNB"


def test_parse_small_btc_fee():
    """Parst sehr kleine BTC-Fee korrekt"""
    amount, asset = parse_amount_with_asset("0.0000080100BTC")
    assert amount == Decimal("0.0000080100")
    assert asset == "BTC"


def test_parse_invalid_format():
    """Fehler bei ungültigem Format"""
    with pytest.raises(ValueError):
        parse_amount_with_asset("invalid")


def test_parse_empty_string():
    """Fehler bei leerem String"""
    with pytest.raises(ValueError):
        parse_amount_with_asset("")


# === generate_bot_trade_source_id ===

def test_source_id_deterministic():
    """Source-ID ist deterministisch (gleicher Input → gleicher Output)"""
    row = {
        "Date(UTC)": "2026-01-11 02:49:13",
        "Side": "SELL",
        "Price": "77950.0000000000",
        "Executed": "0.0080100000BTC",
        "Fee": "0.6243795000EUR",
    }
    id1 = generate_bot_trade_source_id(row, 0)
    id2 = generate_bot_trade_source_id(row, 0)
    assert id1 == id2
    assert id1.startswith("bot_")


def test_source_id_unique_for_different_trades():
    """Verschiedene Trades erzeugen verschiedene Source-IDs"""
    row1 = {
        "Date(UTC)": "2026-01-11 02:49:13",
        "Side": "SELL",
        "Price": "77950.0000000000",
        "Executed": "0.0080100000BTC",
        "Fee": "0.6243795000EUR",
    }
    row2 = {
        "Date(UTC)": "2026-01-10 22:09:34",
        "Side": "BUY",
        "Price": "77700.0000000000",
        "Executed": "0.0080100000BTC",
        "Fee": "0.0000080100BTC",
    }
    assert generate_bot_trade_source_id(row1, 0) != generate_bot_trade_source_id(row2, 1)


def test_source_id_unique_for_identical_rows():
    """Identische Zeilen mit unterschiedlichem Index erzeugen verschiedene IDs"""
    row = {
        "Date(UTC)": "2025-12-23 22:36:33",
        "Side": "BUY",
        "Price": "73950.0000000000",
        "Executed": "0.0004000000BTC",
        "Fee": "0.0000004000BTC",
    }
    ids = {generate_bot_trade_source_id(row, i) for i in range(3)}
    assert len(ids) == 3


# === parse_trading_bots_csv ===

SAMPLE_CSV = '''"Date(UTC)","Pair","Side","Price","Executed","Amount","Fee"
"2026-01-10 22:09:34","BTCEUR","BUY","77700.0000000000","0.0080100000BTC","622.37700000EUR","0.0000080100BTC"
"2026-01-11 02:49:13","BTCEUR","SELL","77950.0000000000","0.0080100000BTC","624.37950000EUR","0.6243795000EUR"
'''

SAMPLE_CSV_WITH_BOM = '\ufeff"Date(UTC)","Pair","Side","Price","Executed","Amount","Fee"\n"2026-01-10 22:09:34","BTCEUR","BUY","77700.0000000000","0.0080100000BTC","622.37700000EUR","0.0000080100BTC"\n'


def test_parse_csv_basic():
    """Parst CSV mit Buy und Sell korrekt"""
    events = parse_trading_bots_csv(SAMPLE_CSV)

    assert len(events) == 2

    # Chronologisch sortiert: Buy zuerst (22:09), dann Sell (02:49)
    buy = events[0]
    sell = events[1]

    assert buy.side == TradeSide.BUY
    assert sell.side == TradeSide.SELL


def test_parse_csv_buy_event():
    """BUY-Event wird korrekt konvertiert"""
    events = parse_trading_bots_csv(SAMPLE_CSV)
    buy = events[0]

    assert buy.type == EventType.TRADE_FILL
    assert buy.asset == "BTC"
    assert buy.amount == Decimal("0.0080100000")
    assert buy.price == Decimal("77700.0000000000")
    assert buy.symbol == "BTCEUR"
    assert buy.side == TradeSide.BUY
    assert buy.fee_asset == "BTC"
    assert buy.fee_amount == Decimal("0.0000080100")
    assert buy.source == EventSource.BINANCE
    assert buy.timestamp == datetime(2026, 1, 10, 22, 9, 34)


def test_parse_csv_sell_event():
    """SELL-Event wird korrekt konvertiert"""
    events = parse_trading_bots_csv(SAMPLE_CSV)
    sell = events[1]

    assert sell.side == TradeSide.SELL
    assert sell.amount == Decimal("0.0080100000")
    assert sell.price == Decimal("77950.0000000000")
    assert sell.fee_asset == "EUR"
    assert sell.fee_amount == Decimal("0.6243795000")


def test_parse_csv_source_id():
    """Source-IDs sind gesetzt und einzigartig"""
    events = parse_trading_bots_csv(SAMPLE_CSV)
    assert all(e.source_id is not None for e in events)
    assert all(e.source_id.startswith("bot_") for e in events)
    # IDs sind unterschiedlich
    assert events[0].source_id != events[1].source_id


def test_parse_csv_event_ids():
    """Event-IDs folgen dem erwarteten Format"""
    events = parse_trading_bots_csv(SAMPLE_CSV)
    assert all(e.id.startswith("binance_bot_BTCEUR_") for e in events)


def test_parse_csv_chronological_order():
    """Events sind chronologisch sortiert"""
    events = parse_trading_bots_csv(SAMPLE_CSV)
    for i in range(len(events) - 1):
        assert events[i].timestamp <= events[i + 1].timestamp


def test_parse_csv_with_bom():
    """CSV mit BOM-Marker wird korrekt geparst"""
    events = parse_trading_bots_csv(SAMPLE_CSV_WITH_BOM)
    assert len(events) == 1
    assert events[0].side == TradeSide.BUY


def test_parse_csv_empty():
    """Leere CSV ergibt leere Liste"""
    csv = '"Date(UTC)","Pair","Side","Price","Executed","Amount","Fee"\n'
    events = parse_trading_bots_csv(csv)
    assert events == []


def test_parse_csv_raw_payload():
    """Raw payload enthält CSV-Zeile und Import-Source"""
    events = parse_trading_bots_csv(SAMPLE_CSV)
    for event in events:
        assert event.raw_payload is not None
        assert "csv_row" in event.raw_payload
        assert event.raw_payload["import_source"] == "trading_bots_csv"


def test_parse_csv_note():
    """Note zeigt Trading Bot Herkunft an"""
    events = parse_trading_bots_csv(SAMPLE_CSV)
    for event in events:
        assert "Trading Bot" in event.note


def test_parse_csv_idempotent_source_ids():
    """Zweimaliges Parsen ergibt gleiche Source-IDs (für Duplikat-Erkennung)"""
    events1 = parse_trading_bots_csv(SAMPLE_CSV)
    events2 = parse_trading_bots_csv(SAMPLE_CSV)

    for e1, e2 in zip(events1, events2):
        assert e1.source_id == e2.source_id
        assert e1.id == e2.id


# === Test mit echten Daten-Mustern ===

REAL_DATA_SAMPLE = '''"Date(UTC)","Pair","Side","Price","Executed","Amount","Fee"
"2025-12-29 03:58:24","BTCEUR","SELL","76343.5300000000","0.0006500000BTC","49.62329450EUR","0.0496232900EUR"
"2025-12-29 08:04:39","BTCEUR","BUY","75808.4300000000","0.0006500000BTC","49.27547950EUR","0.0000006500BTC"
"2025-12-29 09:41:21","BTCEUR","BUY","74738.2300000000","0.0002200000BTC","16.44241060EUR","0.0000002200BTC"
"2025-12-29 09:41:21","BTCEUR","BUY","74738.2300000000","0.0004300000BTC","32.13743890EUR","0.0000004300BTC"
'''


def test_parse_real_data_multiple_buys_same_time():
    """Mehrere Buys zur gleichen Sekunde werden als separate Events geparst"""
    events = parse_trading_bots_csv(REAL_DATA_SAMPLE)
    assert len(events) == 4

    # Die beiden Buys um 09:41:21 sind separate Events
    same_time = [e for e in events if e.timestamp == datetime(2025, 12, 29, 9, 41, 21)]
    assert len(same_time) == 2
    assert same_time[0].source_id != same_time[1].source_id


def test_parse_real_data_small_btc_fees():
    """Sehr kleine BTC-Fees werden korrekt geparst"""
    events = parse_trading_bots_csv(REAL_DATA_SAMPLE)
    buy_events = [e for e in events if e.side == TradeSide.BUY]

    for buy in buy_events:
        assert buy.fee_asset == "BTC"
        assert buy.fee_amount > 0
        assert buy.fee_amount < Decimal("0.001")


def test_parse_real_data_sell_eur_fees():
    """Sell-Fees in EUR werden korrekt geparst"""
    events = parse_trading_bots_csv(REAL_DATA_SAMPLE)
    sell_events = [e for e in events if e.side == TradeSide.SELL]

    for sell in sell_events:
        assert sell.fee_asset == "EUR"
        assert sell.fee_amount > 0
