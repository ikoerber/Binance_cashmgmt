---
phase: 17-combined-score-integration
plan: 01
subsystem: api, domain
tags: [combined-score, alpha-score, decimal, backward-compatibility, tdd]

# Dependency graph
requires:
  - phase: 14-multi-factor-scoring
    provides: "AlphaScoreDataService singleton, Alpha Score domain with AlphaScoreResult"
  - phase: 16-dry-run-bot-dashboard
    provides: "Bot Dashboard consuming Alpha Score, validation through dry-run"
provides:
  - "AlphaInput dataclass in combined_score.py"
  - "Three-signal weighting (50/30/20) with 60/40 fallback"
  - "_normalize_alpha function (-5..+5 to -1..+1)"
  - "Extended conflict detection (alpha-vs-macro divergence)"
  - "Extended quality assessment (three-signal coverage)"
  - "API response includes alpha key (null or object)"
  - "Combined route loads user settings from DB"
affects: [combined-score-frontend, combined-score-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional third signal with fallback weights pattern"
    - "Graceful degradation: settings=None means no alpha fetch"

key-files:
  created: []
  modified:
    - backend/app/domain/combined_score.py
    - backend/app/services/combined_score_service.py
    - backend/app/api/routes/combined.py
    - backend/tests/test_combined_score.py

key-decisions:
  - "Fixed 50/30/20 weights (Macro/Sentiment/Alpha) rather than user-configurable"
  - "Alpha quality 'warmup' or 'unavailable' triggers exact 60/40 fallback"
  - "Conflict detection extended with alpha-vs-macro check, not full three-way"

patterns-established:
  - "Optional signal integration: add optional param with None default, branch on quality"
  - "Weight constants: separate _3 suffixed constants for three-signal case"

requirements-completed: [COMB-01]

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 17 Plan 01: Combined Score Alpha Integration Summary

**AlphaInput dataclass with three-signal weighting (50/30/20) and backward-compatible 60/40 fallback, TDD-driven with 17 new tests**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T17:07:27Z
- **Completed:** 2026-02-27T17:12:27Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 4

## Accomplishments
- AlphaInput dataclass and _normalize_alpha function for Alpha Score normalization
- Three-signal Combined Score: 50% Macro + 30% Sentiment + 20% Alpha when Alpha available
- Full backward compatibility: 60/40 weights preserved when Alpha is None/warmup/unavailable
- Service layer gracefully fetches Alpha Score with try/except fallback
- API route loads user settings from DB (Depends(get_db)) for Alpha Score computation
- Extended conflict detection with alpha-vs-macro divergence check
- Extended quality assessment with three-signal coverage thresholds
- 17 new tests covering normalization, weighting, fallback, quality, and conflict

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests** - `7b69db7` (test)
2. **TDD GREEN: Implementation** - `7340bbd` (feat)

## Files Created/Modified
- `backend/app/domain/combined_score.py` - AlphaInput dataclass, DIRECTION_WEIGHT_3/SIZING_WEIGHT_3/ALPHA_WEIGHT_3 constants, _normalize_alpha, extended compute_combined_score/detect_conflict/assess_quality
- `backend/app/services/combined_score_service.py` - Alpha Score fetching via AlphaScoreDataService, extended get_combined_score with user_id/settings params, _serialize with alpha key
- `backend/app/api/routes/combined.py` - Added Depends(get_db), _get_user_settings helper, passes user_id + settings to service
- `backend/tests/test_combined_score.py` - 17 new tests: TestNormalizeAlpha (6), TestAlphaScoreIntegration (7), TestAlphaQuality (2), TestAlphaConflict (2)

## Decisions Made
- Used fixed 50/30/20 weights (Macro/Sentiment/Alpha) rather than user-configurable weights. STATE.md noted "Existing Combined Score is user-calibrated", so a one-constant change is safer than adding Settings UI.
- Alpha quality "warmup" or "unavailable" triggers exact 60/40 fallback -- the same code path as alpha=None.
- Conflict detection extended with alpha-vs-macro divergence check only (not full three-way), keeping the existing macro-vs-sentiment logic intact.
- API route uses same _get_user_settings pattern as alpha_score.py route for consistency.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- COMB-01 complete: Alpha Score integrated into Combined Score domain, service, and API
- Ready for 17-02 (COMB-02): Frontend Combined Score dashboard with Alpha Score sub-signal card
- API response now includes "alpha" key for frontend consumption

## Self-Check: PASSED

All files exist. All commits verified (7b69db7, 7340bbd).

---
*Phase: 17-combined-score-integration*
*Completed: 2026-02-27*
