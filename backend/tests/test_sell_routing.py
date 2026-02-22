"""
Tests for cross-pair sell routing domain logic.

- compute_cross_pair_realized_pnl_eur(): EUR-normalized realized P&L for cross-pair sell allocation
- RoutingDecision dataclass: Audit record for routing decisions
- compute_pairing_order_params(): Symbol-aware client_order_id and EUR max-value check
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.lots import compute_cross_pair_realized_pnl_eur
from app.domain.models import RoutingDecision, PairingItem


# ---------------------------------------------------------------------------
# Group 1: compute_cross_pair_realized_pnl_eur()
# ---------------------------------------------------------------------------


class TestCrossPairPnlEurSell:
    """Sell on EUR-quoted pair."""

    def test_cross_pair_pnl_sell_xrpeur_lot_xrpeur(self):
        """Sell on XRPEUR, lot from XRPEUR. No conversion needed."""
        result = compute_cross_pair_realized_pnl_eur(
            qty_allocated=Decimal("50"),
            net_proceeds_per_base=Decimal("2.20"),  # EUR/XRP
            sell_quote_asset="EUR",
            lot_cost_eur=Decimal("100"),
            lot_qty_base_initial=Decimal("50"),
            btceur_rate=None,
        )
        # proceeds: 2.20 * 50 = 110, cost: (100/50) * 50 = 100, P&L = 10
        assert result == Decimal("10")

    def test_cross_pair_pnl_sell_xrpeur_lot_xrpbtc(self):
        """Sell on XRPEUR, lot from XRPBTC. Cost uses lot.cost_eur."""
        result = compute_cross_pair_realized_pnl_eur(
            qty_allocated=Decimal("30"),
            net_proceeds_per_base=Decimal("2.20"),  # EUR/XRP
            sell_quote_asset="EUR",
            lot_cost_eur=Decimal("90"),  # EUR equivalent of BTC cost
            lot_qty_base_initial=Decimal("50"),
            btceur_rate=None,
        )
        # proceeds: 2.20 * 30 = 66, cost: (90/50) * 30 = 54, P&L = 12
        assert result == Decimal("12")


class TestCrossPairPnlBtcSell:
    """Sell on BTC-quoted pair -- requires btceur_rate conversion."""

    def test_cross_pair_pnl_sell_xrpbtc_lot_xrpeur(self):
        """Sell on XRPBTC, lot from XRPEUR. BTC proceeds converted to EUR."""
        result = compute_cross_pair_realized_pnl_eur(
            qty_allocated=Decimal("50"),
            net_proceeds_per_base=Decimal("0.0000275"),  # BTC/XRP
            sell_quote_asset="BTC",
            lot_cost_eur=Decimal("100"),
            lot_qty_base_initial=Decimal("50"),
            btceur_rate=Decimal("80000"),
        )
        # EUR proceeds: 0.0000275 * 80000 * 50 = 110, cost: (100/50) * 50 = 100, P&L = 10
        assert result == Decimal("10")

    def test_cross_pair_pnl_loss_scenario(self):
        """Sell at a loss -- negative P&L."""
        result = compute_cross_pair_realized_pnl_eur(
            qty_allocated=Decimal("50"),
            net_proceeds_per_base=Decimal("0.0000200"),  # BTC/XRP
            sell_quote_asset="BTC",
            lot_cost_eur=Decimal("120"),
            lot_qty_base_initial=Decimal("50"),
            btceur_rate=Decimal("80000"),
        )
        # EUR proceeds: 0.0000200 * 80000 * 50 = 80, cost: (120/50) * 50 = 120, P&L = -40
        assert result == Decimal("-40")

    def test_cross_pair_pnl_btc_sell_requires_btceur_rate(self):
        """BTC sell without btceur_rate raises ValueError."""
        with pytest.raises(ValueError, match="btceur_rate required"):
            compute_cross_pair_realized_pnl_eur(
                qty_allocated=Decimal("50"),
                net_proceeds_per_base=Decimal("0.0000275"),
                sell_quote_asset="BTC",
                lot_cost_eur=Decimal("100"),
                lot_qty_base_initial=Decimal("50"),
                btceur_rate=None,
            )


class TestCrossPairPnlEdgeCases:
    """Edge cases for cross-pair P&L computation."""

    def test_cross_pair_pnl_zero_qty(self):
        """Zero qty_allocated returns Decimal('0')."""
        result = compute_cross_pair_realized_pnl_eur(
            qty_allocated=Decimal("0"),
            net_proceeds_per_base=Decimal("2.20"),
            sell_quote_asset="EUR",
            lot_cost_eur=Decimal("100"),
            lot_qty_base_initial=Decimal("50"),
        )
        assert result == Decimal("0")

    def test_cross_pair_pnl_partial_allocation(self):
        """Partial allocation uses proportional cost."""
        result = compute_cross_pair_realized_pnl_eur(
            qty_allocated=Decimal("25"),  # half of 50 XRP lot
            net_proceeds_per_base=Decimal("2.20"),  # EUR/XRP
            sell_quote_asset="EUR",
            lot_cost_eur=Decimal("100"),  # total lot cost
            lot_qty_base_initial=Decimal("50"),
        )
        # cost_per_unit = 100/50 = 2.0, cost_portion = 2.0 * 25 = 50
        # proceeds = 2.20 * 25 = 55, P&L = 55 - 50 = 5
        assert result == Decimal("5")


# ---------------------------------------------------------------------------
# Group 2: RoutingDecision dataclass
# ---------------------------------------------------------------------------


class TestRoutingDecision:
    """RoutingDecision dataclass stores audit fields and serializes."""

    def test_routing_decision_creation(self):
        """Create RoutingDecision with all fields, verify storage."""
        ts = datetime(2026, 2, 22, 10, 30, 0)
        rd = RoutingDecision(
            selected_route="XRPBTC",
            xrpeur_price=Decimal("2.20"),
            xrpbtc_price=Decimal("0.0000275"),
            btceur_price=Decimal("80000"),
            direct_net_eur=Decimal("109.89"),
            indirect_net_eur=Decimal("110.12"),
            eur_difference=Decimal("0.23"),
            timestamp=ts,
        )
        assert rd.selected_route == "XRPBTC"
        assert rd.xrpeur_price == Decimal("2.20")
        assert rd.xrpbtc_price == Decimal("0.0000275")
        assert rd.btceur_price == Decimal("80000")
        assert rd.direct_net_eur == Decimal("109.89")
        assert rd.indirect_net_eur == Decimal("110.12")
        assert rd.eur_difference == Decimal("0.23")
        assert rd.timestamp == ts

    def test_routing_decision_to_dict(self):
        """to_dict() returns JSON-serializable dict with Decimal as strings."""
        ts = datetime(2026, 2, 22, 10, 30, 0)
        rd = RoutingDecision(
            selected_route="XRPEUR",
            xrpeur_price=Decimal("2.20"),
            xrpbtc_price=Decimal("0.0000275"),
            btceur_price=Decimal("80000"),
            direct_net_eur=Decimal("109.89"),
            indirect_net_eur=Decimal("108.50"),
            eur_difference=Decimal("1.39"),
            timestamp=ts,
        )
        d = rd.to_dict()
        assert d["selected_route"] == "XRPEUR"
        assert d["xrpeur_price"] == "2.20"
        assert d["xrpbtc_price"] == "0.0000275"
        assert d["btceur_price"] == "80000"
        assert d["direct_net_eur"] == "109.89"
        assert d["indirect_net_eur"] == "108.50"
        assert d["eur_difference"] == "1.39"
        assert d["timestamp"] == "2026-02-22T10:30:00"
        # Ensure all values are JSON-serializable (str, not Decimal)
        for key, val in d.items():
            assert isinstance(val, str), f"{key} should be str, got {type(val)}"


# ---------------------------------------------------------------------------
# Group 3: compute_pairing_order_params fixes
# ---------------------------------------------------------------------------


class TestPairingOrderParamsRouting:
    """Symbol-aware client_order_id and EUR max-value check."""

    def _make_items(self, qty=Decimal("50")):
        """Helper: create a list of PairingItem for testing."""
        return [PairingItem(lot_id="lot_1", qty_base=qty, cost_quote=Decimal("100"))]

    def test_pairing_order_params_xrpbtc_client_order_id_no_collision(self):
        """Two XRPBTC calls with different sub-1 prices produce different client_order_ids."""
        from app.domain.orders import compute_pairing_order_params

        params_a = compute_pairing_order_params(
            pairing_id="pair_abc",
            user_id="u1",
            items=self._make_items(),
            market_price=Decimal("0.00002300"),
            symbol="XRPBTC",
        )
        params_b = compute_pairing_order_params(
            pairing_id="pair_abc",
            user_id="u1",
            items=self._make_items(),
            market_price=Decimal("0.00002500"),
            symbol="XRPBTC",
        )
        assert params_a["newClientOrderId"] != params_b["newClientOrderId"]

    def test_pairing_order_params_xrpeur_unchanged(self):
        """Existing XRPEUR behavior: target_price > 1.0, client_order_id works."""
        from app.domain.orders import compute_pairing_order_params

        params = compute_pairing_order_params(
            pairing_id="pair_xyz",
            user_id="u1",
            items=self._make_items(),
            market_price=Decimal("2.20"),
            symbol="XRPEUR",
        )
        assert params["symbol"] == "XRPEUR"
        assert params["side"] == "SELL"
        assert "newClientOrderId" in params
        # Price should be quantized to 4 decimal places (XRPEUR price_precision=4)
        price_str = params["price"]
        # Verify it has up to 4 decimal places
        parts = price_str.split(".")
        assert len(parts) == 2
        assert len(parts[1]) <= 4

    def test_pairing_order_params_max_value_eur_conversion(self):
        """For XRPBTC orders, order_value_eur uses btceur_rate to convert to EUR."""
        from app.domain.orders import compute_pairing_order_params

        params = compute_pairing_order_params(
            pairing_id="pair_abc",
            user_id="u1",
            items=self._make_items(qty=Decimal("50")),
            market_price=Decimal("0.00002500"),
            symbol="XRPBTC",
            btceur_rate=Decimal("80000"),
            max_order_value_eur=Decimal("1000"),
        )
        # order_value in BTC = 50 * 0.00002500... ~= 0.00125 BTC
        # order_value_eur = 0.00125 * 80000 = 100 EUR (under 1000 limit)
        order_value_eur = Decimal(params["order_value_eur"])
        assert order_value_eur > Decimal("0")
        # Should be about 100 EUR, definitely under 1000
        assert params["exceeds_max_order_value"] is False

    def test_pairing_order_params_symbol_precision(self):
        """XRPBTC uses price_precision=8, XRPEUR uses price_precision=4."""
        from app.domain.orders import compute_pairing_order_params

        params_btc = compute_pairing_order_params(
            pairing_id="pair_a",
            user_id="u1",
            items=self._make_items(),
            market_price=Decimal("0.00002345"),
            symbol="XRPBTC",
        )
        params_eur = compute_pairing_order_params(
            pairing_id="pair_b",
            user_id="u1",
            items=self._make_items(),
            market_price=Decimal("2.20"),
            symbol="XRPEUR",
        )
        # XRPBTC: price should have up to 8 decimal places
        price_btc = params_btc["price"]
        parts_btc = price_btc.split(".")
        assert len(parts_btc) == 2
        assert len(parts_btc[1]) <= 8

        # XRPEUR: price should have up to 4 decimal places
        price_eur = params_eur["price"]
        parts_eur = price_eur.split(".")
        assert len(parts_eur) == 2
        assert len(parts_eur[1]) <= 4
