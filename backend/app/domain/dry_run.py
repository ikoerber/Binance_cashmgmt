"""Pure domain logic for dry-run virtual portfolio. No I/O.

All financial calculations use Decimal exclusively. Functions are pure
(no DB access, no network calls, no service imports). Position sizing
matches the backtest engine cost model.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VirtualPosition:
    """An open virtual position held in the dry-run portfolio."""

    symbol: str
    qty: Decimal
    entry_price: Decimal  # After slippage
    entry_time: datetime
    fees_paid: Decimal
    decision_id: Optional[str] = None  # Reference to DryRunDecisionDB.id


@dataclass
class VirtualPortfolioState:
    """Snapshot of virtual portfolio at a point in time."""

    cash: Decimal
    positions: List[VirtualPosition]
    total_equity: Decimal  # cash + sum(position mark-to-market)
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    trade_count: int
    win_count: int


@dataclass
class VirtualTradeResult:
    """Result of executing a virtual buy or sell."""

    new_cash: Decimal
    new_position: Optional[
        VirtualPosition
    ]  # For buy: the new position. For sell: None.
    realized_pnl: Optional[Decimal]  # For sell: the P&L. For buy: None.
    is_win: Optional[bool]  # For sell: whether P&L > 0. For buy: None.
    effective_price: Decimal  # Price after slippage
    fee: Decimal
    qty: Decimal


@dataclass
class DecisionContext:
    """Full context for a dry-run decision, to be persisted."""

    symbol: str
    action: str  # "BUY" | "SELL" | "HOLD" | "NO_SIGNAL"
    reason: str  # Human-readable
    alpha_score: Decimal
    trade_signal: str  # "LONG" | "SHORT" | "NEUTRAL"
    threshold: Decimal
    quality: str
    factor_scores: List[dict]  # Serialized AlphaFactorScore list
    current_price: Decimal
    trailing_stop_level: Optional[Decimal]
    regime_label: Optional[str]
    regime_hurst: Optional[Decimal]
    evaluated_at: datetime
    # Virtual trade fields (None if action is HOLD or NO_SIGNAL)
    virtual_qty: Optional[Decimal] = None
    virtual_price: Optional[Decimal] = None  # After slippage
    virtual_fee: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def compute_position_size(
    equity: Decimal,
    fraction: Decimal,
    price: Decimal,
    fee_rate: Decimal,
) -> Decimal:
    """Compute position size as fixed fraction of equity.

    Matches the backtest engine model:
      available = equity * fraction
      cost_per_unit = price * (1 + fee_rate)
      qty = available / cost_per_unit

    Returns Decimal("0") if equity <= 0 or price <= 0.
    """
    if equity <= Decimal("0") or price <= Decimal("0"):
        return Decimal("0")

    available = equity * fraction
    cost_per_unit = price * (Decimal("1") + fee_rate)
    qty = (available / cost_per_unit).quantize(Decimal("0.00000001"))
    return qty


def execute_virtual_buy(
    cash: Decimal,
    price: Decimal,
    qty: Decimal,
    fee_rate: Decimal,
    slippage_pct: Decimal,
    symbol: str,
    timestamp: datetime,
    decision_id: Optional[str] = None,
) -> VirtualTradeResult:
    """Execute a virtual buy trade.

    Effective price = price * (1 + slippage_pct).
    Cost = qty * effective_price.
    Fee = cost * fee_rate.
    Total deduction = cost + fee.

    Raises ValueError if total deduction exceeds available cash.
    """
    effective_price = price * (Decimal("1") + slippage_pct)
    cost = qty * effective_price
    fee = cost * fee_rate
    total_deduction = cost + fee

    if total_deduction > cash:
        raise ValueError(f"Insufficient cash: need {total_deduction}, have {cash}")

    new_cash = cash - total_deduction
    new_position = VirtualPosition(
        symbol=symbol,
        qty=qty,
        entry_price=effective_price,
        entry_time=timestamp,
        fees_paid=fee,
        decision_id=decision_id,
    )

    return VirtualTradeResult(
        new_cash=new_cash,
        new_position=new_position,
        realized_pnl=None,
        is_win=None,
        effective_price=effective_price,
        fee=fee,
        qty=qty,
    )


def execute_virtual_sell(
    position: VirtualPosition,
    exit_price: Decimal,
    fee_rate: Decimal,
    slippage_pct: Decimal,
) -> VirtualTradeResult:
    """Execute a virtual sell trade (close full position).

    Effective price = exit_price * (1 - slippage_pct).
    Proceeds = position.qty * effective_price.
    Fee = proceeds * fee_rate.
    Net proceeds = proceeds - fee.
    Cost basis = position.qty * position.entry_price + position.fees_paid.
    Realized PnL = net_proceeds - cost_basis.
    """
    effective_price = exit_price * (Decimal("1") - slippage_pct)
    proceeds = position.qty * effective_price
    fee = proceeds * fee_rate
    net_proceeds = proceeds - fee
    cost_basis = position.qty * position.entry_price + position.fees_paid
    realized_pnl = net_proceeds - cost_basis
    is_win = realized_pnl > Decimal("0")

    return VirtualTradeResult(
        new_cash=net_proceeds,  # Increment to add to cash
        new_position=None,
        realized_pnl=realized_pnl,
        is_win=is_win,
        effective_price=effective_price,
        fee=fee,
        qty=position.qty,
    )


def compute_virtual_equity(
    cash: Decimal,
    positions: List[VirtualPosition],
    current_prices: Dict[str, Decimal],
) -> Tuple[Decimal, Decimal]:
    """Compute total equity and unrealized P&L.

    Returns (total_equity, unrealized_pnl).
    Total equity = cash + sum(pos.qty * current_prices[pos.symbol]).
    Unrealized PnL = sum(pos.qty * (current_price - entry_price) - fees_paid).
    """
    market_value = Decimal("0")
    unrealized_pnl = Decimal("0")

    for pos in positions:
        current_price = current_prices.get(pos.symbol, Decimal("0"))
        position_value = pos.qty * current_price
        market_value += position_value

        # Unrealized PnL per position
        unrealized_pnl += pos.qty * (current_price - pos.entry_price) - pos.fees_paid

    total_equity = cash + market_value
    return total_equity, unrealized_pnl


def should_enter_trade(
    signal: str,
    quality: str,
    has_open_position: bool,
) -> Tuple[bool, str]:
    """Determine whether to enter a new trade.

    Should enter only if:
    - signal == "LONG"
    - quality != "warmup"
    - has_open_position == False

    Returns (should_enter, reason).
    """
    if has_open_position:
        return False, "Already have an open position"

    if quality == "warmup":
        return False, "Signal quality is warmup, skipping entry"

    if signal != "LONG":
        return False, f"Signal is {signal}, not LONG"

    return True, "LONG signal with sufficient quality, no open position"


def should_exit_trade(
    candle_low: Decimal,
    trailing_stop_level: Optional[Decimal],
) -> Tuple[bool, str]:
    """Determine whether to exit an existing trade via trailing stop.

    Should exit if trailing_stop_level is not None and candle_low <= trailing_stop_level.

    Returns (should_exit, reason).
    """
    if trailing_stop_level is None:
        return False, "No trailing stop level set"

    if candle_low <= trailing_stop_level:
        return (
            True,
            f"Candle low {candle_low} hit trailing stop at {trailing_stop_level}",
        )

    return False, f"Candle low {candle_low} above trailing stop {trailing_stop_level}"


def determine_action(
    signal: str,
    quality: str,
    has_open_position: bool,
    candle_low: Optional[Decimal],
    trailing_stop_level: Optional[Decimal],
) -> Tuple[str, str]:
    """Orchestrating function to determine the dry-run action.

    Checks exit first (if position open), then entry.
    Actions: "BUY", "SELL", "HOLD", "NO_SIGNAL".

    Returns (action, reason).
    """
    # Check exit first if we have an open position
    if has_open_position and candle_low is not None:
        should_sell, sell_reason = should_exit_trade(candle_low, trailing_stop_level)
        if should_sell:
            return "SELL", sell_reason

    # Check entry
    should_buy, buy_reason = should_enter_trade(signal, quality, has_open_position)
    if should_buy:
        return "BUY", buy_reason

    # Determine if it's HOLD (we have context) or NO_SIGNAL (quality too low)
    if quality == "warmup":
        return "NO_SIGNAL", buy_reason

    if has_open_position:
        return "HOLD", "Position open, no exit signal triggered"

    return "HOLD", buy_reason
