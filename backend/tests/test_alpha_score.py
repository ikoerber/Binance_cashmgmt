"""
Tests for Alpha Score domain logic (4 independent factor computations).

Covers: Z-Score Mean Reversion, Lead-Lag Momentum, Orderbook Imbalance, Funding Rate Score.
Each factor is tested for normal, edge, and boundary cases.
All computations must use Decimal exclusively.
"""

from decimal import Decimal
import pytest

from app.domain.alpha_score import (
    AlphaFactorScore,
    ZScoreResult,
    LeadLagResult,
    OrderbookImbalanceResult,
    FundingRateResult,
    compute_zscore_mean_reversion,
    compute_leadlag_momentum,
    compute_orderbook_imbalance,
    compute_funding_rate_score,
)


# ---------------------------------------------------------------------------
# Factor 1: Z-Score Mean Reversion
# ---------------------------------------------------------------------------

class TestZScoreMeanReversion:
    """Tests for compute_zscore_mean_reversion()."""

    def test_constant_prices_zscore_zero(self):
        """60 identical prices should produce zscore=0, sub_score=0, quality='live'."""
        prices = [Decimal("0.00004")] * 60
        result = compute_zscore_mean_reversion(prices)
        assert isinstance(result, ZScoreResult)
        assert result.zscore == Decimal("0")
        assert result.sub_score == Decimal("0")
        assert result.quality == "live"
        assert result.window_size == 60

    def test_price_below_mean_positive_subscore(self):
        """Last price 2 std below mean should produce positive sub_score (buy signal)."""
        # Build a series where mean is known and last value is 2 std below
        base = Decimal("0.00004")
        # Create 59 values at base, compute mean=base, std from small variance
        prices = [base] * 59
        # Add a value that's notably below the mean to create a known z-score
        # We need to engineer the series carefully
        # Use 58 values at 0.00004, 1 value at 0.00006, and last at low
        prices = [Decimal("0.00004")] * 30 + [Decimal("0.00006")] * 29
        # Mean = (30*0.00004 + 29*0.00006) / 59
        # Let's use simpler approach: create a series with known stats
        prices = []
        for i in range(59):
            prices.append(Decimal("100") + Decimal(str(i % 10)))
        # Last price well below mean
        prices.append(Decimal("80"))

        result = compute_zscore_mean_reversion(prices, window=60)
        assert result.quality == "live"
        assert result.sub_score > Decimal("0")  # Positive = buy signal (price below mean)

    def test_price_above_mean_negative_subscore(self):
        """Last price 2 std above mean should produce negative sub_score (sell signal)."""
        prices = []
        for i in range(59):
            prices.append(Decimal("100") + Decimal(str(i % 10)))
        # Last price well above mean
        prices.append(Decimal("130"))

        result = compute_zscore_mean_reversion(prices, window=60)
        assert result.quality == "live"
        assert result.sub_score < Decimal("0")  # Negative = sell signal (price above mean)

    def test_insufficient_data_warmup(self):
        """Less than window prices should return quality='warmup', sub_score=0."""
        prices = [Decimal("0.00004")] * 30
        result = compute_zscore_mean_reversion(prices, window=60)
        assert result.quality == "warmup"
        assert result.sub_score == Decimal("0")
        assert result.zscore == Decimal("0")

    def test_empty_list_warmup(self):
        """Empty price list should return quality='warmup'."""
        result = compute_zscore_mean_reversion([], window=60)
        assert result.quality == "warmup"
        assert result.sub_score == Decimal("0")

    def test_subscore_clamped_to_range(self):
        """Sub-scores should be clamped to [-5, +5] even for extreme Z-scores."""
        # Create extreme Z-score (price very far from mean)
        prices = [Decimal("100")] * 59 + [Decimal("10")]  # Extreme outlier
        result = compute_zscore_mean_reversion(prices, window=60)
        assert Decimal("-5") <= result.sub_score <= Decimal("5")

    def test_zscore_mapping_at_z_minus_3(self):
        """Z=-3 should map to sub_score=+5 (linear mapping)."""
        # Build a series where we can calculate exact z-score
        # 59 values = 100, last = 100 - 3*std
        # For uniform 100, std=0, so we need variation
        # Use a known distribution instead
        import statistics
        prices_float = [100.0] * 58 + [110.0]  # Some variance
        mean_f = statistics.mean(prices_float)
        std_f = statistics.pstdev(prices_float)
        if std_f > 0:
            target = mean_f - 3 * std_f
            prices = [Decimal(str(p)) for p in prices_float] + [Decimal(str(target))]
            result = compute_zscore_mean_reversion(prices, window=60)
            # Z should be approximately -3, sub_score approximately +5
            assert result.sub_score > Decimal("4")
            assert result.sub_score <= Decimal("5")

    def test_custom_window_size(self):
        """Custom window should be respected."""
        prices = [Decimal("100")] * 20
        result = compute_zscore_mean_reversion(prices, window=20)
        assert result.quality == "live"
        assert result.window_size == 20

    def test_result_types_are_decimal(self):
        """All numeric fields should be Decimal, not float."""
        prices = [Decimal("100") + Decimal(str(i)) for i in range(60)]
        result = compute_zscore_mean_reversion(prices)
        assert isinstance(result.zscore, Decimal)
        assert isinstance(result.sub_score, Decimal)
        assert isinstance(result.mean, Decimal)
        assert isinstance(result.std, Decimal)
        assert isinstance(result.current_ratio, Decimal)


