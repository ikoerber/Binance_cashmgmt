"""
Order Domain Logic – Pure Funktionen (kein I/O, keine Seiteneffekte).

Berechnet Order-Parameter deterministisch aus Eingabedaten.
Enthaelt Binance Exchange Filter Validierung (LOT_SIZE, PRICE_FILTER, NOTIONAL).
"""
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Any, List

from app.symbol_registry import get_price_precision, get_base_precision, get_quote_asset


# ─── Binance Exchange Filter Types ───


@dataclass(frozen=True)
class SymbolFilters:
    """Binance Exchange Filters fuer ein Trading Pair (immutable, pure data)."""

    # LOT_SIZE
    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal
    # PRICE_FILTER
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    # NOTIONAL / MIN_NOTIONAL
    min_notional: Decimal


def parse_symbol_filters(raw_filters: list[dict]) -> SymbolFilters:
    """
    Extrahiert LOT_SIZE, PRICE_FILTER und NOTIONAL aus Binance exchangeInfo Antwort.

    Args:
        raw_filters: Liste der Filter-Dicts aus Binance Symbol-Info

    Returns:
        SymbolFilters Dataclass

    Raises:
        ValueError: Wenn LOT_SIZE oder PRICE_FILTER fehlt
    """
    filters_by_type = {f["filterType"]: f for f in raw_filters}

    lot_size = filters_by_type.get("LOT_SIZE")
    if not lot_size:
        raise ValueError("LOT_SIZE filter nicht gefunden")

    price_filter = filters_by_type.get("PRICE_FILTER")
    if not price_filter:
        raise ValueError("PRICE_FILTER nicht gefunden")

    # Binance verwendet sowohl NOTIONAL als auch MIN_NOTIONAL (aeltere Symbols)
    notional = filters_by_type.get("NOTIONAL") or filters_by_type.get("MIN_NOTIONAL")
    min_notional = Decimal(notional.get("minNotional", "0")) if notional else Decimal("0")

    return SymbolFilters(
        min_qty=Decimal(lot_size["minQty"]),
        max_qty=Decimal(lot_size["maxQty"]),
        step_size=Decimal(lot_size["stepSize"]),
        min_price=Decimal(price_filter["minPrice"]),
        max_price=Decimal(price_filter["maxPrice"]),
        tick_size=Decimal(price_filter["tickSize"]),
        min_notional=min_notional,
    )


def round_qty_to_step_size(qty: Decimal, step_size: Decimal) -> Decimal:
    """
    Floor-Rundung auf naechstes Vielfaches von step_size.

    Floor statt Round, damit nie mehr als verfuegbar verkauft wird.
    Bei step_size == 0 wird qty unveraendert zurueckgegeben.
    """
    if step_size <= 0:
        return qty
    return (qty // step_size) * step_size


def round_price_to_tick_size(price: Decimal, tick_size: Decimal) -> Decimal:
    """
    Rundet Preis auf naechstes Vielfaches von tick_size (ROUND_HALF_UP).

    Bei tick_size == 0 wird price unveraendert zurueckgegeben.
    """
    if tick_size <= 0:
        return price
    # Anzahl Dezimalstellen aus tick_size ableiten
    # z.B. tick_size=0.01 → quantize auf 2 Stellen
    return price.quantize(tick_size, rounding=ROUND_HALF_UP)


def validate_order_filters(
    qty: Decimal, price: Decimal, filters: SymbolFilters
) -> List[str]:
    """
    Validiert qty und price gegen Binance Exchange Filters.

    Returns:
        Liste von Fehlermeldungen (leer = valide)
    """
    errors = []

    # LOT_SIZE
    if qty < filters.min_qty:
        errors.append(f"Menge {qty} unter Minimum {filters.min_qty}")
    if qty > filters.max_qty:
        errors.append(f"Menge {qty} ueber Maximum {filters.max_qty}")
    if filters.step_size > 0:
        remainder = qty % filters.step_size
        if remainder != Decimal("0"):
            errors.append(
                f"Menge {qty} ist kein Vielfaches von stepSize {filters.step_size}"
            )

    # PRICE_FILTER
    if price < filters.min_price:
        errors.append(f"Preis {price} unter Minimum {filters.min_price}")
    if filters.max_price > 0 and price > filters.max_price:
        errors.append(f"Preis {price} ueber Maximum {filters.max_price}")

    # NOTIONAL
    notional = qty * price
    if filters.min_notional > 0 and notional < filters.min_notional:
        errors.append(
            f"Orderwert {notional} unter minNotional {filters.min_notional}"
        )

    return errors


# ─── Pairing Order Parameter Berechnung ───


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
    # For sub-1 prices (e.g. XRPEUR ~0.50 EUR), use satoshi encoding to avoid int(price) = 0 collisions
    version = "v1"
    safe_pairing_id = re.sub(r'[^a-zA-Z0-9_-]', '', pairing_id)[:12]

    if target_price_rounded >= Decimal("1"):
        price_enc = str(int(target_price_rounded))
    else:
        # Satoshi encoding for sub-1 EUR prices: multiply by 1e8 to get integer representation
        price_enc = str(int(target_price_rounded * Decimal("100000000")))

    # Include short symbol to prevent cross-symbol collisions
    symbol_short = symbol[:6]
    client_order_id = f"{user_id}_p_{safe_pairing_id}_{symbol_short}_{price_enc}_{version}"[:36]

    # Order value in EUR (all pairs are EUR-quoted)
    order_value_eur = total_qty_rounded * target_price_rounded

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
