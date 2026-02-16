"""Portfolio API Endpoints"""
import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.portfolio_service import get_portfolio_state, get_daily_performance
from app.services.binance import BinanceService
from app.api.dependencies import get_binance_service_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/{user_id}")
def get_portfolio(
    user_id: str,
    market_price: float,
    db: Session = Depends(get_db),
    binance: BinanceService = Depends(get_binance_service_optional)
):
    """
    Holt Portfolio-Zustand für einen User

    BINANCE ALS SINGLE SOURCE OF TRUTH:
    - BTC/EUR Balance direkt von Binance
    - Break-even nur für getrackte Lots

    Args:
        user_id: User ID
        market_price: Aktueller BTC/EUR Marktpreis
        db: Database Session (injected)
        binance: Optional Binance Service (injected)

    Returns:
        Portfolio-KPIs
    """
    try:
        market_price_decimal = Decimal(str(market_price))
        return get_portfolio_state(db, user_id, market_price_decimal, binance)
    except Exception as e:
        logger.exception("Portfolio endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/daily")
def get_daily_performance_endpoint(
    user_id: str,
    market_price: float,
    db: Session = Depends(get_db),
):
    """Tages-Performance: Realized P&L, Buys/Sells, Unrealized P&L Change"""
    try:
        market_price_decimal = Decimal(str(market_price))
        return get_daily_performance(db, user_id, market_price_decimal)
    except Exception as e:
        logger.exception("Daily performance endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail=str(e))
