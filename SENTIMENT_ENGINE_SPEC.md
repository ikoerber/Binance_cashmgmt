# SentimentEngine - Spezifikation v2.0

**Status:** Entwurf
**Bezug:** Erweiterung des bestehenden BTC/EUR Cashflow-Management Systems
**Abgrenzung:** Komplementaer zum MacroSignal (Makro-Richtung), NICHT Ersatz

---

## 1. Zielsetzung

Die SentimentEngine aggregiert krypto-spezifische Stimmungsindikatoren zu einem normalisierten **Sentiment Score (0-100)**. Dieser Score ergaenzt das bestehende MacroSignal (das globale Makro-Faktoren wie DXY, Yield-Spreads und BTC-Momentum abdeckt) um **Marktsentiment, Derivate-Hitze und technische Trendlage**.

### 1.1 Abgrenzung MacroSignal vs. SentimentEngine

| Aspekt | MacroSignal (besteht) | SentimentEngine (neu) |
|--------|----------------------|----------------------|
| **Fokus** | Globale Makro-Faktoren | Krypto-spezifisches Sentiment |
| **Faktoren** | BTC-Momentum, EUR/USD, DXY, Yield-Spread | Fear&Greed, Funding Rate, Taker-Volume, Trend-Deviation |
| **Zeitrahmen** | 1m / 5m / 15m (kurzfristig) | Taeglich / 8h / rollierend (mittel-/langfristig) |
| **Score-Bereich** | -2 bis +2 (Richtung) | 0 bis 100 (Stimmungslage) |
| **Zweck** | Kurzfristige Richtungsempfehlung | Position-Sizing und Risiko-Steuerung |
| **Output** | "STARK LONG" / "NEUTRAL" / "STARK SHORT" | "Extreme Fear" / "Neutral" / "Extreme Greed" |

### 1.2 Kombiniertes Signal (spaeter)

In einer zukuenftigen Iteration koennen MacroSignal und SentimentEngine zu einem **Combined Score** zusammengefuehrt werden:
- MacroSignal = kurzfristige Richtung (Timing)
- SentimentEngine = mittelfristige Stimmung (Position-Sizing)
- Combined = Wann UND Wieviel

---

## 2. Architektur-Einordnung

### 2.1 Schichten (analog zu MacroSignal)

```
domain/sentiment.py          Pure Scoring-Logik (kein I/O)
services/sentiment_service.py    Daten-Fetching + Caching (analog zu MacroDataService)
api/routes/sentiment.py      Thin HTTP Layer
db/models.py                 SentimentHistoryDB (neues Modell)
```

### 2.2 Konventionen (aus bestehendem Projekt)

- **Decimal** fuer alle numerischen Berechnungen (niemals float)
- **Dataclasses** fuer Domain-Objekte
- **CachedValue-Pattern** mit TTL (wie in MacroDataService)
- **Thread-safe** via Lock (Singleton-Service)
- **Graceful Degradation** - fehlende Quellen liefern Score 50 (Neutral)
- **Quality-Badges** pro Datenquelle ("live", "cached", "stale", "unavailable")

---

## 3. Datenquellen (5 Pillars)

### EU-Compliance

Alle Quellen muessen von EU/Deutschland aus erreichbar sein. Die Binance Futures API (`fapi.binance.com`) ist aufgrund der MiCA-Regulierung in der EU potentiell geo-blockiert und wird daher **nicht verwendet**.

### Pillar 1: Emotional Sentiment (Gewicht: 20%)

**Primaer:** Alternative.me Fear & Greed Index
- **Endpoint:** `GET https://api.alternative.me/fng/?limit=1`
- **Auth:** Keine (oeffentlich)
- **Rate Limit:** 60 req/min
- **Update:** Taeglich (1x pro 24h)
- **Cache-TTL:** 1 Stunde (Wert aendert sich nur taeglich)
- **Mapping:** Direkter Wert (0-100), keine Transformation noetig

**Fallback:** CoinMarketCap Fear & Greed API
- **Endpoint:** `GET https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest`
- **Auth:** API-Key (Header `X-CMC_PRO_API_KEY`)
- **Free Tier:** 10.000 Credits/Monat (~333 Calls/Tag)
- **Aktivierung:** Nur wenn Alternative.me 3x hintereinander fehlschlaegt

