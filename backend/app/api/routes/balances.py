"""
Balances API Routes

Liefert aktive Symbole basierend auf Binance-Kontostaenden.
"""
import logging
import os
from decimal import Decimal

from fastapi import APIRouter

from app.symbol_registry import KNOWN_PAIRS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/balances", tags=["balances"])

# Dust threshold: Balances darunter gelten als "nicht gehalten"
DUST_THRESHOLD = Decimal("0.00000001")


@router.get("/{user_id}/active-symbols")
def get_active_symbols(user_id: str):
    """
    Gibt die aktiven Symbole basierend auf Binance-Balancen zurueck.

    Logik:
    - Fuer jedes KNOWN_PAIR: Wenn das base_asset eine Balance > dust threshold hat, ist das Paar aktiv.
    - XRPBTC Sonderregel: Wird angezeigt wenn XRP gehalten wird (unabhaengig von BTC Balance).
    - Fallback: Wenn kein Symbol qualifiziert, wird ["BTCEUR"] zurueckgegeben.
    - Graceful Degradation: Bei Binance-Fehler werden alle Symbole zurueckgegeben.

    Returns:
        {"active_symbols": [...], "balances": {...}}
    """
    try:
        from app.services.binance import BinanceService

        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet = os.getenv("BINANCE_TESTNET", "").lower() == "true"

        service = BinanceService(api_key, api_secret, testnet=testnet)
        raw_balances = service.fetch_account_balance()

        # String-serialisierte Balances fuer Response
        balances_str = {}
        for asset, info in raw_balances.items():
            balances_str[asset] = str(info["total"])

        # Aktive Symbole bestimmen
        active = []
        for symbol, pair in KNOWN_PAIRS.items():
            base = pair.base_asset
            balance = raw_balances.get(base, {})
            total = balance.get("total", Decimal("0"))

            if total > DUST_THRESHOLD:
                active.append(symbol)

        # Fallback: Wenn keine Symbole qualifizieren, BTCEUR als Default
        if not active:
            active = ["BTCEUR"]

        return {
            "active_symbols": active,
            "balances": balances_str,
        }

    except Exception:
        logger.exception("Fehler beim Abrufen der Binance-Balancen fuer active-symbols")
        return {
            "active_symbols": list(KNOWN_PAIRS.keys()),
            "balances": {},
            "error": "Balance fetch failed",
        }
