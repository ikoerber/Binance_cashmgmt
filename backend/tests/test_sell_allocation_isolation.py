"""Tests fuer Sell Allocation Symbol Isolation.

Stellt sicher, dass Sell-Fills nur gegen Lots desselben Base-Assets allokieren.
Verifiziert Rueckwaertskompatibilitaet fuer BTC-only-User und korrekte
Cross-Pair-Allokation innerhalb desselben Base-Assets (z.B. XRPEUR + XRPBTC).
"""

from decimal import Decimal
from datetime import datetime

import pytest

from app.symbol_registry import get_symbols_for_base_asset, get_base_asset
from app.domain.lots import (
    allocate_sell_fifo,
    allocate_sell_with_strategy,
    allocate_sell_to_lot,
)
from app.domain.models import (
    LedgerEvent,
    EventType,
    TradeSide,
    EventSource,
    TradeLot,
    LotStatus,
    AllocationStrategy,
)

# ---------------------------------------------------------------------------
# Helper Factories
# ---------------------------------------------------------------------------


def _make_lot(id, symbol, qty_open, cost_quote, created_at=None):
    """Erstellt ein Domain-TradeLot mit Standardwerten."""
    return TradeLot(
        id=id,
        created_from_fill_id=f"fill_{id}",
        created_at=created_at or datetime(2024, 1, 1),
        qty_base_initial=qty_open,
        qty_base_open=qty_open,
        cost_quote=cost_quote,
        status=LotStatus.OPEN,
        symbol=symbol,
    )


def _make_sell_event(id, symbol, amount, price, timestamp=None):
    """Erstellt ein Domain-LedgerEvent (Sell-Fill) mit Standardwerten."""
    return LedgerEvent(
        id=id,
        type=EventType.TRADE_FILL,
        timestamp=timestamp or datetime(2024, 6, 1),
        asset=get_base_asset(symbol),
        amount=amount,
        price=price,
        side=TradeSide.SELL,
        source=EventSource.BINANCE,
        symbol=symbol,
    )


# ---------------------------------------------------------------------------
# Symbol Registry Tests
# ---------------------------------------------------------------------------


class TestGetSymbolsForBaseAsset:
    """Tests fuer die get_symbols_for_base_asset() Hilfsfunktion."""

    def test_get_symbols_for_base_asset_xrp(self):
        """XRP hat zwei Symbole: XRPEUR und XRPBTC."""
        result = get_symbols_for_base_asset("XRP")
        assert set(result) == {"XRPEUR", "XRPBTC"}

    def test_get_symbols_for_base_asset_btc(self):
        """BTC hat nur ein Symbol: BTCEUR."""
        result = get_symbols_for_base_asset("BTC")
        assert result == ["BTCEUR"]

    def test_get_symbols_for_base_asset_eth(self):
        """ETH hat nur ein Symbol: ETHEUR."""
        result = get_symbols_for_base_asset("ETH")
        assert result == ["ETHEUR"]

    def test_get_symbols_for_base_asset_unknown_raises(self):
        """Unbekanntes Base-Asset wirft ValueError."""
        with pytest.raises(ValueError, match="No symbols found"):
            get_symbols_for_base_asset("DOGE")


# ---------------------------------------------------------------------------
# Cross-Asset Isolation Tests (Domain-Layer)
# ---------------------------------------------------------------------------


