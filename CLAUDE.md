# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# BTC/EUR Cashflow-Management & Automation App

## Projektstatus

BTC/EUR Cashflow-Management & Automation App für Binance Spot Trading. Ledger-basiertes, deterministisches, auditierbares Cashflow-Tracking und automatisiertes Trading-System.

**Implementiert (Iteration 1-3):**
- Append-only Ledger mit allen Event-Typen
- Portfolio Break-even (WAC) + Dashboard mit 8 KPI-Kacheln
- TradeLots (1 Fill = 1 Lot) + FIFO Sell Allocation
- Trade-Cockpit mit Filtern, Sortierung, Live-P&L, Sell-Order-Indikatoren, Erholungspreis-KPI
- Binance Sync (Fills Import, inkrementell)
- Order-Erstellung (TAKE_PROFIT_LIMIT Sell pro Lot) + Order-Tracking
- Pairing: Backend-Heuristik + Frontend-UI (Vorschläge, manuell, Simulation, Lifecycle)
- Reconciliation-Service + Reconciliation-UI (3 Sektionen: Orders, Balances, Fills)
- Settings-Seite (max_order_value_eur konfigurierbar)
- Live BTC/EUR Preis via Binance API
- Makro-Signal Backend (4 Faktoren, konfigurierbar, Richtungsempfehlung)
- Sentiment Engine v3 Backend (5 Pillars, korrelationsgewichtete Aggregation, Dispersion + Volatility Scaling)
- Combined Score Dashboard: Vereint MacroSignal (Richtung, 60%) und Sentiment (Sizing, 40%) zu einheitlicher Handlungsempfehlung mit Unified Score (-100 bis +100), ersetzt eigenstaendige MacroSignal- und Sentiment-Seiten
- CSV Import (Binance Spot Order History)
- API-Key Authentication (Header `X-API-Key`, konfigurierbar via `API_KEY` in `.env`)
- Transaction-Safety: SQLAlchemy Auto-Commit/Rollback via `yield`-Pattern
- Shared Formatters (`utils/formatters.js`) fuer alle Frontend-Komponenten
- Komponenten-Aufspaltung: LotFilters, OpenOrdersPanel, SimulationModal, PairingExistingTab
- Dependencies gepinnt auf exakte Versionen in `requirements.txt`
- Alternative Sell Allocation Strategien (FIFO, LIFO, HIGHEST_COST) konfigurierbar in Settings
- Historische Fee-Umrechnung: BNB-Fees per Binance Klines API zum Fill-Zeitpunkt konvertiert (statt aktuellem Preis), `fee_eur_value` auf LedgerEvent persistiert, Portfolio BNB-Fee-Handling konsistent mit Lot-Ebene
- Orderblock Detection Engine: Institutionelle Preiszonen-Erkennung mit 5-Phasen-Validierung, Conviction Scoring (Cont/Bouchaud), AlbaTherium-Klassifikation, Backtesting mit Triple-Barrier-Methode (Lopez de Prado), Candlestick-Chart-Visualisierung (lightweight-charts)
- API Hardening: Error Message Sanitization (generische Fehlermeldungen, keine Stacktraces an Client), Structured Logging (`logger.exception()`) auf allen Route-Modulen, Input Validation (`market_price` NaN/Inf/negativ-Pruefung)
- Decimal-String-Transport: Pairing API (`qty_btc`, `threshold_pct`) und Settings API (`max_order_value_eur`, `ob_atr_multiplier`, `ob_target_rr`) als String statt float (Praezisionsverlust vermeiden)
- Race Condition Protection: Row-Level Locking (`with_for_update()`) in Pairing-Service (Create + Lock)
- FIFO Abort-on-Error: Sync-Service bricht Sell-Allocation-Schleife bei Fehler ab (schuetzt FIFO-Invariante)
- Pairing-Heuristik v1.2: Minimum 2 Lots pro Pairing (einzelne profitable Lots direkt per Sell-Order verkaufbar)
- WebSocket Phase 3: Echtzeit Fill-Verarbeitung (Lot-Erstellung + Sell-Allocation via executionReport, ohne manuellen Sync)

## Kernprinzipien

- **Ledger-first**: Alle Berechnungen aus append-only Event-Ledger ableitbar
- **Deterministisch**: Jede Kennzahl aus Ledger + Regeln reproduzierbar
- **Decimal-Präzision**: `Decimal` für alle Geld-/Preisberechnungen (niemals float)
- **Idempotente Orders**: `clientOrderId` = `{userId}_{lotId}_{targetPrice}_{qty}_{version}`
- **FIFO Allocation**: Sell-Fills schließen immer die ältesten Lots zuerst
- **Simulation vor Execution**: Pairing-Ausführung nur nach Simulation-Preview
- **Zeitkonsistente Orderblocks**: Keine Look-Ahead-Bias — Zonen erst ab `confirmed_at_index + 1` handelbar

## Technologiestack

**Backend:** Python 3 + FastAPI, SQLAlchemy 2, Alembic, python-binance
**Frontend:** React 19 + Vite 7, TanStack Query, Axios, Recharts
**Datenbank:** SQLite (Alembic mit `render_as_batch=True` fuer volle Migrations-Kompatibilitaet)
**Testing:** pytest (Backend), ruff + black (Linting)
**Infrastruktur:** Redis (geplant für Celery/RQ Worker)

## Projektstruktur

