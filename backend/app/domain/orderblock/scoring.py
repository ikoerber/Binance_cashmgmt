"""
Orderblock Scoring – Volume-Analyse, Conviction Score, ATR.

Quantitative Bewertung von Orderblock-Zonen basierend auf
Volume Z-Score, Percentile (Cont), OFI Divergence (Bouchaud),
Impact Efficiency Ratio und Composite Conviction Score.

Alle Berechnungen verwenden Decimal (niemals float).
"""

from decimal import Decimal
from typing import List, Optional

from app.domain.orderblock.models import Candle, ConvictionLevel, OBDirection


# ---------------------------------------------------------------------------
# ATR Berechnung (Wilder's Smoothing)
# ---------------------------------------------------------------------------


def compute_atr(candles: List[Candle], length: int) -> List[Optional[Decimal]]:
    """
    True Range ATR mit Wilder's Smoothing.

    TR(i) = max(H(i)-L(i), |H(i)-C(i-1)|, |L(i)-C(i-1)|)
    ATR initialisiert als SMA der ersten `length` TRs,
    dann: ATR(i) = (ATR(i-1) * (length-1) + TR(i)) / length

    Returns: Liste aligned mit candles. Erste `length` Eintraege sind None.
    """
    n = len(candles)
    if n == 0:
        return []

    result: List[Optional[Decimal]] = [None] * n
    if n <= length:
        return result

    # True Range berechnen
    tr_values: List[Decimal] = [candles[0].high - candles[0].low]
    for i in range(1, n):
        c = candles[i]
        prev_close = candles[i - 1].close
        hl = c.high - c.low
        hc = abs(c.high - prev_close)
        lc = abs(c.low - prev_close)
        tr_values.append(max(hl, hc, lc))

    # SMA der ersten `length` TRs (Index 1..length, da Index 0 hat keinen prev_close fuer echte TR)
    atr_sum = sum(tr_values[1 : length + 1])
    length_d = Decimal(str(length))
    atr = atr_sum / length_d
    result[length] = atr

    # Wilder's Smoothing
    for i in range(length + 1, n):
        atr = (atr * (length_d - Decimal("1")) + tr_values[i]) / length_d
        result[i] = atr

    return result


# ---------------------------------------------------------------------------
# Volume Z-Score
# ---------------------------------------------------------------------------


def compute_volume_zscore(
    candles: List[Candle],
    index: int,
    lookback: int,
) -> Decimal:
    """
    Z-Score des Volumens bei index vs. vorherige `lookback` Kerzen.

    Z = (V - mean) / std
    Bei unzureichender Historie oder std=0: Z = 0.
    """
    if index < lookback or index >= len(candles):
        return Decimal("0")

    volumes = [candles[i].volume for i in range(index - lookback, index)]
    n = Decimal(str(len(volumes)))

    if n == 0:
        return Decimal("0")

    mean = sum(volumes) / n
    variance = sum((v - mean) ** 2 for v in volumes) / n

    if variance == 0:
        return Decimal("0")

    # Decimal sqrt via Newton's method
    std = _decimal_sqrt(variance)
    if std == 0:
        return Decimal("0")

    return (candles[index].volume - mean) / std


def compute_volume_weight(
    candles: List[Candle],
    ob_index: int,
    impulse_count: int = 3,
) -> Decimal:
    """
    volume_weight = Volume(impulse_phase) / SMA(Volume, 20)

    Impulse_phase = erste `impulse_count` Kerzen nach OB.
    """
    n = len(candles)
    if ob_index + impulse_count >= n:
        return Decimal("0")

    # Impulse-Phase Volumen (Summe)
    impulse_vol = sum(
        candles[ob_index + 1 + j].volume
        for j in range(min(impulse_count, n - ob_index - 1))
    )

    # SMA(Volume, 20) vor OB
    sma_lookback = 20
    if ob_index < sma_lookback:
        return Decimal("0")

    sma_vol = sum(
        candles[ob_index - sma_lookback + j].volume for j in range(sma_lookback)
    ) / Decimal(str(sma_lookback))

    if sma_vol == 0:
        return Decimal("0")

    return impulse_vol / sma_vol


# ---------------------------------------------------------------------------
# Volume Percentile (Cont: robust gegen Heavy-Tailed Verteilungen)
# ---------------------------------------------------------------------------