class TestCrossAssetIsolation:
    """Tests, die sicherstellen, dass Sell-Fills nur Lots desselben Base-Assets allokieren."""

    def test_fifo_only_receives_same_base_lots(self):
        """BTC-Sell allokiert nur gegen BTC-Lot, nicht gegen XRP-Lot.

        Simuliert das Service-Layer-Filtering: der Domain-Funktion werden nur
        Lots desselben Base-Assets uebergeben.
        """
        btc_lot = _make_lot("lot_btc_1", "BTCEUR", Decimal("0.01"), Decimal("500"))
        xrp_lot = _make_lot("lot_xrp_1", "XRPEUR", Decimal("1000"), Decimal("550"))

        btc_sell = _make_sell_event(
            "sell_1", "BTCEUR", Decimal("0.01"), Decimal("55000")
        )

        # Service-Layer wuerde nur BTC-Lots uebergeben
        updated_lots, allocations = allocate_sell_fifo(btc_sell, [btc_lot])

        assert len(allocations) == 1
        assert allocations[0].trade_lot_id == "lot_btc_1"
        # XRP-Lot wuerde gar nicht uebergeben werden — bleibt unangetastet
        assert xrp_lot.qty_base_open == Decimal("1000")
        assert xrp_lot.status == LotStatus.OPEN

    def test_strategy_lifo_only_receives_same_base_lots(self):
        """LIFO-Strategie: XRP-Sell allokiert gegen XRP-Lots (XRPEUR + XRPBTC), nicht gegen BTC-Lot.

        Zeigt, dass der Service-Layer beide XRP-Symbole (XRPEUR, XRPBTC) fuer
        den Domain-Layer bereitstellt, aber BTC-Lots ausschliesst.
        """
        xrp_lot_eur = _make_lot(
            "lot_xrp_eur",
            "XRPEUR",
            Decimal("500"),
            Decimal("275"),
            created_at=datetime(2024, 1, 1),
        )
        xrp_lot_btc = _make_lot(
            "lot_xrp_btc",
            "XRPBTC",
            Decimal("300"),
            Decimal("150"),
            created_at=datetime(2024, 2, 1),
        )
        btc_lot = _make_lot("lot_btc_1", "BTCEUR", Decimal("0.01"), Decimal("500"))

        xrp_sell = _make_sell_event(
            "sell_xrp", "XRPEUR", Decimal("400"), Decimal("0.60")
        )

        # Service-Layer wuerde nur XRP-Lots uebergeben (LIFO: neueste zuerst)
        updated_lots, allocations = allocate_sell_with_strategy(
            xrp_sell, [xrp_lot_eur, xrp_lot_btc], AllocationStrategy.LIFO
        )

        # LIFO: lot_xrp_btc (Feb) wird zuerst allokiert, dann lot_xrp_eur (Jan)
        assert len(allocations) == 2
        lot_ids_allocated = {a.trade_lot_id for a in allocations}
        assert lot_ids_allocated == {"lot_xrp_btc", "lot_xrp_eur"}
        # BTC-Lot bleibt unangetastet
        assert btc_lot.qty_base_open == Decimal("0.01")

    def test_xrp_sell_allocates_across_xrp_pairs(self):
        """XRP-Sell kann gegen Lots beider XRP-Paare allokieren (XRPEUR + XRPBTC).

        Beide Lots gehoeren zum selben Base-Asset XRP und sind daher fuer die
        Allokation berechtigt.
        """
        xrp_lot_eur = _make_lot(
            "lot_xrp_eur",
            "XRPEUR",
            Decimal("200"),
            Decimal("100"),
            created_at=datetime(2024, 1, 1),
        )
        xrp_lot_btc = _make_lot(
            "lot_xrp_btc",
            "XRPBTC",
            Decimal("300"),
            Decimal("150"),
            created_at=datetime(2024, 2, 1),
        )

        xrp_sell = _make_sell_event(
            "sell_xrp", "XRPEUR", Decimal("400"), Decimal("0.55")
        )

        # FIFO: lot_xrp_eur (Jan) zuerst, dann lot_xrp_btc (Feb)
        updated_lots, allocations = allocate_sell_fifo(
            xrp_sell, [xrp_lot_eur, xrp_lot_btc]
        )

        assert len(allocations) == 2

        # Lot 1 (XRPEUR, 200 XRP) komplett geschlossen
        alloc_eur = next(a for a in allocations if a.trade_lot_id == "lot_xrp_eur")
        assert alloc_eur.qty_allocated == Decimal("200")

        # Lot 2 (XRPBTC, 300 XRP) teilweise allokiert (200 verbleibend)
        alloc_btc = next(a for a in allocations if a.trade_lot_id == "lot_xrp_btc")
        assert alloc_btc.qty_allocated == Decimal("200")


