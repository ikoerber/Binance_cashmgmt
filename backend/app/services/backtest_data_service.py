"""
Backtest Data Service - Orchestriert Alpha Score Backtesting.

Singleton-Service mit:
- Paginiertem Kline-Fetching (Binance REST API)
- Domain Backtest Engine Orchestrierung
- Ergebnis-Persistierung (AlphaBacktestRunDB)
- Laufzeit-Tracking und Cancellation

Datenquellen: Binance REST API (oeffentliche Klines, kein API Key noetig).
"""

import asyncio
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.domain.backtest_engine import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BenchmarkResult,
    EquityPoint,
    MonthlyReturn,
    TradeRecord,
    compute_warmup_period,
    run_alpha_backtest,
)
from app.services.binance_public_client import get_binance_public_client

logger = logging.getLogger(__name__)

# --- Konfiguration ---

MAX_KLINES_PER_REQUEST = 1000

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

# Symbols that the backtest engine trades on
BACKTEST_SYMBOLS = {"BTCEUR", "XRPEUR", "XRPBTC"}

# Maximum months for backtest data (limits API load)
MAX_MONTHS = 24


# --- Kline Parsing ---


def _parse_binance_kline(raw: list) -> dict:
    """
    Parse a raw Binance kline array into a candle dict.

    Format: {open_time: datetime, open: Decimal, high: Decimal, low: Decimal,
             close: Decimal, volume: Decimal}
    """
    return {
        "open_time": datetime.fromtimestamp(raw[0] / 1000, tz=timezone.utc).replace(
            tzinfo=None
        ),
        "open": Decimal(str(raw[1])),
        "high": Decimal(str(raw[2])),
        "low": Decimal(str(raw[3])),
        "close": Decimal(str(raw[4])),
        "volume": Decimal(str(raw[5])),
    }


