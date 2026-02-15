"""Tests fuer die Sentiment Engine v3 Domain-Logik."""
from decimal import Decimal

import pytest

from app.domain.sentiment import (
    DispersionInfo,
    SentimentResultV3,
    VolatilityScaling,
    compute_pillar_dispersion,
    compute_piecewise_linear_multiplier,
    compute_volatility_scaling,
    get_recommendation_v3,
    compute_sentiment_v3,
    score_funding_rate,
    V3_MULTIPLIER_FLOOR,
    V3_MULTIPLIER_CEILING,
)


# ─── Pillar-Dispersion ───


class TestPillarDispersion:
    def test_uniform_scores(self):
        """Identische Pillar-Scores -> std=0, confidence=1.0."""
        result = compute_pillar_dispersion([Decimal("50"), Decimal("50"), Decimal("50"), Decimal("50")])
        assert result.pillar_std == Decimal("0.0")
        assert result.confidence_factor == Decimal("1.000")
        assert result.high_dispersion is False

    def test_moderate_divergence(self):
        """Maessige Divergenz -> confidence zwischen 0 und 1."""
        result = compute_pillar_dispersion([Decimal("30"), Decimal("50"), Decimal("40"), Decimal("60")])
        assert Decimal("0") < result.confidence_factor < Decimal("1")
        assert result.pillar_std > Decimal("0")

    def test_extreme_divergence(self):
        """Starke Divergenz (std >= 30) -> confidence = 0."""
        result = compute_pillar_dispersion([Decimal("0"), Decimal("100"), Decimal("0"), Decimal("100")])
        assert result.confidence_factor == Decimal("0.000")
        assert result.high_dispersion is True

    def test_single_pillar(self):
        """Nur ein Pillar -> std=0, confidence=1.0."""
        result = compute_pillar_dispersion([Decimal("70")])
        assert result.pillar_std == Decimal("0")
        assert result.confidence_factor == Decimal("1")

    def test_empty_list(self):
        """Leere Liste -> std=0, confidence=1.0."""
        result = compute_pillar_dispersion([])
        assert result.confidence_factor == Decimal("1")

    def test_high_dispersion_threshold(self):
        """Dispersion Flag ab std >= 15."""
        # std = 15 genau -> high_dispersion=True
        # Scores mit std=15: z.B. [35, 65] -> mean=50, variance=225, std=15
        result = compute_pillar_dispersion([Decimal("35"), Decimal("65")])
        assert result.high_dispersion is True

    def test_just_below_high_dispersion(self):
        """Knapp unter high_dispersion-Schwelle."""
        # [40, 60] -> mean=50, variance=100, std=10 < 15
        result = compute_pillar_dispersion([Decimal("40"), Decimal("60")])
        assert result.high_dispersion is False


# ─── Funding Rate Scoring ───


class TestFundingRateScoring:
    def test_none_returns_unavailable(self):
        """None -> unavailable, score 50."""
        p = score_funding_rate(None)
        assert p.quality == "unavailable"
        assert p.score == Decimal("50")

    def test_neutral_rate(self):
        """Standard-Rate (0.01%) -> neutral Zone (35-65)."""
        p = score_funding_rate(Decimal("0.0001"))
        assert Decimal("35") <= p.score <= Decimal("65")
        assert p.quality == "live"
        assert p.raw_value == Decimal("0.0001")

    def test_high_positive_rate(self):
        """Hohe positive Rate -> Greed (hoher Score)."""
        p = score_funding_rate(Decimal("0.0005"))
        assert p.score > Decimal("65")

    def test_negative_rate(self):
        """Negative Rate -> Fear (niedriger Score)."""
        p = score_funding_rate(Decimal("-0.0005"))
        assert p.score < Decimal("35")

    def test_extreme_negative(self):
        """Stark negative Rate -> Score 0."""
        p = score_funding_rate(Decimal("-0.002"))
        assert p.score == Decimal("0.0")

    def test_extreme_positive(self):
        """Stark positive Rate -> Score 100."""
        p = score_funding_rate(Decimal("0.002"))
        assert p.score == Decimal("100.0")

    def test_zero_rate(self):
        """Rate 0 -> neutral Zone."""
        p = score_funding_rate(Decimal("0"))
        assert Decimal("35") <= p.score <= Decimal("65")


# ─── Piecewise Linear Multiplier ───


