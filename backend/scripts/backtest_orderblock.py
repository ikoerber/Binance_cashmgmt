#!/usr/bin/env python3
"""
Orderblock Detection & Backtest CLI Runner.

Modi:
  single:  Einzelner Backtest mit festen Parametern (Default)
  sweep:   Parameter-Sweep ueber ATR-Mult, Target-R:R, Timeframes

Verwendung:
    cd backend && source venv/bin/activate

    # Einzel-Backtest
    python scripts/backtest_orderblock.py --symbol BTCEUR --interval 1h --months 6

    # Parameter-Sweep (Standardwerte)
    python scripts/backtest_orderblock.py --mode sweep --months 12

    # Sweep mit eigenen Ranges
    python scripts/backtest_orderblock.py --mode sweep --months 12 \
        --sweep-atr-mults 1.5,2.0,2.5,3.0 \
        --sweep-rrs 1.5,2.0,3.0 \
        --sweep-intervals 1h,4h

    # CSV-Export
    python scripts/backtest_orderblock.py --mode sweep --months 12 --csv sweep_results.csv
"""

import argparse
import csv as csv_module
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

# Domain-Logik importieren
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.orderblock import OBConfig
from app.services.orderblock_data_service import OrderblockDataService

# ---------------------------------------------------------------------------
# Dataclass fuer Sweep-Ergebnisse
# ---------------------------------------------------------------------------


@dataclass
class SweepRow:
    """Eine Zeile im Sweep-Ergebnis."""

    interval: str
    atr_mult: str
    target_rr: str
    zones: int
    trades: int
    hits: int
    misses: int
    expired: int
    open_trades: int
    hit_rate: Optional[str]
    expectancy: Optional[str]
    hc_count: int
    hc_hit_rate: Optional[str]
    std_hit_rate: Optional[str]
    avg_pen: str
    med_pen: str
    avg_hold: str
    med_hold: str
    zones_per_month: str


# ---------------------------------------------------------------------------
# Single Backtest
# ---------------------------------------------------------------------------


def run_single(args):
    """Einzelner Backtest mit festem Parameter-Set."""
    config = OBConfig(
        atr_length=args.atr_length,
        atr_multiplier=Decimal(str(args.atr_mult)),
        target_rr=Decimal(str(args.target_rr)),
        zscore_threshold=Decimal(str(args.zscore_threshold)),
        max_holding_candles=args.max_holding,
    )

    print("=" * 70)
    print("  ORDERBLOCK DETECTION & BACKTEST")
    print("=" * 70)
    print(f"  Symbol:     {args.symbol}")
    print(f"  Interval:   {args.interval}")
    print(f"  Monate:     {args.months}")
    print(f"  ATR:        length={config.atr_length}, mult={config.atr_multiplier}")
    print(f"  Target R:R: {config.target_rr}")
    print(f"  Max Hold:   {config.max_holding_candles} Kerzen (0=deaktiviert)")
    print(
        f"  Z-Score:    lookback={config.zscore_lookback}, threshold={config.zscore_threshold}"
    )
    print("=" * 70)
    print()

    service = OrderblockDataService()

    # --- Phase 1: Kline-Daten laden ---
    print("[1/3] Kline-Daten laden...")
    t0 = time.time()
    candles = service.fetch_candles(args.symbol, args.interval, months=args.months)
    t1 = time.time()
    print(f"      {len(candles)} Kerzen geladen ({t1 - t0:.1f}s)")

    if not candles:
        print("FEHLER: Keine Kline-Daten erhalten.")
        sys.exit(1)

    print(f"      Zeitraum: {candles[0].timestamp} bis {candles[-1].timestamp}")
    print()

    # --- Phase 2: Detection ---
    print("[2/3] Detection ausfuehren...")
    t0 = time.time()
    result = service.run_backtest(args.symbol, args.interval, args.months, config)
    t1 = time.time()
    print(f"      Detection + Backtest in {t1 - t0:.1f}s")
    print()

    # --- Phase 3: Report ---
    _print_single_report(result, float(config.target_rr))


