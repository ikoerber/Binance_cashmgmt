# Security-Audit: BTC/EUR Cashflow-Management App

**Datum:** 2026-02-18
**Auditor:** Claude Opus 4.6
**Scope:** Full-Stack (Backend + Frontend + Config + Dependencies)

---

## Gesamtbewertung

Das Projekt zeigt eine **solide Sicherheitsbasis** mit durchgehender IDOR-Absicherung, SQLAlchemy-ORM (keine SQL-Injection), generischer Error-Sanitization und Decimal-Praezision fuer alle Finanzberechnungen. Die Hauptrisiken liegen in der **Authentifizierung** (Timing-Attack, fehlender Auth-Bypass-Schutz), **Konfiguration** (API-Keys in Git-History) und **Input-Validierung** (fehlende Checks in Pairing-Routes).

---

## CRITICAL

### 1. ~~Timing-Attack in API-Key-Vergleich~~ BEHOBEN

**Schwere:** CRITICAL
**Status:** BEHOBEN (bereits vor Audit gefixt)
**Datei:** `backend/app/api/auth.py`

`hmac.compare_digest()` wird bereits verwendet. War zum Audit-Zeitpunkt bereits korrekt implementiert.

---

### 2. ~~Auth wird bei fehlendem API_SECRET_KEY still deaktiviert~~ BEHOBEN

**Schwere:** CRITICAL
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/api/auth.py`

**Fix:** Production-Guard hinzugefuegt. Bei `APP_ENV=production` ohne `API_SECRET_KEY` wird HTTP 500 zurueckgegeben. In Development: Warning-Log statt stiller Deaktivierung.

---

### 3. ~~Fehlende market_price-Validierung in Pairing-Routes~~ BEHOBEN

**Schwere:** CRITICAL
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/api/routes/pairing.py`

**Fix:** `_validate_market_price()` Helper hinzugefuegt und in allen 3 Endpoints (suggestions, simulate, execute) vor der Decimal-Konvertierung aufgerufen. Prueft auf NaN, Infinity und negative Werte (HTTP 400).

---

### 4. API-Keys in Git-Repository committed

**Schwere:** CRITICAL
**Datei:** `backend/.env` (in Git-History)

**Problem:** Reale Binance-, TwelveData- und FRED-API-Keys sind in der Git-History enthalten:
- `BINANCE_API_KEY` / `BINANCE_API_SECRET` (Produktions-Keys)
- `TEST_BINANCE_API_KEY` / `TEST_BINANCE_API_SECRET`
- `TWELVE_DATA_API_KEY`
- `FRED_API_KEY`

**Impact:** Jeder mit Repository-Zugang kann auf dem Binance-Account handeln, Kontostatus abrufen oder im schlimmsten Fall Withdrawals initiieren (abhaengig von API-Key-Permissions).

**Anmerkung:** `.env` ist korrekt in `.gitignore` eingetragen, wurde aber in einem frueheren Commit hinzugefuegt.

**Fix:**
1. **SOFORT:** Alle API-Keys rotieren (Binance, TwelveData, FRED)
2. `.env` aus Git-History entfernen:
   ```bash
   git filter-repo --invert-paths --path backend/.env
   git push --force-with-lease
   ```
3. Pre-Commit-Hook einrichten:
   ```bash
   # .git/hooks/pre-commit
   if git diff --cached --name-only | grep -E '\.env$'; then
     echo "ERROR: .env cannot be committed"
     exit 1
   fi
   ```

**Aufwand:** 30 min (Key-Rotation + History-Cleanup)

---

## HIGH

### 5. Kein Rate-Limiting auf Auth-Failures

**Schwere:** HIGH
**Datei:** `backend/app/api/auth.py`

**Problem:** Brute-Force-Angriffe auf den API-Key sind unbegrenzt moeglich. Keine Verzoegerung, keine Sperre, kein Logging der Fehlversuche.

**Angriffsvektor:** Automatisiertes Skript mit 10.000+ Versuchen/Sekunde.

**Fix:** Rate-Limiting-Middleware (z.B. `slowapi`):
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
# 5 fehlgeschlagene Auth-Versuche pro Minute pro IP
```

**Aufwand:** 1-2h

---

### 6. WebSocket Auth Race Condition

**Schwere:** HIGH
**Datei:** `backend/app/api/routes/websocket.py:55-70`

**Problem:** Bei First-Message-Auth wird der WebSocket **vor** der Authentifizierung akzeptiert (`await websocket.accept()`). Im Zeitfenster zwischen Accept und Auth-Message koennen unauthentifizierte Nachrichten eintreffen.

**Fix:** Auth-Message als erste Nachricht erzwingen. Alle anderen Nachrichten vor erfolgreicher Auth verwerfen.

**Aufwand:** 1h

---

### 7. ~~WebSocket: Timing-Attack + Query-Parameter-Auth~~ BEHOBEN

**Schwere:** HIGH
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/api/routes/websocket.py`

