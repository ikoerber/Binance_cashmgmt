# Phase 17: Combined Score Integration - Research

**Researched:** 2026-02-27
**Domain:** Signal aggregation / backward-compatible weight redistribution
**Confidence:** HIGH

## Summary

Phase 17 integrates the Alpha Score (built in Phase 14, validated through backtesting in Phase 15 and dry-run in Phase 16) into the existing Combined Score as an optional third signal. The Combined Score currently combines MacroSignal (60% weight, direction) and Sentiment (40% weight, sizing) into a Unified Score (-100 to +100). The Alpha Score (-5 to +5) must become a third input that enriches the Combined Score when available, while preserving exact existing behavior when unavailable.

The implementation is entirely within the existing codebase's established patterns. No new libraries are required. The core challenge is designing a backward-compatible weight redistribution scheme in the pure domain layer (`combined_score.py`) and wiring the Alpha Score data through the service layer (`combined_score_service.py`) and API route. The frontend (`CombinedScore.jsx`) needs a third sub-signal card with Alpha Score factor breakdown.

**Primary recommendation:** Add an optional `AlphaInput` dataclass to `combined_score.py`, extend `compute_combined_score()` with backward-compatible three-signal weighting (e.g., 50/30/20 when Alpha available, 60/40 when not), and propagate through service/API/frontend layers following established patterns exactly.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMB-01 | Alpha Score feeds into Combined Score as optional 3rd signal (backward-compatible: when unavailable, existing 60/40 weights unchanged) | Domain layer pattern: optional `AlphaInput` parameter with `None` default in `compute_combined_score()`. When `None`, use current `DIRECTION_WEIGHT=0.60` / `SIZING_WEIGHT=0.40`. When present, redistribute to three-way weights. Service layer: fetch Alpha Score via `get_alpha_score_data_service()`, handle warmup/unavailable → pass `None`. No DB migration needed (no new settings columns). |
| COMB-02 | Combined Score dashboard shows Alpha Score contribution when available (factor breakdown in details) | Frontend pattern: third sub-signal card alongside existing Macro and Sentiment cards, with collapsible factor detail rows (reuse existing `combined-factor-bar-track` CSS pattern from Macro detail). New `alpha_detail` key in API response with factor breakdown array. Conditional rendering: hide card entirely when `alpha` key is absent or `alpha.status === "warmup"`. |
</phase_requirements>

## Standard Stack

### Core

No new dependencies. All implementation uses existing libraries already in the project.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python Decimal | stdlib | All score computations | Project invariant: Decimal for all money/price/score calculations |
| dataclasses | stdlib | AlphaInput, extended CombinedScoreResult | Matches DirectionInput, SizingInput pattern |
| FastAPI | existing | API route (no changes to combined route signature needed) | Already used |
| React + TanStack Query | existing | Frontend sub-signal card | Already used for CombinedScore.jsx |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | existing | Tests for extended domain logic | Extend test_combined_score.py |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Fixed three-way weights (50/30/20) | User-configurable combined weights via Settings | Adds complexity, Settings schema change, risk of miscalibration. Fixed weights are simpler and match the project's "Existing Combined Score is user-calibrated" constraint from STATE.md. Configurable weights can be a follow-up. |
| Fetching Alpha Score in combined route | Passing Alpha Score from frontend (already fetched for Bot Dashboard) | Would break server-side computation purity. Service layer should orchestrate all data fetching. |

## Architecture Patterns

### Recommended Changes

```
backend/app/domain/combined_score.py    # Add AlphaInput, extend compute_combined_score
backend/app/services/combined_score_service.py  # Fetch Alpha Score, build AlphaInput
backend/app/api/routes/combined.py      # Pass user_id + settings (needs DB dep)
backend/tests/test_combined_score.py    # Extend with Alpha Score integration tests
frontend/src/components/CombinedScore.jsx  # Third sub-signal card
frontend/src/components/CombinedScore.css  # Styling for Alpha card
```

### Pattern 1: Optional Third Signal with Fallback Weights

**What:** The `compute_combined_score()` function gains an optional `alpha: Optional[AlphaInput] = None` parameter. When `None`, the function uses existing 60/40 weights unchanged. When provided, weights redistribute.

