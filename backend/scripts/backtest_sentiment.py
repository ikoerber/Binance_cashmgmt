#!/usr/bin/env python3
"""
SentimentEngine Backtest Script v3.

Vergleicht drei Scoring-Varianten mit echten historischen Daten:
  v1: Feste Brackets (Original-Spezifikation)
  v2: Rolling-Percentile + Score-Velocity + Regime-Switch
  v3: Correlation-Gewichte + Dispersion + Piecewise-Multiplier + Vol-Scaling

Datenquellen (echte API-Calls):
  - Fear & Greed Index: Alternative.me (seit Feb 2018)
  - Klines (OHLCV, Taker Volume): Binance Spot API
  - Funding Rate: NICHT verfuegbar fuer Backtest

4 DCA-Strategien im Vergleich:
  - Flat: Konstant 100 EUR/Woche
  - v1 Contrarian: Mehr bei Fear, weniger bei Greed (Spezifikation)
  - v2 Regime-Switch: Momentum im Mittelfeld, Contrarian an Extremen
  - v3 Dispersion+Vol: Correlation-gewichtet, Dispersion-Konfidenz, Vol-Scaling

Verwendung:
    cd backend && source venv/bin/activate
    python scripts/backtest_sentiment.py --days 2000 --symbol BTCUSDT
"""

import argparse
import csv
import json
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import requests