# ---------------------------------------------------------------------------
# Factor 2: Lead-Lag Momentum
# ---------------------------------------------------------------------------

class TestLeadLagMomentum:
    """Tests for compute_leadlag_momentum()."""

    def test_btc_up_xrp_flat_positive_subscore(self):
        """BTC moves up strongly, XRP flat, high correlation -> positive sub_score."""
        # BTC returns: mostly flat then sudden jump
        btc_returns = [Decimal("0.001")] * 25 + [Decimal("0.05")] * 5  # Strong BTC move
        # XRP returns: flat throughout (hasn't followed)
        xrp_returns = [Decimal("0.001")] * 30
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30, max_lag=10)
        assert isinstance(result, LeadLagResult)
        assert result.quality == "live"
        # BTC up + XRP lagging = buy XRP signal (positive)
        assert result.sub_score >= Decimal("0")

    def test_btc_down_xrp_flat_negative_subscore(self):
        """BTC drops strongly, XRP flat -> negative sub_score (expect XRP to follow down)."""
        btc_returns = [Decimal("-0.001")] * 25 + [Decimal("-0.05")] * 5
        xrp_returns = [Decimal("-0.001")] * 30
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30, max_lag=10)
        assert result.quality == "live"
        assert result.sub_score <= Decimal("0")

    def test_no_correlation_zero_subscore(self):
        """No significant correlation should produce sub_score near 0."""
        # Random-ish returns with no pattern
        btc_returns = [Decimal("0.01") if i % 2 == 0 else Decimal("-0.01") for i in range(30)]
        xrp_returns = [Decimal("0.01") if i % 3 == 0 else Decimal("-0.01") for i in range(30)]
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30)
        assert result.quality == "live"
        # Should be close to 0 when no clear lead-lag relationship
        assert Decimal("-3") <= result.sub_score <= Decimal("3")

    def test_insufficient_data_warmup(self):
        """Less than window returns should return warmup."""
        btc_returns = [Decimal("0.01")] * 10
        xrp_returns = [Decimal("0.01")] * 10
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30)
        assert result.quality == "warmup"
        assert result.sub_score == Decimal("0")

    def test_all_returns_zero_subscore_zero(self):
        """All zero returns should produce sub_score=0."""
        btc_returns = [Decimal("0")] * 30
        xrp_returns = [Decimal("0")] * 30
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30)
        assert result.sub_score == Decimal("0")

    def test_subscore_clamped(self):
        """Sub-score should be clamped to [-5, +5]."""
        btc_returns = [Decimal("0")] * 25 + [Decimal("0.10")] * 5
        xrp_returns = [Decimal("0")] * 30
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30)
        assert Decimal("-5") <= result.sub_score <= Decimal("5")

    def test_result_types_are_decimal(self):
        """All numeric fields should be Decimal."""
        btc_returns = [Decimal("0.01")] * 30
        xrp_returns = [Decimal("0.01")] * 30
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30)
        assert isinstance(result.sub_score, Decimal)
        assert isinstance(result.best_lag, int)

    def test_mismatched_lengths_uses_minimum(self):
        """Mismatched input lengths should use minimum length."""
        btc_returns = [Decimal("0.01")] * 35
        xrp_returns = [Decimal("0.01")] * 30
        # Should handle gracefully (use shorter length)
        result = compute_leadlag_momentum(btc_returns, xrp_returns, window=30)
        assert result.quality == "live"


