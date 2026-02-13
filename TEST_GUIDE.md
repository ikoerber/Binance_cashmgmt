# Test-Anleitung: Backend mit echten Binance-Daten

## Voraussetzungen

1. **Binance Account** (Spot Trading)
2. **API-Keys** mit Trading-Berechtigung
3. **Mindestens 1 BTC/EUR Trade** auf Binance (für Test-Daten)

## Schritt-für-Schritt Anleitung

### 1. Binance API-Keys erstellen

1. Gehe zu [Binance API Management](https://www.binance.com/en/my/settings/api-management)
2. Erstelle neuen API-Key
3. Aktiviere Berechtigungen:
   - ✅ Enable Reading
   - ✅ Enable Spot & Margin Trading
   - ❌ Enable Withdrawals (NICHT aktivieren!)
4. Notiere **API Key** und **Secret Key**

### 2. Backend konfigurieren

```bash
cd backend

# .env Datei bearbeiten
nano .env
```

Füge ein:
```env
# Database
DATABASE_URL=sqlite:///./cashmgnt.db

# Binance API
BINANCE_API_KEY=dein_api_key_hier
BINANCE_API_SECRET=dein_api_secret_hier
BINANCE_TESTNET=false  # false für Production, true für Testnet

# App
APP_ENV=development
LOG_LEVEL=INFO
```

**⚠️ WICHTIG:**
- `.env` ist in `.gitignore` → wird NICHT committet
- Secrets NIEMALS in Code oder Git einchecken!

### 3. Test-User in DB anlegen

```bash
cd backend
source venv/bin/activate
python setup_test_user.py
```

Output:
```
✅ User 'user_123' erfolgreich erstellt!
   Email: test@example.com
   ID: user_123
```

### 4. Backend starten

```bash
# Im backend/ Verzeichnis
source venv/bin/activate
uvicorn app.main:app --reload
```

Backend läuft auf: http://localhost:8000

### 5. Binance Fills synchronisieren

**Option A: Via Swagger UI** (empfohlen für erste Tests)

1. Öffne http://localhost:8000/docs
2. Gehe zu `POST /api/sync/{user_id}/fills`
3. Klicke "Try it out"
4. Fülle aus:
   - `user_id`: `user_123`
   - `symbol`: `BTCEUR`
   - `start_time`: (leer lassen oder z.B. `2024-01-01T00:00:00`)
5. Klicke "Execute"

**Option B: Via curl**

```bash
curl -X POST "http://localhost:8000/api/sync/user_123/fills?symbol=BTCEUR"
```

**Erwartete Response:**
```json
{
  "status": "success",
  "new_fills": 10,
  "new_lots": 6,
  "allocations": 4,
  "message": "Synced 10 fills, created 6 lots, 4 allocations"
}
```

### 6. Portfolio abrufen

**Aktuellen BTC/EUR Preis holen:**

```bash
# Via Binance API (in Python)
python -c "from binance.client import Client; import os; c = Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET')); print(c.get_symbol_ticker(symbol='BTCEUR')['price'])"
```

Dann Portfolio abrufen:

```bash
# Beispiel mit Preis 50000 EUR
curl "http://localhost:8000/api/portfolio/user_123?market_price=50000"
```

**Response:**
```json
{
  "timestamp": "2024-02-10T20:00:00",
  "btc_qty": "0.05",
  "btc_cost_basis_eur": "2500.00",
  "break_even": "50000.00",
  "eur_available": "1000.00",
  "market_price": "52000.00",
  "market_value_eur": "2600.00",
  "unrealized_pnl_eur": "100.00",
  "realized_pnl_eur": "50.00",
  "external_net_eur": "0.00",
  "target_price": "52500.00",
  "target_margin_pct": "0.05"
}
```

### 7. TradeLots anzeigen

```bash
# Alle offenen Lots
curl "http://localhost:8000/api/lots/user_123?status=OPEN"

# Alle Lots (inkl. geschlossene)
curl "http://localhost:8000/api/lots/user_123"
```

### 8. Pairing-Vorschläge

```bash
curl "http://localhost:8000/api/pairing/user_123/suggestions?market_price=52000&threshold_pct=0.05"
```

### 9. Auto-Order erstellen (⚠️ Vorsicht!)

**WICHTIG:** Dies erstellt eine ECHTE Order auf Binance!

```bash
# Limit-Sell-Order für ein Lot erstellen
curl -X POST "http://localhost:8000/api/orders/user_123/lot/lot_fill_123/create?target_margin_pct=0.05&fee_buffer_pct=0.002"
```

**Response:**
```json
{
  "status": "success",
  "order_id": 123456789,
  "client_order_id": "user_123_lot_fill_123_52500_1000_v1",
  "symbol": "BTCEUR",
  "side": "SELL",
  "type": "LIMIT",
  "quantity": 0.01,
  "price": 52500.00,
  "lot_id": "lot_fill_123",
  "break_even": "50000.00",
  "target_margin_pct": "0.05"
}
```

### 10. Offene Orders anzeigen

```bash
curl "http://localhost:8000/api/orders/open?symbol=BTCEUR"
```

### 11. Order canceln

```bash
curl -X DELETE "http://localhost:8000/api/orders/123456789?symbol=BTCEUR"
```

## Frontend mit echten Daten

1. Backend muss laufen (siehe oben)
2. Fills müssen synchronisiert sein (siehe Schritt 5)
3. Frontend starten:

```bash
cd frontend
npm run dev
```

4. Öffne http://localhost:5173
5. Dashboard zeigt jetzt echte Portfolio-Daten! 🎉

## Troubleshooting

### "Binance credentials not configured"

→ `.env` Datei prüfen, API-Keys korrekt?

```bash
cd backend
cat .env | grep BINANCE
```

### "Invalid API-key, IP, or permissions for action"

→ API-Key Berechtigungen prüfen auf Binance:
- Reading: ✅
- Spot Trading: ✅
- IP-Whitelist (wenn aktiviert): Deine IP hinzufügen

### "No new fills to sync"

→ Keine Trades auf Binance vorhanden oder bereits synchronisiert

Lösung:
```bash
# Prüfe ob Trades existieren
curl "http://localhost:8000/api/lots/user_123"

# Falls leer: Manuell einen Trade auf Binance machen (kleine Menge!)
# Dann erneut synchronisieren
```

### "Lot not found"

→ Lot-ID falsch oder Lot existiert nicht

Lösung:
```bash
# Liste alle Lots
curl "http://localhost:8000/api/lots/user_123"

# Verwende eine existierende lot_id
```

## Sicherheitshinweise

⚠️ **Produktionsumgebung:**
- API-Keys NIEMALS committen
- IP-Whitelist auf Binance aktivieren
- Withdrawal-Berechtigung NICHT aktivieren
- Kleine Test-Beträge verwenden
- Orders vor Ausführung doppelt prüfen

⚠️ **Testnet verwenden (empfohlen für erste Tests):**

1. Registriere auf [Binance Testnet](https://testnet.binance.vision/)
2. Erstelle Testnet API-Keys
3. Setze in `.env`: `BINANCE_TESTNET=true`
4. Verwende Testnet Coins (keine echten Trades!)

## Nächste Schritte

- [ ] Alle Endpoints testen
- [ ] Frontend mit echten Daten testen
- [ ] Pairing ausprobieren (Simulation)
- [ ] Auto-Order im Testnet testen
- [ ] Bei Erfolg: Production mit kleinen Beträgen

Viel Erfolg! 🚀