# Domain-Logik importieren
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.domain.sentiment import (
    PillarScore,
    SentimentResult,
    compute_sentiment,
    compute_sentiment_v2,
    compute_sentiment_v3,
    compute_score_velocity,
    get_regime_switch_multiplier,
    score_dma_composite,
    score_fear_and_greed,
    score_taker_ratio,
    score_volume_momentum,
    classify_score,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERCENTILE_WINDOW = 90  # Tage fuer Rolling-Percentile


# ---------------------------------------------------------------------------
# Data Fetching (echte API-Calls)
# ---------------------------------------------------------------------------

def fetch_fear_and_greed(limit: int = 0) -> list[dict]:
    """Holt historische Fear & Greed Daten von Alternative.me (echt)."""
    url = f"https://api.alternative.me/fng/?limit={limit}&format=json"
    print(f"  [API] Fear & Greed Index (limit={limit})...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    print(f"  -> {len(data)} Datenpunkte (seit {data[-1]['timestamp'] if data else '?'})")
    return data


def fetch_binance_klines_extended(
    symbol: str = "BTCUSDT",
    interval: str = "1d",
    days: int = 2000,
) -> list[list]:
    """Holt Klines paginiert von Binance Spot API (echt)."""
    all_klines = []
    end_time = int(datetime.now().timestamp() * 1000)
    remaining = days

    while remaining > 0:
        batch_limit = min(remaining, 1000)
        url = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": batch_limit,
            "endTime": end_time,
        }
        print(f"  [API] Binance Klines (remaining={remaining})...")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break

        all_klines = batch + all_klines
        remaining -= len(batch)
        end_time = batch[0][0] - 1
        time.sleep(0.5)

    print(f"  -> {len(all_klines)} Klines gesamt")
    return all_klines


# ---------------------------------------------------------------------------
# Data Processing
# ---------------------------------------------------------------------------

@dataclass
class DayData:
    date: datetime
    close_price: Decimal
    volume: Decimal
    taker_buy_volume: Decimal
    fng_value: Optional[Decimal] = None


def parse_klines(klines: list[list]) -> dict[str, DayData]:
    result = {}
    for k in klines:
        ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
        date_key = ts.strftime("%Y-%m-%d")
        result[date_key] = DayData(
            date=ts,
            close_price=Decimal(str(k[4])),
            volume=Decimal(str(k[5])),
            taker_buy_volume=Decimal(str(k[9])),
        )
    return result


def merge_fng_into_klines(kline_data: dict[str, DayData], fng_data: list[dict]) -> None:
    merged = 0
    for entry in fng_data:
        ts = int(entry["timestamp"])
        date_key = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if date_key in kline_data:
            kline_data[date_key].fng_value = Decimal(entry["value"])
            merged += 1
    print(f"  -> {merged} F&G-Werte mit Klines gemerged")


# ---------------------------------------------------------------------------
# Backtest Row
# ---------------------------------------------------------------------------

@dataclass
class BacktestRow:
    date: str
    close_price: Decimal
    # v1 Score
    score_v1: Decimal
    label_v1: str
    # v2 Score (Rolling-Percentile)
    score_v2: Decimal
    label_v2: str
    # Velocity (7d Aenderung des v2-Score)
    velocity_v2: Optional[Decimal]
    # Regime-Switch Multiplier
    regime_multiplier: Decimal
    # Concordance
    concordance_v1: bool
    concordance_v2: bool
    # Rohdaten
    fng_raw: Optional[Decimal]
    taker_ratio: Optional[Decimal]
    dist_50dma: Optional[Decimal]
    vol_ratio: Optional[Decimal]
    # v3 Score (Correlation-gewichtet + Dispersion + Vol-Scaling)
    score_v3: Decimal = Decimal("50")
    label_v3: str = "Neutral"
    multiplier_v3: Decimal = Decimal("1.00")
    raw_multiplier_v3: Decimal = Decimal("1.00")
    dispersion_std_v3: Decimal = Decimal("0")
    dispersion_confidence_v3: Decimal = Decimal("1")
    vol_regime_v3: str = "NORMAL"
    vol_ratio_20_120: Optional[Decimal] = None
    # Forward-Returns
    fwd_return_7d: Optional[Decimal] = None
    fwd_return_14d: Optional[Decimal] = None
    fwd_return_30d: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

def run_backtest(
    kline_data: dict[str, DayData],
    warmup_days: int = 200,
) -> list[BacktestRow]:
    sorted_dates = sorted(kline_data.keys())
    date_to_price = {d: kline_data[d].close_price for d in sorted_dates}

    results: list[BacktestRow] = []
    close_history: list[Decimal] = []
    volume_history: list[Decimal] = []

    # Rolling-Historie fuer v2 Percentile (90 Tage)
    hist_fng: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)
    hist_taker: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)
    hist_dma: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)
    hist_vol: deque[Decimal] = deque(maxlen=PERCENTILE_WINDOW)

    # Score-History fuer Velocity
    score_v2_history: list[Decimal] = []

    print(f"\nBerechne Scores fuer {len(sorted_dates)} Tage (Warmup: {warmup_days})...")

    for i, date_key in enumerate(sorted_dates):
        day = kline_data[date_key]
        close_history.append(day.close_price)
        volume_history.append(day.volume)

        if i < warmup_days:
            # Waehrend Warmup trotzdem Percentile-Historien fuettern
            if day.fng_value is not None:
                hist_fng.append(day.fng_value)
            taker_sell = day.volume - day.taker_buy_volume
            if taker_sell > 0:
                hist_taker.append(day.taker_buy_volume / taker_sell)
            if len(close_history) >= 50:
                sma50_w = sum(close_history[-50:]) / Decimal("50")
                if sma50_w > 0:
                    hist_dma.append(((day.close_price - sma50_w) / sma50_w) * Decimal("100"))
            if len(volume_history) >= 21:
                vol_20d = sum(volume_history[-20:]) / Decimal("20")
                if vol_20d > 0:
                    hist_vol.append(day.volume / vol_20d)
            continue

        # --- Rohdaten berechnen ---

        # Taker Ratios 7d
        taker_ratios_7d = []
        for j in range(max(0, i - 6), i + 1):
            d = sorted_dates[j]
            dd = kline_data[d]
            ts = dd.volume - dd.taker_buy_volume
            if ts > 0:
                taker_ratios_7d.append(dd.taker_buy_volume / ts)
        taker_ratio_avg = (
            sum(taker_ratios_7d) / Decimal(str(len(taker_ratios_7d)))
            if len(taker_ratios_7d) >= 3 else None
        )

        # DMAs
        sma50 = sum(close_history[-50:]) / Decimal("50") if len(close_history) >= 50 else None
        sma200 = sum(close_history[-200:]) / Decimal("200") if len(close_history) >= 200 else None
        dist_50dma_pct = (
            ((day.close_price - sma50) / sma50) * Decimal("100")
            if sma50 and sma50 > 0 else None
        )

        # Volume
        vol_ratio = None
        price_change_pct = None
        if len(volume_history) >= 21:
            vol_20d = sum(volume_history[-20:]) / Decimal("20")
            if vol_20d > 0:
                vol_ratio = day.volume / vol_20d
        if len(close_history) >= 2 and close_history[-2] > 0:
            price_change_pct = ((day.close_price - close_history[-2]) / close_history[-2]) * Decimal("100")

        # --- v1 Score (feste Brackets) ---
        v1_pillars = [
            score_fear_and_greed(day.fng_value),
            PillarScore(name="Funding Rate", score=Decimal("50"),
                        raw_value=None, source="okx", quality="unavailable"),
            score_taker_ratio(taker_ratio_avg),
            score_dma_composite(day.close_price, sma50, sma200),
            score_volume_momentum(vol_ratio, price_change_pct),
        ]
        result_v1 = compute_sentiment(v1_pillars)

        # --- v2 Score (Rolling-Percentile) ---
        result_v2 = compute_sentiment_v2(
            fng_value=day.fng_value,
            taker_ratio_7d=taker_ratio_avg,
            dist_50dma_pct=dist_50dma_pct,
            vol_ratio=vol_ratio,
            price_change_pct=price_change_pct,
            history_fng=list(hist_fng),
            history_taker=list(hist_taker),
            history_dma=list(hist_dma),
            history_vol=list(hist_vol),
            sma50=sma50,
            sma200=sma200,
        )

        # Percentile-Historien aktualisieren (nach Berechnung, damit heutiger
        # Wert noch nicht in seiner eigenen Percentile-Berechnung steckt)
        if day.fng_value is not None:
            hist_fng.append(day.fng_value)
        if taker_ratio_avg is not None:
            hist_taker.append(taker_ratio_avg)
        if dist_50dma_pct is not None:
            hist_dma.append(dist_50dma_pct)
        if vol_ratio is not None:
            hist_vol.append(vol_ratio)

        # --- Score-Velocity ---
        score_v2_history.append(result_v2.composite_score)
        velocity = compute_score_velocity(score_v2_history, lookback=7)

        # --- Regime-Switch Multiplier ---
        regime_mult = get_regime_switch_multiplier(result_v2.composite_score, velocity)

        # --- v3 Score (Correlation-gewichtet, Dispersion, Vol-Scaling) ---
        daily_returns_list = None
        if len(close_history) >= 121:
            daily_returns_list = []
            start_idx = max(1, len(close_history) - 120)
            for j in range(start_idx, len(close_history)):
                if close_history[j - 1] > 0:
                    daily_returns_list.append(
                        (close_history[j] - close_history[j - 1]) / close_history[j - 1]
                    )

        result_v3 = compute_sentiment_v3(
            fng_value=day.fng_value,
            taker_ratio_7d=taker_ratio_avg,
            dist_50dma_pct=dist_50dma_pct,
            vol_ratio=vol_ratio,
            price_change_pct=price_change_pct,
            history_fng=list(hist_fng),
            history_taker=list(hist_taker),
            history_dma=list(hist_dma),
            history_vol=list(hist_vol),
            sma50=sma50,
            sma200=sma200,
            daily_returns=daily_returns_list,
        )

        # --- Forward-Returns ---
        fwd_7d = fwd_14d = fwd_30d = None
        idx = i  # i == index in sorted_dates
        if idx + 7 < len(sorted_dates):
            fp = date_to_price[sorted_dates[idx + 7]]
            fwd_7d = ((fp - day.close_price) / day.close_price) * Decimal("100")
        if idx + 14 < len(sorted_dates):
            fp = date_to_price[sorted_dates[idx + 14]]
            fwd_14d = ((fp - day.close_price) / day.close_price) * Decimal("100")
        if idx + 30 < len(sorted_dates):
            fp = date_to_price[sorted_dates[idx + 30]]
            fwd_30d = ((fp - day.close_price) / day.close_price) * Decimal("100")

        row = BacktestRow(
            date=date_key,
            close_price=day.close_price,
            score_v1=result_v1.composite_score,
            label_v1=result_v1.composite_label.value,
            score_v2=result_v2.composite_score,
            label_v2=result_v2.composite_label.value,
            velocity_v2=velocity,
            regime_multiplier=regime_mult,
            concordance_v1=result_v1.concordance_applied,
            concordance_v2=result_v2.concordance_applied,
            fng_raw=day.fng_value,
            taker_ratio=taker_ratio_avg,
            dist_50dma=dist_50dma_pct,
            vol_ratio=vol_ratio,
            score_v3=result_v3.composite_score,
            label_v3=result_v3.composite_label.value,
            multiplier_v3=result_v3.recommendation.buy_size_multiplier,
            raw_multiplier_v3=result_v3.recommendation.raw_multiplier,
            dispersion_std_v3=result_v3.recommendation.dispersion.pillar_std,
            dispersion_confidence_v3=result_v3.recommendation.dispersion.confidence_factor,
            vol_regime_v3=result_v3.recommendation.volatility.regime if result_v3.recommendation.volatility else "N/A",
            vol_ratio_20_120=result_v3.recommendation.volatility.vol_ratio if result_v3.recommendation.volatility else None,
            fwd_return_7d=fwd_7d,
            fwd_return_14d=fwd_14d,
            fwd_return_30d=fwd_30d,
        )
        results.append(row)

        if (i - warmup_days) % 200 == 0:
            vel_str = f"{velocity:+.1f}" if velocity is not None else "n/a"
            vol_r = result_v3.recommendation.volatility
            vol_str = vol_r.regime if vol_r else "N/A"
            print(
                f"  Tag {i - warmup_days + 1:>5}: {date_key} | "
                f"v1={result_v1.composite_score:>5} | "
                f"v2={result_v2.composite_score:>5} | "
                f"v3={result_v3.composite_score:>5} mult={result_v3.recommendation.buy_size_multiplier} vol={vol_str:<6} | "
                f"Preis: {day.close_price:>10.2f}"
            )

    print(f"\n-> {len(results)} Tage berechnet")
    return results


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

