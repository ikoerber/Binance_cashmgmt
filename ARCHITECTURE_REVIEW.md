# Architektur-Review: BTC/EUR Cashflow-Management App

**Datum:** 2026-02-18
**Reviewer:** Claude Opus 4.6 (Software-Architektur-Perspektive)

## Gesamtbewertung: Solide Architektur mit gezieltem Verbesserungspotenzial

Das Projekt zeigt eine **durchdachte, schichtensaubere Architektur** mit klarer Trennung von Domain-, Service- und API-Schicht. Fuer ein Projekt dieser Groesse und Komplexitaet ist die Codequalitaet ueberdurchschnittlich. Nachfolgend die Ergebnisse nach Schicht.

---

## 1. Domain Layer — Exzellent

**Staerken:**
- **Strikt pure**: Kein einziger Import von `db`, `services` oder `api` in der gesamten Domain-Schicht. Null I/O-Leaks.
- **Keine zirkulaeren Abhaengigkeiten**: Dependency-Graph ist strikt azyklisch (`models` <- alles andere, `orderblock` <- `orderblock_backtest`)
- **Decimal konsequent**: Geldbetraege/Preise durchgehend als `Decimal`, nur in `macro_signal.py:335-337` wird `float()` fuer die Serialisierung verwendet (akzeptabel, da es sich um Signal-Scores handelt, nicht um Geldbetraege)
- **Gute Validierung**: `lots.py` validiert Preconditions frueh (`raise ValueError` fuer falsche Event-Typen/Sides)
- **Saubere Dataclass-Modellierung** in `domain/models.py`
- **Division-by-Zero**: Alle 6 identifizierten Stellen sind korrekt abgesichert
- **Deterministische Logik**: Kein Randomness, kein Time-Dependency — gleiche Eingabe ergibt immer gleiches Ergebnis

**Beobachtungen:**
- ~~`orderblock.py` ist mit **1397 Zeilen** die groesste Domain-Datei~~ → **Behoben (P2.9)**: Aufgeteilt in Package `domain/orderblock/` mit 6 Sub-Modulen (`models.py`, `scoring.py`, `detection.py`, `classification.py`, `confluence.py`, `parsing.py`) + `__init__.py` Re-Exports fuer volle Backward-Kompatibilitaet
- `sentiment.py` hat **1048 Zeilen** — aehnliche Ueberlegung moeglich. Pillar-Scoring-Logik wird 5x wiederholt (DRY-Verbesserung durch Pillar-Processor-Loop)
- Fehlende Invariant-Validierung: `qty_btc_open <= qty_btc_initial` wird nicht explizit geprueft (durch Logik verhindert, aber nicht enforced)
- **Neu: `domain/orders.py`** — Pure Order-Parameter-Berechnung (`compute_pairing_order_params()`) aus Service-Layer extrahiert

**Bewertung: A (9.1/10)**

---

## 2. Service Layer — Gut (mit identifizierten Risiken)

**Staerken:**
- Services orchestrieren korrekt Domain-Logik + DB/API-Zugriffe
- **Transaction Management**: Konsistentes `db.flush()`-Pattern, FIFO Abort-on-Error in `sync_service.py` schuetzt Dateninvarianten
- **Thread-Safety**: Alle Singletons (`SentimentDataService`, `OrderblockDataService`, `MacroDataService`, `BinancePublicClient`) verwenden korrekte Double-Checked-Locking-Patterns
- **Binance-Abstraktion**: Saubere Trennung authenticated vs. public Client, Retry-Logik mit Exponential Backoff, korrekte Paginierung
- **Row-Level Locking**: In `pairing_service.py` korrekt implementiert (`with_for_update()`)

**Risiken:**

| Risiko | Schwere | Ort | Empfehlung | Status |
|--------|---------|-----|------------|--------|
| ~~**Zirkulaere Abhaengigkeit** `order_service` <-> `pairing_service`~~ | Mittel | Lazy Imports in beiden Richtungen | `compute_pairing_order_params()` in Domain extrahieren | **Behoben (P1.5)** — Funktion nach `domain/orders.py` extrahiert, Lazy-Import entfernt |
| **Fehlendes Row-Level Locking** bei `process_sell_fill()` | Hoch | `lot_service.py:637-729` | `.with_for_update()` auf Lot-Queries analog zu `pairing_service` | Offen |
| ~~**N+1 Query** in `get_lots_for_user()`~~ | Mittel | `lot_service.py:84` — `_lot_db_to_dict()` fuehrt pro Lot eine separate Fill-Event-Query aus | Batch-Load der Fill-Events vor der Schleife | **Behoben (P1.4)** — Batch-Load mit `fill_map`, 2 Queries statt 1+N |
| **Inkonsistente Error-Response-Formate** | Niedrig | Verschiedene Services | Standardisierte Status-Enums einfuehren | Offen |

