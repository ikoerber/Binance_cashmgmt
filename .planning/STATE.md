# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-22)

**Core value:** Binance API Interaktionen resilient und beobachtbar machen — keine stillen Sync-Fehler, automatischer Retry mit Backoff, proaktive Reconciliation mit Alerts
**Current focus:** v1.1 API Hardening — Phase 7 in progress (Proactive Reconciliation)

## Current Position

Phase: 7 of 8 (Proactive Reconciliation)
Plan: 2 of 2
Status: In progress
Last activity: 2026-02-22 — Completed 07-01 (DB models + evaluate_discrepancies domain logic)

Progress: [██████░░░░] 62% (v1.1, 5/8 plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 13 (8 v1.0 + 5 v1.1)
- Average duration: 3.5min
- Total execution time: 48min

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 05-01 | Error Classification + Enhanced Retry | 3min | 1 (TDD) | 2 |
| 05-02 | Configurable Timeout + Retryable Wrappers | 4min | 2 | 8 |
| 06-01 | Per-Fill Sync Result Tracking | 4min | 1 (TDD) | 3 |
| 06-02 | API Layer + Lot Service Sync Report Propagation | 2min | 2 | 2 |
| 07-01 | DB models + evaluate_discrepancies domain logic | 4min | 2 (TDD) | 4 |

*Updated after each plan completion*

## Accumulated Context

### Decisions

- [05-01] Keep _is_retryable() as backward-compat wrapper -- all existing @retry_on_transient_error() usages stay unchanged
- [05-01] BinanceAPIError wraps both permanent and exhausted-retry errors -- single exception type for all API failure paths
- [05-01] Retry-After used as minimum wait (max of computed backoff and header value)
- [05-02] create_order wrapper has NO retry decorator -- duplicate order risk per REQUIREMENTS.md Out of Scope
- [05-02] All read/cancel wrapper methods have @retry_on_transient_error for automatic retry with backoff
- [05-02] Consumer services never access binance_service.client.* directly -- all calls go through wrapper methods
- [06-01] FillOutcome as string constants (not Python Enum) -- trivial JSON serialization
- [06-01] fill_details in to_dict() only includes FAILED and SKIPPED_FIFO entries -- compact response
- [06-01] last_synced_source_id uses numeric max comparison (Binance trade IDs are integers)
- [06-01] SyncResult.to_dict() preserves all existing response keys -- zero API route changes needed
- [06-02] Full-sync watermark uses numeric max comparison across batches (consistent with SyncResult)
- [06-02] Fiat sync errors tracked as fill_details entries with source_id='fiat_sync' and outcome='FAILED'
- [06-02] Full-sync status set to partial_success when fills_failed > 0 without fifo_error
- [07-01] Idempotent migration pattern (_table_exists, _add_column_if_not_exists, _index_exists) for SQLite compatibility
- [07-01] Severity threshold: > tolerance = warning, > 10x tolerance = critical (strict greater-than, not >=)
- [07-01] Alert dict format: {alert_type, severity, title, details_json} for consistent AlertEventDB creation

Full v1.0 decision log archived in milestones/v1.0-phases/ SUMMARY.md files.

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-22
Stopped at: Completed 07-01-PLAN.md (DB models + evaluate_discrepancies domain logic)
Resume file: None