SCORE_BUCKETS = [
    ("Extreme Fear (0-15)", Decimal("0"), Decimal("15")),
    ("Fear (16-35)", Decimal("16"), Decimal("35")),
    ("Neutral (36-65)", Decimal("36"), Decimal("65")),
    ("Greed (66-85)", Decimal("66"), Decimal("85")),
    ("Extreme Greed (86-100)", Decimal("86"), Decimal("100")),
]


def _stats(values: list[Decimal]) -> dict:
    if not values:
        return {"avg": None, "median": None, "win_rate": None, "count": 0}
    s = sorted(values)
    n = len(s)
    avg = sum(s) / Decimal(str(n))
    median = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
    win = Decimal(str(sum(1 for v in s if v > 0))) / Decimal(str(n)) * Decimal("100")
    return {
        "avg": avg.quantize(Decimal("0.01")),
        "median": median.quantize(Decimal("0.01")),
        "win_rate": win.quantize(Decimal("0.1")),
        "count": n,
    }


def analyze_by_buckets(
    results: list[BacktestRow],
    score_getter,
    label: str,
) -> dict:
    analysis = {}
    for bucket_name, lo, hi in SCORE_BUCKETS:
        rows = [r for r in results if lo <= score_getter(r) <= hi]
        if not rows:
            analysis[bucket_name] = {"count": 0, "pct_of_total": Decimal("0")}
            continue

        fwd_7d = [r.fwd_return_7d for r in rows if r.fwd_return_7d is not None]
        fwd_14d = [r.fwd_return_14d for r in rows if r.fwd_return_14d is not None]
        fwd_30d = [r.fwd_return_30d for r in rows if r.fwd_return_30d is not None]

        analysis[bucket_name] = {
            "count": len(rows),
            "pct_of_total": (Decimal(str(len(rows))) / Decimal(str(len(results))) * Decimal("100")).quantize(Decimal("0.1")),
            "fwd_7d": _stats(fwd_7d),
            "fwd_14d": _stats(fwd_14d),
            "fwd_30d": _stats(fwd_30d),
        }
    return analysis


