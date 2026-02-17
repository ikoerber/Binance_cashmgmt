"""
Orderblock Persistence Service - DB CRUD fuer Zonen und Backtest-Runs.

Upsert-Logik fuer Zonen (Detection-Ergebnisse werden pro Run aktualisiert).
Backtest-Runs werden als immutable Snapshots persistiert.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import BacktestRunDB, OrderblockZoneDB
from app.domain.orderblock_backtest import BacktestResult
from app.services.orderblock_data_service import utc_iso

logger = logging.getLogger(__name__)


def _utcnow():
    """Naive UTC now."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def save_detection_result(
    db: Session,
    user_id: str,
    zones: list,
    symbol: str,
    interval: str,
    config_json: dict,
) -> int:
    """
    Upsert erkannter Zonen fuer einen User/Symbol/Interval.

    Bestehende Zonen werden per ID aktualisiert (State, Timestamps).
    Neue Zonen werden eingefuegt.
    Zonen die nicht mehr im Ergebnis sind werden entfernt (stale cleanup).

    Returns: Anzahl upserted Zonen.
    """
    if not zones:
        logger.warning(
            "Empty detection result for %s/%s/%s – skipping upsert and stale cleanup",
            user_id, symbol, interval,
        )
        return 0

    # Duplikat-Pruefung: Warnung wenn Detection-Engine doppelte IDs liefert
    current_ids = {zone.id for zone in zones}
    if len(current_ids) != len(zones):
        dupes = len(zones) - len(current_ids)
        logger.warning(
            "Detection returned %d duplicate zone IDs for %s/%s/%s – last-wins semantics apply",
            dupes, user_id, symbol, interval,
        )

    # Stale-Cleanup: Zonen entfernen die nicht mehr im aktuellen Ergebnis sind
    stale_query = db.query(OrderblockZoneDB).filter(
        OrderblockZoneDB.user_id == user_id,
        OrderblockZoneDB.symbol == symbol,
        OrderblockZoneDB.interval == interval,
    )
    if current_ids:
        stale_query = stale_query.filter(
            ~OrderblockZoneDB.id.in_(current_ids)
        )
    stale_count = stale_query.delete(synchronize_session="fetch")
    if stale_count:
        logger.info("Removed %d stale zones for %s/%s/%s", stale_count, user_id, symbol, interval)

    # Alle existierenden Zone-IDs in einer Abfrage laden (N+1 vermeiden)
    existing_ids = {
        row.id
        for row in db.query(OrderblockZoneDB.id).filter(
            OrderblockZoneDB.id.in_(current_ids)
        ).all()
    }
    existing_map = {}
    if existing_ids:
        existing_zones = db.query(OrderblockZoneDB).filter(
            OrderblockZoneDB.id.in_(existing_ids)
        ).all()
        existing_map = {z.id: z for z in existing_zones}

    count = 0
    for zone in zones:
        existing = existing_map.get(zone.id)

        if existing:
            existing.state = zone.state.value
            existing.mitigated_at = zone.mitigated_at
            existing.invalidated_at = zone.invalidated_at
            existing.category = zone.category.value if hasattr(zone.category, "value") else zone.category
            # Liquidity Sweep (deterministisch, aendert sich nicht bei Re-Run)
            existing.has_liquidity_sweep = zone.has_liquidity_sweep
            existing.liquidity_sweep_level = zone.liquidity_sweep_level
            # Sentiment Confluence (Snapshot aktualisiert sich bei Re-Analyse)
            existing.sentiment_at_detection = zone.sentiment_at_detection
            existing.confluence_label = zone.confluence_label
            existing.confluence_score = zone.confluence_score
            existing.updated_at = _utcnow()
        else:
            db_zone = OrderblockZoneDB(
                id=zone.id,
                user_id=user_id,
                symbol=symbol,
                interval=interval,
                direction=zone.direction.value,
                state=zone.state.value,
                conviction=zone.conviction.value,
                zone_top=zone.zone_top,
                zone_bottom=zone.zone_bottom,
                equilibrium=zone.equilibrium,
                entry_edge=zone.entry_edge,
                stop_edge=zone.stop_edge,
                formed_at=zone.formed_at,
                confirmed_at=zone.confirmed_at,
                mitigated_at=zone.mitigated_at,
                invalidated_at=zone.invalidated_at,
                volume_zscore=zone.volume_zscore,
                volume_weight=zone.volume_weight,
                volume_percentile=zone.volume_percentile,
                ofi_divergence=zone.ofi_divergence,
                impact_efficiency_ratio=zone.impact_efficiency_ratio,
                conviction_score=zone.conviction_score,
                is_high_conviction_zscore=zone.is_high_conviction_zscore,
                category=zone.category.value if hasattr(zone.category, "value") else "UNCLASSIFIED",
                has_liquidity_sweep=zone.has_liquidity_sweep,
                liquidity_sweep_level=zone.liquidity_sweep_level,
                sentiment_at_detection=zone.sentiment_at_detection,
                confluence_label=zone.confluence_label,
                confluence_score=zone.confluence_score,
                atr_at_formation=zone.atr_at_formation,
                displacement_range=zone.displacement_range,
                bos_swing_price=zone.bos_swing_price,
                config_json=config_json,
            )
            db.add(db_zone)

        count += 1

    db.flush()
    logger.info("Upserted %d zones for %s/%s/%s", count, user_id, symbol, interval)
    return count


