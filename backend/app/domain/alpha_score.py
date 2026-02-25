"""
Alpha Score Domain-Logik (pure, kein I/O).

Vier unabhaengige quantitative Faktor-Berechnungen fuer den Alpha Score (-5 bis +5):
  1. Z-Score Mean Reversion (XRP/BTC Ratio)
  2. Lead-Lag Momentum (BTC fuehrt XRP)
  3. Orderbook Imbalance (Bid/Ask Volumen)
  4. Funding Rate Score (OKX Funding)

Alle Berechnungen verwenden Decimal (kein float).
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUBSCORE_MIN = Decimal("-5")
_SUBSCORE_MAX = Decimal("5")

# Z-Score mapping: Z=-3 -> +5, Z=0 -> 0, Z=+3 -> -5
_ZSCORE_MAP_RANGE = Decimal("3")

# Funding rate: |rate| >= 0.1% (0.001) maps to +/-5
_FUNDING_RATE_MAX = Decimal("0.001")

# Lead-Lag: correlation threshold for signal
_LEADLAG_CORR_THRESHOLD = Decimal("0.3")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AlphaFactorScore:
    """A single factor's contribution to the Alpha Score."""
    name: str
    sub_score: Decimal          # -5 to +5 per factor
    raw_value: Optional[Decimal]
    weight: Decimal             # Current weight (may be regime-adjusted)
    base_weight: Decimal        # User-configured weight before regime adjustment
    quality: str                # "live" | "cached" | "stale" | "unavailable" | "warmup"
    description: str = ""


@dataclass
class ZScoreResult:
    """Result of Z-Score Mean Reversion computation."""
    zscore: Decimal             # Raw Z-Score value
    sub_score: Decimal          # Mapped to -5..+5
    mean: Decimal
    std: Decimal
    current_ratio: Decimal
    window_size: int
    quality: str                # "live" | "warmup"


@dataclass
class LeadLagResult:
    """Result of Lead-Lag Momentum computation."""
    sub_score: Decimal          # -5..+5
    best_lag: int               # Lag with highest correlation (0 = no lag)
    best_correlation: Decimal   # Correlation at best lag
    btc_move_strength: Decimal  # Recent BTC return magnitude in std devs
    quality: str                # "live" | "warmup"


@dataclass
class OrderbookImbalanceResult:
    """Result of Orderbook Imbalance computation."""
    sub_score: Decimal          # -5..+5
    imbalance_ratio: Decimal    # -1 to +1 (bid_vol - ask_vol) / total
    bid_volume: Decimal
    ask_volume: Decimal
    quality: str                # "live" | "unavailable"


@dataclass
class FundingRateResult:
    """Result of Funding Rate Score computation."""
    sub_score: Decimal          # -5..+5
    raw_rate: Decimal           # The funding rate value
    divergence: Optional[Decimal]  # Divergence from BTC funding (if available)
    quality: str                # "live" | "unavailable"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_subscore(value: Decimal) -> Decimal:
    """Clamp a sub-score to [-5, +5]."""
    return max(_SUBSCORE_MIN, min(_SUBSCORE_MAX, value))


def _decimal_std(values: List[Decimal]) -> Decimal:
    """Population standard deviation in Decimal."""
    n = Decimal(str(len(values)))
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return variance.sqrt() if variance > 0 else Decimal("0")


def _decimal_mean(values: List[Decimal]) -> Decimal:
    """Mean in Decimal."""
    return sum(values) / Decimal(str(len(values)))


def _decimal_pearson_correlation(
    xs: List[Decimal],
    ys: List[Decimal],
) -> Decimal:
    """
    Pearson correlation coefficient in pure Decimal.

    Returns 0 if either series has zero variance.
    """
    n = len(xs)
    if n == 0:
        return Decimal("0")

    n_dec = Decimal(str(n))
    mean_x = sum(xs) / n_dec
    mean_y = sum(ys) / n_dec

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / n_dec
    var_x = sum((x - mean_x) ** 2 for x in xs) / n_dec
    var_y = sum((y - mean_y) ** 2 for y in ys) / n_dec

    if var_x == 0 or var_y == 0:
        return Decimal("0")

    std_x = var_x.sqrt()
    std_y = var_y.sqrt()

    if std_x == 0 or std_y == 0:
        return Decimal("0")

    return cov / (std_x * std_y)


# ---------------------------------------------------------------------------
# Factor 1: Z-Score Mean Reversion
# ---------------------------------------------------------------------------

