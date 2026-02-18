"""
Orderblock Detection – 5-Phasen-Validierungspipeline.

Identifiziert hochreaktive institutionelle Preiszonen (Orderblocks)
auf Basis von OHLCV-Kerzen:
  1. Formation (Base Candle)
  2. Displacement (ATR-basiert)
  3. Fair Value Gap (3-Kerzen-Imbalance)
  4. Structure Break (BOS via Swing Fractal, Close-basiert)
  5. State Management (UNMITIGATED / MITIGATED / INVALID)

Alle Berechnungen verwenden Decimal (niemals float).
Zeitkonsistent: Kein Look-Ahead-Bias. OB gilt erst ab confirmed_at.
"""

from dataclasses import replace
from decimal import Decimal
from typing import List, Optional

from app.domain.orderblock.models import (
    Candle,
    FairValueGap,
    OBConfig,
    OBDirection,
    OBState,
    Orderblock,
    SwingPoint,
)
from app.domain.orderblock.scoring import (
    _clamp,
    compute_atr,
    compute_conviction_score,
    compute_impact_efficiency_ratio,
    compute_ofi_divergence,
    compute_volume_percentile,
    compute_volume_weight,
    compute_volume_zscore,
    conviction_level_from_score,
)
from app.domain.orderblock.classification import classify_orderblocks


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
    for i in range(max(start_index, 2), min(start_index + window, n)):
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
# Liquidity Sweep Detection
# ---------------------------------------------------------------------------


def detect_liquidity_sweep(
    candles: List[Candle],
    ob_index: int,
    direction: OBDirection,
    all_swings: List[SwingPoint],
    lookback: int,
) -> tuple:
    """
    Erkennt ob ein Liquidity Sweep vor der OB-Formation stattfand.

    Ein Sweep liegt vor wenn eine Kerze ueber einen bestaetigten Swing-Punkt
    hinaus wicked, aber auf der "richtigen" Seite geschlossen hat (Reversal).

    Bullish OB: Kerze wicked unter Swing Low (Sell-Stops abgeraeumt),
                schliesst aber ueber dem Swing Low.
    Bearish OB: Kerze wicked ueber Swing High (Buy-Stops abgeraeumt),
                schliesst aber unter dem Swing High.

    Sucht im Fenster [ob_index - lookback, ob_index).
    Verwendet nur Swings die VOR dem OB bestaetigt sind (keine Look-Ahead-Bias).

    Returns: (has_sweep: bool, sweep_level: Optional[Decimal])
    """
    if lookback <= 0:
        return (False, None)

    window_start = max(0, ob_index - lookback)

    # Nur bestaetigte Swings vor der OB-Formation verwenden
    if direction == OBDirection.BULLISH:
        # Bullish OB: Sweep unter vorherigen Swing Lows
        relevant_swings = [
            s for s in all_swings
            if not s.is_high  # Swing Lows
            and s.confirmed_at_index < ob_index  # Zeitkonsistent
            and s.index < ob_index  # Swing liegt vor dem OB
        ]
    else:
        # Bearish OB: Sweep ueber vorherigen Swing Highs
        relevant_swings = [
            s for s in all_swings
            if s.is_high  # Swing Highs
            and s.confirmed_at_index < ob_index
            and s.index < ob_index
        ]

    if not relevant_swings:
        return (False, None)

    # Suche die juengste Sweep-Kerze im Lookback-Fenster
    best_sweep_idx = -1
    best_sweep_level = None

    for candle_idx in range(window_start, ob_index):
        candle = candles[candle_idx]
        for swing in relevant_swings:
            if direction == OBDirection.BULLISH:
                # Wick unter Swing Low, Close darueber = Sell-Stop Sweep
                if candle.low <= swing.price and candle.close > swing.price:
                    if candle_idx > best_sweep_idx:
                        best_sweep_idx = candle_idx
                        best_sweep_level = swing.price
            else:
                # Wick ueber Swing High, Close darunter = Buy-Stop Sweep
                if candle.high >= swing.price and candle.close < swing.price:
                    if candle_idx > best_sweep_idx:
                        best_sweep_idx = candle_idx
                        best_sweep_level = swing.price

    if best_sweep_idx >= 0:
        return (True, best_sweep_level)
    return (False, None)


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
                if last_swing_high is None or sw.index > last_swing_high.index:
                    last_swing_high = sw
            else:
                if last_swing_low is None or sw.index > last_swing_low.index:
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

    # Liquidity Sweep Detection (verwendet dieselben Swing Points wie BOS)
    has_sweep, sweep_level = detect_liquidity_sweep(
        candles, ob_index, direction, all_swings, config.sweep_lookback
    )

    # Sweep Conviction Boost (additiv, gedeckelt bei 100)
    if has_sweep:
        conv_score = _clamp(
            conv_score + config.sweep_conviction_boost,
            Decimal("0"),
            Decimal("100"),
        )
        conviction = conviction_level_from_score(conv_score)

    # Spec 4.3: Expliziter Z-Score Threshold Filter
    is_hc_zscore = vol_zscore > config.zscore_threshold

    ts = int(candles[ob_index].timestamp.timestamp())
    ob_id = f"ob_{direction.value.lower()}_{ts}_{ob_index}"

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
        has_liquidity_sweep=has_sweep,
        liquidity_sweep_level=sweep_level,
    )


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
            replace(
                ob,
                state=new_state,
                mitigated_at=mitigated_at,
                invalidated_at=invalidated_at,
            )
        )

    return updated