def delete_all_zones(
    db: Session,
    user_id: str,
    symbol: str,
    interval: str,
) -> int:
    """
    Loescht alle Zonen fuer einen User/Symbol/Interval.

    Returns: Anzahl geloeschter Zonen.
    """
    count = db.query(OrderblockZoneDB).filter(
        OrderblockZoneDB.user_id == user_id,
        OrderblockZoneDB.symbol == symbol,
        OrderblockZoneDB.interval == interval,
    ).delete(synchronize_session="fetch")
    db.flush()
    return count


def get_zones(
    db: Session,
    user_id: str,
    symbol: str,
    interval: str,
    state: Optional[str] = None,
) -> List[dict]:
    """
    Zonen fuer User/Symbol/Interval laden.

    Optional nach State filtern (UNMITIGATED, MITIGATED, INVALID).
    """
    query = db.query(OrderblockZoneDB).filter(
        OrderblockZoneDB.user_id == user_id,
        OrderblockZoneDB.symbol == symbol,
        OrderblockZoneDB.interval == interval,
    )

    if state:
        query = query.filter(OrderblockZoneDB.state == state)

    query = query.order_by(OrderblockZoneDB.formed_at.desc())
    zones = query.all()

    return [_zone_db_to_dict(z) for z in zones]


def get_zone_detail(
    db: Session,
    zone_id: str,
    user_id: Optional[str] = None,
) -> Optional[dict]:
    """Einzelne Zone laden (inkl. Config). Optional nach user_id filtern (IDOR-Schutz)."""
    query = db.query(OrderblockZoneDB).filter_by(id=zone_id)
    if user_id is not None:
        query = query.filter(OrderblockZoneDB.user_id == user_id)
    zone = query.first()
    if zone is None:
        return None
    return _zone_db_to_dict(zone)


def save_backtest_result(
    db: Session,
    user_id: str,
    result: BacktestResult,
    *,
    config_json: dict,
    metrics_json: dict,
    trades_json: list,
) -> str:
    """
    Backtest-Run als immutablen Snapshot persistieren.

    Args:
        result: Domain-Objekt mit Metriken und Metadaten.
        config_json: Serialisierte Config fuer JSON-Spalte.
        metrics_json: Serialisierte Metriken fuer JSON-Spalte.
        trades_json: Serialisierte Trades fuer JSON-Spalte.

    Returns: Run-ID.
    """
    run_id = f"bt_{uuid.uuid4().hex[:12]}"
    metrics = result.metrics

    db_run = BacktestRunDB(
        id=run_id,
        user_id=user_id,
        symbol=result.symbol,
        interval=result.timeframe,
        data_start=result.data_start,
        data_end=result.data_end,
        candle_count=result.candle_count,
        total_zones=metrics.total_zones,
        total_trades=metrics.total_trades,
        hits=metrics.hits,
        misses=metrics.misses,
        hit_rate=metrics.hit_rate,
        avg_penetration_depth_pct=metrics.avg_penetration_depth_pct,
        avg_holding_duration_candles=metrics.avg_holding_duration_candles,
        high_conviction_count=metrics.high_conviction_count,
        high_conviction_hit_rate=metrics.high_conviction_hit_rate,
        expired_trades=metrics.expired_trades,
        max_holding_candles=result.config.max_holding_candles,
        config_json=config_json,
        metrics_json=metrics_json,
        trades_json=trades_json,
    )
    db.add(db_run)
    db.flush()

    logger.info("Saved backtest run %s for %s/%s", run_id, result.symbol, result.timeframe)
    return run_id


def get_backtest_runs(
    db: Session,
    user_id: str,
    symbol: Optional[str] = None,
) -> List[dict]:
    """Backtest-Runs fuer User laden (optional nach Symbol filtern)."""
    query = db.query(BacktestRunDB).filter(BacktestRunDB.user_id == user_id)

    if symbol:
        query = query.filter(BacktestRunDB.symbol == symbol)

    query = query.order_by(BacktestRunDB.created_at.desc())
    runs = query.all()

    return [_run_db_to_dict(r, include_trades=False) for r in runs]


