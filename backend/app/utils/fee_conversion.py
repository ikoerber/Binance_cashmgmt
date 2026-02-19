"""
Fee-Konvertierung: Quote-Currency-Wert einer Fee berechnen.

Pure Funktion (kein I/O) — gehoert in Utils, nicht in Domain oder Services,
da sie von beiden Schichten genutzt wird.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def compute_fee_quote_value(
    fee_amount: Decimal | None,
    fee_asset: str | None,
    fill_price: Decimal | None,
    fee_conversion_rates: dict[str, Decimal] | None = None,
    quote_asset: str = "EUR",
    base_asset: str | None = None,
) -> Decimal | None:
    """
    Berechnet den Quote-Currency-Wert einer Fee (zentrale Implementierung).

    Wird von Domain-Logik, SyncService und CSV-Import genutzt.

    Args:
        fee_amount: Fee-Betrag (im jeweiligen Asset)
        fee_asset: Fee-Asset (z.B. "EUR", "BTC", "BNB")
        fill_price: Preis des Fills (fuer Base-Asset-Fee-Konvertierung)
        fee_conversion_rates: Konvertierungsraten zu Quote-Currency (z.B. {"BNB": Decimal("700.00")})
        quote_asset: Quote-Currency des Trading-Pairs (z.B. "EUR", "BTC")
        base_asset: Base-Asset des Trading-Pairs (z.B. "BTC", "XRP") — fuer fill_price Konvertierung

    Returns:
        Quote-Currency-Wert der Fee, oder None wenn keine Fee oder kein Konvertierungskurs
    """
    if not fee_amount or fee_amount == 0:
        return None

    if fee_asset == quote_asset:
        # Fee ist bereits in Quote-Currency
        return fee_amount
    elif fee_asset == base_asset and fill_price:
        # Fee in Base-Asset — ueber Trade-Preis (Base/Quote) konvertieren
        return fee_amount * fill_price
    elif fee_asset and fee_conversion_rates is not None and fee_asset in fee_conversion_rates:
        # Fee in anderem Asset mit Konvertierungsrate (z.B. BNB)
        return fee_amount * fee_conversion_rates[fee_asset]

    # Kein Konvertierungskurs verfuegbar
    return None
