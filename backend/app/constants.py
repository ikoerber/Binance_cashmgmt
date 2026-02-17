"""
Zentralisierte Konstanten fuer die gesamte Applikation.

Vermeidet Duplikation von Mappings und Magic Values ueber Services hinweg.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# Minimale BTC-Praezision (1 Satoshi = 0.00000001 BTC)
# Verwendet als Schwellwert fuer Dust-Mengen in Sell-Allocation und Lot-Status-Checks.
# Mengen <= MIN_BTC_PRECISION werden als Null behandelt.
MIN_BTC_PRECISION = Decimal("0.00000001")

# Binance Order Status -> Interner Status
# Verwendet in: order_service, order_tracking_service, reconciliation_service,
#               websocket_event_handler
# Quelle: https://binance-docs.github.io/apidocs/spot/en/#order-status-status
BINANCE_ORDER_STATUS_MAP: dict[str, str] = {
    "NEW": "OPEN",
    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
    "FILLED": "FILLED",
    "CANCELED": "CANCELLED",
    "PENDING_CANCEL": "CANCELLED",
    "REJECTED": "REJECTED",
    "EXPIRED": "EXPIRED",
    "EXPIRED_IN_MATCH": "EXPIRED",
}


def map_binance_order_status(binance_status: str) -> str | None:
    """
    Mapped Binance Order Status auf internen Status.

    Gibt None zurueck bei unbekanntem Status (statt stillschweigend 'OPEN').
    Caller muessen None explizit behandeln.

    Args:
        binance_status: Status-String von Binance API

    Returns:
        Interner Status-String oder None bei unbekanntem Status
    """
    internal = BINANCE_ORDER_STATUS_MAP.get(binance_status)
    if internal is None:
        logger.warning(
            "Unbekannter Binance Order Status '%s' — kein Mapping vorhanden. "
            "BINANCE_ORDER_STATUS_MAP muss erweitert werden.",
            binance_status,
        )
    return internal
