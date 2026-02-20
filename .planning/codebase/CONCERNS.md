# Concerns

## Technical Debt

### TD-1: No Frontend Tests
- **Severity:** MEDIUM
- **Location:** `frontend/src/`
- **Issue:** Zero automated frontend tests. 30 component files with complex logic (pairing lifecycle, lot filtering, orderblock charts) have no test coverage.
- **Risk:** Regressions in critical UI flows go undetected. Recent multi-symbol refactoring changed field names (`_eur` → `_quote`) across components without automated verification.
- **Mitigation:** Planned Vitest setup. Priority targets: formatters, useLotsData hook, pairing lifecycle.

### TD-2: No API Route Tests
- **Severity:** LOW-MEDIUM
- **Location:** `backend/app/api/routes/`
- **Issue:** 15 route modules with no direct HTTP-level tests (no FastAPI TestClient usage). Routes are indirectly tested via service-level tests.
- **Risk:** Input validation, error sanitization, and auth checks not directly verified.

### TD-3: SQLite in Production
- **Severity:** LOW
- **Location:** `backend/app/db/database.py`
- **Issue:** SQLite used for production (single-user app). `check_same_thread=False` required. Alembic needs `render_as_batch=True` for migrations.
- **Risk:** No concurrent write support. Acceptable for single-user, but limits scaling.

### TD-4: Hardcoded User ID
- **Severity:** LOW
- **Location:** `frontend/src/App.jsx:69`
- **Issue:** `userId="user_123"` hardcoded in `WebSocketProvider` and `UserProvider`. Single-user assumption baked into frontend.
- **Risk:** Multi-user support would require auth flow + dynamic user resolution.

### TD-5: Large Frontend Bundle
- **Severity:** LOW
- **Location:** `frontend/`
- **Issue:** Single chunk at 949 KB (gzipped: 289 KB). Vite warns about chunk size >500 KB.
- **Risk:** Slower initial load. lightweight-charts and Recharts contribute significantly.
- **Mitigation:** Code splitting via dynamic imports for Orderblock (chart-heavy) and CombinedScore pages.

## Security Considerations

### SEC-1: API Key in Header (No Session/JWT)
- **Location:** `backend/app/api/auth.py`
- **Current:** Static API key via `X-API-Key` header, configured in `.env`
- **Risk:** Key transmitted with every request. No expiry, rotation, or per-user scoping.
- **Acceptable for:** Single-user self-hosted app. Would need proper auth for multi-user.

### SEC-2: Error Message Sanitization
- **Status:** IMPLEMENTED
- **Location:** All route modules
- **Pattern:** Generic `"Interner Serverfehler"` to client, `logger.exception()` server-side
- **No stacktraces leak to client.**

### SEC-3: Binance API Key Storage
- **Location:** `backend/.env`
- **Status:** `.env` in `.gitignore`, test keys separated via `TEST_BINANCE_API_KEY`
- **Risk:** Keys in plaintext on disk. No secret manager integration.

### SEC-4: Row-Level Locking for Race Conditions
- **Status:** IMPLEMENTED
- **Location:** `backend/app/services/pairing_service.py`
- **Pattern:** `with_for_update()` on lot queries during pairing create/lock
- **Prevents:** Double allocation of same lot to multiple pairings

## Performance Considerations

### PERF-1: Ledger Full-Scan on Every Portfolio Query
- **Location:** `backend/app/services/portfolio_service.py`
- **Issue:** Every portfolio query loads ALL ledger events for the user (filtered by symbol + NULL), then computes from scratch.
- **Impact:** O(n) per query where n = total events. Currently acceptable for hundreds of events.
- **Mitigation needed at:** ~10K+ events. Options: materialized portfolio state, event sourcing snapshots.

### PERF-2: Sentiment Service Initialization
- **Location:** `backend/app/services/sentiment_data_service.py`
- **Issue:** First-time initialization loads 300 days of kline history. Handled at startup via lifespan.
- **Status:** Mitigated (async init in `main.py` lifespan). TTL cache prevents repeated fetches.

### PERF-3: Orderblock Detection Computation
- **Location:** `backend/app/services/orderblock_data_service.py`
- **Issue:** 5-phase pipeline + backtesting on potentially thousands of candles. CPU-intensive.
- **Status:** TTL cache (1 hour) prevents redundant computation. No background worker yet.

## Fragile Areas

### FRAG-1: FIFO Abort-on-Error
- **Location:** `backend/app/services/sync_service.py`
- **Issue:** Sell allocation loop aborts on first error. This is intentional (protects FIFO invariant) but means one bad fill blocks all subsequent allocations.
- **Impact:** Manual intervention required if a fill has unexpected data.

### FRAG-2: Symbol Registry Synchronization
- **Location:** `backend/app/symbol_registry.py` + `frontend/src/utils/symbolRegistry.js`
- **Issue:** Two separate symbol registries (backend Python, frontend JS) must stay in sync manually.
- **Risk:** Adding a new symbol requires updating both files. No automated check.

### FRAG-3: Binance API Dependencies
- **Location:** `backend/app/services/binance.py`, `sync_service.py`
- **Issue:** Multiple features depend on Binance API availability: sync, reconciliation, balance fetch, kline data.
- **Mitigation:** Graceful degradation for sentiment (falls back to cached data). Portfolio falls back to ledger if Binance unreachable.

### FRAG-4: WebSocket Reconnection
- **Location:** `backend/app/services/websocket_manager.py`, `frontend/src/contexts/WebSocketContext.jsx`
- **Issue:** WebSocket connections can drop. Reconnection logic exists but edge cases in fill processing during reconnect may cause missed fills.
- **Mitigation:** Manual sync (`POST /api/lots/{user_id}/sync`) catches up missed fills.

## Known Limitations

1. **Single exchange:** Binance only. No multi-exchange support.
2. **Spot only:** No futures, margin, or derivatives.
3. **No tax reporting:** Export/CSV planned but not implemented.
4. **No Redis/worker:** Background jobs planned (Celery/RQ) but not implemented. All processing is synchronous or in async endpoints.
5. **Single user:** Hardcoded `user_123`. Multi-user would need auth system overhaul.
