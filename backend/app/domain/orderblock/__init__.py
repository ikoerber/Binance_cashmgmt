"""
Orderblock Detection Engine – Package.

Re-exportiert alle public Symbols fuer Backward-Kompatibilitaet.
Bestehende ``from app.domain.orderblock import X`` Statements
funktionieren ohne Aenderung.
"""

# Models & Enums
from app.domain.orderblock.models import (  # noqa: F401
    Candle,
    ConfluenceLabel,
    ConvictionLevel,
    EntryPolicy,
    FairValueGap,
    InducementLevel,
    MitigationPolicy,
    OBCategory,
    OBConfig,
    OBDirection,
    OBState,
    Orderblock,
    SentimentConfluence,
    StopPolicy,
    SwingPoint,
)

# Scoring
from app.domain.orderblock.scoring import (  # noqa: F401
    _approx_tanh,
    _body_ratio,
    _clamp,
    _compute_clv_ofi,
    _decimal_sqrt,
    compute_atr,
    compute_conviction_score,
    compute_impact_efficiency_ratio,
    compute_ofi_divergence,
    compute_volume_percentile,
    compute_volume_weight,
    compute_volume_zscore,
    conviction_level_from_score,
)

# Detection
from app.domain.orderblock.detection import (  # noqa: F401
    _is_inside_bar,
    _try_validate_ob,
    detect_liquidity_sweep,
    detect_orderblocks,
    find_fvgs,
    find_swing_points,
    update_zone_states,
)

# Classification
from app.domain.orderblock.classification import (  # noqa: F401
    classify_orderblocks,
    find_inducement_levels,
)

# Confluence
from app.domain.orderblock.confluence import (  # noqa: F401
    annotate_zones_with_confluence,
    compute_sentiment_confluence,
)

# Parsing
from app.domain.orderblock.parsing import parse_binance_kline  # noqa: F401
