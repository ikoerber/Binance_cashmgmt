# Phase 16: Dry-Run Mode + Bot Dashboard - Research

**Researched:** 2026-02-27
**Domain:** Real-time paper trading engine, virtual portfolio, Bot navigation UI
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Signal logging detail level**: Full factor breakdown per entry -- all 4 Alpha Score factors with individual scores, composite Alpha Score, trailing stop levels, current price, action taken (BUY/HOLD/SELL/NO_SIGNAL), and reason text
- **Evaluation frequency**: Every candle close matching the Alpha Score interval (e.g. every 15m). Produces ~96 entries/day at 15m interval.
- **Retention**: 30 days rolling, auto-purge older entries
- **Display**: Filterable table (columns: time, action, Alpha Score, price, reason) with date range, action type, symbol filters. Above it: time-series chart showing Alpha Score over time with buy/sell markers.
- **Virtual portfolio initial capital**: Configurable by user in Settings (same pattern as backtest initial capital). Can be reset anytime.
- **Cost model**: Reuse backtest fee rate (default 0.1%) and slippage (default 0.05%) from Phase 15. Consistent with backtest results for fair comparison.
- **Position sizing**: Fixed fraction of virtual equity per trade (compounding) -- same model as backtest engine
- **Reset**: Reset button in Bot section with confirmation dialog. Wipes virtual positions and P&L. Decision log stays (separate concern).
- **Toggle location**: Prominent toggle at the top of the Bot Dashboard header. Always visible when in Bot view.
- **Confirmation**: No confirmation dialog needed -- dry-run is a safe mode that never places real orders. Simple toggle on/off.
- **Active indicators**: Persistent amber banner at top of Bot section: "DRY-RUN MODE -- No real orders". Plus a small badge on the Bot nav item when active.
- **Structural enforcement (DRY-05)**: Dry-run service has NO import/reference to order-placing code. Bot Dashboard has no "Place Order" buttons. The structural guarantee is invisible -- there's simply nothing to click.
- **Bot Dashboard visual hierarchy**: Hero section at top with large Alpha Score display + factor bars + dry-run status toggle/banner. Middle: Signal history chart (time series). Bottom: KPI cards (virtual P&L, trade count, win rate, last backtest summary, regime indicator).
- **Factor bars**: Horizontal bars with labels for each of the 4 factors (Z-Score, Lead-Lag, Orderbook, Funding). Similar to sentiment pillar bars in Combined Score page.
- **Navigation**: 4 nav groups -- Trading (Dashboard, Lots) / Analyse (Combined Score, Orderblocks, Backtest) / Bot (Bot Dashboard, Decision Log) / Admin (Reconciliation, Settings, API Docs)
- **Real-time updates**: WebSocket for Alpha Score, virtual P&L, and dry-run status. Signal history chart updates when new decisions are logged.
- Factor bars should follow the same visual pattern as sentiment pillar bars in the existing Combined Score page
- 4-group navigation restructure (Trading/Analyse/Bot/Admin) aligns with the roadmap's "4th area" specification
- Virtual portfolio must stay completely isolated from production ledger -- separate DB tables, never appear on main Dashboard

