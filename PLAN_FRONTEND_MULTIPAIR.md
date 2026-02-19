# Frontend-Umbau: Multi-Pair-Architektur

## Kontext

Das Backend ist seit den letzten zwei Commits (`Multi-Symbol Support P1 + P2`) voll multi-pair-faehig. Das Frontend hat zwar einen Symbol-Selector in der Navbar und die API-Client-Funktionen akzeptieren `symbol`-Parameter, aber die Architektur ist fundamental auf "ein Symbol zur Zeit" ausgelegt. Mehrere Komponenten (CombinedScore, Orderblock) ignorieren das aktive Symbol komplett und zeigen immer BTCEUR-Daten. Es gibt keine Cross-Symbol-Uebersicht, keinen URL-basierten Symbol-Kontext und keinen stabilen State beim Wechsel.

**Ziel:** Frontend so umbauen, dass Multi-Pair-Trading natuerlich und fehlerfrei funktioniert — mit URL-basiertem Symbol-Routing, Cross-Symbol-Overview und korrekter Cache-Isolation.

---

## Phase 1: Routing-Architektur + Symbol-Context (Foundation)

### 1.1 Neue URL-Struktur

```
/                           → Cross-Symbol Overview (NEU)
/s/:symbol                  → Per-Symbol Dashboard (bisher /)
/s/:symbol/lots             → TradeLots
/s/:symbol/combined         → Combined Score
/s/:symbol/orderblock       → Orderblock
/s/:symbol/reconciliation   → Reconciliation
/settings                   → Settings (global)
```

**Warum `/s/:symbol` als Path-Parameter:**
- Symbol ist Teil der Route-Identitaet (React Router matched natuerlich)
- Deep-Linking, Browser Back/Forward, Page Refresh funktionieren
- TanStack Query Cache ist automatisch getrennt
- Kurzes `/s/` Prefix trennt per-Symbol von globalen Routes

### 1.2 Neue Datei: `SymbolLayout.jsx`

Wrapper-Komponente fuer alle `/s/:symbol/*` Routes:
- Liest `:symbol` aus `useParams()`
- Validiert gegen `KNOWN_PAIRS`, redirect zu `/s/BTCEUR` bei unbekanntem Symbol
- Stellt `SymbolContext` bereit: `{ symbol, marketPrice }`
- Rendert Tier-2-Navigation (Sub-Nav-Links) + Live-Preis
- Rendert `<Outlet />` fuer Child-Routes

### 1.3 Context-Umbau

**AppStateContext.jsx** wird aufgespalten:

| Vorher | Nachher |
|--------|---------|
| `AppStateContext` (userId, activeSymbol, marketPrice) | `UserContext` (userId) — global |
| | `SymbolContext` (symbol, marketPrice) — in SymbolLayout |

Neuer Hook: `useSymbol()` → ersetzt alle `useAppState()` Aufrufe die `activeSymbol`/`marketPrice` brauchen.
Neuer Hook: `useUser()` → gibt nur `userId` zurueck.

### 1.4 Navigation (2-Tier)

**Tier 1 (Global, immer sichtbar):**
- Links: App-Name
- Mitte: Symbol-Tabs (BTCEUR | ETHEUR | Overview) — navigieren zu `/s/BTCEUR/...` bzw. `/`
- Rechts: Aggregierter Portfolio-Wert + Settings-Link

**Tier 2 (Nur auf `/s/:symbol/*`, innerhalb SymbolLayout):**
- Sub-Nav: Dashboard, TradeLots, Combined Score, Orderblock, Reconciliation
- Live-Preis fuer aktuelles Symbol (verschoben aus Tier 1)

**Symbol-Tab-Wechsel-Verhalten:** Auf `/s/BTCEUR/lots` → Klick auf ETHEUR → navigiert zu `/s/ETHEUR/lots` (Sub-Page bleibt erhalten). Helper-Funktion `buildSymbolUrl(newSymbol, currentPathname)`.

### 1.5 Route-Konfiguration in App.jsx