**Warum 20% statt 40%:**
Der F&G-Index ist selbst ein Composite (Volatilitaet 25%, Volume 25%, Social 15%, Surveys 15%, Dominance 10%, Trends 10%). Eine Gewichtung ueber 25% wuerde eine Redundanz mit Pillar 4 (Trend-Deviation) erzeugen, da F&G bereits Volatilitaet und Trend-Daten enthaelt.

### Pillar 2: Derivate-Hitze / Funding Rate (Gewicht: 20%)

**Primaer:** OKX Public Funding Rate API (EU-lizenziert, kein Geo-Block)
- **Endpoint:** `GET https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP`
- **Auth:** Keine (oeffentlich)
- **Rate Limit:** 20 req/2s
- **Update:** Alle 8 Stunden (Settlement: 00:00, 08:00, 16:00 UTC)
- **Cache-TTL:** 30 Minuten

**Warum nicht Binance Futures:**
`fapi.binance.com` ist in der EU (Deutschland, Italien, Niederlande) aufgrund MiCA potentiell geo-blockiert. OKX hat EU-Lizenzen und liefert aeauivalente Daten.

**Mapping (Rolling-Percentile statt fixer Schwellwerte):**

Bevorzugt: Rolling Z-Score gegen 30-Tage-Historie:
```
z = (current_rate - mean_30d) / std_30d
score = sigmoid(z) * 100    # 0-100 normalisiert
```

Fallback (feste Schwellwerte, wenn Historie < 30 Tage):

| Funding Rate (pro 8h) | Score | Interpretation |
|------------------------|-------|----------------|
| < -0.03% | 0-10 | Extreme Fear (Shorts zahlen stark) |
| -0.03% bis -0.005% | 10-35 | Fear |
| -0.005% bis +0.02% | 35-65 | Neutral (0.01% = Default-Rate) |
| +0.02% bis +0.04% | 65-90 | Greed (Longs zahlen Aufschlag) |
| > +0.04% | 90-100 | Extreme Greed (nahe Binance-Cap 0.05%) |

**Wichtig:** 0.01%/8h ist der Default-Neutralwert (nicht bullish). Erst Abweichungen davon signalisieren Richtung.

### Pillar 3: Taker Buy/Sell Ratio (Gewicht: 20%)

**Quelle:** Binance Spot Klines API (bereits im Projekt verwendet)
- **Endpoint:** `GET https://api.binance.com/api/v3/klines?symbol=BTCEUR&interval=1d&limit=7`
- **Auth:** Keine (oeffentlich)
- **Rate Limit:** Weight 2 pro Request (6000 Weight/min gesamt - bereits im Projekt)
- **Cache-TTL:** 5 Minuten

**Daten aus Klines:**
- Index 5: `volume` (Gesamt-Volumen)
- Index 9: `taker_buy_base_asset_volume` (Taker-Kaufvolumen)
- Berechnung: `taker_sell_volume = volume - taker_buy_volume`
- Ratio: `buy_sell_ratio = taker_buy_volume / taker_sell_volume`

**Mapping (7-Tage-Durchschnitt der Ratio):**

| Buy/Sell Ratio (7d avg) | Score | Interpretation |
|--------------------------|-------|----------------|
| < 0.85 | 0-15 | Starker Verkaufsdruck |
| 0.85 - 0.95 | 15-40 | Leichter Verkaufsdruck |
| 0.95 - 1.05 | 40-60 | Neutral |
| 1.05 - 1.15 | 60-85 | Leichter Kaufdruck |
| > 1.15 | 85-100 | Starker Kaufdruck |

**Warum statt "On-Chain Flow Proxy":**
Die Original-Spezifikation nannte Pillar 3 "On-Chain/Flow Proxy", verwendete aber Price-to-DMA -- das ist ein technischer Indikator, kein On-Chain-Metrik. Taker Buy/Sell Ratio misst **tatsaechlichen Orderflow** (Market Orders) und ist ein genuiner Flow-Indikator. Echte On-Chain-Daten (Exchange Inflows, Whale Ratio) erfordern kostenpflichtige APIs (Glassnode ab $39/Monat) und sind fuer v1 nicht vorgesehen.

