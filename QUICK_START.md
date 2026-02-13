# 🚀 Quick Start - Backend mit deinen Binance-Daten

## ✅ Setup abgeschlossen!

Dein Binance Account ist verbunden:
- **BTC**: 0.155 BTC (davon 0.08 in Orders)
- **EUR**: 2733.40 EUR (davon 2714.75 in Orders)
- **Account Type**: SPOT
- **Trading**: Enabled ✅

## Starte das System

### Terminal 1: Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

✅ Backend läuft auf http://localhost:8000

### Terminal 2: Binance Fills synchronisieren

```bash
# Prüfe ob Backend läuft
curl http://localhost:8000/health

# Synchronisiere alle BTC/EUR Fills
curl -X POST "http://localhost:8000/api/sync/user_123/fills?symbol=BTCEUR"
```

**Erwartete Response:**
```json
{
  "status": "success",
  "new_fills": XX,
  "new_lots": XX,
  "allocations": XX
}
```

### Terminal 3: Portfolio anzeigen

```bash
# Hole aktuellen BTC/EUR Preis
curl "https://api.binance.com/api/v3/ticker/price?symbol=BTCEUR"

# Beispiel: Preis ist 84500 EUR
curl "http://localhost:8000/api/portfolio/user_123?market_price=84500"
```

**Response zeigt:**
```json
{
  "btc_qty": "0.15524132",
  "btc_cost_basis_eur": "XX",
  "break_even": "XX",
  "unrealized_pnl_eur": "XX",
  "realized_pnl_eur": "XX",
  "target_price": "XX"
}
```

## Starte Frontend

### Terminal 4: Frontend

```bash
cd frontend
npm run dev
```

✅ Frontend läuft auf http://localhost:5173

**Das Dashboard zeigt jetzt deine echten Portfolio-Daten! 📊**

## Weitere Endpoints testen

### 1. TradeLots anzeigen

```bash
# Alle offenen Lots
curl "http://localhost:8000/api/lots/user_123?status=OPEN"

# Lot-Details
curl "http://localhost:8000/api/lots/user_123/lot_fill_XXX"
```

### 2. Pairing-Vorschläge

```bash
curl "http://localhost:8000/api/pairing/user_123/suggestions?market_price=84500&threshold_pct=0.05"
```

### 3. Offene Orders anzeigen

```bash
curl "http://localhost:8000/api/orders/open?symbol=BTCEUR"
```

### 4. Auto-Order erstellen (⚠️ Vorsicht!)

**WICHTIG:** Dies erstellt eine ECHTE Order auf Binance!

```bash
# Erst Lots anzeigen, um eine Lot-ID zu bekommen
curl "http://localhost:8000/api/lots/user_123?status=OPEN"

# Dann Order erstellen (ersetze LOT_ID mit echter ID)
curl -X POST "http://localhost:8000/api/orders/user_123/lot/LOT_ID/create?target_margin_pct=0.05&fee_buffer_pct=0.002"
```

## API Dokumentation

Interaktive API-Docs: http://localhost:8000/docs

Hier kannst du alle Endpoints direkt testen! 📚

## Troubleshooting

### Backend startet nicht

```bash
cd backend
source venv/bin/activate
python test_env.py  # Prüft Binance Connection
```

### Keine Fills nach Sync

→ Prüfe ob du BTC/EUR Trades auf Binance hast:
```bash
# Direkt bei Binance prüfen
python -c "from binance.client import Client; import os; from dotenv import load_dotenv; load_dotenv(); c = Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET')); trades = c.get_my_trades(symbol='BTCEUR', limit=5); print(f'Anzahl Trades: {len(trades)}'); [print(f\"Trade: {t['qty']} BTC @ {t['price']} EUR\") for t in trades]"
```

### Frontend zeigt keine Daten

1. Backend muss laufen (Port 8000)
2. Fills müssen synchronisiert sein
3. Browser Console prüfen (F12)

## Nächste Schritte

- ✅ Portfolio analysieren
- ✅ TradeLots durchsehen
- ✅ Pairing-Vorschläge checken
- ⚠️ Auto-Orders testen (vorsichtig!)

**Viel Erfolg mit deinem Trading System! 🎯**
