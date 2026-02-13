# Datenbank Rebuild von Binance

Dieses Dokument beschreibt, wie die Datenbank komplett neu aus Binance-Daten erstellt wird.

## ✅ Was wurde korrigiert

1. **BNB-Fee-Konvertierung** - BNB-Gebühren werden jetzt korrekt in EUR umgerechnet
2. **UTC-Timestamps** - Alle Zeitstempel werden korrekt in UTC gespeichert
3. **EXTERNAL_CASHFLOW** - EUR-Deposits/Withdrawals als EXTERNAL_CASHFLOW erfasst

## 🚀 Schnellstart

### 1. API-Credentials vorbereiten

Du benötigst deine Binance API-Credentials. Diese erhältst du auf:
- **Production**: https://www.binance.com/en/my/settings/api-management
- **Testnet**: https://testnet.binance.vision/

**Wichtig:** Die API-Keys benötigen folgende Berechtigungen:
- ✅ **Read** (Enable Reading)
- ❌ **Trade** (nicht benötigt für Rebuild)
- ❌ **Withdrawals** (nicht benötigt für Rebuild)

### 2. Environment Variables setzen

```bash
# Production Binance
export BINANCE_API_KEY='your_api_key_here'
export BINANCE_API_SECRET='your_api_secret_here'
export BINANCE_TESTNET='false'

# ODER für Testnet
export BINANCE_API_KEY='testnet_api_key'
export BINANCE_API_SECRET='testnet_api_secret'
export BINANCE_TESTNET='true'
```

**Sicherheit:**
- ⚠️ Niemals API-Keys committen!
- ⚠️ Keys in `.env` speichern und `.gitignore` hinzufügen
- ✅ Oder direkt in der Shell exportieren

### 3. Virtual Environment aktivieren

```bash
cd /Users/ikoerber/AIProjects/cashmgnt/backend
source venv/bin/activate
```

### 4. Rebuild ausführen

```bash
python rebuild_db_from_binance.py
```

## 📊 Was das Script macht

Das Script führt folgende Schritte aus:

### Step 1: Delete old database
- Löscht `cashmgnt.db` falls vorhanden

### Step 2: Create new database
- Erstellt neue SQLite-Datenbank
- Erstellt alle Tabellen (users, ledger_events, trade_lots, etc.)

### Step 3: Create default user
- Erstellt Standard-User `user_123`

### Step 4: Initialize Binance Service
- Verbindet mit Binance API
- Mit korrektem UTC-Timestamp-Handling

### Step 5: Sync Trades/Fills (BTC/EUR)
- Holt alle Trades von Binance
- Erstellt Ledger Events
- Erstellt TradeLots (1 Fill = 1 Lot)
- Führt FIFO-Allocation für Sells durch
- **Mit BNB-Fee-Konvertierung!**

### Step 6: Sync Deposits
- EUR-Deposits → `EXTERNAL_CASHFLOW`
- BTC-Deposits → `DEPOSIT`

### Step 7: Sync Withdrawals
- EUR-Withdrawals → `EXTERNAL_CASHFLOW` (negativ)
- BTC-Withdrawals → `WITHDRAWAL`

### Step 8: Verify and Report
- Zeigt Statistiken:
  - Anzahl Events (Fills, Deposits, Withdrawals, Cashflows)
  - Anzahl TradeLots (total, open)
  - Anzahl Sell-Allocations

### Step 9: Check Balances
- Zeigt aktuelle Binance-Balances (BTC, EUR, BNB)

## 📝 Beispiel-Output

