"""FastAPI Main Application"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import require_api_key
from dotenv import load_dotenv

# Load .env file BEFORE importing routes
load_dotenv()

from app.db.database import init_db, create_tables
from app.api.routes import (
    portfolio,
    lots,
    sync,
    pairing,
    orders,
    reconciliation,
    cashflow,
    settings,
    macro,
    sentiment,
    orderblock,
    combined,
)
from app.api.routes import websocket as websocket_route
from app.services.websocket_manager import get_stream_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisiert DB, Sentiment-Historien und WebSocket Manager beim Start"""
    database_url = os.getenv("DATABASE_URL", "sqlite:///./cashmgnt.db")
    init_db(database_url)
    create_tables()
    # Sentiment-Historien vorinitialisieren (vermeidet 60s Delay beim ersten Request)
    from app.services.sentiment_data_service import get_sentiment_data_service

    service = get_sentiment_data_service()
    await asyncio.to_thread(service.initialize)

    # WebSocket Manager starten (Binance Streams)
    stream_manager = get_stream_manager()
    await stream_manager.start()
    await stream_manager.start_user_data_stream()

    yield

    # WebSocket Manager stoppen
    await stream_manager.stop()


# App erstellen (OHNE globale Auth-Dependency — WebSocket unterstuetzt kein APIKeyHeader)
app = FastAPI(
    title="BTC/EUR Cashflow Management API",
    description="Ledger-first, deterministisches Cashflow-Tracking für BTC/EUR Trading",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS für Frontend
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-Key Auth als Router-Dependency (statt global, weil APIKeyHeader nicht mit WebSocket kompatibel)
api_auth = [Depends(require_api_key)]

# HTTP Routes (mit API-Key Auth)
app.include_router(portfolio.router, dependencies=api_auth)
app.include_router(lots.router, dependencies=api_auth)
app.include_router(sync.router, dependencies=api_auth)
app.include_router(pairing.router, dependencies=api_auth)
app.include_router(orders.router, dependencies=api_auth)
app.include_router(reconciliation.router, dependencies=api_auth)
app.include_router(cashflow.router, dependencies=api_auth)
app.include_router(settings.router, dependencies=api_auth)
app.include_router(macro.router, dependencies=api_auth)
app.include_router(sentiment.router, dependencies=api_auth)
app.include_router(orderblock.router, dependencies=api_auth)
app.include_router(combined.router, dependencies=api_auth)

# WebSocket Route (eigene Auth via Query-Parameter, kein APIKeyHeader)
app.include_router(websocket_route.router)


@app.get("/")
def root():
    """Health Check"""
    return {"status": "ok", "app": "BTC/EUR Cashflow Management", "version": "0.1.0"}


@app.get("/api/websocket/stats")
def websocket_stats():
    """WebSocket Verbindungsstatistiken"""
    return get_stream_manager().get_stats()


@app.get("/health")
def health():
    """Health Check Endpoint"""
    return {"status": "healthy"}


@app.get("/api/server-ip")
def server_ip():
    """Gibt die öffentliche IP des Servers zurück (für Binance IP-Whitelisting)"""
    import urllib.request

    try:
        ip = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode()
        return {"ip": ip}
    except Exception:
        return {"ip": None}
