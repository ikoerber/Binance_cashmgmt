# Conventions

## Code Style

### Backend (Python)
- **Formatter:** black (default config)
- **Linter:** ruff
- **Run:** `ruff check . && black --check .` / `black . && ruff check --fix .`
- **Python version:** 3.13+
- **Type hints:** Used for function signatures (not exhaustive)

### Frontend (JavaScript/React)
- **Linter:** ESLint (via `npm run lint`)
- **No TypeScript** — plain JavaScript with JSX
- **No UI framework** — plain CSS, component-scoped
- **React 19** with functional components only (no class components)

## Decimal Precision

**Critical invariant:** `Decimal` for all money/price calculations. Never `float`.

```python
# CORRECT
from decimal import Decimal
price = Decimal("50000.00")
qty = Decimal("0.01")
cost = price * qty  # Decimal("500.00")

# WRONG
price = 50000.00  # float — precision loss
```

**API transport:** Decimal values as strings to prevent IEEE 754 loss:
```python
# Backend response
{"base_qty": "0.01234567", "break_even": "48523.45"}

# Frontend parsing
const qty = parseFloat(portfolio.base_qty);
```

## Error Handling

### Backend Routes
- All routes wrap in try/except
- Client gets generic message: `"Interner Serverfehler"` (HTTP 500)
- Server logs full exception: `logger.exception("...")`
- Input validation: `market_price` checked for NaN, Inf, negative (HTTP 400)

```python
# Pattern in every route
try:
    result = some_service_call(db, user_id, ...)
    return result
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
except Exception:
    logger.exception("Unexpected error in ...")
    raise HTTPException(status_code=500, detail="Interner Serverfehler")
```

### Domain Functions
- Raise `ValueError` for business logic violations
- No logging in domain layer (pure functions)
- Return types are always dataclasses or primitives

### Frontend
- TanStack Query handles loading/error states
- Components check `isLoading`, `error` before rendering data
- Optimistic updates not used — refetch after mutations via query invalidation

## Import Organization

### Backend
```python
# 1. Standard library
import logging
from datetime import datetime
from decimal import Decimal

# 2. Third-party
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# 3. Internal (app)
from app.domain.models import LedgerEvent, PortfolioState
from app.services.portfolio_service import get_portfolio_state
from app.db.database import get_db
```

### Frontend
```javascript
// 1. React/libraries
import { useMemo, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';

// 2. Internal
import { getPortfolio, getLots } from '../api/client';
import { useSymbol } from '../contexts/SymbolContext';
import { formatEUR, formatBTC } from '../utils/formatters';
import './Component.css';
```

## Database Patterns

### Session Management (yield pattern)
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

### Row-Level Locking (race condition protection)
```python
# Used in pairing_service.py for create + lock
lots = db.query(TradeLotDB).filter(...).with_for_update().all()
```

### Alembic Migrations
- SQLite requires `render_as_batch=True` for ALTER TABLE operations
- Run: `alembic upgrade head` / `alembic revision --autogenerate -m "..."`

## API Design Patterns

### Endpoint Naming
- REST-style: `GET /api/lots/{user_id}`, `POST /api/orders/{user_id}/lot/{lot_id}/create`
- All routes prefixed with `/api/`
- User ID in URL path (not query param) for main resource endpoints

### Response Format
- All responses are JSON dicts (not wrapped in envelope)
- Lists returned as `{"lots": [...]}`, `{"orders": [...]}`, etc.
- Decimal values as strings: `"base_qty": "0.01234567"`
- Timestamps as ISO 8601 strings

### Authentication
- Header: `X-API-Key`
- Configured via `API_KEY` in `.env`
- Applied globally via FastAPI dependency

## Frontend Patterns

### Data Fetching
```javascript
// TanStack Query with symbol-scoped keys
const { data, isLoading, error } = useQuery({
  queryKey: ['portfolio', activeSymbol, userId, stablePrice],
  queryFn: () => getPortfolio(userId, marketPrice, activeSymbol),
});
```

### Query Invalidation After Mutations
```javascript
const mutation = useMutation({
  mutationFn: (data) => createOrder(userId, lotId, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['orders'] });
    queryClient.invalidateQueries({ queryKey: ['lots'] });
  },
});
```

### Shared Formatters
```javascript
// All components use shared formatters from utils/formatters.js
formatEUR(1234.56)    // "1.234,56 €"
formatBTC(0.01234)    // "0,01234 ₿"
formatPct(5.5)        // "+5,50%"
formatNumber(1234.56) // "1.234,56"
```

### CSS Conventions
- Component-scoped: `Dashboard.css`, `LotsTable.css`, etc.
- Color scheme: Purple nav gradient, green profit, red loss, indigo accent
- Patterns: summary cards, filter groups, toggle switches, status badges
- No CSS-in-JS, no Tailwind — plain CSS with BEM-like class names
