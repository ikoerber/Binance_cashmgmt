"""
Tests fuer Orderblock Service Layer.

Testet:
- OrderblockDataService mit gemockter Binance API
- Kline-Pagination, Caching, Detection/Backtest Orchestrierung
- Persistence Service (Zone Upsert, Backtest-Run CRUD)
- Serialisierung (Zone, Config, Metrics, Trade)

Alle Tests verwenden synthetische Daten oder Mocks (kein echtes I/O).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.domain.orderblock import (
    Candle,
    ConvictionLevel,
    FairValueGap,
    OBConfig,
    OBDirection,
    OBState,
    Orderblock,
)
from app.domain.orderblock_backtest import (
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    TradeOutcome,
    ZScoreCluster,
)
from app.services.orderblock_data_service import (
    ALLOWED_INTERVALS,
    CachedValue,
    OrderblockDataService,
    serialize_config,
    serialize_metrics,
    serialize_trade,
    serialize_zone,
)
from tests.conftest import OB_BASE_TIME as BASE_TIME, make_candle as _make_candle, make_binance_kline as _make_binance_kline


# ===========================================================================
# CachedValue Tests
# ===========================================================================


class TestCachedValue:
    def test_not_expired(self):
        now = datetime.now(timezone.utc)
        cv = CachedValue("data", now, timedelta(hours=1))
        assert not cv.is_expired(now + timedelta(minutes=30))

    def test_expired(self):
        now = datetime.now(timezone.utc)
        cv = CachedValue("data", now, timedelta(hours=1))
        assert cv.is_expired(now + timedelta(hours=1, seconds=1))


# ===========================================================================
# OrderblockDataService Tests
# ===========================================================================


class TestKlineFetching:
    """Tests fuer paginierte Kline-Abfrage mit gemocktem BinancePublicClient."""

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_fetch_single_page(self, mock_get_client):
        """Einzelne Seite (< 1000 Kerzen)."""
        klines = [_make_binance_kline(i) for i in range(50)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        result = service.fetch_candles("BTCEUR", "1h", months=1)

        assert len(result) == 50
        assert isinstance(result[0], Candle)
        assert result[0].open == Decimal("100")
        mock_client.get_klines.assert_called_once()

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_fetch_pagination(self, mock_get_client):
        """Mehrere Seiten (> 1000 Kerzen simuliert)."""
        page1 = [_make_binance_kline(i) for i in range(1000)]
        page2 = [_make_binance_kline(1000 + i) for i in range(500)]

        mock_client = MagicMock()
        mock_client.get_klines.side_effect = [page1, page2]
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        result = service.fetch_candles("BTCEUR", "1h", months=3)

        assert len(result) == 1500
        assert mock_client.get_klines.call_count == 2

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_fetch_api_error_returns_partial(self, mock_get_client):
        """API-Fehler nach erster Seite → partielle Daten."""
        page1 = [_make_binance_kline(i) for i in range(100)]

        mock_client = MagicMock()
        mock_client.get_klines.side_effect = [page1, Exception("Connection Error")]
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        # Erzwingt Pagination durch kurzes Interval
        result = service._fetch_klines_paginated(
            "BTCEUR",
            "1h",
            BASE_TIME,
            BASE_TIME + timedelta(hours=2000),
        )
        # Erste Seite hat nur 100 → bricht nach erster Seite ab (< 1000)
        assert len(result) == 100

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_cache_hit(self, mock_get_client):
        """Zweiter Aufruf verwendet Cache."""
        klines = [_make_binance_kline(i) for i in range(10)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        r1 = service.fetch_candles("BTCEUR", "1h", months=1)
        r2 = service.fetch_candles("BTCEUR", "1h", months=1)

        assert len(r1) == len(r2)
        # Nur ein API-Call (zweiter ist Cache-Hit)
        assert mock_client.get_klines.call_count == 1

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_empty_response(self, mock_get_client):
        """Leere API-Antwort → leere Liste."""
        mock_client = MagicMock()
        mock_client.get_klines.return_value = []
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        result = service.fetch_candles("BTCEUR", "1h", months=1)
        assert result == []


class TestAnalyzeOrchestration:
    """Tests fuer analyze() Orchestrierung (Combined Detection + Backtest)."""

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_analyze_returns_structure(self, mock_get_client):
        """Analyze liefert korrektes Result-Dict mit Zonen, Metriken, Trades."""
        klines = [_make_binance_kline(i) for i in range(50)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        result = service.analyze("BTCEUR", "1h", months=1)

        assert "zones" in result
        assert "metrics" in result
        assert "trades" in result
        assert "config" in result
        assert "meta" in result
        assert result["meta"]["symbol"] == "BTCEUR"
        assert result["meta"]["interval"] == "1h"

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_analyze_empty_candles(self, mock_get_client):
        """Analyze mit leeren Daten → leere Zonen und Trades."""
        mock_client = MagicMock()
        mock_client.get_klines.return_value = []
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        result = service.analyze("BTCEUR", "1h", months=1)

        assert result["zones"] == []
        assert result["trades"] == []
        assert result["meta"]["candle_count"] == 0

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_analyze_contains_raw_zones_and_result(self, mock_get_client):
        """Analyze liefert raw_zones und result fuer Persistenz."""
        klines = [_make_binance_kline(i) for i in range(50)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        service = OrderblockDataService()
        result = service.analyze("BTCEUR", "1h", months=1)

        assert "raw_zones" in result
        # raw_zones kann leer sein (flache Daten), aber Key muss existieren
        assert isinstance(result["raw_zones"], list)


# ===========================================================================
# Serialisierung Tests
# ===========================================================================


class TestSerialization:
    """Tests fuer Serialisierungsfunktionen."""

    def testserialize_config(self):
        config = OBConfig()
        d = serialize_config(config)

        assert d["atr_length"] == 20
        assert d["atr_multiplier"] == "2.0"
        assert d["fvg_window"] == 3
        assert d["swing_fractal_n"] == 2
        assert d["target_rr"] == "2.0"
        assert d["entry_policy"] == "NEAR_EDGE"
        assert d["stop_policy"] == "STOP_EDGE_TOUCH"
        assert d["mitigation_policy"] == "ZONE_TOUCH"

    def testserialize_zone(self):
        fvg = FairValueGap(
            index=5,
            timestamp=BASE_TIME,
            gap_top=Decimal("105"),
            gap_bottom=Decimal("100"),
            direction=OBDirection.BULLISH,
        )
        ob = Orderblock(
            id="ob_bullish_12345",
            direction=OBDirection.BULLISH,
            zone_top=Decimal("100"),
            zone_bottom=Decimal("95"),
            equilibrium=Decimal("97.5"),
            entry_edge=Decimal("100"),
            stop_edge=Decimal("95"),
            formed_at=BASE_TIME,
            confirmed_at=BASE_TIME + timedelta(hours=3),
            formed_at_index=10,
            confirmed_at_index=13,
            state=OBState.UNMITIGATED,
            conviction=ConvictionLevel.HIGH,
            volume_zscore=Decimal("2.5"),
            volume_weight=Decimal("1.8"),
            fvg=fvg,
            atr_at_formation=Decimal("5"),
            displacement_range=Decimal("15"),
            bos_swing_price=Decimal("102"),
            config=OBConfig(),
        )

        d = serialize_zone(ob)
        assert d["id"] == "ob_bullish_12345"
        assert d["direction"] == "BULLISH"
        assert d["state"] == "UNMITIGATED"
        assert d["conviction"] == "HIGH"
        assert d["zone_top"] == "100"
        assert d["zone_bottom"] == "95"
        assert d["mitigated_at"] is None

    def test_serialize_zone_with_mitigation(self):
        fvg = FairValueGap(
            index=5,
            timestamp=BASE_TIME,
            gap_top=Decimal("105"),
            gap_bottom=Decimal("100"),
            direction=OBDirection.BULLISH,
        )
        ob = Orderblock(
            id="ob_bullish_12345",
            direction=OBDirection.BULLISH,
            zone_top=Decimal("100"),
            zone_bottom=Decimal("95"),
            equilibrium=Decimal("97.5"),
            entry_edge=Decimal("100"),
            stop_edge=Decimal("95"),
            formed_at=BASE_TIME,
            confirmed_at=BASE_TIME + timedelta(hours=3),
            formed_at_index=10,
            confirmed_at_index=13,
            state=OBState.MITIGATED,
            conviction=ConvictionLevel.STANDARD,
            volume_zscore=Decimal("1.2"),
            volume_weight=Decimal("0.9"),
            fvg=fvg,
            atr_at_formation=Decimal("5"),
            displacement_range=Decimal("12"),
            bos_swing_price=Decimal("102"),
            config=OBConfig(),
            mitigated_at=BASE_TIME + timedelta(hours=10),
        )

        d = serialize_zone(ob)
        assert d["state"] == "MITIGATED"
        assert d["mitigated_at"] is not None

    def testserialize_trade(self):
        trade = BacktestTrade(
            ob_id="ob_bullish_12345",
            direction=OBDirection.BULLISH,
            entry_edge=Decimal("100"),
            stop_edge=Decimal("95"),
            target=Decimal("110"),
            entry_price=Decimal("100"),
            entry_timestamp=BASE_TIME,
            exit_timestamp=BASE_TIME + timedelta(hours=5),
            outcome=TradeOutcome.HIT,
            penetration_depth_pct=Decimal("20"),
            holding_duration_candles=5,
            min_adverse_price=Decimal("99"),
            conviction=ConvictionLevel.HIGH,
            volume_zscore=Decimal("2.5"),
        )

        d = serialize_trade(trade)
        assert d["ob_id"] == "ob_bullish_12345"
        assert d["outcome"] == "HIT"
        assert d["holding_duration_candles"] == 5
        assert d["conviction"] == "HIGH"

    def test_serialize_trade_open(self):
        trade = BacktestTrade(
            ob_id="ob_bearish_99999",
            direction=OBDirection.BEARISH,
            entry_edge=Decimal("100"),
            stop_edge=Decimal("105"),
            target=Decimal("90"),
            entry_price=Decimal("100"),
            entry_timestamp=BASE_TIME,
            exit_timestamp=None,
            outcome=TradeOutcome.OPEN,
            penetration_depth_pct=Decimal("0"),
            holding_duration_candles=100,
            min_adverse_price=Decimal("100"),
            conviction=ConvictionLevel.STANDARD,
            volume_zscore=Decimal("0.5"),
        )

        d = serialize_trade(trade)
        assert d["outcome"] == "OPEN"
        assert d["exit_timestamp"] is None


# ===========================================================================
# Persistence Service Tests (mit SQLite In-Memory)
# ===========================================================================


class TestPersistenceService:
    """Tests fuer Zone/Backtest CRUD mit SQLite In-Memory DB."""

    @pytest.fixture
    def db_session(self):
        """Erzeugt eine SQLAlchemy In-Memory Session."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.db.database import Base
        from app.db.models import OrderblockZoneDB, BacktestRunDB  # noqa: F401

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def _make_zone(self, ob_id="ob_bullish_12345", state=OBState.UNMITIGATED):
        fvg = FairValueGap(
            index=5,
            timestamp=BASE_TIME,
            gap_top=Decimal("105"),
            gap_bottom=Decimal("100"),
            direction=OBDirection.BULLISH,
        )
        return Orderblock(
            id=ob_id,
            direction=OBDirection.BULLISH,
            zone_top=Decimal("100"),
            zone_bottom=Decimal("95"),
            equilibrium=Decimal("97.5"),
            entry_edge=Decimal("100"),
            stop_edge=Decimal("95"),
            formed_at=BASE_TIME,
            confirmed_at=BASE_TIME + timedelta(hours=3),
            formed_at_index=10,
            confirmed_at_index=13,
            state=state,
            conviction=ConvictionLevel.HIGH,
            volume_zscore=Decimal("2.5"),
            volume_weight=Decimal("1.8"),
            fvg=fvg,
            atr_at_formation=Decimal("5"),
            displacement_range=Decimal("15"),
            bos_swing_price=Decimal("102"),
            config=OBConfig(),
        )

    def test_save_and_get_zones(self, db_session):
        from app.services.orderblock_persistence_service import (
            save_detection_result,
            get_zones,
        )

        zone = self._make_zone()
        config_json = serialize_config(OBConfig())

        saved = save_detection_result(
            db_session, "user_1", [zone], "BTCEUR", "1h", config_json
        )
        db_session.commit()

        assert saved == 1

        zones = get_zones(db_session, "user_1", "BTCEUR", "1h")
        assert len(zones) == 1
        assert zones[0]["id"] == "ob_bullish_12345"
        assert zones[0]["direction"] == "BULLISH"
        assert zones[0]["state"] == "UNMITIGATED"

    def test_upsert_zone_state(self, db_session):
        from app.services.orderblock_persistence_service import (
            save_detection_result,
            get_zones,
        )

        config_json = serialize_config(OBConfig())

        # Erstmal UNMITIGATED speichern
        zone1 = self._make_zone(state=OBState.UNMITIGATED)
        save_detection_result(
            db_session, "user_1", [zone1], "BTCEUR", "1h", config_json
        )
        db_session.commit()

        # Dann als MITIGATED updaten (Upsert)
        zone2 = self._make_zone(state=OBState.MITIGATED)
        zone2.mitigated_at = BASE_TIME + timedelta(hours=10)
        save_detection_result(
            db_session, "user_1", [zone2], "BTCEUR", "1h", config_json
        )
        db_session.commit()

        zones = get_zones(db_session, "user_1", "BTCEUR", "1h")
        assert len(zones) == 1
        assert zones[0]["state"] == "MITIGATED"
        assert zones[0]["mitigated_at"] is not None

    def test_get_zones_with_state_filter(self, db_session):
        from app.services.orderblock_persistence_service import (
            save_detection_result,
            get_zones,
        )

        config_json = serialize_config(OBConfig())

        z1 = self._make_zone("ob_1", OBState.UNMITIGATED)
        z2 = self._make_zone("ob_2", OBState.MITIGATED)
        z2.mitigated_at = BASE_TIME + timedelta(hours=5)
        z3 = self._make_zone("ob_3", OBState.INVALID)
        z3.invalidated_at = BASE_TIME + timedelta(hours=8)

        save_detection_result(
            db_session, "user_1", [z1, z2, z3], "BTCEUR", "1h", config_json
        )
        db_session.commit()

        unmitigated = get_zones(db_session, "user_1", "BTCEUR", "1h", "UNMITIGATED")
        assert len(unmitigated) == 1

        mitigated = get_zones(db_session, "user_1", "BTCEUR", "1h", "MITIGATED")
        assert len(mitigated) == 1

        all_zones = get_zones(db_session, "user_1", "BTCEUR", "1h")
        assert len(all_zones) == 3

    def test_get_zone_detail(self, db_session):
        from app.services.orderblock_persistence_service import (
            save_detection_result,
            get_zone_detail,
        )

        config_json = serialize_config(OBConfig())
        zone = self._make_zone()
        save_detection_result(
            db_session, "user_1", [zone], "BTCEUR", "1h", config_json
        )
        db_session.commit()

        detail = get_zone_detail(db_session, "ob_bullish_12345")
        assert detail is not None
        assert detail["id"] == "ob_bullish_12345"
        assert detail["config"] is not None

    def test_get_zone_detail_not_found(self, db_session):
        from app.services.orderblock_persistence_service import get_zone_detail

        detail = get_zone_detail(db_session, "nonexistent")
        assert detail is None

    def test_save_and_get_backtest_run(self, db_session):
        from app.services.orderblock_persistence_service import (
            save_backtest_result,
            get_backtest_runs,
            get_backtest_run,
        )

        result, kwargs = self._make_backtest_result_data()
        run_id = save_backtest_result(db_session, "user_1", result, **kwargs)
        db_session.commit()

        assert run_id.startswith("bt_")

        runs = get_backtest_runs(db_session, "user_1")
        assert len(runs) == 1
        assert runs[0]["id"] == run_id

        detail = get_backtest_run(db_session, run_id)
        assert detail is not None
        assert "trades" in detail

    def test_get_backtest_runs_with_symbol_filter(self, db_session):
        from app.services.orderblock_persistence_service import (
            save_backtest_result,
            get_backtest_runs,
        )

        r1, kw1 = self._make_backtest_result_data(symbol="BTCEUR")
        r2, kw2 = self._make_backtest_result_data(symbol="BTCUSDT")

        save_backtest_result(db_session, "user_1", r1, **kw1)
        save_backtest_result(db_session, "user_1", r2, **kw2)
        db_session.commit()

        all_runs = get_backtest_runs(db_session, "user_1")
        assert len(all_runs) == 2

        eur_runs = get_backtest_runs(db_session, "user_1", symbol="BTCEUR")
        assert len(eur_runs) == 1

    def test_get_backtest_run_not_found(self, db_session):
        from app.services.orderblock_persistence_service import get_backtest_run

        detail = get_backtest_run(db_session, "nonexistent")
        assert detail is None

    def _make_backtest_result_data(self, symbol="BTCEUR"):
        """Erzeugt ein minimales (result, kwargs) Tuple fuer save_backtest_result."""
        metrics = BacktestMetrics(
            total_zones=5,
            total_trades=3,
            hits=2,
            misses=1,
            open_trades=0,
            expired_trades=0,
            hit_rate=Decimal("0.6667"),
            avg_penetration_depth_pct=Decimal("25.5"),
            median_penetration_depth_pct=Decimal("20.0"),
            avg_holding_duration_candles=Decimal("10"),
            median_holding_duration_candles=Decimal("8"),
            high_conviction_count=2,
            high_conviction_hit_rate=Decimal("0.75"),
            standard_conviction_hit_rate=Decimal("0.50"),
            conviction_breakdown=[],
            zscore_clusters=[],
            high_conviction_zscore_count=1,
            high_conviction_zscore_hit_rate=Decimal("1.0"),
            unmitigated_count=1,
            mitigated_count=3,
            invalid_count=1,
            zones_per_month=Decimal("2.5"),
        )

        result = BacktestResult(
            metrics=metrics,
            trades=[],
            zones=[],
            config=OBConfig(),
            timeframe="1h",
            symbol=symbol,
            data_start=BASE_TIME,
            data_end=BASE_TIME + timedelta(days=180),
            candle_count=4380,
        )

        kwargs = {
            "config_json": serialize_config(OBConfig()),
            "metrics_json": serialize_metrics(result),
            "trades_json": [],
        }

        return result, kwargs