```jsx
<Routes>
  <Route path="/" element={<Overview />} />
  <Route path="/s/:symbol" element={<SymbolLayout />}>
    <Route index element={<Dashboard />} />
    <Route path="lots" element={<LotsTable />} />
    <Route path="combined" element={<CombinedScore />} />
    <Route path="orderblock" element={<Orderblock />} />
    <Route path="reconciliation" element={<Reconciliation />} />
  </Route>
  <Route path="/settings" element={<Settings />} />
  <Route path="*" element={<Navigate to="/" replace />} />
</Routes>
```

Entfaellt: `memo()` Wrapper (MemoReconciliation etc.) — nicht mehr noetig, da Preis-Updates auf SymbolContext isoliert sind.

---

## Phase 2: Alle Komponenten auf useSymbol() umstellen + Query-Keys fixen

### 2.1 Query-Key-Konvention

**Jeder per-Symbol Query muss `symbol` enthalten:**

```
['portfolio', symbol, userId, stablePrice]
['lots', symbol, userId, statusFilter, fromDate, toDate]
['orders', symbol, userId, status]
['pairings', symbol, userId, statusFilter]
['pairingSuggestions', symbol, userId, marketPrice, thresholdPct]
['combined-score', symbol, userId, interval]
['ob-zones', symbol, userId, interval]
['ob-backtest-runs', symbol, userId]
['ob-candles', symbol, userId, zoneId, interval]
```

**Symbol-agnostisch (unveraendert):**
```
['settings', userId]
['server-ip']
```

### 2.2 Komponenten-Aenderungen

| Datei | Aenderung |
|-------|-----------|
| **CombinedScore.jsx** | `useAppState()` → `useSymbol()` + `useUser()`. Query-Key: `['combined-score', symbol, userId, interval]`. API-Call: `getCombinedScore(userId, interval, symbol)`. Header: `getPairLabel(symbol)` statt hardcoded "BTC/EUR" |
| **Orderblock.jsx** | `useAppState()` → `useSymbol()` + `useUser()`. Symbol in alle Query-Keys + API-Calls: `analyzeOrderblocks(userId, { symbol, ... })`, `getOrderblockZones(userId, { symbol, ... })`, `deleteOrderblockZones(userId, { symbol, ... })`, `getOrderblockCandles(userId, { symbol, ... })`, `getOrderblockBacktestRuns(userId, symbol)` |
| **Dashboard.jsx** | `useAppState()` → `useSymbol()` + `useUser()`. Query-Keys anpassen (symbol als 2. Element) |
| **useLotsData.js** | `useAppState()` → `useSymbol()` + `useUser()`. Bestehende Query-Keys: `activeSymbol` → `symbol` umbenennen. Orders-Query: Symbol an `getOrdersForUser()` durchreichen. Pairings-Query: Symbol an `listPairings()` durchreichen |
| **LotsTable.jsx** | `useAppState()` → `useSymbol()` + `useUser()` |
| **PairingPanel.jsx** | `useAppState()` → `useSymbol()` + `useUser()`. Query-Key fuer Suggestions: `symbol` hinzufuegen |
| **PairingExistingTab.jsx** | `useAppState()` → `useSymbol()` + `useUser()`. Query-Key: Symbol hinzufuegen |
| **Reconciliation.jsx** | `useAppState()` → `useSymbol()` + `useUser()` |
| **Settings.jsx** | `useAppState()` → `useUser()` (kein Symbol noetig, global) |
| **FillNotification.jsx** | Symbol aus `useSymbol()` lesen. Nur Fills fuer aktuelles Symbol anzeigen (auf Overview-Seite: alle) |
| **OpenOrdersPanel.jsx, LotFilters.jsx, SimulationModal.jsx** | `useAppState()` → `useSymbol()` + `useUser()` |

### 2.3 API-Client-Aenderungen (client.js)

Funktionen die bisher `symbol` nicht erhalten:
- `getOrdersForUser(userId, status)` → `getOrdersForUser(userId, status, symbol)` + `params: { status, symbol }`
- `listPairings(userId, status)` → `listPairings(userId, status, symbol)` + `params: { status, symbol }`
- `getMergeGroups(userId)` → `getMergeGroups(userId, symbol)` + `params: { symbol }`

