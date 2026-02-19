"""
Order Domain Logic – Pure Funktionen (kein I/O, keine Seiteneffekte).

Berechnet Order-Parameter deterministisch aus Eingabedaten.
"""
import re
from decimal import Decimal
from typing import Dict, Any


def compute_pairing_order_params(
    pairing_id: str,
    user_id: str,
    items: list,
    market_price: Decimal,
    fee_buffer_pct: Decimal = Decimal("0.002"),
    max_order_value_eur: Decimal = Decimal("1000"),
    custom_sell_price: Decimal | None = None,
    symbol: str = "BTCEUR",
) -> Dict[str, Any]:
    """
    Berechnet aggregierte Binance-Order-Parameter fuer ein Pairing.

    Alle Lots werden zu einer einzigen Order zusammengefasst, da der
    Zielpreis (market_price + fee_buffer) fuer alle Lots identisch ist.

    Reine Berechnung ohne Seiteneffekte (kein DB-Zugriff, kein Binance-Call).

    Args:
        pairing_id: Pairing ID
        user_id: User ID
        items: Liste von PairingItems mit lot_id und qty_base
        market_price: Aktueller Marktpreis
        fee_buffer_pct: Fee-Puffer (Default: 0.2%)
        max_order_value_eur: Max. Orderwert (aus UserSettings)
        custom_sell_price: Optionaler benutzerdefinierter Verkaufspreis (ueberschreibt Berechnung)
        symbol: Trading Pair (Default: BTCEUR)

    Returns:
        Dict mit aggregierten Binance-Order-Parametern
    """
    if custom_sell_price is not None:
        if custom_sell_price.is_nan() or custom_sell_price.is_infinite():
            raise ValueError("custom_sell_price darf nicht NaN oder Infinity sein")
        if custom_sell_price <= 0:
            raise ValueError("custom_sell_price muss groesser als 0 sein")
        target_price_rounded = custom_sell_price.quantize(Decimal("0.01"))
    else:
        target_price = market_price * (Decimal("1") + fee_buffer_pct)
        target_price_rounded = target_price.quantize(Decimal("0.01"))

    total_qty = sum(item.qty_base for item in items)
    total_qty_rounded = total_qty.quantize(Decimal("0.00001"))

    version = "v1"
    safe_pairing_id = re.sub(r'[^a-zA-Z0-9_-]', '', pairing_id)[:12]
    client_order_id = f"{user_id}_pairing_{safe_pairing_id}_{int(target_price_rounded)}_{version}"[:36]

    order_value = total_qty_rounded * target_price_rounded
    exceeds_max = order_value > max_order_value_eur

    lot_ids = [item.lot_id for item in items]

    return {
        "lot_ids": lot_ids,
        "lot_count": len(items),
        "symbol": symbol,
        "side": "SELL",
        "type": "TAKE_PROFIT_LIMIT",
        "timeInForce": "GTC",
        "quantity": str(total_qty_rounded),
        "price": str(target_price_rounded),
        "stopPrice": str(target_price_rounded),
        "newClientOrderId": client_order_id,
        "order_value_eur": str(order_value),
        "exceeds_max_order_value": exceeds_max,
        "max_order_value_eur": str(max_order_value_eur),
    }
