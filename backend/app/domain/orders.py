"""
Order Domain Logic – Pure Funktionen (kein I/O, keine Seiteneffekte).

Berechnet Order-Parameter deterministisch aus Eingabedaten.
"""
import re
from decimal import Decimal
from typing import Dict, Any

from app.symbol_registry import get_price_precision, get_base_precision, get_quote_asset


def compute_pairing_order_params(
    pairing_id: str,
    user_id: str,
    items: list,
    market_price: Decimal,
    fee_buffer_pct: Decimal = Decimal("0.002"),
    max_order_value_eur: Decimal = Decimal("1000"),
    custom_sell_price: Decimal | None = None,
    symbol: str = "BTCEUR",
    btceur_rate: Decimal | None = None,
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
        btceur_rate: BTC/EUR-Kurs fuer EUR-Konvertierung (Pflicht fuer nicht-EUR-quoted Symbols)

    Returns:
        Dict mit aggregierten Binance-Order-Parametern
    """
    # Precision from symbol registry
    price_prec = get_price_precision(symbol)
    base_prec = get_base_precision(symbol)
    quote_asset = get_quote_asset(symbol)

    price_quantizer = Decimal(10) ** (-price_prec)
    base_quantizer = Decimal(10) ** (-base_prec)

    if custom_sell_price is not None:
        if custom_sell_price.is_nan() or custom_sell_price.is_infinite():
            raise ValueError("custom_sell_price darf nicht NaN oder Infinity sein")
        if custom_sell_price <= 0:
            raise ValueError("custom_sell_price muss groesser als 0 sein")
        target_price_rounded = custom_sell_price.quantize(price_quantizer)
    else:
        target_price = market_price * (Decimal("1") + fee_buffer_pct)
        target_price_rounded = target_price.quantize(price_quantizer)

    total_qty = sum(item.qty_base for item in items)
    total_qty_rounded = total_qty.quantize(base_quantizer)

    # Symbol-aware client_order_id
    # For sub-1 prices (e.g. XRPBTC), use satoshi encoding to avoid int(price) = 0 collisions
    version = "v1"
    safe_pairing_id = re.sub(r'[^a-zA-Z0-9_-]', '', pairing_id)[:12]

    if target_price_rounded >= Decimal("1"):
        price_enc = str(int(target_price_rounded))
    else:
        # Satoshi encoding: multiply by 1e8 to get integer representation
        price_enc = str(int(target_price_rounded * Decimal("100000000")))

    # Include short symbol to prevent cross-symbol collisions
    symbol_short = symbol[:6]
    client_order_id = f"{user_id}_p_{safe_pairing_id}_{symbol_short}_{price_enc}_{version}"[:36]

    # Order value computation: in quote currency first, then convert to EUR if needed
    order_value_quote = total_qty_rounded * target_price_rounded

    if quote_asset == "EUR":
        order_value_eur = order_value_quote
    elif btceur_rate is not None:
        order_value_eur = order_value_quote * btceur_rate
    else:
        # Fallback: use quote value as-is (may be in BTC, conservative check)
        order_value_eur = order_value_quote

    exceeds_max = order_value_eur > max_order_value_eur

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
        "order_value_eur": str(order_value_eur),
        "exceeds_max_order_value": exceeds_max,
        "max_order_value_eur": str(max_order_value_eur),
    }
