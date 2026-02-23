---
phase: 05-api-resilience
plan: 01
subsystem: api
tags: [retry, error-classification, backoff, rate-limit, binance-api, resilience]

# Dependency graph
requires:
  - phase: 04-sell-routing
    provides: Stable codebase with existing retry decorator in backend/app/utils/retry.py
provides:
  - ErrorClassification dataclass for structured error categorization (transient vs permanent)
  - BinanceAPIError exception wrapper with classification metadata and attempt count
  - classify_error() function with full Binance API error taxonomy
  - Retry-After header support for 429 rate-limit responses
  - Enhanced retry decorator with error classification and structured error propagation
affects: [05-api-resilience, 06-sync-reliability, binance-service]

# Tech tracking
tech-stack:
  added: []
  patterns: [error-classification, structured-exceptions, retry-after-header]

key-files:
  created:
    - backend/tests/test_retry.py
  modified:
    - backend/app/utils/retry.py

key-decisions:
  - "Keep _is_retryable() as backward-compat wrapper instead of removing it — all existing @retry_on_transient_error() usages stay unchanged"
  - "BinanceAPIError wraps both permanent and exhausted-retry errors — single exception type for all API failure paths"
  - "Retry-After used as minimum wait (max of computed backoff and header value) — never shorter than server requests"

patterns-established:
  - "Error Classification: classify_error() returns ErrorClassification dataclass with is_transient, category, status_code, retry_after"
  - "Structured Exceptions: BinanceAPIError carries original_exception + classification + attempts for caller inspection"
  - "Retry-After Respect: 429 responses with Retry-After header use header value as minimum delay"

requirements-completed: [API-01, API-03]

# Metrics
duration: 3min
completed: 2026-02-22
---

# Phase 5 Plan 1: Structured Error Classification + Enhanced Retry Summary

**Enhanced retry utility with 6-category error classification (rate_limit, server_error, timeout, connection_error, client_error, unknown), Retry-After header support for 429 responses, and BinanceAPIError structured exception -- 37 TDD tests, full backward compatibility**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-22T20:17:26Z
- **Completed:** 2026-02-22T20:20:36Z
- **Tasks:** 1 feature (TDD: RED -> GREEN, no REFACTOR needed)
- **Files modified:** 2

## Accomplishments
- ErrorClassification dataclass with 6 categories classifying all Binance API error types
- BinanceAPIError structured exception carrying original exception, classification metadata, and attempt count
- classify_error() pure function handling BinanceAPIException, requests.Timeout, requests.ConnectionError, requests.HTTPError, and unknown exceptions
- Retry-After header extraction and respect (used as minimum wait time for 429 responses)
- Enhanced retry decorator: permanent errors propagate immediately as BinanceAPIError, transient errors retry with backoff
- Full backward compatibility -- _is_retryable() preserved, decorator signature unchanged, all 670 existing tests pass

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests for error classification** - `c60e3f8` (test)
2. **TDD GREEN: Implement error classification and enhanced retry** - `ffcd661` (feat)

_No REFACTOR commit needed -- code was clean after GREEN._

## Files Created/Modified
- `backend/app/utils/retry.py` - Enhanced with ErrorClassification, BinanceAPIError, classify_error(), Retry-After support (309 lines)
- `backend/tests/test_retry.py` - 37 test cases in 5 test classes covering all classification rules, decorator behaviors, and edge cases (490 lines)

## Decisions Made
- Kept `_is_retryable()` as backward-compatibility wrapper for `classify_error().is_transient` instead of removing it -- ensures all existing `@retry_on_transient_error()` usages in binance.py work without changes
- `BinanceAPIError` wraps both permanent and retry-exhausted errors -- callers get a single exception type for all API failures
- Retry-After used as minimum wait (`max(computed_backoff, retry_after)`) -- never waits shorter than the server requests
- `_extract_retry_after()` handles missing response, missing headers, and unparseable values gracefully (returns None)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Error classification foundation ready for Plan 05-02 (configurable timeout + consolidated retryable wrappers)
- `BinanceAPIError` and `classify_error()` available for import by any module needing structured error handling
- All existing Binance service methods continue to work unchanged via backward-compatible decorator

## Self-Check: PASSED

- FOUND: backend/app/utils/retry.py
- FOUND: backend/tests/test_retry.py
- FOUND: .planning/phases/05-api-resilience/05-01-SUMMARY.md
- FOUND: c60e3f8 (RED commit)
- FOUND: ffcd661 (GREEN commit)

---
*Phase: 05-api-resilience*
*Completed: 2026-02-22*
