"""
Orderblock Backtest Engine – Pure Domain-Logik (kein I/O).

Simuliert das historische Anlaufen von Orderblocks und berechnet
Performance-Metriken: Hit-Rate, Penetration Depth, Holding Duration,
Z-Score Cluster-Analyse.

Alle Berechnungen verwenden Decimal (niemals float).
Zeitkonsistent: Zonen gelten erst ab confirmed_at.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from app.domain.orderblock import (
    Candle,
    ConvictionLevel,
    OBConfig,
    OBDirection,
    OBState,
    Orderblock,
    detect_orderblocks,
    update_zone_states,
)

# ---------------------------------------------------------------------------
# Enums & Dataclasses
# ---------------------------------------------------------------------------


class TradeOutcome(Enum):
    """Ergebnis eines simulierten Zone-Approachs."""

    HIT = "HIT"
    MISS = "MISS"
    OPEN = "OPEN"
    EXPIRED = "EXPIRED"  # Triple Barrier: max_holding_candles ueberschritten


@dataclass
class BacktestTrade:
    """Ein simulierter Zone-Approach."""

    ob_id: str
    direction: OBDirection
    entry_edge: Decimal
    stop_edge: Decimal
    target: Decimal
    entry_price: Decimal
    entry_timestamp: datetime
    exit_timestamp: Optional[datetime]
    outcome: TradeOutcome
    penetration_depth_pct: Decimal  # 0-100, clamped
    holding_duration_candles: int
    min_adverse_price: Decimal
    conviction: ConvictionLevel
    volume_zscore: Decimal
    conviction_score: Decimal = Decimal("0")


@dataclass
class ConvictionBreakdown:
    """Hit-Rate pro Conviction Level (4-stufig)."""

    level: str  # "LOW" | "STANDARD" | "HIGH" | "INSTITUTIONAL"
    count: int
    hits: int
    misses: int
    expired: int
    hit_rate: Optional[Decimal]


@dataclass
class ZScoreCluster:
    """Hit-Rate pro Z-Score Bucket."""

    range_label: str
    range_low: Decimal
    range_high: Decimal
    count: int
    hits: int
    misses: int
    hit_rate: Optional[Decimal]


@dataclass
class BacktestMetrics:
    """Aggregierte Statistiken."""

    total_zones: int
    total_trades: int
    hits: int
    misses: int
    open_trades: int
    expired_trades: int
    hit_rate: Optional[Decimal]
    avg_penetration_depth_pct: Decimal
    median_penetration_depth_pct: Decimal
    avg_holding_duration_candles: Decimal
    median_holding_duration_candles: Decimal
    high_conviction_count: int
    high_conviction_hit_rate: Optional[Decimal]
    standard_conviction_hit_rate: Optional[Decimal]
    conviction_breakdown: List[ConvictionBreakdown]
    zscore_clusters: List[ZScoreCluster]
    high_conviction_zscore_count: int  # Spec 4.3: OBs mit Z-Score > Threshold
    high_conviction_zscore_hit_rate: Optional[Decimal]
    unmitigated_count: int
    mitigated_count: int
    invalid_count: int
    zones_per_month: Decimal


@dataclass
class BacktestResult:
    """Vollstaendiges Backtest-Ergebnis."""

    metrics: BacktestMetrics
    trades: List[BacktestTrade]
    zones: List[Orderblock]
    config: OBConfig
    timeframe: str
    symbol: str
    data_start: datetime
    data_end: datetime
    candle_count: int


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def simulate_zone_approach(
    ob: Orderblock,
    candles: List[Candle],
    config: OBConfig,
) -> Optional[BacktestTrade]:
    """
    Simuliert Entry/Stop/Target fuer eine einzelne Zone.

    Entry: Limit-Touch an entry_edge (ab confirmed_at + 1)
    Stop: Wick-Touch an stop_edge (konservativ)
    Target: target_rr * Zone-Weite ab Entry

    Bei gleichzeitigem Stop und Target in derselben Kerze: MISS (konservativ).
    Returns None wenn Zone nie beruehrt wird.
    """
    n = len(candles)
    start_idx = ob.confirmed_at_index + 1

    if start_idx >= n:
        return None

    # Target berechnen
    zone_width = ob.zone_top - ob.zone_bottom
    target_distance = config.target_rr * zone_width

    if ob.direction == OBDirection.BULLISH:
        target = ob.entry_edge + target_distance
    else:
        target = ob.entry_edge - target_distance

    entry_price = ob.entry_edge

    # Phase 1: Warten auf Entry
    entry_idx = None
    for i in range(start_idx, n):
        c = candles[i]
        if ob.direction == OBDirection.BULLISH:
            if c.low <= ob.entry_edge:
                entry_idx = i
                break
        else:
            if c.high >= ob.entry_edge:
                entry_idx = i
                break

    if entry_idx is None:
        return None  # Zone nie beruehrt

    # Phase 2: Nach Entry - Stop oder Target (ab naechster Kerze)
    min_adverse = entry_price  # Fuer Penetration Depth
    holding_candles = 0

    for i in range(entry_idx + 1, n):
        c = candles[i]
        holding_candles = i - entry_idx

        # --- Triple Barrier: Zeitlimit (Lopez de Prado) ---
        if config.max_holding_candles > 0 and holding_candles > config.max_holding_candles:
            return _make_trade(
                ob,
                entry_price,
                target,
                candles[entry_idx].timestamp,
                c.timestamp,
                TradeOutcome.EXPIRED,
                min_adverse,
                holding_candles,
                config,
            )

        # Adverse Price tracken
        if ob.direction == OBDirection.BULLISH:
            if c.low < min_adverse:
                min_adverse = c.low
        else:
            if c.high > min_adverse:
                min_adverse = c.high

        # Stop und Target pruefen
        stop_hit = False
        target_hit = False

        if ob.direction == OBDirection.BULLISH:
            stop_hit = c.low <= ob.stop_edge
            target_hit = c.high >= target
        else:
            stop_hit = c.high >= ob.stop_edge
            target_hit = c.low <= target

        # Gleiche Kerze: Stop gewinnt (konservativ)
        if stop_hit:
            return _make_trade(
                ob,
                entry_price,
                target,
                candles[entry_idx].timestamp,
                c.timestamp,
                TradeOutcome.MISS,
                min_adverse,
                holding_candles,
                config,
            )

        if target_hit:
            return _make_trade(
                ob,
                entry_price,
                target,
                candles[entry_idx].timestamp,
                c.timestamp,
                TradeOutcome.HIT,
                min_adverse,
                holding_candles,
                config,
            )

    # Ende der Daten: Trade noch offen
    return _make_trade(
        ob,
        entry_price,
        target,
        candles[entry_idx].timestamp,
        None,
        TradeOutcome.OPEN,
        min_adverse,
        n - 1 - entry_idx,
        config,
    )


def _make_trade(
    ob: Orderblock,
    entry_price: Decimal,
    target: Decimal,
    entry_ts: datetime,
    exit_ts: Optional[datetime],
    outcome: TradeOutcome,
    min_adverse: Decimal,
    holding_candles: int,
    config: OBConfig,
) -> BacktestTrade:
    """Erstellt BacktestTrade mit Penetration Depth Berechnung."""
    # Penetration Depth: Wie tief dringt Preis in die Zone ein
    edge_distance = abs(ob.entry_edge - ob.stop_edge)

    if edge_distance == 0:
        pen_depth = Decimal("0")
    elif ob.direction == OBDirection.BULLISH:
        pen_depth = (entry_price - min_adverse) / edge_distance * Decimal("100")
    else:
        pen_depth = (min_adverse - entry_price) / edge_distance * Decimal("100")

    # Clamp auf [0, 100]
    pen_depth = max(Decimal("0"), min(Decimal("100"), pen_depth))

    return BacktestTrade(
        ob_id=ob.id,
        direction=ob.direction,
        entry_edge=ob.entry_edge,
        stop_edge=ob.stop_edge,
        target=target,
        entry_price=entry_price,
        entry_timestamp=entry_ts,
        exit_timestamp=exit_ts,
        outcome=outcome,
        penetration_depth_pct=pen_depth,
        holding_duration_candles=holding_candles,
        min_adverse_price=min_adverse,
        conviction=ob.conviction,
        volume_zscore=ob.volume_zscore,
        conviction_score=ob.conviction_score,
    )


# ---------------------------------------------------------------------------
# Metriken
# ---------------------------------------------------------------------------


def compute_backtest_metrics(
    trades: List[BacktestTrade],
    zones: List[Orderblock],
    candle_count: int,
    data_start: datetime,
    data_end: datetime,
    zscore_threshold: Decimal = Decimal("2.0"),
) -> BacktestMetrics:
    """Berechnet alle Metriken aus Trades und Zonen."""
    total_zones = len(zones)
    total_trades = len(trades)
    hits = sum(1 for t in trades if t.outcome == TradeOutcome.HIT)
    misses = sum(1 for t in trades if t.outcome == TradeOutcome.MISS)
    open_trades = sum(1 for t in trades if t.outcome == TradeOutcome.OPEN)
    expired_trades = sum(1 for t in trades if t.outcome == TradeOutcome.EXPIRED)

    # Hit Rate (nur abgeschlossene Trades: HIT + MISS, ohne OPEN/EXPIRED)
    closed = hits + misses
    hit_rate = Decimal(str(hits)) / Decimal(str(closed)) if closed > 0 else None

    # Penetration Depth
    pen_depths = [t.penetration_depth_pct for t in trades]
    avg_pen = _mean_decimal(pen_depths) if pen_depths else Decimal("0")
    median_pen = _median_decimal(pen_depths) if pen_depths else Decimal("0")

    # Holding Duration
    hold_durations = [Decimal(str(t.holding_duration_candles)) for t in trades]
    avg_hold = _mean_decimal(hold_durations) if hold_durations else Decimal("0")
    median_hold = _median_decimal(hold_durations) if hold_durations else Decimal("0")

    # 4-Level Conviction Breakdown
    conviction_breakdown: List[ConvictionBreakdown] = []
    for level in ConvictionLevel:
        level_trades = [t for t in trades if t.conviction == level]
        level_hits = sum(1 for t in level_trades if t.outcome == TradeOutcome.HIT)
        level_misses = sum(1 for t in level_trades if t.outcome == TradeOutcome.MISS)
        level_expired = sum(
            1 for t in level_trades if t.outcome == TradeOutcome.EXPIRED
        )
        level_closed = level_hits + level_misses
        level_hr = (
            Decimal(str(level_hits)) / Decimal(str(level_closed))
            if level_closed > 0
            else None
        )
        conviction_breakdown.append(
            ConvictionBreakdown(
                level=level.value,
                count=len(level_trades),
                hits=level_hits,
                misses=level_misses,
                expired=level_expired,
                hit_rate=level_hr,
            )
        )

    # Backward-Compat: HIGH + INSTITUTIONAL -> alte high_conviction Felder
    high_bd = next((b for b in conviction_breakdown if b.level == "HIGH"), None)
    inst_bd = next(
        (b for b in conviction_breakdown if b.level == "INSTITUTIONAL"), None
    )
    hc_count = (high_bd.count if high_bd else 0) + (inst_bd.count if inst_bd else 0)
    hc_hits = (high_bd.hits if high_bd else 0) + (inst_bd.hits if inst_bd else 0)
    hc_closed = hc_hits + (high_bd.misses if high_bd else 0) + (
        inst_bd.misses if inst_bd else 0
    )
    hc_hit_rate = (
        Decimal(str(hc_hits)) / Decimal(str(hc_closed)) if hc_closed > 0 else None
    )

    std_bd = next((b for b in conviction_breakdown if b.level == "STANDARD"), None)
    low_bd = next((b for b in conviction_breakdown if b.level == "LOW"), None)
    sc_hits = (std_bd.hits if std_bd else 0) + (low_bd.hits if low_bd else 0)
    sc_closed = sc_hits + (std_bd.misses if std_bd else 0) + (
        low_bd.misses if low_bd else 0
    )
    sc_hit_rate = (
        Decimal(str(sc_hits)) / Decimal(str(sc_closed)) if sc_closed > 0 else None
    )

    # Z-Score Clusters
    zscore_clusters = _compute_zscore_clusters(trades)

    # Spec 4.3: HIGH_CONVICTION Z-Score Filter (explizit: Z > threshold)
    hc_zscore_trades = [t for t in trades if t.volume_zscore > zscore_threshold]
    hc_zscore_count = len(hc_zscore_trades)
    hc_zscore_hits = sum(1 for t in hc_zscore_trades if t.outcome == TradeOutcome.HIT)
    hc_zscore_closed = hc_zscore_hits + sum(
        1 for t in hc_zscore_trades if t.outcome == TradeOutcome.MISS
    )
    hc_zscore_hit_rate = (
        Decimal(str(hc_zscore_hits)) / Decimal(str(hc_zscore_closed))
        if hc_zscore_closed > 0
        else None
    )

    # State Distribution
    unmitigated = sum(1 for z in zones if z.state == OBState.UNMITIGATED)
    mitigated = sum(1 for z in zones if z.state == OBState.MITIGATED)
    invalid = sum(1 for z in zones if z.state == OBState.INVALID)

    # Zones per Month
    if data_start and data_end:
        days = max((data_end - data_start).days, 1)
        months = Decimal(str(days)) / Decimal("30")
        zones_per_month = (
            Decimal(str(total_zones)) / months if months > 0 else Decimal("0")
        )
    else:
        zones_per_month = Decimal("0")

    return BacktestMetrics(
        total_zones=total_zones,
        total_trades=total_trades,
        hits=hits,
        misses=misses,
        open_trades=open_trades,
        expired_trades=expired_trades,
        hit_rate=hit_rate,
        avg_penetration_depth_pct=avg_pen,
        median_penetration_depth_pct=median_pen,
        avg_holding_duration_candles=avg_hold,
        median_holding_duration_candles=median_hold,
        high_conviction_count=hc_count,
        high_conviction_hit_rate=hc_hit_rate,
        standard_conviction_hit_rate=sc_hit_rate,
        conviction_breakdown=conviction_breakdown,
        zscore_clusters=zscore_clusters,
        high_conviction_zscore_count=hc_zscore_count,
        high_conviction_zscore_hit_rate=hc_zscore_hit_rate,
        unmitigated_count=unmitigated,
        mitigated_count=mitigated,
        invalid_count=invalid,
        zones_per_month=zones_per_month,
    )


def _compute_zscore_clusters(
    trades: List[BacktestTrade],
    bucket_width: Decimal = Decimal("0.5"),
) -> List[ZScoreCluster]:
    """Gruppiert Trades nach Z-Score Buckets und berechnet Hit-Rate pro Bucket."""
    if not trades:
        return []

    # Bestimme Bucket-Grenzen
    min_z = min(t.volume_zscore for t in trades)
    max_z = max(t.volume_zscore for t in trades)

    # Bucket-Start auf naechstes Vielfaches von bucket_width abrunden
    start = (min_z / bucket_width).to_integral_value(
        rounding="ROUND_FLOOR"
    ) * bucket_width
    end = (
        (max_z / bucket_width).to_integral_value(rounding="ROUND_CEILING") + 1
    ) * bucket_width

    clusters: List[ZScoreCluster] = []
    current = start

    while current < end:
        bucket_high = current + bucket_width
        bucket_trades = [t for t in trades if current <= t.volume_zscore < bucket_high]

        if bucket_trades:
            bucket_hits = sum(1 for t in bucket_trades if t.outcome == TradeOutcome.HIT)
            bucket_misses = sum(
                1 for t in bucket_trades if t.outcome == TradeOutcome.MISS
            )
            bucket_closed = bucket_hits + bucket_misses
            bucket_hr = (
                Decimal(str(bucket_hits)) / Decimal(str(bucket_closed))
                if bucket_closed > 0
                else None
            )

            clusters.append(
                ZScoreCluster(
                    range_label=f"{current:.1f}-{bucket_high:.1f}",
                    range_low=current,
                    range_high=bucket_high,
                    count=len(bucket_trades),
                    hits=bucket_hits,
                    misses=bucket_misses,
                    hit_rate=bucket_hr,
                )
            )

        current += bucket_width

    return clusters


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_backtest(
    candles: List[Candle],
    config: OBConfig,
    timeframe: str = "1h",
    symbol: str = "BTCEUR",
) -> BacktestResult:
    """
    Vollstaendiger Backtest:
    1. detect_orderblocks()
    2. update_zone_states()
    3. simulate_zone_approach() pro Zone
    4. compute_backtest_metrics()
    """
    # Detection
    zones = detect_orderblocks(candles, config)

    # State Updates
    zones = update_zone_states(zones, candles)

    # Simulation
    trades: List[BacktestTrade] = []
    for zone in zones:
        trade = simulate_zone_approach(zone, candles, config)
        if trade is not None:
            trades.append(trade)

    # Metriken
    data_start = candles[0].timestamp if candles else datetime(2024, 1, 1)
    data_end = candles[-1].timestamp if candles else datetime(2024, 1, 1)

    metrics = compute_backtest_metrics(
        trades, zones, len(candles), data_start, data_end,
        zscore_threshold=config.zscore_threshold,
    )

    return BacktestResult(
        metrics=metrics,
        trades=trades,
        zones=zones,
        config=config,
        timeframe=timeframe,
        symbol=symbol,
        data_start=data_start,
        data_end=data_end,
        candle_count=len(candles),
    )


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _mean_decimal(values: List[Decimal]) -> Decimal:
    """Durchschnitt einer Decimal-Liste."""
    if not values:
        return Decimal("0")
    return sum(values) / Decimal(str(len(values)))


def _median_decimal(values: List[Decimal]) -> Decimal:
    """Median einer Decimal-Liste (stdlib-only)."""
    if not values:
        return Decimal("0")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / Decimal("2")
    return sorted_vals[mid]