def _print_single_report(result, target_rr: float = 2.0):
    """Formatierter Report fuer Einzel-Backtest."""
    metrics = result.get("metrics", {})
    zones = result.get("zones", [])

    print("=" * 70)
    print("  ERGEBNIS")
    print("=" * 70)
    print()

    # Zonen-Uebersicht
    print(f"  Erkannte Zonen:         {metrics.get('total_zones', 0)}")
    print(f"    - UNMITIGATED:        {metrics.get('unmitigated_count', 0)}")
    print(f"    - MITIGATED:          {metrics.get('mitigated_count', 0)}")
    print(f"    - INVALID:            {metrics.get('invalid_count', 0)}")
    print(
        f"  Zonen/Monat:            {_fmt_dec(metrics.get('zones_per_month', '0'), 2)}"
    )
    print()

    # Backtest-Metriken
    print("  ─── Backtest-Metriken ───")
    print(f"  Trades:                 {metrics.get('total_trades', 0)}")
    print(f"    - Hits:               {metrics.get('hits', 0)}")
    print(f"    - Misses:             {metrics.get('misses', 0)}")
    print(f"    - Expired:            {metrics.get('expired_trades', 0)}")
    print(f"    - Open:               {metrics.get('open_trades', 0)}")
    hit_rate = metrics.get("hit_rate")
    print(f"  Hit-Rate:               {_fmt_pct(hit_rate)}")
    print(f"  Expectancy:             {_compute_expectancy_str(metrics, target_rr)}")
    print()

    print(
        f"  Avg Penetration Depth:  {_fmt_dec(metrics.get('avg_penetration_depth_pct', '0'), 1)}%"
    )
    print(
        f"  Median Penetration:     {_fmt_dec(metrics.get('median_penetration_depth_pct', '0'), 1)}%"
    )
    print(
        f"  Avg Holding Duration:   {_fmt_dec(metrics.get('avg_holding_duration_candles', '0'), 1)} Kerzen"
    )
    print(
        f"  Median Holding:         {_fmt_dec(metrics.get('median_holding_duration_candles', '0'), 1)} Kerzen"
    )
    print()

    # 4-Level Conviction Breakdown
    breakdown = metrics.get("conviction_breakdown", [])
    if breakdown:
        print("  ─── Conviction Breakdown (4-Level) ───")
        print(
            f"  {'Level':<16} {'Count':>6} {'Hits':>6} {'Miss':>6} {'Exp':>5} {'HR':>10}"
        )
        print(
            f"  {'─' * 16} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 5} {'─' * 10}"
        )
        for b in breakdown:
            hr = _fmt_pct(b.get("hit_rate"))
            print(
                f"  {b['level']:<16} {b['count']:>6} {b['hits']:>6} "
                f"{b['misses']:>6} {b.get('expired', 0):>5} {hr:>10}"
            )
    else:
        # Fallback: alte 2-Level Felder
        print("  ─── Conviction Breakdown ───")
        print(f"  HIGH Count:             {metrics.get('high_conviction_count', 0)}")
        print(
            f"  HIGH HR:                {_fmt_pct(metrics.get('high_conviction_hit_rate'))}"
        )
        print(
            f"  STANDARD HR:            {_fmt_pct(metrics.get('standard_conviction_hit_rate'))}"
        )
    print()

    # Z-Score Cluster
    clusters = metrics.get("zscore_clusters", [])
    if clusters:
        print("  ─── Z-Score Cluster Hit-Rates ───")
        print(
            f"  {'Range':<12} {'Count':>6} {'Hits':>6} {'Misses':>6} {'Hit-Rate':>10}"
        )
        print(f"  {'─' * 12} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 10}")
        for c in clusters:
            hr = _fmt_pct(c.get("hit_rate"))
            print(
                f"  {c['range_label']:<12} {c['count']:>6} {c['hits']:>6} "
                f"{c['misses']:>6} {hr:>10}"
            )
        print()

    # Top 10 Zonen
    if zones:
        print("  ─── Top 10 Zonen (neueste) ───")
        print(
            f"  {'ID':<30} {'Dir':<8} {'State':<12} {'Conv':<14} {'Score':>6} {'Z-Score':>8}"
        )
        print(
            f"  {'─' * 30} {'─' * 8} {'─' * 12} {'─' * 14} {'─' * 6} {'─' * 8}"
        )
        for z in zones[:10]:
            zs = _fmt_dec(z.get("volume_zscore", "0"), 2)
            cs = _fmt_dec(z.get("conviction_score", "0"), 1)
            print(
                f"  {z['id']:<30} {z['direction']:<8} {z['state']:<12} "
                f"{z['conviction']:<14} {cs:>6} {zs:>8}"
            )
        print()

    print("=" * 70)
    print("  DONE")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Parameter-Sweep