def analyze_velocity_buckets(results: list[BacktestRow]) -> dict:
    """Analysiert Forward-Returns nach Score-Velocity."""
    VEL_BUCKETS = [
        ("Crash (<-15)", None, Decimal("-15")),
        ("Stark fallend (-15..-5)", Decimal("-15"), Decimal("-5")),
        ("Leicht fallend (-5..0)", Decimal("-5"), Decimal("0")),
        ("Leicht steigend (0..+5)", Decimal("0"), Decimal("5")),
        ("Stark steigend (+5..+15)", Decimal("5"), Decimal("15")),
        ("Euphorie (>+15)", Decimal("15"), None),
    ]
    analysis = {}
    rows_with_vel = [r for r in results if r.velocity_v2 is not None]

    for name, lo, hi in VEL_BUCKETS:
        if lo is None:
            bucket = [r for r in rows_with_vel if r.velocity_v2 <= hi]
        elif hi is None:
            bucket = [r for r in rows_with_vel if r.velocity_v2 > lo]
        else:
            bucket = [r for r in rows_with_vel if lo < r.velocity_v2 <= hi]

        if not bucket:
            analysis[name] = {"count": 0, "pct_of_total": Decimal("0")}
            continue

        fwd_7d = [r.fwd_return_7d for r in bucket if r.fwd_return_7d is not None]
        fwd_30d = [r.fwd_return_30d for r in bucket if r.fwd_return_30d is not None]
        analysis[name] = {
            "count": len(bucket),
            "pct_of_total": (Decimal(str(len(bucket))) / Decimal(str(len(rows_with_vel))) * Decimal("100")).quantize(Decimal("0.1")),
            "fwd_7d": _stats(fwd_7d),
            "fwd_30d": _stats(fwd_30d),
        }
    return analysis


# ---------------------------------------------------------------------------
# DCA Simulation (3 Strategien)
# ---------------------------------------------------------------------------