### 2.4 WebSocket Symbol-scoped Invalidation

In `WebSocketContext.jsx`, Invalidation per Symbol statt blanket:

```js
case 'order_update': {
  const sym = data.symbol || 'BTCEUR';
  queryClient.invalidateQueries({ queryKey: ['orders', sym] });
  queryClient.invalidateQueries({ queryKey: ['lots', sym] });
  queryClient.invalidateQueries({ queryKey: ['portfolio', sym] });
  break;
}
```

---

## Phase 3: Cross-Symbol Overview Dashboard

### 3.1 Neue Datei: `Overview.jsx` (Route `/`)

**Aggregiertes Portfolio ueber alle Symbole.**

Datenbeschaffung: Parallel `getPortfolio(userId, prices[sym], sym)` fuer jedes Symbol in `KNOWN_PAIRS`. Frontend-Aggregation (kein neuer Backend-Endpoint noetig).

**Layout:**
1. **Gesamt-Portfolio-Karte:** Aggregierter EUR-Wert, Gesamt-P&L, Gesamt-BTC/ETH Bestaende
2. **Per-Symbol Summary Cards** (je eine Karte pro Paar):
   - Paar-Label + Live-Preis
   - Base-Menge + EUR-Marktwert
   - Unrealisierte P&L (EUR + %)
   - Offene Lots Anzahl
   - Quick-Links: "Lots", "Signals", "Orderblocks" → navigiert zu `/s/{symbol}/...`
3. **Allocation Pie Chart** (Recharts, bereits als Dependency vorhanden): Verteilung nach EUR-Marktwert
4. **Depot-Performance:** Gesamt-Depoterfolg ueber alle Paare

### 3.2 Preise auf Overview-Seite

Die WebSocket `prices` Map enthaelt bereits alle Symbole (`prices['BTCEUR']`, `prices['ETHEUR']`). Auf der Overview-Seite direkt aus dem WebSocketContext lesen — kein `useLivePrice` noetig, da wir alle Preise gleichzeitig brauchen.

---

## Phase 4: Filter-State-Persistenz per Symbol

### 4.1 URL Search Params fuer Filter

In `useLotsData.js`: Filter-State (`statusFilter`, `fromDate`, `toDate`, `sortColumn`, `sortDirection`) in URL Search Params statt `useState`:

```js
const [searchParams, setSearchParams] = useSearchParams();
const statusFilter = searchParams.get('status') || null;
const fromDate = searchParams.get('from') || '';
```

**Vorteil:** Beim Symbol-Wechsel `/s/BTCEUR/lots?status=OPEN` → `/s/ETHEUR/lots` starten die ETH-Lots ohne Filter (sauber). BTCEUR-Filter bleiben im Browser-History erhalten.

### 4.2 Transiente UI-States (NICHT persistieren)

Diese States werden beim Symbol-Wechsel reset (korrekt, da symbol-spezifisch):
- `selectedLotIds` (Lot-IDs sind pro Symbol unterschiedlich)
- `pairingPanelOpen`, `pairingActiveTab`
- `selectedZone`, `selectedTradeRow` (Orderblock)
- `showMacroDetail`, `showSentimentDetail` (CombinedScore)

---

## Zu aendernde Dateien

### Neue Dateien
| Datei | Beschreibung |
|-------|-------------|
| `frontend/src/components/Overview.jsx` | Cross-Symbol Dashboard |
| `frontend/src/components/Overview.css` | Styling |
| `frontend/src/components/SymbolLayout.jsx` | URL-basierter Symbol-Wrapper + Tier-2 Nav |
| `frontend/src/components/GlobalNav.jsx` | Tier-1 Navigation (Symbol-Tabs + Aggregat) |
| `frontend/src/contexts/SymbolContext.jsx` | Symbol + MarketPrice Context + useSymbol() Hook |
| `frontend/src/contexts/UserContext.jsx` | userId Context + useUser() Hook |

