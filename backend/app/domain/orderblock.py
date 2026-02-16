"""
Orderblock Detection Engine – Pure Domain-Logik (kein I/O).

Identifiziert hochreaktive institutionelle Preiszonen (Orderblocks)
auf Basis von OHLCV-Kerzen. 5-Phasen-Validierung:
  1. Formation (Base Candle)
  2. Displacement (ATR-basiert)
  3. Fair Value Gap (3-Kerzen-Imbalance)
  4. Structure Break (BOS via Swing Fractal, Close-basiert)
  5. State Management (UNMITIGATED / MITIGATED / INVALID)

Alle Berechnungen verwenden Decimal (niemals float).
Zeitkonsistent: Kein Look-Ahead-Bias. OB gilt erst ab confirmed_at.

Volume Z-Score Filterung fuer HIGH_CONVICTION Markierung.
Mathematische Grundlage: Bouchaud (Preis-Impact), Lopez de Prado (Overfitting-Vermeidung).
Z-Score = (V_impulse - mean(V_lookback)) / std(V_lookback)
wobei V die Volumen der Kerzen sind. Nur OBs mit Z > threshold gelten als HIGH_CONVICTION.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OBDirection(Enum):
    """Orderblock-Richtung"""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class OBState(Enum):
    """Orderblock-Zustand"""

    UNMITIGATED = "UNMITIGATED"
    MITIGATED = "MITIGATED"
    INVALID = "INVALID"


class ConvictionLevel(Enum):
    """Ueberzeugungsstufe basierend auf Composite Conviction Score (4-stufig)."""

    LOW = "LOW"
    STANDARD = "STANDARD"
    HIGH = "HIGH"
    INSTITUTIONAL = "INSTITUTIONAL"


class EntryPolicy(Enum):
    """Entry-Kante Bestimmung"""

    NEAR_EDGE = "NEAR_EDGE"


class StopPolicy(Enum):
    """Stop-Edge Bestimmung"""

    STOP_EDGE_TOUCH = "STOP_EDGE_TOUCH"


class MitigationPolicy(Enum):
    """Mitigation-Kriterium"""

    ZONE_TOUCH = "ZONE_TOUCH"


class OBCategory(Enum):
    """AlbaTherium-Klassifikation: struktureller Kontext eines Orderblocks."""

    EXTREME = "EXTREME"  # Erster/tiefster OB zwischen Major Low und Major High
    DECISIONAL = "DECISIONAL"  # Juengster OB unterhalb des aktuellen IDM
    SMT = "SMT"  # Smart Money Trap: alle OBs zwischen Extreme und Decisional
    UNCLASSIFIED = "UNCLASSIFIED"  # OBs ausserhalb der Major-Struktur


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Candle:
    """OHLCV-Kerze mit Decimal-Praezision."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass
class OBConfig:
    """Deterministische, serialisierbare Strategie-Konfiguration."""

    atr_length: int = 20
    atr_multiplier: Decimal = Decimal("2.0")
    fvg_window: int = 3
    swing_fractal_n: int = 2
    target_rr: Decimal = Decimal("2.0")
    entry_policy: EntryPolicy = EntryPolicy.NEAR_EDGE
    stop_policy: StopPolicy = StopPolicy.STOP_EDGE_TOUCH
    mitigation_policy: MitigationPolicy = MitigationPolicy.ZONE_TOUCH
    zscore_lookback: int = 50
    zscore_threshold: Decimal = Decimal("2.0")
    max_holding_candles: int = 200  # Triple Barrier Zeitlimit (0=deaktiviert)
    impulse_window: int = 5  # Max Kerzen nach OB fuer Displacement/FVG/BOS (AlbaTherium)


@dataclass
class SwingPoint:
    """Fraktal-Swing (High oder Low)."""

    index: int
    timestamp: datetime
    price: Decimal
    is_high: bool  # True = Swing High, False = Swing Low
    confirmed_at_index: int  # Index wenn n Kerzen rechts bestaetigt


@dataclass
class FairValueGap:
    """3-Kerzen-Imbalance (Fair Value Gap)."""

    index: int  # Index der mittleren Kerze (i)
    timestamp: datetime
    gap_top: Decimal
    gap_bottom: Decimal
    direction: OBDirection


@dataclass
class InducementLevel:
    """Inducement (IDM): Liquiditaetslevel aus dem letzten Pullback vor einem Swing High."""

    index: int
    timestamp: datetime
    price: Decimal
    associated_swing_high_index: int  # Der Swing High den dieser Pullback vorausgeht


