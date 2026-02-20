# Testing

## Overview

- **Framework:** pytest
- **Test files:** 22 files in `backend/tests/`
- **Total tests:** 569+
- **Total lines:** ~10,600
- **Runtime:** ~4 seconds (all tests)
- **Frontend tests:** None yet (planned: Vitest)

## Test Configuration

### `backend/tests/conftest.py`
- **Test key isolation:** Session-scoped autouse fixture swaps `BINANCE_API_KEY` → `TEST_BINANCE_API_KEY`
- **Testnet:** Sets `BINANCE_TESTNET=true` (Binance testnet endpoint)
- **Shared factories:** `make_candle()`, `make_binance_kline()` for orderblock tests
- **Safety:** Warns if test keys are missing (prevents accidental production API usage)

```python
@pytest.fixture(autouse=True, scope="session")
def use_test_binance_keys():
    """Alle Tests verwenden TEST_BINANCE_API_KEY statt Produktions-Keys."""
    os.environ["BINANCE_API_KEY"] = os.getenv("TEST_BINANCE_API_KEY")
    os.environ["BINANCE_TESTNET"] = "true"
```

## Test Structure

### Domain Tests (Pure Logic, No DB)
Most tests operate on domain functions with in-memory dataclasses — no database, no mocking.

| File | Tests | What it covers |
|------|-------|----------------|
| `test_portfolio_breakeven.py` | WAC, fees, partial sells, BNB fee handling |
| `test_portfolio_cross_pair.py` | 11 | Multi-symbol isolation, legacy events, daily perf |
| `test_lots_fifo.py` | FIFO allocation determinism |
| `test_lots_strategies.py` | 18 | LIFO, HIGHEST_COST, overflow strategies |
| `test_lots_lot_specific.py` | Lot-specific sell targets |
| `test_lot_fee_handling.py` | Fee calculation (EUR/BTC/BNB) |
| `test_lot_merge.py` | Lot merge detection |
| `test_pairing.py` | Pairing heuristic, thresholds |
| `test_pairing_execution.py` | Simulation, affected lots |
| `test_macro_signal.py` | Macro factor calculations |
| `test_sentiment_v3.py` | 45+ | 5-pillar scoring, dispersion, volatility, multiplier |
| `test_combined_score.py` | Score normalization, action mapping |
| `test_orderblock_detection.py` | ATR, swings, FVG, conviction, pipeline, states |
| `test_orderblock_backtest.py` | HIT/MISS/EXPIRED/OPEN, penetration, metrics |
| `test_timezone_handling.py` | Timezone edge cases |

### Service Tests (Integration-Like)
| File | What it covers |
|------|----------------|
| `test_order_lifecycle.py` | Create → Fill → Closed |
| `test_sync_lots.py` | Binance sync flow |
| `test_reconciliation.py` | Balance reconciliation |
| `test_csv_import.py` | CSV import validation |
| `test_historical_price.py` | 13 tests — BNB fee conversion, kline prices, fallback |
| `test_orderblock_service.py` | Kline pagination, cache, serialization, CRUD |
| `test_websocket_fill_handler.py` | Real-time fill processing |

## Test Patterns

### Domain Test Pattern (Most Common)
```python
def test_buy_fill_increases_base_qty():
    """Descriptive German docstring."""
    events = [
        LedgerEvent(
            id="1",
            type=EventType.TRADE_FILL,
            timestamp=datetime(2024, 1, 1),
            asset="BTC",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            side=TradeSide.BUY,
            source=EventSource.BINANCE,
        ),
    ]

    portfolio = compute_portfolio_from_ledger(events, symbol="BTCEUR")

    assert portfolio.base_qty == Decimal("0.01")
    assert portfolio.base_cost_basis_quote == Decimal("500.00")
```

### Helper Factories
```python
# In test files — lightweight factory functions
def _make_fill(id, symbol, asset, amount, price, side, **kwargs):
    return LedgerEvent(id=id, type=EventType.TRADE_FILL, ...)

# In conftest.py — shared across test files
def make_candle(index, o, h, low, c, v="100"):
    return Candle(timestamp=OB_BASE_TIME + timedelta(hours=index), ...)
```

### No Mocking (Domain Tests)
Domain tests use real domain functions with in-memory data. No mocking needed because domain has zero I/O.

### Test Organization
- Tests grouped by class (e.g., `TestCrossPairIsolation`, `TestExternalCashflowFilter`)
- German docstrings describing what each test verifies
- Decimal assertions use exact comparison (`== Decimal("0.01")`)

## Running Tests

```bash
cd backend
source venv/bin/activate

# All tests
pytest

# Single file
pytest tests/test_portfolio_cross_pair.py

# Verbose
pytest -v

# With coverage
pytest --cov=app tests/

# Stop on first failure
pytest -x
```

## Coverage

- No formal coverage threshold configured
- Domain layer has highest coverage (pure functions, easy to test)
- Service layer has moderate coverage (some integration tests)
- API routes have minimal direct testing (tested indirectly via service tests)
- Frontend: 0% (no tests yet)

## Test Gaps

1. **Frontend tests** — Zero automated tests. Planned: Vitest for critical flows (pairing lifecycle, lot filters, formatters)
2. **API route tests** — No direct HTTP-level tests (e.g., TestClient)
3. **WebSocket integration** — Limited to fill handler unit tests
4. **End-to-end** — No E2E test framework
