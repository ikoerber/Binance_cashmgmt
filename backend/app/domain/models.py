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
    MERGED = "MERGED"


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
    fee_quote_value: Optional[Decimal] = None  # Vorberechneter Quote-Currency-Wert der Fee (fuer BNB/andere Fee-Assets)

    source: EventSource = EventSource.BINANCE
    source_id: Optional[str] = None  # z.B. Binance tradeId

    note: Optional[str] = None  # Für ADJUSTMENT oder EXTERNAL_CASHFLOW
    raw_payload: Optional[dict] = None  # Original-Daten von Binance


@dataclass
class TradeLot:
    """
    TradeLot - repräsentiert eine Base-Asset-Position

    1 Fill = 1 Lot (deterministisch)
    Jeder Buy-Fill erzeugt genau ein TradeLot.
    """
    id: str
    created_from_fill_id: str  # Referenz zum LedgerEvent
    created_at: datetime

    qty_base_initial: Decimal  # Ursprüngliche Netto-Menge (BRUTTO minus Base-Fee)
    qty_base_open: Decimal  # Aktuell offene Menge

    cost_quote: Decimal  # Gesamtkosten in Quote-Currency (inkl. Fees)

    status: LotStatus = LotStatus.OPEN
    target_margin_pct: Optional[Decimal] = None  # Lot-spezifische Zielmarge
    symbol: str = "BTCEUR"  # Trading Pair

    @property
    def break_even(self) -> Decimal:
        """Break-even Preis pro Base-Asset"""
        if self.qty_base_initial == 0:
            return Decimal("0")
        return self.cost_quote / self.qty_base_initial

    def unrealized_pnl(self, market_price: Decimal) -> Decimal:
        """Unrealisierte P&L in Quote-Currency"""
        return (market_price * self.qty_base_open) - (self.break_even * self.qty_base_open)

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
    realized_pnl_quote: Decimal  # Realisierte P&L in Quote-Currency
    created_at: datetime


@dataclass
class PairingItem:
    """
    Ein Item in einem Pairing

    Kann ein ganzes Lot oder eine Teilmenge sein.
    """
    lot_id: str
    qty_base: Decimal  # Wie viel Base-Asset von diesem Lot im Pairing
    cost_quote: Decimal  # Anteilige Kosten in Quote-Currency


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
    symbol: str = "BTCEUR"  # Trading Pair

    def net_cost(self) -> Decimal:
        """Netto-Kosten aller Items"""
        return sum((item.cost_quote for item in self.items), Decimal("0"))

    def net_qty_base(self) -> Decimal:
        """Netto-Base-Menge aller Items"""
        return sum((item.qty_base for item in self.items), Decimal("0"))

    def net_value(self, market_price: Decimal) -> Decimal:
        """Netto-Marktwert"""
        return self.net_qty_base() * market_price

    def net_pnl(self, market_price: Decimal) -> Decimal:
        """Netto-P&L in Quote-Currency"""
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
    total_base_to_sell: Decimal
    expected_proceeds_quote: Decimal  # Nach Fees
    expected_costs_quote: Decimal
    expected_realized_pnl_quote: Decimal

    # Auswirkungen
    affected_lots: List[dict]  # Welche Lots werden geschlossen/teilweise geschlossen
    remaining_portfolio_base: Decimal
    remaining_portfolio_cost_quote: Decimal

    # Fees
    estimated_fee_quote: Decimal
    fee_pct: Decimal  # z.B. 0.001 für 0.1%


@dataclass
class DailyPerformance:
    """Tages-Performance — berechnet aus Ledger-Events (Vergleich Tagesbeginn vs. jetzt)."""
    date: datetime

    # Realized P&L today (from sells)
    realized_pnl_today_quote: Decimal

    # Today's buys
    buys_count_today: int
    buys_volume_base_today: Decimal
    buys_volume_quote_today: Decimal

    # Today's sells
    sells_count_today: int
    sells_volume_base_today: Decimal
    sells_volume_quote_today: Decimal

    # Unrealized P&L change
    unrealized_pnl_start_of_day_quote: Decimal
    unrealized_pnl_current_quote: Decimal

    @property
    def unrealized_pnl_change_quote(self) -> Decimal:
        return self.unrealized_pnl_current_quote - self.unrealized_pnl_start_of_day_quote


@dataclass
class PortfolioState:
    """
    Portfolio-Zustand zu einem Zeitpunkt

    Wird aus Ledger berechnet (nicht persistiert).
    """
    timestamp: datetime

    # Base-Asset Position
    base_qty: Decimal  # Gesamte Base-Asset-Menge
    base_cost_basis_quote: Decimal  # Gesamtkosten in Quote-Currency

    # Quote-Currency Cash
    quote_available: Decimal  # Verfuegbare Quote-Currency

    # P&L
    realized_pnl_quote: Decimal  # Realisierte Gewinne/Verluste in Quote-Currency

    # External Cashflows
    external_net_quote: Decimal  # Summe externe Ein-/Auszahlungen in Quote-Currency

    @property
    def break_even(self) -> Optional[Decimal]:
        """Portfolio Break-even Preis"""
        if self.base_qty == 0:
            return None
        return self.base_cost_basis_quote / self.base_qty

    def market_value_quote(self, market_price: Decimal) -> Decimal:
        """Marktwert des Base-Asset-Bestands in Quote-Currency"""
        return self.base_qty * market_price

    def unrealized_pnl_quote(self, market_price: Decimal) -> Decimal:
        """Unrealisierte P&L in Quote-Currency"""
        return self.market_value_quote(market_price) - self.base_cost_basis_quote

    def target_price(self, target_margin_pct: Decimal, fee_buffer_pct: Decimal = Decimal("0")) -> Optional[Decimal]:
        """Zielverkaufspreis basierend auf Break-even und Zielmarge"""
        if self.break_even is None:
            return None
        return self.break_even * (Decimal("1") + target_margin_pct) * (Decimal("1") + fee_buffer_pct)