class BacktestDataService:
    """
    Orchestriert Alpha Score Backtesting: Daten-Fetch, Simulation, Persistierung.

    Singleton-Instanz mit Cancellation-Support fuer laufende Backtests.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._active_runs: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # --- Paginated Kline Fetch ---

    def _fetch_candles_paginated(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[dict]:
        """
        Paginiertes Kline-Fetching (max 1000 pro Request).

        Returns:
            Liste von Candle-Dicts mit Decimal-Werten.
        """
        client = get_binance_public_client()
        candles: List[dict] = []
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        interval_ms = INTERVAL_MS.get(interval, 900_000)

        current_start = start_ms
        page = 0

        while current_start < end_ms:
            page += 1
            try:
                data = client.get_klines(
                    symbol,
                    interval,
                    limit=MAX_KLINES_PER_REQUEST,
                    start_time=current_start,
                    end_time=end_ms,
                )
            except Exception as e:
                logger.error(
                    "Binance Kline Fetch Fehler (Page %d, %s): %s", page, symbol, e
                )
                break

            if not data:
                break

            for raw in data:
                candles.append(_parse_binance_kline(raw))

            # Naechste Seite: letzter open_time + interval
            last_ts = data[-1][0]
            current_start = last_ts + interval_ms

            if len(data) < MAX_KLINES_PER_REQUEST:
                break

            logger.debug("Kline Page %d (%s): %d Kerzen", page, symbol, len(data))

        logger.info(
            "Klines gefetcht: %s %s → %d Kerzen (%d Pages)",
            symbol,
            interval,
            len(candles),
            page,
        )
        return candles

    # --- Warmup Start Computation ---

    def _compute_warmup_start(
        self, user_start: datetime, interval: str, warmup_candles: int
    ) -> datetime:
        """
        Berechnet den tatsaechlichen Fetch-Startpunkt inkl. Warmup-Buffer.

        Subtrahiert warmup_candles * interval_ms von user_start.
        """
        interval_ms = INTERVAL_MS.get(interval, 900_000)
        warmup_ms = warmup_candles * interval_ms
        return user_start - timedelta(milliseconds=warmup_ms)

    # --- Main Method: Run Backtest ---

    async def run_backtest(
        self,
        user_id: str,
        symbol: str,
        months: int,
        initial_capital: Decimal,
        config_overrides: dict,
        db: Session,
        settings: dict,
        ws_manager=None,
    ) -> dict:
        """
        Fuehrt einen Alpha Score Backtest durch.

        1. Liest User-Settings fuer Intervall und Parameter
        2. Fetcht paginierte Kline-Daten (XRPBTC, BTCEUR, XRPEUR)
        3. Fuehrt Domain-Simulation aus (asyncio.to_thread)
        4. Persistiert Ergebnis als AlphaBacktestRunDB
        5. Gibt serialisiertes Result-Dict zurueck

        Args:
            user_id: User ID
            symbol: Trading-Symbol (BTCEUR, XRPEUR, XRPBTC)
            months: Datenlookback in Monaten (1-24)
            initial_capital: Startkapital
            config_overrides: Override-Parameter (fee_rate, slippage_pct, etc.)
            db: SQLAlchemy Session
            settings: User-Settings Dict
            ws_manager: Optional WebSocket Manager fuer Progress-Updates
        """
        run_id = f"abt_{uuid.uuid4().hex[:12]}"
        start_time_exec = time.monotonic()

        # Cancel Event
        cancel_event = threading.Event()
        with self._lock:
            self._active_runs[run_id] = cancel_event

        try:
            # 1. Parse settings + overrides
            interval = config_overrides.get(
                "interval",
                settings.get("alpha_score_interval", "15m"),
            )
            fee_rate = Decimal(str(config_overrides.get("fee_rate", "0.001")))
            slippage_pct = Decimal(str(config_overrides.get("slippage_pct", "0.0005")))
            position_fraction = Decimal(
                str(config_overrides.get("position_fraction", "0.10"))
            )
            entry_threshold = Decimal(
                str(
                    config_overrides.get(
                        "entry_threshold",
                        settings.get("alpha_score_threshold", "3.0"),
                    )
                )
            )
            atr_period = int(config_overrides.get("atr_period", 14))
            atr_multiplier = Decimal(
                str(
                    config_overrides.get(
                        "atr_multiplier",
                        settings.get("alpha_score_atr_mult_btc", "2.0"),
                    )
                )
            )
            zscore_window = int(
                config_overrides.get(
                    "zscore_window",
                    settings.get("alpha_score_zscore_window", 60),
                )
            )
            leadlag_window = int(
                config_overrides.get(
                    "leadlag_window",
                    settings.get("alpha_score_leadlag_window", 30),
                )
            )
            hurst_lookback = int(
                config_overrides.get(
                    "hurst_lookback",
                    settings.get("alpha_score_hurst_lookback", 100),
                )
            )
            hurst_trending = Decimal(
                str(
                    config_overrides.get(
                        "hurst_trending",
                        settings.get("alpha_score_hurst_trending", "0.55"),
                    )
                )
            )
            hurst_reverting = Decimal(
                str(
                    config_overrides.get(
                        "hurst_reverting",
                        settings.get("alpha_score_hurst_reverting", "0.45"),
                    )
                )
            )

            # Build weight dict
            w_zscore = Decimal(
                str(
                    config_overrides.get(
                        "weight_zscore",
                        settings.get("alpha_score_weight_zscore", "40"),
                    )
                )
            )
            w_leadlag = Decimal(
                str(
                    config_overrides.get(
                        "weight_leadlag",
                        settings.get("alpha_score_weight_leadlag", "30"),
                    )
                )
            )
            w_imbalance = Decimal(
                str(
                    config_overrides.get(
                        "weight_imbalance",
                        settings.get("alpha_score_weight_imbalance", "20"),
                    )
                )
            )
            w_funding = Decimal(
                str(
                    config_overrides.get(
                        "weight_funding",
                        settings.get("alpha_score_weight_funding", "10"),
                    )
                )
            )
            w_sum = w_zscore + w_leadlag + w_imbalance + w_funding
            if w_sum > 0:
                weights = {
                    "zscore": (w_zscore / w_sum).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    ),
                    "leadlag": (w_leadlag / w_sum).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    ),
                    "imbalance": (w_imbalance / w_sum).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    ),
                    "funding": (w_funding / w_sum).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    ),
                }
            else:
                weights = {
                    "zscore": Decimal("0.40"),
                    "leadlag": Decimal("0.30"),
                    "imbalance": Decimal("0.20"),
                    "funding": Decimal("0.10"),
                }

            # Ensure sum = 1.0
            total = sum(weights.values())
            diff = Decimal("1.0") - total
            if diff != 0:
                largest_key = max(weights, key=lambda k: weights[k])
                weights[largest_key] += diff

            config = BacktestConfig(
                symbol=symbol,
                initial_capital=initial_capital,
                position_fraction=position_fraction,
                entry_threshold=entry_threshold,
                fee_rate=fee_rate,
                slippage_pct=slippage_pct,
                atr_period=atr_period,
                atr_multiplier=atr_multiplier,
                zscore_window=zscore_window,
                leadlag_window=leadlag_window,
                hurst_lookback=hurst_lookback,
                weights=weights,
                hurst_trending=hurst_trending,
                hurst_reverting=hurst_reverting,
            )

            # 2. Compute time range
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            user_start = now - timedelta(days=months * 30)
            warmup_candles = compute_warmup_period(config)
            fetch_start = self._compute_warmup_start(
                user_start, interval, warmup_candles
            )

            # 3. Fetch candle data (blocking I/O in thread)
            logger.info(
                "Backtest %s: Fetching candles for %s %s (%d months, warmup=%d)",
                run_id,
                symbol,
                interval,
                months,
                warmup_candles,
            )

            xrpbtc_candles, btceur_candles, xrpeur_candles = await asyncio.to_thread(
                self._fetch_all_candles, fetch_start, now, interval
            )

            # 4. Progress callback (throttled)
            last_progress_time = [time.monotonic()]

            def progress_callback(processed, total, trades_found):
                now_mono = time.monotonic()
                # Throttle to ~2-4 updates per second
                if now_mono - last_progress_time[0] < 0.3:
                    return
                last_progress_time[0] = now_mono

                if ws_manager is not None:
                    try:
                        pct = int(processed / total * 100) if total > 0 else 0
                        # Fire-and-forget async broadcast
                        asyncio.get_event_loop().call_soon_threadsafe(
                            asyncio.ensure_future,
                            ws_manager._broadcast_to_user(
                                user_id,
                                {
                                    "type": "backtest_progress",
                                    "data": {
                                        "run_id": run_id,
                                        "processed": processed,
                                        "total": total,
                                        "pct": pct,
                                        "trades_found": trades_found,
                                    },
                                },
                            ),
                        )
                    except Exception:
                        pass  # Non-critical

            # 5. Run simulation in thread
            logger.info(
                "Backtest %s: Starting simulation (%d XRPBTC, %d BTCEUR, %d XRPEUR candles)",
                run_id,
                len(xrpbtc_candles),
                len(btceur_candles),
                len(xrpeur_candles),
            )

            result: BacktestResult = await asyncio.to_thread(
                run_alpha_backtest,
                xrpbtc_candles,
                btceur_candles,
                xrpeur_candles,
                config,
                progress_callback,
                cancel_event,
            )

            # 6. Persist result
            saved_run_id = self._save_result(db, user_id, result, run_id, interval)
            duration = time.monotonic() - start_time_exec

            logger.info(
                "Backtest %s: Complete in %.1fs (%d trades, %.2f%% return)",
                saved_run_id,
                duration,
                result.metrics.trade_count,
                float(result.metrics.net_return_pct),
            )

            # 7. Return serialized result
            return self._serialize_result(result, saved_run_id)

        finally:
            with self._lock:
                self._active_runs.pop(run_id, None)

    # --- Fetch All Candle Series ---

    def _fetch_all_candles(
        self, start: datetime, end: datetime, interval: str
    ) -> tuple:
        """Fetcht XRPBTC, BTCEUR und XRPEUR Klines parallel (sequentiell innerhalb Thread)."""
        xrpbtc = self._fetch_candles_paginated("XRPBTC", interval, start, end)
        btceur = self._fetch_candles_paginated("BTCEUR", interval, start, end)

        # XRPEUR may not have long history -- try fetching directly
        xrpeur = self._fetch_candles_paginated("XRPEUR", interval, start, end)

        # Fallback: derive XRPEUR from XRPBTC * BTCEUR if direct fetch returns nothing
        if not xrpeur and xrpbtc and btceur:
            logger.info("XRPEUR not available, deriving from XRPBTC * BTCEUR")
            xrpeur = self._derive_xrpeur(xrpbtc, btceur)

        return xrpbtc, btceur, xrpeur

    @staticmethod
    def _derive_xrpeur(
        xrpbtc_candles: List[dict], btceur_candles: List[dict]
    ) -> List[dict]:
        """
        Leitet XRPEUR-Kerzen aus XRPBTC * BTCEUR ab.

        Matcht auf open_time (nur exakte Matches).
        """
        btceur_by_time = {c["open_time"]: c for c in btceur_candles}
        derived: List[dict] = []

        for xrp in xrpbtc_candles:
            btc = btceur_by_time.get(xrp["open_time"])
            if btc is None:
                continue
            derived.append(
                {
                    "open_time": xrp["open_time"],
                    "open": xrp["open"] * btc["open"],
                    "high": xrp["high"] * btc["high"],
                    "low": xrp["low"] * btc["low"],
                    "close": xrp["close"] * btc["close"],
                    "volume": xrp["volume"],
                }
            )

        return derived

    # --- Cancellation ---

    def cancel_run(self, run_id: str) -> bool:
        """
        Bricht einen laufenden Backtest ab.

        Returns:
            True wenn der Run gefunden und das Cancel-Event gesetzt wurde.
        """
        with self._lock:
            cancel_event = self._active_runs.get(run_id)
            if cancel_event is not None:
                cancel_event.set()
                logger.info("Backtest %s: Cancellation requested", run_id)
                return True
        return False

    # --- Persistence ---

    def _save_result(
        self,
        db: Session,
        user_id: str,
        result: BacktestResult,
        run_id: str,
        interval: str,
    ) -> str:
        """Persistiert BacktestResult als AlphaBacktestRunDB."""
        from app.db.models import AlphaBacktestRunDB

        config_json = _serialize_config(result.config)
        metrics_json = _serialize_metrics(result.metrics)
        trades_json = [_serialize_trade(t) for t in result.trades]
        equity_curve_json = [_serialize_equity_point(pt) for pt in result.equity_curve]
        monthly_json = [_serialize_monthly(m) for m in result.monthly_returns]

        # Compute excess return
        benchmark_return = result.benchmark.return_pct
        net_return = result.metrics.net_return_pct
        excess_return = (net_return - benchmark_return).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        db_run = AlphaBacktestRunDB(
            id=run_id,
            user_id=user_id,
            symbol=result.config.symbol,
            interval=interval,
            data_start=result.data_start,
            data_end=result.data_end,
            candle_count=result.candle_count,
            initial_capital=result.config.initial_capital,
            net_return_pct=result.metrics.net_return_pct,
            sharpe_ratio=result.metrics.sharpe_ratio,
            max_drawdown_pct=result.metrics.max_drawdown_pct,
            trade_count=result.metrics.trade_count,
            win_rate=result.metrics.win_rate,
            total_fees=result.metrics.total_fees,
            total_slippage=result.metrics.total_slippage,
            benchmark_return_pct=benchmark_return,
            excess_return_pct=excess_return,
            config_json=config_json,
            metrics_json=metrics_json,
            trades_json=trades_json,
            equity_curve_json=equity_curve_json,
            monthly_returns_json=monthly_json,
        )
        db.add(db_run)
        db.flush()

        return run_id

    # --- Query Methods ---

    def get_runs(
        self,
        db: Session,
        user_id: str,
        symbol: Optional[str] = None,
    ) -> List[dict]:
        """
        Listet Backtest-Runs fuer einen User (ohne grosse JSON-Blobs).

        Returns:
            Liste von Run-Summary Dicts, sortiert nach created_at desc.
        """
        from app.db.models import AlphaBacktestRunDB

        query = db.query(AlphaBacktestRunDB).filter(
            AlphaBacktestRunDB.user_id == user_id
        )
        if symbol:
            query = query.filter(AlphaBacktestRunDB.symbol == symbol)

        runs = query.order_by(AlphaBacktestRunDB.created_at.desc()).all()

        return [
            {
                "id": run.id,
                "symbol": run.symbol,
                "interval": run.interval,
                "data_start": _utc_iso(run.data_start),
                "data_end": _utc_iso(run.data_end),
                "candle_count": int(run.candle_count) if run.candle_count else 0,
                "initial_capital": str(run.initial_capital),
                "net_return_pct": _dec_str(run.net_return_pct),
                "sharpe_ratio": _dec_str(run.sharpe_ratio),
                "max_drawdown_pct": _dec_str(run.max_drawdown_pct),
                "trade_count": int(run.trade_count) if run.trade_count else 0,
                "win_rate": _dec_str(run.win_rate),
                "total_fees": _dec_str(run.total_fees),
                "total_slippage": _dec_str(run.total_slippage),
                "benchmark_return_pct": _dec_str(run.benchmark_return_pct),
                "excess_return_pct": _dec_str(run.excess_return_pct),
                "sweep_id": run.sweep_id,
                "created_at": _utc_iso(run.created_at),
            }
            for run in runs
        ]

    def get_run_detail(
        self,
        db: Session,
        user_id: str,
        run_id: str,
    ) -> Optional[dict]:
        """
        Gibt vollstaendige Run-Details inkl. Trades, Equity Curve, Monthly Returns.

        Returns:
            None wenn nicht gefunden oder falscher user_id (IDOR-Schutz).
        """
        from app.db.models import AlphaBacktestRunDB

        run = (
            db.query(AlphaBacktestRunDB)
            .filter(
                AlphaBacktestRunDB.id == run_id,
                AlphaBacktestRunDB.user_id == user_id,
            )
            .first()
        )

        if run is None:
            return None

        return {
            "id": run.id,
            "symbol": run.symbol,
            "interval": run.interval,
            "data_start": _utc_iso(run.data_start),
            "data_end": _utc_iso(run.data_end),
            "candle_count": int(run.candle_count) if run.candle_count else 0,
            "initial_capital": str(run.initial_capital),
            "net_return_pct": _dec_str(run.net_return_pct),
            "sharpe_ratio": _dec_str(run.sharpe_ratio),
            "max_drawdown_pct": _dec_str(run.max_drawdown_pct),
            "trade_count": int(run.trade_count) if run.trade_count else 0,
            "win_rate": _dec_str(run.win_rate),
            "total_fees": _dec_str(run.total_fees),
            "total_slippage": _dec_str(run.total_slippage),
            "benchmark_return_pct": _dec_str(run.benchmark_return_pct),
            "excess_return_pct": _dec_str(run.excess_return_pct),
            "sweep_id": run.sweep_id,
            "config_json": run.config_json,
            "metrics_json": run.metrics_json,
            "trades_json": run.trades_json,
            "equity_curve_json": run.equity_curve_json,
            "monthly_returns_json": run.monthly_returns_json,
            "created_at": _utc_iso(run.created_at),
        }

    # --- Result Serialization ---

    @staticmethod
    def _serialize_result(result: BacktestResult, run_id: str) -> dict:
        """Serialisiert BacktestResult fuer API-Response."""
        return {
            "run_id": run_id,
            "symbol": result.config.symbol,
            "candle_count": result.candle_count,
            "warmup_end_index": result.warmup_end_index,
            "data_start": _utc_iso(result.data_start),
            "data_end": _utc_iso(result.data_end),
            "cancelled": result.cancelled,
            "config": _serialize_config(result.config),
            "metrics": _serialize_metrics(result.metrics),
            "benchmark": _serialize_benchmark(result.benchmark),
            "trades": [_serialize_trade(t) for t in result.trades],
            "equity_curve": [_serialize_equity_point(pt) for pt in result.equity_curve],
            "monthly_returns": [_serialize_monthly(m) for m in result.monthly_returns],
        }


# --- Serialization Helpers ---


def _dec_str(val) -> Optional[str]:
    """Convert Decimal/Numeric to string, None-safe."""
    if val is None:
        return None
    return str(val)


def _utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Naive datetime (intern UTC) -> ISO-String mit Z-Suffix."""
    if dt is None:
        return None
    return dt.isoformat() + "Z"


