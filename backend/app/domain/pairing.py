"""
Pairing Logic - Virtuelles Bündeln von Lots

Gewinner- und Verlierer-Lots kombinieren für Netto-Zielmarge.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Tuple
import uuid

from .models import (
    TradeLot,
    Pairing,
    PairingItem,
    PairingStatus,
    PairingSimulation,
    utcnow,
)


def _lot_cost(lot: TradeLot) -> Decimal:
    """Gibt Lot-Kosten in Quote-Currency zurueck."""
    return lot.break_even * lot.qty_base_open


def _lot_pnl_pct(lot: TradeLot, market_price: Decimal) -> Decimal:
    """Berechnet P&L% fuer ein Lot."""
    cost = _lot_cost(lot)
    if cost == 0:
        return Decimal("0")
    value = market_price * lot.qty_base_open
    return (value - cost) / cost


def suggest_pairings(
    lots: List[TradeLot],
    market_price: Decimal,
    threshold_pct: Decimal = Decimal("0.05"),
) -> List[Pairing]:
    """
    Schlaegt Pairings vor (Heuristik v1.2)

    Algorithmus:
    1. Sortiere Lots nach P&L%: Gewinner absteigend, Verlierer aufsteigend
    2. Baue Pairings iterativ:
       - Nimm einen Gewinner
       - Addiere Verlierer bis Schwelle erreicht
       - Wenn nicht erreichbar, naechster Gewinner
    3. Return: Pairing-Vorschlaege

    Args:
        lots: Liste offener TradeLots
        market_price: Aktueller Marktpreis in Quote-Currency
        threshold_pct: Zielmarge (z.B. 0.05 fuer 5%)

    Returns:
        Liste von Pairing-Vorschlaegen
    """
    if not lots:
        return []

    # 1. Lots nach P&L% sortieren
    # Gewinner (positive P&L%) absteigend
    winners = [
        lot for lot in lots
        if _lot_pnl_pct(lot, market_price) > 0
    ]
    winners.sort(
        key=lambda l: _lot_pnl_pct(l, market_price), reverse=True
    )

    # Verlierer (negative P&L%) aufsteigend (negativste zuerst)
    losers = [
        lot for lot in lots
        if _lot_pnl_pct(lot, market_price) <= 0
    ]
    losers.sort(key=lambda l: _lot_pnl_pct(l, market_price))

    if not winners:
        # Keine Gewinner -> keine Pairings moeglich
        return []

    # Symbol aus erstem Lot ableiten
    symbol = lots[0].symbol if lots else "BTCEUR"

    # 2. Pairings bauen
    pairings = []
    used_winners = set()
    used_losers = set()

    for winner in winners:
        if winner.id in used_winners:
            continue

        # Kosten fuer diesen Gewinner
        winner_cost = _lot_cost(winner)

        # Pairing starten mit diesem Gewinner
        items = [
            PairingItem(
                lot_id=winner.id,
                qty_base=winner.qty_base_open,
                cost_quote=winner.break_even * winner.qty_base_open,
            )
        ]

        current_cost = winner_cost
        current_value = market_price * items[0].qty_base
        current_pnl = current_value - current_cost

        # Verlierer hinzufuegen, bis Threshold erreicht
        for loser in losers:
            if loser.id in used_losers:
                continue

            # Simuliere: Was passiert wenn wir diesen Loser hinzufuegen?
            loser_cost = _lot_cost(loser)
            loser_value = market_price * loser.qty_base_open

            new_cost = current_cost + loser_cost
            new_value = current_value + loser_value
            new_pnl = new_value - new_cost
            new_pnl_pct = new_pnl / new_cost if new_cost > 0 else Decimal("0")

            # Wenn immer noch ueber Threshold, hinzufuegen
            if new_pnl_pct >= threshold_pct:
                items.append(
                    PairingItem(
                        lot_id=loser.id,
                        qty_base=loser.qty_base_open,
                        cost_quote=loser.break_even * loser.qty_base_open,
                    )
                )
                current_cost = new_cost
                current_value = new_value
                current_pnl = new_pnl
                used_losers.add(loser.id)

        # Pairing erstellen, wenn >= Threshold UND mindestens 2 Lots
        # Einzelne profitable Lots brauchen kein Pairing -- direkt per Sell-Order verkaufbar
        final_pnl_pct = current_pnl / current_cost if current_cost > 0 else Decimal("0")
        if final_pnl_pct >= threshold_pct and len(items) >= 2:
            pairing = Pairing(
                id=f"pairing_{uuid.uuid4().hex[:8]}",
                items=items,
                threshold_pct=threshold_pct,
                status=PairingStatus.DRAFT,
                created_at=utcnow(),
                symbol=symbol,
            )
            pairings.append(pairing)
            used_winners.add(winner.id)

    return pairings


def simulate_pairing(
    pairing: Pairing,
    market_price: Decimal,
    all_lots: List[TradeLot],
    fee_pct: Decimal = Decimal("0.001"),  # 0.1% Default
    sell_price: Decimal | None = None,
) -> PairingSimulation:
    """
    Simuliert einen Pairing-Verkauf

    Berechnet deterministisch was passieren würde.

    Args:
        pairing: Pairing-Objekt
        market_price: Aktueller Marktpreis
        all_lots: Alle Lots (für Portfolio-Berechnung)
        fee_pct: Trading Fee (z.B. 0.001 für 0.1%)
        sell_price: Tatsaechlicher Verkaufspreis (custom oder market+buffer).
                    Wenn None, wird market_price verwendet.

    Returns:
        PairingSimulation mit allen Details
    """
    # Total Base-Asset zu verkaufen
    total_base = pairing.net_qty_base()

    # Effektiver Verkaufspreis fuer Erloesberechnung
    effective_price = sell_price if sell_price is not None else market_price

    # Erwarteter Erlös (vor Fee)
    gross_proceeds = total_base * effective_price

    # Fee
    estimated_fee = gross_proceeds * fee_pct

    # Netto-Erlös
    net_proceeds = gross_proceeds - estimated_fee

    # Kosten
    total_cost = pairing.net_cost()

    # Realisierte P&L
    realized_pnl = net_proceeds - total_cost

    # Affected Lots (welche Lots werden geschlossen/teilweise geschlossen)
    affected_lots_info = []
    for item in pairing.items:
        # Finde Lot
        lot = next((l for l in all_lots if l.id == item.lot_id), None)
        if lot:
            # Wird das Lot vollständig geschlossen?
            is_full = item.qty_base == lot.qty_base_open

            affected_lots_info.append({
                "lot_id": lot.id,
                "qty_base_to_sell": str(item.qty_base),
                "qty_base_remaining": str(lot.qty_base_open - item.qty_base),
                "is_full_close": is_full,
                "current_status": lot.status.value,
                "new_status": "CLOSED" if is_full else "PARTIAL_CLOSED",
            })

    # Verbleibende Portfolio-Bestände nach Pairing
    total_portfolio_base = sum(lot.qty_base_open for lot in all_lots)
    total_portfolio_cost = sum(lot.break_even * lot.qty_base_open for lot in all_lots)

    remaining_base = total_portfolio_base - total_base
    remaining_cost = total_portfolio_cost - total_cost

    return PairingSimulation(
        pairing=pairing,
        market_price=market_price,
        total_base_to_sell=total_base,
        expected_proceeds_quote=net_proceeds,
        expected_costs_quote=total_cost,
        expected_realized_pnl_quote=realized_pnl,
        affected_lots=affected_lots_info,
        remaining_portfolio_base=remaining_base,
        remaining_portfolio_cost_quote=remaining_cost,
        estimated_fee_quote=estimated_fee,
        fee_pct=fee_pct,
    )


def optimize_pairing_partial(
    winner: TradeLot,
    losers: List[TradeLot],
    market_price: Decimal,
    threshold_pct: Decimal
) -> Pairing | None:
    """
    Optimiert Pairing durch partielle Lot-Nutzung

    Experimentell: Versucht minimale Verlierer-Menge zu finden.
    (Optional für v1.1+)

    Args:
        winner: Gewinner-Lot
        losers: Verfügbare Verlierer-Lots
        market_price: Marktpreis
        threshold_pct: Zielmarge

    Returns:
        Optimiertes Pairing oder None
    """
    # TODO: Implementierung für v1.1+
    # Könnte Binary Search oder Greedy-Algorithmus verwenden
    raise NotImplementedError("Partial pairing optimization not yet implemented")