### Pillar 4: Trend-Deviation / DMA-Composite (Gewicht: 20%)

**Quelle:** Binance Spot Klines API (bereits im Projekt)
- **Endpoint:** `GET https://api.binance.com/api/v3/klines?symbol=BTCEUR&interval=1d&limit=200`
- **Auth:** Keine
- **Cache-TTL:** 15 Minuten (Close-Preise aendern sich laufend)

**Berechnung:**

**(A) Price Distance to 50-DMA:**
```
sma50 = mean(close_prices[-50:])
distance_50 = ((current_price - sma50) / sma50) * 100   # in Prozent
```

**(B) Regime-Filter via 200-DMA:**
```
sma200 = mean(close_prices[-200:])
bullish_regime = sma50 > sma200   # Golden Cross = Aufwaertstrend-Regime
```

**(C) Composite-Score:**

| Distance to 50-DMA | Bullish Regime (50>200) | Bearish Regime (50<200) |
|---------------------|------------------------|------------------------|
| > +15% | 95 (ueberhitzt) | 85 (Erholung, aber fragil) |
| +5% bis +15% | 75 | 65 |
| -5% bis +5% | 55 (gesunder Trend) | 45 (Seitwaerts in Baerenmarkt) |
| -15% bis -5% | 35 (Pullback im Aufwaertstrend) | 20 (Abwaertstrend bestaetigt) |
| < -15% | 20 (starke Korrektur) | 5 (Kapitulation) |

**Warum 50+200 DMA statt nur 50:**
50-DMA allein kann kurzfristige Pullbacks nicht von echten Trendwechseln unterscheiden. Die Kombination mit der 200-DMA als Regime-Filter (analog zum Golden/Death Cross) liefert kontextabhaengige Bewertungen.

### Pillar 5: Volume-Momentum (Gewicht: 20%)

**Quelle:** Binance Spot Klines API (bereits im Projekt)
- **Endpoint:** `GET https://api.binance.com/api/v3/klines?symbol=BTCEUR&interval=1d&limit=21`
- **Auth:** Keine
- **Cache-TTL:** 5 Minuten

**Berechnung:**
```
vol_20d_avg = mean(volumes[-20:])
vol_current = volume_today
vol_ratio = vol_current / vol_20d_avg
```

**Mapping:**

| Volume Ratio | Score | Interpretation |
|-------------|-------|----------------|
| < 0.5 | 30 | Sehr niedriges Volumen (Desinteresse) |
| 0.5 - 0.8 | 40 | Unterdurchschnittlich |
| 0.8 - 1.2 | 50 | Normal |
| 1.2 - 2.0 | 65 | Erhoehtes Interesse |
| > 2.0 | 80 | Extrem hohes Volumen (Panik oder Euphorie) |

**Richtungsanpassung:** Volume-Score wird mit Preis-Richtung kombiniert:
- Hohes Volumen + Preis steigend = Score nach oben anpassen (Greed)
- Hohes Volumen + Preis fallend = Score nach unten anpassen (Fear)

```python
if price_change_24h > 0:
    adjusted_score = base_vol_score  # Hohes Volume bei steigendem Preis = bullish
else:
    adjusted_score = 100 - base_vol_score  # Hohes Volume bei fallendem Preis = bearish
```

---

## 4. Scoring-Aggregation

### 4.1 Gewichteter Durchschnitt

```
raw_score = (fng_score * 0.20)
          + (funding_score * 0.20)
          + (taker_ratio_score * 0.20)
          + (dma_score * 0.20)
          + (volume_score * 0.20)
```

### 4.2 Concordance-Amplification (Non-Linear)

Wenn >=4 von 5 Pillars in dieselbe Richtung zeigen (alle >65 oder alle <35), wird der Score verstaerkt:

```python
pillar_scores = [fng, funding, taker, dma, volume]
above_65 = sum(1 for s in pillar_scores if s > 65)
below_35 = sum(1 for s in pillar_scores if s < 35)

CONCORDANCE_BONUS = Decimal("0.15")  # 15% Verstaerkung

if above_65 >= 4:
    # Starke Uebereinstimmung: Greed verstaerken
    concordance = CONCORDANCE_BONUS * (raw_score - 50)
    final_score = min(100, raw_score + concordance)
elif below_35 >= 4:
    # Starke Uebereinstimmung: Fear verstaerken
    concordance = CONCORDANCE_BONUS * (50 - raw_score)
    final_score = max(0, raw_score - concordance)
else:
    final_score = raw_score
```

**Warum:** Ein einfacher gewichteter Durchschnitt unterschaetzt Extremsituationen. Wenn alle unabhaengigen Signale gleichzeitig "Fear" zeigen, ist die Marktlage extremer als der Durchschnitt suggeriert. Akademische Forschung (Farzulla et al., 2025) bestaetigt, dass extreme Sentiment-Regimes ueberproportionale Herding-Effekte erzeugen.

### 4.3 Score-Klassifikation

| Score | Label | Farbe |
|-------|-------|-------|
| 0-15 | Extreme Fear | `#dc2626` (Rot) |
| 16-35 | Fear | `#f97316` (Orange) |
| 36-65 | Neutral | `#64748b` (Slate) |
| 66-85 | Greed | `#22c55e` (Hellgruen) |
| 86-100 | Extreme Greed | `#16a34a` (Gruen) |

---

## 5. Handlungsempfehlungen (Position-Sizing)

**Zentrale Design-Entscheidung:** Der Sentiment Score steuert **Position-Sizing**, nicht binaere Buy/Sell-Entscheidungen. Historische Analysen zeigen, dass die Contrarian-Strategie auf Cycle-Zeitebene (Monate) funktioniert, aber nicht zuverlaessig fuer kurzfristiges Timing ist.

| Score-Bereich | Empfehlung | Parameter-Anpassung |
|---------------|------------|---------------------|
| 0-15 (Extreme Fear) | Aggressiv akkumulieren | `buy_size_multiplier: 1.3` (+30%), tiefere Profit-Taking-Targets |
| 16-35 (Fear) | Leicht erhoehte Kaufgroessen | `buy_size_multiplier: 1.15` (+15%) |
| 36-65 (Neutral) | Standard-Parameter | `buy_size_multiplier: 1.0` (keine Anpassung) |
| 66-85 (Greed) | Vorsichtiger, engere Stops | `buy_size_multiplier: 0.85` (-15%), hoehere Profit-Targets |
| 86-100 (Extreme Greed) | Stark reduziert, De-Risking | `buy_size_multiplier: 0.7` (-30%), aggressives Profit-Taking |

**Warum nicht 20/80-Schwellen wie in der Original-Spezifikation:**
- Scores von 20-30 sind **haeufig**, nicht "extrem" -- echte Contrarian-Signale liegen bei <15 und >85
- Die profitabelste historische Strategie kauft bei F&G <= 10 (nicht 20)
- Position-Sizing ist robuster als binaere Trigger

---

## 6. Daten-Persistierung

### 6.1 Neues DB-Modell: SentimentHistoryDB

**Warum DB statt CSV:** Das bestehende Projekt verwendet SQLAlchemy/SQLite. Eine CSV-Datei wuerde das Architektur-Pattern brechen und bietet keine Query-Moeglichkeiten. Die Sentiment-Historie wird in einer neuen DB-Tabelle gespeichert.