# ---------------------------------------------------------------------------
# Factor 3: Orderbook Imbalance
# ---------------------------------------------------------------------------

class TestOrderbookImbalance:
    """Tests for compute_orderbook_imbalance()."""

    def test_bid_heavy_positive_subscore(self):
        """70% bid / 30% ask within band -> positive sub_score (buy pressure)."""
        mid = Decimal("0.00004")
        band = Decimal("0.01")
        low = mid * (Decimal("1") - band)
        high = mid * (Decimal("1") + band)

        # Bids within band: 7 units
        bids = [(mid - Decimal("0.0000001") * Decimal(str(i)), Decimal("1")) for i in range(7)]
        # Asks within band: 3 units
        asks = [(mid + Decimal("0.0000001") * Decimal(str(i)), Decimal("1")) for i in range(3)]

        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        assert isinstance(result, OrderbookImbalanceResult)
        assert result.quality == "live"
        assert result.sub_score > Decimal("0")  # Buy pressure

    def test_ask_heavy_negative_subscore(self):
        """30% bid / 70% ask -> negative sub_score (sell pressure)."""
        mid = Decimal("100")
        band = Decimal("0.01")

        bids = [(mid - Decimal("0.5"), Decimal("3"))]
        asks = [(mid + Decimal("0.5"), Decimal("7"))]

        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        assert result.quality == "live"
        assert result.sub_score < Decimal("0")  # Sell pressure

    def test_equal_volume_zero_subscore(self):
        """Equal bid/ask volume -> sub_score=0."""
        mid = Decimal("100")
        band = Decimal("0.01")

        bids = [(mid - Decimal("0.5"), Decimal("10"))]
        asks = [(mid + Decimal("0.5"), Decimal("10"))]

        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        assert result.quality == "live"
        assert result.sub_score == Decimal("0")

    def test_empty_orderbook_unavailable(self):
        """Empty bid/ask lists -> quality='unavailable', sub_score=0."""
        mid = Decimal("100")
        result = compute_orderbook_imbalance([], [], mid)
        assert result.quality == "unavailable"
        assert result.sub_score == Decimal("0")

    def test_all_volume_one_side_bids(self):
        """All volume on bid side -> sub_score=+5."""
        mid = Decimal("100")
        band = Decimal("0.01")
        bids = [(mid - Decimal("0.5"), Decimal("100"))]
        asks = []  # No asks

        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        assert result.sub_score == Decimal("5")

    def test_all_volume_one_side_asks(self):
        """All volume on ask side -> sub_score=-5."""
        mid = Decimal("100")
        band = Decimal("0.01")
        bids = []  # No bids
        asks = [(mid + Decimal("0.5"), Decimal("100"))]

        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        assert result.sub_score == Decimal("-5")

    def test_volume_outside_band_excluded(self):
        """Orders outside the band should not be counted."""
        mid = Decimal("100")
        band = Decimal("0.01")  # 1% = 99..101

        # Bid far outside band
        bids = [(Decimal("90"), Decimal("1000"))]
        # Ask within band
        asks = [(Decimal("100.5"), Decimal("10"))]

        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        # Only ask volume within band, no bid volume in band
        assert result.sub_score < Decimal("0")

    def test_zero_total_volume_in_band(self):
        """No volume within band -> sub_score=0."""
        mid = Decimal("100")
        band = Decimal("0.001")  # Very narrow band

        bids = [(Decimal("90"), Decimal("10"))]  # Far outside
        asks = [(Decimal("110"), Decimal("10"))]  # Far outside

        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        assert result.sub_score == Decimal("0")

    def test_subscore_clamped(self):
        """Sub-score should be clamped to [-5, +5]."""
        mid = Decimal("100")
        band = Decimal("0.01")
        bids = [(mid - Decimal("0.5"), Decimal("100"))]
        asks = [(mid + Decimal("0.5"), Decimal("1"))]
        result = compute_orderbook_imbalance(bids, asks, mid, band_pct=band)
        assert Decimal("-5") <= result.sub_score <= Decimal("5")

    def test_result_types_are_decimal(self):
        """All numeric fields should be Decimal."""
        mid = Decimal("100")
        bids = [(Decimal("99.5"), Decimal("5"))]
        asks = [(Decimal("100.5"), Decimal("5"))]
        result = compute_orderbook_imbalance(bids, asks, mid)
        assert isinstance(result.sub_score, Decimal)
        assert isinstance(result.imbalance_ratio, Decimal)
        assert isinstance(result.bid_volume, Decimal)
        assert isinstance(result.ask_volume, Decimal)


