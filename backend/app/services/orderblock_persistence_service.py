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

    Returns: Anzahl upserted Zonen.
    """
    count = 0
    for zone in zones:
        existing = db.query(OrderblockZoneDB).filter_by(id=zone.id).first()

        if existing:
            existing.state = zone.state.value
            existing.mitigated_at = zone.mitigated_at
            existing.invalidated_at = zone.invalidated_at
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
                atr_at_formation=zone.atr_at_formation,
                displacement_range=zone.displacement_range,
                bos_swing_price=zone.bos_swing_price,
                config_json=config_json,
            )
            db.add(db_zone)

        count += 1

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
) -> Optional[dict]:
    """Einzelne Zone laden (inkl. Config)."""
    zone = db.query(OrderblockZoneDB).filter_by(id=zone_id).first()
    if zone is None:
        return None
    return _zone_db_to_dict(zone)


def save_backtest_result(
    db: Session,
    user_id: str,
    result_data: dict,
) -> str:
    """
    Backtest-Run als immutablen Snapshot persistieren.

    Returns: Run-ID.
    """
    run_id = f"bt_{uuid.uuid4().hex[:12]}"
    result = result_data["result"]
    metrics = result.metrics

    db_run = BacktestRunDB(
        id=run_id,
        user_id=user_id,
        symbol=result_data["meta"]["symbol"],
        interval=result_data["meta"]["interval"],
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
        config_json=result_data["config"],
        metrics_json=result_data["metrics"],
        trades_json=result_data["trades"],
    )
    db.add(db_run)
    db.flush()

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
) -> Optional[dict]:
    """Einzelnen Backtest-Run mit vollstaendigen Metriken + Trades laden."""
    run = db.query(BacktestRunDB).filter_by(id=run_id).first()
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
        "formed_at": z.formed_at.isoformat() if z.formed_at else None,
        "confirmed_at": z.confirmed_at.isoformat() if z.confirmed_at else None,
        "mitigated_at": z.mitigated_at.isoformat() if z.mitigated_at else None,
        "invalidated_at": z.invalidated_at.isoformat() if z.invalidated_at else None,
        "volume_zscore": str(z.volume_zscore),
        "volume_weight": str(z.volume_weight),
        "volume_percentile": str(z.volume_percentile) if z.volume_percentile is not None else None,
        "ofi_divergence": str(z.ofi_divergence) if z.ofi_divergence is not None else None,
        "impact_efficiency_ratio": str(z.impact_efficiency_ratio) if z.impact_efficiency_ratio is not None else None,
        "conviction_score": str(z.conviction_score) if z.conviction_score is not None else None,
        "is_high_conviction_zscore": bool(z.is_high_conviction_zscore) if z.is_high_conviction_zscore is not None else False,
        "atr_at_formation": str(z.atr_at_formation),
        "displacement_range": str(z.displacement_range),
        "bos_swing_price": str(z.bos_swing_price),
        "config": z.config_json,
        "created_at": z.created_at.isoformat() if z.created_at else None,
        "updated_at": z.updated_at.isoformat() if z.updated_at else None,
    }


def _run_db_to_dict(r: BacktestRunDB, include_trades: bool = False) -> dict:
    """DB-Zeile → API-Dict."""
    result = {
        "id": r.id,
        "user_id": r.user_id,
        "symbol": r.symbol,
        "interval": r.interval,
        "data_start": r.data_start.isoformat() if r.data_start else None,
        "data_end": r.data_end.isoformat() if r.data_end else None,
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
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

    if include_trades:
        result["trades"] = r.trades_json

    return result
