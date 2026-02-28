# Phase 13: XRPBTC Infrastructure - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Re-add XRPBTC to Symbol Registry, Binance Sync, and frontend with correct EUR-denominated financials. No cross-pair pairing. No sell order creation for XRPBTC lots. XRPBTC is re-added for analysis and position tracking, with automated trading handled by the Omni-Bot in later phases.

</domain>

<decisions>
## Implementation Decisions

### Lot display & P&L
- Dual display: show both BTC and EUR values side by side (e.g., "0.00002345 BTC / 1.87 EUR")
- Side-by-side layout in table columns (separated by slash), same font size for both values
- Pair badge on each lot row: small badge showing "XRPBTC" or "XRPEUR" to distinguish lots visually
- Unrealized P&L uses live BTCEUR price for EUR conversion (real-time EUR equivalent, not historical rate at purchase)

### Historical data handling
- Backfill existing XRPBTC lots via Binance Klines API (fetch historical BTC/EUR rate at each lot's fill time)
- New Alembic forward migration to re-add ALL columns dropped in v2.0 migration 094dac6f695a (quote_to_eur_rate, lot_symbol, base_asset, and any others)
- Few or no existing XRPBTC lots expected, but backfill script handles whatever exists
- Backfill uses proper Decimal precision (fix the float() issue from original backfill_cost_eur.py)

### Symbol selector
- XRPBTC pill placed after XRPEUR in navbar: BTCEUR | ETHEUR | XRPEUR | XRPBTC
- Different accent color for XRPBTC pill (amber/orange for BTC-quoted, distinguishes from purple EUR pairs)
- Subtle "Low liquidity" indicator on the XRPBTC dashboard (not intrusive, informational)

### Pairing isolation
- No pairing for XRPBTC lots at all (not just excluded from EUR pairings — pairing is entirely disabled for BTC-quoted pairs)
- Hide PairingPanel UI entirely on XRPBTC page (no checkboxes, no pairing tabs)
- No sell order creation for XRPBTC lots (analysis/tracking only, automated selling via Omni-Bot later)

### Claude's Discretion
- Overview page inclusion of XRPBTC in portfolio totals (Claude determines based on existing component patterns)
- Pairing isolation strictness (Claude determines whether suggestions-only or full isolation from manual selection is cleaner)

</decisions>

<specifics>
## Specific Ideas

- Amber/orange color for XRPBTC aligns with the existing Binance-accent color (#f7931a) already used for sync operations
- The dual BTC/EUR display pattern may be useful for other BTC-quoted pairs if added in the future

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 13-xrpbtc-infrastructure*
*Context gathered: 2026-02-25*