**Bewertung: B+ (7.8/10) → A- (8.4/10, nach P1.4 + P1.5 Fixes)**

---

## 3. API Routes — Gut (ein kritischer Befund)

**Staerken:**
- Routes sind **duenn** (95% reine HTTP-Delegation)
- **Authentication konsistent**: Alle 12 HTTP-Router mit `api_auth` Dependency, WebSocket mit separatem Auth-Mechanismus
- **Error Sanitization**: Durchgehend generische Client-Fehler (`"Interner Serverfehler"`), `logger.exception()` serverseitig
- **Pydantic-Validierung**: Gute Nutzung von `@field_validator` (z.B. `orderblock.py:59-114`)
- **HTTP Status Codes**: Konsistent (400/404/403/500/504)

**Kritischer Befund:**

> **`db.commit()` direkt in Route aufgerufen** — `settings.py:171` verletzt das `yield`-Pattern aus `get_db()`. Fuehrt potenziell zu Double-Commit. `db.commit()` und `db.refresh()` aus der Route entfernen.

**Weitere Befunde:**

| Befund | Schwere | Ort |
|--------|---------|-----|
| Kein Request-Model fuer Order-Erstellung (inline Query-Params) | Niedrig | `routes/orders.py` |
| `threshold_pct` ohne Range-Validierung (`ge=0, le=1.0`) | Niedrig | `routes/pairing.py:54` |
| Config-Resolution und Serialisierung in Route statt Service | Niedrig | `routes/orderblock.py:202-215` |
| `asyncio.to_thread()` in Route statt Service | Niedrig | `routes/sentiment.py:49-50` |
| FIFO-Error als Custom-Status statt HTTP 500 | Niedrig | `routes/sync.py:93-101` |

**Bewertung: B (8.5/10, nach P0-Fix: B+)**

---

## 4. DB Layer & Migrationen — Gut

**Staerken:**
- **Normalisierung**: 1NF/2NF/3NF eingehalten, keine Redundanzen
- **Indexing**: Composite-Indexes auf haeufigen Query-Patterns (`idx_ledger_user_timestamp`, `idx_lots_user_status`, `idx_ob_zones_user_symbol_interval`)
- **Alembic**: `render_as_batch=True` korrekt fuer SQLite, reversible Migrationen mit Downgrade-Pfad
- **Foreign Keys**: Korrekt definiert mit `ForeignKeyConstraint`
- **IDOR-Schutz**: In den meisten Endpoints implementiert (user_id wird durchgereicht)

**Befunde:**

| Befund | Schwere | Ort |
|--------|---------|-----|
| `client_order_id` ist global unique statt `(user_id, client_order_id)` composite | Mittel | `db/models.py:228` |
| Dead Tables `User` und `APICredential` existieren ohne Nutzung | Niedrig | `db/models.py:73-105` |
| `fee_eur_value` Denormalisierung nicht dokumentiert | Niedrig | `db/models.py:131-137` |
| IDOR-Schutz in Orderblock/Cashflow Services nicht verifiziert | Mittel | Service-Layer Audit noetig |

**Bewertung: B+ (8.8/10)**

---

## 5. Frontend — Gut strukturiert, Testing fehlt komplett

**Staerken:**
- **Keine God-Components**: Groesste Komponente `LotsTable.jsx` (372 Zeilen) delegiert korrekt an 4 Sub-Komponenten (`LotSummaryCards`, `LotFilters`, `OpenOrdersPanel`, `PairingPanel`)
- **TanStack Query** korrekt eingesetzt: Hierarchische Query-Keys, Cache-Invalidierung nach Mutations, angemessenes `staleTime`
- **WebSocket-Integration**: Produktionsreif — Exponential Backoff (max 30s), REST-Fallback, Memory-Leak-Prevention, Query-Invalidierung bei Events, Heartbeat (30s)
- **Smart Performance**: Preis-Debouncing (`roundPrice` in Dashboard), `React.memo()` auf Route-Komponenten, `useMemo` fuer berechnete Werte
- **Konsistentes Error-Handling**: `err.response?.data?.detail || err.message` Pattern ueberall
- **API-Key sicher**: Via `import.meta.env.VITE_API_KEY`, nicht hardcoded
- **Styling konsistent**: Component-scoped CSS, Design-System-Compliance (Slate/Green/Red/Purple)