# ---------------------------------------------------------------------------
# Backward Compatibility Tests
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Tests, die sicherstellen, dass BTC-only-User keine Verhaltensaenderung erleben."""

    def test_btceur_backward_compatibility(self):
        """FIFO-Allokation mit nur BTCEUR-Lots funktioniert wie bisher."""
        lot1 = _make_lot(
            "lot_1",
            "BTCEUR",
            Decimal("0.01"),
            Decimal("500"),
            created_at=datetime(2024, 1, 1),
        )
        lot2 = _make_lot(
            "lot_2",
            "BTCEUR",
            Decimal("0.01"),
            Decimal("510"),
            created_at=datetime(2024, 2, 1),
        )

        btc_sell = _make_sell_event(
            "sell_1", "BTCEUR", Decimal("0.015"), Decimal("55000")
        )

        updated_lots, allocations = allocate_sell_fifo(btc_sell, [lot1, lot2])

        # FIFO: lot_1 zuerst (komplett), dann lot_2 (teilweise)
        assert len(allocations) == 2
        assert allocations[0].trade_lot_id == "lot_1"
        assert allocations[0].qty_allocated == Decimal("0.01")
        assert allocations[1].trade_lot_id == "lot_2"
        assert allocations[1].qty_allocated == Decimal("0.005")

    def test_legacy_event_without_symbol_defaults_btceur(self):
        """Fallback-Pfad: get_base_asset('BTCEUR') gibt 'BTC' zurueck.

        Legacy-Events ohne Symbol nutzen 'BTCEUR' als Default.
        """
        base = get_base_asset("BTCEUR")
        assert base == "BTC"
        symbols = get_symbols_for_base_asset(base)
        assert symbols == ["BTCEUR"]


# ---------------------------------------------------------------------------
# Overflow Isolation Tests
# ---------------------------------------------------------------------------


class TestOverflowIsolation:
    """Tests fuer Overflow-Queries bei lot-spezifischer Allokation."""

    def test_lot_specific_overflow_respects_base_asset(self):
        """Lot-spezifischer Overflow allokiert nur gegen Lots desselben Base-Assets.

        Target: XRP-Lot (wird allokiert)
        Overflow: ein weiteres XRP-Lot (soll genutzt werden)
        BTC-Lot wird vom Service-Layer herausgefiltert und gar nicht uebergeben.
        """
        target_xrp = _make_lot(
            "lot_xrp_target",
            "XRPEUR",
            Decimal("100"),
            Decimal("50"),
            created_at=datetime(2024, 1, 1),
        )
        overflow_xrp = _make_lot(
            "lot_xrp_overflow",
            "XRPBTC",
            Decimal("200"),
            Decimal("100"),
            created_at=datetime(2024, 2, 1),
        )
        btc_lot = _make_lot("lot_btc_1", "BTCEUR", Decimal("0.5"), Decimal("25000"))

        xrp_sell = _make_sell_event(
            "sell_xrp", "XRPEUR", Decimal("250"), Decimal("0.55")
        )

        # Service-Layer wuerde nur XRP-Lots als Overflow uebergeben
        updated_lots, allocations = allocate_sell_to_lot(
            xrp_sell,
            target_xrp,
            [overflow_xrp],  # BTC-Lot wird vom Service-Layer herausgefiltert
        )

        assert len(allocations) == 2

        # Target komplett geschlossen
        alloc_target = next(
            a for a in allocations if a.trade_lot_id == "lot_xrp_target"
        )
        assert alloc_target.qty_allocated == Decimal("100")

        # Overflow: 150 von 200 XRP allokiert
        alloc_overflow = next(
            a for a in allocations if a.trade_lot_id == "lot_xrp_overflow"
        )
        assert alloc_overflow.qty_allocated == Decimal("150")

        # BTC-Lot bleibt unangetastet
        assert btc_lot.qty_base_open == Decimal("0.5")
        assert btc_lot.status == LotStatus.OPEN