def simulate_dca_quad(
    results: list[BacktestRow],
    base_eur: Decimal = Decimal("100"),
    interval: int = 7,
) -> dict:
    """4 DCA-Strategien: Flat, v1 Contrarian, v2 Regime-Switch, v3 Dispersion+Vol."""

    # v1 Contrarian Multiplier (aus Spezifikation)
    def _v1_mult(score: Decimal) -> Decimal:
        for th, m in [
            (Decimal("15"), Decimal("1.30")),
            (Decimal("35"), Decimal("1.15")),
            (Decimal("65"), Decimal("1.00")),
            (Decimal("85"), Decimal("0.85")),
            (Decimal("100"), Decimal("0.70")),
        ]:
            if score <= th:
                return m
        return Decimal("1.00")

    flat = {"btc": Decimal("0"), "eur": Decimal("0")}
    v1 = {"btc": Decimal("0"), "eur": Decimal("0")}
    v2 = {"btc": Decimal("0"), "eur": Decimal("0")}
    v3 = {"btc": Decimal("0"), "eur": Decimal("0")}
    buys = 0

    for i, row in enumerate(results):
        if i % interval != 0 or row.close_price <= 0:
            continue
        buys += 1

        # Flat
        flat["btc"] += base_eur / row.close_price
        flat["eur"] += base_eur

        # v1 Contrarian
        m1 = _v1_mult(row.score_v1)
        v1_amount = base_eur * m1
        v1["btc"] += v1_amount / row.close_price
        v1["eur"] += v1_amount

        # v2 Regime-Switch (nutzt Velocity)
        m2 = row.regime_multiplier
        v2_amount = base_eur * m2
        v2["btc"] += v2_amount / row.close_price
        v2["eur"] += v2_amount

        # v3 Dispersion+Vol (Piecewise-Linear + Dispersion + Vol-Scaling)
        m3 = row.multiplier_v3
        v3_amount = base_eur * m3
        v3["btc"] += v3_amount / row.close_price
        v3["eur"] += v3_amount

    end_price = results[-1].close_price if results else Decimal("0")

    def _summarize(d: dict, name: str) -> dict:
        val = d["btc"] * end_price
        pnl = val - d["eur"]
        pnl_pct = (pnl / d["eur"] * Decimal("100")) if d["eur"] > 0 else Decimal("0")
        avg = d["eur"] / d["btc"] if d["btc"] > 0 else Decimal("0")
        return {
            "name": name,
            "eur_spent": d["eur"].quantize(Decimal("0.01")),
            "btc": d["btc"].quantize(Decimal("0.00000001")),
            "avg_price": avg.quantize(Decimal("0.01")),
            "value": val.quantize(Decimal("0.01")),
            "pnl_eur": pnl.quantize(Decimal("0.01")),
            "pnl_pct": pnl_pct.quantize(Decimal("0.01")),
        }

    return {
        "buys": buys,
        "end_price": end_price,
        "flat": _summarize(flat, "Flat DCA"),
        "v1_contrarian": _summarize(v1, "v1 Contrarian"),
        "v2_regime": _summarize(v2, "v2 Regime-Switch"),
        "v3_dispersion": _summarize(v3, "v3 Dispersion+Vol"),
    }


# ---------------------------------------------------------------------------
# Pillar-Korrelation (welcher Pillar hat den besten Vorhersagewert?)
# ---------------------------------------------------------------------------

def analyze_pillar_correlation(results: list[BacktestRow]) -> dict:
    """Korrelation jedes Roh-Indikators mit 30d-Forward-Returns."""
    rows = [r for r in results if r.fwd_return_30d is not None]
    if len(rows) < 50:
        return {}

    def _corr(xs: list[Decimal], ys: list[Decimal]) -> Optional[Decimal]:
        n = len(xs)
        if n < 30:
            return None
        mean_x = sum(xs) / Decimal(str(n))
        mean_y = sum(ys) / Decimal(str(n))
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / Decimal(str(n))
        var_x = sum((x - mean_x) ** 2 for x in xs) / Decimal(str(n))
        var_y = sum((y - mean_y) ** 2 for y in ys) / Decimal(str(n))
        if var_x == 0 or var_y == 0:
            return None
        # sqrt via float (Decimal.sqrt nur fuer positive)
        import math
        std_x = Decimal(str(math.sqrt(float(var_x))))
        std_y = Decimal(str(math.sqrt(float(var_y))))
        if std_x == 0 or std_y == 0:
            return None
        return (cov / (std_x * std_y)).quantize(Decimal("0.001"))

    fwd = [r.fwd_return_30d for r in rows]
    correlations = {}

    # F&G
    pairs = [(r.fng_raw, r.fwd_return_30d) for r in rows if r.fng_raw is not None and r.fwd_return_30d is not None]
    if len(pairs) >= 30:
        correlations["Fear & Greed"] = _corr([p[0] for p in pairs], [p[1] for p in pairs])

    # Taker Ratio
    pairs = [(r.taker_ratio, r.fwd_return_30d) for r in rows if r.taker_ratio is not None and r.fwd_return_30d is not None]
    if len(pairs) >= 30:
        correlations["Taker Ratio"] = _corr([p[0] for p in pairs], [p[1] for p in pairs])

    # DMA Distance
    pairs = [(r.dist_50dma, r.fwd_return_30d) for r in rows if r.dist_50dma is not None and r.fwd_return_30d is not None]
    if len(pairs) >= 30:
        correlations["DMA Distance"] = _corr([p[0] for p in pairs], [p[1] for p in pairs])

    # Volume Ratio
    pairs = [(r.vol_ratio, r.fwd_return_30d) for r in rows if r.vol_ratio is not None and r.fwd_return_30d is not None]
    if len(pairs) >= 30:
        correlations["Volume Ratio"] = _corr([p[0] for p in pairs], [p[1] for p in pairs])

    # Composite Scores
    correlations["Score v1"] = _corr([r.score_v1 for r in rows], fwd)
    correlations["Score v2"] = _corr([r.score_v2 for r in rows], fwd)
    correlations["Score v3"] = _corr([r.score_v3 for r in rows], fwd)

    # Velocity
    vel_rows = [(r.velocity_v2, r.fwd_return_30d) for r in rows if r.velocity_v2 is not None and r.fwd_return_30d is not None]
    if len(vel_rows) >= 30:
        correlations["Velocity v2"] = _corr([p[0] for p in vel_rows], [p[1] for p in vel_rows])

    return correlations