**When to use:** Always -- this is the core pattern for COMB-01.

**Example:**
```python
# Domain layer (pure, no I/O)
@dataclass
class AlphaInput:
    """Optional Alpha Score input for Combined Scoring."""
    score: Decimal          # -5 to +5
    trade_signal: str       # "LONG" | "SHORT" | "NEUTRAL"
    quality: str            # "full" | "partial" | "degraded" | "warmup"
    active_factors: int
    total_factors: int
    threshold: Decimal

# Weight scheme when Alpha available
DIRECTION_WEIGHT_3 = Decimal("0.50")   # was 0.60
SIZING_WEIGHT_3 = Decimal("0.30")      # was 0.40
ALPHA_WEIGHT_3 = Decimal("0.20")       # new

def compute_combined_score(
    direction: DirectionInput,
    sizing: SizingInput,
    alpha: Optional[AlphaInput] = None,   # NEW, backward-compatible
) -> CombinedScoreResult:
    if alpha is None or alpha.quality in ("warmup", "unavailable"):
        # Exact existing behavior: 60/40
        dir_w = DIRECTION_WEIGHT   # 0.60
        siz_w = SIZING_WEIGHT     # 0.40
        alp_w = Decimal("0")
        alpha_normalized = Decimal("0")
    else:
        dir_w = DIRECTION_WEIGHT_3  # 0.50
        siz_w = SIZING_WEIGHT_3    # 0.30
        alp_w = ALPHA_WEIGHT_3     # 0.20
        alpha_normalized = _normalize_alpha(alpha.score)  # -5..+5 → -1..+1

    unified_raw = (
        direction_normalized * dir_w
        + sentiment_direction * siz_w
        + alpha_normalized * alp_w
    )
    # ... rest of computation follows existing pattern
```

### Pattern 2: Service Layer Alpha Score Fetching

**What:** `CombinedScoreService.get_combined_score()` fetches the Alpha Score from `AlphaScoreDataService` and constructs `AlphaInput`. Handles warmup, unavailable, and timeout gracefully.

**When to use:** In the service orchestration layer.

**Example:**
```python
# Service layer
def get_combined_score(self, interval_minutes, symbol, user_id, settings):
    # ... existing macro + sentiment fetching ...

    # 3. Alpha Score (optional, graceful degradation)
    alpha_input = None
    try:
        alpha_service = get_alpha_score_data_service()
        alpha_data = alpha_service.get_alpha_score(user_id=user_id, settings=settings)
        if alpha_data.get("status") == "ok":
            alpha_input = AlphaInput(
                score=Decimal(alpha_data["score"]),
                trade_signal=alpha_data["trade_signal"],
                quality=alpha_data["quality"],
                active_factors=alpha_data["active_factors"],
                total_factors=alpha_data["total_factors"],
                threshold=Decimal(alpha_data["threshold"]),
            )
    except Exception:
        logger.warning("Alpha Score fuer Combined Score nicht verfuegbar")
        # alpha_input remains None → fallback to 60/40

    result = compute_combined_score(direction, sizing, alpha=alpha_input)
```

### Pattern 3: Frontend Conditional Sub-Signal Card

**What:** The frontend renders a third Alpha Score card when `data.alpha` is present and has status "ok". Otherwise, the layout remains unchanged (two cards: Macro + Sentiment).

**When to use:** In CombinedScore.jsx rendering.

**Example:**
```jsx
{/* Alpha Score Card (only when available) */}
{data.alpha && data.alpha.status !== 'warmup' && (
  <div className="combined-subsignal-card">
    <div className="combined-subsignal-header">
      <h3>Alpha Score</h3>
      <span className="combined-weight-badge">{formatNumber(data.alpha.weight * 100, 0)}%</span>
    </div>
    {/* Factor breakdown using existing combined-factor-bar-track pattern */}
  </div>
)}
```

### Anti-Patterns to Avoid

