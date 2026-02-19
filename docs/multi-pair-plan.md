# Multi-Trading-Pair Support (ETH/EUR + beliebige Paare)

## Context

Die App unterstützt aktuell ausschließlich BTC/EUR. Um ETH/EUR (und zukünftig weitere Paare) zu handeln, muss die gesamte Architektur von einem Single-Pair-System zu einem Multi-Pair-System erweitert werden. Die Hauptprobleme: `trade_lots` hat keine `symbol`-Spalte, Feldnamen sind BTC-spezifisch (`qty_btc_*`), Portfolio-Berechnung kennt nur ein Asset, WebSocket ist auf BTCEUR hardcoded, Frontend zeigt überall "BTC" Labels.

**Entscheidungen:**
- Per-Symbol Tabs im Dashboard (+ optionaler "Gesamt"-Tab)
- Pairings strikt innerhalb desselben Symbols
- Volle Umbenennung `qty_btc_*` → `qty_base_*`
- Generische Multi-Pair-Fähigkeit (nicht nur BTC+ETH)

---

## Phase 0: Symbol Registry (Fundament)

Zentrales Mapping von Symbol → Base/Quote/Precision. Alle Schichten referenzieren nur diese Registry.

### Backend: Neue Datei `backend/app/symbol_registry.py`
```python
@dataclass(frozen=True)
class TradingPair:
    symbol: str          # "BTCEUR"
    base_asset: str      # "BTC"
    quote_asset: str     # "EUR"
    base_precision: int  # 8 für BTC, 5 für ETH
    price_precision: int # 2
    label: str           # "BTC/EUR"

KNOWN_PAIRS = {
    "BTCEUR": TradingPair("BTCEUR", "BTC", "EUR", 8, 2, "BTC/EUR"),
    "ETHEUR": TradingPair("ETHEUR", "ETH", "EUR", 5, 2, "ETH/EUR"),
}

def parse_symbol(symbol: str) -> TradingPair: ...
def get_base_asset(symbol: str) -> str: ...
def get_base_precision(symbol: str) -> int: ...
```

### Frontend: Neue Datei `frontend/src/utils/symbolRegistry.js`
```javascript
export const KNOWN_PAIRS = {
  BTCEUR: { symbol: 'BTCEUR', base: 'BTC', quote: 'EUR', baseDecimals: 8, label: 'BTC/EUR' },
  ETHEUR: { symbol: 'ETHEUR', base: 'ETH', quote: 'EUR', baseDecimals: 5, label: 'ETH/EUR' },
};
export const parseSymbol = (symbol) => KNOWN_PAIRS[symbol];
export const getBaseDecimals = (symbol) => KNOWN_PAIRS[symbol]?.baseDecimals ?? 8;
export const getBaseLabel = (symbol) => KNOWN_PAIRS[symbol]?.base ?? symbol;
export const getPairLabel = (symbol) => KNOWN_PAIRS[symbol]?.label ?? symbol;
export const getAllSymbols = () => Object.keys(KNOWN_PAIRS);
```

### Frontend: `frontend/src/utils/formatters.js` erweitern
- Neuer generischer Formatter `formatBase(num, symbol)` mit dynamischer Dezimalstellen + Label
- `formatBTC` bleibt als Alias: `(num) => formatBase(num, 'BTCEUR')`

---

## Phase 1: DB Schema + Domain Models

### 1A: Alembic Migration (neue Datei `backend/alembic/versions/xxxx_multi_pair_support.py`)

SQLite mit `render_as_batch=True` (bereits konfiguriert).

**`trade_lots`:**
1. Spalte `symbol` hinzufügen (nullable=True)
2. Backfill: `UPDATE trade_lots SET symbol = 'BTCEUR'`
3. `symbol` auf `nullable=False` setzen
4. Rename: `qty_btc_initial` → `qty_base_initial`, `qty_btc_open` → `qty_base_open`
5. Neuer Index: `idx_lots_user_symbol_status` auf `(user_id, symbol, status)`

**`pairings`:**
1. Spalte `symbol` hinzufügen (nullable=True)
2. Backfill: `UPDATE pairings SET symbol = 'BTCEUR'`
3. `symbol` auf `nullable=False` setzen

**`pairing_items`:**
1. Rename: `qty_btc` → `qty_base`

### 1B: ORM Models (`backend/app/db/models.py`)

- **TradeLotDB**: `qty_btc_initial` → `qty_base_initial`, `qty_btc_open` → `qty_base_open`, neue Spalte `symbol = Column(String, nullable=False)`, Index aktualisieren
- **PairingDB**: neue Spalte `symbol = Column(String, nullable=False)`
- **PairingItemDB**: `qty_btc` → `qty_base`

### 1C: Domain Dataclasses (`backend/app/domain/models.py`)

