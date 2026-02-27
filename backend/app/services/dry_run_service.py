"""
Dry-Run Service - Real-time paper trading engine.

STRUCTURAL ISOLATION (DRY-05):
This module MUST NOT import from:
- app.services.order_service
- app.services.binance (BinanceService)
- app.services.order_tracking_service
- app.services.pairing_service

All market data comes through AlphaScoreDataService and BinancePublicClient.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Optional

from app.db.database import SessionLocal
from app.db.models import (
    DryRunDecisionDB,
    DryRunPortfolioDB,
    DryRunPositionDB,
    UserSettingsDB,
)
from app.domain.dry_run import (
    VirtualPosition,
    compute_position_size,
    compute_virtual_equity,
    determine_action,
    execute_virtual_buy,
    execute_virtual_sell,
)
from app.services.alpha_score_data_service import get_alpha_score_data_service
from app.services.binance_public_client import get_binance_public_client
from app.services.websocket_manager import get_stream_manager

logger = logging.getLogger(__name__)

# --- Defaults ---
DEFAULT_FEE_RATE = Decimal("0.001")  # 0.1%
DEFAULT_SLIPPAGE = Decimal("0.0005")  # 0.05%
DEFAULT_POSITION_FRACTION = Decimal("0.10")  # 10% of equity per trade
DEFAULT_INITIAL_CAPITAL = Decimal("10000")
DEFAULT_INTERVAL = "15m"

# Interval -> seconds mapping
INTERVAL_SECONDS: Dict[str, int] = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}

# Purge threshold
PURGE_DAYS = 30


def _parse_interval_minutes(interval: str) -> int:
    """Konvertiert Intervall-String in Minuten."""
    mapping = {"5m": 5, "15m": 15, "1h": 60}
    return mapping.get(interval, 15)


def _next_boundary_sleep(now: datetime, interval_seconds: int) -> float:
    """Calculate seconds until next wall-clock interval boundary.

    For example, with interval_seconds=900 (15m):
    - At 14:07:32, next boundary is 14:15:00 -> sleep 7*60+28 = 448s
    - At 14:15:00, next boundary is 14:30:00 -> sleep 900s

    Returns at least 1 second to avoid busy-loop.
    """
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
    current_boundary = (seconds_since_midnight // interval_seconds) * interval_seconds
    next_boundary = current_boundary + interval_seconds
    sleep_seconds = next_boundary - seconds_since_midnight

    # Handle edge case: exactly on boundary -> sleep full interval
    if sleep_seconds <= 0:
        sleep_seconds = interval_seconds

    return max(1.0, float(sleep_seconds))


def _get_settings_dict(settings_row: Optional[UserSettingsDB]) -> dict:
    """Convert UserSettingsDB to dict with defaults."""
    from app.api.routes.settings import DEFAULTS, _settings_to_dict

    if settings_row:
        return _settings_to_dict(settings_row)
    return dict(DEFAULTS)


class DryRunService:
    """Singleton dry-run paper trading engine.

    Manages an asyncio background task that evaluates Alpha Score signals
    at candle-close boundaries for all active dry-run portfolios, executing
    virtual trades and broadcasting updates via WebSocket.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    # --- Lifecycle ---

    async def start(self):
        """Start the evaluation loop. Called from main.py lifespan."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._evaluation_loop())
        logger.info("DryRunService gestartet")

    async def stop(self):
        """Stop the evaluation loop. Called from main.py lifespan cleanup."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DryRunService gestoppt")

    # --- Evaluation Loop ---

    async def _evaluation_loop(self):
        """Main loop: fires at candle-close interval boundaries."""
        while self._running:
            try:
                # Determine minimum interval from active users
                interval_seconds = await self._get_min_interval_seconds()
                now = datetime.now(timezone.utc)
                sleep_seconds = _next_boundary_sleep(now, interval_seconds)

                await asyncio.sleep(sleep_seconds)

                if not self._running:
                    break

                # Evaluate all active user+symbol combinations
                await self._evaluate_all_active()

                # 30-day purge (once per loop iteration)
                await self._purge_old_decisions()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Evaluation loop Fehler")
                if self._running:
                    await asyncio.sleep(10)  # Brief pause before retry

    async def _get_min_interval_seconds(self) -> int:
        """Query active portfolios and return minimum interval in seconds."""
        try:
            db = SessionLocal()
            try:
                active_portfolios = (
                    db.query(DryRunPortfolioDB)
                    .filter(DryRunPortfolioDB.is_active.is_(True))
                    .all()
                )

                if not active_portfolios:
                    return INTERVAL_SECONDS.get(DEFAULT_INTERVAL, 900)

                min_seconds = 900  # Default 15m
                for portfolio in active_portfolios:
                    settings = (
                        db.query(UserSettingsDB)
                        .filter(UserSettingsDB.user_id == portfolio.user_id)
                        .first()
                    )
                    interval = DEFAULT_INTERVAL
                    if settings and settings.alpha_score_interval:
                        interval = settings.alpha_score_interval
                    secs = INTERVAL_SECONDS.get(interval, 900)
                    min_seconds = min(min_seconds, secs)

                return min_seconds
            finally:
                db.close()
        except Exception:
            logger.exception("Fehler beim Ermitteln des Min-Intervalls")
            return INTERVAL_SECONDS.get(DEFAULT_INTERVAL, 900)

    async def _evaluate_all_active(self):
        """Evaluate all active dry-run portfolios."""
        db = SessionLocal()
        try:
            active_portfolios = (
                db.query(DryRunPortfolioDB)
                .filter(DryRunPortfolioDB.is_active.is_(True))
                .all()
            )

            for portfolio in active_portfolios:
                user_id = portfolio.user_id
                # Determine which symbols to evaluate
                # For now: BTCEUR (primary pair)
                symbols = ["BTCEUR"]

                for symbol in symbols:
                    try:
                        # Idempotency check
                        if self._is_already_evaluated(user_id, symbol, db):
                            continue

                        async with self._lock:
                            await asyncio.to_thread(
                                self._evaluate_single, user_id, symbol, db
                            )
                            db.commit()
                    except Exception:
                        db.rollback()
                        logger.exception(
                            "Evaluation fehlgeschlagen: user=%s, symbol=%s",
                            user_id,
                            symbol,
                        )
        finally:
            db.close()

    def _is_already_evaluated(self, user_id: str, symbol: str, db) -> bool:
        """Check if we already evaluated this user+symbol in the current interval."""
        settings = (
            db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
        )
        interval = DEFAULT_INTERVAL
        if settings and settings.alpha_score_interval:
            interval = settings.alpha_score_interval

        interval_secs = INTERVAL_SECONDS.get(interval, 900)
        now = datetime.now(timezone.utc)
        # Calculate current interval start
        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
        current_boundary = (seconds_since_midnight // interval_secs) * interval_secs
        interval_start = now.replace(
            hour=current_boundary // 3600,
            minute=(current_boundary % 3600) // 60,
            second=0,
            microsecond=0,
        )

        latest_decision = (
            db.query(DryRunDecisionDB)
            .filter(
                DryRunDecisionDB.user_id == user_id,
                DryRunDecisionDB.symbol == symbol,
                DryRunDecisionDB.evaluated_at >= interval_start,
            )
            .first()
        )
        return latest_decision is not None

    def _evaluate_single(self, user_id: str, symbol: str, db):
        """Evaluate a single user+symbol combination.

        Runs in thread pool (called via asyncio.to_thread) since
        AlphaScoreDataService uses synchronous HTTP requests.
        """
        now = datetime.now(timezone.utc)

        # 1. Load settings
        settings_row = (
            db.query(UserSettingsDB).filter(UserSettingsDB.user_id == user_id).first()
        )
        settings = _get_settings_dict(settings_row)

        # 2. Get Alpha Score
        alpha_service = get_alpha_score_data_service()
        alpha_result = alpha_service.get_alpha_score(
            user_id=user_id,
            settings=settings,
        )

        # Handle warmup state
        if alpha_result.get("status") == "warmup":
            self._log_no_signal_decision(
                user_id, symbol, "Alpha Score im Warmup-Status", now, db
            )
            return

        # 3. Load portfolio and positions
        portfolio = (
            db.query(DryRunPortfolioDB)
            .filter(DryRunPortfolioDB.user_id == user_id)
            .first()
        )
        if not portfolio:
            return

        positions = (
            db.query(DryRunPositionDB)
            .filter(
                DryRunPositionDB.user_id == user_id,
                DryRunPositionDB.symbol == symbol,
            )
            .all()
        )

        # 4. Get current price
        current_price = self._get_current_price(symbol, alpha_result)
        if current_price is None or current_price <= Decimal("0"):
            self._log_no_signal_decision(
                user_id, symbol, "Kein gueltiger Preis verfuegbar", now, db
            )
            return

        # 5. Get trailing stop level
        trailing_stop_level = self._extract_trailing_stop(symbol, alpha_result)

        # 6. Determine action
        signal = alpha_result.get("trade_signal", "NEUTRAL")
        quality = alpha_result.get("quality", "warmup")
        has_open_position = len(positions) > 0

        action, reason = determine_action(
            signal=signal,
            quality=quality,
            has_open_position=has_open_position,
            candle_low=current_price,  # Use current price as proxy for candle low
            trailing_stop_level=trailing_stop_level,
        )

        # 7. Execute virtual trade if applicable
        fee_rate = DEFAULT_FEE_RATE
        slippage_pct = DEFAULT_SLIPPAGE
        position_fraction = DEFAULT_POSITION_FRACTION
        virtual_qty = None
        virtual_price = None
        virtual_fee = None

        if action == "BUY" and not has_open_position:
            try:
                # Compute position size
                equity = Decimal(str(portfolio.total_equity or portfolio.cash))
                qty = compute_position_size(
                    equity=equity,
                    fraction=position_fraction,
                    price=current_price,
                    fee_rate=fee_rate,
                )

                if qty > Decimal("0"):
                    cash = Decimal(str(portfolio.cash))
                    decision_id = f"drd_{uuid.uuid4().hex[:12]}"

                    trade_result = execute_virtual_buy(
                        cash=cash,
                        price=current_price,
                        qty=qty,
                        fee_rate=fee_rate,
                        slippage_pct=slippage_pct,
                        symbol=symbol,
                        timestamp=now,
                        decision_id=decision_id,
                    )

                    # Create position record
                    position_id = f"drpos_{uuid.uuid4().hex[:12]}"
                    new_pos = DryRunPositionDB(
                        id=position_id,
                        user_id=user_id,
                        portfolio_id=portfolio.id,
                        symbol=symbol,
                        qty=trade_result.qty,
                        entry_price=trade_result.effective_price,
                        entry_time=now,
                        fees_paid=trade_result.fee,
                        decision_id=decision_id,
                    )
                    db.add(new_pos)

                    # Update portfolio
                    portfolio.cash = trade_result.new_cash
                    portfolio.trade_count = int(portfolio.trade_count or 0) + 1

                    virtual_qty = trade_result.qty
                    virtual_price = trade_result.effective_price
                    virtual_fee = trade_result.fee
                else:
                    action = "HOLD"
                    reason = "Position size zu klein (qty=0)"
            except ValueError as e:
                action = "HOLD"
                reason = f"Buy nicht moeglich: {e}"

        elif action == "SELL" and has_open_position:
            # Sell all positions for this symbol
            for pos in positions:
                try:
                    vpos = VirtualPosition(
                        symbol=pos.symbol,
                        qty=Decimal(str(pos.qty)),
                        entry_price=Decimal(str(pos.entry_price)),
                        entry_time=pos.entry_time,
                        fees_paid=Decimal(str(pos.fees_paid)),
                        decision_id=pos.decision_id,
                    )

                    trade_result = execute_virtual_sell(
                        position=vpos,
                        exit_price=current_price,
                        fee_rate=fee_rate,
                        slippage_pct=slippage_pct,
                    )

                    # Update portfolio
                    portfolio.cash = (
                        Decimal(str(portfolio.cash)) + trade_result.new_cash
                    )
                    portfolio.realized_pnl = (
                        Decimal(str(portfolio.realized_pnl or 0))
                        + trade_result.realized_pnl
                    )
                    if trade_result.is_win:
                        portfolio.win_count = int(portfolio.win_count or 0) + 1

                    virtual_qty = trade_result.qty
                    virtual_price = trade_result.effective_price
                    virtual_fee = trade_result.fee

                    # Delete position
                    db.delete(pos)
                except Exception:
                    logger.exception("Sell fehlgeschlagen fuer Position %s", pos.id)

        # 8. Update equity
        remaining_positions = (
            db.query(DryRunPositionDB).filter(DryRunPositionDB.user_id == user_id).all()
        )
        vpositions = [
            VirtualPosition(
                symbol=p.symbol,
                qty=Decimal(str(p.qty)),
                entry_price=Decimal(str(p.entry_price)),
                entry_time=p.entry_time,
                fees_paid=Decimal(str(p.fees_paid)),
            )
            for p in remaining_positions
        ]

        # Get prices for all held symbols
        price_map: Dict[str, Decimal] = {symbol: current_price}
        for p in remaining_positions:
            if p.symbol not in price_map:
                try:
                    price_map[p.symbol] = get_binance_public_client().get_ticker_price(
                        p.symbol
                    )
                except Exception:
                    price_map[p.symbol] = Decimal("0")

        total_equity, unrealized_pnl = compute_virtual_equity(
            cash=Decimal(str(portfolio.cash)),
            positions=vpositions,
            current_prices=price_map,
        )
        portfolio.total_equity = total_equity
        portfolio.unrealized_pnl = unrealized_pnl

        # 9. Create decision record
        decision_id_val = (
            virtual_qty is not None
            and action in ("BUY", "SELL")
            and f"drd_{uuid.uuid4().hex[:12]}"
        ) or f"drd_{uuid.uuid4().hex[:12]}"

        alpha_score_val = Decimal(str(alpha_result.get("score", "0")))
        threshold_val = Decimal(str(alpha_result.get("threshold", "3.0")))

        factors = alpha_result.get("factors", [])
        factor_scores = self._serialize_factor_scores(factors)

        # Extract individual factor sub_scores for queryable columns
        factor_map = {f.get("name"): f.get("sub_score") for f in factors}

        regime = alpha_result.get("regime", {})

        decision = DryRunDecisionDB(
            id=decision_id_val,
            user_id=user_id,
            symbol=symbol,
            action=action,
            reason=reason,
            alpha_score=alpha_score_val,
            trade_signal=signal,
            threshold=threshold_val,
            quality=quality,
            factor_zscore=self._safe_decimal(factor_map.get("zscore")),
            factor_leadlag=self._safe_decimal(factor_map.get("leadlag")),
            factor_imbalance=self._safe_decimal(factor_map.get("imbalance")),
            factor_funding=self._safe_decimal(factor_map.get("funding")),
            factors_json=factor_scores,
            current_price=current_price,
            trailing_stop_level=trailing_stop_level,
            regime_label=regime.get("label"),
            regime_hurst=self._safe_decimal(regime.get("hurst")),
            virtual_qty=virtual_qty,
            virtual_price=virtual_price,
            virtual_fee=virtual_fee,
            evaluated_at=now,
        )
        db.add(decision)

        # 10. Broadcast via WebSocket
        asyncio.get_event_loop().create_task(
            self._broadcast_decision(user_id, decision, action)
        )
        if action in ("BUY", "SELL"):
            asyncio.get_event_loop().create_task(
                self._broadcast_portfolio_update(user_id, portfolio)
            )

    def _log_no_signal_decision(
        self, user_id: str, symbol: str, reason: str, now: datetime, db
    ):
        """Log a NO_SIGNAL decision when Alpha Score is unavailable."""
        decision = DryRunDecisionDB(
            id=f"drd_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            symbol=symbol,
            action="NO_SIGNAL",
            reason=reason,
            alpha_score=Decimal("0"),
            trade_signal="NEUTRAL",
            threshold=Decimal("3.0"),
            quality="warmup",
            factors_json=[],
            current_price=Decimal("0"),
            evaluated_at=now,
        )
        db.add(decision)
        db.commit()

    def _get_current_price(self, symbol: str, alpha_result: dict) -> Optional[Decimal]:
        """Extract current price from Alpha Score result or fetch from Binance."""
        # Try to get from trailing stops (most recent price)
        try:
            stops = get_alpha_score_data_service().get_trailing_stops(
                user_id="__internal__", settings={}
            )
            stop_data = stops.get("stops", {}).get(
                symbol.replace("BTC", "").replace("EUR", "") + "EUR", {}
            )
            if stop_data and stop_data.get("last_price"):
                return Decimal(str(stop_data["last_price"]))
        except Exception:
            pass

        # Fallback: fetch from Binance public API
        try:
            return get_binance_public_client().get_ticker_price(symbol)
        except Exception:
            logger.warning("Preis-Fetch fehlgeschlagen fuer %s", symbol)
            return None

    def _extract_trailing_stop(
        self, symbol: str, alpha_result: dict
    ) -> Optional[Decimal]:
        """Extract trailing stop level for symbol."""
        try:
            stops = get_alpha_score_data_service().get_trailing_stops(
                user_id="__internal__", settings={}
            )
            # Map BTCEUR -> stop data
            stop_key = symbol
            if symbol == "BTCEUR":
                stop_key = "BTCEUR"
            elif symbol == "XRPEUR":
                stop_key = "XRPEUR"

            stop_data = stops.get("stops", {}).get(stop_key, {})
            if stop_data and stop_data.get("stop_level"):
                return Decimal(str(stop_data["stop_level"]))
        except Exception:
            pass
        return None

    @staticmethod
    def _serialize_factor_scores(factors: list) -> list:
        """Convert factor score dicts to serializable format for factors_json."""
        result = []
        for f in factors:
            result.append(
                {
                    "name": f.get("name"),
                    "sub_score": f.get("sub_score"),
                    "raw_value": f.get("raw_value"),
                    "weight": f.get("weight"),
                    "base_weight": f.get("base_weight"),
                    "quality": f.get("quality"),
                    "description": f.get("description"),
                }
            )
        return result

    @staticmethod
    def _safe_decimal(value) -> Optional[Decimal]:
        """Safely convert a value to Decimal, returning None on failure."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    # --- 30-Day Purge ---

    async def _purge_old_decisions(self):
        """Delete decisions older than 30 days."""
        try:
            db = SessionLocal()
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=PURGE_DAYS)
                deleted = (
                    db.query(DryRunDecisionDB)
                    .filter(DryRunDecisionDB.evaluated_at < cutoff)
                    .delete()
                )
                if deleted > 0:
                    db.commit()
                    logger.info(
                        "Purged %d dry-run decisions older than %d days",
                        deleted,
                        PURGE_DAYS,
                    )
                else:
                    db.rollback()
            finally:
                db.close()
        except Exception:
            logger.exception("Purge fehlgeschlagen")

    # --- Toggle ---

    async def toggle_dry_run(self, user_id: str, db) -> dict:
        """Toggle dry-run on/off for a user."""
        async with self._lock:
            portfolio = (
                db.query(DryRunPortfolioDB)
                .filter(DryRunPortfolioDB.user_id == user_id)
                .first()
            )

            now = datetime.now(timezone.utc)

            if portfolio:
                # Toggle existing
                new_active = not portfolio.is_active
                portfolio.is_active = new_active
                if new_active:
                    portfolio.activated_at = now
            else:
                # Create new portfolio
                settings = (
                    db.query(UserSettingsDB)
                    .filter(UserSettingsDB.user_id == user_id)
                    .first()
                )
                initial_capital = DEFAULT_INITIAL_CAPITAL
                if settings and settings.dry_run_initial_capital:
                    initial_capital = Decimal(str(settings.dry_run_initial_capital))

                portfolio = DryRunPortfolioDB(
                    id=f"drp_{uuid.uuid4().hex[:12]}",
                    user_id=user_id,
                    initial_capital=initial_capital,
                    cash=initial_capital,
                    total_equity=initial_capital,
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    trade_count=0,
                    win_count=0,
                    is_active=True,
                    activated_at=now,
                )
                db.add(portfolio)
                new_active = True

            db.flush()

            # Broadcast status change
            asyncio.create_task(self._broadcast_status(user_id, new_active))

            return {
                "is_active": new_active,
                "message": "Dry-Run aktiviert" if new_active else "Dry-Run deaktiviert",
            }

    # --- Reset ---

    async def reset_portfolio(self, user_id: str, db) -> dict:
        """Reset virtual portfolio: wipe positions and P&L, keep decision log."""
        async with self._lock:
            # Delete all positions
            db.query(DryRunPositionDB).filter(
                DryRunPositionDB.user_id == user_id
            ).delete()

            # Reset portfolio state
            portfolio = (
                db.query(DryRunPortfolioDB)
                .filter(DryRunPortfolioDB.user_id == user_id)
                .first()
            )

            if portfolio:
                portfolio.cash = portfolio.initial_capital
                portfolio.total_equity = portfolio.initial_capital
                portfolio.unrealized_pnl = Decimal("0")
                portfolio.realized_pnl = Decimal("0")
                portfolio.trade_count = 0
                portfolio.win_count = 0
                # Keep is_active unchanged
            else:
                return {"message": "Kein Portfolio gefunden", "portfolio": None}

            db.flush()

            # Broadcast portfolio update
            asyncio.create_task(self._broadcast_portfolio_update(user_id, portfolio))

            return {
                "message": "Portfolio zurueckgesetzt",
                "portfolio": self._portfolio_to_dict(portfolio, []),
            }

    # --- Query Methods ---

    def get_status(self, user_id: str, db) -> dict:
        """Get dry-run status for a user."""
        portfolio = (
            db.query(DryRunPortfolioDB)
            .filter(DryRunPortfolioDB.user_id == user_id)
            .first()
        )

        if not portfolio:
            return {
                "is_active": False,
                "positions": [],
                "realized_pnl": "0",
                "unrealized_pnl": "0",
                "trade_count": 0,
                "win_rate": "0",
                "initial_capital": str(DEFAULT_INITIAL_CAPITAL),
                "cash": str(DEFAULT_INITIAL_CAPITAL),
                "total_equity": str(DEFAULT_INITIAL_CAPITAL),
            }

        positions = (
            db.query(DryRunPositionDB).filter(DryRunPositionDB.user_id == user_id).all()
        )

        trade_count = int(portfolio.trade_count or 0)
        win_count = int(portfolio.win_count or 0)
        win_rate = (
            str(Decimal(str(win_count)) / Decimal(str(trade_count)))
            if trade_count > 0
            else "0"
        )

        return {
            "is_active": portfolio.is_active,
            "positions": [self._position_to_dict(p) for p in positions],
            "realized_pnl": str(portfolio.realized_pnl or 0),
            "unrealized_pnl": str(portfolio.unrealized_pnl or 0),
            "trade_count": trade_count,
            "win_rate": win_rate,
            "initial_capital": str(portfolio.initial_capital),
            "cash": str(portfolio.cash),
            "total_equity": str(portfolio.total_equity),
        }

    def get_portfolio(self, user_id: str, db) -> dict:
        """Get full virtual portfolio state."""
        portfolio = (
            db.query(DryRunPortfolioDB)
            .filter(DryRunPortfolioDB.user_id == user_id)
            .first()
        )

        if not portfolio:
            return {
                "initial_capital": str(DEFAULT_INITIAL_CAPITAL),
                "cash": str(DEFAULT_INITIAL_CAPITAL),
                "total_equity": str(DEFAULT_INITIAL_CAPITAL),
                "unrealized_pnl": "0",
                "realized_pnl": "0",
                "trade_count": 0,
                "win_count": 0,
                "win_rate": "0",
                "is_active": False,
                "positions": [],
                "activated_at": None,
            }

        positions = (
            db.query(DryRunPositionDB).filter(DryRunPositionDB.user_id == user_id).all()
        )

        return self._portfolio_to_dict(portfolio, positions)

    def get_decisions(
        self,
        user_id: str,
        db,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        action: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get filterable decision log."""
        query = db.query(DryRunDecisionDB).filter(DryRunDecisionDB.user_id == user_id)

        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                query = query.filter(DryRunDecisionDB.evaluated_at >= from_dt)
            except ValueError:
                pass

        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                query = query.filter(DryRunDecisionDB.evaluated_at <= to_dt)
            except ValueError:
                pass

        if action:
            query = query.filter(DryRunDecisionDB.action == action)

        if symbol:
            query = query.filter(DryRunDecisionDB.symbol == symbol)

        total = query.count()

        decisions = (
            query.order_by(DryRunDecisionDB.evaluated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "decisions": [self._decision_to_dict(d) for d in decisions],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_decision(self, user_id: str, decision_id: str, db) -> Optional[dict]:
        """Get a single decision with full detail."""
        decision = (
            db.query(DryRunDecisionDB)
            .filter(
                DryRunDecisionDB.id == decision_id,
                DryRunDecisionDB.user_id == user_id,
            )
            .first()
        )

        if not decision:
            return None

        return self._decision_to_dict(decision)

    # --- Serialization Helpers ---

    @staticmethod
    def _position_to_dict(pos: DryRunPositionDB) -> dict:
        return {
            "id": pos.id,
            "symbol": pos.symbol,
            "qty": str(pos.qty),
            "entry_price": str(pos.entry_price),
            "entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
            "fees_paid": str(pos.fees_paid),
            "decision_id": pos.decision_id,
        }

    @staticmethod
    def _portfolio_to_dict(portfolio: DryRunPortfolioDB, positions: list) -> dict:
        trade_count = int(portfolio.trade_count or 0)
        win_count = int(portfolio.win_count or 0)
        win_rate = (
            str(Decimal(str(win_count)) / Decimal(str(trade_count)))
            if trade_count > 0
            else "0"
        )

        return {
            "initial_capital": str(portfolio.initial_capital),
            "cash": str(portfolio.cash),
            "total_equity": str(portfolio.total_equity),
            "unrealized_pnl": str(portfolio.unrealized_pnl or 0),
            "realized_pnl": str(portfolio.realized_pnl or 0),
            "trade_count": trade_count,
            "win_count": win_count,
            "win_rate": win_rate,
            "is_active": portfolio.is_active,
            "positions": [DryRunService._position_to_dict(p) for p in positions],
            "activated_at": (
                portfolio.activated_at.isoformat() if portfolio.activated_at else None
            ),
        }

    @staticmethod
    def _decision_to_dict(d: DryRunDecisionDB) -> dict:
        return {
            "id": d.id,
            "symbol": d.symbol,
            "action": d.action,
            "reason": d.reason,
            "alpha_score": str(d.alpha_score),
            "trade_signal": d.trade_signal,
            "threshold": str(d.threshold),
            "quality": d.quality,
            "factor_zscore": (
                str(d.factor_zscore) if d.factor_zscore is not None else None
            ),
            "factor_leadlag": (
                str(d.factor_leadlag) if d.factor_leadlag is not None else None
            ),
            "factor_imbalance": (
                str(d.factor_imbalance) if d.factor_imbalance is not None else None
            ),
            "factor_funding": (
                str(d.factor_funding) if d.factor_funding is not None else None
            ),
            "factors": d.factors_json or [],
            "current_price": str(d.current_price),
            "trailing_stop_level": (
                str(d.trailing_stop_level)
                if d.trailing_stop_level is not None
                else None
            ),
            "regime_label": d.regime_label,
            "regime_hurst": (
                str(d.regime_hurst) if d.regime_hurst is not None else None
            ),
            "virtual_qty": (str(d.virtual_qty) if d.virtual_qty is not None else None),
            "virtual_price": (
                str(d.virtual_price) if d.virtual_price is not None else None
            ),
            "virtual_fee": (str(d.virtual_fee) if d.virtual_fee is not None else None),
            "evaluated_at": (d.evaluated_at.isoformat() if d.evaluated_at else None),
        }

    # --- WebSocket Broadcasting ---

    async def _broadcast_decision(
        self, user_id: str, decision: DryRunDecisionDB, action: str
    ):
        """Broadcast a new decision via WebSocket."""
        try:
            manager = get_stream_manager()
            message = {
                "type": "dry_run_decision",
                "data": {
                    "id": decision.id,
                    "symbol": decision.symbol,
                    "action": action,
                    "alpha_score": str(decision.alpha_score),
                    "current_price": str(decision.current_price),
                    "evaluated_at": (
                        decision.evaluated_at.isoformat()
                        if decision.evaluated_at
                        else None
                    ),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await manager.broadcast_message(user_id, message)
        except Exception:
            logger.debug("WebSocket Broadcast fehlgeschlagen fuer dry_run_decision")

    async def _broadcast_status(self, user_id: str, is_active: bool):
        """Broadcast dry-run status change via WebSocket."""
        try:
            manager = get_stream_manager()
            message = {
                "type": "dry_run_status",
                "data": {"is_active": is_active},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await manager.broadcast_message(user_id, message)
        except Exception:
            logger.debug("WebSocket Broadcast fehlgeschlagen fuer dry_run_status")

    async def _broadcast_portfolio_update(
        self, user_id: str, portfolio: DryRunPortfolioDB
    ):
        """Broadcast portfolio update via WebSocket."""
        try:
            manager = get_stream_manager()
            message = {
                "type": "dry_run_portfolio_update",
                "data": {
                    "cash": str(portfolio.cash),
                    "total_equity": str(portfolio.total_equity),
                    "unrealized_pnl": str(portfolio.unrealized_pnl or 0),
                    "realized_pnl": str(portfolio.realized_pnl or 0),
                    "trade_count": int(portfolio.trade_count or 0),
                    "win_count": int(portfolio.win_count or 0),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await manager.broadcast_message(user_id, message)
        except Exception:
            logger.debug(
                "WebSocket Broadcast fehlgeschlagen fuer dry_run_portfolio_update"
            )


# --- Singleton ---

_dry_run_service: Optional[DryRunService] = None


def get_dry_run_service() -> DryRunService:
    """Liefert die Singleton-Instanz des DryRunService."""
    global _dry_run_service
    if _dry_run_service is None:
        _dry_run_service = DryRunService()
    return _dry_run_service