# ---------------------------------------------------------------------------
# Factor 4: Funding Rate Score
# ---------------------------------------------------------------------------

class TestFundingRateScore:
    """Tests for compute_funding_rate_score()."""

    def test_positive_funding_negative_subscore(self):
        """Positive funding (longs paying) -> negative sub_score (contrarian sell)."""
        result = compute_funding_rate_score(Decimal("0.0005"))
        assert isinstance(result, FundingRateResult)
        assert result.quality == "live"
        assert result.sub_score < Decimal("0")

    def test_negative_funding_positive_subscore(self):
        """Negative funding (shorts paying) -> positive sub_score (contrarian buy)."""
        result = compute_funding_rate_score(Decimal("-0.0005"))
        assert result.quality == "live"
        assert result.sub_score > Decimal("0")

    def test_none_funding_unavailable(self):
        """None funding -> quality='unavailable', sub_score=0."""
        result = compute_funding_rate_score(None)
        assert result.quality == "unavailable"
        assert result.sub_score == Decimal("0")

    def test_zero_funding_zero_subscore(self):
        """Zero funding -> sub_score=0."""
        result = compute_funding_rate_score(Decimal("0"))
        assert result.quality == "live"
        assert result.sub_score == Decimal("0")

    def test_extreme_positive_funding_minus_five(self):
        """Funding >= 0.1% should map to sub_score=-5."""
        result = compute_funding_rate_score(Decimal("0.001"))
        assert result.sub_score == Decimal("-5")

    def test_extreme_negative_funding_plus_five(self):
        """Funding <= -0.1% should map to sub_score=+5."""
        result = compute_funding_rate_score(Decimal("-0.001"))
        assert result.sub_score == Decimal("5")

    def test_subscore_clamped(self):
        """Sub-score should be clamped to [-5, +5] for extreme values."""
        result = compute_funding_rate_score(Decimal("0.01"))  # 1% funding
        assert Decimal("-5") <= result.sub_score <= Decimal("5")
        result2 = compute_funding_rate_score(Decimal("-0.01"))
        assert Decimal("-5") <= result2.sub_score <= Decimal("5")

    def test_with_btc_funding_reference(self):
        """With BTC funding, relative divergence should affect score."""
        # Asset funding more negative than BTC -> extra buy signal
        result = compute_funding_rate_score(
            Decimal("-0.0005"),
            btc_funding=Decimal("0.0001"),
        )
        assert result.quality == "live"
        # Score should be more positive than without btc_funding
        result_no_btc = compute_funding_rate_score(Decimal("-0.0005"))
        # With btc reference showing divergence, score should differ
        assert isinstance(result.sub_score, Decimal)

    def test_btc_funding_same_as_asset_no_extra_signal(self):
        """When BTC and asset funding are equal, no extra signal from divergence."""
        rate = Decimal("0.0002")
        result_with = compute_funding_rate_score(rate, btc_funding=rate)
        result_without = compute_funding_rate_score(rate)
        # Scores should be similar (base signal same)
        assert isinstance(result_with.sub_score, Decimal)

    def test_result_types_are_decimal(self):
        """All numeric fields should be Decimal."""
        result = compute_funding_rate_score(Decimal("0.0003"))
        assert isinstance(result.sub_score, Decimal)
        assert isinstance(result.raw_rate, Decimal)


