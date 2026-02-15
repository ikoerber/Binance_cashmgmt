"""Domain models - pure Python dataclasses"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List


def utcnow() -> datetime:
    """Returns current UTC time as naive datetime (for DB compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EventType(Enum):
    """Ledger Event Types"""
    TRADE_FILL = "TRADE_FILL"
    FEE = "FEE"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    EXTERNAL_CASHFLOW = "EXTERNAL_CASHFLOW"
    ADJUSTMENT = "ADJUSTMENT"


class EventSource(Enum):
    """Event Source"""
    BINANCE = "BINANCE"
    EXTERNAL = "EXTERNAL"
    ADJUSTMENT = "ADJUSTMENT"


class TradeSide(Enum):
    """Trade Side"""
    BUY = "BUY"
    SELL = "SELL"


class LotStatus(Enum):
    """TradeLot Status"""
    OPEN = "OPEN"
    PARTIAL_CLOSED = "PARTIAL_CLOSED"
    CLOSED = "CLOSED"


class AllocationStrategy(Enum):
    """Sell Allocation Strategy"""
    FIFO = "FIFO"             # First In, First Out (aelteste Lots zuerst)
    LIFO = "LIFO"             # Last In, First Out (neueste Lots zuerst)
    HIGHEST_COST = "HIGHEST_COST"  # Hoechster Break-even zuerst (Tax-Loss Harvesting)


@dataclass
class LedgerEvent:
    """
    Immutable Ledger Event (append-only)

    Alle Zustandsänderungen im System gehen durch Ledger Events.
    Events sind immutable und werden nie gelöscht oder geändert.
    """
    id: str
    type: EventType
    timestamp: datetime
    asset: str  # "BTC" oder "EUR"
    amount: Decimal  # Positive oder negative Menge

    # Optional fields je nach Event-Typ
    symbol: Optional[str] = None  # z.B. "BTCEUR"
    price: Optional[Decimal] = None  # Preis zum Zeitpunkt des Events
    side: Optional[TradeSide] = None  # BUY/SELL für TRADE_FILL

    fee_asset: Optional[str] = None
    fee_amount: Optional[Decimal] = None
    fee_eur_value: Optional[Decimal] = None  # Vorberechneter EUR-Wert der Fee (fuer BNB/andere Fee-Assets)

    source: EventSource = EventSource.BINANCE
    source_id: Optional[str] = None  # z.B. Binance tradeId

    note: Optional[str] = None  # Für ADJUSTMENT oder EXTERNAL_CASHFLOW
    raw_payload: Optional[dict] = None  # Original-Daten von Binance


@dataclass
class TradeLot:
    """
    TradeLot - repräsentiert eine BTC-Position

    1 Fill = 1 Lot (deterministisch)
    Jeder Buy-Fill erzeugt genau ein TradeLot.
    """
    id: str
    created_from_fill_id: str  # Referenz zum LedgerEvent
    created_at: datetime

    qty_btc_initial: Decimal  # Ursprüngliche Netto-Menge (BRUTTO minus BTC-Fee)
    qty_btc_open: Decimal  # Aktuell offene Menge

    cost_eur: Decimal  # Gesamtkosten in EUR (inkl. Fees)

    status: LotStatus = LotStatus.OPEN
    target_margin_pct: Optional[Decimal] = None  # Lot-spezifische Zielmarge

    @property
    def break_even(self) -> Decimal:
        """Break-even Preis pro BTC"""
        if self.qty_btc_initial == 0:
            return Decimal("0")
        return self.cost_eur / self.qty_btc_initial

    def unrealized_pnl(self, market_price: Decimal) -> Decimal:
        """Unrealisierte P&L in EUR"""
        return (market_price * self.qty_btc_open) - (self.break_even * self.qty_btc_open)

    def unrealized_pnl_pct(self, market_price: Decimal) -> Decimal:
        """Unrealisierte P&L in %"""
        if self.break_even == 0:
            return Decimal("0")
        return (market_price / self.break_even) - Decimal("1")


@dataclass
class SellAllocation:
    """
    Sell Allocation - FIFO Zuordnung von Sell-Fills zu TradeLots

    Persistiert die Zuordnung: Welcher Sell-Fill schließt welches Lot.
    """
    id: str
    sell_fill_id: str  # Referenz zum Sell LedgerEvent
    trade_lot_id: str
    qty_allocated: Decimal  # Wie viel BTC von diesem Lot verkauft wurde
    realized_pnl_eur: Decimal  # Realisierte P&L in EUR
    created_at: datetime


@dataclass
class PairingItem:
    """
    Ein Item in einem Pairing

    Kann ein ganzes Lot oder eine Teilmenge sein.
    """
    lot_id: str
    qty_btc: Decimal  # Wie viel BTC von diesem Lot im Pairing
    cost_eur: Decimal  # Anteilige Kosten


class PairingStatus(Enum):
    """Pairing Status"""
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    EXECUTED = "EXECUTED"


@dataclass
class Pairing:
    """
    Virtuelles Pairing von TradeLots

    Bündelt Gewinner- und Verlierer-Lots für Netto-Zielmarge.
    """
    id: str
    items: List[PairingItem]
    threshold_pct: Decimal  # z.B. 0.05 für 5%
    status: PairingStatus = PairingStatus.DRAFT
    created_at: Optional[datetime] = None

    def net_cost(self) -> Decimal:
        """Netto-Kosten aller Items"""
        return sum((item.cost_eur for item in self.items), Decimal("0"))

    def net_qty_btc(self) -> Decimal:
        """Netto-BTC-Menge aller Items"""
        return sum((item.qty_btc for item in self.items), Decimal("0"))

    def net_value(self, market_price: Decimal) -> Decimal:
        """Netto-Marktwert"""
        return self.net_qty_btc() * market_price

    def net_pnl(self, market_price: Decimal) -> Decimal:
        """Netto-P&L in EUR"""
        return self.net_value(market_price) - self.net_cost()

    def net_pnl_pct(self, market_price: Decimal) -> Decimal:
        """Netto-P&L in %"""
        if self.net_cost() == 0:
            return Decimal("0")
        return self.net_pnl(market_price) / self.net_cost()

    def is_profitable(self, market_price: Decimal) -> bool:
        """Prüft ob Pairing profitable ist (>= Threshold)"""
        return self.net_pnl_pct(market_price) >= self.threshold_pct


@dataclass
class PairingSimulation:
    """
    Simulation eines Pairing-Verkaufs

    Zeigt was passieren würde, bevor es ausgeführt wird.
    """
    pairing: Pairing
    market_price: Decimal

    # Erwartete Ergebnisse
    total_btc_to_sell: Decimal
    expected_proceeds_eur: Decimal  # Nach Fees
    expected_costs_eur: Decimal
    expected_realized_pnl_eur: Decimal

    # Auswirkungen
    affected_lots: List[dict]  # Welche Lots werden geschlossen/teilweise geschlossen
    remaining_portfolio_btc: Decimal
    remaining_portfolio_cost_eur: Decimal

    # Fees
    estimated_fee_eur: Decimal
    fee_pct: Decimal  # z.B. 0.001 für 0.1%


@dataclass
class DailyPerformance:
    """Tages-Performance — berechnet aus Ledger-Events (Vergleich Tagesbeginn vs. jetzt)."""
    date: datetime

    # Realized P&L today (from sells)
    realized_pnl_today_eur: Decimal

    # Today's buys
    buys_count_today: int
    buys_volume_btc_today: Decimal
    buys_volume_eur_today: Decimal

    # Today's sells
    sells_count_today: int
    sells_volume_btc_today: Decimal
    sells_volume_eur_today: Decimal

    # Unrealized P&L change
    unrealized_pnl_start_of_day_eur: Decimal
    unrealized_pnl_current_eur: Decimal

    @property
    def unrealized_pnl_change_eur(self) -> Decimal:
        return self.unrealized_pnl_current_eur - self.unrealized_pnl_start_of_day_eur


@dataclass
class PortfolioState:
    """
    Portfolio-Zustand zu einem Zeitpunkt

    Wird aus Ledger berechnet (nicht persistiert).
    """
    timestamp: datetime

    # BTC Position
    btc_qty: Decimal  # Gesamte BTC-Menge
    btc_cost_basis_eur: Decimal  # Gesamtkosten in EUR

    # EUR Cash
    eur_available: Decimal  # Verfügbare EUR

    # P&L
    realized_pnl_eur: Decimal  # Realisierte Gewinne/Verluste

    # External Cashflows
    external_net_eur: Decimal  # Summe externe Ein-/Auszahlungen

    @property
    def break_even(self) -> Optional[Decimal]:
        """Portfolio Break-even Preis"""
        if self.btc_qty == 0:
            return None
        return self.btc_cost_basis_eur / self.btc_qty

    def market_value_eur(self, market_price: Decimal) -> Decimal:
        """Marktwert des BTC-Bestands in EUR"""
        return self.btc_qty * market_price

    def unrealized_pnl_eur(self, market_price: Decimal) -> Decimal:
        """Unrealisierte P&L in EUR"""
        return self.market_value_eur(market_price) - self.btc_cost_basis_eur

    def target_price(self, target_margin_pct: Decimal, fee_buffer_pct: Decimal = Decimal("0")) -> Optional[Decimal]:
        """Zielverkaufspreis basierend auf Break-even und Zielmarge"""
        if self.break_even is None:
            return None
        return self.break_even * (Decimal("1") + target_margin_pct) * (Decimal("1") + fee_buffer_pct)
