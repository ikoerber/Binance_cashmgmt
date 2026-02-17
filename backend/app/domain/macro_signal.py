"""
Makro-Signal Domain-Logik - Pure Scoring-Funktionen (kein I/O)

Berechnet ein konfigurierbares Richtungssignal (1m/5m/15m) fuer BTC/EUR
basierend auf 4 Makro-Faktoren: BTC/USD Momentum, EUR/USD Richtung,
DXY Richtung, US02Y-DE02Y Zinsspread.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List


# ─── Basis-Schwellenwerte (kalibriert fuer 15 Min) ───

BTC_STRONG_THRESHOLD = Decimal("1.0")
BTC_MILD_THRESHOLD = Decimal("0.3")

EUR_STRONG_THRESHOLD = Decimal("0.5")
EUR_MILD_THRESHOLD = Decimal("0.2")

DXY_STRONG_THRESHOLD = Decimal("0.3")
DXY_MILD_THRESHOLD = Decimal("0.1")

SPREAD_STRONG_THRESHOLD = Decimal("10")  # bps
SPREAD_MILD_THRESHOLD = Decimal("5")  # bps

# Gueltige Intervalle
VALID_INTERVALS = {1, 5, 15}

# Skalierungsfaktoren relativ zu 15m (sqrt(time) Volatilitaets-Approximation)
_INTERVAL_SCALE = {
    1: Decimal("0.258"),   # sqrt(1/15)
    5: Decimal("0.577"),   # sqrt(5/15)
    15: Decimal("1.0"),    # Baseline
}


# ─── Intervall-skalierte Schwellenwerte ───

@dataclass
class IntervalThresholds:
    """Schwellenwerte skaliert nach Intervall-Laenge."""
    btc_strong: Decimal
    btc_mild: Decimal
    eur_strong: Decimal
    eur_mild: Decimal
    dxy_strong: Decimal
    dxy_mild: Decimal
    spread_strong: Decimal
    spread_mild: Decimal
    interval_minutes: int


def get_thresholds(interval_minutes: int = 15) -> IntervalThresholds:
    """Liefert Scoring-Schwellenwerte skaliert fuer das gegebene Intervall."""
    if interval_minutes not in _INTERVAL_SCALE:
        interval_minutes = 15
    scale = _INTERVAL_SCALE[interval_minutes]
    return IntervalThresholds(
        btc_strong=BTC_STRONG_THRESHOLD * scale,
        btc_mild=BTC_MILD_THRESHOLD * scale,
        eur_strong=EUR_STRONG_THRESHOLD * scale,
        eur_mild=EUR_MILD_THRESHOLD * scale,
        dxy_strong=DXY_STRONG_THRESHOLD * scale,
        dxy_mild=DXY_MILD_THRESHOLD * scale,
        spread_strong=SPREAD_STRONG_THRESHOLD * scale,
        spread_mild=SPREAD_MILD_THRESHOLD * scale,
        interval_minutes=interval_minutes,
    )


# ─── Empfehlungs-Mapping ───

RECOMMENDATIONS = {
    2: "STARK LONG",
    1: "LONG",
    0: "NEUTRAL",
    -1: "SHORT",
    -2: "STARK SHORT",
}

RECOMMENDATION_COLORS = {
    2: "#16a34a",   # Gruen
    1: "#22c55e",   # Hellgruen
    0: "#64748b",   # Slate
    -1: "#f97316",  # Orange
    -2: "#dc2626",  # Rot
}


# ─── Dataclasses ───

@dataclass
class MacroIndicator:
    """Ein einzelner Makro-Indikator mit aktuellem und historischem Wert."""
    name: str
    current: Optional[Decimal]
    previous_15m: Optional[Decimal]
    change_pct: Optional[Decimal]  # Prozentuale Aenderung
    timestamp: Optional[datetime]
    source: str  # "binance", "twelvedata", "calculated"
    quality: str  # "live", "cached", "stale", "unavailable"


@dataclass
class SignalScore:
    """Bewertung eines einzelnen Faktors."""
    factor: str
    score: int  # -2 bis +2
    reason: str
    change_value: Optional[Decimal] = None  # Die Aenderung die zum Score fuehrte
    direction: str = "direct"  # "direct" oder "inverse" - Einflussrichtung auf BTC/EUR


@dataclass
class MacroSignalResult:
    """Vollstaendiges Signal-Ergebnis."""
    indicators: dict  # name -> MacroIndicator als dict
    scores: List[SignalScore]
    composite_score: int  # -2 bis +2 (gemapped)
    composite_raw: int  # Rohsumme -8 bis +8
    recommendation: str  # z.B. "STARK LONG"
    recommendation_color: str
    timestamp: datetime
    next_update: Optional[datetime]
    active_factors: int  # Anzahl aktiver Faktoren (nicht N/A)
    total_factors: int  # Gesamtanzahl Faktoren
    interval_minutes: int = 15  # Aktuelles Signal-Intervall


# ─── Scoring-Funktionen ───

def _score_momentum(change_pct: Decimal, strong: Decimal, mild: Decimal) -> int:
    """Generische Momentum-Bewertung: positiv = bullish."""
    if change_pct > strong:
        return 2
    elif change_pct > mild:
        return 1
    elif change_pct >= -mild:
        return 0
    elif change_pct >= -strong:
        return -1
    else:
        return -2


def _score_inverse(change_pct: Decimal, strong: Decimal, mild: Decimal) -> int:
    """Inverse Momentum-Bewertung: positiv = bearish (z.B. EUR staerker = BTC/EUR bearish)."""
    if change_pct > strong:
        return -2
    elif change_pct > mild:
        return -1
    elif change_pct >= -mild:
        return 0
    elif change_pct >= -strong:
        return 1
    else:
        return 2


def score_btc_momentum(current: Decimal, previous: Decimal, thresholds: Optional[IntervalThresholds] = None) -> SignalScore:
    """
    BTC/USD Momentum: aktuell vs. vorheriger Wert.
    Steigend = bullish fuer BTC/EUR (direkt).
    """
    if previous == 0:
        return SignalScore(factor="BTC/USD Momentum", score=0, reason="Keine Vergleichsdaten", direction="direct")

    t = thresholds or get_thresholds(15)
    change_pct = ((current - previous) / previous) * Decimal("100")
    score = _score_momentum(change_pct, t.btc_strong, t.btc_mild)

    reasons = {
        2: "Starker Aufwaertstrend",
        1: "Leichter Aufwaertstrend",
        0: "Seitwaerts",
        -1: "Leichter Abwaertstrend",
        -2: "Starker Abwaertstrend",
    }
    reason = f"{reasons[score]} ({change_pct:+.2f}%)"
    return SignalScore(factor="BTC/USD Momentum", score=score, reason=reason, change_value=change_pct, direction="direct")


def score_eur_usd(current: Decimal, previous: Decimal, thresholds: Optional[IntervalThresholds] = None) -> SignalScore:
    """
    EUR/USD Richtung (invers).
    EUR steigt = BTC/EUR faellt (weniger EUR pro BTC) = bearish.
    EUR faellt = BTC/EUR steigt = bullish.
    """
    if previous == 0:
        return SignalScore(factor="EUR/USD Richtung", score=0, reason="Keine Vergleichsdaten", direction="inverse")

    t = thresholds or get_thresholds(15)
    change_pct = ((current - previous) / previous) * Decimal("100")
    score = _score_inverse(change_pct, t.eur_strong, t.eur_mild)

    if score > 0:
        reason = f"EUR schwaecher ({change_pct:+.3f}%) - bullish BTC/EUR"
    elif score < 0:
        reason = f"EUR staerker ({change_pct:+.3f}%) - bearish BTC/EUR"
    else:
        reason = f"EUR stabil ({change_pct:+.3f}%)"
    return SignalScore(factor="EUR/USD Richtung", score=score, reason=reason, change_value=change_pct, direction="inverse")


def score_dxy(current: Decimal, previous: Decimal, thresholds: Optional[IntervalThresholds] = None) -> SignalScore:
    """
    DXY Richtung (invers).
    DXY steigt = USD staerker = Risk-Off = bearish fuer BTC.
    DXY faellt = USD schwaecher = bullish fuer BTC.
    """
    if previous == 0:
        return SignalScore(factor="DXY Richtung", score=0, reason="Keine Vergleichsdaten", direction="inverse")

    t = thresholds or get_thresholds(15)
    change_pct = ((current - previous) / previous) * Decimal("100")
    score = _score_inverse(change_pct, t.dxy_strong, t.dxy_mild)

    if score > 0:
        reason = f"USD schwaecher ({change_pct:+.2f}%) - bullish BTC"
    elif score < 0:
        reason = f"USD staerker ({change_pct:+.2f}%) - bearish BTC"
    else:
        reason = f"USD stabil ({change_pct:+.2f}%)"
    return SignalScore(factor="DXY Richtung", score=score, reason=reason, change_value=change_pct, direction="inverse")


def score_yield_spread(current_spread: Decimal, previous_spread: Decimal, thresholds: Optional[IntervalThresholds] = None) -> SignalScore:
    """
    US02Y-DE02Y Zinsspread Richtung (in Basispunkten, invers).
    Spread weitet sich = USD attraktiver = Kapitalfluss in USD = bearish BTC.
    Spread engt sich ein = bullish BTC.
    """
    t = thresholds or get_thresholds(15)
    change_bps = (current_spread - previous_spread) * Decimal("100")  # % -> bps
    score = _score_inverse(change_bps, t.spread_strong, t.spread_mild)

    if score > 0:
        reason = f"Spread engt sich ein ({change_bps:+.1f} bps) - bullish BTC"
    elif score < 0:
        reason = f"Spread weitet sich ({change_bps:+.1f} bps) - bearish BTC"
    else:
        reason = f"Spread stabil ({change_bps:+.1f} bps)"
    return SignalScore(factor="Zinsspread US-DE", score=score, reason=reason, change_value=change_bps, direction="inverse")


def _map_composite_to_recommendation(raw_score: int) -> int:
    """Mapped Rohscore (-8..+8) auf Empfehlung (-2..+2)."""
    if raw_score >= 4:
        return 2
    elif raw_score >= 2:
        return 1
    elif raw_score >= -1:
        return 0
    elif raw_score >= -3:
        return -1
    else:
        return -2


def compute_macro_signal(indicators: dict, interval_minutes: int = 15) -> MacroSignalResult:
    """
    Hauptfunktion: Berechnet das Makro-Signal aus allen verfuegbaren Indikatoren.

    Args:
        indicators: Dict mit MacroIndicator-Objekten, Keys:
            "btc_usd", "eur_usd", "dxy", "us02y", "de02y", "spread"
        interval_minutes: Signal-Intervall (1, 5, oder 15 Minuten)

    Returns:
        MacroSignalResult mit Scores, Empfehlung und Metadaten.
    """
    from app.domain.models import utcnow

    thresholds = get_thresholds(interval_minutes)
    scores = []
    active_factors = 0

    # Faktor 1: BTC/USD Momentum
    btc = indicators.get("btc_usd")
    if btc and btc.current is not None and btc.previous_15m is not None:
        scores.append(score_btc_momentum(btc.current, btc.previous_15m, thresholds))
        active_factors += 1
    else:
        scores.append(SignalScore(factor="BTC/USD Momentum", score=0, reason="Daten nicht verfuegbar", direction="direct"))

    # Faktor 2: EUR/USD Richtung
    eur = indicators.get("eur_usd")
    if eur and eur.current is not None and eur.previous_15m is not None:
        scores.append(score_eur_usd(eur.current, eur.previous_15m, thresholds))
        active_factors += 1
    else:
        scores.append(SignalScore(factor="EUR/USD Richtung", score=0, reason="Daten nicht verfuegbar", direction="inverse"))

    # Faktor 3: DXY Richtung
    dxy = indicators.get("dxy")
    if dxy and dxy.current is not None and dxy.previous_15m is not None:
        scores.append(score_dxy(dxy.current, dxy.previous_15m, thresholds))
        active_factors += 1
    else:
        scores.append(SignalScore(factor="DXY Richtung", score=0, reason="Daten nicht verfuegbar", direction="inverse"))

    # Faktor 4: Zinsspread
    spread = indicators.get("spread")
    if spread and spread.current is not None and spread.previous_15m is not None:
        scores.append(score_yield_spread(spread.current, spread.previous_15m, thresholds))
        active_factors += 1
    else:
        scores.append(SignalScore(factor="Zinsspread US-DE", score=0, reason="Daten nicht verfuegbar", direction="inverse"))

    # Komposit berechnen
    raw_score = sum(s.score for s in scores)
    mapped = _map_composite_to_recommendation(raw_score)

    now = utcnow()

    # Naechstes Update berechnen (basierend auf konfiguriertem Intervall)
    interval = thresholds.interval_minutes
    minute = now.minute
    next_boundary = ((minute // interval) + 1) * interval
    next_update = now.replace(second=0, microsecond=0)
    if next_boundary >= 60:
        from datetime import timedelta
        overflow_minutes = next_boundary - 60
        next_update = next_update.replace(minute=0) + timedelta(hours=1, minutes=overflow_minutes)
    else:
        next_update = next_update.replace(minute=next_boundary)

    # Indikatoren als serialisierbare Dicts
    indicator_dicts = {}
    for key, ind in indicators.items():
        indicator_dicts[key] = {
            "name": ind.name,
            "current": float(ind.current) if ind.current is not None else None,
            "previous_15m": float(ind.previous_15m) if ind.previous_15m is not None else None,
            "change_pct": float(ind.change_pct) if ind.change_pct is not None else None,
            "source": ind.source,
            "quality": ind.quality,
        }

    return MacroSignalResult(
        indicators=indicator_dicts,
        scores=scores,
        composite_score=mapped,
        composite_raw=raw_score,
        recommendation=RECOMMENDATIONS[mapped],
        recommendation_color=RECOMMENDATION_COLORS[mapped],
        timestamp=now,
        next_update=next_update,
        active_factors=active_factors,
        total_factors=4,
        interval_minutes=interval,
    )


# ---------------------------------------------------------------------------
# Hilfs-Berechnungen (extrahiert aus macro_data_service)
# ---------------------------------------------------------------------------

def compute_change_pct(
    current: Optional[Decimal],
    previous: Optional[Decimal],
) -> Optional[Decimal]:
    """
    Berechnet prozentuale Veraenderung. None-safe.

    Returns:
        ((current - previous) / previous) * 100, oder None
    """
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / previous) * Decimal("100")


def compute_derived_eur_usd(
    btc_eur: Optional[Decimal],
    btc_usdt: Optional[Decimal],
    btc_eur_prev: Optional[Decimal],
    btc_usdt_prev: Optional[Decimal],
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Berechnet EUR/USD Fallback-Kurs aus BTC-Cross-Rates.

    EUR/USD = BTC/EUR / BTC/USDT (Kreuzrate)

    Returns:
        (current_eur_usd, previous_eur_usd) — jeweils Optional[Decimal]
    """
    current = None
    previous = None
    if btc_eur is not None and btc_usdt is not None and btc_usdt > 0:
        current = btc_eur / btc_usdt
    if (
        btc_eur_prev is not None
        and btc_usdt_prev is not None
        and btc_usdt_prev > 0
    ):
        previous = btc_eur_prev / btc_usdt_prev
    return current, previous


def compute_yield_spread(
    rate_a: Optional[Decimal],
    rate_b: Optional[Decimal],
) -> Optional[Decimal]:
    """
    Berechnet Spread (rate_a - rate_b). None-safe.

    Typisch: US 2Y Yield - DE 2Y Yield.

    Returns:
        Spread als Decimal, oder None wenn ein Wert fehlt
    """
    if rate_a is None or rate_b is None:
        return None
    return rate_a - rate_b