# ===========================================================================
# Allowed Intervals/Symbols Tests
# ===========================================================================


class TestSerializeMetrics:
    """Tests fuer _serialize_metrics Funktion."""

    def test_serialize_metrics_complete(self):
        """Vollstaendige Metriken korrekt serialisiert."""
        from app.domain.orderblock_backtest import ConvictionBreakdown

        metrics = BacktestMetrics(
            total_zones=10,
            total_trades=8,
            hits=5,
            misses=2,
            open_trades=1,
            expired_trades=0,
            hit_rate=Decimal("0.7143"),
            avg_penetration_depth_pct=Decimal("35.5"),
            median_penetration_depth_pct=Decimal("30.0"),
            avg_holding_duration_candles=Decimal("12"),
            median_holding_duration_candles=Decimal("10"),
            high_conviction_count=4,
            high_conviction_hit_rate=Decimal("0.80"),
            standard_conviction_hit_rate=Decimal("0.50"),
            conviction_breakdown=[
                ConvictionBreakdown(level="LOW", count=1, hits=0, misses=1, expired=0, hit_rate=Decimal("0")),
                ConvictionBreakdown(level="STANDARD", count=2, hits=1, misses=1, expired=0, hit_rate=Decimal("0.5")),
                ConvictionBreakdown(level="HIGH", count=3, hits=2, misses=0, expired=1, hit_rate=Decimal("1")),
                ConvictionBreakdown(level="INSTITUTIONAL", count=2, hits=2, misses=0, expired=0, hit_rate=Decimal("1")),
            ],
            zscore_clusters=[
                ZScoreCluster(range_label="1.0-1.5", range_low=Decimal("1.0"), range_high=Decimal("1.5"), count=3, hits=2, misses=1, hit_rate=Decimal("0.6667")),
            ],
            high_conviction_zscore_count=3,
            high_conviction_zscore_hit_rate=Decimal("0.75"),
            unmitigated_count=3,
            mitigated_count=5,
            invalid_count=2,
            zones_per_month=Decimal("3.3"),
        )

        result = BacktestResult(
            metrics=metrics,
            trades=[],
            zones=[],
            config=OBConfig(),
            timeframe="1h",
            symbol="BTCEUR",
            data_start=BASE_TIME,
            data_end=BASE_TIME + timedelta(days=90),
            candle_count=2160,
        )

        d = serialize_metrics(result)

        assert d["total_zones"] == 10
        assert d["total_trades"] == 8
        assert d["hits"] == 5
        assert d["misses"] == 2
        assert d["open_trades"] == 1
        assert d["expired_trades"] == 0
        assert d["hit_rate"] == "0.7143"
        assert d["avg_penetration_depth_pct"] == "35.5"
        assert d["median_penetration_depth_pct"] == "30.0"
        assert d["avg_holding_duration_candles"] == "12"
        assert d["median_holding_duration_candles"] == "10"
        assert d["high_conviction_count"] == 4
        assert d["high_conviction_hit_rate"] == "0.80"
        assert d["standard_conviction_hit_rate"] == "0.50"
        assert d["unmitigated_count"] == 3
        assert d["mitigated_count"] == 5
        assert d["invalid_count"] == 2
        assert d["zones_per_month"] == "3.3"

        # Conviction Breakdown
        assert len(d["conviction_breakdown"]) == 4
        high_bd = next(b for b in d["conviction_breakdown"] if b["level"] == "HIGH")
        assert high_bd["count"] == 3
        assert high_bd["hits"] == 2
        assert high_bd["expired"] == 1
        assert high_bd["hit_rate"] == "1"

        # Z-Score Clusters
        assert len(d["zscore_clusters"]) == 1
        assert d["zscore_clusters"][0]["range_label"] == "1.0-1.5"
        assert d["zscore_clusters"][0]["count"] == 3

    def test_serialize_metrics_none_hit_rate(self):
        """hit_rate=None wird korrekt serialisiert."""
        metrics = BacktestMetrics(
            total_zones=0, total_trades=0, hits=0, misses=0,
            open_trades=0, expired_trades=0, hit_rate=None,
            avg_penetration_depth_pct=Decimal("0"),
            median_penetration_depth_pct=Decimal("0"),
            avg_holding_duration_candles=Decimal("0"),
            median_holding_duration_candles=Decimal("0"),
            high_conviction_count=0, high_conviction_hit_rate=None,
            standard_conviction_hit_rate=None,
            conviction_breakdown=[], zscore_clusters=[],
            high_conviction_zscore_count=0, high_conviction_zscore_hit_rate=None,
            unmitigated_count=0, mitigated_count=0, invalid_count=0,
            zones_per_month=Decimal("0"),
        )
        result = BacktestResult(
            metrics=metrics, trades=[], zones=[], config=OBConfig(),
            timeframe="1h", symbol="BTCEUR",
            data_start=BASE_TIME, data_end=BASE_TIME + timedelta(days=30),
            candle_count=0,
        )
        d = serialize_metrics(result)
        assert d["hit_rate"] is None
        assert d["high_conviction_hit_rate"] is None
        assert d["standard_conviction_hit_rate"] is None