### Claude's Discretion
- Regime indicator visual design (badge, icon, or chart annotation)
- Backtest summary widget format (which metrics to surface from most recent run)
- Decision log expandable row design (how factor details are shown on drill-down)
- Color scheme for Bot section (existing app palette or distinct accent)
- Signal history chart type (line chart vs. area chart vs. candlestick background)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DRY-01 | User can activate dry-run mode that computes real-time signals without placing actual orders | DryRunService singleton with evaluation loop triggered by candle close; user_settings column for dry_run_enabled; WebSocket broadcast for status changes |
| DRY-02 | Dry-run logs every decision with full context (all 4 factor scores, Alpha Score, trailing stop levels, prices, action, reason) | DryRunDecisionDB table with factor_json blob + queryable action/score columns; logged at each candle close evaluation |
| DRY-03 | Dry-run tracks virtual portfolio (positions, P&L) in separate tables from production ledger | DryRunPortfolioDB + DryRunPositionDB tables (completely separate from ledger_events/trade_lots); virtual equity computed from positions + cash |
| DRY-04 | User can view dry-run decision log with filtering (date range, action type, symbol) | GET /api/dry-run/{user_id}/decisions endpoint with query params; frontend DecisionLog component with table + filters |
| DRY-05 | Dry-run mode has NO access to order-placing functionality (structural prevention, not flag-based) | DryRunService in separate module with no imports from order_service, binance.py, or order_tracking_service; verified by import analysis |
| BOT-01 | New "Bot" section in navigation (4th area: Trading/Analyse/Bot/Admin) | SymbolLayout sub-nav restructured into 4 groups; GlobalNav adds Bot pill for standalone routes |
| BOT-02 | Bot dashboard shows current Alpha Score with factor breakdown (visual bars per factor) | Reuses existing GET /api/alpha-score/{user_id}/score; factor bars with horizontal progress pattern from CombinedScore pillar bars |
| BOT-03 | Bot dashboard shows signal history (recent Alpha Score values over time, chart) | GET /api/dry-run/{user_id}/decisions returns time-series data; Recharts LineChart with buy/sell markers |
| BOT-04 | Bot dashboard shows dry-run status (active/inactive, current virtual positions, virtual P&L) | GET /api/dry-run/{user_id}/status returns is_active, positions, virtual_pnl; WebSocket dry_run_update messages |
| BOT-05 | Bot dashboard shows backtest results (most recent run summary, link to full history) | Reuses existing GET /api/backtest/{user_id}/runs (limit=1, sort=latest); surfaces key metrics (net return, Sharpe, trade count, win rate) |
| BOT-06 | Bot dashboard shows regime indicator (trending/mean-reverting with confidence) | Already returned in Alpha Score response (regime.label, regime.confidence, regime.hurst); render as styled badge |
</phase_requirements>

## Summary

Phase 16 adds a real-time paper trading mode (dry-run) and a dedicated Bot Dashboard to the application. The dry-run engine evaluates Alpha Score signals at each candle close, logs every decision with full factor context, and manages a virtual portfolio with positions and P&L -- all completely isolated from the production ledger and order-placing infrastructure. The Bot Dashboard provides a unified view into the scoring engine's operation, combining live Alpha Score display, signal history, virtual portfolio status, backtest results, and regime information.

The core architectural challenge is **structural isolation** (DRY-05): the dry-run service must have zero import paths to order-placing code. This is achieved by creating a standalone `DryRunService` in a new module that only imports from the alpha_score domain and data service, never from order_service, binance.py, or order_tracking_service. The service evaluates signals using the existing `AlphaScoreDataService.get_alpha_score()` method and applies the backtest engine's position sizing and cost model for virtual trades.

The second challenge is **real-time evaluation at candle close**. The dry-run engine needs a timer/scheduler that fires at each interval boundary (e.g., every 15 minutes at :00, :15, :30, :45). This is implemented as an asyncio background task in the FastAPI lifespan, similar to the existing WebSocket stream manager pattern.

**Primary recommendation:** Build the DryRunService as a completely standalone module with its own DB tables (DryRunDecisionDB, DryRunPortfolioDB, DryRunPositionDB), its own API route module, and its own WebSocket message types. Never import from order-related modules. Reuse the existing Alpha Score computation and backtest cost model through their public interfaces only.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | API routes for dry-run endpoints | Already in stack |
| SQLAlchemy 2 | existing | DryRunDecisionDB, DryRunPortfolioDB, DryRunPositionDB tables | Already in stack |
| Alembic | existing | Migration for new tables (render_as_batch=True for SQLite) | Already in stack |
| React 19 | existing | Bot Dashboard, Decision Log frontend components | Already in stack |
| TanStack Query | existing | Data fetching with refetchInterval for live updates | Already in stack |
| Recharts | existing | Signal history chart (LineChart with markers) | Already in stack |
| WebSocket | existing | Real-time dry-run status and decision broadcasts | Already in stack (aiohttp + native WS) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Background task for candle-close evaluation loop | DryRunService scheduler |
| Decimal | stdlib | All virtual portfolio calculations | Same pattern as backtest engine |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncio background task | Celery/Redis worker | Overkill for single timer; Redis not yet deployed. asyncio task matches existing WebSocket pattern |
| Separate DB tables | JSON blobs on existing tables | Violates isolation requirement; separate tables ensure no contamination |
| Polling for signal history | Server-Sent Events (SSE) | WebSocket already established; SSE would add complexity for no gain |

