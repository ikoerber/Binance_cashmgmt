"""FastAPI Main Application"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import require_api_key, validate_user_id, validate_startup_config
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
    alerts,
    alpha_score,
    backtest,
    dry_run,
    health,
)
from app.api.routes import websocket as websocket_route
from app.services.websocket_manager import get_stream_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisiert DB, Sentiment-Historien und WebSocket Manager beim Start"""
    # Sicherheitskonfiguration pruefen (blockiert Production ohne API_SECRET_KEY)
    validate_startup_config()

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

    # Dry-Run Service starten
    from app.services.dry_run_service import get_dry_run_service

    dry_run_svc = get_dry_run_service()
    await dry_run_svc.start()

    # Telegram Notifier starten (nach anderen Services, fuer sinnvolle Health-Checks)
    from app.services.telegram_notifier import get_telegram_notifier

    notifier = get_telegram_notifier()
    await notifier.start()

    yield

    # Dry-Run Service stoppen
    await dry_run_svc.stop()

    # Telegram Notifier stoppen
    await notifier.stop()

    # WebSocket Manager stoppen
    await stream_manager.stop()


# App erstellen (OHNE globale Auth-Dependency — WebSocket unterstuetzt kein APIKeyHeader)
app = FastAPI(
    title="BTC/EUR Cashflow Management API",
    description="Ledger-first, deterministisches Cashflow-Tracking für BTC/EUR Trading",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS für Frontend (explizite Methods/Headers statt Wildcard)
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
    max_age=3600,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Security-Headers fuer alle HTTP-Responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    return response


# API-Key Auth + User-ID-Validierung als Router-Dependencies
# (nicht global, weil APIKeyHeader nicht mit WebSocket kompatibel)
api_auth = [Depends(require_api_key)]
api_auth_with_user = [Depends(require_api_key), Depends(validate_user_id)]

# HTTP Routes mit Auth + User-ID-Validierung (alle Routen mit {user_id} im Pfad)
app.include_router(portfolio.router, dependencies=api_auth_with_user)
app.include_router(lots.router, dependencies=api_auth_with_user)
app.include_router(sync.router, dependencies=api_auth_with_user)
app.include_router(pairing.router, dependencies=api_auth_with_user)
app.include_router(orders.router, dependencies=api_auth_with_user)
app.include_router(reconciliation.router, dependencies=api_auth_with_user)
app.include_router(cashflow.router, dependencies=api_auth_with_user)
app.include_router(settings.router, dependencies=api_auth_with_user)
app.include_router(sentiment.router, dependencies=api_auth_with_user)
app.include_router(orderblock.router, dependencies=api_auth_with_user)
app.include_router(combined.router, dependencies=api_auth_with_user)
app.include_router(alerts.router, dependencies=api_auth_with_user)
app.include_router(alpha_score.router, dependencies=api_auth_with_user)
app.include_router(backtest.router, dependencies=api_auth_with_user)
app.include_router(dry_run.router, dependencies=api_auth_with_user)
app.include_router(health.router, dependencies=api_auth_with_user)

# HTTP Routes nur mit Auth (keine {user_id} im Pfad)
app.include_router(macro.router, dependencies=api_auth)

# WebSocket Route (eigene Auth via Query-Parameter, kein APIKeyHeader)
app.include_router(websocket_route.router)


@app.get("/")
def root():
    """Health Check"""
    return {"status": "ok", "app": "BTC/EUR Cashflow Management", "version": "0.1.0"}


@app.get("/api/websocket/stats", dependencies=api_auth)
def websocket_stats():
    """WebSocket Verbindungsstatistiken"""
    return get_stream_manager().get_stats()


@app.get("/health")
def health():
    """Health Check Endpoint"""
    return {"status": "healthy"}


@app.get("/api/server-ip", dependencies=api_auth)
def server_ip():
    """Gibt die öffentliche IP des Servers zurück (für Binance IP-Whitelisting)"""
    import urllib.request

    try:
        ip = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode()
        return {"ip": ip}
    except Exception:
        return {"ip": None}