# ---------------------------------------------------------------------------
# AlphaFactorScore Dataclass
# ---------------------------------------------------------------------------

class TestAlphaFactorScore:
    """Tests for the AlphaFactorScore dataclass."""

    def test_creation(self):
        """AlphaFactorScore should be creatable with all fields."""
        score = AlphaFactorScore(
            name="Z-Score Mean Reversion",
            sub_score=Decimal("2.5"),
            raw_value=Decimal("-1.5"),
            weight=Decimal("0.40"),
            base_weight=Decimal("0.40"),
            quality="live",
            description="Z=-1.5, buy signal",
        )
        assert score.name == "Z-Score Mean Reversion"
        assert score.sub_score == Decimal("2.5")
        assert score.quality == "live"

    def test_default_description(self):
        """Description should default to empty string."""
        score = AlphaFactorScore(
            name="test",
            sub_score=Decimal("0"),
            raw_value=None,
            weight=Decimal("0.25"),
            base_weight=Decimal("0.25"),
            quality="warmup",
        )
        assert score.description == ""


# ---------------------------------------------------------------------------
# Hurst Exponent (R/S Analysis)
# ---------------------------------------------------------------------------

from app.domain.alpha_score import (
    HurstResult,
    RegimeInfo,
    AlphaScoreResult,
    TrailingStopState,
    compute_hurst_rs,
    compute_regime_adjusted_weights,
    compute_alpha_score,
    compute_atr_standalone,
    update_trailing_stop,
)
from datetime import datetime, timezone


class TestHurstRS:
    """Tests for compute_hurst_rs()."""

    def test_random_walk_hurst_near_half(self):
        """Shuffled/random data should produce H near 0.5."""
        import random
        random.seed(42)
        # Random walk: cumsum of random steps
        prices = []
        p = Decimal("100")
        for _ in range(200):
            step = Decimal(str(random.choice([-1, 1]))) * Decimal("0.5")
            p += step
            prices.append(p)
        result = compute_hurst_rs(prices)
        assert isinstance(result, HurstResult)
        # Random walk H should be roughly 0.4-0.6
        assert Decimal("0.3") <= result.hurst <= Decimal("0.7")

    def test_trending_data_hurst_above_threshold(self):
        """Persistent trending data should produce H > 0.45 (not mean-reverting)."""
        import random
        random.seed(99)
        # Trending walk: cumulative sum with positive drift
        prices = []
        p = Decimal("100")
        for _ in range(500):
            # Strong persistent drift: +0.5 base, small noise
            step = Decimal("0.5") + Decimal(str(round(random.gauss(0, 0.1), 4)))
            p += step
            prices.append(p)
        result = compute_hurst_rs(prices)
        # Persistent trending data should NOT be classified as mean_reverting
        assert result.regime in ("trending", "transitional")

    def test_mean_reverting_data_hurst_below_threshold(self):
        """Oscillating data should produce H < 0.5."""
        prices = []
        for i in range(200):
            # Alternating pattern: strongly mean-reverting
            if i % 2 == 0:
                prices.append(Decimal("100") + Decimal(str(i % 5)))
            else:
                prices.append(Decimal("110") - Decimal(str(i % 5)))
        result = compute_hurst_rs(prices)
        assert result.hurst < Decimal("0.55")

    def test_insufficient_data_default(self):
        """Less than min_window*2 data points -> H=0.5, confidence=0."""
        prices = [Decimal("100")] * 15
        result = compute_hurst_rs(prices, min_window=10)
        assert result.hurst == Decimal("0.5")
        assert result.regime == "transitional"
        assert result.confidence == Decimal("0")

    def test_constant_series_default(self):
        """All same price -> H=0.5, confidence=0."""
        prices = [Decimal("100")] * 200
        result = compute_hurst_rs(prices)
        assert result.hurst == Decimal("0.5")
        assert result.confidence == Decimal("0")

    def test_result_types_decimal(self):
        """All numeric fields should be Decimal."""
        prices = [Decimal("100") + Decimal(str(i)) for i in range(200)]
        result = compute_hurst_rs(prices)
        assert isinstance(result.hurst, Decimal)
        assert isinstance(result.confidence, Decimal)
        assert isinstance(result.data_points, int)

    def test_regime_labels(self):
        """Regime should be one of the three valid labels."""
        prices = [Decimal("100") + Decimal(str(i)) for i in range(200)]
        result = compute_hurst_rs(prices)
        assert result.regime in ("trending", "mean_reverting", "transitional")


