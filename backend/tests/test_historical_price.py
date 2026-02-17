"""
Tests fuer historische Fee-Konvertierung

Testet:
- BinanceService.get_historical_price()
- SyncService._get_per_fill_fee_conversion_rates()
- compute_fee_eur_value() (domain/lots.py)
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.services.binance import BinanceService
from app.services.sync_service import SyncService
from app.domain.lots import compute_fee_eur_value
from app.domain.models import LedgerEvent, EventType, EventSource, TradeSide


# === BinanceService.get_historical_price() ===


def test_get_historical_price_returns_decimal():
    """Test: get_historical_price gibt Decimal Close-Preis zurueck"""
    mock_client = MagicMock()
    mock_client.get_klines.return_value = [
        [
            1704067200000,  # open time
            "700.00",       # open
            "705.00",       # high
            "698.00",       # low
            "702.50",       # close (Index 4)
            "100.0",        # volume
            1704067259999,  # close time
            "70250.0",      # quote asset volume
            50,             # trades
            "60.0",         # taker buy base
            "42150.0",      # taker buy quote
            "0",            # ignore
        ]
    ]

    with patch("app.services.binance_public_client.get_binance_public_client", return_value=mock_client):
        service = BinanceService("key", "secret")
        price = service.get_historical_price("BNBEUR", datetime(2024, 1, 1, 12, 0))

        assert price == Decimal("702.50")
        assert isinstance(price, Decimal)

        # Pruefe API-Aufruf
        mock_client.get_klines.assert_called_once()
        args, kwargs = mock_client.get_klines.call_args
        assert args == ("BNBEUR", "1m")
        assert kwargs["limit"] == 1
        assert "start_time" in kwargs


def test_get_historical_price_no_data_raises():
    """Test: Leere Klines -> Exception"""
    mock_client = MagicMock()
    mock_client.get_klines.return_value = []

    with patch("app.services.binance_public_client.get_binance_public_client", return_value=mock_client):
        service = BinanceService("key", "secret")

        with pytest.raises(Exception, match="No kline data"):
            service.get_historical_price("BNBEUR", datetime(2024, 1, 1, 12, 0))


def test_get_historical_price_uses_public_client():
    """Test: get_historical_price nutzt BinancePublicClient statt direktem requests.get"""
    mock_client = MagicMock()
    mock_client.get_klines.return_value = [
        [0, "0", "0", "0", "500.00", "0", 0, "0", 0, "0", "0", "0"]
    ]

    with patch("app.services.binance_public_client.get_binance_public_client", return_value=mock_client):
        service = BinanceService("key", "secret")
        price = service.get_historical_price("BNBEUR", datetime(2024, 1, 1, 12, 0))

        assert price == Decimal("500.00")
        mock_client.get_klines.assert_called_once()
        args, kwargs = mock_client.get_klines.call_args
        assert args == ("BNBEUR", "1m")
        assert kwargs["limit"] == 1
        assert "start_time" in kwargs


# === SyncService._get_per_fill_fee_conversion_rates() ===


def _make_fill(fill_id, timestamp, fee_asset="BNB", fee_amount="0.001"):
    return LedgerEvent(
        id=fill_id,
        type=EventType.TRADE_FILL,
        timestamp=timestamp,
        asset="BTC",
        amount=Decimal("0.01"),
        symbol="BTCEUR",
        price=Decimal("50000.00"),
        side=TradeSide.BUY,
        fee_asset=fee_asset,
        fee_amount=Decimal(fee_amount),
        source=EventSource.BINANCE,
    )


def test_per_fill_rates_minute_caching():
    """Test: Fills in derselben Minute teilen sich einen API-Call"""
    mock_binance = MagicMock()
    mock_binance.get_historical_price.return_value = Decimal("700.00")

    sync = SyncService(mock_binance)

    # 3 Fills in derselben Minute
    fills = [
        _make_fill("f1", datetime(2024, 1, 1, 12, 30, 10)),
        _make_fill("f2", datetime(2024, 1, 1, 12, 30, 25)),
        _make_fill("f3", datetime(2024, 1, 1, 12, 30, 45)),
    ]

    rates = sync._get_per_fill_fee_conversion_rates(fills)

    # Nur 1 API-Call (alle in derselben Minute)
    assert mock_binance.get_historical_price.call_count == 1

    # Alle 3 Fills bekommen den gleichen Preis
    assert rates["f1"] == {"BNB": Decimal("700.00")}
    assert rates["f2"] == {"BNB": Decimal("700.00")}
    assert rates["f3"] == {"BNB": Decimal("700.00")}


def test_per_fill_rates_different_minutes():
    """Test: Fills in verschiedenen Minuten -> separate API-Calls"""
    mock_binance = MagicMock()
    mock_binance.get_historical_price.side_effect = [
        Decimal("700.00"),
        Decimal("710.00"),
    ]

    sync = SyncService(mock_binance)

    fills = [
        _make_fill("f1", datetime(2024, 1, 1, 12, 30)),
        _make_fill("f2", datetime(2024, 1, 1, 12, 31)),
    ]

    rates = sync._get_per_fill_fee_conversion_rates(fills)

    assert mock_binance.get_historical_price.call_count == 2
    assert rates["f1"] == {"BNB": Decimal("700.00")}
    assert rates["f2"] == {"BNB": Decimal("710.00")}


def test_per_fill_rates_graceful_fallback():
    """Test: Falls historisch fehlschlaegt, Fallback auf aktuellen Preis"""
    mock_binance = MagicMock()
    mock_binance.get_historical_price.side_effect = Exception("API Error")
    mock_binance.get_current_price.return_value = Decimal("705.00")

    sync = SyncService(mock_binance)
    fills = [_make_fill("f1", datetime(2024, 1, 1, 12, 30))]

    rates = sync._get_per_fill_fee_conversion_rates(fills)

    assert rates["f1"] == {"BNB": Decimal("705.00")}
    mock_binance.get_current_price.assert_called_once_with("BNBEUR")


def test_per_fill_rates_both_fail():
    """Test: Historisch + Aktuell fehlschlagen -> kein Rate"""
    mock_binance = MagicMock()
    mock_binance.get_historical_price.side_effect = Exception("API Error")
    mock_binance.get_current_price.side_effect = Exception("API Error")

    sync = SyncService(mock_binance)
    fills = [_make_fill("f1", datetime(2024, 1, 1, 12, 30))]

    rates = sync._get_per_fill_fee_conversion_rates(fills)

    assert "f1" not in rates


def test_per_fill_rates_skips_eur_btc_fees():
    """Test: EUR- und BTC-Fees brauchen keine Konvertierung"""
    mock_binance = MagicMock()
    sync = SyncService(mock_binance)

    fills = [
        _make_fill("f1", datetime(2024, 1, 1, 12, 30), fee_asset="EUR", fee_amount="1.00"),
        _make_fill("f2", datetime(2024, 1, 1, 12, 31), fee_asset="BTC", fee_amount="0.00001"),
    ]

    rates = sync._get_per_fill_fee_conversion_rates(fills)

    assert rates == {}
    mock_binance.get_historical_price.assert_not_called()


# === compute_fee_eur_value() (domain/lots.py) ===


def test_compute_fee_eur_value_eur_fee():
    """Test: EUR-Fee -> direkt zurueckgeben"""
    result = compute_fee_eur_value(Decimal("1.50"), "EUR", Decimal("50000"), {})
    assert result == Decimal("1.50")


def test_compute_fee_eur_value_btc_fee():
    """Test: BTC-Fee -> fee_amount * fill_price"""
    result = compute_fee_eur_value(Decimal("0.00001"), "BTC", Decimal("50000"), {})
    # 0.00001 * 50000 = 0.50
    assert result == Decimal("0.50000")


def test_compute_fee_eur_value_bnb_fee():
    """Test: BNB-Fee -> fee_amount * conversion_rate"""
    result = compute_fee_eur_value(Decimal("0.001"), "BNB", Decimal("50000"), {"BNB": Decimal("700.00")})
    # 0.001 * 700 = 0.70
    assert result == Decimal("0.700")


def test_compute_fee_eur_value_no_fee():
    """Test: Kein Fee -> None"""
    result = compute_fee_eur_value(None, None, Decimal("50000"), {})
    assert result is None


def test_compute_fee_eur_value_unknown_asset():
    """Test: Unbekanntes Fee-Asset ohne Rate -> ValueError"""
    with pytest.raises(ValueError, match="No conversion rate for fee asset XRP"):
        compute_fee_eur_value(Decimal("10"), "XRP", Decimal("50000"), {})