```python
class SentimentHistoryDB(Base):
    """Historische Sentiment-Scores fuer Backtesting und Analyse."""
    __tablename__ = "sentiment_history"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Composite
    composite_score = Column(Numeric, nullable=False)       # 0-100
    composite_label = Column(String, nullable=False)         # "Extreme Fear" etc.
    concordance_applied = Column(Boolean, default=False)     # Ob Concordance aktiv war

    # Pillar-Scores (fuer Backtesting/Analyse)
    fng_score = Column(Numeric, nullable=True)               # 0-100 oder NULL
    funding_score = Column(Numeric, nullable=True)
    taker_ratio_score = Column(Numeric, nullable=True)
    dma_score = Column(Numeric, nullable=True)
    volume_score = Column(Numeric, nullable=True)

    # Rohdaten-Snapshot
    fng_raw_value = Column(Numeric, nullable=True)           # Original F&G Wert
    funding_rate_raw = Column(Numeric, nullable=True)        # Rohe Funding Rate
    taker_buy_sell_ratio = Column(Numeric, nullable=True)    # Rohe Ratio
    price_vs_50dma_pct = Column(Numeric, nullable=True)      # % Abstand
    volume_ratio = Column(Numeric, nullable=True)            # Vol / 20d-Avg

    # Metadaten
    active_pillars = Column(Integer, nullable=False)         # Wie viele Quellen aktiv
    total_pillars = Column(Integer, default=5)

    created_at = Column(DateTime, default=utcnow)
```

### 6.2 Speicher-Frequenz

- **1x pro Stunde** automatisch (via Service-Aufruf)
- **Bei jedem API-Call** wird der aktuelle Score berechnet, aber nur stuendlich persistiert
- **Retention:** Unbegrenzt (typisch: <400 Eintraege/Jahr, vernachlaessigbar)

---

## 7. API-Endpoints

| Route | Methode | Beschreibung |
|-------|---------|--------------|
| `/api/sentiment/{user_id}/current` | GET | Aktueller Sentiment Score + alle Pillar-Details |
| `/api/sentiment/{user_id}/history` | GET | Historische Scores (Query: `days=30`, `limit=100`) |

### 7.1 Response-Format: GET /api/sentiment/{user_id}/current

```json
{
  "composite_score": 28.5,
  "composite_label": "Fear",
  "composite_color": "#f97316",
  "concordance_applied": false,
  "recommendation": {
    "action": "Leicht erhoehte Kaufgroessen",
    "buy_size_multiplier": 1.15
  },
  "pillars": [
    {
      "name": "Fear & Greed Index",
      "score": 22,
      "raw_value": 22,
      "source": "alternative.me",
      "quality": "live",
      "weight": 0.20,
      "description": "Fear - Markt aengstlich"
    },
    {
      "name": "Funding Rate",
      "score": 35,
      "raw_value": -0.0012,
      "source": "okx",
      "quality": "live",
      "weight": 0.20,
      "description": "Leicht negativ - Shorts ueberwiegen"
    },
    {
      "name": "Taker Buy/Sell Ratio",
      "score": 38,
      "raw_value": 0.94,
      "source": "binance",
      "quality": "live",
      "weight": 0.20,
      "description": "Leichter Verkaufsdruck (7d avg)"
    },
    {
      "name": "Trend-Deviation (DMA)",
      "score": 25,
      "raw_value": -8.3,
      "source": "binance",
      "quality": "live",
      "weight": 0.20,
      "description": "-8.3% unter 50-DMA, Bearish Regime"
    },
    {
      "name": "Volume-Momentum",
      "score": 42,
      "raw_value": 0.87,
      "source": "binance",
      "quality": "live",
      "weight": 0.20,
      "description": "Unterdurchschnittliches Volumen"
    }
  ],
  "active_pillars": 5,
  "total_pillars": 5,
  "timestamp": "2026-02-14T12:00:00",
  "next_update": "2026-02-14T13:00:00"
}
```

---

## 8. Frontend-Integration

### 8.1 Neue Komponente: SentimentDashboard.jsx

**Navigation:** Neuer Tab "Sentiment" in der Navbar (neben Dashboard, TradeLots, Reconciliation, Settings, Makro-Signal)

**Layout:**

```
+------------------------------------------------------+
| SENTIMENT SCORE           Score: 28.5 / 100          |
| [=========>                                   ] Fear  |
| Empfehlung: Leicht erhoehte Kaufgroessen (1.15x)     |
+------------------------------------------------------+

+----------+ +----------+ +----------+ +----------+ +----------+
| Fear &   | | Funding  | | Taker    | | Trend    | | Volume   |
| Greed    | | Rate     | | Ratio    | | (DMA)    | | Momentum |
|   22     | |   35     | |   38     | |   25     | |   42     |
| "Fear"   | | "-0.12%" | | "0.94"   | | "-8.3%"  | | "0.87x"  |
| [======] | | [====  ] | | [===== ] | | [====  ] | | [=====]  |
+----------+ +----------+ +----------+ +----------+ +----------+

+------------------------------------------------------+
| HISTORIE (30 Tage)                                    |
| [Recharts AreaChart: Score ueber Zeit]               |
| Fear/Greed-Zonen als farbige Baender                  |
+------------------------------------------------------+
```