def compute_zscore_mean_reversion(
    prices: List[Decimal],
    window: int = 60,
) -> ZScoreResult:
    """
    Z-Score of current XRP/BTC ratio vs rolling window.

    Negative Z-Score (ratio below mean) = XRP undervalued vs BTC = BUY signal (+sub_score)
    Positive Z-Score (ratio above mean) = XRP overvalued vs BTC = SELL signal (-sub_score)

    Mapping: Z=-3 -> +5, Z=0 -> 0, Z=+3 -> -5. Linear, clamped to [-5, +5].

    Args:
        prices: XRPBTC close prices (newest last)
        window: Rolling window size (default 60)

    Returns:
        ZScoreResult with zscore, sub_score, mean, std, quality
    """
    if len(prices) < window:
        return ZScoreResult(
            zscore=Decimal("0"),
            sub_score=Decimal("0"),
            mean=Decimal("0"),
            std=Decimal("0"),
            current_ratio=prices[-1] if prices else Decimal("0"),
            window_size=len(prices),
            quality="warmup",
        )

    window_prices = prices[-window:]
    n = Decimal(str(window))
    mean = sum(window_prices) / n
    variance = sum((p - mean) ** 2 for p in window_prices) / n
    std = variance.sqrt() if variance > 0 else Decimal("0")

    if std == 0:
        return ZScoreResult(
            zscore=Decimal("0"),
            sub_score=Decimal("0"),
            mean=mean,
            std=std,
            current_ratio=prices[-1],
            window_size=window,
            quality="live",
        )

    zscore = (prices[-1] - mean) / std

    # Map Z-Score to sub_score: Z=-3 -> +5, Z=0 -> 0, Z=+3 -> -5
    # sub_score = -zscore * 5/3
    sub_score = (-zscore * _SUBSCORE_MAX / _ZSCORE_MAP_RANGE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    sub_score = _clamp_subscore(sub_score)

    return ZScoreResult(
        zscore=zscore.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        sub_score=sub_score,
        mean=mean,
        std=std,
        current_ratio=prices[-1],
        window_size=window,
        quality="live",
    )


# ---------------------------------------------------------------------------
# Factor 2: Lead-Lag Momentum
# ---------------------------------------------------------------------------

def compute_leadlag_momentum(
    btc_returns: List[Decimal],
    xrp_returns: List[Decimal],
    window: int = 30,
    max_lag: int = 10,
) -> LeadLagResult:
    """
    Detect BTC price movements that XRP has not yet followed.

    Cross-correlates BTCEUR returns with XRPBTC returns at lags 1..max_lag.
    If BTC moved strongly (> 1 std dev) and XRP lagged (high correlation at lag > 0),
    sub_score is positive (buy XRP, anticipating catch-up).

    Args:
        btc_returns: BTCEUR return series (aligned timestamps)
        xrp_returns: XRPBTC return series (aligned timestamps)
        window: Minimum data requirement (default 30)
        max_lag: Maximum lag to test (default 10)

    Returns:
        LeadLagResult with sub_score, best_lag, correlation, btc_move_strength
    """
    # Use the shorter series length
    min_len = min(len(btc_returns), len(xrp_returns))
    btc_returns = btc_returns[:min_len]
    xrp_returns = xrp_returns[:min_len]

    if min_len < window:
        return LeadLagResult(
            sub_score=Decimal("0"),
            best_lag=0,
            best_correlation=Decimal("0"),
            btc_move_strength=Decimal("0"),
            quality="warmup",
        )

    # Check if all returns are zero
    if all(r == Decimal("0") for r in btc_returns) or all(r == Decimal("0") for r in xrp_returns):
        return LeadLagResult(
            sub_score=Decimal("0"),
            best_lag=0,
            best_correlation=Decimal("0"),
            btc_move_strength=Decimal("0"),
            quality="live",
        )

    # Compute BTC move strength (recent BTC return in std devs)
    btc_std = _decimal_std(btc_returns)
    btc_mean = _decimal_mean(btc_returns)
    recent_btc_return = btc_returns[-1]

    if btc_std > 0:
        btc_move_strength = (recent_btc_return - btc_mean) / btc_std
    else:
        btc_move_strength = Decimal("0")

    # Cross-correlate at lags 1..max_lag
    # lag=k means: correlate btc_returns[:-k] with xrp_returns[k:]
    # This tests if BTC movement at time t predicts XRP movement at time t+k
    best_lag = 0
    best_corr = Decimal("0")
    best_corr_abs = Decimal("0")

    for lag in range(1, max_lag + 1):
        if lag >= min_len:
            break

        btc_segment = btc_returns[:min_len - lag]
        xrp_segment = xrp_returns[lag:]

        if len(btc_segment) < 10:  # Need minimum data for meaningful correlation
            continue

        corr = _decimal_pearson_correlation(btc_segment, xrp_segment)
        corr_abs = abs(corr)

        if corr_abs > best_corr_abs:
            best_corr_abs = corr_abs
            best_corr = corr
            best_lag = lag

    # Signal computation:
    # If BTC moved strongly and correlation is significant, generate signal
    # Direction: If BTC went up (positive return) and XRP lags -> buy XRP (positive score)
    #            If BTC went down and XRP lags -> sell XRP (negative score)

    if best_corr_abs < _LEADLAG_CORR_THRESHOLD or btc_std == 0:
        sub_score = Decimal("0")
    else:
        # Signal strength = BTC move strength * correlation magnitude
        # Recent cumulative BTC return (last 5 candles for responsiveness)
        recent_window = min(5, min_len)
        recent_btc_sum = sum(btc_returns[-recent_window:])
        recent_xrp_sum = sum(xrp_returns[-recent_window:])

        # Divergence: BTC moved but XRP didn't follow yet
        divergence = recent_btc_sum - recent_xrp_sum

        # Scale by correlation strength and divergence
        # Positive divergence (BTC up more than XRP) + positive correlation = buy XRP
        signal_raw = divergence * best_corr_abs * Decimal("50")

        sub_score = signal_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sub_score = _clamp_subscore(sub_score)

    return LeadLagResult(
        sub_score=sub_score,
        best_lag=best_lag,
        best_correlation=best_corr.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        btc_move_strength=btc_move_strength.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        quality="live",
    )


# ---------------------------------------------------------------------------
# Factor 3: Orderbook Imbalance
# ---------------------------------------------------------------------------

def compute_orderbook_imbalance(
    bids: List[Tuple[Decimal, Decimal]],
    asks: List[Tuple[Decimal, Decimal]],
    mid_price: Decimal,
    band_pct: Decimal = Decimal("0.01"),
) -> OrderbookImbalanceResult:
    """
    Compute orderbook imbalance from bid/ask volume within a price band.

    Imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol)
    Mapped linearly from [-1, +1] to [-5, +5].

    Args:
        bids: List of (price, quantity) tuples
        asks: List of (price, quantity) tuples
        mid_price: Current mid price
        band_pct: Band percentage around mid price (default 1%)

    Returns:
        OrderbookImbalanceResult with sub_score, imbalance_ratio, volumes
    """
    if not bids and not asks:
        return OrderbookImbalanceResult(
            sub_score=Decimal("0"),
            imbalance_ratio=Decimal("0"),
            bid_volume=Decimal("0"),
            ask_volume=Decimal("0"),
            quality="unavailable",
        )

    band_low = mid_price * (Decimal("1") - band_pct)
    band_high = mid_price * (Decimal("1") + band_pct)

    # Sum bid volume within band
    bid_volume = Decimal("0")
    for price, qty in bids:
        if band_low <= price <= band_high:
            bid_volume += qty

    # Sum ask volume within band
    ask_volume = Decimal("0")
    for price, qty in asks:
        if band_low <= price <= band_high:
            ask_volume += qty

    total_volume = bid_volume + ask_volume

    if total_volume == 0:
        return OrderbookImbalanceResult(
            sub_score=Decimal("0"),
            imbalance_ratio=Decimal("0"),
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            quality="live",
        )

    # Imbalance ratio: -1 (all asks) to +1 (all bids)
    imbalance_ratio = (bid_volume - ask_volume) / total_volume

    # Map linearly from [-1, +1] to [-5, +5]
    sub_score = (imbalance_ratio * _SUBSCORE_MAX).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    sub_score = _clamp_subscore(sub_score)

    return OrderbookImbalanceResult(
        sub_score=sub_score,
        imbalance_ratio=imbalance_ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        bid_volume=bid_volume,
        ask_volume=ask_volume,
        quality="live",
    )


# ---------------------------------------------------------------------------
# Factor 4: Funding Rate Score
# ---------------------------------------------------------------------------

def compute_funding_rate_score(
    funding_rate: Optional[Decimal],
    btc_funding: Optional[Decimal] = None,
) -> FundingRateResult:
    """
    Score the funding rate as a contrarian indicator.

    High positive funding = overleveraged longs = sell signal (negative sub_score).
    High negative funding = overleveraged shorts = buy signal (positive sub_score).
    Scale: |rate| >= 0.1% (0.001) maps to +/-5.

    With BTC reference: relative divergence adds signal.

    Args:
        funding_rate: Current funding rate for target asset (e.g., XRP-USDT-SWAP)
        btc_funding: Optional BTC funding rate for relative comparison

    Returns:
        FundingRateResult with sub_score, raw_rate, divergence
    """
    if funding_rate is None:
        return FundingRateResult(
            sub_score=Decimal("0"),
            raw_rate=Decimal("0"),
            divergence=None,
            quality="unavailable",
        )

    # Base score: linear mapping of funding rate to sub_score
    # Negative rate -> positive score (buy signal)
    # Positive rate -> negative score (sell signal)
    # |rate| >= 0.001 maps to |sub_score| = 5
    if _FUNDING_RATE_MAX > 0:
        base_score = (-funding_rate * _SUBSCORE_MAX / _FUNDING_RATE_MAX).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
    else:
        base_score = Decimal("0")

    # Divergence adjustment (if BTC funding is available)
    divergence = None
    divergence_adjustment = Decimal("0")
    if btc_funding is not None:
        divergence = funding_rate - btc_funding
        # If asset funding is more negative than BTC -> extra buy signal
        # If asset funding is more positive than BTC -> extra sell signal
        divergence_score = (-divergence * _SUBSCORE_MAX / _FUNDING_RATE_MAX * Decimal("0.3")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        divergence_adjustment = divergence_score

    sub_score = _clamp_subscore(base_score + divergence_adjustment)

    return FundingRateResult(
        sub_score=sub_score,
        raw_rate=funding_rate,
        divergence=divergence,
        quality="live",
    )