```
================================================================================
🔄 DATABASE REBUILD FROM BINANCE
================================================================================

Step 1: Delete old database
--------------------------------------------------------------------------------
Deleting old database: cashmgnt.db
✅ Old database deleted

Step 2: Create new database
--------------------------------------------------------------------------------
Creating all tables...
✅ All tables created

Step 3: Create default user
--------------------------------------------------------------------------------
✅ User created: user_123

Step 4: Initialize Binance Service
--------------------------------------------------------------------------------
Using Testnet: False
✅ Binance Service initialized

Step 5: Sync Trades/Fills (BTC/EUR)
--------------------------------------------------------------------------------
INFO: Using current BNB/EUR price: 700.50 for fee conversion
✅ Synced 187 fills
   - Created 145 lots
   - Created 42 allocations
   - Message: Synced 187 fills, created 145 lots, 42 allocations

Step 6: Sync Deposits (EUR → EXTERNAL_CASHFLOW, BTC → DEPOSIT)
--------------------------------------------------------------------------------
Found 5 EUR deposits
Found 0 BTC deposits
✅ Synced 5 deposits

Step 7: Sync Withdrawals (EUR → EXTERNAL_CASHFLOW, BTC → WITHDRAWAL)
--------------------------------------------------------------------------------
Found 2 EUR withdrawals
Found 0 BTC withdrawals
✅ Synced 2 withdrawals

Step 8: Verify and Report
--------------------------------------------------------------------------------
Database Contents:
  Total Events: 194
    - Trade Fills: 187
    - Deposits: 0
    - Withdrawals: 0
    - External Cashflows: 7
  Total Lots: 145
    - Open Lots: 103
  Total Sell Allocations: 42

Step 9: Check Balances
--------------------------------------------------------------------------------
Current Binance Balances:
  BTC: 0.05382 (free: 0.05382, locked: 0.0)
  EUR: 1523.45 (free: 1523.45, locked: 0.0)
  BNB: 0.12345 (free: 0.12345, locked: 0.0)

================================================================================
✅ DATABASE REBUILD COMPLETE!
================================================================================

Next steps:
1. Verify data: sqlite3 cashmgnt.db
2. Start API server: uvicorn app.main:app --reload
3. Check portfolio: http://localhost:8000/api/portfolio
```

## 🔍 Daten verifizieren

### Mit SQLite direkt prüfen

```bash
sqlite3 cashmgnt.db

# Events anzeigen
SELECT type, COUNT(*) FROM ledger_events GROUP BY type;

# Neueste Events
SELECT type, timestamp, asset, amount, fee_asset, fee_amount
FROM ledger_events
ORDER BY timestamp DESC
LIMIT 10;

# Offene Lots
SELECT id, qty_btc_open, cost_eur, cost_eur/qty_btc_initial as break_even
FROM trade_lots
WHERE qty_btc_open > 0
ORDER BY created_at DESC;
```

### Mit API prüfen

```bash
# Server starten
uvicorn app.main:app --reload

# Portfolio abrufen
curl http://localhost:8000/api/portfolio

# Lots abrufen
curl http://localhost:8000/api/lots?status=OPEN
```

## 🐛 Troubleshooting

### "Binance API credentials not found"
→ Environment Variables nicht gesetzt. Siehe Step 2.

### "BinanceAPIException: Invalid API-key"
→ API-Key falsch oder abgelaufen. Prüfe auf Binance.

### "BinanceAPIException: Timestamp for this request is outside of the recvWindow"
→ Systemuhr nicht korrekt. Synchronisiere Zeit:
```bash
# macOS
sudo sntp -sS time.apple.com

# Linux
sudo ntpdate pool.ntp.org
```

### "WARNING: BNB fee detected but no conversion rate provided"
→ BNB/EUR-Paar nicht verfügbar oder Rate-Limit erreicht. Script läuft trotzdem.

### Leere Deposit/Withdrawal-Historie
→ Normal, wenn keine Deposits/Withdrawals vorhanden sind oder API-Keys keine Berechtigung haben.

## 🔒 Sicherheit

- ✅ API-Keys niemals committen
- ✅ Keys nur mit **Read-Only** Berechtigung verwenden
- ✅ IP-Whitelist auf Binance aktivieren (optional)
- ✅ API-Keys nach Nutzung deaktivieren/löschen (optional)
- ⚠️ Binance Testnet für Tests verwenden

## 📚 Weitere Informationen

- **Binance API Docs**: https://binance-docs.github.io/apidocs/spot/en/
- **CLAUDE.md**: Vollständige Spezifikation im Projekt-Root
- **Tests**: `pytest tests/` - Alle Tests sollten nach Rebuild bestehen