def compute_volume_percentile(
    candles: List[Candle],
    index: int,
    lookback: int,
) -> Decimal:
    """
    Rank-basierter Volumen-Percentile bei index vs. vorherige `lookback` Kerzen.

    percentile = count(V_lookback < V_index) / lookback * 100

    Robust gegen Heavy-Tailed Verteilungen (Cont):
    Order-Volumina folgen Power-Law P(V>x) ~ x^(-alpha), alpha ~1.3-1.7.
    Z-Score (Gauss-Annahme) ist dort unzuverlaessig, Percentile nicht.

    Bei unzureichender Historie: Decimal("50") (neutral).
    """
    if index < lookback or index >= len(candles):
        return Decimal("50")

    current_vol = candles[index].volume
    count_below = sum(
        1 for i in range(index - lookback, index) if candles[i].volume < current_vol
    )

    return Decimal(str(count_below)) / Decimal(str(lookback)) * Decimal("100")


# ---------------------------------------------------------------------------
# OFI Divergence (Bouchaud: Order Flow Imbalance Proxy aus OHLCV)
# ---------------------------------------------------------------------------


def _compute_clv_ofi(candle: Candle) -> Decimal:
    """
    Close Location Value * Volume fuer eine einzelne Kerze.

    CLV = (2*Close - High - Low) / (High - Low), Bereich [-1, +1].
    Positiv = Close nahe High (Kaufdruck), Negativ = Close nahe Low (Verkaufsdruck).
    Bei Doji (High == Low): 0.
    """
    hl_range = candle.high - candle.low
    if hl_range == 0:
        return Decimal("0")
    clv = (Decimal("2") * candle.close - candle.high - candle.low) / hl_range
    return clv * candle.volume


def compute_ofi_divergence(
    candles: List[Candle],
    ob_index: int,
    formation_lookback: int = 5,
    impulse_count: int = 3,
) -> Decimal:
    """
    Order Flow Imbalance Divergenz (Bouchaud).

    Misst die Verschiebung des Order Flows von der Formations- zur Impulsphase.
    CLV-Proxy: (2*Close - High - Low) / (High - Low), volumengewichtet.

    OFI_formation = Durchschnitt CLV*Vol der `formation_lookback` Kerzen vor OB.
    OFI_impulse = Durchschnitt CLV*Vol der `impulse_count` Kerzen nach OB.
    Divergenz = OFI_impulse - OFI_formation.

    Bullish OB: Positive Divergenz erwartet (Shift von Selling zu Buying).
    Bearish OB: Negative Divergenz erwartet (Shift von Buying zu Selling).

    Returns Decimal("0") bei unzureichenden Daten.
    """
    n = len(candles)

    # Formation Phase
    form_start = max(0, ob_index - formation_lookback)
    form_count = ob_index - form_start
    if form_count <= 0:
        return Decimal("0")

    formation_ofi = sum(_compute_clv_ofi(candles[i]) for i in range(form_start, ob_index))
    formation_ofi = formation_ofi / Decimal(str(form_count))

    # Impulse Phase
    imp_start = ob_index + 1
    imp_end = min(ob_index + 1 + impulse_count, n)
    imp_count = imp_end - imp_start
    if imp_count <= 0:
        return Decimal("0")

    impulse_ofi = sum(_compute_clv_ofi(candles[i]) for i in range(imp_start, imp_end))
    impulse_ofi = impulse_ofi / Decimal(str(imp_count))

    return impulse_ofi - formation_ofi


# ---------------------------------------------------------------------------
# Impact Efficiency Ratio (Bouchaud: Square Root Law)
# ---------------------------------------------------------------------------


def compute_impact_efficiency_ratio(
    candles: List[Candle],
    ob_index: int,
    atr_at_formation: Decimal,
    formation_lookback: int = 5,
    avg_vol_lookback: int = 20,
) -> Decimal:
    """
    Impact Efficiency Ratio (Bouchaud Square Root Law).

    IER = participation_rate / normalized_displacement^2

    participation_rate = cumulative_vol(formation) / avg_vol
    normalized_displacement = abs(price_move_formation) / ATR

    Hoher IER = viel Volumen bei wenig Preisbewegung = institutionelle Akkumulation.
    Niedriger IER = Preisbewegung proportional zum Volumen = Retail/News.

    Basiert auf Bouchaud: Delta_P = Y * sigma * sqrt(Q/V).
    Umgestellt: IER = Q/V / (Delta_P/sigma)^2 >> 1 bei Akkumulation.

    Returns Decimal("0") bei unzureichenden Daten oder Null-Displacement.
    """
    if atr_at_formation == 0:
        return Decimal("0")

    # Formation Phase Volumen
    form_start = max(0, ob_index - formation_lookback)
    if form_start >= ob_index:
        return Decimal("0")

    cumulative_vol = sum(candles[i].volume for i in range(form_start, ob_index + 1))

    # Durchschnittsvolumen
    avg_start = max(0, ob_index - avg_vol_lookback)
    avg_count = ob_index - avg_start
    if avg_count <= 0:
        return Decimal("0")

    avg_vol = sum(candles[i].volume for i in range(avg_start, ob_index)) / Decimal(
        str(avg_count)
    )
    if avg_vol == 0:
        return Decimal("0")

    participation_rate = cumulative_vol / avg_vol

    # Normalisierter Displacement
    price_move = abs(candles[ob_index].close - candles[form_start].open)
    normalized_displacement = price_move / atr_at_formation

    if normalized_displacement == 0:
        return Decimal("0")

    return participation_rate / (normalized_displacement ** 2)