- **TradeLot**: `qty_btc_initial` → `qty_base_initial`, `qty_btc_open` → `qty_base_open`, neues Feld `symbol: str = "BTCEUR"`. Properties `break_even`, `unrealized_pnl` anpassen.
- **PairingItem**: `qty_btc` → `qty_base`
- **Pairing**: `net_qty_btc()` → `net_qty_base()`, neues Feld `symbol: str = "BTCEUR"`
- **PairingSimulation**: `total_btc_to_sell` → `total_base_to_sell`, `remaining_portfolio_btc` → `remaining_portfolio_base`
- **PortfolioState**: `btc_qty` → `base_qty`, `btc_cost_basis_eur` → `base_cost_basis_eur`, neues Feld `symbol: str = "BTCEUR"`. Properties anpassen.
- **DailyPerformance**: `buys_volume_btc_today` → `buys_volume_base_today`, `sells_volume_btc_today` → `sells_volume_base_today`

### 1D: Domain-Logik

**`backend/app/domain/portfolio.py`** — `compute_portfolio_from_ledger()`:
- Neuer Parameter `symbol: str = "BTCEUR"`
- Statt `event.asset == "BTC"` → `event.asset == get_base_asset(symbol)` aus Registry
- Events nach `event.symbol == symbol` filtern (für TRADE_FILL)
- `PortfolioState` mit `symbol` und umbenannten Feldern zurückgeben

**`backend/app/domain/lots.py`**:
- `create_trade_lot_from_buy_fill()`: Fee-Check `fee_asset == "BTC"` → `fee_asset == get_base_asset(symbol)`, `symbol` auf TradeLot setzen
- Alle `qty_btc_*` Referenzen → `qty_base_*`

**`backend/app/domain/pairing.py`**:
- Alle `qty_btc` → `qty_base`, `net_qty_btc` → `net_qty_base`
- Caller ist verantwortlich, nur Same-Symbol-Lots zu übergeben

**`backend/app/domain/orders.py`** (falls vorhanden):
- Hardcoded `"BTCEUR"` → Symbol-Parameter

**`backend/app/domain/lot_merge.py`**:
- `new_qty_btc_initial` → `new_qty_base_initial`, `new_qty_btc_open` → `new_qty_base_open`

---

## Phase 2: Services Layer

### 2A: `backend/app/services/lot_service.py` (~1161 Zeilen, größtes Service-File)
- `get_lots_for_user()`: Neuer Parameter `symbol: Optional[str]`, Filter `.filter(TradeLotDB.symbol == symbol)` wenn gesetzt
- `create_lot_from_buy_fill()`: `symbol` aus Fill-Event auf Lot persistieren
- Sell-Allocation Funktionen: Open-Lots nach Symbol filtern (verhindert Cross-Symbol-Allocation)
- `_lot_db_to_dict()`: Rename `qty_btc_*` → `qty_base_*`, `symbol` hinzufügen
- `_lot_db_to_domain()`: Mapping anpassen
- Merge-Funktionen: Symbol-Filter + Rename

### 2B: `backend/app/services/pairing_service.py`
- `get_pairing_suggestions()`: Parameter `symbol`, Lots nach Symbol filtern
- `create_pairing()`: `symbol` Parameter, **Validierung: alle Lot-Symbole müssen identisch sein**, `symbol` auf PairingDB persistieren
- `list_pairings()`: Optionaler Symbol-Filter
- `_pairing_to_dict()`: Rename `qty_btc` → `qty_base`, `net_qty_btc` → `net_qty_base`, `symbol` hinzufügen
- `simulate_pairing_execution()`: Lots nach Pairing-Symbol filtern

### 2C: `backend/app/services/order_service.py`
- `create_limit_sell_for_lot()`: Symbol aus Lot-Objekt statt hardcoded
- `create_limit_sell_for_pairing()`: Symbol aus Pairing-Objekt
- Precision aus Symbol-Registry statt hardcoded

### 2D: `backend/app/services/portfolio_service.py`
- `get_portfolio_state()`: Parameter `symbol`, Base-Asset dynamisch, Lots nach Symbol filtern
- Binance-Balance: `get_base_asset(symbol)` statt hardcoded "BTC"

### 2E: `backend/app/services/sync_service.py`
- Lot-Erstellung setzt `symbol` aus dem Fill-Event
- Fee-Check: `get_base_asset(symbol)` statt `"BTC"`

### 2F: `backend/app/services/websocket_manager.py` (KRITISCH)
- Multi-Stream: `wss://stream.binance.com:9443/stream?streams=btceur@ticker/etheur@ticker`
- Combined-Stream-Format parsen: `{"stream": "...", "data": {...}}`
- Preise pro Symbol speichern: `self.current_prices = {"BTCEUR": ..., "ETHEUR": ...}`