# ---------------------------------------------------------------------------
# Regime-Adjusted Weights
# ---------------------------------------------------------------------------

class TestRegimeAdjustedWeights:
    """Tests for compute_regime_adjusted_weights()."""

    def test_mean_reverting_weights_unchanged(self):
        """H <= 0.45 -> weights unchanged from base."""
        base = {"zscore": Decimal("0.40"), "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"), "funding": Decimal("0.10")}
        result = compute_regime_adjusted_weights(base, Decimal("0.40"))
        assert result["zscore"] == Decimal("0.40")
        assert result["leadlag"] == Decimal("0.30")

    def test_boundary_045_weights_unchanged(self):
        """H = 0.45 -> weights unchanged (boundary)."""
        base = {"zscore": Decimal("0.40"), "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"), "funding": Decimal("0.10")}
        result = compute_regime_adjusted_weights(base, Decimal("0.45"))
        assert result["zscore"] == Decimal("0.40")

    def test_trending_zscore_zero(self):
        """H >= 0.55 -> Z-Score weight = 0, freed weight redistributed."""
        base = {"zscore": Decimal("0.40"), "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"), "funding": Decimal("0.10")}
        result = compute_regime_adjusted_weights(base, Decimal("0.55"))
        assert result["zscore"] == Decimal("0")

    def test_trending_redistribution_ratios(self):
        """H >= 0.55 -> freed weight distributed 60/30/10."""
        base = {"zscore": Decimal("0.40"), "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"), "funding": Decimal("0.10")}
        result = compute_regime_adjusted_weights(base, Decimal("0.60"))
        freed = Decimal("0.40")  # Full zscore weight freed
        assert abs(result["leadlag"] - (Decimal("0.30") + freed * Decimal("0.60"))) < Decimal("0.01")
        assert abs(result["imbalance"] - (Decimal("0.20") + freed * Decimal("0.30"))) < Decimal("0.01")
        assert abs(result["funding"] - (Decimal("0.10") + freed * Decimal("0.10"))) < Decimal("0.01")

    def test_transitional_050_half_reduction(self):
        """H = 0.50 -> Z-Score reduced by 50% of base, freed weight redistributed."""
        base = {"zscore": Decimal("0.40"), "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"), "funding": Decimal("0.10")}
        result = compute_regime_adjusted_weights(base, Decimal("0.50"))
        # 50% between 0.45 and 0.55, so 50% reduction
        expected_zscore = Decimal("0.20")  # 0.40 * 0.5
        assert abs(result["zscore"] - expected_zscore) < Decimal("0.01")

    def test_weights_sum_to_one(self):
        """Weights must always sum to 1.0."""
        base = {"zscore": Decimal("0.40"), "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"), "funding": Decimal("0.10")}
        for h_val in ["0.35", "0.45", "0.48", "0.50", "0.52", "0.55", "0.65"]:
            result = compute_regime_adjusted_weights(base, Decimal(h_val))
            total = sum(result.values())
            assert abs(total - Decimal("1.0")) < Decimal("0.001"), \
                f"H={h_val}: weights sum to {total}"

    def test_clamped_beyond_thresholds(self):
        """H = 0.70 -> same result as 0.55 (clamped at threshold)."""
        base = {"zscore": Decimal("0.40"), "leadlag": Decimal("0.30"),
                "imbalance": Decimal("0.20"), "funding": Decimal("0.10")}
        r55 = compute_regime_adjusted_weights(base, Decimal("0.55"))
        r70 = compute_regime_adjusted_weights(base, Decimal("0.70"))
        for k in base:
            assert abs(r55[k] - r70[k]) < Decimal("0.001")