### 8.2 Styling (analog zu bestehenden Konventionen)

- **Akzentfarbe:** Amber/Gold `#f59e0b` (unterscheidbar von MacroSignal Purple, Reconciliation Blue)
- **Score-Bar:** Gradient von Rot (0) ueber Slate (50) zu Gruen (100)
- **Pillar-Karten:** Analog zu MacroSignal Indicator-Cards mit Quality-Badge
- **CSS:** `SentimentDashboard.css` (component-scoped, plain CSS)

### 8.3 API-Client Erweiterung

```javascript
// In api/client.js ergaenzen:
export const getSentimentCurrent = (userId) =>
  api.get(`/sentiment/${userId}/current`).then(r => r.data);

export const getSentimentHistory = (userId, days = 30) =>
  api.get(`/sentiment/${userId}/history`, { params: { days } }).then(r => r.data);
```

### 8.4 Polling

- **Refetch-Intervall:** 5 Minuten (Sentiment aendert sich langsamer als MacroSignal)
- **History-Chart:** Refetch alle 30 Minuten

---

## 9. Implementierungsplan

### Phase 1: Backend Domain + Service (Kern)

1. **`domain/sentiment.py`** - Pure Scoring-Funktionen:
   - `score_fear_and_greed(raw_value) -> Decimal`
   - `score_funding_rate(rate, history_30d) -> Decimal`
   - `score_taker_ratio(ratio_7d_avg) -> Decimal`
   - `score_dma_composite(price, sma50, sma200) -> Decimal`
   - `score_volume_momentum(vol_ratio, price_change_pct) -> Decimal`
   - `compute_sentiment(pillar_scores) -> SentimentResult`
   - `apply_concordance(raw_score, pillar_scores) -> Decimal`

2. **`services/sentiment_service.py`** - Daten-Fetching + Caching:
   - `SentimentService` (Singleton, analog zu `MacroDataService`)
   - `get_current_sentiment(user_id) -> SentimentResult`
   - Interne Methoden: `_fetch_fng()`, `_fetch_okx_funding()`, `_fetch_binance_klines()`
   - Cache pro Quelle mit individuellen TTLs
   - Funding-Rate-Historie (deque, 30 Tage) fuer Z-Score-Berechnung

3. **DB-Migration:** `SentimentHistoryDB` Tabelle via Alembic

### Phase 2: API + Frontend

4. **`api/routes/sentiment.py`** - HTTP-Endpoints
5. **`SentimentDashboard.jsx`** + `SentimentDashboard.css` - Frontend-Komponente
6. **`api/client.js`** - Erweiterung um Sentiment-Calls
7. **`App.jsx`** - Neuer Nav-Tab "Sentiment"

### Phase 3: Tests + Integration

8. **`tests/test_sentiment.py`** - Domain-Tests:
   - Alle 5 Pillar-Scoring-Funktionen
   - Concordance-Amplification
   - Graceful Degradation (fehlende Quellen)
   - Edge Cases (Division by Zero, leere Historie)
9. **`tests/test_sentiment_service.py`** - Service-Integration-Tests (mit Mocks)
10. **Manueller E2E-Test** mit echten API-Daten

---

## 10. Konfiguration

### 10.1 Environment Variables (.env)

```bash
# Optional: CoinMarketCap API Key (Fallback fuer Fear & Greed)
CMC_API_KEY=                    # Leer = nur Alternative.me verwenden

# Sentiment-spezifisch
SENTIMENT_HISTORY_INTERVAL=3600  # Persistierung alle 3600 Sekunden (1h)
```

### 10.2 User-Settings (Erweiterung UserSettingsDB)

