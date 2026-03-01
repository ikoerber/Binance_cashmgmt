---
phase: 28-bnb-fee-tracking
verified: 2026-03-01T11:00:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 28: BNB Fee Tracking Verification Report

**Phase Goal:** User sees BNB balance and cumulative trading fee costs in the Overview asset table, backed by a new backend endpoint
**Verified:** 2026-03-01T11:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A backend endpoint GET /api/portfolio/{user_id}/bnb-fees returns BNB balance and cumulative fee EUR total | VERIFIED | `portfolio.py` line 80: `@router.get("/{user_id}/bnb-fees")`. Route confirmed at `/api/portfolio/{user_id}/bnb-fees`. |
| 2 | The endpoint queries Binance for current BNB balance (free + locked) | VERIFIED | `portfolio_service.py` lines 197-201: `binance_service.fetch_account_balance()` → `bnb_info.get("total", ...)`. `fetch_account_balance()` confirmed in `binance.py` line 251. |
| 3 | The endpoint aggregates fee_quote_value from all TRADE_FILL LedgerEvents where fee_asset is BNB | VERIFIED | `portfolio_service.py` lines 212-220: `func.sum(LedgerEventDB.fee_quote_value)` with filters `EventTypeEnum.TRADE_FILL`, `fee_asset == "BNB"`, `fee_quote_value.isnot(None)`. |
| 4 | The Overview asset table shows a BNB row below the tradable asset rows | VERIFIED | `Overview.jsx` lines 253-270: BNB row rendered after `symbolSummaries.map(...)` block inside `<tbody>`. |
| 5 | The BNB row displays the current BNB balance from the backend | VERIFIED | `Overview.jsx` line 261: `{formatNumber(parseFloat(bnbData.bnb_balance), 4)}`. |
| 6 | The BNB row displays the cumulative EUR-equivalent of BNB trading fees | VERIFIED | `Overview.jsx` line 267: `Fees: {formatEUR(parseFloat(bnbData.cumulative_fee_eur))}`. |
| 7 | The BNB row is not clickable (no navigation, BNB is not a trading pair) | VERIFIED | No `onClick` on BNB row. `onClick` at line 235 only applies to tradable asset rows. BNB row at line 255 has no event handler. |
| 8 | The BNB row is visually distinct (muted style, no P&L% column value) | VERIFIED | `Overview.jsx` line 255: class `overview-asset-row--muted` applied. `Overview.css` lines 175-201: `cursor: default`, `background: transparent` on hover, muted color variables. P&L column shows "Fees: X EUR" instead of percentage. |
| 9 | The frontend calls the new endpoint and integrates BNB data into the Overview | VERIFIED | `Overview.jsx` lines 54-58: `useQuery` with `queryFn: () => getBnbFees(userId)`. `getBnbFees` imported from `client.js` at line 10. |
| 10 | Frontend builds without errors | VERIFIED | `npm run build` exits successfully: "built in 1.34s". No TypeScript/JS errors. |
| 11 | Backend tests pass | VERIFIED | 817 tests pass. 1 pre-existing failure in `test_health_check.py` (AttributeError unrelated to this phase, documented in SUMMARY). |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/api/routes/portfolio.py` | GET /api/portfolio/{user_id}/bnb-fees endpoint | VERIFIED | Lines 80-96. `@router.get("/{user_id}/bnb-fees")`. Imports `get_bnb_fee_summary`. Uses `get_binance_service_optional`. Error sanitization present. |
| `backend/app/services/portfolio_service.py` | get_bnb_fee_summary() service function | VERIFIED | Lines 170-234. Full implementation with BNB balance fetch, fee_quote_value aggregation, BNB/EUR ticker fetch, graceful degradation, Decimal precision. |
| `frontend/src/components/Overview.jsx` | BNB row in asset table | VERIFIED | Lines 53-58 (useQuery), lines 253-270 (BNB row rendering). Contains `bnbData`, conditional render on `bnb_balance > 0`. |
| `frontend/src/api/client.js` | getBnbFees() API client function | VERIFIED | Lines 31-34. `export const getBnbFees = async (userId) => { ... apiClient.get('/api/portfolio/${userId}/bnb-fees') ... }` |
| `frontend/src/components/Overview.css` | BNB muted row and fee info styles | VERIFIED | Lines 174-201. `.overview-asset-row--muted` (cursor, hover, colors) and `.overview-fee-info` (italic, secondary color). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/app/api/routes/portfolio.py` | `backend/app/services/portfolio_service.py` | `get_bnb_fee_summary(db, user_id, binance)` | WIRED | Line 9 import, line 93 call: `return get_bnb_fee_summary(db, user_id, binance)`. |
| `frontend/src/components/Overview.jsx` | `frontend/src/api/client.js` | `getBnbFees(userId)` query | WIRED | Line 10 import, line 56 usage: `queryFn: () => getBnbFees(userId)`. Response consumed at lines 254, 261, 264, 267. |
| `backend/app/services/portfolio_service.py` | `backend/app/db/models.py` | `LedgerEventDB` with `fee_asset='BNB'` and `fee_quote_value` aggregation | WIRED | Lines 212-220: `LedgerEventDB.fee_asset == "BNB"`, `LedgerEventDB.fee_quote_value.isnot(None)`, `func.sum(LedgerEventDB.fee_quote_value)`. `EventTypeEnum` imported at line 10. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| OVW-04 | 28-01-PLAN.md | User sees a BNB row in the asset table showing current Binance BNB balance | SATISFIED | BNB row in `Overview.jsx` lines 254-269 shows `bnbData.bnb_balance` formatted with `formatNumber(..., 4)`. Fetched from Binance via `fetch_account_balance()`. |
| OVW-05 | 28-01-PLAN.md | User sees the EUR-equivalent of cumulative BNB trading fees in the BNB row | SATISFIED | BNB row P&L column displays `Fees: {formatEUR(parseFloat(bnbData.cumulative_fee_eur))}` (line 267). Backed by `SUM(fee_quote_value)` in `get_bnb_fee_summary()`. |

No orphaned requirements found — both OVW-04 and OVW-05 map to this phase in REQUIREMENTS.md and are fully implemented.

### Anti-Patterns Found

No blockers or warnings detected.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/tests/test_health_check.py` | N/A | Pre-existing test failure (AttributeError) | Info | Unrelated to Phase 28. Present before this phase, documented in SUMMARY. 817 other tests pass. |

No stub patterns, placeholder returns, or TODO comments found in the 5 modified files.

### Human Verification Required

The following items require manual testing to fully confirm:

#### 1. BNB Row Conditional Visibility

**Test:** Log in as a user with 0 BNB balance, navigate to Portfolio Overview.
**Expected:** No BNB row appears in the asset table.
**Why human:** Cannot test the `parseFloat(bnbData.bnb_balance) > 0` branch without a live Binance account with 0 BNB.

#### 2. BNB Balance EUR Valuation Accuracy

**Test:** Compare the BNB EUR value displayed in the row against the actual BNB/EUR price from Binance at the time of the request.
**Expected:** `bnb_balance * current BNBEUR price` matches displayed value within rounding.
**Why human:** Requires a live Binance account with BNB holdings.

#### 3. Cumulative Fee EUR Accuracy

**Test:** Cross-reference `cumulative_fee_eur` against manually summed `fee_quote_value` values from the ledger for a known user.
**Expected:** Values match (deterministic aggregation).
**Why human:** Requires access to production ledger data.

### Gaps Summary

None. All must-haves verified. Phase goal is fully achieved.

---

_Verified: 2026-03-01T11:00:00Z_
_Verifier: Claude (gsd-verifier)_