class TestPiecewiseLinearMultiplier:
    def test_score_zero(self):
        """Score 0 -> maximaler Fear-Multiplier (1.50)."""
        m = compute_piecewise_linear_multiplier(Decimal("0"))
        assert m == V3_MULTIPLIER_FLOOR

    def test_score_100(self):
        """Score 100 -> minimaler Greed-Multiplier (0.85)."""
        m = compute_piecewise_linear_multiplier(Decimal("100"))
        assert m == V3_MULTIPLIER_CEILING

    def test_score_50_neutral(self):
        """Score 50 -> exakt 1.0 (neutrale Zone)."""
        m = compute_piecewise_linear_multiplier(Decimal("50"))
        assert m == Decimal("1.000")

    def test_boundary_40(self):
        """Score 40 -> nahtloser Uebergang zu 1.0."""
        m = compute_piecewise_linear_multiplier(Decimal("40"))
        assert m == Decimal("1.000")

    def test_boundary_60(self):
        """Score 60 -> nahtloser Uebergang von 1.0."""
        m = compute_piecewise_linear_multiplier(Decimal("60"))
        assert m == Decimal("1.000")

    def test_midpoint_fear_side(self):
        """Score 20 -> Mitte zwischen 1.50 und 1.00 = 1.25."""
        m = compute_piecewise_linear_multiplier(Decimal("20"))
        assert m == Decimal("1.250")

    def test_midpoint_greed_side(self):
        """Score 80 -> Mitte zwischen 1.00 und 0.85 = 0.925."""
        m = compute_piecewise_linear_multiplier(Decimal("80"))
        assert m == Decimal("0.925")

    def test_asymmetry(self):
        """Fear-Range (0.50) groesser als Greed-Range (0.15)."""
        m_fear = compute_piecewise_linear_multiplier(Decimal("0"))
        m_greed = compute_piecewise_linear_multiplier(Decimal("100"))
        fear_range = m_fear - Decimal("1")     # +0.50
        greed_range = Decimal("1") - m_greed   # +0.15
        assert fear_range > greed_range

    def test_continuity_at_boundaries(self):
        """Keine Spruenge an den Grenzen 40 und 60."""
        m_39 = compute_piecewise_linear_multiplier(Decimal("39"))
        m_40 = compute_piecewise_linear_multiplier(Decimal("40"))
        m_41 = compute_piecewise_linear_multiplier(Decimal("41"))
        assert abs(m_39 - m_40) < Decimal("0.02")
        assert m_40 == m_41  # beide in neutraler Zone

        m_59 = compute_piecewise_linear_multiplier(Decimal("59"))
        m_60 = compute_piecewise_linear_multiplier(Decimal("60"))
        m_61 = compute_piecewise_linear_multiplier(Decimal("61"))
        assert m_59 == m_60  # beide in neutraler Zone
        assert abs(m_60 - m_61) < Decimal("0.01")

    def test_monotonic_decreasing(self):
        """Multiplier ist monoton fallend ueber den gesamten Score-Bereich."""
        prev = compute_piecewise_linear_multiplier(Decimal("0"))
        for s in range(1, 101):
            curr = compute_piecewise_linear_multiplier(Decimal(str(s)))
            assert curr <= prev, f"Nicht monoton bei Score {s}: {curr} > {prev}"
            prev = curr


# ─── Volatility-Scaling ───


class TestVolatilityScaling:
    def _make_returns(self, base_return: Decimal, n: int) -> list[Decimal]:
        """Erzeugt synthetische Daily-Returns."""
        return [base_return] * n

    def test_insufficient_data(self):
        """Weniger als 120 Returns -> None."""
        result = compute_volatility_scaling([Decimal("0.01")] * 50)
        assert result is None

    def test_none_input(self):
        """None Input -> None."""
        result = compute_volatility_scaling(None)
        assert result is None

    def test_normal_regime(self):
        """Gleichmaessige Returns -> NORMAL Regime, factor=1.0."""
        returns = self._make_returns(Decimal("0.01"), 120)
        result = compute_volatility_scaling(returns)
        # Konstante Returns -> std=0, aber alle gleich -> vol_ratio undefiniert
        # Stattdessen leicht variierende Returns verwenden
        returns = [Decimal("0.01") if i % 2 == 0 else Decimal("-0.01") for i in range(120)]
        result = compute_volatility_scaling(returns)
        assert result is not None
        assert result.regime == "NORMAL"
        assert result.scaling_factor == Decimal("1.0")

    def test_high_vol_regime(self):
        """Hohe kurzfristige Vol -> HIGH Regime, factor=0.5."""
        # 100 Tage ruhig, 20 Tage wild
        calm = [Decimal("0.001") if i % 2 == 0 else Decimal("-0.001") for i in range(100)]
        wild = [Decimal("0.05") if i % 2 == 0 else Decimal("-0.05") for i in range(20)]
        result = compute_volatility_scaling(calm + wild)
        assert result is not None
        assert result.regime == "HIGH"
        assert result.scaling_factor == Decimal("0.5")

    def test_low_vol_regime(self):
        """Niedrige kurzfristige Vol -> LOW Regime, factor=1.2."""
        # 100 Tage wild, 20 Tage ruhig
        wild = [Decimal("0.05") if i % 2 == 0 else Decimal("-0.05") for i in range(100)]
        calm = [Decimal("0.001") if i % 2 == 0 else Decimal("-0.001") for i in range(20)]
        result = compute_volatility_scaling(wild + calm)
        assert result is not None
        assert result.regime == "LOW"
        assert result.scaling_factor == Decimal("1.2")

    def test_returns_dataclass_fields(self):
        """Prueft dass alle Felder korrekt gefuellt werden."""
        returns = [Decimal("0.01") if i % 2 == 0 else Decimal("-0.01") for i in range(120)]
        result = compute_volatility_scaling(returns)
        assert result is not None
        assert isinstance(result.realized_vol_20d, Decimal)
        assert isinstance(result.avg_vol_120d, Decimal)
        assert isinstance(result.vol_ratio, Decimal)
        assert result.regime in ("HIGH", "NORMAL", "LOW")