@dataclass
class Orderblock:
    """Ein validierter Orderblock (Zone)."""

    id: str
    direction: OBDirection
    zone_top: Decimal
    zone_bottom: Decimal
    equilibrium: Decimal
    entry_edge: Decimal
    stop_edge: Decimal
    formed_at: datetime
    confirmed_at: datetime
    formed_at_index: int
    confirmed_at_index: int
    state: OBState
    conviction: ConvictionLevel
    volume_zscore: Decimal
    volume_weight: Decimal
    fvg: FairValueGap
    atr_at_formation: Decimal
    displacement_range: Decimal
    bos_swing_price: Decimal
    config: OBConfig
    volume_percentile: Decimal = Decimal("0")
    ofi_divergence: Decimal = Decimal("0")
    impact_efficiency_ratio: Decimal = Decimal("0")
    conviction_score: Decimal = Decimal("0")
    is_high_conviction_zscore: bool = False  # Spec 4.3: volume_zscore > zscore_threshold
    category: str = "UNCLASSIFIED"  # OBCategory: EXTREME/DECISIONAL/SMT/UNCLASSIFIED
    mitigated_at: Optional[datetime] = None
    invalidated_at: Optional[datetime] = None


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
# Swing Point Detection (Fraktal)
# ---------------------------------------------------------------------------


def _is_inside_bar(candles: List[Candle], index: int) -> bool:
    """
    Inside Bar: High(i) <= High(i-1) AND Low(i) >= Low(i-1).

    Inside Bars etablieren keine neuen Preisextreme und werden
    bei der Swing-Erkennung uebersprungen (AlbaTherium).
    """
    if index <= 0:
        return False
    return (
        candles[index].high <= candles[index - 1].high
        and candles[index].low >= candles[index - 1].low
    )


def find_swing_points(candles: List[Candle], fractal_n: int) -> List[SwingPoint]:
    """
    Fraktal Swing Highs/Lows mit Inside-Bar-Filterung.

    Swing High bei Index i: High(i) > High(j) fuer alle j in [i-n..i-1] und [i+1..i+n]
    Swing Low bei Index i: Low(i) < Low(j) fuer alle j in [i-n..i-1] und [i+1..i+n]

    Inside Bars (Kerzen innerhalb der Range der Vorgaengerkerze) werden
    uebersprungen, da sie keine neuen Preisextreme etablieren (AlbaTherium).

    confirmed_at_index = i + fractal_n (rechte Seite bestaetigt den Swing).
    Zeitkonsistent: Swing wird erst bei confirmed_at_index sichtbar.
    """
    swings: List[SwingPoint] = []
    n = len(candles)

    for i in range(fractal_n, n - fractal_n):
        # Inside Bars uebersprungen (AlbaTherium)
        if _is_inside_bar(candles, i):
            continue
        # Swing High Check
        is_swing_high = True
        for j in range(1, fractal_n + 1):
            if (
                candles[i].high <= candles[i - j].high
                or candles[i].high <= candles[i + j].high
            ):
                is_swing_high = False
                break

        if is_swing_high:
            swings.append(
                SwingPoint(
                    index=i,
                    timestamp=candles[i].timestamp,
                    price=candles[i].high,
                    is_high=True,
                    confirmed_at_index=i + fractal_n,
                )
            )

        # Swing Low Check
        is_swing_low = True
        for j in range(1, fractal_n + 1):
            if (
                candles[i].low >= candles[i - j].low
                or candles[i].low >= candles[i + j].low
            ):
                is_swing_low = False
                break

        if is_swing_low:
            swings.append(
                SwingPoint(
                    index=i,
                    timestamp=candles[i].timestamp,
                    price=candles[i].low,
                    is_high=False,
                    confirmed_at_index=i + fractal_n,
                )
            )

    return swings


# ---------------------------------------------------------------------------
# Fair Value Gap Detection
# ---------------------------------------------------------------------------