- **Modifying existing weight constants:** Never change `DIRECTION_WEIGHT = 0.60` or `SIZING_WEIGHT = 0.40`. These are the fallback values. Add new constants for the three-signal case.
- **Breaking the pure domain function signature:** The `alpha` parameter MUST be optional with `None` default. Callers that don't pass it must get identical results to current behavior.
- **Fetching Alpha Score in the API route:** Keep data fetching in the service layer. The route should remain thin.
- **Using float for Alpha Score normalization:** All score computations must use Decimal. The Alpha Score domain already returns Decimal values.
- **Adding user-configurable combined weights in this phase:** STATE.md says "Existing Combined Score is user-calibrated." Adding weight configuration is a separate concern. Use fixed three-way weights.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Alpha Score computation | Custom Alpha Score logic in combined_score.py | `AlphaScoreDataService.get_alpha_score()` via service layer | Alpha Score already fully implemented in Phase 14 with 4 factors, regime detection, graceful degradation |
| Score normalization (-5..+5 to -1..+1) | Complex mapping function | Simple linear: `score / Decimal("5")` clamped to [-1, +1] | Alpha Score range is fixed at [-5, +5], same as sub-scores |
| Quality assessment with 3 signals | New quality logic from scratch | Extend existing `_assess_quality()` to accept optional alpha quality | Existing function already handles partial data for 2 signals |
| Conflict detection with 3 signals | Separate 3-way conflict system | Extend existing `_detect_conflict()` to optionally check alpha direction | Alpha direction aligns with macro direction (both directional), so the existing macro-vs-sentiment conflict logic naturally extends |

**Key insight:** The Alpha Score is already fully built and tested. This phase only integrates its output into the Combined Score -- no new scoring logic is needed, only weight redistribution and UI display.

## Common Pitfalls

### Pitfall 1: Breaking Backward Compatibility

**What goes wrong:** Changing `compute_combined_score()` in a way that produces different results when Alpha Score is not available (warmup, data gap, dry-run not active).
**Why it happens:** Accidentally using three-way weights even when Alpha is `None`, or changing confidence computation path.
**How to avoid:** Add a test that calls `compute_combined_score(direction, sizing)` (no alpha param) and asserts it produces the exact same result as the current implementation. Run existing test_combined_score.py unchanged -- all tests must pass.
**Warning signs:** Any existing test in `test_combined_score.py` fails after the change.

### Pitfall 2: Alpha Score Range Mismatch

**What goes wrong:** Alpha Score is -5 to +5, MacroSignal raw is -8 to +8, Sentiment is 0-100. Normalizing to the same -1..+1 range incorrectly would bias the Combined Score.
**Why it happens:** Using different normalization scales or forgetting that Alpha Score is already directional (positive = buy, negative = sell) while Sentiment is contrarian (low score = buy).
**How to avoid:** Alpha Score normalization is straightforward: `alpha_normalized = score / 5`, clamped to [-1, +1]. It is already directional (positive = LONG/buy, negative = SHORT/sell), same polarity as MacroSignal. No contrarian inversion needed.
**Warning signs:** Combined Score moves in the wrong direction when Alpha Score is strong.

### Pitfall 3: Service Layer Timeout Cascade

**What goes wrong:** Adding Alpha Score fetch to `get_combined_score()` increases total latency. If Alpha Score fetch takes too long, it blocks the Combined Score response.
**Why it happens:** `AlphaScoreDataService.get_alpha_score()` fetches from multiple sources (Binance klines, OKX funding, orderbook depth).
**How to avoid:** Wrap Alpha Score fetch in a try/except with a short timeout (e.g., 10s). If it fails or times out, `alpha_input = None` and fallback to 60/40 weights. The combined route already has a 30s overall timeout.
**Warning signs:** Combined Score endpoint becomes noticeably slower or times out more frequently.

### Pitfall 4: Combined API Route Needs DB Access for Settings