# ─── Recommendation V3 ───


class TestRecommendationV3:
    def test_fear_multiplier_above_one(self):
        """Bei Fear-Score ist Multiplier > 1.0."""
        rec = get_recommendation_v3(
            Decimal("10"),
            [Decimal("10"), Decimal("12"), Decimal("8"), Decimal("11")],
        )
        assert rec.buy_size_multiplier > Decimal("1.0")
        assert rec.action == "Aggressiv akkumulieren"

    def test_greed_multiplier_below_one(self):
        """Bei Greed-Score ist Multiplier < 1.0."""
        rec = get_recommendation_v3(
            Decimal("90"),
            [Decimal("88"), Decimal("92"), Decimal("85"), Decimal("90")],
        )
        assert rec.buy_size_multiplier < Decimal("1.0")

    def test_neutral_multiplier_is_one(self):
        """Bei neutralem Score ist Multiplier = 1.0."""
        rec = get_recommendation_v3(
            Decimal("50"),
            [Decimal("50"), Decimal("50"), Decimal("50"), Decimal("50")],
        )
        assert rec.buy_size_multiplier == Decimal("1.00")

    def test_dispersion_dampens_signal(self):
        """Hohe Pillar-Divergenz daempft den Multiplier Richtung 1.0."""
        # Ohne Divergenz
        rec_agree = get_recommendation_v3(
            Decimal("10"),
            [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10")],
        )
        # Mit Divergenz
        rec_diverge = get_recommendation_v3(
            Decimal("10"),
            [Decimal("0"), Decimal("100"), Decimal("5"), Decimal("95")],
        )
        # Divergenz sollte Multiplier naeher an 1.0 bringen
        assert abs(rec_diverge.buy_size_multiplier - Decimal("1")) < abs(rec_agree.buy_size_multiplier - Decimal("1"))

    def test_high_vol_compresses(self):
        """HIGH Vol komprimiert Multiplier-Range Richtung 1.0."""
        calm = [Decimal("0.001") if i % 2 == 0 else Decimal("-0.001") for i in range(100)]
        wild = [Decimal("0.05") if i % 2 == 0 else Decimal("-0.05") for i in range(20)]

        rec_no_vol = get_recommendation_v3(
            Decimal("10"),
            [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10")],
            daily_returns=None,
        )
        rec_high_vol = get_recommendation_v3(
            Decimal("10"),
            [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10")],
            daily_returns=calm + wild,
        )
        # HIGH Vol -> weniger aggressiv (naeher an 1.0)
        assert abs(rec_high_vol.buy_size_multiplier - Decimal("1")) < abs(rec_no_vol.buy_size_multiplier - Decimal("1"))

    def test_raw_multiplier_preserved(self):
        """raw_multiplier bleibt unabhaengig von Dispersion/Vol."""
        rec = get_recommendation_v3(
            Decimal("10"),
            [Decimal("0"), Decimal("100"), Decimal("5"), Decimal("95")],
        )
        expected_raw = compute_piecewise_linear_multiplier(Decimal("10"))
        assert rec.raw_multiplier == expected_raw


# ─── Compute Sentiment V3 ───


class TestComputeSentimentV3:
    def test_dma_has_highest_influence(self):
        """DMA-Pillar mit 42% Gewicht hat den groessten Einfluss."""
        # Alle Pillars neutral (50) ausser DMA (hoch)
        result_dma_high = compute_sentiment_v3(
            fng_value=Decimal("50"),
            taker_ratio_7d=Decimal("1.00"),
            dist_50dma_pct=Decimal("20"),   # weit ueber 50-DMA
            vol_ratio=Decimal("1.0"),
            price_change_pct=Decimal("0"),
            history_fng=[Decimal(str(i)) for i in range(30, 70)] * 3,
            history_taker=[Decimal("1.0")] * 90,
            history_dma=[Decimal("0")] * 90,
            history_vol=[Decimal("1.0")] * 90,
        )
        # Alle neutral ausser Volume (hoch)
        result_vol_high = compute_sentiment_v3(
            fng_value=Decimal("50"),
            taker_ratio_7d=Decimal("1.00"),
            dist_50dma_pct=Decimal("0"),
            vol_ratio=Decimal("3.0"),       # weit ueber Durchschnitt
            price_change_pct=Decimal("5"),
            history_fng=[Decimal(str(i)) for i in range(30, 70)] * 3,
            history_taker=[Decimal("1.0")] * 90,
            history_dma=[Decimal("0")] * 90,
            history_vol=[Decimal("1.0")] * 90,
        )
        # DMA-Einfluss sollte Score staerker verschieben als Volume
        dma_deviation = abs(result_dma_high.composite_score - Decimal("50"))
        vol_deviation = abs(result_vol_high.composite_score - Decimal("50"))
        assert dma_deviation > vol_deviation

    def test_all_unavailable(self):
        """Alle Pillars unavailable -> Score 50, Multiplier 1.00."""
        result = compute_sentiment_v3(
            fng_value=None,
            taker_ratio_7d=None,
            dist_50dma_pct=None,
            vol_ratio=None,
            price_change_pct=None,
        )
        assert result.composite_score == Decimal("50.0")
        assert result.recommendation.buy_size_multiplier == Decimal("1.00")
        assert result.active_pillars == 0

    def test_missing_pillars_renormalized(self):
        """Fehlende Pillars werden renormalisiert (Gewichte summieren zu 1.0)."""
        # Nur F&G und DMA verfuegbar
        result = compute_sentiment_v3(
            fng_value=Decimal("80"),
            taker_ratio_7d=None,
            dist_50dma_pct=Decimal("10"),
            vol_ratio=None,
            price_change_pct=None,
            history_fng=[Decimal(str(i)) for i in range(20, 80)] * 2,
            history_dma=[Decimal("0")] * 90,
        )
        assert result.active_pillars == 2
        assert result.composite_score != Decimal("50.0")  # nicht neutral

    def test_returns_correct_dataclass(self):
        """Prueft dass SentimentResultV3 zurueckgegeben wird."""
        result = compute_sentiment_v3(
            fng_value=Decimal("50"),
            taker_ratio_7d=Decimal("1.0"),
            dist_50dma_pct=Decimal("0"),
            vol_ratio=Decimal("1.0"),
            price_change_pct=Decimal("0"),
            history_fng=[Decimal("50")] * 90,
            history_taker=[Decimal("1.0")] * 90,
            history_dma=[Decimal("0")] * 90,
            history_vol=[Decimal("1.0")] * 90,
        )
        assert isinstance(result, SentimentResultV3)
        assert result.total_pillars == 5
        assert result.active_pillars == 4  # Funding unavailable
        assert result.composite_label is not None
        assert result.composite_color is not None

    def test_funding_rate_activates_pillar(self):
        """Mit funding_rate sind alle 5 Pillars aktiv."""
        result = compute_sentiment_v3(
            fng_value=Decimal("50"),
            taker_ratio_7d=Decimal("1.0"),
            dist_50dma_pct=Decimal("0"),
            vol_ratio=Decimal("1.0"),
            price_change_pct=Decimal("0"),
            history_fng=[Decimal("50")] * 90,
            history_taker=[Decimal("1.0")] * 90,
            history_dma=[Decimal("0")] * 90,
            history_vol=[Decimal("1.0")] * 90,
            funding_rate=Decimal("0.0001"),
        )
        assert result.active_pillars == 5
        funding_pillar = result.pillars[1]
        assert funding_pillar.name == "Funding Rate"
        assert funding_pillar.quality == "live"
        assert funding_pillar.raw_value == Decimal("0.0001")

    def test_score_clamped_0_100(self):
        """Score bleibt im Bereich 0-100."""
        result = compute_sentiment_v3(
            fng_value=Decimal("100"),
            taker_ratio_7d=Decimal("2.0"),
            dist_50dma_pct=Decimal("50"),
            vol_ratio=Decimal("5.0"),
            price_change_pct=Decimal("10"),
            history_fng=[Decimal("10")] * 90,
            history_taker=[Decimal("0.9")] * 90,
            history_dma=[Decimal("-10")] * 90,
            history_vol=[Decimal("0.8")] * 90,
        )
        assert Decimal("0") <= result.composite_score <= Decimal("100")