**Installation:**
No new packages needed. All dependencies already in stack.

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── app/
│   ├── domain/
│   │   └── dry_run.py             # Pure domain: virtual position management, P&L calculation
│   ├── services/
│   │   └── dry_run_service.py     # DryRunService singleton: evaluation loop, virtual trades, persistence
│   ├── api/
│   │   └── routes/
│   │       └── dry_run.py         # API endpoints: status, decisions, portfolio, reset, toggle
│   └── db/
│       └── models.py              # +DryRunDecisionDB, +DryRunPortfolioDB, +DryRunPositionDB

frontend/
├── src/
│   ├── components/
│   │   ├── BotDashboard.jsx       # Hero score display, factor bars, signal chart, KPI cards
│   │   ├── BotDashboard.css
│   │   ├── DecisionLog.jsx        # Filterable decision table with expandable rows
│   │   └── DecisionLog.css
│   ├── api/
│   │   └── client.js              # +dry-run API functions
│   └── components/
│       ├── SymbolLayout.jsx       # Modified: 4 nav groups
│       └── GlobalNav.jsx          # Modified: Bot section links
```

### Pattern 1: Structural Isolation (DRY-05)
**What:** DryRunService must never import from order-placing modules.
**When to use:** Any module that handles paper trading / dry-run logic.
**Example:**
```python
# dry_run_service.py -- ALLOWED imports
from app.domain.alpha_score import AlphaScoreResult, AlphaFactorScore, RegimeInfo
from app.services.alpha_score_data_service import get_alpha_score_data_service
from app.db.models import DryRunDecisionDB, DryRunPortfolioDB, DryRunPositionDB, UserSettingsDB

