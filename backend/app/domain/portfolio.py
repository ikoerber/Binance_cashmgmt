"""Portfolio Calculation Logic - Pure functions"""
from datetime import datetime
from decimal import Decimal
from typing import List

from .models import (
    DailyPerformance,
    EventType,
    LedgerEvent,
    PortfolioState,
    TradeSide,
    utcnow,
)


def compute_portfolio_from_ledger(
    events: List[LedgerEvent],
    as_of: datetime | None = None
) -> PortfolioState:
    """
    Berechnet Portfolio-Zustand aus Ledger Events

    Dies ist die zentrale Funktion: Deterministisch, reproduzierbar.
    Alle Portfolio-KPIs werden aus dem Event-Stream abgeleitet.

    Args:
        events: Liste von LedgerEvents (chronologisch sortiert)
        as_of: Optional - berechne Zustand zu diesem Zeitpunkt

    Returns:
        PortfolioState mit allen KPIs
    """
    # Filter events bis as_of (falls angegeben)
    if as_of:
        events = [e for e in events if e.timestamp <= as_of]

    # Initialer Zustand
    btc_qty = Decimal("0")
    btc_cost_basis_eur = Decimal("0")
    eur_available = Decimal("0")
    realized_pnl_eur = Decimal("0")
    external_net_eur = Decimal("0")

    latest_timestamp = utcnow()
    if events:
        latest_timestamp = max(e.timestamp for e in events)

    for event in events:
        if event.type == EventType.TRADE_FILL:
            if event.side == TradeSide.BUY:
                # Buy: BTC-Bestand erhöht, Kosten erhöht, EUR reduziert
                # WICHTIG: qty von Binance ist BRUTTO (VOR Fee-Abzug)
                trade_cost = event.price * event.amount

                if event.fee_asset == "BTC" and event.fee_amount and event.price:
                    # BTC Fee: Menge um Fee reduzieren, KEINE zusätzlichen EUR-Kosten
                    btc_qty += event.amount - event.fee_amount
                elif event.fee_asset == "EUR" and event.fee_amount:
                    # EUR Fee: volle BTC-Menge, zusätzliche EUR-Kosten
                    btc_qty += event.amount
                    trade_cost += event.fee_amount
                else:
                    # Kein Fee oder BNB Fee (BTC-Menge nicht betroffen)
                    btc_qty += event.amount

                btc_cost_basis_eur += trade_cost
                eur_available -= trade_cost

            elif event.side == TradeSide.SELL:
                # Sell: BTC-Bestand reduziert, EUR erhöht, P&L realisiert
                sell_qty = event.amount

                # Erlös = Verkaufspreis * Menge
                sell_proceeds = event.price * sell_qty

                # Fee abziehen (falls in EUR)
                if event.fee_asset == "EUR" and event.fee_amount:
                    sell_proceeds -= event.fee_amount
                # Fee in BTC: event.amount ist bereits netto, aber EUR-Fee-Wert muss vom Erlös abgezogen werden
                elif event.fee_asset == "BTC" and event.fee_amount and event.price:
                    fee_eur_value = event.fee_amount * event.price
                    sell_proceeds -= fee_eur_value

                # Weighted Average Cost: Anteilige Kostenbasis
                if btc_qty > 0:
                    avg_cost_per_btc = btc_cost_basis_eur / btc_qty
                    cost_of_sold = avg_cost_per_btc * sell_qty
                else:
                    cost_of_sold = Decimal("0")

                # Realisierte P&L
                pnl = sell_proceeds - cost_of_sold
                realized_pnl_eur += pnl

                # Bestände anpassen
                btc_qty -= sell_qty
                btc_cost_basis_eur -= cost_of_sold
                eur_available += sell_proceeds

        elif event.type == EventType.DEPOSIT:
            # Einzahlung (EUR oder BTC)
            if event.asset == "EUR":
                eur_available += event.amount
            elif event.asset == "BTC":
                btc_qty += event.amount
                # Deposit erhöht NICHT die Kostenbasis (wurde extern gekauft)

        elif event.type == EventType.WITHDRAWAL:
            # Auszahlung (EUR oder BTC)
            if event.asset == "EUR":
                eur_available -= event.amount
            elif event.asset == "BTC":
                # Withdrawal: Anteilige Kostenbasis entfernen
                if btc_qty > 0:
                    avg_cost_per_btc = btc_cost_basis_eur / btc_qty
                    cost_of_withdrawn = avg_cost_per_btc * event.amount
                    btc_cost_basis_eur -= cost_of_withdrawn
                btc_qty -= event.amount

        elif event.type == EventType.EXTERNAL_CASHFLOW:
            # Externe Cashflows (Bank Ein-/Auszahlung)
            # Beeinflussen NICHT BTC-Kostenbasis
            external_net_eur += event.amount

        elif event.type == EventType.FEE:
            # Separate Fee Events (falls nicht im Fill enthalten)
            if event.asset == "EUR":
                eur_available -= event.amount
            elif event.asset == "BTC":
                btc_qty -= event.amount
                # Fee reduziert BTC-Menge, Kostenbasis bleibt
                # (macht Break-even höher)

        elif event.type == EventType.ADJUSTMENT:
            # Admin-Korrektur: Je nach Asset anpassen
            if event.asset == "EUR":
                eur_available += event.amount
            elif event.asset == "BTC":
                btc_qty += event.amount
                # Kostenbasis bei ADJUSTMENT nicht automatisch anpassen
                # (muss explizit entschieden werden)

    return PortfolioState(
        timestamp=latest_timestamp,
        btc_qty=btc_qty,
        btc_cost_basis_eur=btc_cost_basis_eur,
        eur_available=eur_available,
        realized_pnl_eur=realized_pnl_eur,
        external_net_eur=external_net_eur,
    )


