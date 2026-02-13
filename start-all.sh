#!/bin/bash
# Startet Backend + Frontend gleichzeitig

echo "🚀 Starting BTC/EUR Cashflow Management System..."
echo ""

# Backend starten (im Hintergrund)
echo "📦 Starting Backend..."
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Warte 3 Sekunden
sleep 3

# Frontend starten
echo "🎨 Starting Frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ System gestartet!"
echo "📍 Backend:  http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo "🎨 Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers..."

# Warte auf Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