# ---------------------------------------------------------------------------


def run_sweep(args):
    """Parameter-Sweep ueber ATR-Mult x Target-R:R x Intervals."""
    atr_mults = _parse_floats(args.sweep_atr_mults)
    target_rrs = _parse_floats(args.sweep_rrs)
    intervals = [s.strip() for s in args.sweep_intervals.split(",")]

    total_combos = len(intervals) * len(atr_mults) * len(target_rrs)

    print("=" * 70)
    print("  ORDERBLOCK PARAMETER-SWEEP")
    print("=" * 70)
    print(f"  Symbol:     {args.symbol}")
    print(f"  Monate:     {args.months}")
    print(f"  Intervals:  {', '.join(intervals)}")
    print(f"  ATR-Mults:  {', '.join(str(x) for x in atr_mults)}")
    print(f"  Target-RRs: {', '.join(str(x) for x in target_rrs)}")
    print(f"  Z-Score TH: {args.zscore_threshold}")
    print(f"  Kombinationen: {total_combos}")
    print("=" * 70)
    print()

    service = OrderblockDataService()
    rows: list[SweepRow] = []
    combo_nr = 0
    t_start = time.time()

    for interval in intervals:
        # Klines einmal pro Interval laden (Cache)
        print(f"[{interval}] Klines laden...")
        t0 = time.time()
        candles = service.fetch_candles(args.symbol, interval, months=args.months)
        t1 = time.time()
        print(f"  {len(candles)} Kerzen ({t1 - t0:.1f}s)")

        if not candles:
            print(f"  WARNUNG: Keine Daten fuer {interval}, ueberspringe.")
            combo_nr += len(atr_mults) * len(target_rrs)
            continue

        for atr_mult in atr_mults:
            for target_rr in target_rrs:
                combo_nr += 1
                config = OBConfig(
                    atr_length=args.atr_length,
                    atr_multiplier=Decimal(str(atr_mult)),
                    target_rr=Decimal(str(target_rr)),
                    zscore_threshold=Decimal(str(args.zscore_threshold)),
                    max_holding_candles=args.max_holding,
                )

                result = service.run_backtest(
                    args.symbol, interval, args.months, config
                )
                m = result.get("metrics", {})

                row = SweepRow(
                    interval=interval,
                    atr_mult=str(atr_mult),
                    target_rr=str(target_rr),
                    zones=m.get("total_zones", 0),
                    trades=m.get("total_trades", 0),
                    hits=m.get("hits", 0),
                    misses=m.get("misses", 0),
                    expired=m.get("expired_trades", 0),
                    open_trades=m.get("open_trades", 0),
                    hit_rate=_fmt_pct(m.get("hit_rate")),
                    expectancy=_compute_expectancy_str(m, target_rr),
                    hc_count=m.get("high_conviction_count", 0),
                    hc_hit_rate=_fmt_pct(m.get("high_conviction_hit_rate")),
                    std_hit_rate=_fmt_pct(m.get("standard_conviction_hit_rate")),
                    avg_pen=_fmt_dec(m.get("avg_penetration_depth_pct", "0"), 1),
                    med_pen=_fmt_dec(m.get("median_penetration_depth_pct", "0"), 1),
                    avg_hold=_fmt_dec(m.get("avg_holding_duration_candles", "0"), 1),
                    med_hold=_fmt_dec(m.get("median_holding_duration_candles", "0"), 1),
                    zones_per_month=_fmt_dec(m.get("zones_per_month", "0"), 1),
                )
                rows.append(row)

                print(
                    f"  [{combo_nr}/{total_combos}] {interval} ATR={atr_mult} RR={target_rr}"
                    f"  →  Zonen={row.zones} Trades={row.trades}"
                    f" HR={row.hit_rate} Exp={row.expectancy}"
                )

    t_total = time.time() - t_start
    print()
    print(f"  Sweep abgeschlossen in {t_total:.1f}s")
    print()

    # Ergebnis-Tabelle
    _print_sweep_table(rows)

    # CSV Export
    if args.csv:
        _export_csv(rows, args.csv, args.symbol, args.months)

    # Beste Kombination
    _print_best(rows)