def compute_daily_performance(
    events: List[LedgerEvent],
    market_price: Decimal,
    reference_date: datetime | None = None,
) -> DailyPerformance:
    """
    Berechnet Tages-Performance aus Ledger Events.

    Strategie: Portfolio-Zustand am Tagesbeginn vs. jetzt vergleichen.
    """
    if reference_date is None:
        reference_date = utcnow()

    start_of_day = reference_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Portfolio-Zustand am Tagesbeginn und jetzt
    portfolio_sod = compute_portfolio_from_ledger(events, as_of=start_of_day)
    portfolio_now = compute_portfolio_from_ledger(events)

    # Delta realisierte P&L
    realized_pnl_today = portfolio_now.realized_pnl_eur - portfolio_sod.realized_pnl_eur

    # Unrealisierte P&L (beide mit aktuellem Marktpreis)
    unrealized_sod = portfolio_sod.unrealized_pnl_eur(market_price)
    unrealized_now = portfolio_now.unrealized_pnl_eur(market_price)

    # Heutige Trade-Fills filtern
    today_fills = [
        e for e in events
        if e.timestamp > start_of_day and e.type == EventType.TRADE_FILL
    ]

    buys = [e for e in today_fills if e.side == TradeSide.BUY]
    sells = [e for e in today_fills if e.side == TradeSide.SELL]

    return DailyPerformance(
        date=start_of_day,
        realized_pnl_today_eur=realized_pnl_today,
        buys_count_today=len(buys),
        buys_volume_btc_today=sum((e.amount for e in buys), Decimal("0")),
        buys_volume_eur_today=sum((e.amount * e.price for e in buys), Decimal("0")),
        sells_count_today=len(sells),
        sells_volume_btc_today=sum((e.amount for e in sells), Decimal("0")),
        sells_volume_eur_today=sum((e.amount * e.price for e in sells), Decimal("0")),
        unrealized_pnl_start_of_day_eur=unrealized_sod,
        unrealized_pnl_current_eur=unrealized_now,
    )


def calculate_target_price(
    break_even: Decimal,
    target_margin_pct: Decimal,
    fee_buffer_pct: Decimal = Decimal("0")
) -> Decimal:
    """
    Berechnet Zielverkaufspreis

    Args:
        break_even: Break-even Preis
        target_margin_pct: Zielmarge in Prozent (z.B. 0.05 für 5%)
        fee_buffer_pct: Optionaler Fee-Puffer (z.B. 0.002 für 0.2%)

    Returns:
        Zielpreis
    """
    return break_even * (Decimal("1") + target_margin_pct) * (Decimal("1") + fee_buffer_pct)