def _serialize_config(config: BacktestConfig) -> dict:
    """Serialisiert BacktestConfig fuer JSON."""
    return {
        "symbol": config.symbol,
        "initial_capital": str(config.initial_capital),
        "position_fraction": str(config.position_fraction),
        "entry_threshold": str(config.entry_threshold),
        "fee_rate": str(config.fee_rate),
        "slippage_pct": str(config.slippage_pct),
        "atr_period": config.atr_period,
        "atr_multiplier": str(config.atr_multiplier),
        "zscore_window": config.zscore_window,
        "leadlag_window": config.leadlag_window,
        "hurst_lookback": config.hurst_lookback,
        "weights": {k: str(v) for k, v in config.weights.items()},
        "hurst_trending": str(config.hurst_trending),
        "hurst_reverting": str(config.hurst_reverting),
    }


def _serialize_metrics(metrics: BacktestMetrics) -> dict:
    """Serialisiert BacktestMetrics fuer JSON."""
    return {
        "net_return_pct": str(metrics.net_return_pct),
        "sharpe_ratio": _dec_str(metrics.sharpe_ratio),
        "max_drawdown_pct": str(metrics.max_drawdown_pct),
        "trade_count": metrics.trade_count,
        "win_rate": _dec_str(metrics.win_rate),
        "total_fees": str(metrics.total_fees),
        "total_slippage": str(metrics.total_slippage),
        "avg_trade_duration": _dec_str(metrics.avg_trade_duration),
    }