```
cashmgnt/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI App, Route-Registrierung
│   │   ├── domain/                    # Pure Domain-Logik (kein I/O)
│   │   │   ├── models.py             # Dataclasses: LedgerEvent, TradeLot, Pairing, PortfolioState
│   │   │   ├── portfolio.py           # compute_portfolio_from_ledger() - zentrale Berechnung
│   │   │   ├── lots.py                # create_trade_lot_from_buy_fill(), allocate_sell_with_strategy(), allocate_sell_fifo()
│   │   │   ├── pairing.py            # suggest_pairings(), simulate_pairing()
│   │   │   ├── macro_signal.py        # Makro-Faktoren Analyse + Richtungsempfehlung
│   │   │   ├── sentiment.py           # Sentiment v3: 5-Pillar Scoring, Dispersion, Volatility Scaling
│   │   │   ├── orderblock.py          # Orderblock Detection: 5-Phasen-Pipeline, Conviction Scoring, Zone State Machine
│   │   │   └── orderblock_backtest.py # Backtesting: Triple-Barrier-Simulation, Hit-Rate-Metriken, Conviction-Breakdown
│   │   ├── services/                  # DB-Integration, Binance API
│   │   │   ├── binance.py            # Binance API Client (inkl. get_historical_price via Klines API)
│   │   │   ├── sync_service.py       # Fills importieren (historische Fee-Konvertierung pro Fill, FIFO Abort-on-Error)
│   │   │   ├── lot_service.py        # Lot CRUD + FIFO
│   │   │   ├── order_service.py      # Order-Erstellung (TAKE_PROFIT_LIMIT)
│   │   │   ├── order_tracking_service.py # Order State Lifecycle
│   │   │   ├── pairing_service.py    # Pairing-Persistenz + Lifecycle (Row-Level Locking)
│   │   │   ├── portfolio_service.py  # Portfolio-State aus Ledger
│   │   │   ├── reconciliation_service.py
│   │   │   ├── csv_import_service.py  # CSV Import (nur fuer Trading Bot / Grid Bot Trades, da diese NICHT ueber die Binance API abrufbar sind)
│   │   │   ├── macro_data_service.py  # Makro-Daten (Klines, Fear&Greed, etc.)
│   │   │   ├── sentiment_data_service.py # Sentiment-Daten: F&G, OKX Funding, Klines, Caching (Singleton)
│   │   │   ├── orderblock_data_service.py # Kline-Fetching (Binance REST, paginiert), Detection-Orchestrierung, TTL-Cache (1h)
│   │   │   └── orderblock_persistence_service.py # Zone CRUD (Upsert, Stale-Cleanup), Backtest-Run Persistierung
│   │   ├── db/
│   │   │   ├── database.py           # SQLAlchemy Session
│   │   │   └── models.py             # ORM: LedgerEventDB, TradeLotDB, PairingDB, OrderDB, UserSettingsDB
│   │   ├── api/
│   │   │   ├── auth.py                # API-Key Authentication Dependency
│   │   │   └── routes/                # Thin HTTP Layer
│   │   │       ├── portfolio.py       # GET /api/portfolio/{user_id}
│   │   │       ├── lots.py            # GET/POST /api/lots/...
│   │   │       ├── orders.py         # POST/GET/DELETE /api/orders/...
│   │   │       ├── pairing.py        # GET/POST/DELETE /api/pairing/...
│   │   │       ├── cashflow.py       # External Cashflows
│   │   │       ├── sync.py           # Binance Sync
│   │   │       ├── reconciliation.py # POST /api/reconciliation/...
│   │   │       ├── settings.py       # GET/PUT /api/settings/{user_id}
│   │   │       ├── macro.py          # GET /api/macro/...
│   │   │       ├── sentiment.py     # GET /api/sentiment/{user_id}/current
│   │   │       ├── combined.py     # GET /api/combined/{user_id}/score (MacroSignal + Sentiment)
│   │   │       └── orderblock.py    # POST analyze, GET/DELETE zones, GET backtest runs/candles
│   ├── scripts/
│   │   ├── backtest_sentiment.py     # Backtesting: v1/v2/v3 Sentiment vs. 2000+ Tage historische Daten
│   │   └── backtest_orderblock.py    # Orderblock Backtesting: Single-Run + Parameter-Sweep (ATR, R:R, Timeframes)
│   ├── tests/                         # 18 Testdateien
│   │   └── conftest.py               # TEST_BINANCE_API_KEY + Testnet
│   ├── alembic/                       # DB-Migrationen
│   ├── requirements.txt
│   └── .env                           # DB_URL, BINANCE_API_KEY/SECRET, TEST_BINANCE_API_KEY/SECRET
│
└── frontend/
    ├── src/
    │   ├── App.jsx                    # Routing: Dashboard | TradeLots | Combined Score | Orderblocks | Reconciliation | Settings | API Docs
    │   ├── api/client.js              # Axios: Portfolio, Lots, Orders, Pairing, Sync, Reconciliation, Settings, Combined Score, Orderblocks
    │   ├── components/
    │   │   ├── Dashboard.jsx          # 8 KPI-Kacheln (Break-even, P&L, BTC, EUR)
    │   │   ├── LotsTable.jsx          # Trade-Cockpit: Tabelle, Sort, Checkboxen, Pairing-Integration
    │   │   ├── LotFilters.jsx         # Filter-Bar (Status, Order Nr, Datum, Closed-Toggle)
    │   │   ├── OpenOrdersPanel.jsx    # Offene Sell Orders Tabelle
    │   │   ├── PairingPanel.jsx       # 2-Tab Panel: Vorschläge | Manuell + Routing zu Bestehende
    │   │   ├── PairingExistingTab.jsx # Tab "Bestehende Pairings" (Lifecycle, Mutations, Simulation)
    │   │   ├── SimulationModal.jsx    # Simulation Preview Overlay (presentational)
    │   │   ├── Reconciliation.jsx     # 3 Sektionen: Orders, Balances, Fills + Diskrepanzen
    │   │   ├── Settings.jsx           # Konfigurierbare Parameter (max_order_value_eur)
    │   │   ├── CombinedScore.jsx      # Combined Score: MacroSignal (60%) + Sentiment (40%), Unified Score, Sub-Signal Details
    │   │   ├── LotsTable.css
    │   │   ├── PairingPanel.css
    │   │   ├── Dashboard.css
    │   │   ├── Reconciliation.css
    │   │   ├── Settings.css
    │   │   ├── CombinedScore.css
    │   │   ├── Orderblock.jsx         # Orderblock Dashboard: Analyse, KPI-Cards, Zone-Tabelle, Backtest-Trades, Filter
    │   │   ├── OrderblockChart.jsx    # Candlestick-Chart (lightweight-charts): Zonen-Overlay, Trade-Marker, Volume
    │   │   ├── FillNotification.jsx    # Echtzeit Fill-Benachrichtigungen via WebSocket
    │   │   ├── FillNotification.css
    │   │   └── Orderblock.css
    │   ├── contexts/
    │   │   └── WebSocketContext.jsx    # WebSocket Provider + useLivePrice Hook (Echtzeit-Preis, Order- und Balance-Updates)
    │   ├── utils/
    │   │   └── formatters.js          # Shared: formatNumber, formatEUR, formatBTC, formatPct, formatDate, formatTime
    │   └── hooks/useLivePrice.js      # Binance Ticker Polling (10s, Legacy-Fallback)
    ├── package.json
    └── vite.config.js
```

## Entwicklungskommandos

### Backend
```bash
cd backend
source venv/bin/activate

# Server starten
uvicorn app.main:app --reload

# Tests
pytest
pytest tests/test_pairing.py              # Einzelne Datei
pytest --cov=app tests/                   # Mit Coverage

# Linting
ruff check . && black --check .
black . && ruff check --fix .             # Auto-Fix
```

### Sentiment Backtesting
```bash
cd backend
python scripts/backtest_sentiment.py --days 2000 --symbol BTCUSDT
```

### Orderblock Backtesting
```bash
cd backend
# Single Run
python scripts/backtest_orderblock.py --symbol BTCEUR --interval 4h --months 6

# Parameter-Sweep (Grid Search ueber ATR-Multiplikatoren, Risk:Reward, Timeframes)
python scripts/backtest_orderblock.py --mode sweep --months 12 \
  --sweep-atr-mults 1.5,2.0,2.5,3.0 \
  --sweep-rrs 1.5,2.0,3.0 \
  --csv sweep_results.csv
```

### Frontend
```bash
cd frontend
npm install
npm run dev                               # Dev Server
npm run build                             # Production Build
npm run lint
```

### Datenbank
```bash
cd backend
alembic upgrade head                      # Migrationen ausführen
alembic revision --autogenerate -m "..."  # Neue Migration
alembic downgrade -1                      # Rollback
```

## API-Endpoints (Backend)

| Route | Methode | Beschreibung |
|-------|---------|--------------|
| `/api/portfolio/{user_id}` | GET | Portfolio-State (KPIs, Break-even, P&L) |
| `/api/lots/{user_id}` | GET | Lots mit Filter (status, from_date, to_date) |
| `/api/lots/{user_id}/sync` | POST | Binance Fills importieren |
| `/api/lots/{user_id}/{lot_id}` | GET | Lot-Detail + Allocations |
| `/api/lots/{user_id}/{lot_id}/auto-order` | PATCH | Auto-Order Toggle |
| `/api/orders/{user_id}/lot/{lot_id}/create` | POST | TAKE_PROFIT_LIMIT Sell Order erstellen |
| `/api/orders/{user_id}/list` | GET | Orders filtern (status, lot_id, pairing_id) |
| `/api/orders/{order_id}` | DELETE | Order stornieren |
| `/api/pairing/{user_id}/suggestions` | GET | Auto-Vorschläge (market_price, threshold_pct) |
| `/api/pairing/{user_id}/create` | POST | Pairing persistieren (items[], threshold_pct) |
| `/api/pairing/{user_id}/list` | GET | Pairings filtern (status) |
| `/api/pairing/{user_id}/simulate/{id}` | GET | Simulation durchführen |
| `/api/pairing/{user_id}/{id}/lock` | POST | DRAFT -> LOCKED |
| `/api/pairing/{user_id}/{id}/execute` | POST | LOCKED -> EXECUTED |
| `/api/pairing/{user_id}/{id}` | DELETE | Nur DRAFT löschbar |
| `/api/reconciliation/{user_id}/run` | POST | Vollständige Reconciliation (Orders + Balances + Fills) |
| `/api/reconciliation/{user_id}/orders` | POST | Order-Status mit Binance abgleichen |
| `/api/reconciliation/{user_id}/balances` | POST | Balances vergleichen (Binance vs. Ledger) |
| `/api/reconciliation/{user_id}/fills` | POST | Fills synchronisieren |
| `/api/settings/{user_id}` | GET | User-Settings laden (oder Defaults) |
| `/api/settings/{user_id}` | PUT | User-Settings speichern (upsert) |
| `/api/sentiment/{user_id}/current` | GET | Aktueller Sentiment Score v3 (5 Pillars, Dispersion, Volatility) |
| `/api/combined/{user_id}/score` | GET | Combined Score: MacroSignal (60%) + Sentiment (40%), Unified Score (-100 bis +100) |
| `/api/orderblock/{user_id}/analyze` | POST | Orderblock-Erkennung + Backtest ausfuehren (Symbol, Intervall, Monate, Config) |
| `/api/orderblock/{user_id}/zones` | GET | Erkannte Zonen laden (Filter: symbol, interval, state) |
| `/api/orderblock/{user_id}/zones/{zone_id}` | GET | Einzelne Zone mit vollstaendiger Config |
| `/api/orderblock/{user_id}/zones` | DELETE | Zonen loeschen (symbol + interval) |
| `/api/orderblock/{user_id}/backtest/runs` | GET | Backtest-Historien (Filter: symbol) |
| `/api/orderblock/{user_id}/backtest/runs/{run_id}` | GET | Backtest-Detail mit allen Trades |
| `/api/orderblock/{user_id}/candles` | GET | OHLCV-Kerzen fuer Chart (Zone-basiert oder Zeitfenster) |