### 2G: `backend/app/services/websocket_fill_handler.py` (KRITISCH)
- Guard `if symbol != "BTCEUR": skip` **entfernen**
- Stattdessen: `parse_symbol(symbol)` — unbekannte Symbole loggen und skippen
- `asset` dynamisch: `pair.base_asset` statt hardcoded `"BTC"`

### 2H: `backend/app/services/reconciliation_service.py`
- `reconcile_balances()`: Base-Asset aus Symbol-Registry
- Response-Felder dynamisch (nicht hardcoded "btc"/"eur")

### 2I: `backend/app/services/order_tracking_service.py`
- Defaults `symbol="BTCEUR"` bleiben, aber Caller übergibt explizit

### 2J: `backend/app/services/csv_import_service.py`
- Bereits dynamisch (liest Symbol aus CSV) — nur Rename-Kompatibilität

---

## Phase 3: API Routes

### Alle Route-Dateien in `backend/app/api/routes/`:

**`portfolio.py`**: `symbol: str = Query("BTCEUR")` zu `get_portfolio()` hinzufügen

**`lots.py`**: `symbol: Optional[str] = Query(None)` zu `list_lots()` hinzufügen

**`pairing.py`**:
- `symbol: str = Query("BTCEUR")` zu `get_suggestions()`
- `PairingCreateRequest`: Feld `symbol: str = "BTCEUR"` hinzufügen
- Pydantic-Model: `qty_btc` → `qty_base`

**`orders.py`**: Symbol kommt jetzt aus Lot/Pairing, nicht mehr aus Default

**`reconciliation.py`**: Symbol an `reconcile_balances()` durchreichen

**`combined.py`, `sentiment.py`**: `ALLOWED_SYMBOLS` → `KNOWN_PAIRS.keys()` aus Registry. Sentiment/Macro bleiben vorerst BTC-fokussiert (marktweite Signale).

**Symbol-Validierung**: Alle Endpoints validieren `symbol in KNOWN_PAIRS`

---

## Phase 4: Frontend — Globaler Symbol-Selector + Data Flow

### 4A: App State erweitern (`frontend/src/contexts/AppStateContext.jsx`)
- Neuer State: `activeSymbol` + `setActiveSymbol`
- Im Provider bereitstellen

### 4B: Symbol Selector in Navbar (`frontend/src/App.jsx`)
- Pill-Buttons oder Dropdown in der Navbar mit allen Symbolen aus `getAllSymbols()`
- `useLivePrice(activeSymbol)` statt hardcoded `'BTCEUR'`
- Titel: `${getPairLabel(activeSymbol)} Cashflow Management`
- Footer: Dynamischer Pair-Name

### 4C: WebSocket Context (`frontend/src/contexts/WebSocketContext.jsx`)
- Preise pro Symbol empfangen und speichern
- `useLivePrice(symbol)` filtert nach aktivem Symbol

### 4D: API Client (`frontend/src/api/client.js`)
- Alle Funktionen: `symbol` Parameter zu API-Calls durchreichen
- Defaults bleiben `'BTCEUR'`, Komponenten übergeben `activeSymbol`

### 4E: Alle Komponenten aktualisieren

**`Dashboard.jsx`**: Titel + Labels dynamisch (`${getBaseLabel(activeSymbol)} Bestand`), `formatBase()` statt `formatBTC()`, API-Calls mit `activeSymbol`

**`LotsTable.jsx`**: Feld-Zugriff `lot.qty_base_initial` statt `lot.qty_btc_initial`, `formatBase()` mit Symbol, Sync/Orders mit `activeSymbol`

**`LotSummaryCards.jsx`**: `formatBase()` mit Symbol

**`LotFilters.jsx`**: Keine Änderung nötig (keine BTC-Referenzen)

**`OpenOrdersPanel.jsx`**: `formatBase()` statt `formatBTC()`

**`PairingPanel.jsx`**: `qty_base` statt `qty_btc`, API-Calls mit Symbol

**`PairingExistingTab.jsx`**: Rename `qty_btc` → `qty_base`

**`SimulationModal.jsx`**: `total_base_to_sell`, `remaining_portfolio_base`, dynamische Labels

**`Reconciliation.jsx`**: Labels dynamisch (`"BTC"` → `getBaseLabel(activeSymbol)`), API mit Symbol

**`CombinedScore.jsx`**: Pair-Label dynamisch. Inhaltlich bleibt es BTC-fokussiert (Makro/Sentiment sind marktweite Signale).

**`FillNotification.jsx`**: Symbol in Notification-Text anzeigen

**`Orderblock.jsx`**: Bereits symbol-aware — `activeSymbol` als Default verwenden

**`useLotsData.js`**: `activeSymbol` als Query-Key-Dependency, an API-Calls übergeben