def _print_sweep_table(rows: list[SweepRow]):
    """Formatierte Sweep-Ergebnis-Tabelle."""
    print("=" * 120)
    print("  SWEEP-ERGEBNISSE")
    print("=" * 120)
    print()

    hdr = (
        f"  {'TF':<5} {'ATR':>5} {'RR':>5} {'Zones':>6} {'Trades':>7}"
        f" {'Hits':>5} {'Miss':>5} {'HR':>8} {'Expect':>8}"
        f" {'HC':>4} {'HC-HR':>8} {'Std-HR':>8}"
        f" {'AvgPen':>7} {'MedPen':>7} {'AvgHld':>7} {'Z/Mo':>6}"
    )
    print(hdr)
    print(
        f"  {'─' * 5} {'─' * 5} {'─' * 5} {'─' * 6} {'─' * 7}"
        f" {'─' * 5} {'─' * 5} {'─' * 8} {'─' * 8}"
        f" {'─' * 4} {'─' * 8} {'─' * 8}"
        f" {'─' * 7} {'─' * 7} {'─' * 7} {'─' * 6}"
    )

    for r in rows:
        print(
            f"  {r.interval:<5} {r.atr_mult:>5} {r.target_rr:>5}"
            f" {r.zones:>6} {r.trades:>7}"
            f" {r.hits:>5} {r.misses:>5} {r.hit_rate:>8} {r.expectancy:>8}"
            f" {r.hc_count:>4} {r.hc_hit_rate:>8} {r.std_hit_rate:>8}"
            f" {r.avg_pen:>7} {r.med_pen:>7} {r.avg_hold:>7} {r.zones_per_month:>6}"
        )

    print()


def _print_best(rows: list[SweepRow]):
    """Beste Kombination nach Expectancy."""
    # Filter: mindestens 5 abgeschlossene Trades
    valid = [r for r in rows if (r.hits + r.misses) >= 5]
    if not valid:
        print("  Keine Kombination mit >= 5 abgeschlossenen Trades.")
        return

    # Sortiere nach Expectancy (absteigend)
    def _exp_sort_key(r: SweepRow) -> float:
        try:
            return float(r.expectancy.rstrip("R")) if r.expectancy != "N/A" else -999
        except (ValueError, AttributeError):
            return -999

    valid.sort(key=_exp_sort_key, reverse=True)
    best = valid[0]

    print("=" * 70)
    print("  BESTE KOMBINATION (min. 5 Trades, nach Expectancy)")
    print("=" * 70)
    print(f"  Timeframe:     {best.interval}")
    print(f"  ATR-Mult:      {best.atr_mult}")
    print(f"  Target-RR:     {best.target_rr}")
    print(f"  Zonen:         {best.zones}")
    print(f"  Trades:        {best.trades} ({best.hits}H / {best.misses}M)")
    print(f"  Hit-Rate:      {best.hit_rate}")
    print(f"  Expectancy:    {best.expectancy}")
    print(f"  HC Hit-Rate:   {best.hc_hit_rate} ({best.hc_count} Trades)")
    print(f"  Avg Pen:       {best.avg_pen}%")
    print(f"  Avg Holding:   {best.avg_hold} Kerzen")
    print("=" * 70)

    # Top 3
    if len(valid) >= 3:
        print()
        print("  Top 3:")
        for i, r in enumerate(valid[:3], 1):
            print(
                f"    {i}. {r.interval} ATR={r.atr_mult} RR={r.target_rr}"
                f"  HR={r.hit_rate} Exp={r.expectancy}"
                f"  ({r.hits}H/{r.misses}M, {r.zones} Zonen)"
            )
    print()


