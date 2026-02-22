"""SQLAlchemy Database Models"""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    Column,
    String,
    DateTime,
    Numeric,
    Enum as SQLEnum,
    ForeignKey,
    Text,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


def _utcnow():
    """Naive UTC now for SQLAlchemy defaults."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Enums
class EventTypeEnum(str, enum.Enum):
    TRADE_FILL = "TRADE_FILL"
    FEE = "FEE"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    EXTERNAL_CASHFLOW = "EXTERNAL_CASHFLOW"
    ADJUSTMENT = "ADJUSTMENT"


class EventSourceEnum(str, enum.Enum):
    BINANCE = "BINANCE"
    EXTERNAL = "EXTERNAL"
    ADJUSTMENT = "ADJUSTMENT"


class TradeSideEnum(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class LotStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    PARTIAL_CLOSED = "PARTIAL_CLOSED"
    CLOSED = "CLOSED"
    MERGED = "MERGED"


class OrderStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PairingStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    EXECUTED = "EXECUTED"


# Models
class User(Base):
    """Benutzer"""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    # Relationships
    api_credentials = relationship(
        "APICredential", back_populates="user", cascade="all, delete-orphan"
    )
    ledger_events = relationship(
        "LedgerEventDB", back_populates="user", cascade="all, delete-orphan"
    )
    trade_lots = relationship(
        "TradeLotDB", back_populates="user", cascade="all, delete-orphan"
    )
    orders = relationship(
        "OrderDB", back_populates="user", cascade="all, delete-orphan"
    )
    pairings = relationship(
        "PairingDB", back_populates="user", cascade="all, delete-orphan"
    )
    reconciliation_runs = relationship(
        "ReconciliationRunDB", back_populates="user", cascade="all, delete-orphan"
    )
    alert_events = relationship(
        "AlertEventDB", back_populates="user", cascade="all, delete-orphan"
    )


class APICredential(Base):
    """Binance API Credentials (verschlüsselt)"""

    __tablename__ = "api_credentials"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Encrypted/Hashed values (niemals Klartext!)
    api_key_encrypted = Column(String, nullable=False)
    api_secret_encrypted = Column(String, nullable=False)

    testnet = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="api_credentials")


class LedgerEventDB(Base):
    """
    Ledger Event - Append-only Event Log

    Mapping von domain.models.LedgerEvent zu DB
    """

    __tablename__ = "ledger_events"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    type = Column(SQLEnum(EventTypeEnum), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)

    asset = Column(String, nullable=False)  # "BTC", "EUR", "BNB"
    amount = Column(
        Numeric(precision=20, scale=10), nullable=False
    )  # Decimal mit Präzision

    # Optional fields
    symbol = Column(String, nullable=True)  # z.B. "BTCEUR"
    price = Column(Numeric(precision=20, scale=10), nullable=True)
    side = Column(SQLEnum(TradeSideEnum), nullable=True)

    fee_asset = Column(String, nullable=True)
    fee_amount = Column(Numeric(precision=20, scale=10), nullable=True)
    fee_quote_value = Column(
        Numeric(precision=20, scale=10), nullable=True
    )  # Vorberechneter Quote-Asset-Wert der Fee

    source = Column(SQLEnum(EventSourceEnum), nullable=False)
    source_id = Column(String, nullable=True, index=True)  # Binance tradeId/orderId

    note = Column(Text, nullable=True)
    raw_payload = Column(JSON, nullable=True)  # Original Binance Response

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="ledger_events")

    # Indexes für Performance
    __table_args__ = (
        Index("idx_ledger_user_timestamp", "user_id", "timestamp"),
        Index("idx_ledger_source_id", "source_id"),
    )


class TradeLotDB(Base):
    """
    TradeLot - Base-Asset Position

    1 Fill = 1 Lot
    """

    __tablename__ = "trade_lots"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    symbol = Column(String, nullable=False, server_default="BTCEUR")

    created_from_fill_id = Column(
        String, ForeignKey("ledger_events.id"), nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    qty_base_initial = Column(Numeric(precision=20, scale=10), nullable=False)
    qty_base_open = Column(Numeric(precision=20, scale=10), nullable=False)

    cost_quote = Column(
        Numeric(precision=20, scale=10), nullable=False
    )  # Kosten in Quote-Asset
    cost_eur = Column(
        Numeric(precision=20, scale=10), nullable=True
    )  # EUR-equivalent Kosten (None = needs backfill)
    quote_to_eur_rate = Column(
        Numeric(precision=20, scale=10), nullable=True
    )  # Konvertierungsrate zum Fill-Zeitpunkt

    status = Column(SQLEnum(LotStatusEnum), nullable=False, default=LotStatusEnum.OPEN)
    target_margin_pct = Column(Numeric(precision=10, scale=6), nullable=True)
    auto_order_enabled = Column(Boolean, default=False, nullable=False)

    # Merge-Tracking (Soft-Delete)
    merged_into_lot_id = Column(String, ForeignKey("trade_lots.id"), nullable=True)
    merged_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="trade_lots")
    sell_allocations = relationship(
        "SellAllocationDB", back_populates="trade_lot", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_lots_user_symbol_status", "user_id", "symbol", "status"),
    )


class SellAllocationDB(Base):
    """
    Sell Allocation - FIFO Zuordnung

    Persistiert: Welcher Sell-Fill schließt welches Lot.
    """

    __tablename__ = "sell_allocations"

    id = Column(String, primary_key=True)

    sell_fill_id = Column(String, ForeignKey("ledger_events.id"), nullable=False)
    trade_lot_id = Column(String, ForeignKey("trade_lots.id"), nullable=False)

    qty_allocated = Column(Numeric(precision=20, scale=10), nullable=False)
    realized_pnl_quote = Column(
        Numeric(precision=20, scale=10), nullable=False
    )  # Realisierte P&L in Quote-Asset
    realized_pnl_eur = Column(
        Numeric(precision=20, scale=10), nullable=True
    )  # EUR-normalized P&L (for cross-pair allocations)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    # Relationships
    trade_lot = relationship("TradeLotDB", back_populates="sell_allocations")

    # Indexes
    __table_args__ = (
        Index("idx_allocations_sell_fill", "sell_fill_id"),
        Index("idx_allocations_lot", "trade_lot_id"),
    )


class OrderDB(Base):
    """
    Order - Order State Tracking

    Trackt alle Orders (manuell & automatisch) mit vollständigem Lifecycle.
    """

    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Order Identifiers (idempotency via client_order_id)
    client_order_id = Column(String, unique=True, nullable=False, index=True)
    binance_order_id = Column(String, nullable=True, index=True)

    # Order Details
    symbol = Column(String, nullable=False)  # "BTCEUR"
    side = Column(SQLEnum(TradeSideEnum), nullable=False)  # BUY/SELL
    type = Column(String, nullable=False)  # "LIMIT", "MARKET", "STOP_LIMIT"
    quantity = Column(Numeric(precision=20, scale=10), nullable=False)
    price = Column(
        Numeric(precision=20, scale=10), nullable=True
    )  # NULL for MARKET orders
    stop_price = Column(
        Numeric(precision=20, scale=10), nullable=True
    )  # Trigger price for TAKE_PROFIT_LIMIT

    status = Column(
        SQLEnum(OrderStatusEnum), nullable=False, default=OrderStatusEnum.PENDING
    )

    # Linked Resources (optional)
    linked_lot_id = Column(String, ForeignKey("trade_lots.id"), nullable=True)
    linked_pairing_id = Column(String, ForeignKey("pairings.id"), nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Raw Binance response
    raw_response = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="orders")
    trade_lot = relationship("TradeLotDB", foreign_keys=[linked_lot_id])
    pairing = relationship("PairingDB", foreign_keys=[linked_pairing_id])

    # Indexes
    __table_args__ = (
        Index("idx_orders_user_status", "user_id", "status"),
        Index("idx_orders_binance_id", "binance_order_id"),
    )


class PairingDB(Base):
    """
    Pairing - Virtuelle Trade-Verrechnung

    Gruppiert Gewinner- und Verlierer-Lots für Netto-P&L-Ziele.
    """

    __tablename__ = "pairings"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    symbol = Column(String, nullable=False, server_default="BTCEUR")
    base_asset = Column(
        String, nullable=True
    )  # Base-Asset fuer Cross-Pair (z.B. "XRP"), NULL fuer Single-Pair

    threshold_pct = Column(
        Numeric(precision=10, scale=6), nullable=False
    )  # z.B. 0.05 für 5%
    status = Column(
        SQLEnum(PairingStatusEnum), nullable=False, default=PairingStatusEnum.DRAFT
    )

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    locked_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    routing_decision_json = Column(
        JSON, nullable=True
    )  # Routing audit: selected route, prices, EUR proceeds, delta

    # Relationships
    user = relationship("User", back_populates="pairings")
    items = relationship(
        "PairingItemDB", back_populates="pairing", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (Index("idx_pairings_user_status", "user_id", "status"),)


class PairingItemDB(Base):
    """
    Pairing Item - Einzelne Lots in einem Pairing

    N:M Beziehung zwischen Pairings und TradeLots.
    """

    __tablename__ = "pairing_items"

    id = Column(String, primary_key=True)
    pairing_id = Column(String, ForeignKey("pairings.id"), nullable=False)
    lot_id = Column(String, ForeignKey("trade_lots.id"), nullable=False)

    qty_base = Column(Numeric(precision=20, scale=10), nullable=False)
    cost_quote = Column(
        Numeric(precision=20, scale=10), nullable=False
    )  # Kosten in Quote-Asset
    cost_eur = Column(
        Numeric(precision=20, scale=10), nullable=True
    )  # EUR-normalisierte Kosten (fuer Cross-Pair)
    lot_symbol = Column(
        String, nullable=True
    )  # Pair-of-origin (z.B. "XRPEUR" oder "XRPBTC")

    # Relationships
    pairing = relationship("PairingDB", back_populates="items")
    trade_lot = relationship("TradeLotDB")

    # Indexes
    __table_args__ = (
        Index("idx_pairing_items_pairing", "pairing_id"),
        Index("idx_pairing_items_lot", "lot_id"),
    )


class OBDirectionEnum(str, enum.Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class OBStateEnum(str, enum.Enum):
    UNMITIGATED = "UNMITIGATED"
    MITIGATED = "MITIGATED"
    INVALID = "INVALID"


class OBConvictionEnum(str, enum.Enum):
    """Deprecated: Conviction wird jetzt als String gespeichert (4-stufig)."""

    LOW = "LOW"
    STANDARD = "STANDARD"
    HIGH = "HIGH"
    INSTITUTIONAL = "INSTITUTIONAL"


class OrderblockZoneDB(Base):
    """
    Orderblock Zone - Erkannte institutionelle Preiszone.

    Persistiert Detection-Ergebnisse inkl. State-Transitionen.
    """

    __tablename__ = "orderblock_zones"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    symbol = Column(String, nullable=False)
    interval = Column(String, nullable=False)

    direction = Column(SQLEnum(OBDirectionEnum), nullable=False)
    state = Column(SQLEnum(OBStateEnum), nullable=False)
    conviction = Column(String, nullable=False)

    zone_top = Column(Numeric(precision=20, scale=10), nullable=False)
    zone_bottom = Column(Numeric(precision=20, scale=10), nullable=False)
    equilibrium = Column(Numeric(precision=20, scale=10), nullable=False)
    entry_edge = Column(Numeric(precision=20, scale=10), nullable=False)
    stop_edge = Column(Numeric(precision=20, scale=10), nullable=False)

    formed_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=False)
    mitigated_at = Column(DateTime, nullable=True)
    invalidated_at = Column(DateTime, nullable=True)

    volume_zscore = Column(Numeric(precision=10, scale=4), nullable=False)
    volume_weight = Column(Numeric(precision=10, scale=4), nullable=False)
    volume_percentile = Column(Numeric(precision=10, scale=4), nullable=True)
    ofi_divergence = Column(Numeric(precision=20, scale=10), nullable=True)
    impact_efficiency_ratio = Column(Numeric(precision=20, scale=10), nullable=True)
    conviction_score = Column(Numeric(precision=10, scale=4), nullable=True)
    is_high_conviction_zscore = Column(Boolean, nullable=False, server_default="0")
    category = Column(String, nullable=True, server_default="UNCLASSIFIED")

    # Liquidity Sweep
    has_liquidity_sweep = Column(Boolean, nullable=False, server_default="0")
    liquidity_sweep_level = Column(Numeric(precision=20, scale=10), nullable=True)

    # Sentiment Confluence
    sentiment_at_detection = Column(Numeric(precision=10, scale=4), nullable=True)
    confluence_label = Column(String, nullable=True)
    confluence_score = Column(Numeric(precision=10, scale=4), nullable=True)

    atr_at_formation = Column(Numeric(precision=20, scale=10), nullable=False)
    displacement_range = Column(Numeric(precision=20, scale=10), nullable=False)
    bos_swing_price = Column(Numeric(precision=20, scale=10), nullable=False)

    config_json = Column(JSON, nullable=False)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("idx_ob_zones_user_symbol_interval", "user_id", "symbol", "interval"),
        Index("idx_ob_zones_user_state", "user_id", "state"),
        Index("idx_ob_zones_formed_at", "formed_at"),
    )


class BacktestRunDB(Base):
    """
    Backtest Run - Persistiertes Backtest-Ergebnis.

    Speichert Konfiguration, Metriken und einzelne Trades als JSON.
    """

    __tablename__ = "backtest_runs"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    symbol = Column(String, nullable=False)
    interval = Column(String, nullable=False)

    data_start = Column(DateTime, nullable=False)
    data_end = Column(DateTime, nullable=False)
    candle_count = Column(Numeric(precision=10, scale=0), nullable=False)

    total_zones = Column(Numeric(precision=10, scale=0), nullable=False)
    total_trades = Column(Numeric(precision=10, scale=0), nullable=False)
    hits = Column(Numeric(precision=10, scale=0), nullable=False)
    misses = Column(Numeric(precision=10, scale=0), nullable=False)
    hit_rate = Column(Numeric(precision=10, scale=4), nullable=True)

    avg_penetration_depth_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    avg_holding_duration_candles = Column(Numeric(precision=10, scale=4), nullable=True)

    high_conviction_count = Column(Numeric(precision=10, scale=0), nullable=True)
    high_conviction_hit_rate = Column(Numeric(precision=10, scale=4), nullable=True)
    expired_trades = Column(
        Numeric(precision=10, scale=0), nullable=True, server_default="0"
    )
    max_holding_candles = Column(Numeric(precision=10, scale=0), nullable=True)

    config_json = Column(JSON, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    trades_json = Column(JSON, nullable=False)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (Index("idx_backtest_user_symbol", "user_id", "symbol"),)


class UserSettingsDB(Base):
    """
    User Settings - Konfigurierbare Parameter pro User

    Erweiterbar fuer zukuenftige Settings (z.B. target_margin_pct, fee_buffer_pct).
    """

    __tablename__ = "user_settings"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)

    max_order_value_eur = Column(
        Numeric(precision=20, scale=2), nullable=False, server_default="1000"
    )
    macro_signal_interval = Column(String, nullable=False, server_default="15")
    sell_allocation_strategy = Column(String, nullable=False, server_default="FIFO")

    # Orderblock Detection Settings
    ob_interval = Column(String, nullable=True)
    ob_atr_multiplier = Column(Numeric(precision=10, scale=4), nullable=True)
    ob_target_rr = Column(Numeric(precision=10, scale=4), nullable=True)
    ob_impulse_window = Column(Numeric(precision=5, scale=0), nullable=True)

    # Reconciliation Thresholds
    recon_tolerance_base = Column(
        Numeric(precision=20, scale=8), nullable=True
    )  # Default handled in service: Decimal("0.0001")
    recon_tolerance_quote = Column(
        Numeric(precision=20, scale=2), nullable=True
    )  # Default handled in service: Decimal("1.00")

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User")


class ReconciliationRunDB(Base):
    """
    Reconciliation Run - Persistiertes Reconciliation-Ergebnis

    Speichert Trigger, Status, vollstaendigen Report und Diskrepanz-Flag.
    """

    __tablename__ = "reconciliation_runs"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    symbol = Column(String, nullable=False)  # z.B. "BTCEUR"
    trigger = Column(
        String, nullable=False
    )  # "manual", "post_sync", "post_full_sync"
    status = Column(String, nullable=False)  # "completed", "partial", "failed"

    report_json = Column(JSON, nullable=False)  # Full reconciliation report dict
    has_discrepancies = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="reconciliation_runs")
    alert_events = relationship(
        "AlertEventDB",
        back_populates="reconciliation_run",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("idx_recon_runs_user_created", "user_id", "created_at"),
    )


class AlertEventDB(Base):
    """
    Alert Event - Persistierter Alert fuer Diskrepanzen und Fehler

    Wird aus Reconciliation-Ergebnissen generiert wenn Thresholds ueberschritten werden.
    """

    __tablename__ = "alert_events"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    reconciliation_run_id = Column(
        String, ForeignKey("reconciliation_runs.id"), nullable=True
    )  # Alerts can exist without a run in future

    alert_type = Column(
        String, nullable=False
    )  # "BALANCE_DISCREPANCY", "ORDER_DISCREPANCY", "SYNC_ERROR", "BALANCE_CHECK_ERROR"
    severity = Column(String, nullable=False)  # "info", "warning", "critical"
    title = Column(String, nullable=False)  # Short human-readable title

    details_json = Column(
        JSON, nullable=True
    )  # Structured details: asset, expected, actual, diff, threshold

    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="alert_events")
    reconciliation_run = relationship(
        "ReconciliationRunDB", back_populates="alert_events"
    )

    # Indexes
    __table_args__ = (
        Index("idx_alerts_user_ack", "user_id", "acknowledged"),
        Index("idx_alerts_user_created", "user_id", "created_at"),
    )