| Setting | Default | Beschreibung |
|---------|---------|------------|
| `sentiment_enabled` | `true` | Sentiment-Feature aktiviert |
| `sentiment_buy_multiplier_extreme_fear` | `1.30` | Kaufgroessen-Multiplikator bei Extreme Fear |
| `sentiment_buy_multiplier_fear` | `1.15` | Bei Fear |
| `sentiment_buy_multiplier_greed` | `0.85` | Bei Greed |
| `sentiment_buy_multiplier_extreme_greed` | `0.70` | Bei Extreme Greed |

---

## 11. Fehlerbehandlung & Graceful Degradation

| Szenario | Verhalten |
|----------|-----------|
| Alternative.me nicht erreichbar | Pillar 1 Score = 50 (Neutral), Quality = "unavailable" |
| OKX nicht erreichbar | Pillar 2 Score = 50, Quality = "unavailable" |
| Binance Klines fehlschlagen | Pillar 3-5 Score = 50, Quality = "unavailable" |
| Weniger als 30 Tage Funding-Historie | Fallback auf feste Schwellwerte (statt Z-Score) |
| Weniger als 200 Tage Klines | 200-DMA nicht berechnen, nur 50-DMA verwenden |
| Alle Quellen down | Composite = 50, Label = "Neutral (keine Daten)", active_pillars = 0 |

**Qualitaets-Warnung:** Wenn `active_pillars < 3`, wird im Frontend ein Warning-Badge angezeigt: "Eingeschraenkte Datenlage - Score nicht zuverlaessig".

---

## 12. Sicherheit

- **API-Keys** nur via `.env` (niemals hardcoded)
- **Bestehende `X-API-Key` Authentication** schuetzt alle neuen Endpoints
- **Keine Binance-Credentials noetig** - alle Quellen sind oeffentlich (ausser optionaler CMC-Fallback)
- **Rate-Limit-Aware:** Binance Klines teilen sich das Weight-Budget mit bestehendem MacroDataService
  - Gesamtbudget: 6000 Weight/min
  - MacroSignal: ~20 Weight/min (bei 30s Polling)
  - SentimentEngine: ~6 Weight/min (bei 5min Polling, 3 Kline-Requests a 2 Weight)
  - Reserve: >5900 Weight/min

---

## 13. Offene Punkte (v2.0+)

| Feature | Prioritaet | Abhaengigkeit |
|---------|-----------|---------------|
| Combined Score (MacroSignal + Sentiment) | Hoch | Nach Validierung beider Systeme |
| Social Sentiment (Twitter/X, Reddit) | Mittel | NLP-Modell oder externe API (LunarCrush, Santiment) |
| Echte On-Chain-Daten (Exchange Flows) | Mittel | Glassnode/CryptoQuant Subscription ($39+/Monat) |
| Open Interest Changes | Mittel | OKX API erweiterbar |
| MVRV Z-Score | Niedrig | Glassnode Subscription |
| Stablecoin Supply Ratio (SSR) | Niedrig | CryptoQuant oder DefiLlama |
| WebSocket statt Polling | Niedrig | Allgemeines Infrastruktur-Upgrade |
| Backtesting-Modul | Niedrig | Nach 3+ Monaten Daten-Sammlung |
| Auto-Order Integration | Hoch | Erst nach Iteration 4 (Auto-Order Automation) |

---

## 14. Akzeptanzkriterien

1. **Score reproduzierbar:** Gleiche Rohdaten liefern identischen Score (deterministische Domain-Logik)
2. **Graceful Degradation:** System funktioniert mit 1-5 aktiven Pillars
3. **EU-kompatibel:** Keine Abhaengigkeit von geo-blockierten APIs
4. **Keine Float-Arithmetik:** Alle Scores intern als Decimal
5. **Concordance korrekt:** Bei >=4 uebereinstimmenden Pillars wird Score verstaerkt
6. **History persistent:** Stuendliche Scores in DB gespeichert
7. **Frontend zeigt:** Composite Score, alle 5 Pillar-Karten, History-Chart, Empfehlung
8. **Tests:** >=90% Coverage fuer `domain/sentiment.py`
9. **Performance:** API-Response < 2s (cached) / < 10s (cold start, alle Fetches)
