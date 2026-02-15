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
from app.api.routes import portfolio, lots, sync, pairing, orders, reconciliation, cashflow, settings, macro, sentiment


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisiert DB und Sentiment-Historien beim Start"""
    database_url = os.getenv("DATABASE_URL", "sqlite:///./cashmgnt.db")
    init_db(database_url)
    create_tables()
    # Sentiment-Historien vorinitialisieren (vermeidet 60s Delay beim ersten Request)
    from app.services.sentiment_data_service import get_sentiment_data_service
    service = get_sentiment_data_service()
    await asyncio.to_thread(service.initialize)
    yield


# App erstellen
app = FastAPI(
    title="BTC/EUR Cashflow Management API",
    description="Ledger-first, deterministisches Cashflow-Tracking für BTC/EUR Trading",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(require_api_key)],
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

# Routes registrieren
app.include_router(portfolio.router)
app.include_router(lots.router)
app.include_router(sync.router)
app.include_router(pairing.router)
app.include_router(orders.router)
app.include_router(reconciliation.router)
app.include_router(cashflow.router)
app.include_router(settings.router)
app.include_router(macro.router)
app.include_router(sentiment.router)


@app.get("/")
def root():
    """Health Check"""
    return {
        "status": "ok",
        "app": "BTC/EUR Cashflow Management",
        "version": "0.1.0"
    }


@app.get("/health")
def health():
    """Health Check Endpoint"""
    return {"status": "healthy"}
