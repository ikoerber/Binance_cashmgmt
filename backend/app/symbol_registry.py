"""
Symbol Registry - Zentrales Mapping von Symbol → Base/Quote/Precision.

Alle Schichten (Domain, Services, API, Frontend) referenzieren diese Registry.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TradingPair:
    symbol: str          # "BTCEUR"
    base_asset: str      # "BTC"
    quote_asset: str     # "EUR"
    base_precision: int  # 8 für BTC, 5 für ETH
    price_precision: int  # 2
    label: str           # "BTC/EUR"


KNOWN_PAIRS = {
    "BTCEUR": TradingPair("BTCEUR", "BTC", "EUR", 8, 2, "BTC/EUR"),
    "ETHEUR": TradingPair("ETHEUR", "ETH", "EUR", 5, 2, "ETH/EUR"),
    "XRPEUR": TradingPair("XRPEUR", "XRP", "EUR", 2, 4, "XRP/EUR"),
    "XRPBTC": TradingPair("XRPBTC", "XRP", "BTC", 2, 8, "XRP/BTC"),
}


def parse_symbol(symbol: str) -> TradingPair:
    """Gibt TradingPair für ein Symbol zurück. Wirft ValueError bei unbekanntem Symbol."""
    pair = KNOWN_PAIRS.get(symbol)
    if not pair:
        raise ValueError(f"Unknown symbol: {symbol}. Known: {list(KNOWN_PAIRS.keys())}")
    return pair


def get_base_asset(symbol: str) -> str:
    """Gibt Base-Asset für ein Symbol zurück (z.B. 'BTC' für 'BTCEUR')."""
    return parse_symbol(symbol).base_asset


def get_symbols_for_base_asset(base_asset: str) -> list[str]:
    """Returns all known symbols for a given base asset.

    Examples:
        get_symbols_for_base_asset("XRP") -> ["XRPEUR", "XRPBTC"]
        get_symbols_for_base_asset("BTC") -> ["BTCEUR"]
        get_symbols_for_base_asset("ETH") -> ["ETHEUR"]

    Raises:
        ValueError: If no symbols found for the base asset.
    """
    symbols = [
        pair.symbol for pair in KNOWN_PAIRS.values() if pair.base_asset == base_asset
    ]
    if not symbols:
        raise ValueError(f"No symbols found for base asset: {base_asset}")
    return symbols


def get_base_precision(symbol: str) -> int:
    """Gibt Base-Precision für ein Symbol zurück (z.B. 8 für BTC)."""
    return parse_symbol(symbol).base_precision


def get_price_precision(symbol: str) -> int:
    """Gibt Price-Precision für ein Symbol zurück (z.B. 2)."""
    return parse_symbol(symbol).price_precision


def get_quote_asset(symbol: str) -> str:
    """Gibt Quote-Asset für ein Symbol zurück (z.B. 'EUR' für 'BTCEUR')."""
    return parse_symbol(symbol).quote_asset


def get_min_base_precision(symbol: str) -> Decimal:
    """Gibt kleinste handelbare Einheit zurück (z.B. 0.00000001 für BTC, 0.00001 für ETH)."""
    return Decimal(10) ** (-parse_symbol(symbol).base_precision)


def is_known_symbol(symbol: str) -> bool:
    """Prüft ob ein Symbol bekannt ist."""
    return symbol in KNOWN_PAIRS