**Verbesserungspotenzial:**

| Befund | Schwere | Empfehlung |
|--------|---------|------------|
| **0 Frontend-Tests** | Kritisch | Vitest + React Testing Library aufsetzen. Prioritaet: `formatters.js`, `LotsTable`, `PairingPanel` |
| WebSocket-Preis nicht validiert (NaN/Inf moeglich) | Mittel | Range-Check nach `parseFloat(data.price)` |
| Mutation-Error-Handler dupliziert | Niedrig | `useMutationWithNotification` Hook extrahieren |
| Inline-Berechnungen in Render (`calculateUnrealizedPnl`) | Niedrig | In Utils extrahieren oder `useMemo` |
| Fehlendes `useCallback` auf Table-Row-Handler | Niedrig | `toggleLotSelection` wrappen |
| Kein globaler Error Boundary | Niedrig | React Error Boundary Komponente hinzufuegen |
| Unauthentifizierte WebSocket-Verbindung bei fehlendem API-Key | Niedrig | Explizit warnen oder abbrechen |

**Bewertung: A- (Architektur), F (Testing)**

---

## 6. Testing — Backend vorbildlich, Frontend fehlt

### Backend: 21 Testdateien — Exzellent

- **Umfassende Abdeckung**: Portfolio, Lots (FIFO/LIFO/HIGHEST_COST), Pairing, Orders, Sync, Reconciliation, CSV Import, Timezone, Macro Signal, Historical Price, Sentiment v3, Orderblock Detection/Backtest/Service, Combined Score, WebSocket Fill Handler, Lot Merge
- **Sauberes Arrange-Act-Assert Pattern** durchgehend
- **Excellent Test-Isolation**: In-memory SQLite, keine Shared State, Fixtures korrekt scoped
- **Sicherheit**: `conftest.py` erzwingt `TEST_BINANCE_API_KEY` + Testnet (autouse, session-scoped), Warnung bei fehlenden Test-Keys
- **Korrektes Mocking**: Binance API, historische Preise, Public Client

### Frontend: 0 Testdateien — Kritisch

- Kein Vitest/React Testing Library Setup
- `formatters.js` wird ueberall genutzt und ist komplett ungetestet
- Komplexe State-Logik (Pairing-Lifecycle, Lot-Filterung) ohne Regressionsschutz

**Bewertung: Backend A, Frontend F**

---

## 7. Infrastruktur — Luecken

| Fehlendes Element | Prioritaet | Impact |
|-------------------|-----------|--------|
| **Frontend-Tests** (Vitest) | Kritisch | Regressionsrisiko bei UI-Aenderungen |
| **CI/CD Pipeline** (GitHub Actions) | Hoch | Keine automatischen Quality-Gates |
| **Docker/docker-compose** | Mittel | Deployment-Komplexitaet, Umgebungs-Paritaet |
| `package-lock.json` in Git | Mittel | Reproduzierbare Frontend-Builds |
| `.env.example` unvollstaendig | Niedrig | Onboarding-Friction (TEST-Keys, CORS_ORIGINS fehlen) |
| pytest Coverage-Enforcement | Niedrig | Kein Minimum-Threshold (`--cov-fail-under=80`) |
| vite.config.js Build-Optimierung | Niedrig | Keine Minification/Code-Splitting-Konfiguration |

**Bewertung: D**

---

## Priorisierte Empfehlungen

### P0 — Vor Produktiveinsatz fixen

1. ~~**`db.commit()` aus `settings.py` Route entfernen**~~ ✅ **Erledigt**verletzt Transaction-Pattern, potenzieller Double-Commit
   - Ort: `backend/app/api/routes/settings.py:171`
   - Fix: `db.commit()` und `db.refresh()` entfernen, yield-Pattern handles it
   - Aufwand: 10 min

2. ~~**Row-Level Locking auf `process_sell_fill()`** — Race Condition bei Sell-Allocation**~~ ✅ **Erledigt**
   - Ort: `backend/app/services/lot_service.py:637-729`
   - Fix: `.with_for_update()` auf Lot-Queries analog zu `pairing_service`
   - Aufwand: 30 min

3. **Frontend-Tests aufsetzen** (Vitest) — mindestens `formatters.js` + kritische Flows
   - Ort: `frontend/`
   - Fix: Vitest + React Testing Library, `test_formatters.js` als erstes
   - Aufwand: 2-4h Setup + erste Tests