# NEVER import these (structural guarantee):
# from app.services.order_service import OrderService       # FORBIDDEN
# from app.services.binance import BinanceService           # FORBIDDEN
# from app.services.order_tracking_service import ...       # FORBIDDEN
```
**Enforcement:** Code review + grep-based CI check: `grep -r "order_service\|binance\.py\|order_tracking" app/services/dry_run_service.py` must return empty.

### Pattern 2: Candle-Close Evaluation Loop
**What:** Background asyncio task that fires signal evaluation at interval boundaries.
**When to use:** DryRunService needs to evaluate at each candle close.
**Example:**
```python
async def _evaluation_loop(self):
    """Runs in FastAPI lifespan background task."""
    while self._running:
        now = datetime.now(timezone.utc)
        interval_seconds = self._interval_seconds  # e.g., 900 for 15m
        # Calculate seconds until next interval boundary
        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
        next_boundary = ((seconds_since_midnight // interval_seconds) + 1) * interval_seconds
        sleep_seconds = next_boundary - seconds_since_midnight
        await asyncio.sleep(sleep_seconds)

        if not self._active:
            continue  # Skip evaluation when dry-run is off

        try:
            await self._evaluate_and_log()
        except Exception as e:
            logger.error("Dry-run evaluation failed: %s", e)
```
This follows the same pattern as `BinanceStreamManager._price_stream_loop()` -- an async while-loop started as a task in the lifespan.

### Pattern 3: Virtual Portfolio as Pure Domain
**What:** Virtual position tracking and P&L calculation as pure functions (no I/O), matching the backtest engine pattern.
**When to use:** Computing virtual equity, position sizing, trade P&L.
**Example:**
```python
# domain/dry_run.py (pure, no I/O)
@dataclass
class VirtualPosition:
    symbol: str
    qty: Decimal
    entry_price: Decimal
    entry_time: datetime
    fees_paid: Decimal

@dataclass
class VirtualPortfolio:
    cash: Decimal
    positions: List[VirtualPosition]
    total_equity: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    trade_count: int
    win_count: int

def compute_position_size(equity: Decimal, fraction: Decimal, price: Decimal, fee_rate: Decimal) -> Decimal:
    """Fixed fraction of equity, same as backtest engine."""
    available = equity * fraction
    cost_per_unit = price * (Decimal("1") + fee_rate)
    return (available / cost_per_unit).quantize(Decimal("0.00000001"))

def execute_virtual_buy(portfolio: VirtualPortfolio, price: Decimal, qty: Decimal,
                        fee_rate: Decimal, slippage_pct: Decimal, timestamp: datetime) -> VirtualPortfolio:
    """Returns new portfolio state after virtual buy."""
    effective_price = price * (Decimal("1") + slippage_pct)
    cost = qty * effective_price
    fee = cost * fee_rate
    # ... returns updated portfolio
```

### Pattern 4: WebSocket Broadcast for Dry-Run Events
**What:** Broadcast dry-run decisions and status changes via existing WebSocket infrastructure.
**When to use:** When a new decision is logged or dry-run is toggled.
**Example:**
```python
# In dry_run_service.py after evaluation
async def _broadcast_decision(self, decision: dict):
    """Broadcast via existing WebSocket manager."""
    stream_manager = get_stream_manager()
    message = {
        "type": "dry_run_decision",
        "data": decision,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await stream_manager._broadcast_to_user(self._user_id, message)
```
The existing WebSocket infrastructure (`BinanceStreamManager._broadcast_to_user`) already handles multi-client broadcast with disconnection cleanup. Add new message types: `dry_run_decision`, `dry_run_status`, `dry_run_portfolio_update`.

### Pattern 5: Navigation Restructure (4 Groups)
**What:** Restructure SymbolLayout sub-nav from 3 groups to 4, and add Bot section to GlobalNav.
**When to use:** Both symbol-scoped routes (/s/:symbol/bot) and standalone routes (/bot/decisions).
**Decision:** Bot Dashboard lives at `/s/:symbol/bot` (symbol-scoped, since Alpha Score is symbol-specific). Decision Log at `/s/:symbol/bot/decisions`. This matches the existing pattern where Combined Score is at `/s/:symbol/combined`.

```jsx
// SymbolLayout.jsx sub-nav groups
<div className="subnav-group">
  <span className="subnav-group-label">Trading</span>
  <NavLink to={`/s/${symbol}/dashboard`}>Dashboard</NavLink>
  <NavLink to={`/s/${symbol}/lots`}>TradeLots</NavLink>
</div>
<div className="subnav-group">
  <span className="subnav-group-label">Analyse</span>
  <NavLink to={`/s/${symbol}/combined`}>Combined Score</NavLink>
  <NavLink to={`/s/${symbol}/orderblock`}>Orderblocks</NavLink>
</div>
<div className="subnav-group">
  <span className="subnav-group-label">Bot</span>
  <NavLink to={`/s/${symbol}/bot`}>Bot Dashboard</NavLink>
  <NavLink to={`/s/${symbol}/bot/decisions`}>Decision Log</NavLink>
</div>
<div className="subnav-group">
  <span className="subnav-group-label">Admin</span>
  <NavLink to={`/s/${symbol}/reconciliation`}>Reconciliation</NavLink>
</div>
```
Note: Backtest moves from GlobalNav to the Analyse group (symbol-scoped), and Settings/API Docs stay in GlobalNav as global items. This is a significant navigation restructure.

### Anti-Patterns to Avoid
- **Boolean flag for safety:** Do NOT add `is_dry_run: bool` to OrderService and check it before placing orders. DRY-05 requires structural prevention -- the DryRunService simply never has access to order-placing code.
- **Shared tables with production:** Do NOT add `is_virtual: bool` column to `trade_lots` or `ledger_events`. Virtual portfolio data MUST be in separate tables.
- **Polling for signal evaluation:** Do NOT use periodic REST polling from frontend to trigger evaluations. The backend evaluation loop runs autonomously on candle-close boundaries.
- **Coupling to BinanceService:** DryRunService must NEVER instantiate or reference BinanceService. All market data comes through AlphaScoreDataService (which already handles Binance API calls internally).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Position sizing math | Custom sizing logic | Reuse backtest engine's `BacktestConfig.position_fraction` model | Consistency between backtest and dry-run results |
| Fee/slippage calculation | Custom cost model | Reuse backtest's `fee_rate` + `slippage_pct` approach | Fair comparison between backtest and dry-run |
| Alpha Score computation | Duplicate factor calculations | Call `AlphaScoreDataService.get_alpha_score()` | Single source of truth, already cached |
| WebSocket broadcast | Custom WS connection | Use existing `BinanceStreamManager._broadcast_to_user()` | Already handles multi-client, cleanup, reconnection |
| Time-series charting | Custom SVG chart | Recharts LineChart (same as Backtest equity curve) | Already in stack, tested patterns available |
| Auto-purge old entries | Custom cron job | SQLAlchemy delete query in evaluation loop (after each batch) | Simpler, runs in same context as writes |

**Key insight:** The dry-run engine is essentially the backtest engine running in real-time instead of on historical data. Reuse the backtest's cost model and position sizing, but replace historical candle iteration with live Alpha Score polling.

## Common Pitfalls

### Pitfall 1: Evaluation Timer Drift
**What goes wrong:** Using `asyncio.sleep(900)` (fixed 15 minutes) causes drift -- evaluations gradually shift away from candle boundaries (e.g., :00, :15, :30, :45).
**Why it happens:** Sleep duration doesn't account for evaluation execution time or system clock jitter.
**How to avoid:** Calculate sleep duration to next interval boundary from current time, not from last evaluation. Always snap to wall-clock boundaries.
**Warning signs:** Decision log timestamps drift from exact interval boundaries (e.g., 14:15:03 instead of 14:15:00).

### Pitfall 2: Race Between Toggle and Evaluation
**What goes wrong:** User toggles dry-run off while an evaluation is in progress. Evaluation completes and logs a decision after dry-run was disabled.
**Why it happens:** Toggle and evaluation run in different async contexts.
**How to avoid:** Use an asyncio.Lock in DryRunService. The evaluation loop acquires the lock before checking `_active` and holds it through decision logging. The toggle endpoint also acquires the lock.
**Warning signs:** Decision logged with timestamp after dry-run deactivation timestamp.

### Pitfall 3: Virtual Portfolio Contaminating Production Queries
**What goes wrong:** Frontend query for "my lots" accidentally includes virtual positions.
**Why it happens:** If virtual data is in the same tables (even with a flag), ORM queries may forget the filter.
**How to avoid:** Separate tables entirely. `DryRunPositionDB` and `DryRunPortfolioDB` are completely different tables from `TradeLotDB` and `LedgerEventDB`. No shared table, no risk.
**Warning signs:** Virtual positions appearing in Dashboard, Lots view, or Portfolio KPIs.

### Pitfall 4: 30-Day Purge Deleting Active Context
**What goes wrong:** Auto-purge deletes decisions that reference still-open virtual positions.
**Why it happens:** Purge uses simple age threshold without checking if the decision opened a position still being held.
**How to avoid:** Purge only deletes decisions older than 30 days. Virtual positions reference the decision that opened them (decision_id foreign key), but the position itself is the source of truth -- losing the old decision log entry doesn't affect the position. Document this explicitly.
**Warning signs:** Users confused by positions without visible opening decision in the log.

### Pitfall 5: Multiple Evaluations During Startup
**What goes wrong:** If the server restarts mid-interval, the evaluation loop fires immediately for the "current" boundary, potentially double-evaluating if the pre-restart instance already evaluated.
**Why it happens:** The evaluation loop calculates the next boundary from current time without checking what was already evaluated.
**How to avoid:** Before evaluating, query the most recent decision for this user+symbol. If its timestamp is within the current interval, skip. This is a simple idempotency check.
**Warning signs:** Duplicate decision log entries at the same timestamp.

### Pitfall 6: Navigation Restructure Breaking Bookmarks
**What goes wrong:** Moving Backtest from `/backtest` to `/s/:symbol/backtest` breaks existing bookmarks and links.
**Why it happens:** Route restructure changes URL structure.
**How to avoid:** Add a redirect route: `<Route path="/backtest" element={<Navigate to="/s/BTCEUR/backtest" replace />} />`. Or keep Backtest at its current standalone location and only move it visually in the nav. Recommendation: Keep Backtest at `/backtest` as a standalone route (it's symbol-agnostic at entry), but show it in the Analyse group visually. This matches the current architecture.
**Warning signs:** 404 errors when users click bookmarks.

## Code Examples

### New Database Tables

```python
# In app/db/models.py

class DryRunDecisionDB(Base):
    """
    Dry-Run Decision Log - Every signal evaluation at candle close.

    Separate from production ledger. Auto-purged after 30 days.
    """
    __tablename__ = "dry_run_decisions"

    id = Column(String, primary_key=True)  # "drd_{uuid_hex[:12]}"
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)  # "BTCEUR" | "XRPEUR"

    # Decision
    action = Column(String, nullable=False)  # "BUY" | "SELL" | "HOLD" | "NO_SIGNAL"
    reason = Column(Text, nullable=False)  # Human-readable explanation

    # Alpha Score snapshot
    alpha_score = Column(Numeric(precision=10, scale=4), nullable=False)
    trade_signal = Column(String, nullable=False)  # "LONG" | "SHORT" | "NEUTRAL"
    threshold = Column(Numeric(precision=10, scale=4), nullable=False)
    quality = Column(String, nullable=False)  # "full" | "partial" | "degraded"

    # Factor breakdown (queryable + JSON blob for full detail)
    factor_zscore = Column(Numeric(precision=10, scale=4), nullable=True)
    factor_leadlag = Column(Numeric(precision=10, scale=4), nullable=True)
    factor_imbalance = Column(Numeric(precision=10, scale=4), nullable=True)
    factor_funding = Column(Numeric(precision=10, scale=4), nullable=True)
    factors_json = Column(JSON, nullable=False)  # Full factor detail array

    # Market context
    current_price = Column(Numeric(precision=20, scale=10), nullable=False)
    trailing_stop_level = Column(Numeric(precision=20, scale=10), nullable=True)

    # Regime
    regime_label = Column(String, nullable=True)
    regime_hurst = Column(Numeric(precision=10, scale=4), nullable=True)

    # Virtual trade (if action is BUY or SELL)
    virtual_qty = Column(Numeric(precision=20, scale=10), nullable=True)
    virtual_price = Column(Numeric(precision=20, scale=10), nullable=True)  # After slippage
    virtual_fee = Column(Numeric(precision=20, scale=10), nullable=True)

    evaluated_at = Column(DateTime, nullable=False, index=True)  # Candle close time
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("idx_drd_user_symbol_time", "user_id", "symbol", "evaluated_at"),
        Index("idx_drd_user_action", "user_id", "action"),
    )


class DryRunPortfolioDB(Base):
    """
    Dry-Run Virtual Portfolio state per user.

    Single row per user - updated after each evaluation.
    Completely separate from production portfolio.
    """
    __tablename__ = "dry_run_portfolios"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)

    initial_capital = Column(Numeric(precision=20, scale=2), nullable=False)
    cash = Column(Numeric(precision=20, scale=2), nullable=False)
    total_equity = Column(Numeric(precision=20, scale=2), nullable=False)
    unrealized_pnl = Column(Numeric(precision=20, scale=4), nullable=False)
    realized_pnl = Column(Numeric(precision=20, scale=4), nullable=False)

    trade_count = Column(Numeric(precision=10, scale=0), nullable=False, server_default="0")
    win_count = Column(Numeric(precision=10, scale=0), nullable=False, server_default="0")

    is_active = Column(Boolean, nullable=False, default=False)
    activated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class DryRunPositionDB(Base):
    """
    Dry-Run Virtual Position - Open virtual positions.

    Separate from trade_lots. Cleaned on portfolio reset.
    """
    __tablename__ = "dry_run_positions"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    portfolio_id = Column(String, ForeignKey("dry_run_portfolios.id"), nullable=False)

    symbol = Column(String, nullable=False)
    qty = Column(Numeric(precision=20, scale=10), nullable=False)
    entry_price = Column(Numeric(precision=20, scale=10), nullable=False)
    entry_time = Column(DateTime, nullable=False)
    fees_paid = Column(Numeric(precision=20, scale=10), nullable=False)
    decision_id = Column(String, ForeignKey("dry_run_decisions.id"), nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("idx_drp_user_symbol", "user_id", "symbol"),
    )
