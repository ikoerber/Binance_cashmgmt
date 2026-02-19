"""
Unit Tests für sync_and_refresh_lots

Testet die Kombination Binance-Sync + Lot-Rückgabe
ohne echte DB/Binance-Abhängigkeit.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.domain.models import LedgerEvent, EventType, EventSource, TradeSide


def _make_buy_fill(
    fill_id: str, qty: str, price: str, timestamp: datetime
) -> LedgerEvent:
    """Hilfsfunktion: erstellt Buy-Fill LedgerEvent"""
    return LedgerEvent(
        id=f"binance_BTCEUR_{fill_id}",
        type=EventType.TRADE_FILL,
        timestamp=timestamp,
        asset="BTC",
        amount=Decimal(qty),
        symbol="BTCEUR",
        price=Decimal(price),
        side=TradeSide.BUY,
        source=EventSource.BINANCE,
        source_id=fill_id,
    )


def _make_sell_fill(
    fill_id: str, qty: str, price: str, timestamp: datetime
) -> LedgerEvent:
    """Hilfsfunktion: erstellt Sell-Fill LedgerEvent"""
    return LedgerEvent(
        id=f"binance_BTCEUR_{fill_id}",
        type=EventType.TRADE_FILL,
        timestamp=timestamp,
        asset="BTC",
        amount=Decimal(qty),
        symbol="BTCEUR",
        price=Decimal(price),
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
        source_id=fill_id,
    )


class TestSyncAndRefreshLotsUnit:
    """Unit Tests für die Sync-Logik ohne DB"""

    def test_sync_service_called_with_correct_params(self):
        """Prüft, dass SyncService.sync_fills korrekt aufgerufen wird"""
        from app.services.lot_service import sync_and_refresh_lots

        mock_db = MagicMock()
        mock_binance = MagicMock()
        mock_sync_report = {
            "status": "success",
            "new_fills": 2,
            "new_lots": 1,
            "allocations": 1,
            "errors": [],
            "message": "Synced 2 fills",
        }

        # Mock get_lots_for_user
        mock_lots = [
            {"id": "lot_1", "qty_base_open": "0.01", "status": "OPEN"},
        ]

        with patch("app.services.sync_service.SyncService") as MockSyncClass, patch(
            "app.services.lot_service.get_lots_for_user", return_value=mock_lots
        ):
            mock_sync_instance = MockSyncClass.return_value
            mock_sync_instance.sync_fills.return_value = mock_sync_report

            result = sync_and_refresh_lots(
                mock_db, "user_1", mock_binance, "BTCEUR", None
            )

            # SyncService wurde mit BinanceService initialisiert
            MockSyncClass.assert_called_once_with(mock_binance)

            # sync_fills wurde aufgerufen
            mock_sync_instance.sync_fills.assert_called_once_with(
                mock_db, "user_1", "BTCEUR", None
            )

            # Ergebnis enthält sync_report und lots
            assert result["sync_report"] == mock_sync_report
            assert result["lots"] == mock_lots
            assert result["lots_count"] == 1

    def test_sync_no_new_fills_returns_existing_lots(self):
        """Auch ohne neue Fills werden aktuelle Lots zurückgegeben"""
        from app.services.lot_service import sync_and_refresh_lots

        mock_db = MagicMock()
        mock_binance = MagicMock()
        mock_sync_report = {
            "status": "success",
            "new_fills": 0,
            "new_lots": 0,
            "allocations": 0,
            "message": "No new fills to sync",
        }

        mock_lots = [
            {"id": "lot_1", "status": "OPEN"},
            {"id": "lot_2", "status": "CLOSED"},
        ]

        with patch("app.services.sync_service.SyncService") as MockSyncClass, patch(
            "app.services.lot_service.get_lots_for_user", return_value=mock_lots
        ):
            mock_sync_instance = MockSyncClass.return_value
            mock_sync_instance.sync_fills.return_value = mock_sync_report

            result = sync_and_refresh_lots(mock_db, "user_1", mock_binance)

            assert result["sync_report"]["new_fills"] == 0
            assert result["lots_count"] == 2

    def test_sync_with_start_time(self):
        """start_time wird korrekt durchgereicht"""
        from app.services.lot_service import sync_and_refresh_lots

        mock_db = MagicMock()
        mock_binance = MagicMock()
        start_dt = datetime(2024, 6, 1)

        with patch("app.services.sync_service.SyncService") as MockSyncClass, patch(
            "app.services.lot_service.get_lots_for_user", return_value=[]
        ):
            mock_sync_instance = MockSyncClass.return_value
            mock_sync_instance.sync_fills.return_value = {
                "status": "success",
                "new_fills": 0,
                "new_lots": 0,
                "allocations": 0,
                "message": "",
            }

            sync_and_refresh_lots(mock_db, "user_1", mock_binance, "BTCEUR", start_dt)

            mock_sync_instance.sync_fills.assert_called_once_with(
                mock_db, "user_1", "BTCEUR", start_dt
            )