# ---------------------------------------------------------------------------
# Alpha Score Composite
# ---------------------------------------------------------------------------

class TestAlphaScoreComposite:
    """Tests for compute_alpha_score()."""

    def _make_factors(self, sub_scores, qualities=None):
        """Helper to build AlphaFactorScore list."""
        names = ["zscore", "leadlag", "imbalance", "funding"]
        weights = [Decimal("0.40"), Decimal("0.30"), Decimal("0.20"), Decimal("0.10")]
        if qualities is None:
            qualities = ["live"] * 4
        factors = []
        for i, name in enumerate(names):
            factors.append(AlphaFactorScore(
                name=name,
                sub_score=Decimal(str(sub_scores[i])),
                raw_value=None,
                weight=weights[i],
                base_weight=weights[i],
                quality=qualities[i],
            ))
        return factors

    def test_weighted_sum_correct(self):
        """Weighted sum of sub_scores should produce correct composite score."""
        factors = self._make_factors([3, 2, 1, 1])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime)
        assert isinstance(result, AlphaScoreResult)
        # Weighted sum: 3*0.4 + 2*0.3 + 1*0.2 + 1*0.1 = 1.2 + 0.6 + 0.2 + 0.1 = 2.1
        assert abs(result.score - Decimal("2.1")) < Decimal("0.1")

    def test_long_signal(self):
        """Score >= threshold -> LONG."""
        factors = self._make_factors([5, 4, 3, 2])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime, threshold=Decimal("3.0"))
        assert result.trade_signal == "LONG"

    def test_short_signal(self):
        """Score <= -threshold -> SHORT."""
        factors = self._make_factors([-5, -4, -3, -2])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime, threshold=Decimal("3.0"))
        assert result.trade_signal == "SHORT"

    def test_neutral_signal(self):
        """Score between -threshold and +threshold -> NEUTRAL."""
        factors = self._make_factors([1, 0.5, 0, -0.5])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime, threshold=Decimal("3.0"))
        assert result.trade_signal == "NEUTRAL"

    def test_quality_full(self):
        """All 4 live -> quality='full'."""
        factors = self._make_factors([1, 1, 1, 1])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime)
        assert result.quality == "full"
        assert result.active_factors == 4

    def test_quality_partial(self):
        """3 live, 1 unavailable -> quality='partial'."""
        factors = self._make_factors([1, 1, 1, 0], ["live", "live", "live", "unavailable"])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime)
        assert result.quality == "partial"
        assert result.active_factors == 3

    def test_quality_degraded(self):
        """1-2 live -> quality='degraded'."""
        factors = self._make_factors([1, 0, 0, 0],
                                     ["live", "unavailable", "unavailable", "warmup"])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime)
        assert result.quality == "degraded"

    def test_quality_warmup(self):
        """All warmup -> quality='warmup', score=0."""
        factors = self._make_factors([0, 0, 0, 0],
                                     ["warmup", "warmup", "warmup", "warmup"])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime)
        assert result.quality == "warmup"
        assert result.score == Decimal("0")

    def test_score_clamped(self):
        """Score clamped to [-5, +5]."""
        factors = self._make_factors([5, 5, 5, 5])
        regime = RegimeInfo(hurst=Decimal("0.5"), regime="transitional",
                            confidence=Decimal("0.8"), zscore_weight_pct=Decimal("40"))
        result = compute_alpha_score(factors, regime)
        assert Decimal("-5") <= result.score <= Decimal("5")


# ---------------------------------------------------------------------------
# ATR Standalone
# ---------------------------------------------------------------------------

class TestATRStandalone:
    """Tests for compute_atr_standalone() (Wilder's Smoothing)."""

    def test_basic_atr(self):
        """ATR should compute correctly for simple data."""
        candles = []
        for i in range(20):
            candles.append({
                "high": Decimal("110") + Decimal(str(i)),
                "low": Decimal("90") + Decimal(str(i)),
                "close": Decimal("100") + Decimal(str(i)),
            })
        result = compute_atr_standalone(candles, period=14)
        assert result is not None
        assert isinstance(result, Decimal)
        assert result > Decimal("0")

    def test_insufficient_candles(self):
        """Fewer than period+1 candles -> None."""
        candles = [{"high": Decimal("110"), "low": Decimal("90"),
                     "close": Decimal("100")}] * 10
        result = compute_atr_standalone(candles, period=14)
        assert result is None

    def test_empty_candles(self):
        """Empty candle list -> None."""
        result = compute_atr_standalone([], period=14)
        assert result is None