def find_fvgs(
    candles: List[Candle],
    start_index: int,
    window: int,
    direction: OBDirection,
) -> List[FairValueGap]:
    """
    3-Kerzen-Imbalance FVGs innerhalb [start_index, start_index + window).

    Bullish FVG bei Kerze i: Low(i) > High(i-2) → Gap = [High(i-2), Low(i)]
    Bearish FVG bei Kerze i: High(i) < Low(i-2) → Gap = [High(i), Low(i-2)]

    Prueft nur FVGs in der angegebenen Richtung.
    """
    fvgs: List[FairValueGap] = []
    n = len(candles)

    # Wir brauchen mindestens 3 Kerzen (i-2, i-1, i)
    # start_index ist die erste Kerze nach dem OB
    for i in range(max(start_index, 2), min(start_index + window + 2, n)):
        if i - 2 < 0:
            continue

        if direction == OBDirection.BULLISH:
            # Bullish FVG: Low(i) > High(i-2)
            if candles[i].low > candles[i - 2].high:
                fvgs.append(
                    FairValueGap(
                        index=i,
                        timestamp=candles[i].timestamp,
                        gap_top=candles[i].low,
                        gap_bottom=candles[i - 2].high,
                        direction=OBDirection.BULLISH,
                    )
                )
        else:
            # Bearish FVG: High(i) < Low(i-2)
            if candles[i].high < candles[i - 2].low:
                fvgs.append(
                    FairValueGap(
                        index=i,
                        timestamp=candles[i].timestamp,
                        gap_top=candles[i - 2].low,
                        gap_bottom=candles[i].high,
                        direction=OBDirection.BEARISH,
                    )
                )

    return fvgs


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
# Hauptlogik: detect_orderblocks
# ---------------------------------------------------------------------------


def detect_orderblocks(
    candles: List[Candle],
    config: OBConfig,
) -> List[Orderblock]:
    """
    Hauptdetektionsfunktion. Verarbeitet Kerzen sequentiell (kein Look-Ahead).

    Phase 1: Formation (Base Candle)
    Phase 2: Displacement (ATR-Check)
    Phase 3: FVG (3-Kerzen-Imbalance)
    Phase 4: BOS (Swing Break, Close-basiert)
    Phase 5: State = UNMITIGATED (initial)
    + Z-Score Filterung fuer HIGH_CONVICTION

    Returns: Liste validierter Orderblocks.
    """
    n = len(candles)
    if n < config.atr_length + config.fvg_window + 5:
        return []

    # Vorberechnungen
    atr_values = compute_atr(candles, config.atr_length)
    all_swings = find_swing_points(candles, config.swing_fractal_n)

    orderblocks: List[Orderblock] = []

    for i in range(config.atr_length + 1, n - config.impulse_window):
        # ATR muss verfuegbar sein
        atr_at_ob = atr_values[i]
        if atr_at_ob is None:
            continue

        # --- Phase 1: Formation Check ---
        # Bullish OB: Bearish Kerze (Close < Open) vor bullischem Impuls
        # Bearish OB: Bullish Kerze (Close > Open) vor bearischem Impuls
        is_bearish_candle = candles[i].close < candles[i].open
        is_bullish_candle = candles[i].close > candles[i].open

        if not is_bearish_candle and not is_bullish_candle:
            continue  # Doji - ueberspringe

        directions_to_check: List[OBDirection] = []
        if is_bearish_candle:
            directions_to_check.append(OBDirection.BULLISH)
        if is_bullish_candle:
            directions_to_check.append(OBDirection.BEARISH)

        for direction in directions_to_check:
            ob = _try_validate_ob(
                candles,
                i,
                direction,
                atr_at_ob,
                config,
                all_swings,
            )
            if ob is not None:
                orderblocks.append(ob)

    # Post-Processing: AlbaTherium-Klassifikation (Extreme/Decisional/SMT)
    orderblocks = classify_orderblocks(orderblocks, all_swings, candles)

    return orderblocks