# ---------------------------------------------------------------------------
# Output / Printing
# ---------------------------------------------------------------------------

def _fmt(val):
    return f"{val:>+7.2f}%" if val is not None else "    n/a"


def _fmt_wr(val):
    return f"{val:>5.1f}%" if val is not None else "  n/a"


def print_bucket_analysis(analysis: dict, title: str) -> None:
    print("\n" + "=" * 95)
    print(title)
    print("=" * 95)
    header = (f"{'Bucket':<28} {'Tage':>6} {'%':>6} | "
              f"{'7d avg':>8} {'7d med':>8} {'7d win':>7} | "
              f"{'30d avg':>8} {'30d med':>8} {'30d win':>7}")
    print(header)
    print("-" * 95)

    for bucket_name, lo, hi in SCORE_BUCKETS:
        data = analysis.get(bucket_name, {})
        count = data.get("count", 0)
        pct = data.get("pct_of_total", Decimal("0"))
        if count == 0:
            print(f"{bucket_name:<28} {count:>6} {pct:>5}% |   (keine Daten)")
            continue
        f7 = data.get("fwd_7d", {})
        f30 = data.get("fwd_30d", {})
        print(
            f"{bucket_name:<28} {count:>6} {pct:>5}% | "
            f"{_fmt(f7.get('avg'))} {_fmt(f7.get('median'))} {_fmt_wr(f7.get('win_rate'))} | "
            f"{_fmt(f30.get('avg'))} {_fmt(f30.get('median'))} {_fmt_wr(f30.get('win_rate'))}"
        )
    print("=" * 95)


def print_velocity_analysis(analysis: dict) -> None:
    print("\n" + "=" * 80)
    print("VELOCITY-ANALYSE: Forward-Returns nach Score-Aenderungsgeschwindigkeit (v2)")
    print("=" * 80)
    header = f"{'Velocity-Bucket':<30} {'Tage':>6} {'%':>6} | {'7d avg':>8} {'7d win':>7} | {'30d avg':>8} {'30d win':>7}"
    print(header)
    print("-" * 80)

    for name, data in analysis.items():
        count = data.get("count", 0)
        pct = data.get("pct_of_total", Decimal("0"))
        if count == 0:
            print(f"{name:<30} {count:>6} {pct:>5}% |   (keine Daten)")
            continue
        f7 = data.get("fwd_7d", {})
        f30 = data.get("fwd_30d", {})
        print(
            f"{name:<30} {count:>6} {pct:>5}% | "
            f"{_fmt(f7.get('avg'))} {_fmt_wr(f7.get('win_rate'))} | "
            f"{_fmt(f30.get('avg'))} {_fmt_wr(f30.get('win_rate'))}"
        )
    print("=" * 80)


def print_pillar_correlation(correlations: dict) -> None:
    print("\n" + "=" * 55)
    print("PILLAR-KORRELATION mit 30d-Forward-Returns")
    print("(Pearson r: +1 = perfekt positiv, -1 = perfekt negativ)")
    print("=" * 55)
    sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1] or 0), reverse=True)
    for name, r in sorted_corr:
        if r is None:
            print(f"  {name:<20}  n/a")
        else:
            bar_len = int(abs(float(r)) * 30)
            direction = "+" if r > 0 else "-"
            bar = direction * bar_len
            print(f"  {name:<20} {r:>+7.3f}  {bar}")
    print("=" * 55)