```

### DryRunService Singleton Skeleton

```python
# app/services/dry_run_service.py
"""
Dry-Run Service - Real-time paper trading engine.

STRUCTURAL ISOLATION (DRY-05):
This module MUST NOT import from:
- app.services.order_service
- app.services.binance (BinanceService)
- app.services.order_tracking_service
- app.services.pairing_service

All market data comes through AlphaScoreDataService.
"""
import asyncio
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.dry_run import (
    compute_position_size,
    execute_virtual_buy,
    execute_virtual_sell,
    compute_virtual_equity,
)
from app.services.alpha_score_data_service import get_alpha_score_data_service
from app.db.models import (
    DryRunDecisionDB,
    DryRunPortfolioDB,
    DryRunPositionDB,
    UserSettingsDB,
)

logger = logging.getLogger(__name__)

class DryRunService:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._running = False
        self._task = None

    async def start(self):
        """Start evaluation loop. Called from lifespan."""
        self._running = True
        self._task = asyncio.create_task(self._evaluation_loop())

    async def stop(self):
        """Stop evaluation loop. Called from lifespan."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _evaluation_loop(self):
        """Fires at each candle-close boundary for all active dry-run users."""
        # ...implementation per Pattern 2 above...
```

### API Routes

```python
# app/api/routes/dry_run.py
router = APIRouter(prefix="/api/dry-run", tags=["dry-run"])

@router.get("/{user_id}/status")
# Returns: is_active, positions, virtual_pnl, trade_count, win_rate

@router.post("/{user_id}/toggle")
# Toggles dry-run on/off; returns new status

@router.get("/{user_id}/decisions")
# Filterable decision log: from_date, to_date, action, symbol, limit, offset

@router.get("/{user_id}/decisions/{decision_id}")
# Full decision detail with factor breakdown

@router.post("/{user_id}/reset")
# Resets virtual portfolio (positions + P&L), keeps decision log

@router.get("/{user_id}/portfolio")
# Current virtual portfolio state
```

### Frontend API Client Additions

```javascript
// In api/client.js
export const getDryRunStatus = async (userId) => {
  const response = await apiClient.get(`/api/dry-run/${userId}/status`);
  return response.data;
};

export const toggleDryRun = async (userId) => {
  const response = await apiClient.post(`/api/dry-run/${userId}/toggle`);
  return response.data;
};

export const getDryRunDecisions = async (userId, { fromDate, toDate, action, symbol, limit = 50, offset = 0 } = {}) => {
  const response = await apiClient.get(`/api/dry-run/${userId}/decisions`, {
    params: { from_date: fromDate, to_date: toDate, action, symbol, limit, offset },
  });
  return response.data;
};

export const resetDryRunPortfolio = async (userId) => {
  const response = await apiClient.post(`/api/dry-run/${userId}/reset`);
  return response.data;
};

export const getDryRunPortfolio = async (userId) => {
  const response = await apiClient.get(`/api/dry-run/${userId}/portfolio`);
  return response.data;
};
```

### WebSocket Message Types

```javascript
// In WebSocketContext.jsx, add to switch(data.type):
case 'dry_run_decision': {
  // New decision logged -- invalidate decision log queries
  queryClient.invalidateQueries({ queryKey: ['dry-run-decisions'] });
  queryClient.invalidateQueries({ queryKey: ['dry-run-status'] });
  break;
}
case 'dry_run_status': {
  // Status changed (toggle on/off) -- invalidate status queries
  queryClient.invalidateQueries({ queryKey: ['dry-run-status'] });
  break;
}
case 'dry_run_portfolio_update': {
  // Virtual P&L updated -- invalidate portfolio queries
  queryClient.invalidateQueries({ queryKey: ['dry-run-portfolio'] });
  break;
}
```

### Settings Additions

```python
# In UserSettingsDB, add:
dry_run_initial_capital = Column(Numeric(precision=20, scale=2), nullable=True)  # Default: 10000

# In SettingsUpdate Pydantic model, add:
dry_run_initial_capital: Optional[str] = Field(default="10000")

# In DEFAULTS, add:
"dry_run_initial_capital": "10000",
```

### Claude's Discretion Recommendations

**Regime indicator design:** Use a styled badge similar to quality badges in Combined Score. Color: amber for trending, blue for mean-reverting, slate for transitional. Show Hurst value and confidence as tooltip.

**Backtest summary widget:** Surface 4 key metrics from most recent run: Net Return %, Sharpe Ratio, Trade Count, Win Rate. Show as mini KPI cards with "View Full Backtest" link.

**Decision log expandable row:** Click a row to expand inline (accordion pattern), showing all 4 factor sub-scores as horizontal bars (same as hero section), trailing stop level, and the full reason text. Similar pattern to the existing Backtest trade list.

**Color scheme for Bot section:** Use the existing amber accent (#d97706) from Orderblocks for the Bot section. Amber conveys "caution/paper trading" which aligns with dry-run's observational nature. Dry-run banner uses amber background.

**Signal history chart:** Recharts LineChart showing Alpha Score over time (-5 to +5 y-axis). Buy decisions marked with green upward triangles, Sell with red downward triangles, HOLD as gray dots. Reference lines at +threshold and -threshold. This is the most readable option for time-series signal data.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Boolean flag on OrderService (`if not dry_run: place_order()`) | Structural isolation (separate module, no imports) | Current best practice | Eliminates entire class of accidental-execution bugs |
| Single-table with `is_virtual` flag | Separate tables for virtual data | Database isolation pattern | Zero contamination risk between production and dry-run |
| Cron-based scheduler | asyncio background task in lifespan | FastAPI pattern | No external dependencies, runs in same process |

## Open Questions

1. **Multi-user evaluation scheduling**
   - What we know: The evaluation loop needs to fire for all active dry-run users at candle boundaries. Users may have different intervals (5m, 15m, 1h).
   - What's unclear: Whether to run one loop per interval or one loop per user.
   - Recommendation: One loop per distinct interval. At each boundary, query all active users with that interval and evaluate in sequence. This is simpler and avoids proliferating asyncio tasks. With a single-user app (as stated in project scope), this is trivially one evaluation per boundary.

2. **Backtest route location after nav restructure**
   - What we know: Backtest is currently at `/backtest` (standalone, symbol-agnostic). The new nav has an "Analyse" group.
   - What's unclear: Should Backtest move to `/s/:symbol/backtest` or stay at `/backtest` with a visual grouping in Analyse?
   - Recommendation: Keep Backtest at `/backtest` as standalone route. Show it in the Analyse group of GlobalNav (alongside the Backtest pill in the right section). Backtest is inherently symbol-agnostic at entry (user selects symbol in the form). Moving it under `/s/:symbol` would be confusing.

3. **Virtual portfolio persistence across server restarts**
   - What we know: Virtual portfolio state is stored in DB tables.
   - What's unclear: Should the evaluation loop auto-resume after server restart?
   - Recommendation: Yes. On lifespan startup, check for active dry-run portfolios and resume the evaluation loop. The `is_active` column on DryRunPortfolioDB persists the toggle state across restarts. The idempotency check (skip if already evaluated for this interval) prevents double-evaluation.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: All patterns derived from direct inspection of existing modules
  - `app/services/alpha_score_data_service.py` -- Singleton pattern, Alpha Score computation interface
  - `app/services/websocket_manager.py` -- Background task pattern, WebSocket broadcast
  - `app/services/backtest_data_service.py` -- Backtest orchestration, cost model
  - `app/domain/backtest_engine.py` -- BacktestConfig dataclass (fee_rate, slippage_pct, position_fraction)
  - `app/db/models.py` -- Full ORM model reference, table patterns
  - `app/api/routes/settings.py` -- Settings pattern (SettingsUpdate, DEFAULTS, _settings_to_dict)
  - `frontend/src/components/SymbolLayout.jsx` -- Current 3-group sub-nav structure
  - `frontend/src/components/GlobalNav.jsx` -- Current top-level navigation
  - `frontend/src/components/CombinedScore.jsx` -- Factor bar visual pattern reference
  - `frontend/src/contexts/WebSocketContext.jsx` -- WebSocket message handling patterns
  - `frontend/src/api/client.js` -- API client function patterns

### Secondary (MEDIUM confidence)
- FastAPI background tasks in lifespan: Standard pattern documented in FastAPI docs for long-running async tasks
- asyncio timer alignment: Standard approach for scheduling at wall-clock boundaries

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all technologies already in use in the project
- Architecture: HIGH -- patterns derived from existing codebase (DryRunService mirrors AlphaScoreDataService and BacktestDataService patterns)
- Pitfalls: HIGH -- based on direct analysis of existing service interactions and data model
- Navigation: MEDIUM -- the 4-group restructure impacts multiple components; exact routing decisions have tradeoffs

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable domain, no external dependencies)