def _try_validate_ob(
    candles: List[Candle],
    ob_index: int,
    direction: OBDirection,
    atr_at_ob: Decimal,
    config: OBConfig,
    all_swings: List[SwingPoint],
) -> Optional[Orderblock]:
    """Versucht einen einzelnen OB-Kandidaten durch alle 5 Phasen zu validieren."""
    n = len(candles)
    impulse_end = min(ob_index + 1 + config.impulse_window, n)

    # --- Phase 2: Displacement Check ---
    displacement_threshold = config.atr_multiplier * atr_at_ob
    displacement_candle_idx = None
    displacement_range = Decimal("0")

    for j in range(ob_index + 1, impulse_end):
        candle_range = candles[j].high - candles[j].low
        if candle_range >= displacement_threshold:
            # Richtungs-Check: Bullish OB -> Impuls nach oben, Bearish OB -> Impuls nach unten
            if direction == OBDirection.BULLISH and candles[j].close > candles[j].open:
                displacement_candle_idx = j
                displacement_range = candle_range
                break
            elif (
                direction == OBDirection.BEARISH and candles[j].close < candles[j].open
            ):
                displacement_candle_idx = j
                displacement_range = candle_range
                break

    if displacement_candle_idx is None:
        return None

    # --- Phase 3: FVG Check ---
    fvgs = find_fvgs(candles, ob_index + 1, config.impulse_window, direction)
    if not fvgs:
        return None

    # --- Phase 4: BOS/MSS Check (Close-basiert) ---
    # Finde den letzten bestaetigten Swing vor dem OB
    last_swing_high: Optional[SwingPoint] = None
    last_swing_low: Optional[SwingPoint] = None

    for sw in all_swings:
        if sw.confirmed_at_index <= ob_index:
            if sw.is_high:
                if last_swing_high is None or sw.price > last_swing_high.price:
                    last_swing_high = sw
            else:
                if last_swing_low is None or sw.price < last_swing_low.price:
                    last_swing_low = sw

    bos_candle_idx = None
    bos_swing_price = Decimal("0")

    if direction == OBDirection.BULLISH and last_swing_high is not None:
        # Bullish BOS: Close ueber letztem Swing High
        for j in range(ob_index + 1, impulse_end):
            if candles[j].close > last_swing_high.price:
                bos_candle_idx = j
                bos_swing_price = last_swing_high.price
                break
    elif direction == OBDirection.BEARISH and last_swing_low is not None:
        # Bearish BOS: Close unter letztem Swing Low
        for j in range(ob_index + 1, impulse_end):
            if candles[j].close < last_swing_low.price:
                bos_candle_idx = j
                bos_swing_price = last_swing_low.price
                break

    if bos_candle_idx is None:
        return None

    # --- Phase 5: Zone erstellen ---
    zone_top = candles[ob_index].high
    zone_bottom = candles[ob_index].low
    equilibrium = (zone_top + zone_bottom) / Decimal("2")

    if direction == OBDirection.BULLISH:
        entry_edge = zone_top
        stop_edge = zone_bottom
    else:
        entry_edge = zone_bottom
        stop_edge = zone_top

    # Confirmed at = spaetester der 3 Checks (Displacement, FVG, BOS)
    confirmed_at_index = max(displacement_candle_idx, fvgs[0].index, bos_candle_idx)

    # Volume Z-Score (auf Impulse-Phase)
    impulse_volumes = [candles[j].volume for j in range(ob_index + 1, impulse_end)]
    if impulse_volumes:
        # Z-Score des mittleren Impuls-Volumens
        avg_impulse_vol_idx = ob_index + 1
        vol_zscore = compute_volume_zscore(
            candles, avg_impulse_vol_idx, config.zscore_lookback
        )
    else:
        vol_zscore = Decimal("0")

    vol_weight = compute_volume_weight(candles, ob_index, impulse_count=config.impulse_window)

    # Volume Percentile (Cont: robust gegen Heavy Tails)
    vol_percentile = compute_volume_percentile(
        candles, ob_index + 1, config.zscore_lookback
    )

    # OFI Divergence (Bouchaud: Order Flow Imbalance Proxy)
    ofi_div = compute_ofi_divergence(candles, ob_index)

    # Impact Efficiency Ratio (Bouchaud: Square Root Law)
    ier = compute_impact_efficiency_ratio(candles, ob_index, atr_at_ob)

    # Composite Conviction Score (4-Signal Aggregation)
    impulse_candle = candles[displacement_candle_idx]
    conv_score = compute_conviction_score(
        volume_percentile=vol_percentile,
        volume_zscore=vol_zscore,
        ofi_divergence=ofi_div,
        direction=direction,
        impulse_candle=impulse_candle,
        volume_weight=vol_weight,
    )
    conviction = conviction_level_from_score(conv_score)

    # Spec 4.3: Expliziter Z-Score Threshold Filter
    is_hc_zscore = vol_zscore > config.zscore_threshold

    ts = int(candles[ob_index].timestamp.timestamp())
    ob_id = f"ob_{direction.value.lower()}_{ts}"

    return Orderblock(
        id=ob_id,
        direction=direction,
        zone_top=zone_top,
        zone_bottom=zone_bottom,
        equilibrium=equilibrium,
        entry_edge=entry_edge,
        stop_edge=stop_edge,
        formed_at=candles[ob_index].timestamp,
        confirmed_at=candles[confirmed_at_index].timestamp,
        formed_at_index=ob_index,
        confirmed_at_index=confirmed_at_index,
        state=OBState.UNMITIGATED,
        conviction=conviction,
        volume_zscore=vol_zscore,
        volume_weight=vol_weight,
        fvg=fvgs[0],
        atr_at_formation=atr_at_ob,
        displacement_range=displacement_range,
        bos_swing_price=bos_swing_price,
        config=config,
        volume_percentile=vol_percentile,
        ofi_divergence=ofi_div,
        impact_efficiency_ratio=ier,
        conviction_score=conv_score,
        is_high_conviction_zscore=is_hc_zscore,
    )


