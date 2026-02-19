"""
Symbol Registry - Zentrales Mapping von Symbol → Base/Quote/Precision.

Alle Schichten (Domain, Services, API, Frontend) referenzieren diese Registry.
"""
from dataclasses import dataclass


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


def get_base_precision(symbol: str) -> int:
    """Gibt Base-Precision für ein Symbol zurück (z.B. 8 für BTC)."""
    return parse_symbol(symbol).base_precision


def get_price_precision(symbol: str) -> int:
    """Gibt Price-Precision für ein Symbol zurück (z.B. 2)."""
    return parse_symbol(symbol).price_precision


def is_known_symbol(symbol: str) -> bool:
    """Prüft ob ein Symbol bekannt ist."""
    return symbol in KNOWN_PAIRS