## Architektur

### Schichtenmodell
```
API Routes (thin)  →  Services (DB + Binance)  →  Domain (pure, no I/O)
     ↓                       ↓                          ↓
  FastAPI              SQLAlchemy ORM            Dataclasses + Decimal
  Pydantic             python-binance            Deterministische Logik
```

### Domain-Logik (kein I/O, pure Funktionen)

**`domain/portfolio.py`** - `compute_portfolio_from_ledger(events, market_price)`:
- Zentrale Funktion, berechnet alle KPIs aus Ledger-Events
- WAC Break-even, realisierte/unrealisierte P&L, EUR/BTC Bestände

**`domain/lots.py`**:
- `create_trade_lot_from_buy_fill()` - 1 Fill = 1 Lot (Fees in EUR/BTC/BNB)
- `allocate_sell_with_strategy()` - Strategy-Aware Sell Allocation (FIFO/LIFO/HIGHEST_COST)
- `allocate_sell_fifo()` - FIFO Wrapper (Rueckwaertskompatibilitaet)
- `allocate_sell_to_lot()` - Lot-spezifische Allocation + Overflow nach konfigurierbarer Strategie
- `_sort_lots_by_strategy()` - Sortierung nach Strategie (FIFO: created_at asc, LIFO: created_at desc, HIGHEST_COST: break_even desc)

**`domain/pairing.py`**:
- `suggest_pairings(lots, market_price, threshold_pct)` - Heuristik v1.2 (Minimum 2 Lots, einzelne profitable Lots direkt per Sell-Order)
- `simulate_pairing(pairing, market_price, all_lots, fee_pct)` - Deterministische Simulation

**`domain/sentiment.py`** - Sentiment Engine v3 (pure, kein I/O):
- 5 korrelierte Pillars: DMA (42%), F&G (28%), Funding (20%), Taker (18%), Volume (12%)
- `compute_sentiment_v3(pillars, weights)` - Gewichtete Aggregation mit Renormalisierung bei fehlenden Pillars
- `compute_pillar_dispersion(scores)` - Confidence-Faktor (std=0 → 1.0, std≥30 → 0.0)
- `compute_volatility_scaling(daily_returns)` - Regime-Erkennung (HIGH/NORMAL/LOW)
- `compute_piecewise_linear_multiplier(score)` - Stetige Buy-Size-Empfehlung (1.5x Fear → 1.0x Neutral → 0.85x Greed)
- `get_recommendation_v3()` - Finaler Multiplikator: base × dispersion_confidence × volatility_scaling
- `rolling_percentile()`, `score_funding_rate()` - Pillar-Normalisierung
- Dataclasses: `PillarScore`, `DispersionInfo`, `VolatilityScaling`, `SentimentResultV3`, `SentimentRecommendationV3`

**`domain/orderblock.py`** - Orderblock Detection Engine (pure, kein I/O):

Orderblocks sind hochreaktive institutionelle Preiszonen, die durch Marktstruktur-Analyse identifiziert werden. Das Konzept basiert auf der Beobachtung, dass grosse Marktteilnehmer (Smart Money) Positionen in definierten Preisbereichen akkumulieren oder distribuieren. Kehrt der Preis in diese Zonen zurueck, reagiert der Markt haeufig scharf, da dort ungefuellte institutionelle Limit-Orders verbleiben und prognostizierbare Preisreaktionen entstehen.

- **Richtung**: BULLISH = letzte baerische Kerze vor starkem Aufwaertsimpuls (Akkumulationszone, wirkt als Unterstuetzung). BEARISH = letzte bullische Kerze vor starkem Abwaertsimpuls (Distributionszone, wirkt als Widerstand).

**5-Phasen-Validierungspipeline** (eliminiert Fehlsignale durch sequentielle Bestaetigungen):

| Phase | Pruefung | Finanzlogik |
|-------|----------|-------------|
| 1. Formation | Kandidatenkerze identifizieren (baerisch fuer Bullish-OB, bullisch fuer Bearish-OB, keine Dojis) | Institutionelle Positionsbildung hinterlaesst charakteristische Kerzenformationen |
| 2. Displacement | Impulsstärke muss `ATR × atr_multiplier` (Default: 2.0 × 20-Perioden-ATR) ueberschreiten | Starke Preisbewegung = Bestaetigung institutioneller Aktivitaet (Retail erzeugt keine Displacements dieser Groessenordnung) |
| 3. Fair Value Gap (FVG) | 3-Kerzen-Ungleichgewicht innerhalb `impulse_window` (Default: 5 Kerzen): Bullish FVG = `Low(i) > High(i-2)`, Bearish FVG = `High(i) < Low(i-2)` | Preis-Luecke = Markt hat die Zone uebersprungen, es besteht ein Ungleichgewicht zwischen Angebot und Nachfrage |
| 4. Break of Structure (BOS) | Fraktaler Swing-Punkt vor OB-Index muss gebrochen werden (Bullish: Close > letztes Swing-High, Bearish: Close < letztes Swing-Low). Fraktal-Erkennung n=2, Inside-Bars werden uebersprungen | Strukturbruch = Trendwende bestaetigt, die Marktstruktur verschiebt sich zugunsten der OB-Richtung |
| 5. State Management | Initialer Zustand: UNMITIGATED. Bestaetigung bei `max(displacement_idx, fvg_idx, bos_idx)`. Zone erst ab `confirmed_at_index + 1` handelbar | Zeitkonsistenz: Keine Look-Ahead-Bias — Backtesting und Live-Erkennung liefern identische Ergebnisse |

**Conviction Scoring (0-100)** — Vier gleichgewichtete Komponenten (je 25%):

| Komponente | Methodik | Begruendung |
|------------|----------|-------------|
| Volume Percentile (Cont) | `percentile(V, lookback=50)` — robust gegenueber Heavy-Tail-Verteilungen | Handelsvolumina folgen Potenzgesetzen, nicht Normalverteilungen. Z-Scores allein waeren unzuverlaessig |
| Volume Z-Score | `z = (V - mean) / std`, normalisiert auf 0-100 (z=4 → 100) | Erfasst die Abweichung vom Baseline-Volumen als klassisches Standardsignal |
| OFI Divergence (Bouchaud) | Close-Location-Value × Volumen, Vergleich Formation vs. Impuls, Sigmoid-Normalisierung | Institutionelle Akkumulation zeigt geringen Price Impact bei hohem Volumen — der Orderfluss verschiebt sich von Verkauf zu Kauf (oder umgekehrt) |
| Impulse Intensity | `body_ratio × (volume_weight / 3) × 100` — Kerzenkoerper-Staerke kombiniert mit Volumen-Surge | Starker Kerzenkoerper + ueberdurchschnittliches Volumen = hohe Impulsqualitaet |

- Conviction-Stufen: LOW (<35), STANDARD (35-55), HIGH (55-75), INSTITUTIONAL (75+)
- High-Conviction Z-Score Flag: `volume_zscore > zscore_threshold` (Default: 2.0) — separater Filter fuer ungewoehnlich hohes Impulsvolumen

**Impact Efficiency Ratio (Bouchaud Square Root Law)**:
- `IER = participation_rate / normalized_displacement²`
- Hoher IER (>> 1): Viel Volumen, wenig Preisbewegung → institutionelle Akkumulation (Smart Money arbeitet unerkannt)
- Niedriger IER (≈ 1): Volumen proportional zur Preisbewegung → Retail-getrieben oder News-Event

