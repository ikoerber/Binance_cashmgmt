"""
Orderblock Domain Models – Enums und Dataclasses.

Alle Datentypen fuer die Orderblock Detection Engine.
Keine Logik, kein I/O.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


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


class ConfluenceLabel(Enum):
    """Sentiment-OB Confluence Stufe."""

    STRONG_CONTRARIAN = "STRONG_CONTRARIAN"  # Fear + Bullish OB oder Greed + Bearish OB
    MODERATE_CONTRARIAN = "MODERATE_CONTRARIAN"  # Moderate kontraere Konstellation
    NEUTRAL = "NEUTRAL"  # Keine klare Confluence
    ADVERSE = "ADVERSE"  # OB-Richtung aligned mit Sentiment-Extrem (unguenstig)


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
    sweep_lookback: int = 10  # Kerzen vor OB-Formation fuer Liquidity Sweep Erkennung
    sweep_conviction_boost: Decimal = Decimal("10")  # Additive Punkte bei Sweep


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
class SentimentConfluence:
    """Ergebnis der Sentiment-OB Cross-Referenz Berechnung."""

    confluence_score: Decimal  # conviction × multiplier, capped bei 100
    confluence_label: ConfluenceLabel
    sentiment_at_detection: Decimal  # Sentiment-Snapshot zum Analyse-Zeitpunkt


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
    category: OBCategory = OBCategory.UNCLASSIFIED
    mitigated_at: Optional[datetime] = None
    invalidated_at: Optional[datetime] = None
    # Liquidity Sweep
    has_liquidity_sweep: bool = False
    liquidity_sweep_level: Optional[Decimal] = None
    # Sentiment Confluence
    sentiment_at_detection: Optional[Decimal] = None
    confluence_label: Optional[str] = None  # ConfluenceLabel.value oder None
    confluence_score: Optional[Decimal] = None
