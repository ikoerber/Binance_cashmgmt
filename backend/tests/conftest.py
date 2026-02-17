"""
Pytest Konfiguration - Test-Keys fuer Binance + Shared Test Factories.

Stellt sicher, dass alle Tests die TEST_BINANCE_API_KEY verwenden
statt der Produktions-Keys. Setzt BINANCE_TESTNET=true.
"""
import os
import warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from dotenv import load_dotenv

from app.domain.orderblock import Candle

# ─── Shared Test Factories (Orderblock) ───

OB_BASE_TIME = datetime(2024, 1, 1, 0, 0, 0)


def make_candle(index, o, h, low, c, v="100"):
    """Erzeugt eine Test-Candle mit Index-basiertem Timestamp."""
    return Candle(
        timestamp=OB_BASE_TIME + timedelta(hours=index),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(v),
    )


def make_binance_kline(index, o="100", h="101", low="99", c="100", v="100"):
    """Erzeugt ein Binance-Kline-Array (Liste) im API-Format."""
    ts = int(
        (OB_BASE_TIME + timedelta(hours=index))
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )
    return [
        ts,
        o,
        h,
        low,
        c,
        v,
        ts + 3600000 - 1,
        "0",
        10,
        "50",
        "0",
        "0",
    ]

# .env laden damit TEST_BINANCE_API_KEY verfuegbar ist
load_dotenv()


@pytest.fixture(autouse=True, scope="session")
def use_test_binance_keys():
    """Alle Tests verwenden TEST_BINANCE_API_KEY statt Produktions-Keys."""
    test_key = os.getenv("TEST_BINANCE_API_KEY")
    test_secret = os.getenv("TEST_BINANCE_API_SECRET")

    if not test_key or not test_secret:
        warnings.warn(
            "TEST_BINANCE_API_KEY oder TEST_BINANCE_API_SECRET fehlen in .env! "
            "Tests koennten versehentlich Produktions-Keys verwenden.",
            UserWarning,
            stacklevel=2,
        )
        return

    os.environ["BINANCE_API_KEY"] = test_key
    os.environ["BINANCE_API_SECRET"] = test_secret
    os.environ["BINANCE_TESTNET"] = "true"
