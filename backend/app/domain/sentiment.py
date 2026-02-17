"""
SentimentEngine Domain-Logik (pure, kein I/O).

Aggregiert 5 Pillars zu einem normalisierten Sentiment Score (0-100):
  1. Fear & Greed Index (28%)
  2. Funding Rate (20%)
  3. Taker Buy/Sell Ratio (18%)
  4. Trend-Deviation / DMA-Composite (42%)
  5. Volume-Momentum (12%)

Gewichte basieren auf Backtest-Korrelation mit 30d-Forward-Returns.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional
import math


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class SentimentLabel(Enum):
    EXTREME_FEAR = "Extreme Fear"
    FEAR = "Fear"
    NEUTRAL = "Neutral"
    GREED = "Greed"
    EXTREME_GREED = "Extreme Greed"


LABEL_COLORS = {
    SentimentLabel.EXTREME_FEAR: "#dc2626",
    SentimentLabel.FEAR: "#f97316",
    SentimentLabel.NEUTRAL: "#64748b",
    SentimentLabel.GREED: "#22c55e",
    SentimentLabel.EXTREME_GREED: "#16a34a",
}

LABEL_THRESHOLDS = [
    (Decimal("15"), SentimentLabel.EXTREME_FEAR),
    (Decimal("35"), SentimentLabel.FEAR),
    (Decimal("65"), SentimentLabel.NEUTRAL),
    (Decimal("85"), SentimentLabel.GREED),
    (Decimal("100"), SentimentLabel.EXTREME_GREED),
]

# Normalisierte Pillar-Gewichte (Backtest-Korrelation mit 30d-Forward-Returns)
# Rohwerte vor Normalisierung: DMA 0.42, F&G 0.28, Funding 0.20, Taker 0.18, Volume 0.12
V3_PILLAR_WEIGHTS = {
    "dma": Decimal("0.35"),       # DMA-Composite (hoechste Korrelation)
    "fng": Decimal("0.2333"),     # Fear & Greed Index
    "funding": Decimal("0.1667"), # Funding Rate
    "taker": Decimal("0.15"),     # Taker Buy/Sell Ratio
    "volume": Decimal("0.10"),    # Volume-Momentum (niedrigste Korrelation)
}
# Summe = 1.0 (Renormalisierung greift nur bei fehlenden Pillars)

# Piecewise Linear Multiplier Kontrollpunkte
V3_MULTIPLIER_FLOOR = Decimal("1.50")    # Score 0 (Extreme Fear)
V3_MULTIPLIER_CEILING = Decimal("0.85")  # Score 100 (Extreme Greed)
V3_NEUTRAL_BAND_LO = Decimal("40")
V3_NEUTRAL_BAND_HI = Decimal("60")

# Dispersion
V3_DISPERSION_MAX_STD = Decimal("30")  # Pillar-StdDev ab der Confidence -> 0

# Volatility-Scaling
V3_VOL_HIGH_THRESHOLD = Decimal("1.5")    # vol_ratio oberhalb -> HIGH Regime
V3_VOL_LOW_THRESHOLD = Decimal("0.7")     # vol_ratio unterhalb -> LOW Regime
V3_VOL_HIGH_COMPRESSION = Decimal("0.5")  # Multiplier-Deviation skalieren in HIGH
V3_VOL_LOW_EXPANSION = Decimal("1.2")     # Multiplier-Deviation skalieren in LOW

# Funding Rate: Feste Schwellwerte (kein Percentile - keine hinreichende Historie verfuegbar)
# Negative Rate = Shorts zahlen Longs = bearish sentiment -> niedriger Score
# Positive Rate = Longs zahlen Shorts = bullish sentiment -> hoher Score
_FUNDING_RATE_BRACKETS = [
    # (rate_low, rate_high, score_low, score_high)
    (Decimal("-0.001"), Decimal("-0.0003"), Decimal("0"), Decimal("10")),
    (Decimal("-0.0003"), Decimal("-0.00005"), Decimal("10"), Decimal("35")),
    (Decimal("-0.00005"), Decimal("0.0002"), Decimal("35"), Decimal("65")),
    (Decimal("0.0002"), Decimal("0.0004"), Decimal("65"), Decimal("90")),
    (Decimal("0.0004"), Decimal("0.001"), Decimal("90"), Decimal("100")),
]

# Action-Map
_V3_ACTION_MAP = {
    SentimentLabel.EXTREME_FEAR: "Aggressiv akkumulieren",
    SentimentLabel.FEAR: "Erhoehte Kaufgroessen",
    SentimentLabel.NEUTRAL: "Standard-Parameter",
    SentimentLabel.GREED: "Vorsichtiger, engere Stops",
    SentimentLabel.EXTREME_GREED: "Reduziert, De-Risking",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PillarScore:
    name: str
    score: Decimal          # 0-100 normalisiert
    raw_value: Optional[Decimal] = None
    source: str = ""
    quality: str = "live"   # live | cached | stale | unavailable
    description: str = ""


@dataclass
class DispersionInfo:
    pillar_std: Decimal           # Standardabweichung der aktiven Pillar-Scores
    confidence_factor: Decimal    # 0.0 bis 1.0 (Anteil des Raw-Multiplier-Signals)
    high_dispersion: bool         # True wenn Pillars stark divergieren


@dataclass
class VolatilityScaling:
    realized_vol_20d: Decimal     # 20-Tage realisierte Volatilitaet
    avg_vol_120d: Decimal         # 120-Tage Durchschnitts-Volatilitaet
    vol_ratio: Decimal            # realized_vol_20d / avg_vol_120d
    regime: str                   # "HIGH", "NORMAL", "LOW"
    scaling_factor: Decimal       # Angewandt auf Multiplier-Deviation


@dataclass
class SentimentRecommendationV3:
    action: str
    buy_size_multiplier: Decimal  # Finaler Multiplier (nach Dispersion + Vol)
    raw_multiplier: Decimal       # Vor Dispersion/Vol-Anpassung
    dispersion: DispersionInfo
    volatility: Optional[VolatilityScaling]


@dataclass
class SentimentResultV3:
    composite_score: Decimal
    composite_label: SentimentLabel
    composite_color: str
    recommendation: SentimentRecommendationV3
    pillars: List[PillarScore]
    active_pillars: int
    total_pillars: int = 5
    timestamp: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value: Decimal, lo: Decimal = Decimal("0"), hi: Decimal = Decimal("100")) -> Decimal:
    return max(lo, min(hi, value))


def _linear_interpolate(
    value: Decimal,
    in_lo: Decimal,
    in_hi: Decimal,
    out_lo: Decimal,
    out_hi: Decimal,
) -> Decimal:
    """Lineares Mapping von [in_lo, in_hi] auf [out_lo, out_hi], geclampt."""
    if in_hi == in_lo:
        return (out_lo + out_hi) / 2
    t = (value - in_lo) / (in_hi - in_lo)
    t = max(Decimal("0"), min(Decimal("1"), t))
    return out_lo + t * (out_hi - out_lo)


def classify_score(score: Decimal) -> SentimentLabel:
    for threshold, label in LABEL_THRESHOLDS:
        if score <= threshold:
            return label
    return SentimentLabel.EXTREME_GREED


# ---------------------------------------------------------------------------
# Funding Rate Scoring
# ---------------------------------------------------------------------------

def score_funding_rate(rate: Optional[Decimal]) -> PillarScore:
    """
    Funding Rate Scoring via feste Schwellwerte (Piecewise-Linear).

    Negative Rate (Shorts zahlen Longs) -> Fear (niedriger Score).
    Positive Rate (Longs zahlen Shorts) -> Greed (hoher Score).
    Neutrale Zone um 0.01% (Standard-Rate).
    """
    if rate is None:
        return PillarScore(
            name="Funding Rate",
            score=Decimal("50"),
            raw_value=None,
            source="okx",
            quality="unavailable",
            description="Daten nicht verfuegbar",
        )

    score = Decimal("50")
    for r_lo, r_hi, s_lo, s_hi in _FUNDING_RATE_BRACKETS:
        if r_lo <= rate < r_hi:
            score = _linear_interpolate(rate, r_lo, r_hi, s_lo, s_hi)
            break
    else:
        if rate < Decimal("-0.001"):
            score = Decimal("0")
        elif rate >= Decimal("0.001"):
            score = Decimal("100")

    score = _clamp(score).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    rate_pct = rate * Decimal("100")
    return PillarScore(
        name="Funding Rate",
        score=score,
        raw_value=rate,
        source="okx",
        quality="live",
        description=f"Rate: {rate_pct:+.4f}%",
    )


# ---------------------------------------------------------------------------
# Rolling-Percentile Scoring
# ---------------------------------------------------------------------------

def rolling_percentile(value: Decimal, history: List[Decimal]) -> Decimal:
    """
    Berechnet den Percentile-Rank eines Wertes in einer Historie (0-100).

    Statt fixer Schwellwerte wird der Wert relativ zu seiner eigenen
    juengsten Vergangenheit bewertet. Das normalisiert automatisch
    fuer verschiedene Marktregime.
    """
    if not history:
        return Decimal("50")
    sorted_hist = sorted(history)
    n = len(sorted_hist)
    below = sum(1 for h in sorted_hist if h < value)
    equal = sum(1 for h in sorted_hist if h == value)
    # Percentile: (below + 0.5 * equal) / n * 100
    percentile = (Decimal(str(below)) + Decimal("0.5") * Decimal(str(equal))) / Decimal(str(n)) * Decimal("100")
    return _clamp(percentile).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pillar-Dispersion
# ---------------------------------------------------------------------------

def compute_pillar_dispersion(pillar_scores: List[Decimal]) -> DispersionInfo:
    """
    Berechnet die Standardabweichung der Pillar-Scores als Konfidenz-Mass.

    Hohe Uebereinstimmung -> volles Signal,
    hohe Divergenz -> neutralisiert.
    """
    n = len(pillar_scores)
    if n <= 1:
        return DispersionInfo(
            pillar_std=Decimal("0"),
            confidence_factor=Decimal("1"),
            high_dispersion=False,
        )

    mean = sum(pillar_scores) / Decimal(str(n))
    variance = sum((s - mean) ** 2 for s in pillar_scores) / Decimal(str(n))
    std = variance.sqrt() if variance > 0 else Decimal("0")

    # Confidence: linear von 1.0 (std=0) bis 0.0 (std >= MAX_STD)
    confidence = _clamp(
        Decimal("1") - std / V3_DISPERSION_MAX_STD,
        lo=Decimal("0"),
        hi=Decimal("1"),
    )

    high_disp = std >= V3_DISPERSION_MAX_STD / 2  # ab std >= 15

    return DispersionInfo(
        pillar_std=std.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        confidence_factor=confidence.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        high_dispersion=high_disp,
    )


# ---------------------------------------------------------------------------
# Piecewise Linear Multiplier
# ---------------------------------------------------------------------------

def compute_piecewise_linear_multiplier(score: Decimal) -> Decimal:
    """
    Stetige, asymmetrische Multiplier-Funktion (keine Bucket-Spruenge).

    Score 0-40:   1.50 -> 1.00 (Fear: aggressiver akkumulieren)
    Score 40-60:  1.00 (neutrale Flat-Zone)
    Score 60-100: 1.00 -> 0.85 (Greed: konservativer)
    """
    score = _clamp(score)

    if score < V3_NEUTRAL_BAND_LO:
        # Linear: FLOOR (1.50) bei Score=0 -> 1.00 bei Score=40
        return _linear_interpolate(
            score,
            Decimal("0"), V3_NEUTRAL_BAND_LO,
            V3_MULTIPLIER_FLOOR, Decimal("1"),
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    if score > V3_NEUTRAL_BAND_HI:
        # Linear: 1.00 bei Score=60 -> CEILING (0.85) bei Score=100
        return _linear_interpolate(
            score,
            V3_NEUTRAL_BAND_HI, Decimal("100"),
            Decimal("1"), V3_MULTIPLIER_CEILING,
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Neutrale Zone
    return Decimal("1.000")


# ---------------------------------------------------------------------------
# Volatility-Scaling
# ---------------------------------------------------------------------------

def compute_volatility_scaling(
    daily_returns: Optional[List[Decimal]],
    short_window: int = 20,
    long_window: int = 120,
) -> Optional[VolatilityScaling]:
    """
    Volatilitaets-Regime als orthogonaler Positions-Skalierungsfaktor.

    Vergleicht 20d realisierte Vol mit 120d Durchschnitt.
    HIGH Vol -> Multiplier-Range komprimieren (vorsichtiger).
    LOW Vol -> Multiplier-Range leicht erweitern (opportunistischer).
    """
    if daily_returns is None or len(daily_returns) < long_window:
        return None

    def _std_decimal(values: List[Decimal]) -> Decimal:
        n = Decimal(str(len(values)))
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return variance.sqrt() if variance > 0 else Decimal("0")

    returns_short = daily_returns[-short_window:]
    returns_long = daily_returns[-long_window:]

    # Annualisierte Volatilitaet: std * sqrt(365)
    sqrt_365 = Decimal(str(math.sqrt(365)))
    realized_vol_20d = _std_decimal(returns_short) * sqrt_365
    avg_vol_120d = _std_decimal(returns_long) * sqrt_365

    if avg_vol_120d == 0:
        return None

    vol_ratio = realized_vol_20d / avg_vol_120d

    if vol_ratio > V3_VOL_HIGH_THRESHOLD:
        regime = "HIGH"
        scaling_factor = V3_VOL_HIGH_COMPRESSION
    elif vol_ratio < V3_VOL_LOW_THRESHOLD:
        regime = "LOW"
        scaling_factor = V3_VOL_LOW_EXPANSION
    else:
        regime = "NORMAL"
        scaling_factor = Decimal("1.0")

    return VolatilityScaling(
        realized_vol_20d=realized_vol_20d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        avg_vol_120d=avg_vol_120d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        vol_ratio=vol_ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        regime=regime,
        scaling_factor=scaling_factor,
    )


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

def get_recommendation_v3(
    score: Decimal,
    pillar_scores: List[Decimal],
    daily_returns: Optional[List[Decimal]] = None,
) -> SentimentRecommendationV3:
    """
    Berechnet den finalen Multiplier durch Komposition:
    1. Piecewise Linear Multiplier (aus Score)
    2. Dispersion-Skalierung (Pillar-Uebereinstimmung)
    3. Volatility-Skalierung (Marktregime)

    final = 1.0 + (raw - 1.0) * confidence * vol_factor
    """
    raw_multiplier = compute_piecewise_linear_multiplier(score)
    dispersion = compute_pillar_dispersion(pillar_scores)
    vol_scaling = compute_volatility_scaling(daily_returns)

    # Dispersion: Skaliert Deviation von 1.0
    deviation = raw_multiplier - Decimal("1")
    adjusted_deviation = deviation * dispersion.confidence_factor

    # Volatility: Skaliert Deviation weiter
    if vol_scaling is not None:
        adjusted_deviation = adjusted_deviation * vol_scaling.scaling_factor

    final_multiplier = (Decimal("1") + adjusted_deviation).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    label = classify_score(score)
    action = _V3_ACTION_MAP.get(label, "Standard-Parameter")

    return SentimentRecommendationV3(
        action=action,
        buy_size_multiplier=final_multiplier,
        raw_multiplier=raw_multiplier,
        dispersion=dispersion,
        volatility=vol_scaling,
    )


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def compute_sentiment_v3(
    fng_value: Optional[Decimal],
    taker_ratio_7d: Optional[Decimal],
    dist_50dma_pct: Optional[Decimal],
    vol_ratio: Optional[Decimal],
    price_change_pct: Optional[Decimal],
    history_fng: Optional[List[Decimal]] = None,
    history_taker: Optional[List[Decimal]] = None,
    history_dma: Optional[List[Decimal]] = None,
    history_vol: Optional[List[Decimal]] = None,
    sma50: Optional[Decimal] = None,
    sma200: Optional[Decimal] = None,
    daily_returns: Optional[List[Decimal]] = None,
    funding_rate: Optional[Decimal] = None,
) -> SentimentResultV3:
    """
    Sentiment Scoring: Correlation-gewichtete Pillars + Dispersion + Volatility.

    - Pillar-Gewichte: DMA 42%, F&G 28%, Taker 18%, Volume 12%
    - Dispersion-Konfidenz statt Concordance-Bonus
    - Piecewise-Linear Multiplier statt Bucket-Tabelle
    - Volatility-Scaling als orthogonaler Faktor
    """
    pillar_keys = []  # Tracking: welche Pillar-Keys sind aktiv
    pillars = []
    active_count = 0

    # --- Pillar 1: F&G (Percentile) ---
    if fng_value is not None and history_fng and len(history_fng) >= 30:
        score = rolling_percentile(fng_value, history_fng)
        active_count += 1
        quality = "live"
        pillar_keys.append("fng")
    elif fng_value is not None:
        score = _clamp(fng_value)
        active_count += 1
        quality = "live"
        pillar_keys.append("fng")
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Fear & Greed",
        score=score,
        raw_value=fng_value,
        source="alternative.me",
        quality=quality,
    ))

    # --- Pillar 2: Funding Rate (feste Schwellwerte) ---
    funding_pillar = score_funding_rate(funding_rate)
    if funding_pillar.quality != "unavailable":
        active_count += 1
        pillar_keys.append("funding")
    pillars.append(funding_pillar)

    # --- Pillar 3: Taker Ratio (Percentile) ---
    if taker_ratio_7d is not None and history_taker and len(history_taker) >= 30:
        score = rolling_percentile(taker_ratio_7d, history_taker)
        active_count += 1
        quality = "live"
        pillar_keys.append("taker")
    elif taker_ratio_7d is not None:
        score = Decimal("50")
        active_count += 1
        quality = "live"
        pillar_keys.append("taker")
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Taker Buy/Sell Ratio",
        score=score,
        raw_value=taker_ratio_7d,
        source="binance",
        quality=quality,
    ))

    # --- Pillar 4: DMA-Composite (Percentile + Regime) ---
    if dist_50dma_pct is not None and history_dma and len(history_dma) >= 30:
        base_pctl = rolling_percentile(dist_50dma_pct, history_dma)
        bullish = sma50 > sma200 if sma50 and sma200 and sma200 > 0 else True
        if not bullish:
            score = (base_pctl * Decimal("0.8")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        else:
            score = base_pctl
        active_count += 1
        quality = "live"
        pillar_keys.append("dma")
    elif dist_50dma_pct is not None:
        score = Decimal("50")
        active_count += 1
        quality = "live"
        pillar_keys.append("dma")
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Trend-Deviation (DMA)",
        score=_clamp(score),
        raw_value=dist_50dma_pct,
        source="binance",
        quality=quality,
    ))

    # --- Pillar 5: Volume-Momentum (Percentile + Richtung) ---
    if vol_ratio is not None and history_vol and len(history_vol) >= 30:
        base_pctl = rolling_percentile(vol_ratio, history_vol)
        if price_change_pct is not None and price_change_pct < 0:
            score = (Decimal("100") - base_pctl).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        else:
            score = base_pctl
        active_count += 1
        quality = "live"
        pillar_keys.append("volume")
    elif vol_ratio is not None:
        score = Decimal("50")
        active_count += 1
        quality = "live"
        pillar_keys.append("volume")
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Volume-Momentum",
        score=_clamp(score),
        raw_value=vol_ratio,
        source="binance",
        quality=quality,
    ))

    # --- Gewichteter Durchschnitt (Correlation-Based) ---
    active = [p for p in pillars if p.quality != "unavailable"]
    if not active:
        raw_score = Decimal("50")
    else:
        # Gewichte fuer aktive Pillars holen und renormalisieren
        raw_weights = [V3_PILLAR_WEIGHTS[k] for k in pillar_keys]
        weight_sum = sum(raw_weights)
        if weight_sum > 0:
            normalized = [w / weight_sum for w in raw_weights]
        else:
            normalized = [Decimal("1") / Decimal(str(len(active)))] * len(active)
        raw_score = sum(p.score * w for p, w in zip(active, normalized))

    raw_score = _clamp(raw_score).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    # --- Recommendation (Dispersion + Volatility integriert) ---
    active_scores = [p.score for p in active]
    recommendation = get_recommendation_v3(raw_score, active_scores, daily_returns)

    label = classify_score(raw_score)
    color = LABEL_COLORS[label]

    return SentimentResultV3(
        composite_score=raw_score,
        composite_label=label,
        composite_color=color,
        recommendation=recommendation,
        pillars=pillars,
        active_pillars=active_count,
        total_pillars=len(pillars),
    )


# ---------------------------------------------------------------------------
# v1 Legacy: Fixed-Bracket Scoring (fuer Backtest-Vergleich)
# ---------------------------------------------------------------------------

@dataclass
class SentimentResult:
    """Sentiment-Ergebnis fuer v1/v2 (ohne Recommendation-Komposition)."""
    composite_score: Decimal
    composite_label: SentimentLabel
    composite_color: str
    concordance_applied: bool
    pillars: List[PillarScore]


def score_fear_and_greed(fng_value: Optional[Decimal]) -> PillarScore:
    """v1: F&G Index direkt als Score (0-100 Durchreichung)."""
    if fng_value is None:
        return PillarScore(
            name="Fear & Greed", score=Decimal("50"),
            quality="unavailable", source="alternative.me",
        )
    return PillarScore(
        name="Fear & Greed", score=_clamp(fng_value),
        raw_value=fng_value, source="alternative.me", quality="live",
    )


def score_taker_ratio(ratio: Optional[Decimal]) -> PillarScore:
    """v1: Taker Buy/Sell Ratio via feste Brackets (0.85-1.15 -> 0-100)."""
    if ratio is None:
        return PillarScore(
            name="Taker Buy/Sell Ratio", score=Decimal("50"),
            quality="unavailable", source="binance",
        )
    score = _linear_interpolate(
        ratio, Decimal("0.85"), Decimal("1.15"), Decimal("0"), Decimal("100"),
    )
    return PillarScore(
        name="Taker Buy/Sell Ratio", score=_clamp(score),
        raw_value=ratio, source="binance", quality="live",
    )


def score_dma_composite(
    price: Optional[Decimal],
    sma50: Optional[Decimal],
    sma200: Optional[Decimal],
) -> PillarScore:
    """v1: DMA-Composite via feste Brackets (-20% bis +20% -> 0-100)."""
    if price is None or sma50 is None or sma50 == 0:
        return PillarScore(
            name="Trend-Deviation (DMA)", score=Decimal("50"),
            quality="unavailable", source="binance",
        )
    dist_pct = ((price - sma50) / sma50) * Decimal("100")
    score = _linear_interpolate(
        dist_pct, Decimal("-20"), Decimal("20"), Decimal("0"), Decimal("100"),
    )
    # Regime-Filter: bearish (SMA50 < SMA200) -> daempfen
    if sma200 and sma200 > 0 and sma50 < sma200:
        score = score * Decimal("0.8")
    return PillarScore(
        name="Trend-Deviation (DMA)", score=_clamp(score),
        raw_value=dist_pct, source="binance", quality="live",
    )


def score_volume_momentum(
    vol_ratio: Optional[Decimal],
    price_change_pct: Optional[Decimal],
) -> PillarScore:
    """v1: Volume-Momentum via feste Brackets (0.5-2.0x -> 0-100, richtungsangepasst)."""
    if vol_ratio is None:
        return PillarScore(
            name="Volume-Momentum", score=Decimal("50"),
            quality="unavailable", source="binance",
        )
    score = _linear_interpolate(
        vol_ratio, Decimal("0.5"), Decimal("2.0"), Decimal("0"), Decimal("100"),
    )
    # Hohes Volumen bei fallendem Preis = Fear -> invertieren
    if price_change_pct is not None and price_change_pct < 0:
        score = Decimal("100") - score
    return PillarScore(
        name="Volume-Momentum", score=_clamp(score),
        raw_value=vol_ratio, source="binance", quality="live",
    )


def compute_sentiment(pillars: List[PillarScore]) -> SentimentResult:
    """v1: Gleichgewichteter Durchschnitt aller aktiven Pillars + Concordance."""
    active = [p for p in pillars if p.quality != "unavailable"]
    if not active:
        raw_score = Decimal("50")
    else:
        raw_score = sum(p.score for p in active) / Decimal(str(len(active)))
    raw_score = _clamp(raw_score).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    # Concordance: Alle aktiven Pillars zeigen in dieselbe Richtung
    concordance = False
    if len(active) >= 3:
        all_fear = all(p.score < Decimal("40") for p in active)
        all_greed = all(p.score > Decimal("60") for p in active)
        concordance = all_fear or all_greed

    label = classify_score(raw_score)
    color = LABEL_COLORS[label]

    return SentimentResult(
        composite_score=raw_score,
        composite_label=label,
        composite_color=color,
        concordance_applied=concordance,
        pillars=pillars,
    )


# ---------------------------------------------------------------------------
# v2 Legacy: Rolling-Percentile + Velocity + Regime-Switch (fuer Backtest)
# ---------------------------------------------------------------------------

def compute_sentiment_v2(
    fng_value: Optional[Decimal],
    taker_ratio_7d: Optional[Decimal],
    dist_50dma_pct: Optional[Decimal],
    vol_ratio: Optional[Decimal],
    price_change_pct: Optional[Decimal],
    history_fng: Optional[List[Decimal]] = None,
    history_taker: Optional[List[Decimal]] = None,
    history_dma: Optional[List[Decimal]] = None,
    history_vol: Optional[List[Decimal]] = None,
    sma50: Optional[Decimal] = None,
    sma200: Optional[Decimal] = None,
) -> SentimentResult:
    """v2: Rolling-Percentile Scoring, gleichgewichtet, mit Concordance."""
    pillars = []
    active_count = 0

    # F&G (Percentile)
    if fng_value is not None and history_fng and len(history_fng) >= 30:
        score = rolling_percentile(fng_value, history_fng)
        quality = "live"
        active_count += 1
    elif fng_value is not None:
        score = _clamp(fng_value)
        quality = "live"
        active_count += 1
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Fear & Greed", score=score, raw_value=fng_value,
        source="alternative.me", quality=quality,
    ))

    # Funding (nicht verfuegbar in v2)
    pillars.append(PillarScore(
        name="Funding Rate", score=Decimal("50"),
        raw_value=None, source="okx", quality="unavailable",
    ))

    # Taker (Percentile)
    if taker_ratio_7d is not None and history_taker and len(history_taker) >= 30:
        score = rolling_percentile(taker_ratio_7d, history_taker)
        quality = "live"
        active_count += 1
    elif taker_ratio_7d is not None:
        score = Decimal("50")
        quality = "live"
        active_count += 1
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Taker Buy/Sell Ratio", score=score, raw_value=taker_ratio_7d,
        source="binance", quality=quality,
    ))

    # DMA (Percentile + Regime)
    if dist_50dma_pct is not None and history_dma and len(history_dma) >= 30:
        base_pctl = rolling_percentile(dist_50dma_pct, history_dma)
        bullish = sma50 > sma200 if sma50 and sma200 and sma200 > 0 else True
        score = (base_pctl * Decimal("0.8")).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        ) if not bullish else base_pctl
        quality = "live"
        active_count += 1
    elif dist_50dma_pct is not None:
        score = Decimal("50")
        quality = "live"
        active_count += 1
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Trend-Deviation (DMA)", score=_clamp(score),
        raw_value=dist_50dma_pct, source="binance", quality=quality,
    ))

    # Volume (Percentile + Richtung)
    if vol_ratio is not None and history_vol and len(history_vol) >= 30:
        base_pctl = rolling_percentile(vol_ratio, history_vol)
        score = (Decimal("100") - base_pctl).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        ) if price_change_pct is not None and price_change_pct < 0 else base_pctl
        quality = "live"
        active_count += 1
    elif vol_ratio is not None:
        score = Decimal("50")
        quality = "live"
        active_count += 1
    else:
        score = Decimal("50")
        quality = "unavailable"
    pillars.append(PillarScore(
        name="Volume-Momentum", score=_clamp(score),
        raw_value=vol_ratio, source="binance", quality=quality,
    ))

    # Gleichgewichteter Durchschnitt (v2 hat keine korrelationsbasierten Gewichte)
    active = [p for p in pillars if p.quality != "unavailable"]
    if not active:
        raw_score = Decimal("50")
    else:
        raw_score = sum(p.score for p in active) / Decimal(str(len(active)))
    raw_score = _clamp(raw_score).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    # Concordance
    concordance = False
    if len(active) >= 3:
        all_fear = all(p.score < Decimal("40") for p in active)
        all_greed = all(p.score > Decimal("60") for p in active)
        concordance = all_fear or all_greed

    label = classify_score(raw_score)
    color = LABEL_COLORS[label]

    return SentimentResult(
        composite_score=raw_score,
        composite_label=label,
        composite_color=color,
        concordance_applied=concordance,
        pillars=pillars,
    )


# ---------------------------------------------------------------------------
# Kline-Indikatoren (extrahiert aus sentiment_data_service)
# ---------------------------------------------------------------------------

@dataclass
class KlineIndicators:
    """Technische Indikatoren berechnet aus OHLCV-Daten."""
    current_price: Decimal
    sma50: Optional[Decimal]
    sma200: Optional[Decimal]
    dist_50dma_pct: Optional[Decimal]
    vol_ratio: Optional[Decimal]
    price_change_pct: Optional[Decimal]
    taker_ratio_7d: Optional[Decimal]


def compute_kline_indicators(
    closes: List[Decimal],
    volumes: List[Decimal],
    taker_buy_vols: List[Decimal],
) -> Optional[KlineIndicators]:
    """
    Berechnet technische Indikatoren aus OHLCV-Daten (pure, kein I/O).

    Benoetigt mindestens 50 Closes fuer SMA50.
    SMA200 nur verfuegbar bei >= 200 Closes.

    Args:
        closes: Close-Preise (chronologisch)
        volumes: Volumina (chronologisch)
        taker_buy_vols: Taker-Buy-Volumina (chronologisch)

    Returns:
        KlineIndicators oder None bei unzureichenden Daten
    """
    if len(closes) < 50:
        return None

    current_price = closes[-1]

    # SMAs
    sma50 = sum(closes[-50:]) / Decimal("50")
    sma200 = sum(closes[-200:]) / Decimal("200") if len(closes) >= 200 else None

    # Distance to 50-DMA
    dist_50dma_pct = (
        ((current_price - sma50) / sma50) * Decimal("100") if sma50 > 0 else None
    )

    # Volume Ratio (heute vs 20-Tage-Durchschnitt)
    vol_ratio = None
    if len(volumes) >= 21:
        vol_20d = sum(volumes[-21:-1]) / Decimal("20")
        if vol_20d > 0:
            vol_ratio = volumes[-1] / vol_20d

    # Price Change (heute vs gestern)
    price_change_pct = None
    if len(closes) >= 2 and closes[-2] > 0:
        price_change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * Decimal("100")

    # Taker Ratio (7d Durchschnitt)
    taker_ratio_7d = _compute_taker_ratio_7d(
        volumes[-7:] if len(volumes) >= 7 else volumes,
        taker_buy_vols[-7:] if len(taker_buy_vols) >= 7 else taker_buy_vols,
    )

    return KlineIndicators(
        current_price=current_price,
        sma50=sma50,
        sma200=sma200,
        dist_50dma_pct=dist_50dma_pct,
        vol_ratio=vol_ratio,
        price_change_pct=price_change_pct,
        taker_ratio_7d=taker_ratio_7d,
    )


def _compute_taker_ratio_7d(
    volumes: List[Decimal],
    taker_buy_vols: List[Decimal],
) -> Optional[Decimal]:
    """Berechnet 7-Tage-Durchschnitt des Taker Buy/Sell Ratio."""
    ratios = []
    for i in range(len(volumes)):
        sell_vol = volumes[i] - taker_buy_vols[i]
        if sell_vol > 0:
            ratios.append(taker_buy_vols[i] / sell_vol)
    if len(ratios) < 3:
        return None
    return sum(ratios) / Decimal(str(len(ratios)))


@dataclass
class HistoricalPillarScores:
    """Rolling-Window Pillar-Scores fuer Percentile-Initialisierung."""
    dma_distances: List[Decimal]
    volume_ratios: List[Decimal]
    taker_ratios: List[Decimal]
    daily_returns: List[Decimal]


def compute_historical_pillar_scores(
    closes: List[Decimal],
    volumes: List[Decimal],
    taker_buy_vols: List[Decimal],
    start_idx: int,
) -> HistoricalPillarScores:
    """
    Berechnet historische Pillar-Scores ueber einen Kerzen-Range (pure, kein I/O).

    Fuer Percentile-Initialisierung: Berechnet DMA-Distance, Volume-Ratio,
    Taker-Ratio und Daily-Returns ab start_idx.

    Args:
        closes: Close-Preise (chronologisch)
        volumes: Volumina (chronologisch)
        taker_buy_vols: Taker-Buy-Volumina (chronologisch)
        start_idx: Start-Index (typisch: max(200, len-90))

    Returns:
        HistoricalPillarScores mit 4 Listen
    """
    dma_distances: List[Decimal] = []
    volume_ratios: List[Decimal] = []
    taker_ratios: List[Decimal] = []
    daily_returns: List[Decimal] = []

    for i in range(start_idx, len(closes)):
        # DMA Distance
        if i >= 50:
            sma50 = sum(closes[i - 49 : i + 1]) / Decimal("50")
            if sma50 > 0:
                dma_distances.append(
                    ((closes[i] - sma50) / sma50) * Decimal("100")
                )

        # Volume Ratio
        if i >= 21:
            vol_20d = sum(volumes[i - 20 : i]) / Decimal("20")
            if vol_20d > 0:
                volume_ratios.append(volumes[i] / vol_20d)

        # Taker Ratio
        window_vols = volumes[max(0, i - 6) : i + 1]
        window_taker = taker_buy_vols[max(0, i - 6) : i + 1]
        tr = _compute_taker_ratio_7d(window_vols, window_taker)
        if tr is not None:
            taker_ratios.append(tr)

        # Daily Returns
        if i >= 1 and closes[i - 1] > 0:
            daily_returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

    return HistoricalPillarScores(
        dma_distances=dma_distances,
        volume_ratios=volume_ratios,
        taker_ratios=taker_ratios,
        daily_returns=daily_returns,
    )


def compute_daily_return(
    close_today: Decimal,
    close_yesterday: Decimal,
) -> Optional[Decimal]:
    """Berechnet taegliche Rendite. None wenn close_yesterday <= 0."""
    if close_yesterday <= 0:
        return None
    return (close_today - close_yesterday) / close_yesterday


# ---------------------------------------------------------------------------
# v1 Legacy: Score Velocity / Regime Switch
# ---------------------------------------------------------------------------

def compute_score_velocity(
    score_history: List[Decimal],
    lookback: int = 7,
) -> Optional[Decimal]:
    """v2: Score-Aenderungsgeschwindigkeit ueber N Tage."""
    if len(score_history) < lookback + 1:
        return None
    current = score_history[-1]
    past = score_history[-(lookback + 1)]
    return (current - past).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def get_regime_switch_multiplier(
    score: Decimal,
    velocity: Optional[Decimal],
) -> Decimal:
    """
    v2: Regime-Switch DCA-Multiplikator.

    Extremwerte: Contrarian (Akkumulation bei Fear, Reduktion bei Greed).
    Mittelfeld: Momentum-getrieben (Velocity bestimmt Richtung).
    """
    if score <= Decimal("15"):
        return Decimal("1.30")
    if score <= Decimal("35"):
        return Decimal("1.15")
    if score >= Decimal("85"):
        return Decimal("0.70")
    if score >= Decimal("65"):
        return Decimal("0.85")
    # Neutrale Zone: Velocity als Momentum-Signal
    if velocity is not None and velocity > Decimal("5"):
        return Decimal("0.90")   # Score steigt schnell -> vorsichtiger
    if velocity is not None and velocity < Decimal("-5"):
        return Decimal("1.10")   # Score faellt schnell -> akkumulieren
    return Decimal("1.00")