**Fix:**
- `hmac.compare_digest()` fuer timing-safe Vergleich implementiert
- Query-Parameter-Auth (`?X-API-Key=...`) komplett entfernt — nur noch First-Message-Auth
- Frontend verwendete bereits First-Message-Auth, keine Anpassung noetig

---

### 8. ~~CORS zu permissiv~~ BEHOBEN

**Schwere:** HIGH
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/main.py`

**Fix:** Explizite `allow_methods` (GET/POST/PUT/DELETE/PATCH/OPTIONS), explizite `allow_headers` (Content-Type, X-API-Key) und `max_age=3600` konfiguriert.

---

### 9. CSV-Injection (Formula Injection)

**Schwere:** HIGH
**Status:** Offen
**Datei:** `backend/app/services/csv_import_service.py`

**Problem:** CSV-Zellen werden ohne Pruefung auf Formel-Praefixe (`=`, `+`, `-`, `@`, `\t`, `\r`) verarbeitet. Wenn ein User manipulierte CSVs importiert und die Daten spaeter exportiert werden, koennten Formeln in Spreadsheet-Applikationen ausgefuehrt werden.

**Aufwand:** 30 min

---

### 10. ~~Kein File-Size-Limit bei CSV-Import~~ BEHOBEN

**Schwere:** HIGH
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/api/routes/sync.py`

**Fix:** 10 MB Size-Limit implementiert. `file.read(MAX_CSV_SIZE + 1)` mit Pruefung, HTTP 413 bei Ueberschreitung.

---

### 11. ~~max_order_value_eur ohne Obergrenze~~ BEHOBEN

**Schwere:** HIGH
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/api/routes/settings.py`

**Fix:** Validierung auf `1 <= max_val <= 1.000.000 EUR`. Ersetzt die vorherige `> 0`-only Pruefung.

---

### 12. Frontend API-Key im Bundle exponiert

**Schwere:** HIGH
**Datei:** `frontend/src/api/client.js:10-13`

**Problem:** `VITE_API_KEY` wird durch Vite in den JavaScript-Bundle eingebettet. Jeder Client kann den API-Key in den Browser-DevTools (Sources, Network) sehen.

**Anmerkung:** Architektonisch bedingt (SPA + Static API-Key). Fuer Production empfohlen: Session-basierte Auth oder Backend-Proxy.

**Fix (langfristig):** Session-Token-basierte Authentifizierung statt statischer API-Keys im Frontend.

**Aufwand:** Groesseres Refactoring (Session-Auth)

---

## MEDIUM

### 13. ~~Fehlende Security-Headers~~ BEHOBEN

**Schwere:** MEDIUM
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/main.py`

**Fix:** HTTP-Middleware hinzugefuegt: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Strict-Transport-Security: max-age=31536000; includeSubDomains`.

---

### 14. Kein Request-Size-Limit

**Schwere:** MEDIUM
**Datei:** `backend/app/main.py`

**Problem:** Keine globale Payload-Groessen-Beschraenkung. Angreifer kann extrem grosse Request-Bodies senden (Memory-Exhaustion).

**Fix:** Middleware oder Uvicorn-Konfiguration: `--limit-max-request-size 10485760` (10 MB).

**Aufwand:** 15 min

---

### 15. ~~WebSocket-Preis nicht auf NaN/Inf validiert (Frontend)~~ BEHOBEN

**Schwere:** MEDIUM
**Status:** BEHOBEN (2026-02-18)
**Datei:** `frontend/src/contexts/WebSocketContext.jsx`

**Fix:** `parseFloat(data.price)` wird jetzt auf `isNaN`, `!isFinite` und `<= 0` geprueft. Ungueltige Preise werden ignoriert.

---

### 16. WebSocket Fill-Handler: Decimal NaN/Inf nicht validiert

**Schwere:** MEDIUM
**Datei:** `backend/app/services/websocket_fill_handler.py:199-208`

**Problem:** Decimal-Werte werden auf `<= 0` geprueft, aber nicht auf `.is_nan()` / `.is_infinite()`. Malicious WebSocket-Message mit `"Infinity"` wuerde als valides Decimal akzeptiert.

**Fix:**
```python
if qty.is_nan() or qty.is_infinite() or price.is_nan() or price.is_infinite():
    logger.warning("Invalid Decimal values: NaN or Infinity")
    return None