def _export_csv(rows: list[SweepRow], filepath: str, symbol: str, months: int):
    """Exportiert Sweep-Ergebnisse als CSV."""
    path = Path(filepath)
    with open(path, "w", newline="") as f:
        writer = csv_module.writer(f)
        writer.writerow(
            [
                "symbol",
                "months",
                "interval",
                "atr_mult",
                "target_rr",
                "zones",
                "trades",
                "hits",
                "misses",
                "open",
                "hit_rate",
                "expectancy",
                "hc_count",
                "hc_hit_rate",
                "std_hit_rate",
                "avg_penetration_pct",
                "median_penetration_pct",
                "avg_holding_candles",
                "median_holding_candles",
                "zones_per_month",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    symbol,
                    months,
                    r.interval,
                    r.atr_mult,
                    r.target_rr,
                    r.zones,
                    r.trades,
                    r.hits,
                    r.misses,
                    r.open_trades,
                    r.hit_rate,
                    r.expectancy,
                    r.hc_count,
                    r.hc_hit_rate,
                    r.std_hit_rate,
                    r.avg_pen,
                    r.med_pen,
                    r.avg_hold,
                    r.med_hold,
                    r.zones_per_month,
                ]
            )

    print(f"  CSV exportiert: {path.resolve()}")
    print()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _fmt_pct(value) -> str:
    """Formatiert einen Dezimalwert als Prozentwert."""
    if value is None:
        return "N/A"
    try:
        d = Decimal(str(value))
        return f"{d * 100:.1f}%"
    except Exception:
        return str(value)


def _fmt_dec(value, places: int = 2) -> str:
    """Formatiert einen Dezimalwert mit fester Nachkommastellen-Anzahl."""
    if value is None:
        return "N/A"
    try:
        d = Decimal(str(value))
        return f"{d:.{places}f}"
    except Exception:
        return str(value)


def _compute_expectancy_str(metrics: dict, target_rr: float = 2.0) -> str:
    """
    Expectancy in R-Vielfachen.

    E = HR * target_rr - (1 - HR) * 1.0
    Positiv = profitabel auf lange Sicht.
    """
    hr_raw = metrics.get("hit_rate")
    if hr_raw is None:
        return "N/A"
    try:
        hr = float(str(hr_raw))
    except (ValueError, TypeError):
        return "N/A"

    exp = hr * target_rr - (1 - hr) * 1.0
    return f"{exp:+.2f}R"


def _parse_floats(s: str) -> list[float]:
    """Parst komma-separierte Floats."""
    return [float(x.strip()) for x in s.split(",")]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Orderblock Detection & Backtest CLI")

    # Mode
    parser.add_argument(
        "--mode",
        choices=["single", "sweep"],
        default="single",
        help="Modus: single (Default) oder sweep",
    )

    # Gemeinsame Parameter
    parser.add_argument(
        "--symbol", default="BTCEUR", help="Trading-Paar (Default: BTCEUR)"
    )
    parser.add_argument(
        "--months", type=int, default=6, help="Monate historische Daten (Default: 6)"
    )
    parser.add_argument(
        "--atr-length", type=int, default=20, help="ATR Laenge (Default: 20)"
    )
    parser.add_argument(
        "--zscore-threshold",
        type=float,
        default=2.0,
        help="Z-Score Threshold fuer HIGH_CONVICTION (Default: 2.0)",
    )

    parser.add_argument(
        "--max-holding",
        type=int,
        default=200,
        help="Max Holding Candles / Triple Barrier (Default: 200, 0=deaktiviert)",
    )

    # Single-Mode Parameter
    parser.add_argument("--interval", default="4h", help="Timeframe (Default: 4h)")
    parser.add_argument(
        "--atr-mult",
        type=float,
        default=2.0,
        help="ATR Multiplier fuer Displacement (Default: 2.0)",
    )
    parser.add_argument(
        "--target-rr",
        type=float,
        default=2.0,
        help="Target Risk-Reward Ratio (Default: 2.0)",
    )

    # Sweep-Mode Parameter
    parser.add_argument(
        "--sweep-intervals",
        default="1h,4h",
        help="Komma-separierte Intervals (Default: 1h,4h)",
    )
    parser.add_argument(
        "--sweep-atr-mults",
        default="1.5,2.0,2.5,3.0",
        help="Komma-separierte ATR-Multiplier (Default: 1.5,2.0,2.5,3.0)",
    )
    parser.add_argument(
        "--sweep-rrs",
        default="1.5,2.0,3.0",
        help="Komma-separierte Target-R:Rs (Default: 1.5,2.0,3.0)",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="CSV-Datei fuer Sweep-Export (optional)",
    )

    args = parser.parse_args()

    if args.mode == "sweep":
        run_sweep(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
