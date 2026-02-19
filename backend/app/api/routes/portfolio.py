"""Portfolio API Endpoints"""
import logging
import math
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.portfolio_service import get_portfolio_state, get_daily_performance
from app.services.binance import BinanceService
from app.api.dependencies import get_binance_service_optional
from app.symbol_registry import is_known_symbol, KNOWN_PAIRS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/{user_id}")
def get_portfolio(
    user_id: str,
    market_price: float,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db),
    binance: BinanceService = Depends(get_binance_service_optional)
):
    """
    Holt Portfolio-Zustand für einen User

    BINANCE ALS SINGLE SOURCE OF TRUTH:
    - Base/Quote Balance direkt von Binance
    - Break-even nur für getrackte Lots

    Args:
        user_id: User ID
        market_price: Aktueller Marktpreis
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)
        binance: Optional Binance Service (injected)

    Returns:
        Portfolio-KPIs
    """
    if not is_known_symbol(symbol):
        raise HTTPException(status_code=400, detail=f"Unbekanntes Symbol: {symbol}. Bekannt: {list(KNOWN_PAIRS.keys())}")

    if not isinstance(market_price, (int, float)) or market_price <= 0 or math.isnan(market_price) or math.isinf(market_price):
        raise HTTPException(status_code=400, detail="market_price muss eine positive Zahl sein")

    try:
        market_price_decimal = Decimal(str(market_price))
        return get_portfolio_state(db, user_id, market_price_decimal, binance, symbol=symbol)
    except Exception as e:
        logger.exception("Portfolio endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/daily")
def get_daily_performance_endpoint(
    user_id: str,
    market_price: float,
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db),
):
    """Tages-Performance: Realized P&L, Buys/Sells, Unrealized P&L Change"""
    if not is_known_symbol(symbol):
        raise HTTPException(status_code=400, detail=f"Unbekanntes Symbol: {symbol}. Bekannt: {list(KNOWN_PAIRS.keys())}")

    if not isinstance(market_price, (int, float)) or market_price <= 0 or math.isnan(market_price) or math.isinf(market_price):
        raise HTTPException(status_code=400, detail="market_price muss eine positive Zahl sein")

    try:
        market_price_decimal = Decimal(str(market_price))
        return get_daily_performance(db, user_id, market_price_decimal, symbol=symbol)
    except Exception as e:
        logger.exception("Daily performance endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