### 4F: TanStack Query Keys
- **WICHTIG**: Alle Query-Keys müssen `activeSymbol` enthalten, damit beim Symbol-Wechsel frische Daten geladen werden
- Beispiel: `['portfolio', userId, activeSymbol, marketPrice]`

---

## Phase 5: Dashboard Per-Symbol Tabs

### `frontend/src/components/Dashboard.jsx`
- Tab-Bar: Ein Tab pro Symbol aus `getAllSymbols()` + "Gesamt"-Tab
- Per-Symbol Tab: Eigene KPIs, Break-even, P&L (wie bisher, aber für das gewählte Symbol)
- "Gesamt"-Tab: Aggregierte EUR-Werte (Total investiert, Total Marktwert, Total P&L)
  - Kein Break-even (sinnlos cross-asset)
  - Summe aller realisierten + unrealisierten P&L
- Styling: Tab-Design passend zum Purple-Gradient der Navbar

### `frontend/src/components/Dashboard.css`
- Tab-Styling hinzufügen

---

## Phase 6: Tests + Cleanup

### Backend Tests (18 Dateien)
- **Mechanisches Rename** in allen Testdateien: `qty_btc_*` → `qty_base_*`, `btc_qty` → `base_qty`
- Neue Tests in `test_symbol_registry.py`: Parse, Precision, Unknown Symbol
- `test_portfolio_breakeven.py`: Test per-symbol Portfolio-Berechnung
- `test_pairing.py`: Test Same-Symbol-Validierung (Cross-Symbol → Fehler)
- `test_lots_fifo.py` / `test_lots_strategies.py`: Verifizieren dass Sell-Allocation nur innerhalb desselben Symbols allokiert
- **Sicherheitstest**: ETHEUR-Sell darf nicht gegen BTCEUR-Lots allokieren

### Grep-Validierung nach jedem Phase-Abschluss
```bash
grep -r "qty_btc" backend/app/ --include="*.py"  # Muss 0 Treffer liefern
grep -r "qty_btc" frontend/src/ --include="*.js" --include="*.jsx"  # Muss 0 Treffer liefern
```

### CLAUDE.md aktualisieren
- Projektstruktur: `symbol_registry.py`, `symbolRegistry.js`
- Datenmodell: Neue Spalten, umbenannte Felder
- Invarianten: Same-Symbol-Pairing-Regel, Symbol-Validierung
- API-Endpoints: `symbol` Parameter dokumentieren

---

## Kritische Risiken + Mitigierung

| Risiko | Mitigierung |
|--------|-------------|
| Rename verpasst eine `qty_btc`-Referenz → Runtime Error | `grep -r "qty_btc"` nach jedem Phase + `pytest` |
| SQLite Migration schlägt fehl (Column Rename) | `render_as_batch=True` (bereits aktiv), Migration auf DB-Kopie testen |
| Cross-Symbol Sell-Allocation (ETHEUR-Sell gegen BTCEUR-Lot) | Symbol-Filter in allen Sell-Allocation-Queries + Assertion in Domain-Logik |
| WebSocket Combined-Stream-Format anders als erwartet | Mit Binance Testnet validieren |
| Bestehende BTC/EUR-Daten gehen kaputt | Backfill `symbol='BTCEUR'` in Migration, alle Defaults auf `"BTCEUR"` |
| API-Response Breaking Change (Frontend erwartet alte Feldnamen) | Phase 1-3 (Backend) und Phase 4 (Frontend) gemeinsam deployen |

## Reihenfolge & Abhängigkeiten

```
Phase 0 (Registry)        → Keine Abhängigkeit
Phase 1 (Schema + Domain) → Benötigt Phase 0
Phase 2 (Services)        → Benötigt Phase 1
Phase 3 (API Routes)      → Benötigt Phase 2
Phase 4 (Frontend Flow)   → Benötigt Phase 3
Phase 5 (Dashboard Tabs)  → Benötigt Phase 4
Phase 6 (Tests + Cleanup) → Parallel zu Phase 4-5 möglich
```

## Verifizierung

1. **Backend**: `pytest` — alle 18 Testdateien grün nach Rename
2. **Grep**: Keine `qty_btc`-Referenzen mehr im Code
3. **Manuell**: BTCEUR-Sync + Dashboard → KPIs korrekt
4. **Manuell**: ETHEUR-Sync → Eigene Lots, eigenes Portfolio, eigene Pairings
5. **Manuell**: Symbol-Wechsel im Frontend → Daten aktualisieren sich
6. **Manuell**: Cross-Symbol-Pairing-Versuch → Fehler
7. **Manuell**: WebSocket zeigt Preise für beide Paare
8. **Linting**: `ruff check . && black --check .`
9. **Frontend**: `npm run build` erfolgreich
