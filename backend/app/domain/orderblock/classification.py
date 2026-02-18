"""
Orderblock Classification – AlbaTherium-Klassifikation.

Strukturelle Einordnung erkannter Orderblocks in den uebergeordneten
Marktkontext (EXTREME / DECISIONAL / SMT / UNCLASSIFIED).
"""

from dataclasses import replace
from typing import List

from app.domain.orderblock.models import (
    Candle,
    InducementLevel,
    OBCategory,
    OBDirection,
    Orderblock,
    SwingPoint,
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
        cat = OBCategory.UNCLASSIFIED

        if ob.direction == OBDirection.BULLISH:
            if major_low.index <= ob.formed_at_index <= major_high.index:
                cat = OBCategory.SMT
        elif ob.direction == OBDirection.BEARISH:
            # Bearish: Major High vor Major Low (Abwaertsbewegung)
            if (
                min(major_high.index, major_low.index)
                <= ob.formed_at_index
                <= max(major_high.index, major_low.index)
            ):
                cat = OBCategory.SMT

        classified.append(replace(ob, category=cat))

    # --- Phase 2: EXTREME identifizieren ---
    # Bullish: tiefster OB (naechst am Major Low)
    bullish_in_range = [
        ob for ob in classified
        if ob.direction == OBDirection.BULLISH and ob.category == OBCategory.SMT
    ]
    if bullish_in_range:
        extreme_id = min(bullish_in_range, key=lambda ob: ob.zone_bottom).id
        classified = [
            replace(ob, category=OBCategory.EXTREME)
            if ob.id == extreme_id else ob
            for ob in classified
        ]

    # Bearish: hoechster OB (naechst am Major High)
    bearish_in_range = [
        ob for ob in classified
        if ob.direction == OBDirection.BEARISH and ob.category == OBCategory.SMT
    ]
    if bearish_in_range:
        extreme_id = max(bearish_in_range, key=lambda ob: ob.zone_top).id
        classified = [
            replace(ob, category=OBCategory.EXTREME)
            if ob.id == extreme_id else ob
            for ob in classified
        ]

    # --- Phase 3: DECISIONAL identifizieren ---
    if current_idm is not None:
        # Bullish: juengster OB unterhalb IDM
        below_idm = [
            ob for ob in classified
            if ob.direction == OBDirection.BULLISH
            and ob.category == OBCategory.SMT
            and ob.zone_top < current_idm
        ]
        if below_idm:
            decisional_id = max(below_idm, key=lambda ob: ob.formed_at_index).id
            classified = [
                replace(ob, category=OBCategory.DECISIONAL)
                if ob.id == decisional_id else ob
                for ob in classified
            ]

    return classified