# ---------------------------------------------------------------------------
# Inducement (IDM) Tracking (AlbaTherium)
# ---------------------------------------------------------------------------


def find_inducement_levels(
    swings: List[SwingPoint],
) -> List[InducementLevel]:
    """
    Findet Inducement-Levels aus der Swing-Struktur.

    Fuer jeden Swing High ist der IDM der tiefste Swing Low zwischen
    dem vorherigen Swing High (oder Start) und diesem Swing High.
    Repraesentiert den letzten Pullback-Tiefpunkt vor dem Push zum neuen High.

    Returns: Inducement-Levels sortiert nach Index.
    """
    inducements: List[InducementLevel] = []

    highs = sorted([s for s in swings if s.is_high], key=lambda s: s.index)
    lows = sorted([s for s in swings if not s.is_high], key=lambda s: s.index)

    for i, sh in enumerate(highs):
        prev_high_idx = highs[i - 1].index if i > 0 else 0

        between_lows = [sl for sl in lows if prev_high_idx < sl.index < sh.index]

        if between_lows:
            idm_swing = min(between_lows, key=lambda sl: sl.price)
            inducements.append(
                InducementLevel(
                    index=idm_swing.index,
                    timestamp=idm_swing.timestamp,
                    price=idm_swing.price,
                    associated_swing_high_index=sh.index,
                )
            )

    return inducements


# ---------------------------------------------------------------------------
# OB-Klassifikation (AlbaTherium: Extreme / Decisional / SMT)
# ---------------------------------------------------------------------------


def classify_orderblocks(
    zones: List[Orderblock],
    swings: List[SwingPoint],
    candles: List[Candle],
) -> List[Orderblock]:
    """
    Post-Processing: Klassifiziert erkannte OBs in strukturelle Kategorien.

    Identifiziert aus der Swing-Struktur:
    - Major High: Hoechster Swing High im Datensatz
    - Major Low: Tiefster Swing Low im Datensatz
    - IDM: Aktuelles Inducement-Level

    Klassifikationsregeln (AlbaTherium):
    - EXTREME: Tiefster Bullish-OB (bzw. hoechster Bearish-OB) zwischen
      Major Low und Major High — Ursprung der Hauptbewegung
    - DECISIONAL: Juengster OB unterhalb des aktuellen IDM —
      institutioneller Re-Entry vor dem finalen Push
    - SMT: Alle anderen OBs zwischen Extreme und Decisional —
      Trapping-Zonen (Smart Money Trap)
    - UNCLASSIFIED: OBs ausserhalb der Major-Struktur

    Pure Funktion: gleicher Input → gleiches Ergebnis.
    """
    if not zones or not swings:
        return zones

    swing_highs = [s for s in swings if s.is_high]
    swing_lows = [s for s in swings if not s.is_high]

    if not swing_highs or not swing_lows:
        return zones

    major_high = max(swing_highs, key=lambda s: s.price)
    major_low = min(swing_lows, key=lambda s: s.price)

    inducements = find_inducement_levels(swings)
    current_idm = inducements[-1].price if inducements else None

    # --- Phase 1: OBs in der Major-Range als SMT markieren ---
    classified: List[Orderblock] = []
    for ob in zones:
        cat = "UNCLASSIFIED"

        if ob.direction == OBDirection.BULLISH:
            if major_low.index <= ob.formed_at_index <= major_high.index:
                cat = "SMT"
        elif ob.direction == OBDirection.BEARISH:
            # Bearish: Major High vor Major Low (Abwaertsbewegung)
            if (
                min(major_high.index, major_low.index)
                <= ob.formed_at_index
                <= max(major_high.index, major_low.index)
            ):
                cat = "SMT"

        classified.append(
            Orderblock(**{**ob.__dict__, "category": cat})
        )

    # --- Phase 2: EXTREME identifizieren ---
    # Bullish: tiefster OB (naechst am Major Low)
    bullish_in_range = [
        ob for ob in classified
        if ob.direction == OBDirection.BULLISH and ob.category == "SMT"
    ]
    if bullish_in_range:
        extreme_id = min(bullish_in_range, key=lambda ob: ob.zone_bottom).id
        classified = [
            Orderblock(**{**ob.__dict__, "category": "EXTREME"})
            if ob.id == extreme_id else ob
            for ob in classified
        ]

    # Bearish: hoechster OB (naechst am Major High)
    bearish_in_range = [
        ob for ob in classified
        if ob.direction == OBDirection.BEARISH and ob.category == "SMT"
    ]
    if bearish_in_range:
        extreme_id = max(bearish_in_range, key=lambda ob: ob.zone_top).id
        classified = [
            Orderblock(**{**ob.__dict__, "category": "EXTREME"})
            if ob.id == extreme_id else ob
            for ob in classified
        ]

    # --- Phase 3: DECISIONAL identifizieren ---
    if current_idm is not None:
        # Bullish: juengster OB unterhalb IDM
        below_idm = [
            ob for ob in classified
            if ob.direction == OBDirection.BULLISH
            and ob.category == "SMT"
            and ob.zone_top < current_idm
        ]
        if below_idm:
            decisional_id = max(below_idm, key=lambda ob: ob.formed_at_index).id
            classified = [
                Orderblock(**{**ob.__dict__, "category": "DECISIONAL"})
                if ob.id == decisional_id else ob
                for ob in classified
            ]

    return classified


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------


