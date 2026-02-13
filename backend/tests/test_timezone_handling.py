"""
Unit Tests für Timezone-Handling

Stellt sicher, dass alle Timestamps in UTC gespeichert werden
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.services.binance import BinanceService


@pytest.fixture
def binance_service():
    """BinanceService mit gemocktem Client (kein Netzwerkzugriff)."""
    with patch("app.services.binance.Client") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        service = BinanceService(api_key="test", api_secret="test", testnet=True)
    return service


def test_binance_trade_timestamp_is_utc(binance_service):
    """Test: Binance Trade Timestamps werden korrekt in UTC konvertiert"""

    # Mock Binance Trade mit bekanntem UTC Timestamp
    # 2026-02-09 19:53:00 UTC = 1770666780000 milliseconds
    mock_trade = {
        "id": 167736655,
        "orderId": 5264855609,
        "symbol": "BTCEUR",
        "price": "57650.00",
        "qty": "0.01",
        "quoteQty": "576.50",
        "commission": "0.00082344",
        "commissionAsset": "BNB",
        "time": 1770666780000,  # 2026-02-09 19:53:00 UTC
        "isBuyer": True,
        "isMaker": True,
        "isBestMatch": True,
    }

    service = binance_service

    # Konvertiere Trade zu LedgerEvent
    event = service._trade_to_ledger_event(mock_trade, "BTCEUR")

    # Erwarteter Timestamp (UTC)
    expected_timestamp = datetime(2026, 2, 9, 19, 53, 0)

    # Prüfe, dass Timestamp korrekt ist (UTC, ohne Timezone-Info)
    assert event.timestamp == expected_timestamp
    assert event.timestamp.tzinfo is None  # Naive datetime (wie in DB)

    # Prüfe, dass es NICHT in lokaler Zeit ist
    # Wenn es in lokaler Zeit wäre (z.B. CET/CEST = UTC+1/+2),
    # wäre der Timestamp 20:53:00 oder 21:53:00, nicht 19:53:00
    assert event.timestamp.hour == 19
    assert event.timestamp.minute == 53


def test_multiple_timestamps_same_day(binance_service):
    """Test: Mehrere Trades am selben Tag, verschiedene Zeiten"""

    service = binance_service

    trades = [
        {
            "id": 1,
            "orderId": 1,
            "symbol": "BTCEUR",
            "price": "50000.00",
            "qty": "0.01",
            "quoteQty": "500.00",
            "commission": "0.0001",
            "commissionAsset": "BNB",
            "time": 1770609200000,  # 2026-02-09 03:53:20 UTC
            "isBuyer": True,
            "isMaker": True,
            "isBestMatch": True,
        },
        {
            "id": 2,
            "orderId": 2,
            "symbol": "BTCEUR",
            "price": "51000.00",
            "qty": "0.01",
            "quoteQty": "510.00",
            "commission": "0.0001",
            "commissionAsset": "BNB",
            "time": 1770666780000,  # 2026-02-09 19:53:00 UTC
            "isBuyer": True,
            "isMaker": True,
            "isBestMatch": True,
        },
        {
            "id": 3,
            "orderId": 3,
            "symbol": "BTCEUR",
            "price": "52000.00",
            "qty": "0.01",
            "quoteQty": "520.00",
            "commission": "0.0001",
            "commissionAsset": "BNB",
            "time": 1770681200000,  # 2026-02-09 23:53:20 UTC
            "isBuyer": True,
            "isMaker": True,
            "isBestMatch": True,
        },
    ]

    events = [service._trade_to_ledger_event(trade, "BTCEUR") for trade in trades]

    # Alle sollten am 2026-02-09 sein (UTC)
    for event in events:
        assert event.timestamp.year == 2026
        assert event.timestamp.month == 2
        assert event.timestamp.day == 9

    # Zeitstempel sollten aufsteigend sein
    assert events[0].timestamp < events[1].timestamp < events[2].timestamp

    # Prüfe spezifische Zeiten
    assert events[0].timestamp.hour == 3
    assert events[1].timestamp.hour == 19
    assert events[2].timestamp.hour == 23


def test_timestamp_across_midnight(binance_service):
    """Test: Timestamps über Mitternacht hinweg"""

    service = binance_service

    # 23:59:00 am 2026-02-09
    trade_before_midnight = {
        "id": 1,
        "orderId": 1,
        "symbol": "BTCEUR",
        "price": "50000.00",
        "qty": "0.01",
        "quoteQty": "500.00",
        "commission": "0.0001",
        "commissionAsset": "BNB",
        "time": 1770681540000,  # 2026-02-09 23:59:00 UTC
        "isBuyer": True,
        "isMaker": True,
        "isBestMatch": True,
    }

    # 00:01:00 am 2026-02-10
    trade_after_midnight = {
        "id": 2,
        "orderId": 2,
        "symbol": "BTCEUR",
        "price": "51000.00",
        "qty": "0.01",
        "quoteQty": "510.00",
        "commission": "0.0001",
        "commissionAsset": "BNB",
        "time": 1770681660000,  # 2026-02-10 00:01:00 UTC
        "isBuyer": True,
        "isMaker": True,
        "isBestMatch": True,
    }

    event1 = service._trade_to_ledger_event(trade_before_midnight, "BTCEUR")
    event2 = service._trade_to_ledger_event(trade_after_midnight, "BTCEUR")

    # Verschiedene Tage
    assert event1.timestamp.day == 9
    assert event2.timestamp.day == 10

    # Korrekte Zeiten
    assert event1.timestamp.hour == 23
    assert event1.timestamp.minute == 59
    assert event2.timestamp.hour == 0
    assert event2.timestamp.minute == 1
