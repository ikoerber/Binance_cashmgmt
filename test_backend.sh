#!/bin/bash
# Quick Backend Test Script

API_URL="http://localhost:8000"
USER_ID="user_123"
MARKET_PRICE="50000"

echo "🧪 Testing BTC/EUR Cashflow Management API"
echo "============================================"
echo ""

# Test 1: Health Check
echo "1️⃣  Health Check..."
response=$(curl -s "${API_URL}/health")
if echo "$response" | grep -q "healthy"; then
    echo "   ✅ API is healthy"
else
    echo "   ❌ API nicht erreichbar. Backend läuft?"
    exit 1
fi
echo ""

# Test 2: Root Endpoint
echo "2️⃣  Root Endpoint..."
curl -s "${API_URL}/" | python3 -m json.tool
echo ""

# Test 3: Portfolio (wird leer sein bis Fills synchronisiert wurden)
echo "3️⃣  Portfolio abrufen..."
response=$(curl -s "${API_URL}/api/portfolio/${USER_ID}?market_price=${MARKET_PRICE}")
if echo "$response" | grep -q "timestamp"; then
    echo "   ✅ Portfolio API funktioniert"
    echo "$response" | python3 -m json.tool
else
    echo "   ⚠️  Portfolio API Fehler:"
    echo "$response" | python3 -m json.tool
fi
echo ""

# Test 4: Lots abrufen
echo "4️⃣  TradeLots abrufen..."
response=$(curl -s "${API_URL}/api/lots/${USER_ID}?limit=10")
if echo "$response" | grep -q "lots"; then
    lot_count=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])")
    echo "   ✅ Lots API funktioniert (${lot_count} Lots gefunden)"

    if [ "$lot_count" -eq "0" ]; then
        echo "   ℹ️  Keine Lots vorhanden. Synchronisiere zuerst Fills!"
    fi
else
    echo "   ⚠️  Lots API Fehler"
fi
echo ""

# Test 5: Pairing Suggestions
echo "5️⃣  Pairing Suggestions..."
response=$(curl -s "${API_URL}/api/pairing/${USER_ID}/suggestions?market_price=${MARKET_PRICE}&threshold_pct=0.05")
if echo "$response" | grep -q "suggestions"; then
    suggestion_count=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])")
    echo "   ✅ Pairing API funktioniert (${suggestion_count} Vorschläge)"
else
    echo "   ⚠️  Pairing API Fehler"
fi
echo ""

echo "============================================"
echo "✅ Backend Test abgeschlossen!"
echo ""
echo "📚 API Dokumentation: ${API_URL}/docs"
echo ""
echo "🔄 Nächster Schritt: Binance Fills synchronisieren"
echo "   curl -X POST \"${API_URL}/api/sync/${USER_ID}/fills?symbol=BTCEUR\""
echo ""