def print_dca_comparison(dca: dict) -> None:
    print("\n" + "=" * 105)
    print("DCA-SIMULATION: 4 Strategien im Vergleich (woechentlich)")
    print("=" * 105)

    f = dca["flat"]
    c = dca["v1_contrarian"]
    r = dca["v2_regime"]
    d = dca["v3_dispersion"]

    print(f"Kaufzeitpunkte: {dca['buys']}")
    print(f"Endpreis:       {dca['end_price']:.2f}")
    print()
    print(f"{'':20} {'Flat DCA':>16} {'v1 Contrarian':>16} {'v2 Regime':>16} {'v3 Disp+Vol':>16}")
    print("-" * 105)
    print(f"{'EUR investiert':<20} {f['eur_spent']:>15} {c['eur_spent']:>15} {r['eur_spent']:>15} {d['eur_spent']:>15}")
    print(f"{'BTC akkumuliert':<20} {f['btc']:>15} {c['btc']:>15} {r['btc']:>15} {d['btc']:>15}")
    print(f"{'Avg. Kaufpreis':<20} {f['avg_price']:>15} {c['avg_price']:>15} {r['avg_price']:>15} {d['avg_price']:>15}")
    print(f"{'Aktueller Wert':<20} {f['value']:>15} {c['value']:>15} {r['value']:>15} {d['value']:>15}")
    print(f"{'P&L (EUR)':<20} {f['pnl_eur']:>15} {c['pnl_eur']:>15} {r['pnl_eur']:>15} {d['pnl_eur']:>15}")
    print(f"{'P&L (%)':<20} {f['pnl_pct']:>14}% {c['pnl_pct']:>14}% {r['pnl_pct']:>14}% {d['pnl_pct']:>14}%")
    print("-" * 105)

    # Deltas vs Flat
    d_v1 = c["pnl_pct"] - f["pnl_pct"]
    d_v2 = r["pnl_pct"] - f["pnl_pct"]
    d_v3 = d["pnl_pct"] - f["pnl_pct"]
    print(f"{'Delta vs. Flat':<20} {'---':>15} {d_v1:>+14.2f}% {d_v2:>+14.2f}% {d_v3:>+14.2f}%")
    print("=" * 105)

    strategies = [
        ("Flat DCA", f["pnl_pct"]),
        ("v1 Contrarian", c["pnl_pct"]),
        ("v2 Regime-Switch", r["pnl_pct"]),
        ("v3 Dispersion+Vol", d["pnl_pct"]),
    ]
    winner, best_pnl = max(strategies, key=lambda x: x[1])
    print(f"\nGewinner: {winner} ({best_pnl}%)")


def print_distribution(results: list[BacktestRow]) -> None:
    """Score-Verteilung v1 vs v2 vs v3."""
    print("\n" + "=" * 85)
    print("SCORE-VERTEILUNG: v1 (Brackets) vs. v2 (Percentile) vs. v3 (Corr-Weighted)")
    print("=" * 85)
    print(f"{'Bucket':<28} {'v1 Tage':>8} {'v1 %':>6} | {'v2 Tage':>8} {'v2 %':>6} | {'v3 Tage':>8} {'v3 %':>6}")
    print("-" * 85)

    for name, lo, hi in SCORE_BUCKETS:
        c1 = len([r for r in results if lo <= r.score_v1 <= hi])
        c2 = len([r for r in results if lo <= r.score_v2 <= hi])
        c3 = len([r for r in results if lo <= r.score_v3 <= hi])
        n = Decimal(str(len(results)))
        p1 = Decimal(str(c1)) / n * Decimal("100")
        p2 = Decimal(str(c2)) / n * Decimal("100")
        p3 = Decimal(str(c3)) / n * Decimal("100")
        print(f"{name:<28} {c1:>8} {p1:>5.1f}% | {c2:>8} {p2:>5.1f}% | {c3:>8} {p3:>5.1f}%")
    print("=" * 85)


