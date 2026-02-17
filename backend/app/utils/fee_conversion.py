"""
Fee-Konvertierung: EUR-Wert einer Fee berechnen.

Pure Funktion (kein I/O) — gehoert in Utils, nicht in Domain oder Services,
da sie von beiden Schichten genutzt wird.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def compute_fee_eur_value(
    fee_amount: Decimal | None,
    fee_asset: str | None,
    fill_price: Decimal | None,
    fee_conversion_rates: dict[str, Decimal] | None = None,
) -> Decimal | None:
    """
    Berechnet den EUR-Wert einer Fee (zentrale Implementierung).

    Wird von Domain-Logik, SyncService und CSV-Import genutzt.

    Args:
        fee_amount: Fee-Betrag (im jeweiligen Asset)
        fee_asset: Fee-Asset (z.B. "EUR", "BTC", "BNB")
        fill_price: Preis des Fills (fuer BTC-Fee-Konvertierung)
        fee_conversion_rates: Konvertierungsraten zu EUR (z.B. {"BNB": Decimal("700.00")})

    Returns:
        EUR-Wert der Fee, oder None wenn keine Fee oder kein Konvertierungskurs

    Raises:
        ValueError: Wenn fee_conversion_rates vorhanden aber Asset nicht enthalten
    """
    if not fee_amount or fee_amount == 0:
        return None

    if fee_asset == "EUR":
        return fee_amount
    elif fee_asset == "BTC" and fill_price:
        return fee_amount * fill_price
    elif fee_asset and fee_conversion_rates is not None:
        if fee_asset in fee_conversion_rates:
            return fee_amount * fee_conversion_rates[fee_asset]
        raise ValueError(
            f"No conversion rate for fee asset {fee_asset}. "
            f"Available rates: {list(fee_conversion_rates.keys())}"
        )

    # Kein conversion_rates dict uebergeben (z.B. CSV-Import ohne historische Daten)
    return None