### P1 — Naechster Sprint

4. ~~**N+1 Query in `get_lots_for_user()` beheben**~~ ✅ **Erledigt**
   - `_lot_db_to_dict()` akzeptiert optionalen `fill_event`-Parameter
   - `get_lots_for_user()` und `get_mergeable_groups()` nutzen Batch-Load via `fill_map`
   - Reduziert 1+N Queries auf 2 Queries

5. ~~**Zirkulaere Abhaengigkeit `order_service` <-> `pairing_service` aufloesen**~~ ✅ **Erledigt**
   - `compute_pairing_order_params()` nach `domain/orders.py` extrahiert (pure Funktion)
   - `pairing_service.py` importiert direkt aus Domain (kein Lazy-Import-Hack mehr)
   - `order_service.py` re-exportiert fuer Backward-Kompatibilitaet
   - Dependency-Graph ist jetzt azyklisch

6. **CI/CD Pipeline** (GitHub Actions: pytest + ruff + npm build)
   - Aufwand: 1-2h

7. **WebSocket-Preis-Validierung** im Frontend
   - Ort: `frontend/src/contexts/WebSocketContext.jsx:88-90`
   - Fix: Range-Check nach `parseFloat(data.price)`

### P2 — Mittelfristig

8. `client_order_id` Constraint auf Composite `(user_id, client_order_id)` umstellen
   - Ort: `backend/app/db/models.py:228`
   - Erfordert Alembic-Migration

9. ~~`orderblock.py` (1397 Zeilen) in Sub-Module aufteilen~~ ✅ **Erledigt**
   - Aufgeteilt in Package `domain/orderblock/` mit 6 Sub-Modulen:
     - `models.py` — Enums + Dataclasses
     - `scoring.py` — ATR, Volume Z-Score/Percentile, OFI, Conviction Score
     - `detection.py` — 5-Phasen-Pipeline, Swing Points, FVG, State Management
     - `classification.py` — AlbaTherium (Extreme/Decisional/SMT)
     - `confluence.py` — Sentiment-OB Cross-Referenz
     - `parsing.py` — Binance Kline Transformation
   - `__init__.py` re-exportiert alle Symbols — kein externer Import geaendert
   - Azyklischer Dependency-Graph: `models` ← `scoring` ← `detection` → `classification`

10. Docker-Setup fuer konsistente Deployments
    - Dockerfile + docker-compose.yml

11. Dead Tables aufraemen oder dokumentieren
    - `User`, `APICredential` in `db/models.py`

12. IDOR-Schutz in Orderblock/Cashflow Service-Layer verifizieren
    - Audit: `get_zone_detail()`, `get_backtest_run()`, `get_cashflow_event()`

13. `.env.example` vervollstaendigen
    - TEST_BINANCE_API_KEY, TEST_BINANCE_API_SECRET, CORS_ORIGINS

### P3 — Nice to Have

14. `useMutationWithNotification` Hook im Frontend extrahieren
15. Sentiment Pillar-Scoring DRY refactoren (Loop statt 5x Copy-Paste)
16. Standardisierte Error-Response-Formate in Services
17. pytest Coverage-Enforcement (`--cov-fail-under=80`)
18. vite.config.js Build-Optimierung (Minification, Code-Splitting)
19. Frontend Error Boundary Komponente

---

## Architektur-Note

| Schicht | Bewertung | Details |
|---------|-----------|---------|
| Domain (pure Logik) | **A** | Strikt pure, keine I/O-Leaks, Decimal konsequent, deterministische Logik, Orderblock modularisiert, Order-Logik extrahiert |
| Service (Orchestrierung) | **A-** | Saubere Orchestrierung, Thread-Safety gut, N+1 behoben, zirkulaere Abh. aufgeloest, 1 verbleibendes Risiko (Row-Level Locking) |
| API Routes + DB | **B** | Duenne Routes, konsistente Auth, 1 kritischer Transaction-Befund |
| Frontend-Architektur | **A-** | Saubere Komponentenstruktur, TanStack Query + WebSocket vorbildlich |
| Frontend-Testing | **F** | 0 Tests fuer komplexe UI-Logik |
| Backend-Testing | **A** | 21 Testdateien, umfassende Coverage, gute Isolation |
| Infrastruktur (CI/CD, Docker) | **D** | Fehlt komplett |
| **Gesamt** | **B+** | **Produktionsreif nach P0-Fixes** |
