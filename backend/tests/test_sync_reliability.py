"""
TDD Tests for Per-Fill Sync Result Tracking (Phase 06-01)

Tests the SyncResult domain model (pure) and sync_fills behavior (mocked):
- SyncResult unit tests: status computation, backward compat, fill_details filtering
- sync_fills integration tests: per-fill tracking, FIFO abort, watermark
- SYNC-02 verification: Phase 5 retry wiring smoke test
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.domain.sync_result import FillOutcome, FillResult, SyncResult

# ============================================================
# Helpers
# ============================================================


def _make_fill_result(
    source_id: str,
    side: str = "BUY",
    outcome: str = FillOutcome.PROCESSED,
    error: str | None = None,
    timestamp: datetime | None = None,
) -> FillResult:
    """Create a FillResult for testing."""
    return FillResult(
        source_id=source_id,
        fill_id=f"binance_BTCEUR_{source_id}",
        side=side,
        outcome=outcome,
        error=error,
        timestamp=timestamp or datetime(2024, 6, 1, 12, 0, 0),
    )


def _make_sync_result(
    fill_results: list[FillResult] | None = None,
    fills_total: int = 0,
    fills_new: int = 0,
    new_lots: int = 0,
    allocations: int = 0,
    fifo_aborted: bool = False,
) -> SyncResult:
    """Create a SyncResult for testing."""
    if fill_results is None:
        fill_results = []
    fills_processed = sum(
        1 for fr in fill_results if fr.outcome == FillOutcome.PROCESSED
    )
    fills_failed = sum(1 for fr in fill_results if fr.outcome == FillOutcome.FAILED)
    fills_skipped_fifo = sum(
        1 for fr in fill_results if fr.outcome == FillOutcome.SKIPPED_FIFO
    )
    return SyncResult(
        fills_total=fills_total,
        fills_new=fills_new,
        fills_processed=fills_processed,
        fills_failed=fills_failed,
        fills_skipped_fifo=fills_skipped_fifo,
        new_lots=new_lots,
        allocations=allocations,
        fill_results=fill_results,
        fifo_aborted=fifo_aborted,
    )


# ============================================================
# SyncResult Unit Tests (pure domain)
# ============================================================


class TestSyncReliability:
    """Pure domain tests for SyncResult."""

    def test_sync_result_status_success(self):
        """All fills processed -> status 'success'."""
        result = _make_sync_result(
            fill_results=[
                _make_fill_result("1"),
                _make_fill_result("2"),
            ],
            fills_total=5,
            fills_new=2,
        )
        assert result.status == "success"

    def test_sync_result_status_no_new_fills(self):
        """fills_new==0 -> status 'no_new_fills'."""
        result = _make_sync_result(fills_total=5, fills_new=0)
        assert result.status == "no_new_fills"

    def test_sync_result_status_partial_success(self):
        """Some fills failed -> status 'partial_success'."""
        result = _make_sync_result(
            fill_results=[
                _make_fill_result("1"),
                _make_fill_result("2", outcome=FillOutcome.FAILED, error="DB error"),
            ],
            fills_total=5,
            fills_new=2,
        )
        assert result.status == "partial_success"

    def test_sync_result_status_fifo_error(self):
        """fifo_aborted=True -> status 'fifo_error'."""
        result = _make_sync_result(
            fill_results=[
                _make_fill_result(
                    "1", side="SELL", outcome=FillOutcome.FAILED, error="FIFO fail"
                ),
                _make_fill_result("2", side="SELL", outcome=FillOutcome.SKIPPED_FIFO),
            ],
            fills_total=5,
            fills_new=2,
            fifo_aborted=True,
        )
        assert result.status == "fifo_error"

    def test_sync_result_errors_backward_compat(self):
        """.errors returns list of error strings from FAILED FillResults."""
        result = _make_sync_result(
            fill_results=[
                _make_fill_result("1"),
                _make_fill_result("2", outcome=FillOutcome.FAILED, error="Error A"),
                _make_fill_result("3", outcome=FillOutcome.FAILED, error="Error B"),
                _make_fill_result("4", outcome=FillOutcome.SKIPPED_FIFO),
            ],
            fills_total=10,
            fills_new=4,
        )
        errors = result.errors
        assert len(errors) == 2
        assert "Error A" in errors
        assert "Error B" in errors

    def test_sync_result_to_dict_backward_compat(self):
        """to_dict() has all existing keys."""
        result = _make_sync_result(
            fill_results=[_make_fill_result("1")],
            fills_total=5,
            fills_new=1,
            new_lots=1,
            allocations=0,
        )
        d = result.to_dict()
        # All existing keys must be present
        assert "status" in d
        assert "new_fills" in d
        assert "new_lots" in d
        assert "allocations" in d
        assert "errors" in d
        assert "message" in d

    def test_sync_result_to_dict_new_fields(self):
        """to_dict() has new fields: fills_processed, fills_failed, fills_skipped_fifo, last_synced_source_id, fifo_aborted, fill_details."""
        result = _make_sync_result(
            fill_results=[_make_fill_result("100")],
            fills_total=5,
            fills_new=1,
            new_lots=1,
        )
        d = result.to_dict()
        assert "fills_processed" in d
        assert "fills_failed" in d
        assert "fills_skipped_fifo" in d
        assert "last_synced_source_id" in d
        assert "fifo_aborted" in d
        assert "fill_details" in d

    def test_sync_result_fill_details_only_failures(self):
        """fill_details only contains FAILED and SKIPPED_FIFO entries."""
        result = _make_sync_result(
            fill_results=[
                _make_fill_result("1"),  # PROCESSED
                _make_fill_result("2"),  # PROCESSED
                _make_fill_result("3", outcome=FillOutcome.FAILED, error="Err"),
                _make_fill_result("4", outcome=FillOutcome.SKIPPED_FIFO),
            ],
            fills_total=10,
            fills_new=4,
        )
        d = result.to_dict()
        details = d["fill_details"]
        assert len(details) == 2
        outcomes = {detail["outcome"] for detail in details}
        assert FillOutcome.PROCESSED not in outcomes
        assert FillOutcome.FAILED in outcomes
        assert FillOutcome.SKIPPED_FIFO in outcomes

    def test_sync_result_last_synced_source_id(self):
        """Correctly picks max source_id from PROCESSED fills (numeric comparison)."""
        result = _make_sync_result(
            fill_results=[
                _make_fill_result("50"),
                _make_fill_result("200"),
                _make_fill_result("100"),
                _make_fill_result("150", outcome=FillOutcome.FAILED, error="Err"),
            ],
            fills_total=10,
            fills_new=4,
        )
        assert result.last_synced_source_id == "200"

    def test_sync_result_last_synced_source_id_none_when_no_processed(self):
        """Returns None when no fills processed."""
        result = _make_sync_result(
            fill_results=[
                _make_fill_result("1", outcome=FillOutcome.FAILED, error="Err"),
            ],
            fills_total=5,
            fills_new=1,
        )
        assert result.last_synced_source_id is None


# ============================================================
# sync_fills Integration Tests (mocked DB + Binance)
# ============================================================


class TestSyncFillsIntegration:
    """Integration tests for sync_fills with mocked dependencies."""

    def _setup_sync_service(self):
        """Create a SyncService with mocked BinanceService."""
        from app.services.sync_service import SyncService

        mock_binance = MagicMock()
        service = SyncService(mock_binance)
        return service, mock_binance

    def _make_buy_event(self, fill_id: str, timestamp: datetime):
        """Create a LedgerEvent for a buy fill."""
        from app.domain.models import LedgerEvent, EventType, EventSource, TradeSide

        return LedgerEvent(
            id=f"binance_BTCEUR_{fill_id}",
            type=EventType.TRADE_FILL,
            timestamp=timestamp,
            asset="BTC",
            amount=Decimal("0.01"),
            symbol="BTCEUR",
            price=Decimal("50000"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
            source_id=fill_id,
        )

    def _make_sell_event(self, fill_id: str, timestamp: datetime):
        """Create a LedgerEvent for a sell fill."""
        from app.domain.models import LedgerEvent, EventType, EventSource, TradeSide

        return LedgerEvent(
            id=f"binance_BTCEUR_{fill_id}",
            type=EventType.TRADE_FILL,
            timestamp=timestamp,
            asset="BTC",
            amount=Decimal("0.01"),
            symbol="BTCEUR",
            price=Decimal("55000"),
            side=TradeSide.SELL,
            source=EventSource.BINANCE,
            source_id=fill_id,
        )

    def test_sync_fills_all_buys_success(self):
        """3 buy fills all succeed -> fills_processed=3, fills_failed=0, status=success."""
        service, mock_binance = self._setup_sync_service()
        mock_db = MagicMock()

        fills = [
            self._make_buy_event("101", datetime(2024, 6, 1, 10, 0)),
            self._make_buy_event("102", datetime(2024, 6, 1, 11, 0)),
            self._make_buy_event("103", datetime(2024, 6, 1, 12, 0)),
        ]
        mock_binance.fetch_trades.return_value = fills

        # No existing fills in DB
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "app.services.sync_service.persist_ledger_event"
        ) as mock_persist, patch(
            "app.services.sync_service.create_lot_from_buy_fill"
        ), patch(
            "app.services.sync_service.compute_fee_quote_value", return_value=None
        ):
            # Mock persist to return event_db with proper side
            from app.db.models import TradeSideEnum

            mock_persist.side_effect = lambda db, uid, ev, fee_quote_value=None: (
                MagicMock(id=ev.id, side=TradeSideEnum.BUY, timestamp=ev.timestamp)
            )

            result = service.sync_fills(mock_db, "user_1", "BTCEUR")

        assert result["fills_processed"] == 3
        assert result["fills_failed"] == 0
        assert result["status"] == "success"

    def test_sync_fills_buy_lot_failure_tracked(self):
        """1 buy fill fails lot creation -> fills_failed=1, error in fill_details."""
        service, mock_binance = self._setup_sync_service()
        mock_db = MagicMock()

        fills = [
            self._make_buy_event("201", datetime(2024, 6, 1, 10, 0)),
            self._make_buy_event("202", datetime(2024, 6, 1, 11, 0)),
        ]
        mock_binance.fetch_trades.return_value = fills
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "app.services.sync_service.persist_ledger_event"
        ) as mock_persist, patch(
            "app.services.sync_service.create_lot_from_buy_fill"
        ) as mock_create_lot, patch(
            "app.services.sync_service.compute_fee_quote_value", return_value=None
        ):
            from app.db.models import TradeSideEnum

            mock_persist.side_effect = lambda db, uid, ev, fee_quote_value=None: (
                MagicMock(id=ev.id, side=TradeSideEnum.BUY, timestamp=ev.timestamp)
            )
            # First lot succeeds, second fails
            mock_create_lot.side_effect = [None, ValueError("Lot creation failed")]

            result = service.sync_fills(mock_db, "user_1", "BTCEUR")

        assert result["fills_failed"] == 1
        assert result["status"] == "partial_success"
        # fill_details should contain the failure
        details = result.get("fill_details", [])
        assert any(d["outcome"] == FillOutcome.FAILED for d in details)

    def test_sync_fills_fifo_abort_marks_remaining(self):
        """Sell fail aborts FIFO, remaining sells marked SKIPPED_FIFO."""
        service, mock_binance = self._setup_sync_service()
        mock_db = MagicMock()

        fills = [
            self._make_sell_event("301", datetime(2024, 6, 1, 10, 0)),
            self._make_sell_event("302", datetime(2024, 6, 1, 11, 0)),
            self._make_sell_event("303", datetime(2024, 6, 1, 12, 0)),
        ]
        mock_binance.fetch_trades.return_value = fills
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "app.services.sync_service.persist_ledger_event"
        ) as mock_persist, patch(
            "app.services.sync_service.process_sell_fill"
        ) as mock_sell, patch(
            "app.services.sync_service.compute_fee_quote_value", return_value=None
        ):
            from app.db.models import TradeSideEnum

            mock_persist.side_effect = lambda db, uid, ev, fee_quote_value=None: (
                MagicMock(id=ev.id, side=TradeSideEnum.SELL, timestamp=ev.timestamp)
            )
            # First sell fails -> FIFO abort
            mock_sell.side_effect = ValueError("FIFO allocation failed")

            result = service.sync_fills(mock_db, "user_1", "BTCEUR")

        assert result["fifo_aborted"] is True
        assert result["status"] == "fifo_error"
        assert result["fills_skipped_fifo"] == 2  # remaining 2 sells skipped

    def test_sync_fills_last_synced_source_id_in_response(self):
        """Response dict has last_synced_source_id from highest processed fill."""
        service, mock_binance = self._setup_sync_service()
        mock_db = MagicMock()

        fills = [
            self._make_buy_event("501", datetime(2024, 6, 1, 10, 0)),
            self._make_buy_event("999", datetime(2024, 6, 1, 11, 0)),
            self._make_buy_event("502", datetime(2024, 6, 1, 12, 0)),
        ]
        mock_binance.fetch_trades.return_value = fills
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "app.services.sync_service.persist_ledger_event"
        ) as mock_persist, patch(
            "app.services.sync_service.create_lot_from_buy_fill"
        ), patch(
            "app.services.sync_service.compute_fee_quote_value", return_value=None
        ):
            from app.db.models import TradeSideEnum

            mock_persist.side_effect = lambda db, uid, ev, fee_quote_value=None: (
                MagicMock(id=ev.id, side=TradeSideEnum.BUY, timestamp=ev.timestamp)
            )

            result = service.sync_fills(mock_db, "user_1", "BTCEUR")

        assert result["last_synced_source_id"] == "999"

    def test_sync_fills_backward_compat_keys(self):
        """Response still has status, new_fills, new_lots, allocations, errors, message keys."""
        service, mock_binance = self._setup_sync_service()
        mock_db = MagicMock()

        fills = [self._make_buy_event("601", datetime(2024, 6, 1, 10, 0))]
        mock_binance.fetch_trades.return_value = fills
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "app.services.sync_service.persist_ledger_event"
        ) as mock_persist, patch(
            "app.services.sync_service.create_lot_from_buy_fill"
        ), patch(
            "app.services.sync_service.compute_fee_quote_value", return_value=None
        ):
            from app.db.models import TradeSideEnum

            mock_persist.side_effect = lambda db, uid, ev, fee_quote_value=None: (
                MagicMock(id=ev.id, side=TradeSideEnum.BUY, timestamp=ev.timestamp)
            )

            result = service.sync_fills(mock_db, "user_1", "BTCEUR")

        # All backward-compat keys present
        for key in [
            "status",
            "new_fills",
            "new_lots",
            "allocations",
            "errors",
            "message",
        ]:
            assert key in result, f"Missing backward-compat key: {key}"


# ============================================================
# SYNC-02 Verification: Phase 5 retry wiring smoke test
# ============================================================


class TestSyncRetryWiring:
    """Verify Phase 5 retry infrastructure is wired into sync flow."""

    def test_sync_fills_transient_error_is_retried(self):
        """
        Mock _fetch_trades_page to raise transient error on first call,
        return fills on second call. Verify sync_fills succeeds.
        Confirms Phase 5 @retry_on_transient_error is wired end-to-end.
        """
        import requests

        from app.services.binance import BinanceService

        # Create a real BinanceService with mocked client
        mock_client = MagicMock()
        binance_service = BinanceService.__new__(BinanceService)
        binance_service.client = mock_client
        binance_service.timeout = 10

        # _fetch_trades_page has @retry_on_transient_error
        # On first call: transient ConnectionError -> retry
        # On second call: return a valid trade dict
        mock_trade = {
            "id": 12345,
            "orderId": 99999,
            "symbol": "BTCEUR",
            "price": "50000.00",
            "qty": "0.01",
            "quoteQty": "500.00",
            "commission": "0.00001",
            "commissionAsset": "BTC",
            "time": 1717236000000,
            "isBuyer": True,
            "isMaker": False,
        }

        # Mock get_my_trades to fail first, then succeed
        mock_client.get_my_trades.side_effect = [
            requests.ConnectionError("transient network failure"),
            [mock_trade],
        ]

        # Call fetch_trades (which calls _fetch_trades_page internally)
        # The retry decorator should handle the transient error
        with patch("time.sleep"):  # Don't actually wait
            fills = binance_service.fetch_trades("BTCEUR")

        assert len(fills) == 1
        assert fills[0].source_id == "12345"
        # Verify get_my_trades was called twice (first failed, second succeeded)
        assert mock_client.get_my_trades.call_count == 2
