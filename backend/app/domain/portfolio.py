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
from app.symbol_registry import get_base_asset, get_quote_asset


def compute_portfolio_from_ledger(
    events: List[LedgerEvent],
    as_of: datetime | None = None,
    symbol: str = "BTCEUR",
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
    base_asset = get_base_asset(symbol)
    quote_asset = get_quote_asset(symbol)

    # Filter events bis as_of (falls angegeben)
    if as_of:
        events = [e for e in events if e.timestamp <= as_of]

    # Initialer Zustand
    base_qty = Decimal("0")
    base_cost_basis_quote = Decimal("0")
    quote_available = Decimal("0")
    realized_pnl_quote = Decimal("0")
    external_net_quote = Decimal("0")

    latest_timestamp = utcnow()
    if events:
        latest_timestamp = max(e.timestamp for e in events)

    for event in events:
        if event.type == EventType.TRADE_FILL:
            if event.side == TradeSide.BUY:
                # Buy: Base-Bestand erhöht, Kosten erhöht, Quote reduziert
                # WICHTIG: qty von Binance ist BRUTTO (VOR Fee-Abzug)
                trade_cost = event.price * event.amount

                if event.fee_asset == base_asset and event.fee_amount and event.price:
                    # Base-Asset Fee: Menge um Fee reduzieren, KEINE zusätzlichen Quote-Kosten
                    base_qty += event.amount - event.fee_amount
                elif event.fee_asset == quote_asset and event.fee_amount:
                    # Quote Fee: volle Base-Menge, zusätzliche Quote-Kosten
                    base_qty += event.amount
                    trade_cost += event.fee_amount
                else:
                    # BNB oder andere Fee: Base-Menge nicht betroffen, aber Quote-Kosten erhoehen
                    base_qty += event.amount
                    if event.fee_quote_value and event.fee_asset not in (quote_asset, base_asset, None):
                        trade_cost += event.fee_quote_value

                base_cost_basis_quote += trade_cost
                quote_available -= trade_cost

            elif event.side == TradeSide.SELL:
                # Sell: Base-Bestand reduziert, Quote erhöht, P&L realisiert
                sell_qty = event.amount

                # Erlös = Verkaufspreis * Menge
                sell_proceeds = event.price * sell_qty

                # Fee abziehen (falls in Quote-Currency)
                if event.fee_asset == quote_asset and event.fee_amount:
                    sell_proceeds -= event.fee_amount
                # Fee in Base-Asset
                elif event.fee_asset == base_asset and event.fee_amount and event.price:
                    base_fee_quote = event.fee_amount * event.price
                    sell_proceeds -= base_fee_quote
                # BNB oder andere Fee: Vorberechneten Quote-Wert abziehen
                elif event.fee_quote_value:
                    sell_proceeds -= event.fee_quote_value

                # Weighted Average Cost: Anteilige Kostenbasis
                if base_qty > 0:
                    avg_cost = base_cost_basis_quote / base_qty
                    cost_of_sold = avg_cost * sell_qty
                else:
                    cost_of_sold = Decimal("0")

                # Realisierte P&L
                pnl = sell_proceeds - cost_of_sold
                realized_pnl_quote += pnl

                # Bestände anpassen
                base_qty -= sell_qty
                base_cost_basis_quote -= cost_of_sold
                quote_available += sell_proceeds

        elif event.type == EventType.DEPOSIT:
            # Einzahlung (Quote-Currency oder Base-Asset)
            if event.asset == quote_asset:
                quote_available += event.amount
            elif event.asset == base_asset:
                base_qty += event.amount
                # Deposit erhöht NICHT die Kostenbasis (wurde extern gekauft)

        elif event.type == EventType.WITHDRAWAL:
            # Auszahlung (Quote-Currency oder Base-Asset)
            if event.asset == quote_asset:
                quote_available -= event.amount
            elif event.asset == base_asset:
                # Withdrawal: Anteilige Kostenbasis entfernen
                if base_qty > 0:
                    avg_cost = base_cost_basis_quote / base_qty
                    cost_of_withdrawn = avg_cost * event.amount
                    base_cost_basis_quote -= cost_of_withdrawn
                base_qty -= event.amount

        elif event.type == EventType.EXTERNAL_CASHFLOW:
            # Externe Cashflows (Bank Ein-/Auszahlung)
            # Beeinflussen NICHT Base-Kostenbasis
            external_net_quote += event.amount

        elif event.type == EventType.FEE:
            # Separate Fee Events (falls nicht im Fill enthalten)
            if event.asset == quote_asset:
                quote_available -= event.amount
            elif event.asset == base_asset:
                base_qty -= event.amount
                # Fee reduziert Base-Menge, Kostenbasis bleibt
                # (macht Break-even höher)

        elif event.type == EventType.ADJUSTMENT:
            # Admin-Korrektur: Je nach Asset anpassen
            if event.asset == quote_asset:
                quote_available += event.amount
            elif event.asset == base_asset:
                base_qty += event.amount
                # Kostenbasis bei ADJUSTMENT nicht automatisch anpassen
                # (muss explizit entschieden werden)

    return PortfolioState(
        timestamp=latest_timestamp,
        base_qty=base_qty,
        base_cost_basis_quote=base_cost_basis_quote,
        quote_available=quote_available,
        realized_pnl_quote=realized_pnl_quote,
        external_net_quote=external_net_quote,
    )


def compute_daily_performance(
    events: List[LedgerEvent],
    market_price: Decimal,
    reference_date: datetime | None = None,
    symbol: str = "BTCEUR",
) -> DailyPerformance:
    """
    Berechnet Tages-Performance aus Ledger Events.

    Strategie: Portfolio-Zustand am Tagesbeginn vs. jetzt vergleichen.
    """
    if reference_date is None:
        reference_date = utcnow()

    start_of_day = reference_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Portfolio-Zustand am Tagesbeginn und jetzt
    portfolio_sod = compute_portfolio_from_ledger(events, as_of=start_of_day, symbol=symbol)
    portfolio_now = compute_portfolio_from_ledger(events, symbol=symbol)

    # Delta realisierte P&L
    realized_pnl_today = portfolio_now.realized_pnl_quote - portfolio_sod.realized_pnl_quote

    # Unrealisierte P&L (beide mit aktuellem Marktpreis)
    unrealized_sod = portfolio_sod.unrealized_pnl_quote(market_price)
    unrealized_now = portfolio_now.unrealized_pnl_quote(market_price)

    # Heutige Trade-Fills filtern
    today_fills = [
        e for e in events
        if e.timestamp > start_of_day and e.type == EventType.TRADE_FILL
    ]

    buys = [e for e in today_fills if e.side == TradeSide.BUY]
    sells = [e for e in today_fills if e.side == TradeSide.SELL]

    return DailyPerformance(
        date=start_of_day,
        realized_pnl_today_quote=realized_pnl_today,
        buys_count_today=len(buys),
        buys_volume_base_today=sum((e.amount for e in buys), Decimal("0")),
        buys_volume_quote_today=sum((e.amount * (e.price or Decimal("0")) for e in buys), Decimal("0")),
        sells_count_today=len(sells),
        sells_volume_base_today=sum((e.amount for e in sells), Decimal("0")),
        sells_volume_quote_today=sum((e.amount * (e.price or Decimal("0")) for e in sells), Decimal("0")),
        unrealized_pnl_start_of_day_quote=unrealized_sod,
        unrealized_pnl_current_quote=unrealized_now,
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