def write_csv(results: list[BacktestRow], filepath: str) -> None:
    fieldnames = [
        "date", "close_price",
        "score_v1", "label_v1", "score_v2", "label_v2",
        "score_v3", "label_v3", "multiplier_v3", "raw_multiplier_v3",
        "dispersion_std_v3", "dispersion_confidence_v3",
        "vol_regime_v3", "vol_ratio_20_120",
        "velocity_v2", "regime_multiplier",
        "concordance_v1", "concordance_v2",
        "fng_raw", "taker_ratio", "dist_50dma_pct", "vol_ratio",
        "fwd_return_7d", "fwd_return_14d", "fwd_return_30d",
    ]

    def _d(val, prec="0.01"):
        return str(val.quantize(Decimal(prec))) if val is not None else ""

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "date": r.date,
                "close_price": str(r.close_price),
                "score_v1": _d(r.score_v1, "0.1"),
                "label_v1": r.label_v1,
                "score_v2": _d(r.score_v2, "0.1"),
                "label_v2": r.label_v2,
                "score_v3": _d(r.score_v3, "0.1"),
                "label_v3": r.label_v3,
                "multiplier_v3": _d(r.multiplier_v3, "0.01"),
                "raw_multiplier_v3": _d(r.raw_multiplier_v3, "0.001"),
                "dispersion_std_v3": _d(r.dispersion_std_v3, "0.1"),
                "dispersion_confidence_v3": _d(r.dispersion_confidence_v3, "0.001"),
                "vol_regime_v3": r.vol_regime_v3,
                "vol_ratio_20_120": _d(r.vol_ratio_20_120, "0.001") if r.vol_ratio_20_120 else "",
                "velocity_v2": _d(r.velocity_v2, "0.1"),
                "regime_multiplier": _d(r.regime_multiplier, "0.01"),
                "concordance_v1": r.concordance_v1,
                "concordance_v2": r.concordance_v2,
                "fng_raw": _d(r.fng_raw, "1") if r.fng_raw else "",
                "taker_ratio": _d(r.taker_ratio, "0.0001"),
                "dist_50dma_pct": _d(r.dist_50dma),
                "vol_ratio": _d(r.vol_ratio),
                "fwd_return_7d": _d(r.fwd_return_7d),
                "fwd_return_14d": _d(r.fwd_return_14d),
                "fwd_return_30d": _d(r.fwd_return_30d),
            })
    print(f"\nCSV: {filepath}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SentimentEngine Backtest v3")
    parser.add_argument("--days", type=int, default=2000)
    parser.add_argument("--symbol", type=str, default="BTCUSDT")
    parser.add_argument("--output", type=str, default="scripts/results")
    parser.add_argument("--dca-amount", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=200)
    args = parser.parse_args()

    print("=" * 70)
    print("SentimentEngine Backtest v3")
    print("v1 (Brackets) vs. v2 (Percentile) vs. v3 (Corr-Weight+Disp+Vol)")
    print("=" * 70)
    print(f"Symbol:           {args.symbol}")
    print(f"Tage:             {args.days}")
    print(f"Warmup:           {args.warmup}")
    print(f"Percentile-Window: {PERCENTILE_WINDOW} Tage")
    print(f"Datenquellen:     Alternative.me (F&G) + Binance Spot (Klines)")
    print()

    # 1. Echte Daten holen
    print("--- Phase 1: Echte Daten holen ---")
    fng_data = fetch_fear_and_greed(limit=0)
    time.sleep(0.5)
    klines = fetch_binance_klines_extended(args.symbol, "1d", args.days)

    # 2. Aufbereiten
    print("\n--- Phase 2: Daten aufbereiten ---")
    kline_data = parse_klines(klines)
    merge_fng_into_klines(kline_data, fng_data)

    dates = sorted(kline_data.keys())
    print(f"  Zeitraum: {dates[0]} bis {dates[-1]} ({len(dates)} Tage)")

    # 3. Backtest
    print("\n--- Phase 3: Backtest (v1 + v2 parallel) ---")
    results = run_backtest(kline_data, warmup_days=args.warmup)
    if not results:
        print("FEHLER: Keine Ergebnisse.")
        sys.exit(1)

    # 4. Analyse
    print("\n--- Phase 4: Analyse ---")

    # 4a. Score-Verteilung
    print_distribution(results)

    # 4b. Forward-Returns pro Bucket (v1 vs v2 vs v3)
    analysis_v1 = analyze_by_buckets(results, lambda r: r.score_v1, "v1")
    print_bucket_analysis(analysis_v1, "v1 FORWARD-RETURNS (feste Brackets)")

    analysis_v2 = analyze_by_buckets(results, lambda r: r.score_v2, "v2")
    print_bucket_analysis(analysis_v2, "v2 FORWARD-RETURNS (Rolling-Percentile)")

    analysis_v3 = analyze_by_buckets(results, lambda r: r.score_v3, "v3")
    print_bucket_analysis(analysis_v3, "v3 FORWARD-RETURNS (Correlation-Weighted)")

    # 4c. Velocity-Analyse
    vel_analysis = analyze_velocity_buckets(results)
    print_velocity_analysis(vel_analysis)

    # 4d. Pillar-Korrelation
    correlations = analyze_pillar_correlation(results)
    print_pillar_correlation(correlations)

    # 5. DCA-Simulation
    print("\n--- Phase 5: DCA-Simulation ---")
    dca = simulate_dca_quad(results, base_eur=Decimal(str(args.dca_amount)))
    print_dca_comparison(dca)

    # 6. Output
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"backtest_v3_{args.symbol}_{ts}.csv"
    write_csv(results, str(csv_path))

    json_path = output_dir / f"analysis_v3_{args.symbol}_{ts}.json"

    def _ser(obj):
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    with open(json_path, "w") as f:
        json.dump({
            "params": vars(args),
            "analysis_v1": analysis_v1,
            "analysis_v2": analysis_v2,
            "analysis_v3": analysis_v3,
            "velocity_analysis": vel_analysis,
            "correlations": correlations,
            "dca_simulation": dca,
        }, f, indent=2, default=_ser)
    print(f"JSON: {json_path}")

    # Summary
    print("\n" + "=" * 70)
    print("ZUSAMMENFASSUNG")
    print("=" * 70)
    print(f"Zeitraum:          {results[0].date} bis {results[-1].date}")
    print(f"Tage analysiert:   {len(results)}")
    print(f"Pillars aktiv:     4 von 5 (Funding Rate nicht im Backtest)")
    print(f"v3 Gewichte:       DMA 42%, F&G 28%, Taker 18%, Volume 12%")
    print(f"v3 Features:       Piecewise-Linear Multiplier, Dispersion-Konfidenz, Vol-Scaling")
    print(f"Datenquellen:      ECHTE API-Daten (Alternative.me + Binance)")


if __name__ == "__main__":
    main()
