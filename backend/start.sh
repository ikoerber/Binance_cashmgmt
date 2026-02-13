#!/bin/bash
# Backend Startup Script

# Aktiviere venv
source venv/bin/activate

# Starte Server
echo "🚀 Starting BTC/EUR Cashflow Management API..."
echo "📍 API: http://localhost:8000"
echo "📚 Docs: http://localhost:8000/docs"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