```

**Aufwand:** 10 min

---

### 17. Binance API-Response nicht schema-validiert

**Schwere:** MEDIUM
**Datei:** `backend/app/services/binance.py`

**Problem:** Trade-Dicts von Binance werden ohne Feld-Pruefung direkt verarbeitet. Fehlende Felder fuehren zu `KeyError`.

**Fix:**
```python
required_fields = ["id", "price", "qty", "commission", "commissionAsset", "time", "isBuyer"]
missing = [f for f in required_fields if f not in trade]
if missing:
    logger.error(f"Malformed Binance trade: missing {missing}")
    raise ValueError(f"Missing fields: {missing}")
```

**Aufwand:** 30 min

---

### 18. ~~CSV-Error Information Disclosure~~ BEHOBEN

**Schwere:** MEDIUM
**Status:** BEHOBEN (2026-02-18)
**Datei:** `backend/app/api/routes/sync.py`

**Fix:** Generische Fehlermeldung (`"CSV-Format ungueltig"`) statt interner Fehlerdetails. Exception wird server-seitig via `logger.warning()` geloggt.

---

### 19. Kein CSRF-Schutz

**Schwere:** MEDIUM
**Datei:** `frontend/src/api/client.js`

**Problem:** State-aendernde Requests (POST/PUT/DELETE) ohne CSRF-Token.

**Anmerkung:** Aktuell API-Key-basiert (kein Cookie), daher Risiko reduziert. Wird relevant bei Umstellung auf Session-Auth.

**Aufwand:** 1-2h (bei Session-Auth-Umstellung)

---

### 20. Fehlende Security-Headers in Vite-Config

**Schwere:** MEDIUM
**Datei:** `frontend/vite.config.js`

**Problem:** Keine Content-Security-Policy, keine X-Frame-Options im Dev-Server. In Production muessen diese auf Webserver-Ebene konfiguriert werden.

**Aufwand:** 30 min (Vite Dev-Config) / Deployment-abhaengig (Production)

---

## LOW

### 21. clientOrderId Hash-Kollision

**Schwere:** LOW
**Datei:** `backend/app/services/order_service.py:100-102`

**Problem:** `int(target_price)` verliert Nachkommastellen. Zwei Orders mit Preisen 50123.45 und 50123.78 erzeugen gleiche ID-Komponente.

**Fix:** `str(target_price_rounded).replace(".", "")` statt `int(target_price)`.

**Aufwand:** 10 min

---

### 22. API_SECRET_KEY ohne Mindestlaenge

**Schwere:** LOW
**Datei:** `backend/app/api/auth.py`

**Problem:** Keine Validierung der Key-Staerke. Koennte `"123"` oder `"password"` sein.

**Fix:** Startup-Validierung: `if len(key) < 32: raise RuntimeError("API_SECRET_KEY too short")`.

**Aufwand:** 10 min

---

### 23. Kein Error Boundary im Frontend

**Schwere:** LOW
**Datei:** Frontend (alle Komponenten)

**Problem:** React-Fehler koennten sensible State-Daten in der Fehlermeldung exponieren. Keine graceful Degradation.

**Aufwand:** 1h

---

### 24. Source Maps in Production nicht deaktiviert

**Schwere:** LOW
**Datei:** `frontend/vite.config.js`

**Problem:** Keine explizite Deaktivierung von Source Maps fuer Production-Builds. Quellcode koennte exponiert werden.

**Fix:** `build: { sourcemap: false }` in vite.config.js.

**Aufwand:** 5 min

---

### 25. Default-Werte fuer API-Keys als leerer String

**Schwere:** LOW
**Datei:** `backend/app/services/macro_data_service.py:69-70`
**Code:**
```python
self._twelve_data_api_key = os.getenv("TWELVE_DATA_API_KEY", "")
self._fred_api_key = os.getenv("FRED_API_KEY", "")
```

**Problem:** Fehlende Keys fuehren zu stillen Fehlern (leerer String → API-Aufruf schlaegt fehl statt fruehe Fehlermeldung).

**Fix:** Startup-Validierung statt stiller Degradation.

**Aufwand:** 15 min

---

## Positiv-Befunde (bereits gut geloest)

| Bereich | Status | Details |
|---------|--------|---------|
| **IDOR-Schutz** | OK | Alle DB-Queries filtern nach `user_id` |
| **SQL-Injection** | OK | SQLAlchemy ORM, keine Raw-Queries, parametrisierte Filter |
| **Error-Sanitization** | OK | Generische Fehlermeldungen an Client (`"Interner Serverfehler"`), `logger.exception()` serverseitig |
| **Decimal-Praezision** | OK | Durchgehend Decimal fuer Geldbetraege, API-Transport als String |
| **Division-by-Zero** | OK | Alle 6 identifizierten Stellen abgesichert |
| **Idempotente Orders** | OK | `clientOrderId`-Pattern verhindert Doppel-Orders |
| **FIFO Abort-on-Error** | OK | Schuetzt FIFO-Invariante bei Sync-Fehlern |
| **Row-Level Locking** | OK | In Pairing-Service korrekt implementiert (`with_for_update()`) |
| **Dependencies gepinnt** | OK | Backend: exakte Versionen, Frontend: `package-lock.json` committed |
| **Test-Isolation** | OK | Testnet-Keys via `conftest.py`, nie Produktion |
| **XSS-Schutz** | OK | React escaped standardmaessig, kein `dangerouslySetInnerHTML` |
| **Kein Raw-SQL** | OK | Ausschliesslich SQLAlchemy ORM |

---

## Priorisierte Massnahmen

### SOFORT (heute) — Stand 2026-02-18

| Nr | Massnahme | Aufwand | Referenz | Status |
|----|-----------|---------|----------|--------|
| 1 | API-Keys rotieren (Binance, TwelveData, FRED) | 15 min | #4 | **MANUELL ERFORDERLICH** |
| 2 | `.env` aus Git-History entfernen | 30 min | #4 | **MANUELL ERFORDERLICH** |
| 3 | `hmac.compare_digest()` in `auth.py` + `websocket.py` | 15 min | #1, #7 | BEHOBEN |
| 4 | `market_price`-Validierung in Pairing-Routes | 15 min | #3 | BEHOBEN |
| 5 | Auth-Bypass bei fehlendem API_SECRET_KEY fixen | 10 min | #2 | BEHOBEN |

### Woche 1

| Nr | Massnahme | Aufwand | Referenz | Status |
|----|-----------|---------|----------|--------|
| 6 | Rate-Limiting Middleware | 1-2h | #5 | Offen |
| 7 | CORS einschraenken (explizite Methods/Headers) | 15 min | #8 | BEHOBEN |
| 8 | Security-Headers Middleware | 30 min | #13 | BEHOBEN |
| 9 | CSV-Injection Sanitization | 30 min | #9 | Offen |
| 10 | CSV File-Size-Limit | 15 min | #10 | BEHOBEN |
| 11 | `max_order_value_eur` Obergrenze | 10 min | #11 | BEHOBEN |
| 12 | CSV-Error Information Disclosure fixen | 5 min | #18 | BEHOBEN |

### Woche 2

| Nr | Massnahme | Aufwand | Referenz | Status |
|----|-----------|---------|----------|--------|
| 13 | WebSocket Auth-Flow verbessern (Race Condition) | 1h | #6 | Offen |
| 14 | Request-Size-Limit | 15 min | #14 | Offen |
| 15 | WebSocket-Preis NaN/Inf-Validierung (Frontend) | 10 min | #15 | BEHOBEN |
| 16 | Fill-Handler NaN/Inf-Validierung | 10 min | #16 | Offen |
| 17 | Binance API-Response Schema-Validierung | 30 min | #17 | Offen |

### Backlog

| Nr | Massnahme | Aufwand | Referenz | Status |
|----|-----------|---------|----------|--------|
| 18 | Frontend API-Key-Architektur (Session-Auth) | Groesser | #12 | Offen |
| 19 | CSRF-Schutz (bei Session-Auth) | 1-2h | #19 | Offen |
| 20 | Frontend Error Boundary | 1h | #23 | Offen |
| 21 | Source Maps in Production deaktivieren | 5 min | #24 | Offen |
| 22 | clientOrderId Kollisionsschutz | 10 min | #21 | Offen |
| 23 | API_SECRET_KEY Mindestlaenge | 10 min | #22 | Offen |
| 24 | Startup-Validierung aller API-Keys | 15 min | #25 | Offen |
| 25 | Pre-Commit-Hook gegen `.env`-Commits | 15 min | #4 | Offen |

---

## Zusammenfassung (Stand: 2026-02-18)

| Schwere | Anzahl | Behoben | Offen |
|---------|--------|---------|-------|
| **CRITICAL** | 4 | 3 (#1, #2, #3) | 1 (#4: API-Keys in Git) |
| **HIGH** | 8 | 4 (#7, #8, #10, #11) | 4 (#5, #6, #9, #12) |
| **MEDIUM** | 8 | 3 (#13, #15, #18) | 5 (#14, #16, #17, #19, #20) |
| **LOW** | 5 | 0 | 5 |
| **Total** | **25** | **10** | **15** |

**Gesamtbewertung:** 10 von 25 Findings behoben (40%). Alle code-basierten CRITICAL Findings sind gefixt. Das verbleibende CRITICAL Finding (#4: API-Keys in Git-History) erfordert manuelles Key-Rotation und `git filter-repo`. Die offenen HIGH Findings (#5 Rate-Limiting, #6 WebSocket Race, #9 CSV-Injection, #12 Frontend API-Key) sollten innerhalb der naechsten 1-2 Wochen adressiert werden.