def get_backtest_run(
    db: Session,
    run_id: str,
    user_id: Optional[str] = None,
) -> Optional[dict]:
    """Einzelnen Backtest-Run mit vollstaendigen Metriken + Trades laden. Optional nach user_id filtern (IDOR-Schutz)."""
    query = db.query(BacktestRunDB).filter_by(id=run_id)
    if user_id is not None:
        query = query.filter(BacktestRunDB.user_id == user_id)
    run = query.first()
    if run is None:
        return None
    return _run_db_to_dict(run, include_trades=True)


# ─── Serialisierung ───


def _zone_db_to_dict(z: OrderblockZoneDB) -> dict:
    """DB-Zeile → API-Dict."""
    return {
        "id": z.id,
        "user_id": z.user_id,
        "symbol": z.symbol,
        "interval": z.interval,
        "direction": (
            z.direction.value if hasattr(z.direction, "value") else z.direction
        ),
        "state": z.state.value if hasattr(z.state, "value") else z.state,
        "conviction": (
            z.conviction.value if hasattr(z.conviction, "value") else z.conviction
        ),
        "zone_top": str(z.zone_top),
        "zone_bottom": str(z.zone_bottom),
        "equilibrium": str(z.equilibrium),
        "entry_edge": str(z.entry_edge),
        "stop_edge": str(z.stop_edge),
        "formed_at": utc_iso(z.formed_at),
        "confirmed_at": utc_iso(z.confirmed_at),
        "mitigated_at": utc_iso(z.mitigated_at),
        "invalidated_at": utc_iso(z.invalidated_at),
        "volume_zscore": str(z.volume_zscore),
        "volume_weight": str(z.volume_weight),
        "volume_percentile": str(z.volume_percentile) if z.volume_percentile is not None else None,
        "ofi_divergence": str(z.ofi_divergence) if z.ofi_divergence is not None else None,
        "impact_efficiency_ratio": str(z.impact_efficiency_ratio) if z.impact_efficiency_ratio is not None else None,
        "conviction_score": str(z.conviction_score) if z.conviction_score is not None else None,
        "is_high_conviction_zscore": bool(z.is_high_conviction_zscore) if z.is_high_conviction_zscore is not None else False,
        "category": z.category or "UNCLASSIFIED",
        "has_liquidity_sweep": bool(z.has_liquidity_sweep) if z.has_liquidity_sweep is not None else False,
        "liquidity_sweep_level": str(z.liquidity_sweep_level) if z.liquidity_sweep_level is not None else None,
        "sentiment_at_detection": str(z.sentiment_at_detection) if z.sentiment_at_detection is not None else None,
        "confluence_label": z.confluence_label,
        "confluence_score": str(z.confluence_score) if z.confluence_score is not None else None,
        "atr_at_formation": str(z.atr_at_formation),
        "displacement_range": str(z.displacement_range),
        "bos_swing_price": str(z.bos_swing_price),
        "config": z.config_json,
        "created_at": utc_iso(z.created_at),
        "updated_at": utc_iso(z.updated_at),
    }


def _run_db_to_dict(r: BacktestRunDB, include_trades: bool = False) -> dict:
    """DB-Zeile → API-Dict."""
    result = {
        "id": r.id,
        "user_id": r.user_id,
        "symbol": r.symbol,
        "interval": r.interval,
        "data_start": utc_iso(r.data_start),
        "data_end": utc_iso(r.data_end),
        "candle_count": int(r.candle_count) if r.candle_count else 0,
        "total_zones": int(r.total_zones) if r.total_zones else 0,
        "total_trades": int(r.total_trades) if r.total_trades else 0,
        "hits": int(r.hits) if r.hits else 0,
        "misses": int(r.misses) if r.misses else 0,
        "hit_rate": str(r.hit_rate) if r.hit_rate is not None else None,
        "avg_penetration_depth_pct": (
            str(r.avg_penetration_depth_pct)
            if r.avg_penetration_depth_pct is not None
            else None
        ),
        "avg_holding_duration_candles": (
            str(r.avg_holding_duration_candles)
            if r.avg_holding_duration_candles is not None
            else None
        ),
        "high_conviction_count": (
            int(r.high_conviction_count) if r.high_conviction_count is not None else 0
        ),
        "high_conviction_hit_rate": (
            str(r.high_conviction_hit_rate)
            if r.high_conviction_hit_rate is not None
            else None
        ),
        "expired_trades": int(r.expired_trades) if r.expired_trades is not None else 0,
        "config": r.config_json,
        "metrics": r.metrics_json,
        "created_at": utc_iso(r.created_at),
    }

    if include_trades:
        result["trades"] = r.trades_json

    return result