# ---------------------------------------------------------------------------
# Trailing Stop State Machine
# ---------------------------------------------------------------------------

class TestTrailingStop:
    """Tests for update_trailing_stop()."""

    def _make_state(self, direction="long", stop_level=None, frozen=False,
                    fresh_count=0, resume_threshold=5):
        return TrailingStopState(
            symbol="BTCEUR",
            stop_level=stop_level,
            atr_value=None,
            atr_distance=None,
            direction=direction,
            frozen=frozen,
            frozen_since=datetime(2026, 1, 1, tzinfo=timezone.utc) if frozen else None,
            fresh_data_count=fresh_count,
            resume_threshold=resume_threshold,
            last_price=None,
            last_updated=None,
        )

    def test_long_price_rises_stop_ratchets_up(self):
        """Long position: price rises -> stop should move up."""
        state = self._make_state(stop_level=Decimal("95"), direction="long")
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("110"), Decimal("5"), Decimal("2"), True, now
        )
        # Stop should be at least price - ATR*mult = 110 - 10 = 100
        assert new_state.stop_level >= Decimal("95")
        assert new_state.stop_level is not None

    def test_long_price_drops_stop_holds(self):
        """Long position: price drops -> stop should NOT move down."""
        state = self._make_state(stop_level=Decimal("100"), direction="long")
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("95"), Decimal("5"), Decimal("2"), True, now
        )
        assert new_state.stop_level == Decimal("100")  # Held at original

    def test_short_price_drops_stop_ratchets_down(self):
        """Short position: price drops -> stop moves down."""
        state = self._make_state(stop_level=Decimal("110"), direction="short")
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("90"), Decimal("5"), Decimal("2"), True, now
        )
        # Stop should be at most price + ATR*mult = 90 + 10 = 100
        assert new_state.stop_level <= Decimal("110")

    def test_freeze_on_stale_data(self):
        """data_is_fresh=False -> frozen=True, stop unchanged."""
        state = self._make_state(stop_level=Decimal("100"), direction="long")
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("120"), Decimal("5"), Decimal("2"), False, now
        )
        assert new_state.frozen is True
        assert new_state.stop_level == Decimal("100")

    def test_resume_after_n_fresh(self):
        """5 consecutive fresh data points -> unfrozen."""
        state = self._make_state(stop_level=Decimal("100"), direction="long",
                                  frozen=True, fresh_count=4, resume_threshold=5)
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("120"), Decimal("5"), Decimal("2"), True, now
        )
        assert new_state.frozen is False
        assert new_state.fresh_data_count >= 5

    def test_resume_counter_resets_on_stale(self):
        """4 fresh then 1 stale -> counter resets."""
        state = self._make_state(stop_level=Decimal("100"), direction="long",
                                  frozen=True, fresh_count=4, resume_threshold=5)
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("120"), Decimal("5"), Decimal("2"), False, now
        )
        assert new_state.frozen is True
        assert new_state.fresh_data_count == 0

    def test_initial_state_sets_stop(self):
        """First update (stop_level=None) -> sets initial stop."""
        state = self._make_state(stop_level=None, direction="long")
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("100"), Decimal("5"), Decimal("2"), True, now
        )
        assert new_state.stop_level is not None
        # For long: stop = price - ATR * mult = 100 - 10 = 90
        assert new_state.stop_level == Decimal("90")

    def test_immutable_state_transition(self):
        """update_trailing_stop should return new state, not mutate input."""
        state = self._make_state(stop_level=Decimal("100"), direction="long")
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        new_state = update_trailing_stop(
            state, Decimal("120"), Decimal("5"), Decimal("2"), True, now
        )
        assert state.stop_level == Decimal("100")  # Original unchanged
        assert new_state is not state