def update_zone_states(
    orderblocks: List[Orderblock],
    candles: List[Candle],
) -> List[Orderblock]:
    """
    Aktualisiert Zone-States basierend auf nachfolgenden Kerzen.

    UNMITIGATED -> MITIGATED: Preis beruehrt Zone (High >= bottom AND Low <= top)
    UNMITIGATED/MITIGATED -> INVALID:
      - Bullish: Low <= zone_bottom (Wick-Touch, konservativ)
      - Bearish: High >= zone_top (Wick-Touch, konservativ)

    Verarbeitet Kerzen ab confirmed_at_index + 1 (zeitkonsistent).
    """
    n = len(candles)
    updated: List[Orderblock] = []

    for ob in orderblocks:
        new_state = ob.state
        mitigated_at = ob.mitigated_at
        invalidated_at = ob.invalidated_at

        for j in range(ob.confirmed_at_index + 1, n):
            c = candles[j]

            if new_state == OBState.INVALID:
                break

            # Invalidierung pruefen (Wick-Touch, konservativ)
            if ob.direction == OBDirection.BULLISH and c.low <= ob.zone_bottom:
                new_state = OBState.INVALID
                invalidated_at = c.timestamp
                break
            elif ob.direction == OBDirection.BEARISH and c.high >= ob.zone_top:
                new_state = OBState.INVALID
                invalidated_at = c.timestamp
                break

            # Mitigation pruefen (Zone Touch)
            if new_state == OBState.UNMITIGATED:
                if c.high >= ob.zone_bottom and c.low <= ob.zone_top:
                    new_state = OBState.MITIGATED
                    mitigated_at = c.timestamp

        updated.append(
            Orderblock(
                id=ob.id,
                direction=ob.direction,
                zone_top=ob.zone_top,
                zone_bottom=ob.zone_bottom,
                equilibrium=ob.equilibrium,
                entry_edge=ob.entry_edge,
                stop_edge=ob.stop_edge,
                formed_at=ob.formed_at,
                confirmed_at=ob.confirmed_at,
                formed_at_index=ob.formed_at_index,
                confirmed_at_index=ob.confirmed_at_index,
                state=new_state,
                conviction=ob.conviction,
                volume_zscore=ob.volume_zscore,
                volume_weight=ob.volume_weight,
                fvg=ob.fvg,
                atr_at_formation=ob.atr_at_formation,
                displacement_range=ob.displacement_range,
                bos_swing_price=ob.bos_swing_price,
                config=ob.config,
                volume_percentile=ob.volume_percentile,
                ofi_divergence=ob.ofi_divergence,
                impact_efficiency_ratio=ob.impact_efficiency_ratio,
                conviction_score=ob.conviction_score,
                is_high_conviction_zscore=ob.is_high_conviction_zscore,
                category=ob.category,
                mitigated_at=mitigated_at,
                invalidated_at=invalidated_at,
            )
        )

    return updated


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