**What goes wrong:** The combined route currently doesn't take a DB dependency or load user settings. But `AlphaScoreDataService.get_alpha_score()` requires a `settings` dict.
**Why it happens:** Current combined route only needs `interval` and `symbol` (passed as query params). Alpha Score needs the full settings dict (weights, windows, thresholds).
**How to avoid:** Add `db: Session = Depends(get_db)` to the combined route, load user settings (following the pattern from `alpha_score.py` route's `_get_user_settings()`). Pass `user_id` and `settings` to the service method.
**Warning signs:** Alpha Score always returns defaults instead of user-configured values.

### Pitfall 5: Frontend CSS Grid with 3 Cards

**What goes wrong:** The existing `.combined-subsignals` layout is designed for 2 cards. Adding a third card may break the grid.
**Why it happens:** Current CSS likely uses `grid-template-columns: 1fr 1fr` or `repeat(2, 1fr)`.
**How to avoid:** When Alpha is available, switch to 3-column grid or use `repeat(auto-fit, minmax(300px, 1fr))` for responsive layout. When Alpha is not available, the layout must remain unchanged (2 cards).
**Warning signs:** Cards overflow or become too narrow on standard screen widths.

## Code Examples

### Alpha Score Normalization (Domain Layer)

```python
# Source: Existing pattern from _normalize_direction in combined_score.py
ALPHA_SCORE_MAX = Decimal("5")

def _normalize_alpha(alpha_score: Decimal) -> Decimal:
    """
    Normalizes Alpha Score (-5..+5) to direction (-1.0..+1.0).

    Alpha Score is already directional (positive = buy, negative = sell),
    same polarity as MacroSignal. No contrarian inversion needed.
    """
    normalized = alpha_score / ALPHA_SCORE_MAX
    return max(Decimal("-1"), min(Decimal("1"), normalized))
```

### Extended Quality Assessment

```python
# Source: Existing _assess_quality pattern in combined_score.py
def _assess_quality(
    direction: DirectionInput,
    sizing: SizingInput,
    alpha: Optional[AlphaInput] = None,
) -> tuple:
    dir_ratio = direction.active_factors / max(1, direction.total_factors)
    siz_ratio = sizing.active_pillars / max(1, sizing.total_pillars)

    if alpha is not None and alpha.quality not in ("warmup", "unavailable"):
        alpha_ratio = alpha.active_factors / max(1, alpha.total_factors)
        # Full: all three have good coverage
        if dir_ratio >= 0.75 and siz_ratio >= 0.6 and alpha_ratio >= 0.5:
            return "full", None
        # ... partial/degraded logic with alpha factored in
    else:
        # Existing 2-signal quality logic unchanged
        if dir_ratio >= 0.75 and siz_ratio >= 0.6:
            return "full", None
        # ...
```

### Service Layer Integration

```python
# Source: Existing CombinedScoreService pattern
# The service method gains user_id and settings parameters
def get_combined_score(
    self,
    interval_minutes: int = 15,
    symbol: str = "BTCEUR",
    user_id: str = "",
    settings: Optional[dict] = None,
) -> dict:
    # ... existing macro + sentiment fetching unchanged ...

    # NEW: Alpha Score (optional)
    alpha_input = None
    if settings is not None:
        try:
            alpha_service = get_alpha_score_data_service()
            alpha_data = alpha_service.get_alpha_score(
                user_id=user_id, settings=settings
            )
            if alpha_data.get("status") == "ok":
                alpha_input = AlphaInput(
                    score=Decimal(alpha_data["score"]),
                    trade_signal=alpha_data["trade_signal"],
                    quality=alpha_data["quality"],
                    active_factors=alpha_data["active_factors"],
                    total_factors=alpha_data["total_factors"],
                    threshold=Decimal(alpha_data["threshold"]),
                )
        except Exception:
            logger.warning("Alpha Score nicht verfuegbar fuer Combined Score")

    result = compute_combined_score(direction, sizing, alpha=alpha_input)
    return self._serialize(result, macro_result, sentiment_data, alpha_input)
```

### API Response Extension

```python
# Source: Existing _serialize pattern in combined_score_service.py
# Add alpha_detail to response (only when alpha was available)
def _serialize(self, result, macro_result, sentiment_data, alpha_input=None):
    base = {
        # ... existing fields unchanged ...
        "alpha": None,  # Always present key, null when unavailable
    }

    if alpha_input is not None and alpha_input.quality not in ("warmup", "unavailable"):
        base["alpha"] = {
            "score": str(alpha_input.score),
            "trade_signal": alpha_input.trade_signal,
            "quality": alpha_input.quality,
            "active_factors": alpha_input.active_factors,
            "total_factors": alpha_input.total_factors,
            "weight": float(result.alpha_weight),
            "status": "ok",
        }
        # Include factor detail from alpha_data if available
        if hasattr(result, 'alpha_detail') and result.alpha_detail:
            base["alpha"]["factors"] = result.alpha_detail

    return base
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 2-signal Combined (60/40) | 3-signal Combined (50/30/20) when Alpha available | Phase 17 (this phase) | Enriches Combined Score with quantitative alpha signal without breaking existing calibration |
| MacroSignal + Sentiment only | MacroSignal + Sentiment + Alpha Score | Phase 17 | Combined Score gains asset-specific quantitative signal (Z-Score, Lead-Lag, Orderbook, Funding) |

**Important context from STATE.md:** "Existing Combined Score is user-calibrated -- Alpha Score integration must be last phase." This confirms the backward-compatibility requirement is paramount.

## Open Questions

1. **Exact three-way weight distribution (50/30/20 vs other splits)**
   - What we know: Current weights are 60% Macro (direction) + 40% Sentiment (sizing). Alpha Score is a directional signal like Macro but asset-specific.
   - What's unclear: Whether 50/30/20 (Macro/Sentiment/Alpha) is optimal, or whether a different split like 45/30/25 would better reflect Alpha's directional nature.
   - Recommendation: Use 50/30/20 as starting point. This preserves Macro as the largest contributor while giving Alpha meaningful but not dominant influence. The exact values can be tuned based on dry-run validation. Since this is a fixed split (not user-configurable in this phase), changing it later is a one-line domain constant change.

2. **Should Alpha Score factor details be fetched separately or included in combined response?**
   - What we know: The Alpha Score API (`/api/alpha-score/{user_id}/score`) already returns full factor breakdown. The Bot Dashboard already displays this.
   - What's unclear: Whether to duplicate factor data in the combined response or have the frontend fetch it separately.
   - Recommendation: Include factor summary in the combined response for consistency (all sub-signal details are inline in the current response). The data is already computed as a side effect of `get_alpha_score()`. Avoids an extra API call from the frontend.

3. **Conflict detection with three signals**
   - What we know: Current conflict detection checks Macro vs Sentiment direction. Alpha Score adds a third directional input.
   - What's unclear: Whether three-way conflicts need special handling (e.g., Macro bullish, Sentiment bearish, Alpha neutral).
   - Recommendation: Keep the existing Macro-vs-Sentiment conflict detection. Add a secondary check for Alpha-vs-Macro divergence only when both are strong (above threshold). Simple extension, not a rewrite.

## Sources

### Primary (HIGH confidence)
- `/Users/ikoerber/AIProjects/cashmgnt/backend/app/domain/combined_score.py` - Current Combined Score domain logic (pure, tested)
- `/Users/ikoerber/AIProjects/cashmgnt/backend/app/domain/alpha_score.py` - Alpha Score domain with AlphaScoreResult dataclass
- `/Users/ikoerber/AIProjects/cashmgnt/backend/app/services/combined_score_service.py` - Current service orchestration pattern
- `/Users/ikoerber/AIProjects/cashmgnt/backend/app/services/alpha_score_data_service.py` - Alpha Score data fetching + serialization
- `/Users/ikoerber/AIProjects/cashmgnt/backend/tests/test_combined_score.py` - 30+ existing tests to preserve
- `/Users/ikoerber/AIProjects/cashmgnt/frontend/src/components/CombinedScore.jsx` - Frontend rendering pattern
- `/Users/ikoerber/AIProjects/cashmgnt/.planning/STATE.md` - "Existing Combined Score is user-calibrated" constraint

### Secondary (MEDIUM confidence)
- `/Users/ikoerber/AIProjects/cashmgnt/backend/app/services/dry_run_service.py` - Reference for how Alpha Score is consumed by other services

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies, all within existing patterns
- Architecture: HIGH - Direct extension of existing Combined Score with well-understood Alpha Score input
- Pitfalls: HIGH - All pitfalls are based on concrete code analysis of current implementation

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable domain, no external dependency changes expected)