**AlbaTherium-Klassifikation** (strukturelle Kategorisierung nach Swing-Hierarchie):
- EXTREME: Erster/tiefster OB zwischen Major Low und Major High — Ursprung der Primaerbewegung
- DECISIONAL: Juengster OB unter aktuellem Inducement-Level — Wiedereinstieg vor finalem Push
- SMT (Smart Money Trap): Alle OBs zwischen EXTREME und DECISIONAL — potenzielle Fallen fuer Retail-Trader
- UNCLASSIFIED: Ausserhalb der identifizierten Marktstruktur

**Zone State Machine**:
- UNMITIGATED → MITIGATED (Preis beruehrt Zone: `High >= bottom AND Low <= top`, Orderfluss erschoepft)
- UNMITIGATED/MITIGATED → INVALID (Wick-Touch durchbricht Zone: Bullish `Low <= zone_bottom`, Bearish `High >= zone_top`)

- Kernfunktionen: `detect_orderblocks()`, `compute_atr()` (Wilder's Smoothing), `find_swing_points()`, `find_fvgs()`, `compute_volume_zscore()`, `compute_volume_percentile()`, `compute_ofi_divergence()`, `compute_impact_efficiency_ratio()`, `compute_conviction_score()`, `classify_orderblocks()`, `update_zone_states()`
- Dataclasses: `Candle`, `Orderblock`, `OBConfig`, `SwingPoint`, `FairValueGap`, `ConvictionLevel`, `OBDirection`, `OBState`, `OBCategory`

**`domain/orderblock_backtest.py`** - Backtesting Engine (pure, kein I/O):

Simuliert das Handeln an erkannten Orderblock-Zonen nach der **Triple-Barrier-Methode** (Lopez de Prado): Jeder Trade hat drei Ausstiegsbedingungen — Take-Profit, Stop-Loss und maximale Haltedauer.

- **Entry**: Limit-Order am `entry_edge` (erste Beruehrung nach `confirmed_at_index + 1`)
- **Stop**: Wick-Touch am `stop_edge` (konservativer Ansatz — bereits ein Docht genuegt)
- **Target**: `entry ± target_rr × zone_width` (konfigurierbar, Default R:R = 2.0)
- **Time-Exit**: Nach `max_holding_candles` (Default: 200) → EXPIRED (Risikomanagement)
- Trade-Outcomes: HIT (Target erreicht), MISS (Stop erreicht), EXPIRED (Zeitlimit), OPEN (Daten enden)
- Metriken: Hit-Rate (nur HIT+MISS), Penetration Depth (wie tief dringt Preis in Zone ein), Holding Duration, Conviction-Breakdown pro Stufe, Z-Score-Clustering
- Dataclasses: `BacktestTrade`, `BacktestMetrics`, `ConvictionBreakdown`, `ZScoreCluster`, `BacktestResult`

**`services/orderblock_data_service.py`** - Singleton mit Thread-Safe TTL-Cache (1h):
- Binance REST API Klines (oeffentlich, kein API-Key erforderlich): Paginierung (max 1000 Kerzen/Request)
- `fetch_candles(symbol, interval, months)` — Paginierter Abruf + Cache
- `analyze(symbol, interval, months, config)` — Orchestrierung: Fetch → Detect → State → Simulate → Metriken
- Serialisierung: `serialize_zone()`, `serialize_config()`, `serialize_metrics()`, `serialize_trade()`, `serialize_candle_for_chart()`

**`services/orderblock_persistence_service.py`** - Zone CRUD + Backtest-Persistenz:
- `save_detection_result()` — Upsert mit Stale-Cleanup (N+1-Query-Optimierung: Batch-Load existierender Zone-IDs)
- `get_zones()` — Filter nach symbol, interval, state (IDOR-geschuetzt via user_id)
- `save_backtest_result()` — Immutable Snapshot (Config + Metriken + Trades als JSON)
- `get_backtest_runs()` / `get_backtest_run()` — Historie + Detail (IDOR-geschuetzt)

**3-stufige Config-Aufloesung** (Orderblock-Analyse):
1. Request-Parameter (hoechste Prioritaet)
2. User-Settings (`ob_interval`, `ob_atr_multiplier`, `ob_target_rr`, `ob_impulse_window`)
3. OBConfig-Defaults (niedrigste Prioritaet)

**`services/sentiment_data_service.py`** - Singleton mit TTL-Cache:
- Datenquellen: Alternative.me F&G (30min TTL), Binance Klines (5min TTL), OKX Funding Rate (15min TTL)
- 90-Tage Rolling Histories (deque) fuer Percentile-Scoring
- 120-Tage Daily Returns fuer Volatility Scaling
- `_initialize_history()` - Einmalige Population (300 Tage Klines)
- Graceful Degradation: Fehlende Quellen → Score 50, Quality "unavailable"
- Quality-Badges: "live", "cached", "stale" (6× TTL), "unavailable"

### Frontend-Komponenten

**LotsTable.jsx** - Hauptkomponente für Trade-Management:
- Tabelle mit 11 Spalten (Checkbox, Order Nr, Datum, Menge, Kosten, Break-even, Sell Order, P&L, Status)
- Summary-Cards: Kosten offener Positionen, Menge Offen, Erholungspreis (bei negativem Depoterfolg)
- Erholungspreis-KPI: Proportionaler Verkaufspreis bei dem alle Lots gemeinsam das Depot-Minus ausgleichen
  - Formel: `P = (total_qty × marktpreis + |deficit|) / (total_qty × (1 - fee_rate))`
  - Wird nur angezeigt wenn Depoterfolg < 0
- Delegiert an Subkomponenten: LotFilters, OpenOrdersPanel
- Sort: Datum, Break-even (client-side)
- Pairing: Checkbox-Selektion → PairingPanel (inline, aufklappbar)
- Live-P&L Berechnung mit marketPrice prop

**LotFilters.jsx** - Filter-Bar (extrahiert aus LotsTable):
- Order Nr (Text), Status (Select), Closed-Toggle, Datumsbereich, Reset-Button

**OpenOrdersPanel.jsx** - Offene Sell Orders (extrahiert aus LotsTable):
- Tabelle: Status, Preis, Menge, Referenz (Lot/Pairing), Erstellt
- "Unter Markt"-Warnung wenn Sell-Preis <= Marktpreis

**PairingPanel.jsx** - 3-Tab Pairing-UI:
- Tab "Vorschläge": Backend-Heuristik, Threshold-Input, Karten mit Netto-KPIs
- Tab "Manuell": Aus Checkbox-Auswahl, Live-Preview, "Pairing erstellen"
- Tab "Bestehende": Delegiert an PairingExistingTab

**PairingExistingTab.jsx** - Bestehende Pairings (extrahiert aus PairingPanel):
- DRAFT/LOCKED/EXECUTED Lifecycle mit eigenen Mutations (Lock/Unlock/Execute/Delete)
- Filter: Status, "Ausgeführte anzeigen"-Toggle
- Simulation-State + SimulationModal inline

**SimulationModal.jsx** - Simulation Preview (extrahiert aus PairingPanel):
- Presentational Overlay: Marktpreis, BTC, Erlös, Kosten, Fees, P&L, betroffene Lots
- Geplante Binance Order (aggregiert), Max-Value-Warnung

**Dashboard.jsx** - Portfolio-Übersicht:
- 8 KPI-Kacheln: Marktpreis, BTC Bestand, Break-even, Target, Unrealisiert/Realisiert P&L, EUR, Extern

**Reconciliation.jsx** - Datenabgleich Binance vs. Ledger:
- "Vollständige Reconciliation" Button + 3 Einzel-Buttons (Orders, Balances, Fills)
- Balances-Sektion: BTC/EUR Vergleichskarten (Binance vs. Berechnet, Differenz, Toleranz-Badge)
- Orders-Sektion: Sync-Stats + Diskrepanz-Tabelle
- Fills-Sektion: Neue Fills/Lots/Allocations Zähler
- useMutation für alle POST-Endpoints, Query-Invalidierung nach Erfolg

**Settings.jsx** - Konfigurierbare Parameter:
- Formular fuer `max_order_value_eur` (Default: 1000 EUR)
- Sell-Allocation Strategie (FIFO / LIFO / Hoechste Kosten) als Button-Group
- useQuery + useMutation fuer GET/PUT Settings-API

**CombinedScore.jsx** - Combined Score Dashboard (ersetzt eigenstaendige MacroSignal- und Sentiment-Seiten):
- Vereint MacroSignal (Richtung, 60%) und Sentiment (Sizing, 40%) zu Unified Score (-100 bis +100)
- Hero Action Banner: Handlungsempfehlung (STARK LONG/LONG/NEUTRAL/SHORT/STARK SHORT) + Size-Multiplikator
- Unified Score Bar: Visueller Indikator mit Threshold-Markierungen (-60/-30/-10/+10/+30/+60)
- Conflict Alert: Warnung bei divergierenden Sub-Signalen (Makro vs. Sentiment)
- MacroSignal Sub-Card: Recommendation Badge, Raw Score, Faktoren-Anzahl, Intervall, aufklappbare Faktor-Details mit Score-Bars
- Sentiment Sub-Card: Label Badge, Composite Score, Buy-Size Multiplikator, Pillar-Anzahl, aufklappbare Pillar-Details mit Progress-Bars + Quality-Badges
- Sentiment-Details: Pillar Agreement (Dispersion), Volatility Regime (HIGH/NORMAL/LOW mit Scaling)
- Quality-System: Gesamtqualitaet (full/partial/degraded) + Confidence-Prozent + Einschraenkungshinweis
- Intervall aus User-Settings (`macro_signal_interval`), Refetch 30s/45s/60s je nach Intervall
- TanStack Query mit Settings-abhaengigem Polling

**Orderblock.jsx** - Orderblock Detection Dashboard:
- Action-Bar: Analyse starten (POST), Zonen loeschen, Intervall-/Lookback-Auswahl (1h/4h/1d, 3-24 Monate)
- KPI-Cards: Gesamtzonen, Hit-Rate, High-Conviction-Anzahl, Durchschnittlicher Conviction Score
- Filter-Bar: Zone-State (UNMITIGATED/MITIGATED/INVALID), Conviction-Level, AlbaTherium-Kategorie
- Charts (Recharts): Zone-State-Verteilung (Stacked Bar), Conviction-Breakdown (Grouped Bar: Hits/Misses/Expired pro Stufe)
- Zone-Tabelle (sortierbar): Direction, State, Conviction, Category, Score, Zone-Range, Formation-Zeitpunkt
- Trade-Tabelle (wenn Backtest vorhanden): Entry/Exit, Outcome, Penetration Depth, Holding Duration, Conviction Score
- Explainer: Aufklappbare Erklaerung der 5-Phasen-Validierung und Conviction-Komponenten
- State: selectedInterval, months, zoneStateFilter, convictionFilter, categoryFilter, selectedZone, Sorting

**OrderblockChart.jsx** - Candlestick-Chart (lightweight-charts / TradingView):
- OHLCV Candlestick-Serie (bullisch gruen, baerisch rot) + Volume-Histogramm (semi-transparent, farbangepasst)
- Price Lines: Zone-Grenzen (top/bottom), Equilibrium, Entry/Stop Edge, Target-Level
- Marker: Kerzenindizes, FVG-Highlight, Swing-Punkte
- Crosshair: Interaktives Preis-/Zeittracking
- Datenfluss: Zone-Selektion → Kerzen-Fetch (±Kontext um `formed_at`), Trade-Selektion → Kerzen-Fetch (Entry bis Exit ± Kontext)
- UTC-Zeitzonenkonvertierung fuer lokale Anzeige

### Datenmodell (Kern-Tabellen)

| Tabelle | Beschreibung |
|---------|--------------|
| `ledger_events` | Append-only Event-Log (TRADE_FILL, FEE, DEPOSIT, WITHDRAWAL, EXTERNAL_CASHFLOW, ADJUSTMENT), inkl. `fee_eur_value` (vorberechneter EUR-Wert der Fee fuer BNB/andere Assets) |
| `trade_lots` | BTC-Positionen (1 pro Buy-Fill): qty_initial, qty_open, cost_eur, break_even, status, auto_order |
| `sell_allocations` | FIFO Zuordnung: sell_fill_id, lot_id, qty_allocated, realized_pnl_eur |
| `orders` | Order-Tracking: client_order_id, binance_order_id, price, stop_price, linked_lot_id, linked_pairing_id |
| `pairings` | Virtuelle Bündelung: threshold_pct, status (DRAFT/LOCKED/EXECUTED) |
| `pairing_items` | N:M Pairing ↔ Lot: qty_btc, cost_eur (unterstützt Teilmengen) |
| `user_settings` | Konfigurierbare Parameter pro User: max_order_value_eur, sell_allocation_strategy (FIFO/LIFO/HIGHEST_COST), ob_interval, ob_atr_multiplier, ob_target_rr, ob_impulse_window |
| `orderblock_zones` | Erkannte Preiszonen: direction, state, conviction, zone_top/bottom, equilibrium, entry/stop_edge, formed/confirmed_at, volume_zscore, volume_weight, volume_percentile, ofi_divergence, impact_efficiency_ratio, conviction_score, is_high_conviction_zscore, category, config_json. Indiziert nach (user_id, symbol, interval), (user_id, state), (formed_at) |
| `backtest_runs` | Immutable Backtest-Snapshots: symbol, interval, data_start/end, candle_count, total_zones/trades, hits/misses/expired, hit_rate, avg_penetration_depth, avg_holding_duration, high_conviction_count/hit_rate, config_json, metrics_json, trades_json. Indiziert nach (user_id, symbol) |

### Kritische Invarianten

1. Ledger ist **append-only** - Korrekturen nur via ADJUSTMENT Events
2. **Decimal überall** - niemals float für Geld/Preise. API-Transport als String (`"1234.56"` statt `1234.56`) um IEEE 754 Praezisionsverlust zu vermeiden
3. **1 Fill = 1 Lot** - deterministische Lot-Bildung, 1:1 Auditierbarkeit
4. **Sell Allocation Strategy** - konfigurierbar (FIFO/LIFO/HIGHEST_COST), deterministisch pro Strategie. Lot-spezifische und Pairing-spezifische Allocations ueberschreiben die Default-Strategie. **Abort-on-Error**: Sync bricht Sell-Allocation-Schleife bei Fehler ab — weitermachen wuerde FIFO-Invariante verletzen, da nachfolgende Sells auf falschen Lots allokiert wuerden
5. **Idempotente Orders** - `clientOrderId` Format: `{userId}_{lotId}_{targetPrice}_{qty}_{version}`
6. **Simulation vor Execution** - Pairing-Ausführung erzwingt vorherige Simulation
7. Pairing-Lifecycle: **DRAFT → LOCKED → EXECUTED** (nur DRAFT löschbar)
8. Externe Cashflows beeinflussen **NICHT** die BTC-Kostenbasis
9. **TAKE_PROFIT_LIMIT** - Alle Sell Orders als Stop-Limit (stopPrice = price = targetPrice)
10. **Max Order-Wert** - Order-Erstellung abgelehnt wenn `qty * price > max_order_value_eur` (konfigurierbar via Settings)
11. **Test-Isolation** - Tests verwenden `TEST_BINANCE_API_KEY` + Testnet, nie Produktions-Keys
12. **Sentiment Scoring** - Korrelationsbasierte Gewichte (nicht gleich), Dispersion als Confidence, Volatility als Scaling - stetige piecewise-linear Multiplikatoren (keine Buckets/Cliff-Effekte)
13. **Fee-Konvertierung** - BNB/andere Fees werden zum historischen Preis (Binance Klines, 1min) zum Fill-Zeitpunkt umgerechnet. `fee_eur_value` wird auf LedgerEvent persistiert. Fallback: aktueller Preis → Skip. Portfolio und Lots konsistent.
14. **Orderblock Zeitkonsistenz** - Zonen erst ab `confirmed_at_index + 1` handelbar. Gleiche Kerzen + gleiche Config → identische Zonen + Trades + Metriken. Keine Look-Ahead-Bias in Detection oder Backtesting.
15. **Orderblock 5-Phasen-Pflicht** - Jede Zone muss alle 5 Validierungsphasen (Formation, Displacement, FVG, BOS, State) bestehen. Kein Ueberspringen einzelner Phasen moeglich.
16. **Conviction Scoring** - Vier gleichgewichtete Komponenten (Volume Percentile, Z-Score, OFI Divergence, Impulse Intensity). Percentile-basiert statt Z-Score-only wegen Heavy-Tail-Verteilung der Volumina (Cont).
17. **Triple Barrier** - Backtesting mit drei Ausstiegsbedingungen (Target, Stop, Zeit). Time-Exit nach `max_holding_candles` verhindert unbegrenzte Haltezeiten.
18. **Orderblock Config-Hierarchie** - Request > User-Settings > OBConfig-Defaults. Kein implizites Override — jede Stufe ist transparent nachvollziehbar.
19. **Error Sanitization** - API-Responses enthalten niemals Stacktraces oder interne Fehlermeldungen. Alle unerwarteten Fehler → `logger.exception()` (server-seitig) + generisches `"Interner Serverfehler"` (client-seitig).
20. **Pairing Race Protection** - `create_pairing()` und `lock_pairing()` verwenden `with_for_update()` Row-Level Locks. Verhindert, dass konkurrierende Requests dasselbe Lot doppelt allokieren.

## Styling-Konventionen (Frontend)

- **Kein UI-Framework** - Plain CSS, component-scoped (`Component.css`)
- **Farbschema**:
  - Navbar: Purple-Gradient (`#667eea` → `#764ba2`)
  - Profit: Grün `#16a34a`, Loss: Rot `#dc2626`
  - Pairing/Akzent: Indigo `#6366f1`
  - Reconciliation: Sky-Blue `#0ea5e9`
  - Combined Score: Action-Color dynamisch (Gruen/Slate/Rot je nach Score), Sub-Signal Cards mit Detail-Toggles
  - Orderblock: Amber `#d97706` (Bullish-Zonen: Gruen `#16a34a`, Bearish-Zonen: Rot `#dc2626`, Score-Gradient: Slate→Blue→Amber→Purple)
  - Binance-Sync: Orange `#f7931a`
  - Neutrals: Slate-Palette (`#f8fafc`, `#e2e8f0`, `#64748b`, `#1e293b`)
- **Patterns**: Summary-Cards, Filter-Groups mit Labels, Toggle-Switches, Status-Badges, Sort-Icons

## Testing

**Backend (18 Testdateien):**
- `test_portfolio_breakeven.py` - WAC, Fees, Partial Sells, BNB-Fee via fee_eur_value
- `test_lots_fifo.py` - FIFO Allocation Deterministik
- `test_lots_strategies.py` - LIFO, HIGHEST_COST, Strategy-Routing, Overflow-Strategien (18 Tests)
- `test_lots_lot_specific.py` - Lot-spezifische Targets
- `test_lot_fee_handling.py` - Fee-Berechnung (EUR/BTC/BNB)
- `test_pairing.py` - Pairing-Heuristik, Thresholds
- `test_pairing_execution.py` - Simulation, Affected Lots
- `test_order_lifecycle.py` - Create → Fill → Closed
- `test_sync_lots.py` - Binance Sync
- `test_reconciliation.py` - Balance-Abgleich
- `test_csv_import.py` - CSV Import Validierung
- `test_timezone_handling.py` - Timezone Edge Cases
- `test_macro_signal.py` - Makro-Signal Berechnung
- `test_historical_price.py` - Historische Fee-Konvertierung: BinanceService.get_historical_price(), Per-Fill Rates, Minuten-Cache, Fallback, _compute_fee_eur_value (13 Tests)
- `test_sentiment_v3.py` - Sentiment v3: Pillar Dispersion, Funding Scoring, Piecewise Multiplier, Volatility Scaling, Recommendation (45+ Tests)
- `test_orderblock_detection.py` - Orderblock Detection: ATR (Wilder's Smoothing), Swing-Fraktal-Erkennung, FVG-Detection, Volume Z-Score/Percentile, OFI Divergence, Impact Efficiency Ratio, Conviction Score, Detection Pipeline, State Transitions, AlbaTherium-Klassifikation
- `test_orderblock_backtest.py` - Orderblock Backtesting: Trade-Outcome-Simulation (HIT/MISS/EXPIRED/OPEN), Penetration Depth, Hit-Rate-Metriken, Conviction-Breakdown, Z-Score-Clustering
- `test_orderblock_service.py` - Orderblock Services: Kline-Paginierung, Cache Hit/Miss/TTL, Serialisierung (Zone/Config/Metriken/Trade), Persistence CRUD, Detection+Backtest Integration

**Test-Konfiguration (`tests/conftest.py`):**
- Alle Tests verwenden automatisch `TEST_BINANCE_API_KEY` statt Produktions-Keys
- `BINANCE_TESTNET=true` wird gesetzt (Testnet-Endpoint)
- Session-scoped, autouse Fixture

**Frontend:** Noch keine automatisierten Tests (geplant: Vitest)

## Sicherheit

- **API-Key Authentication** - Alle API-Routen geschuetzt via `X-API-Key` Header, konfigurierbar via `API_KEY` in `.env`
- **Niemals Secrets committen** - `.env` ist in `.gitignore`
- API-Keys verschlüsselt oder im Secret Manager
- Environment Variables für Konfiguration
- **Error Message Sanitization** - Alle API-Routes geben generische Fehlermeldungen (`"Interner Serverfehler"`) zurueck, keine Stacktraces oder interne Details an Client. Fehler werden server-seitig via `logger.exception()` geloggt.
- **Input Validation** - `market_price` Parameter wird auf NaN, Inf und negative Werte geprueft (HTTP 400). Decimal-Werte werden als String transportiert um Praezisionsverlust zu vermeiden.
- **Race Condition Protection** - Pairing-Service verwendet Row-Level Locking (`with_for_update()`) bei Create und Lock, verhindert konkurrierende Pairing-Erstellungen auf denselben Lots.
- **Test-Keys getrennt** - `TEST_BINANCE_API_KEY` in `.env`, automatisch via `conftest.py` verwendet
- **Max Order-Wert** - Konfigurierbares Limit pro User (Default: 1000 EUR, via Settings-Seite)
- **Transaction-Safety** - SQLAlchemy Sessions mit Auto-Commit/Rollback (`yield`-Pattern in `get_db()`)
- **Sentiment EU-Compliance** - OKX Funding Rate statt Binance Futures (MiCA-konform), alle Quellen oeffentlich (keine Extra-Credentials)

---

# Vollständige Spezifikation

## Konzeptionsdokument – BTC/EUR Cashflow-Management & Automation App (Binance Spot)
**Version:** 1.0
**Prinzip:** Ledger-first, deterministisch, auditierbar, automatisierbar.

---

## 1. Projektübersicht

Diese App liefert:
- **Transparenz** über Euro-Cashflow (intern auf Binance und extern via Bank/Off-Exchange).
- **Rentabilitätssteuerung** auf Portfolio- und Trade-Ebene.
- **Automatisierte Gewinnmitnahmen** über Binance Orders (Limit / optional Stop-Limit).
- **Virtuelle Trade-Verrechnung (Pairing)** zur Liquiditätsfreisetzung bei netto erreichter Zielmarge.

Nicht Ziel in v1:
- Futures/Margin/Derivate
- Multi-Exchange
- Steuerreporting nach nationalem Recht (nur Export/CSV als späteres Add-on)

---

## 2. Kernfunktionen

### 2.1 Break-Even-Analyse & Cashflow-Tracking

#### 2.1.1 Grundprinzip: Ledger statt "Saldo raten"
Alle Berechnungen basieren auf einem **append-only Ledger** (Ereignisstrom). Keine stillen Korrekturen, keine "Excel-Logik" im UI.

**Ledger-Event-Typen:**
- `TRADE_FILL` (Binance Ausführung)
- `FEE` (falls nicht im Fill enthalten)
- `DEPOSIT` / `WITHDRAWAL` (EUR/BTC, Binance)
- `EXTERNAL_CASHFLOW` (Bank rein/raus, manuell oder später via Import/API)
- `ADJUSTMENT` (Admin-Korrektur, immer als neues Event)

#### 2.1.2 Cashflow-Definitionen (EUR-Sicht)

**(A) Trading-Only (operativ)** - Binance Ledger-Events → Orders, Break-even, Bestände
**(B) Full Cashflow (wirtschaftlich)** - Binance + externe Cashflows → Gesamtperformance

KPIs: EUR verfügbar, BTC Bestand + Marktwert, External Net EUR, Realisierte/Unrealisierte P&L

#### 2.1.3 Break-even Berechnung (Portfolio)
- **Weighted Average Cost (WAC)** auf Portfolio-Ebene
- `portfolio_break_even = cost_basis_eur / btc_qty`
- Externe Cashflows verändern NICHT die BTC-Kostenbasis

#### 2.1.4 Ziel-Marge & Zielverkaufspreise
- `target_price = break_even * (1 + target_margin_pct) * (1 + fee_buffer_pct)`
- Kann global oder pro Lot gesetzt werden

### 2.2 Trade-Ebene-Management

#### 2.2.2 TradeLot-Bildung: 1 Fill = 1 Lot
- Jeder Buy-Fill erzeugt genau einen TradeLot
- Partial Fills → mehrere Lots (UI mit Gruppierung/Filter)

#### 2.2.3 TradeLot-Kennzahlen
- `qty_btc_initial`, `qty_btc_open`, `cost_eur`, `break_even`
- `unrealized_pnl_eur`, `unrealized_pnl_pct`
- Status: `OPEN` / `PARTIAL_CLOSED` / `CLOSED`

#### 2.2.4 Sell-Allocation: FIFO
- Älteste offene Lots zuerst schließen
- Allocation wird persistiert: `sell_fill_id`, `trade_lot_id`, `qty_allocated`, `realized_pnl_eur`

### 2.3 Virtuelles Pairing

#### 2.3.2 Pairing-Grundmodell
Ein Pairing = Set von TradeLots (ggf. Teilmengen).
- `net_pnl_pct >= threshold_pct` → verkaufsfähig

#### 2.3.3 Algorithmus (Heuristik v1.2)
1. Sortiere: Gewinner absteigend, Verlierer aufsteigend nach P&L%
2. Pro Gewinner: Verlierer hinzufuegen bis Threshold erreicht
3. Minimum 2 Lots pro Pairing (einzelne profitable Lots direkt per Sell-Order verkaufbar)
4. Ausgabe: Pairing-Vorschlaege mit Netto-Effekt

#### 2.3.4 Simulation (Pflicht vor Ausführung)
Zeigt: betroffene Lots, erwartete P&L, Fees, verbleibende Bestände

#### 2.3.5 Execution: Order pro Lot
- Jede Lot-Schließung als separate Order (saubere Referenzierung)

### 2.4 Automatisierung (Binance Integration)

- **Order-Erstellung**: TAKE_PROFIT_LIMIT Sell (stopPrice = price = targetPrice)
- **Max Order-Wert**: Konfigurierbar via Settings (Default: 1000 EUR), Validierung vor Binance API Call
- **Sync**: Polling + inkrementell (v1), WebSocket (v2)
- **Idempotenz**: Deterministische `clientOrderId`
- **Safety**: Rate-Limit Backoff, Balance-Check, Auto-Order Toggle, Max-Order-Value-Check

---

## 3. UI Design-Vorgaben

### 3.1 Dashboard
8 KPI-Kacheln: EUR, BTC, Break-even, Target, Unrealisierte/Realisierte P&L, Externe Cashflows

### 3.2 Trade-Cockpit (LotsTable)
- Tabelle mit Checkbox (Pairing), Order Nr, Datum, Menge, Kosten, Break-even, Sell Order, P&L, Status
- Filter: Order Nr, Status, Datumsbereich, Closed-Toggle
- Pairing-Action-Bar + aufklappbares PairingPanel

### 3.3 Pairing-Screen (PairingPanel, inline)
- 3 Tabs: Vorschläge (auto) | Manuell (Checkbox-Auswahl) | Bestehende Pairings
- Simulation-Overlay: Modal mit KPIs, betroffenen Lots, verbleibendem Portfolio
- Lifecycle: DRAFT → Simulation → LOCKED → Simulation → EXECUTED

### 3.4 Reconciliation-Screen
- "Vollständige Reconciliation" Button + 3 Einzel-Buttons (Orders, Balances, Fills)
- Balances: BTC/EUR Vergleichskarten (Binance vs. Berechnet) mit Toleranz-Badge
- Orders: Sync-Stats + Diskrepanz-Tabelle
- Fills: Neue Fills/Lots/Allocations Zähler
- Sky-Blue Akzentfarbe (`#0ea5e9`)

### 3.5 Settings-Screen
- Formular für max_order_value_eur (Default: 1000 EUR)
- Orderblock-Parameter: Intervall, ATR-Multiplikator, Target R:R, Impulse Window
- Erweiterbar für zukünftige Settings

### 3.6 Combined Score-Screen (ersetzt eigenstaendige Makro-Signal- und Sentiment-Seiten)
- Hero Action Banner: Handlungsempfehlung + Size-Multiplikator + Unified Score Bar (-100 bis +100)
- Conflict Alert bei divergierenden Sub-Signalen
- 2 Sub-Signal Cards (MacroSignal 60%, Sentiment 40%) mit aufklappbaren Details
- Quality-Badge + Confidence-Anzeige + Intervall-Badge aus Settings
- Dynamische Action-Colors (Gruen/Slate/Rot)

### 3.7 Orderblock-Screen
- Action-Bar: Analyse starten, Zonen loeschen, Intervall-/Lookback-Auswahl
- KPI-Cards: Gesamtzonen, Hit-Rate, High-Conviction-Anzahl, Avg Score
- Filter: State, Conviction-Level, AlbaTherium-Kategorie
- Charts: Zone-State-Verteilung, Conviction-Breakdown (Hits/Misses/Expired)
- Zone-Tabelle: Sortierbar, klickbar → Candlestick-Chart mit Zonen-Overlay
- Trade-Tabelle: Backtest-Trades mit Entry/Exit, Outcome, Penetration Depth
- Candlestick-Chart (lightweight-charts): OHLCV, Volume, Zone-Grenzen, Trade-Marker
- Amber Akzentfarbe (`#d97706`)

---

### 2.5 Sentiment Engine (v3)

Krypto-spezifische Stimmungsanalyse, komplementaer zum MacroSignal (Makro-Richtung ≠ Sentiment-Sizing).

**5 Pillars (korrelationsbasierte Gewichte):**
| Pillar | Gewicht | Quelle | Beschreibung |
|--------|---------|--------|-------------|
| Trend-Deviation (DMA) | 42% | Binance Klines | Price Distance to 50-DMA + 200-DMA Regime-Filter |
| Fear & Greed Index | 28% | alternative.me | Emotional Sentiment (0-100) |
| Funding Rate | 20% | OKX Public API | Derivate-Hitze (EU-kompatibel, kein Binance Futures) |
| Taker Buy/Sell Ratio | 18% | Binance Klines | Orderflow-Indikator (7d avg) |
| Volume-Momentum | 12% | Binance Klines | Volume Ratio vs. 20d-Avg, richtungsangepasst |

**Scoring-Modell:**
- Rolling Percentile (90-Tage Historie) statt fixer Schwellwerte
- Pillar Dispersion als Confidence: std=0 → 1.0, std≥30 → 0.0 (lineare Daempfung)
- Volatility Scaling: HIGH (vol_ratio>1.5, komprimiert), NORMAL, LOW (vol_ratio<0.7, expandiert)
- Piecewise-Linear Multiplikator: 1.5x (Extreme Fear) → 1.0x (Neutral 40-60) → 0.85x (Extreme Greed)
- Finaler Multiplikator: base × dispersion_confidence × volatility_scaling

**Abgrenzung MacroSignal vs. SentimentEngine (Backend-Module, im Frontend vereint via Combined Score):**
- MacroSignal: Kurzfristige Richtung (1m/5m/15m), Score -2 bis +2
- SentimentEngine: Mittelfristiges Position-Sizing (taeglich/rollierend), Score 0-100
- Combined Score: Unified Score (-100 bis +100), Gewichtung Makro 60% + Sentiment 40%

---

### 2.6 Orderblock Detection Engine

Institutionelle Preiszonen-Erkennung fuer die Identifikation hochreaktiver Unterstuetzungs- und Widerstandsbereiche. Orderblocks repraesentieren Preiszonen, in denen institutionelle Marktteilnehmer grosse Positionen akkumuliert oder distribuiert haben. Die Engine kombiniert klassische Marktstrukturanalyse mit quantitativen Methoden der Finanzmarkt-Mikrostrukturforschung.

**Abgrenzung zu anderen Modulen:**
- **MacroSignal**: Kurzfristiges Richtungssignal (1-15 Minuten) — "Wohin bewegt sich der Markt?"
- **Sentiment Engine**: Mittelfristiges Position-Sizing (taeglich) — "Wie gross sollte meine Position sein?"
- **Orderblock Engine**: Praeziselevel-Identifikation (Stunden bis Tage) — "Bei welchem Preis reagiert der Markt?"

Die drei Module sind komplementaer: MacroSignal bestimmt die Richtung, Sentiment die Groesse, Orderblocks den optimalen Einstiegspreis. MacroSignal und Sentiment werden im Frontend ueber den Combined Score vereint dargestellt.

#### 2.6.1 Detection: 5-Phasen-Validierung

Institutionelle Preiszonen werden durch eine 5-stufige Validierungspipeline identifiziert:

1. **Formation**: Identifikation der Kandidatenkerze — letzte Gegenkerze vor dem Impuls
2. **Displacement**: Impulsmessung via ATR-Multiple — bestaetigt institutionelle Staerke
3. **Fair Value Gap**: 3-Kerzen-Ungleichgewicht — bestaetigt Angebot/Nachfrage-Imbalance
4. **Break of Structure**: Fraktaler Swing-Bruch — bestaetigt Trendwende
5. **State Management**: Zeitkonsistente Zonenaktivierung — verhindert Look-Ahead-Bias

Jede Phase eliminiert falsch-positive Signale. Nur Zonen, die alle 5 Phasen bestehen, werden als handelbar markiert.

#### 2.6.2 Conviction Scoring (Cont/Bouchaud)

Jede Zone erhaelt einen quantitativen Conviction Score (0-100) aus vier Komponenten:

- **Volume Percentile (Cont)**: Heavy-Tail-robuste Quantifizierung (Volumina folgen Potenzgesetzen, nicht Gaussverteilungen)
- **Volume Z-Score**: Klassische Abweichung vom Baseline-Volumen
- **OFI Divergence (Bouchaud)**: Orderfluss-Verschiebung — institutionelle Akkumulation zeigt geringen Price Impact bei hohem Volumen
- **Impulse Intensity**: Kerzenkoerper-Staerke kombiniert mit Volumen-Surge

Zusaetzlich: **Impact Efficiency Ratio** (Bouchaud Square Root Law) misst das Verhaeltnis von Volumen zu Preisbewegung — hoher IER deutet auf institutionelle Aktivitaet hin.

#### 2.6.3 AlbaTherium-Klassifikation

Strukturelle Einordnung jeder Zone im uebergeordneten Marktkontext:
- **EXTREME**: Ursprung der Primaerbewegung (tiefster OB zwischen Major Low/High)
- **DECISIONAL**: Wiedereinstiegspunkt vor finalem Push
- **SMT**: Smart Money Trap — potenzielle Retail-Falle zwischen EXTREME und DECISIONAL
- **UNCLASSIFIED**: Ausserhalb identifizierter Marktstruktur

#### 2.6.4 Backtesting (Triple Barrier, Lopez de Prado)

Jede erkannte Zone wird mit der Triple-Barrier-Methode simuliert:
- **Take-Profit**: Target-Preis bei `entry ± target_rr × zone_width`
- **Stop-Loss**: Wick-Touch am Stop-Edge (konservativ)
- **Time-Exit**: Maximale Haltedauer (`max_holding_candles`, Default: 200)

Metriken: Hit-Rate, Penetration Depth, Holding Duration, Conviction-Breakdown pro Stufe, Z-Score-Clustering.

#### 2.6.5 Konfigurierbare Parameter

| Parameter | Default | Beschreibung |
|-----------|---------|--------------|
| `atr_length` | 20 | Perioden fuer ATR-Berechnung (Wilder's Smoothing) |
| `atr_multiplier` | 2.0 | Displacement-Schwelle als Vielfaches der ATR |
| `fvg_window` | 3 | Kerzen fuer Fair Value Gap Erkennung |
| `swing_fractal_n` | 2 | Kerzen links/rechts fuer Fraktal-Swing-Erkennung |
| `target_rr` | 2.0 | Risk:Reward-Verhaeltnis fuer Backtesting |
| `zscore_lookback` | 50 | Kerzen fuer Volume-Statistiken |
| `zscore_threshold` | 2.0 | Z-Score-Schwelle fuer High-Conviction-Flag |
| `max_holding_candles` | 200 | Triple-Barrier Time-Exit (0 = deaktiviert) |
| `impulse_window` | 5 | Kerzen fuer Impulsphase nach Formation |

Persistierbar pro User in Settings (`ob_interval`, `ob_atr_multiplier`, `ob_target_rr`, `ob_impulse_window`).

---

## 4. Offene Punkte (priorisierte Roadmap)

| Prio | Item | Bewertung | Abhaengigkeiten |
|------|------|-----------|-----------------|
| 1 | **Auto-Order Automation** (Trigger-basiert) | **HOCH** — Groesster operativer Hebel. Trigger-System ("Sell bei Break-even + X%") reduziert manuellen Aufwand massiv. Kernfeature fuer Automatisierungsgrad. | Hardening (Prio 3) vor Produktiveinsatz |
| 2 | **Sentiment History Persistierung** | **MITTEL** — `SentimentHistoryDB` Tabelle + `/api/sentiment/{user_id}/history` Endpoint. Periodische Snapshots fuer Trendanalyse und Combined-Score-Backtesting. | — |
| 3 | **Hardening** (Monitoring, Alerting, Rate-Limit) | **MITTEL** — Health-Checks, Binance 429-Handling, Alerting bei Sync-Fehlern / Balance-Diskrepanzen. Notwendig vor produktivem Auto-Order-Einsatz. | — |
| 4 | **Frontend-Tests** (Vitest) | **MITTEL** — 18 Backend-Testdateien, null Frontend-Tests. Regressionsrisiko steigt. Kritische Flows zuerst: Pairing-Lifecycle, Lot-Filter, Formatter-Utils. | — |
| 5 | **Aggregierte Pairing-Orders** (v1.1+) | **NIEDRIG-MITTEL** — Separate Order pro Lot → aggregierte Order. Spart Fees, aber komplex (Teilausfuehrungen, Referenzierung). Erst relevant bei hoher Lot-Anzahl. | — |
| 6 | **Social Sentiment** (Twitter/X, Reddit) | **NIEDRIG** — LunarCrush/Santiment. Marginaler Mehrwert bei hohen API-Kosten und Noise. 5-Pillar Engine v3 bereits robust. | Combined Score (Prio 2) stabil |
| 7 | **Echte On-Chain-Daten** (Glassnode/CryptoQuant) | **NIEDRIG** — APIs teuer (~$39/Monat+), Mehrwert fuer Spot-Trading begrenzt. Aktuelle Pillars decken wichtigste Signale ab. | Combined Score (Prio 2) stabil |


## 5. Akzeptanzkriterien
- Break-even und P&L reproduzierbar aus Ledger
- Lots und Sell-Allocations deterministisch (FIFO)
- Pairing liefert Simulation vor Execution
- Auto-Order erzeugt keine Doppelorders (Idempotenz via clientOrderId)
- UI bedienbar bei hoher Lot-Anzahl (Gruppierung/Filter)
- Sentiment Score reproduzierbar aus gleichen Rohdaten (deterministische Domain-Logik)
- Sentiment Graceful Degradation: System funktioniert mit 1-5 aktiven Pillars
- Sentiment EU-kompatibel: Keine geo-blockierten APIs (OKX statt Binance Futures)
- Orderblock-Erkennung deterministisch: Gleiche Kerzen + gleiche Config → identische Zonen und Metriken
- Orderblock-Backtesting zeitkonsistent: Keine Look-Ahead-Bias (Entry erst ab confirmed_at_index + 1)
- Conviction Score reproduzierbar aus gleichen Volumen-/Preis-Daten (pure Domain-Logik)
- AlbaTherium-Klassifikation konsistent mit identifizierter Swing-Hierarchie