# ---------------------------------------------------------------------------
# Composite Conviction Score (Cont + Bouchaud: 4-Signal Aggregation)
# ---------------------------------------------------------------------------


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    """Begrenzt value auf [lo, hi]."""
    return max(lo, min(hi, value))


def _approx_tanh(x: Decimal) -> Decimal:
    """Approximation von tanh via x/(1+|x|). Bereich: (-1, +1)."""
    return x / (Decimal("1") + abs(x))


def _body_ratio(candle: Candle) -> Decimal:
    """Body/Range Verhaeltnis (0-1). Doji = 0."""
    hl_range = candle.high - candle.low
    if hl_range == 0:
        return Decimal("0")
    return abs(candle.close - candle.open) / hl_range


def compute_conviction_score(
    volume_percentile: Decimal,
    volume_zscore: Decimal,
    ofi_divergence: Decimal,
    direction: OBDirection,
    impulse_candle: Candle,
    volume_weight: Decimal,
) -> Decimal:
    """
    Composite Conviction Score (0-100) aus 4 Signalen (je 25% Gewicht).

    Komponenten:
      1. Volume Percentile (0-100, direkt) - Cont: robust gegen Heavy Tails
      2. Z-Score normalisiert: min(z/4 * 100, 100) - Standard-Signal
      3. OFI Divergenz: richtungsabhaengig via Sigmoid -> [0, 100] - Bouchaud
      4. Impulse Intensity: body_ratio * vol_weight_ratio * 100 - Bouchaud

    Returns: Decimal Score in [0, 100].
    """
    _zero = Decimal("0")
    _hundred = Decimal("100")

    # Komponente 1: Volume Percentile (bereits 0-100)
    c1 = _clamp(volume_percentile, _zero, _hundred)

    # Komponente 2: Normalisierter Z-Score (z=0 -> 0, z=4+ -> 100)
    c2 = _clamp(volume_zscore / Decimal("4") * _hundred, _zero, _hundred)

    # Komponente 3: OFI Divergenz (richtungsabhaengig)
    direction_sign = Decimal("1") if direction == OBDirection.BULLISH else Decimal("-1")
    ofi_signed = ofi_divergence * direction_sign
    ofi_norm = Decimal("50") + Decimal("50") * _approx_tanh(
        ofi_signed / Decimal("1000")
    )
    c3 = _clamp(ofi_norm, _zero, _hundred)

    # Komponente 4: Impulse Intensity (Body-Stärke * Volumen-Staerke)
    body_r = _body_ratio(impulse_candle)
    vol_ratio = volume_weight / Decimal("3")  # weight=3 -> ratio=1
    intensity_raw = body_r * vol_ratio * _hundred
    c4 = _clamp(intensity_raw, _zero, _hundred)

    # Gewichteter Durchschnitt (25% je Komponente)
    score = (c1 + c2 + c3 + c4) / Decimal("4")
    return _clamp(score, _zero, _hundred)


def conviction_level_from_score(score: Decimal) -> ConvictionLevel:
    """Mappt Composite Score auf ConvictionLevel."""
    if score < Decimal("35"):
        return ConvictionLevel.LOW
    elif score < Decimal("55"):
        return ConvictionLevel.STANDARD
    elif score < Decimal("75"):
        return ConvictionLevel.HIGH
    else:
        return ConvictionLevel.INSTITUTIONAL


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _decimal_sqrt(value: Decimal, precision: int = 20) -> Decimal:
    """Newton's method Quadratwurzel fuer Decimal."""
    if value < 0:
        raise ValueError("Cannot compute sqrt of negative value")
    if value == 0:
        return Decimal("0")

    # Startwert
    x = value
    two = Decimal("2")

    for _ in range(precision):
        x_new = (x + value / x) / two
        if x_new == x:
            break
        x = x_new

    return x