def _serialize_benchmark(benchmark: BenchmarkResult) -> dict:
    """Serialisiert BenchmarkResult fuer JSON."""
    return {
        "return_pct": str(benchmark.return_pct),
        "final_equity": str(benchmark.final_equity),
        "sharpe_ratio": _dec_str(benchmark.sharpe_ratio),
    }


def _serialize_trade(trade: TradeRecord) -> dict:
    """Serialisiert TradeRecord fuer JSON."""
    return {
        "entry_time": _utc_iso(trade.entry_time),
        "exit_time": _utc_iso(trade.exit_time),
        "entry_price": str(trade.entry_price),
        "exit_price": _dec_str(trade.exit_price),
        "qty": str(trade.qty),
        "pnl_eur": _dec_str(trade.pnl_eur),
        "pnl_pct": _dec_str(trade.pnl_pct),
        "duration_candles": trade.duration_candles,
        "alpha_score_at_entry": str(trade.alpha_score_at_entry),
        "fees_paid": str(trade.fees_paid),
        "slippage_cost": str(trade.slippage_cost),
        "is_open": trade.is_open,
    }


def _serialize_equity_point(point: EquityPoint) -> dict:
    """Serialisiert EquityPoint fuer JSON."""
    return {
        "t": _utc_iso(point.timestamp),
        "equity": str(point.equity),
        "benchmark": str(point.benchmark_equity),
        "drawdown_pct": str(point.drawdown_pct),
    }


def _serialize_monthly(monthly: MonthlyReturn) -> dict:
    """Serialisiert MonthlyReturn fuer JSON."""
    return {
        "year": monthly.year,
        "month": monthly.month,
        "return_pct": str(monthly.return_pct),
    }


# --- Singleton ---

_service: Optional[BacktestDataService] = None
_service_lock = threading.Lock()


def get_backtest_data_service() -> BacktestDataService:
    """Liefert die Singleton-Instanz des BacktestDataService."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = BacktestDataService()
    return _service