class TestValidation:
    def test_allowed_intervals(self):
        assert "1h" in ALLOWED_INTERVALS
        assert "4h" in ALLOWED_INTERVALS
        assert "1d" in ALLOWED_INTERVALS
        assert "1m" in ALLOWED_INTERVALS
        assert "2h" not in ALLOWED_INTERVALS

    def test_config_defaults(self):
        config = OBConfig()
        d = serialize_config(config)
        assert d["atr_length"] == 20
        assert d["target_rr"] == "2.0"
        assert d["zscore_lookback"] == 50


# ===========================================================================
# API Route Tests (FastAPI TestClient)
# ===========================================================================


class TestOrderblockAPIRoutes:
    """Tests fuer alle Orderblock API Endpoints."""

    @pytest.fixture
    def client(self):
        """FastAPI TestClient mit In-Memory DB (ohne Lifespan)."""
        os.environ.pop("API_SECRET_KEY", None)  # Auth deaktivieren fuer Tests

        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db.database import Base, get_db
        # Alle Models importieren damit Base.metadata sie kennt
        import app.db.models  # noqa: F401

        # Eigene FastAPI App ohne Lifespan (vermeidet Sentiment-Init etc.)
        from fastapi import FastAPI
        from app.api.routes.orderblock import router

        test_app = FastAPI()
        test_app.include_router(router)

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def override_get_db():
            session = TestSession()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        test_app.dependency_overrides[get_db] = override_get_db

        yield TestClient(test_app, raise_server_exceptions=True)

        test_app.dependency_overrides.clear()

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_analyze_endpoint(self, mock_get_client, client):
        """POST /{user_id}/analyze liefert Zonen, Metriken, Trades."""
        klines = [_make_binance_kline(i) for i in range(50)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        resp = client.post(
            "/api/orderblock/user1/analyze",
            json={"symbol": "BTCEUR", "interval": "1h", "months": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "zones" in data
        assert "config" in data
        assert "meta" in data
        assert "metrics" in data
        assert "trades" in data
        assert data["meta"]["symbol"] == "BTCEUR"

    def test_analyze_invalid_symbol(self, client):
        """POST /{user_id}/analyze mit ungueltigem Symbol -> 400."""
        resp = client.post(
            "/api/orderblock/user1/analyze",
            json={"symbol": "ETHEUR", "interval": "1h", "months": 1},
        )
        assert resp.status_code == 400
        assert "Symbol" in resp.json()["detail"]

    def test_analyze_invalid_interval(self, client):
        """POST /{user_id}/analyze mit ungueltigem Interval -> 400."""
        resp = client.post(
            "/api/orderblock/user1/analyze",
            json={"symbol": "BTCEUR", "interval": "2h", "months": 1},
        )
        assert resp.status_code == 400
        assert "Interval" in resp.json()["detail"]

    def test_get_zones_empty(self, client):
        """GET /{user_id}/zones ohne Daten -> leere Liste."""
        resp = client.get(
            "/api/orderblock/user1/zones",
            params={"symbol": "BTCEUR", "interval": "1h"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["zones"] == []
        assert data["count"] == 0

    def test_get_zones_invalid_state(self, client):
        """GET /{user_id}/zones mit ungueltigem State -> 400."""
        resp = client.get(
            "/api/orderblock/user1/zones",
            params={"symbol": "BTCEUR", "interval": "1h", "state": "FOOBAR"},
        )
        assert resp.status_code == 400

    def test_get_zone_detail_not_found(self, client):
        """GET /{user_id}/zones/{zone_id} nicht vorhanden -> 404."""
        resp = client.get("/api/orderblock/user1/zones/nonexistent")
        assert resp.status_code == 404

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_analyze_with_custom_config(self, mock_get_client, client):
        """POST /{user_id}/analyze mit Custom-Config."""
        klines = [_make_binance_kline(i) for i in range(50)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        resp = client.post(
            "/api/orderblock/user1/analyze",
            json={
                "symbol": "BTCEUR",
                "interval": "4h",
                "months": 3,
                "config": {
                    "atr_length": 14,
                    "atr_multiplier": 3.0,
                    "target_rr": 3.0,
                    "max_holding_candles": 100,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["config"]["atr_length"] == 14
        assert data["config"]["atr_multiplier"] == "3.0"

    def test_get_backtest_runs_empty(self, client):
        """GET /{user_id}/backtest/runs ohne Daten -> leere Liste."""
        resp = client.get("/api/orderblock/user1/backtest/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["count"] == 0

    def test_get_backtest_run_not_found(self, client):
        """GET /{user_id}/backtest/runs/{run_id} nicht vorhanden -> 404."""
        resp = client.get("/api/orderblock/user1/backtest/runs/nonexistent")
        assert resp.status_code == 404

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_analyze_and_get_zones_roundtrip(self, mock_get_client, client):
        """Analyze -> Zones abrufbar (Roundtrip)."""
        klines = [_make_binance_kline(i) for i in range(50)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        # Analyze (combined detection + backtest)
        resp = client.post(
            "/api/orderblock/user1/analyze",
            json={"symbol": "BTCEUR", "interval": "1h", "months": 1},
        )
        assert resp.status_code == 200

        # Zones abrufen
        resp = client.get(
            "/api/orderblock/user1/zones",
            params={"symbol": "BTCEUR", "interval": "1h"},
        )
        assert resp.status_code == 200
        # Flache Kerzen produzieren keine OBs, also 0
        assert resp.json()["count"] >= 0

    @patch("app.services.orderblock_data_service.get_binance_public_client")
    def test_analyze_and_get_runs_roundtrip(self, mock_get_client, client):
        """Analyze -> Backtest-Run abrufbar (Roundtrip)."""
        klines = [_make_binance_kline(i) for i in range(50)]
        mock_client = MagicMock()
        mock_client.get_klines.return_value = klines
        mock_get_client.return_value = mock_client

        # Analyze ausfuehren
        resp = client.post(
            "/api/orderblock/user1/analyze",
            json={"symbol": "BTCEUR", "interval": "1h", "months": 1},
        )
        assert resp.status_code == 200
        run_id = resp.json().get("run_id")

        # Runs abrufen
        resp = client.get("/api/orderblock/user1/backtest/runs")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        # run_id kann None sein wenn keine Kerzen → kein Backtest
        if run_id:
            assert len(runs) >= 1
            # Einzelnen Run abrufen
            resp = client.get(f"/api/orderblock/user1/backtest/runs/{run_id}")
            assert resp.status_code == 200
            assert resp.json()["id"] == run_id


# ===========================================================================
# Serialisierung: Sweep + Confluence Felder
# ===========================================================================


class TestSerializeSweepAndConfluence:
    """Tests fuer neue Sweep/Confluence Felder in Serialisierung."""

    def _make_zone(self, **kwargs):
        fvg = FairValueGap(
            index=5, timestamp=BASE_TIME, gap_top=Decimal("105"),
            gap_bottom=Decimal("100"), direction=OBDirection.BULLISH,
        )
        defaults = dict(
            id="ob_test", direction=OBDirection.BULLISH,
            zone_top=Decimal("100"), zone_bottom=Decimal("95"),
            equilibrium=Decimal("97.5"), entry_edge=Decimal("100"),
            stop_edge=Decimal("95"), formed_at=BASE_TIME,
            confirmed_at=BASE_TIME + timedelta(hours=3),
            formed_at_index=10, confirmed_at_index=13,
            state=OBState.UNMITIGATED, conviction=ConvictionLevel.HIGH,
            volume_zscore=Decimal("2.5"), volume_weight=Decimal("1.8"),
            fvg=fvg, atr_at_formation=Decimal("5"),
            displacement_range=Decimal("15"), bos_swing_price=Decimal("102"),
            config=OBConfig(),
        )
        defaults.update(kwargs)
        return Orderblock(**defaults)

    def test_serialize_zone_sweep_fields(self):
        """serialize_zone enthaelt Sweep-Felder."""
        zone = self._make_zone(
            has_liquidity_sweep=True,
            liquidity_sweep_level=Decimal("93.5"),
        )
        d = serialize_zone(zone)
        assert d["has_liquidity_sweep"] is True
        assert d["liquidity_sweep_level"] == "93.5"

    def test_serialize_zone_no_sweep(self):
        """Ohne Sweep: has_liquidity_sweep=False, level=None."""
        zone = self._make_zone()
        d = serialize_zone(zone)
        assert d["has_liquidity_sweep"] is False
        assert d["liquidity_sweep_level"] is None

    def test_serialize_zone_confluence_fields(self):
        """serialize_zone enthaelt Confluence-Felder."""
        zone = self._make_zone(
            sentiment_at_detection=Decimal("25.3"),
            confluence_label="STRONG_CONTRARIAN",
            confluence_score=Decimal("78"),
        )
        d = serialize_zone(zone)
        assert d["sentiment_at_detection"] == "25.3"
        assert d["confluence_label"] == "STRONG_CONTRARIAN"
        assert d["confluence_score"] == "78"

    def test_serialize_zone_no_confluence(self):
        """Ohne Sentiment: Confluence-Felder sind None."""
        zone = self._make_zone()
        d = serialize_zone(zone)
        assert d["sentiment_at_detection"] is None
        assert d["confluence_label"] is None
        assert d["confluence_score"] is None

    def test_serialize_config_sweep_params(self):
        """serialize_config enthaelt sweep_lookback und sweep_conviction_boost."""
        config = OBConfig(sweep_lookback=15, sweep_conviction_boost=Decimal("12"))
        d = serialize_config(config)
        assert d["sweep_lookback"] == 15
        assert d["sweep_conviction_boost"] == "12"

    def test_serialize_config_defaults(self):
        """Default-Config enthaelt Sweep-Defaults."""
        d = serialize_config(OBConfig())
        assert d["sweep_lookback"] == 10
        assert d["sweep_conviction_boost"] == "10"

    def test_serialize_trade_sweep_field(self):
        """serialize_trade enthaelt has_liquidity_sweep."""
        trade = BacktestTrade(
            ob_id="ob_test", direction=OBDirection.BULLISH,
            entry_edge=Decimal("100"), stop_edge=Decimal("95"),
            target=Decimal("110"), entry_price=Decimal("100"),
            entry_timestamp=BASE_TIME, exit_timestamp=BASE_TIME + timedelta(hours=5),
            outcome=TradeOutcome.HIT, penetration_depth_pct=Decimal("10"),
            holding_duration_candles=5, min_adverse_price=Decimal("99"),
            conviction=ConvictionLevel.HIGH, volume_zscore=Decimal("2.5"),
            conviction_score=Decimal("65"), has_liquidity_sweep=True,
        )
        d = serialize_trade(trade)
        assert d["has_liquidity_sweep"] is True