### Bestehende Dateien
| Datei | Art der Aenderung |
|-------|-------------------|
| `frontend/src/App.jsx` | Komplett umstrukturieren: Nested Routes, Context-Hierarchie, Navbar-Auslagerung |
| `frontend/src/contexts/AppStateContext.jsx` | Loeschen (ersetzt durch UserContext + SymbolContext) |
| `frontend/src/api/client.js` | `getOrdersForUser`, `listPairings`, `getMergeGroups`: Symbol-Param hinzufuegen |
| `frontend/src/hooks/useLotsData.js` | Context-Swap, Query-Keys, Filter → URL Search Params |
| `frontend/src/contexts/WebSocketContext.jsx` | Symbol-scoped Invalidation |
| `frontend/src/components/CombinedScore.jsx` | Context-Swap, Symbol in Query+API, dynamisches Label |
| `frontend/src/components/Orderblock.jsx` | Context-Swap, Symbol in alle Queries+Mutations+API-Calls |
| `frontend/src/components/Dashboard.jsx` | Context-Swap |
| `frontend/src/components/LotsTable.jsx` | Context-Swap |
| `frontend/src/components/PairingPanel.jsx` | Context-Swap, Symbol in Query-Key |
| `frontend/src/components/PairingExistingTab.jsx` | Context-Swap, Symbol in Query-Key |
| `frontend/src/components/Reconciliation.jsx` | Context-Swap |
| `frontend/src/components/Settings.jsx` | `useAppState()` → `useUser()` |
| `frontend/src/components/FillNotification.jsx` | Symbol-Filter (nur aktives Symbol anzeigen) |
| `frontend/src/components/OpenOrdersPanel.jsx` | Context-Swap |
| `frontend/src/components/LotFilters.jsx` | Context-Swap |
| `frontend/src/components/SimulationModal.jsx` | Context-Swap |
| `frontend/src/App.css` | Navbar-Styling fuer 2-Tier Navigation |

### Backend (minimal)
| Datei | Aenderung |
|-------|-----------|
| `backend/app/api/routes/orders.py` | `list_orders`: Symbol-Filter an DB-Query durchreichen (falls noch nicht) |
| `backend/app/api/routes/pairing.py` | `list_pairings`: Symbol-Filter-Parameter akzeptieren |

---

## Implementierungs-Reihenfolge

1. **UserContext + SymbolContext** erstellen (neue Dateien)
2. **SymbolLayout + GlobalNav** erstellen
3. **App.jsx** komplett umbauen (Routes, Context-Hierarchie)
4. **AppStateContext loeschen**, alle Imports auf neue Contexts umstellen
5. **Jede Komponente** einzeln migrieren (`useAppState()` → `useSymbol()` + `useUser()`)
6. **Query-Keys** ueberall fixen (Symbol als 2. Element)
7. **CombinedScore + Orderblock** Bug-Fixes (Symbol durchreichen)
8. **API-Client** erweitern (Orders, Pairings, MergeGroups: Symbol-Param)
9. **WebSocket** Symbol-scoped Invalidation
10. **Overview.jsx** erstellen
11. **Filter-State** auf URL Search Params umstellen (useLotsData)
12. **NavLink Updates** in allen Komponenten (relative Links statt absolute)

---

## Verifikation

1. **Symbol-Routing testen:**
   - `/s/BTCEUR/lots` zeigt BTC-Lots, `/s/ETHEUR/lots` zeigt ETH-Lots
   - Page Refresh behaelt Symbol bei
   - Browser Back/Forward navigiert korrekt
   - Unbekanntes Symbol (`/s/XYZUSD/lots`) redirected zu `/s/BTCEUR`

2. **Cache-Isolation testen:**
   - BTCEUR-Lots laden → zu ETHEUR wechseln → zurueck zu BTCEUR: Daten korrekt (kein Mischen)
   - CombinedScore zeigt korrektes Symbol-Label und korrekte Daten

3. **Overview testen:**
   - Zeigt aggregierte Werte beider Symbole
   - Per-Symbol Cards mit korrekten Live-Preisen
   - Click auf Card navigiert zu `/s/{symbol}`

4. **Bestehende Tests:** `npm run build` + `npm run lint` muessen bestehen

5. **Backend-Tests:** `pytest` (bestehende Tests unberuehrt, da Frontend-only Aenderungen)
