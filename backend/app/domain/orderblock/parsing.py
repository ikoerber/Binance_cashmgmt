"""
Orderblock Parsing – Binance Kline Transformation.

Transformiert Binance REST API Kline-Arrays zu Candle-Objekten.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.domain.orderblock.models import Candle


def parse_binance_kline(raw: list) -> Candle:
    """
    Transformiert Binance Kline-Array zu Candle-Objekt.

    Binance Kline Format: [open_time, o, h, l, c, v, close_time, ...]
    Timestamps werden als naive datetime (implizit UTC) gespeichert.

    Args:
        raw: Binance Kline-Array (mindestens 6 Elemente)

    Returns:
        Candle mit Decimal-Praezision
    """
    return Candle(
        timestamp=datetime.fromtimestamp(
            raw[0] / 1000, tz=timezone.utc
        ).replace(tzinfo=None),
        open=Decimal(str(raw[1])),
        high=Decimal(str(raw[2])),
        low=Decimal(str(raw[3])),
        close=Decimal(str(raw[4])),
        volume=Decimal(str(raw[5])),
    )
