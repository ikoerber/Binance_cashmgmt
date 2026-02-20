"""
Tests for Cross-Pair Pairing Domain Logic

Tests EUR-normalized P&L heuristic, dual-route comparison,
and model extensions for mixed-symbol pairings (e.g., XRPEUR + XRPBTC).
Backward compatibility with existing single-pair behavior is verified.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from app.domain.models import (
    TradeLot,
    LotStatus,
    Pairing,
    PairingItem,
    PairingStatus,
    RouteDetails,
    DualRouteComparison,
)
from app.domain.pairing import suggest_pairings, compute_dual_route_comparison


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lot(
    lot_id: str,
    symbol: str,
    qty: str,
    cost_quote: str,
    cost_eur: str | None = None,
    created_at: datetime | None = None,
) -> TradeLot:
    """Helper to build a TradeLot for testing."""
    return TradeLot(
        id=lot_id,
        created_from_fill_id=f"fill_{lot_id}",
        created_at=created_at or datetime(2024, 1, 1),
        qty_base_initial=Decimal(qty),
        qty_base_open=Decimal(qty),
        cost_quote=Decimal(cost_quote),
        cost_eur=Decimal(cost_eur) if cost_eur is not None else None,
        quote_to_eur_rate=Decimal("1") if cost_eur == cost_quote else None,
        status=LotStatus.OPEN,
        symbol=symbol,
    )


# ===========================================================================
# 1. Model Extensions
# ===========================================================================


class TestPairingItemModelExtensions:
    """PairingItem new fields: cost_eur, lot_symbol."""

    def test_pairing_item_has_cost_eur_field(self):
        """PairingItem should support optional cost_eur."""
        item = PairingItem(
            lot_id="lot-1",
            qty_base=Decimal("100"),
            cost_quote=Decimal("50"),
            cost_eur=Decimal("50"),
            lot_symbol="XRPEUR",
        )
        assert item.cost_eur == Decimal("50")
        assert item.lot_symbol == "XRPEUR"

    def test_pairing_item_defaults_none(self):
        """PairingItem cost_eur and lot_symbol default to None."""
        item = PairingItem(
            lot_id="lot-1",
            qty_base=Decimal("100"),
            cost_quote=Decimal("50"),
        )
        assert item.cost_eur is None
        assert item.lot_symbol is None


class TestPairingModelExtensions:
    """Pairing new field: base_asset, is_cross_pair, net_cost_eur."""

    def test_pairing_base_asset_field(self):
        """Pairing should support optional base_asset."""
        pairing = Pairing(
            id="p1",
            items=[],
            threshold_pct=Decimal("0.05"),
            symbol="XRPEUR",
            base_asset="XRP",
        )
        assert pairing.base_asset == "XRP"

    def test_pairing_base_asset_default_none(self):
        """Pairing base_asset defaults to None (single-pair)."""
        pairing = Pairing(
            id="p1",
            items=[],
            threshold_pct=Decimal("0.05"),
        )
        assert pairing.base_asset is None

    def test_is_cross_pair_true(self):
        """is_cross_pair returns True when base_asset is set."""
        pairing = Pairing(
            id="p1",
            items=[],
            threshold_pct=Decimal("0.05"),
            base_asset="XRP",
        )
        assert pairing.is_cross_pair is True

    def test_is_cross_pair_false(self):
        """is_cross_pair returns False when base_asset is None."""
        pairing = Pairing(
            id="p1",
            items=[],
            threshold_pct=Decimal("0.05"),
        )
        assert pairing.is_cross_pair is False

    def test_net_cost_eur_returns_sum(self):
        """net_cost_eur sums item.cost_eur values."""
        items = [
            PairingItem("lot-1", Decimal("100"), Decimal("50"), cost_eur=Decimal("50")),
            PairingItem("lot-2", Decimal("200"), Decimal("0.005"), cost_eur=Decimal("400")),
        ]
        pairing = Pairing(
            id="p1",
            items=items,
            threshold_pct=Decimal("0.05"),
            base_asset="XRP",
        )
        assert pairing.net_cost_eur() == Decimal("450")

    def test_net_cost_eur_returns_none_if_any_missing(self):
        """net_cost_eur returns None if any item lacks cost_eur."""
        items = [
            PairingItem("lot-1", Decimal("100"), Decimal("50"), cost_eur=Decimal("50")),
            PairingItem("lot-2", Decimal("200"), Decimal("0.005")),  # no cost_eur
        ]
        pairing = Pairing(
            id="p1",
            items=items,
            threshold_pct=Decimal("0.05"),
            base_asset="XRP",
        )
        assert pairing.net_cost_eur() is None


# ===========================================================================
# 2. suggest_pairings with use_eur_cost=True (Cross-Pair Mode)
# ===========================================================================


class TestSuggestPairingsCrossPair:
    """Tests for suggest_pairings() with use_eur_cost=True."""

    def test_cross_pair_basic(self):
        """2 XRPEUR lots + 1 XRPBTC lot, use_eur_cost=True -> pairing uses cost_eur."""
        # XRP price in EUR = 0.50
        market_price_eur = Decimal("0.50")

        # Lot 1: XRPEUR, bought at 0.40 EUR -> +25% profit
        lot1 = _make_lot("lot-1", "XRPEUR", "100", "40", cost_eur="40",
                         created_at=datetime(2024, 1, 1))
        # Lot 2: XRPEUR, bought at 0.60 EUR -> -16.7% loss
        lot2 = _make_lot("lot-2", "XRPEUR", "100", "60", cost_eur="60",
                         created_at=datetime(2024, 1, 2))
        # Lot 3: XRPBTC, bought at 0.000008 BTC, cost_eur=45 -> +11.1% profit
        lot3 = _make_lot("lot-3", "XRPBTC", "100", "0.0008", cost_eur="45",
                         created_at=datetime(2024, 1, 3))

        pairings = suggest_pairings(
            [lot1, lot2, lot3], market_price_eur,
            threshold_pct=Decimal("0.05"),
            use_eur_cost=True,
        )

        # Expect at least one pairing containing lots from different symbols
        assert len(pairings) >= 1
        for p in pairings:
            assert p.base_asset == "XRP"
            assert p.is_cross_pair is True
            # All items should have cost_eur populated
            for item in p.items:
                assert item.cost_eur is not None
                assert item.lot_symbol is not None

    def test_cross_pair_uses_cost_eur_for_pnl(self):
        """P&L uses cost_eur (not cost_quote) in cross-pair mode."""
        market_price_eur = Decimal("0.50")

        # Winner: cost_eur=30 -> value=50 -> pnl=+66.7%
        lot1 = _make_lot("lot-1", "XRPEUR", "100", "30", cost_eur="30",
                         created_at=datetime(2024, 1, 1))
        # Loser: cost_eur=55 -> value=50 -> pnl=-9.1%
        lot2 = _make_lot("lot-2", "XRPBTC", "100", "0.001", cost_eur="55",
                         created_at=datetime(2024, 1, 2))

        pairings = suggest_pairings(
            [lot1, lot2], market_price_eur,
            threshold_pct=Decimal("0.05"),
            use_eur_cost=True,
        )

        # Combined: cost_eur=85, value=100, pnl=15/85=17.6% -> above threshold
        assert len(pairings) == 1
        p = pairings[0]
        # Verify P&L is calculated from EUR costs
        total_cost_eur = sum(item.cost_eur for item in p.items)
        total_value = market_price_eur * p.net_qty_base()
        pnl_pct = (total_value - total_cost_eur) / total_cost_eur
        assert pnl_pct >= Decimal("0.05")

    def test_cost_eur_none_raises_valueerror(self):
        """XRPBTC lot with cost_eur=None, use_eur_cost=True -> ValueError."""
        market_price_eur = Decimal("0.50")

        lot1 = _make_lot("lot-1", "XRPEUR", "100", "40", cost_eur="40")
        lot2 = _make_lot("lot-2", "XRPBTC", "100", "0.0008", cost_eur=None)

        with pytest.raises(ValueError, match="cost_eur"):
            suggest_pairings(
                [lot1, lot2], market_price_eur,
                threshold_pct=Decimal("0.05"),
                use_eur_cost=True,
            )

    def test_single_profitable_lot_no_pairing(self):
        """Single profitable lot, use_eur_cost=True -> no pairing (min 2 lots rule)."""
        market_price_eur = Decimal("0.50")
        lot1 = _make_lot("lot-1", "XRPEUR", "100", "30", cost_eur="30")

        pairings = suggest_pairings(
            [lot1], market_price_eur,
            threshold_pct=Decimal("0.05"),
            use_eur_cost=True,
        )
        assert len(pairings) == 0

    def test_pairing_item_fields_populated_in_cross_pair(self):
        """PairingItem.cost_eur and lot_symbol are populated in cross-pair mode."""
        market_price_eur = Decimal("0.50")

        lot1 = _make_lot("lot-1", "XRPEUR", "100", "30", cost_eur="30",
                         created_at=datetime(2024, 1, 1))
        lot2 = _make_lot("lot-2", "XRPBTC", "100", "0.001", cost_eur="55",
                         created_at=datetime(2024, 1, 2))

        pairings = suggest_pairings(
            [lot1, lot2], market_price_eur,
            threshold_pct=Decimal("0.05"),
            use_eur_cost=True,
        )
        assert len(pairings) >= 1
        for item in pairings[0].items:
            assert item.cost_eur is not None
            assert item.lot_symbol in ("XRPEUR", "XRPBTC")


# ===========================================================================
# 3. Backward Compatibility (use_eur_cost=False, default)
# ===========================================================================


class TestSuggestPairingsBackwardCompat:
    """Ensure use_eur_cost=False (default) preserves existing behavior."""

    def test_default_mode_identical_behavior(self):
        """All BTCEUR lots, use_eur_cost=False -> identical to current behavior."""
        market_price = Decimal("50000")

        # Winner: 40k cost -> +25%
        lot1 = _make_lot("lot-1", "BTCEUR", "0.01", "400",
                         created_at=datetime(2024, 1, 1))
        # Loser: 52k cost -> -3.85%
        lot2 = _make_lot("lot-2", "BTCEUR", "0.01", "520",
                         created_at=datetime(2024, 1, 2))

        # Call without use_eur_cost (default=False)
        pairings = suggest_pairings(
            [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
        )

        # Should produce pairing (break_even based cost)
        # Lot1: cost=0.01*40000=400, val=500 -> +25%
        # Lot2: cost=0.01*52000=520, val=500 -> -3.85%
        # Combined: cost=920, val=1000, pnl=80/920=8.7% -> above 5%
        assert len(pairings) >= 1
        p = pairings[0]
        assert p.base_asset is None  # NOT cross-pair
        assert p.is_cross_pair is False

    def test_three_positional_args_unchanged(self):
        """suggest_pairings(lots, price, threshold) with 3 positional args works."""
        market_price = Decimal("50000")
        lot1 = _make_lot("lot-1", "BTCEUR", "0.01", "400",
                         created_at=datetime(2024, 1, 1))
        lot2 = _make_lot("lot-2", "BTCEUR", "0.01", "520",
                         created_at=datetime(2024, 1, 2))

        # 3 positional args -- existing call signature
        pairings = suggest_pairings([lot1, lot2], market_price, Decimal("0.05"))
        assert len(pairings) >= 1

    def test_default_mode_no_cost_eur_on_items(self):
        """In default mode, PairingItem.cost_eur and lot_symbol should be None."""
        market_price = Decimal("50000")
        lot1 = _make_lot("lot-1", "BTCEUR", "0.01", "400",
                         created_at=datetime(2024, 1, 1))
        lot2 = _make_lot("lot-2", "BTCEUR", "0.01", "520",
                         created_at=datetime(2024, 1, 2))

        pairings = suggest_pairings(
            [lot1, lot2], market_price, threshold_pct=Decimal("0.05")
        )
        assert len(pairings) >= 1
        for item in pairings[0].items:
            assert item.cost_eur is None
            assert item.lot_symbol is None


# ===========================================================================
# 4. Dual-Route Comparison
# ===========================================================================


class TestDualRouteComparison:
    """Tests for compute_dual_route_comparison function."""

    def test_direct_route_calculation(self):
        """Direct route: gross = qty * xrpeur_price, net = gross - fees."""
        result = compute_dual_route_comparison(
            total_base=Decimal("1000"),
            xrpeur_price=Decimal("0.50"),
            xrpbtc_price=Decimal("0.000008"),
            btceur_price=Decimal("60000"),
            fee_pct=Decimal("0.001"),
        )
        # Direct: gross = 1000 * 0.50 = 500
        # fees = 500 * 0.001 = 0.50
        # net = 499.50
        assert result.route_direct.gross_proceeds_eur == Decimal("500")
        assert result.route_direct.fees_eur == Decimal("0.500")
        assert result.route_direct.net_proceeds_eur == Decimal("499.500")
        assert result.route_direct.symbol == "XRPEUR"
        assert result.route_direct.conversion_rate is None
        assert result.route_direct.fee_steps == 1

    def test_indirect_route_calculation(self):
        """Indirect route: two fee steps (XRPBTC sell, then BTCEUR sell)."""
        result = compute_dual_route_comparison(
            total_base=Decimal("1000"),
            xrpeur_price=Decimal("0.50"),
            xrpbtc_price=Decimal("0.000008"),
            btceur_price=Decimal("60000"),
            fee_pct=Decimal("0.001"),
        )
        # Indirect:
        # Step 1: gross_btc = 1000 * 0.000008 = 0.008
        #         fees_btc = 0.008 * 0.001 = 0.000008
        #         net_btc = 0.008 - 0.000008 = 0.007992
        # Step 2: gross_eur = 0.007992 * 60000 = 479.52
        #         fees_eur = 479.52 * 0.001 = 0.47952
        #         net_eur = 479.52 - 0.47952 = 479.04048
        assert result.route_indirect.symbol == "XRPBTC"
        assert result.route_indirect.conversion_rate == Decimal("60000")
        assert result.route_indirect.fee_steps == 2
        # net should be approximately 479.04
        assert result.route_indirect.net_proceeds_eur < Decimal("480")
        assert result.route_indirect.net_proceeds_eur > Decimal("479")

    def test_direct_better_than_indirect(self):
        """When direct yields more -> recommended='XRPEUR'."""
        result = compute_dual_route_comparison(
            total_base=Decimal("1000"),
            xrpeur_price=Decimal("0.50"),
            xrpbtc_price=Decimal("0.000008"),
            btceur_price=Decimal("60000"),
            fee_pct=Decimal("0.001"),
        )
        # Direct net ~499.50 > indirect net ~479.04
        assert result.recommended_route == "XRPEUR"
        assert result.eur_difference > Decimal("0")

    def test_indirect_better_than_direct(self):
        """When indirect yields more -> recommended='XRPBTC'."""
        # Make XRPBTC route more profitable: higher btceur_price
        result = compute_dual_route_comparison(
            total_base=Decimal("1000"),
            xrpeur_price=Decimal("0.48"),         # lower direct price
            xrpbtc_price=Decimal("0.000008"),
            btceur_price=Decimal("62000"),          # higher BTC/EUR -> indirect wins
            fee_pct=Decimal("0.001"),
        )
        # Direct: gross=480, net=480-0.48=479.52
        # Indirect: gross_btc=0.008, net_btc=0.007992, gross_eur=0.007992*62000=495.504
        #           net_eur=495.504-0.495504=495.008496
        assert result.recommended_route == "XRPBTC"
        assert result.eur_difference > Decimal("0")

    def test_eur_difference_is_absolute(self):
        """eur_difference is always positive (absolute value)."""
        result = compute_dual_route_comparison(
            total_base=Decimal("1000"),
            xrpeur_price=Decimal("0.50"),
            xrpbtc_price=Decimal("0.000008"),
            btceur_price=Decimal("60000"),
            fee_pct=Decimal("0.001"),
        )
        assert result.eur_difference >= Decimal("0")

    def test_route_details_dataclass(self):
        """RouteDetails dataclass has all expected fields."""
        rd = RouteDetails(
            symbol="XRPEUR",
            sell_price=Decimal("0.50"),
            gross_proceeds_eur=Decimal("500"),
            fees_eur=Decimal("0.50"),
            net_proceeds_eur=Decimal("499.50"),
            conversion_rate=None,
            fee_steps=1,
        )
        assert rd.symbol == "XRPEUR"
        assert rd.sell_price == Decimal("0.50")
        assert rd.conversion_rate is None
        assert rd.fee_steps == 1

    def test_dual_route_comparison_dataclass(self):
        """DualRouteComparison dataclass has all expected fields."""
        route_d = RouteDetails("XRPEUR", Decimal("0.50"), Decimal("500"),
                               Decimal("0.50"), Decimal("499.50"), None, 1)
        route_i = RouteDetails("XRPBTC", Decimal("0.000008"), Decimal("480"),
                               Decimal("0.96"), Decimal("479.04"), Decimal("60000"), 2)
        drc = DualRouteComparison(
            route_direct=route_d,
            route_indirect=route_i,
            recommended_route="XRPEUR",
            eur_difference=Decimal("20.46"),
        )
        assert drc.recommended_route == "XRPEUR"
        assert drc.eur_difference == Decimal("20.46")


# ===========================================================================
# 5. Edge Cases
# ===========================================================================


class TestCrossPairEdgeCases:
    """Edge cases for cross-pair pairing."""

    def test_empty_lots_returns_empty(self):
        """Empty lots list returns empty pairings in cross-pair mode."""
        pairings = suggest_pairings(
            [], Decimal("0.50"), threshold_pct=Decimal("0.05"), use_eur_cost=True
        )
        assert pairings == []

    def test_no_winners_returns_empty(self):
        """All losers -> no pairings in cross-pair mode."""
        market_price_eur = Decimal("0.30")
        lot1 = _make_lot("lot-1", "XRPEUR", "100", "50", cost_eur="50")
        lot2 = _make_lot("lot-2", "XRPBTC", "100", "0.001", cost_eur="45")

        pairings = suggest_pairings(
            [lot1, lot2], market_price_eur,
            threshold_pct=Decimal("0.05"),
            use_eur_cost=True,
        )
        assert len(pairings) == 0

    def test_cross_pair_symbol_from_first_lot(self):
        """Cross-pair pairing sets symbol from first lot."""
        market_price_eur = Decimal("0.50")
        lot1 = _make_lot("lot-1", "XRPEUR", "100", "30", cost_eur="30",
                         created_at=datetime(2024, 1, 1))
        lot2 = _make_lot("lot-2", "XRPBTC", "100", "0.001", cost_eur="55",
                         created_at=datetime(2024, 1, 2))

        pairings = suggest_pairings(
            [lot1, lot2], market_price_eur,
            threshold_pct=Decimal("0.05"),
            use_eur_cost=True,
        )
        assert len(pairings) >= 1
        # Symbol should be set from first lot in the input
        assert pairings[0].symbol == "XRPEUR"
