"""Pairing API Endpoints"""
import logging
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from decimal import Decimal, InvalidOperation
from typing import Optional, List
from pydantic import BaseModel

from app.db.database import get_db
from app.symbol_registry import is_known_symbol, KNOWN_PAIRS

logger = logging.getLogger(__name__)
from app.services.pairing_service import (
    get_pairing_suggestions,
    simulate_pairing_execution,
    create_pairing,
    get_pairing_by_id,
    list_pairings,
    lock_pairing,
    unlock_pairing,
    execute_pairing,
    delete_pairing,
)
from app.services.order_service import OrderService
from app.services.binance import BinanceService
from app.api.dependencies import get_binance_service

router = APIRouter(prefix="/api/pairing", tags=["pairing"])


def _validate_market_price(market_price: float) -> None:
    """Validiert market_price auf NaN, Infinity und negative Werte."""
    if math.isnan(market_price) or math.isinf(market_price) or market_price <= 0:
        raise HTTPException(status_code=400, detail="market_price muss positiv und endlich sein")


def _get_order_service(binance: BinanceService = Depends(get_binance_service)) -> OrderService:
    """Dependency: Order Service für Pairing-Execution"""
    return OrderService(binance)


# ============================================================================
# Request/Response Models
# ============================================================================


class PairingItemCreate(BaseModel):
    lot_id: str
    qty_base: str  # Decimal als String (Praezision)


class PairingCreateRequest(BaseModel):
    items: List[PairingItemCreate]
    threshold_pct: str  # Decimal als String (Praezision)
    symbol: str = "BTCEUR"


@router.get("/{user_id}/suggestions")
def get_suggestions(
    user_id: str,
    market_price: float,
    threshold_pct: float = Query(0.05, description="Threshold in % (z.B. 0.05 für 5%)"),
    symbol: str = Query("BTCEUR", description="Trading Pair"),
    db: Session = Depends(get_db)
):
    """
    Holt Pairing-Vorschläge

    Args:
        user_id: User ID
        market_price: Aktueller Marktpreis
        threshold_pct: Zielmarge (Default: 5%)
        symbol: Trading Pair (Default: BTCEUR)
        db: Database Session (injected)

    Returns:
        Liste von Pairing-Vorschlägen
    """
    if not is_known_symbol(symbol):
        raise HTTPException(status_code=400, detail=f"Unbekanntes Symbol: {symbol}. Bekannt: {list(KNOWN_PAIRS.keys())}")

    _validate_market_price(market_price)
    try:
        market_price_decimal = Decimal(str(market_price))
        threshold_decimal = Decimal(str(threshold_pct))

        suggestions = get_pairing_suggestions(
            db,
            user_id,
            market_price_decimal,
            threshold_decimal,
            symbol=symbol,
        )

        return {
            "suggestions": suggestions,
            "count": len(suggestions),
            "market_price": str(market_price_decimal),
            "threshold_pct": str(threshold_decimal),
            "symbol": symbol,
        }
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/simulate/{pairing_id}")
def simulate(
    user_id: str,
    pairing_id: str,
    market_price: float,
    fee_pct: float = Query(0.001, description="Trading Fee (z.B. 0.001 fuer 0.1%)"),
    fee_buffer_pct: float = Query(0.002, description="Fee-Buffer fuer Zielpreis (z.B. 0.002 fuer 0.2%)"),
    custom_sell_price: Optional[float] = Query(None, description="Benutzerdefinierter Verkaufspreis (ueberschreibt Marktpreis + Fee-Buffer)"),
    db: Session = Depends(get_db)
):
    """
    Simuliert Pairing-Ausfuehrung inkl. geplanter Binance-Order-Parameter

    Args:
        user_id: User ID
        pairing_id: Pairing ID (von Suggestion)
        market_price: Aktueller Marktpreis
        fee_pct: Trading Fee (Default: 0.1%)
        fee_buffer_pct: Fee-Buffer fuer Zielpreis (Default: 0.2%)
        custom_sell_price: Benutzerdefinierter Verkaufspreis (optional)
        db: Database Session (injected)

    Returns:
        Simulation-Details inkl. planned_orders
    """
    _validate_market_price(market_price)
    try:
        market_price_decimal = Decimal(str(market_price))
        fee_pct_decimal = Decimal(str(fee_pct))
        fee_buffer_decimal = Decimal(str(fee_buffer_pct))
        custom_price_decimal = Decimal(str(custom_sell_price)) if custom_sell_price is not None else None

        simulation = simulate_pairing_execution(
            db,
            user_id,
            pairing_id,
            market_price_decimal,
            fee_pct_decimal,
            fee_buffer_decimal,
            custom_sell_price=custom_price_decimal,
        )

        return simulation
    except ValueError as e:
        logger.warning("Pairing simulate not found: user=%s pairing=%s: %s", user_id, pairing_id, e)
        raise HTTPException(status_code=404, detail="Pairing nicht gefunden")
    except Exception:
        logger.exception("Pairing simulate failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


# ============================================================================
# Pairing Persistence Endpoints
# ============================================================================


@router.post("/{user_id}/create")
def create_pairing_endpoint(
    user_id: str,
    request: PairingCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Erstellt und persistiert ein Pairing

    Args:
        user_id: User ID
        request: Pairing creation request with items and threshold
        db: Database Session (injected)

    Returns:
        Created pairing
    """
    if not is_known_symbol(request.symbol):
        raise HTTPException(status_code=400, detail=f"Unbekanntes Symbol: {request.symbol}. Bekannt: {list(KNOWN_PAIRS.keys())}")

    try:
        items = [{"lot_id": item.lot_id, "qty_base": Decimal(str(item.qty_base))} for item in request.items]
        threshold = Decimal(str(request.threshold_pct))

        pairing = create_pairing(db, user_id, items, threshold, symbol=request.symbol)

        return {
            "status": "created",
            "pairing": pairing
        }
    except ValueError as e:
        logger.warning("Pairing validation failed for user=%s: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/list")
def list_pairings_endpoint(
    user_id: str,
    status: Optional[str] = Query(None, description="Filter by status (DRAFT, LOCKED, EXECUTED)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol (z.B. BTCEUR)"),
    db: Session = Depends(get_db)
):
    """
    Listet alle Pairings für User

    Args:
        user_id: User ID
        status: Optional status filter
        symbol: Optional symbol filter
        db: Database Session (injected)

    Returns:
        List of pairings
    """
    try:
        pairings = list_pairings(db, user_id, status, symbol)

        return {
            "pairings": pairings,
            "count": len(pairings),
            "filter": {"status": status, "symbol": symbol}
        }
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.get("/{user_id}/{pairing_id}")
def get_pairing_endpoint(
    user_id: str,
    pairing_id: str,
    db: Session = Depends(get_db)
):
    """
    Holt ein einzelnes Pairing

    Args:
        user_id: User ID
        pairing_id: Pairing ID
        db: Database Session (injected)

    Returns:
        Pairing details
    """
    try:
        pairing = get_pairing_by_id(db, user_id, pairing_id)

        if not pairing:
            raise HTTPException(status_code=404, detail=f"Pairing {pairing_id} not found")

        from app.services.pairing_service import _pairing_to_dict
        return _pairing_to_dict(pairing, Decimal("0"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/{pairing_id}/lock")
def lock_pairing_endpoint(
    user_id: str,
    pairing_id: str,
    db: Session = Depends(get_db)
):
    """
    Sperrt Pairing für Execution (DRAFT → LOCKED)

    Args:
        user_id: User ID
        pairing_id: Pairing ID
        db: Database Session (injected)

    Returns:
        Updated pairing
    """
    try:
        pairing = lock_pairing(db, user_id, pairing_id)

        return {
            "status": "locked",
            "pairing": pairing
        }
    except ValueError as e:
        logger.warning("Pairing validation failed for user=%s: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/{pairing_id}/unlock")
def unlock_pairing_endpoint(
    user_id: str,
    pairing_id: str,
    db: Session = Depends(get_db)
):
    """Entsperrt Pairing (LOCKED → DRAFT)"""
    try:
        pairing = unlock_pairing(db, user_id, pairing_id)
        return {
            "status": "unlocked",
            "pairing": pairing
        }
    except ValueError as e:
        logger.warning("Pairing validation failed for user=%s: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.post("/{user_id}/{pairing_id}/execute")
def execute_pairing_endpoint(
    user_id: str,
    pairing_id: str,
    market_price: float = Query(..., description="Aktueller BTC/EUR Marktpreis"),
    fee_buffer_pct: float = Query(0.002, description="Fee-Buffer fuer Zielpreis (z.B. 0.002 fuer 0.2%)"),
    custom_sell_price: Optional[float] = Query(None, description="Benutzerdefinierter Verkaufspreis (ueberschreibt Marktpreis + Fee-Buffer)"),
    db: Session = Depends(get_db),
    order_service: OrderService = Depends(_get_order_service),
):
    """
    Fuehrt Pairing aus: Erstellt Sell-Orders auf Binance fuer alle Lots im Pairing.

    Ablauf:
    1. Pairing locken (falls noch DRAFT)
    2. Pro Lot: TAKE_PROFIT_LIMIT Sell Order auf Binance platzieren
    3. Bei Erfolg: Pairing als EXECUTED markieren
    4. Bei Fehler: Alle bereits platzierten Orders stornieren (Rollback)

    Args:
        user_id: User ID
        pairing_id: Pairing ID
        market_price: Aktueller BTC/EUR Marktpreis (fuer Sell Price Berechnung)
        fee_buffer_pct: Fee-Buffer fuer Zielpreis (Default: 0.2%)
        custom_sell_price: Benutzerdefinierter Verkaufspreis (optional)
        db: Database Session (injected)
        order_service: Order Service (injected)

    Returns:
        Erstellte Orders + Pairing Status
    """
    _validate_market_price(market_price)
    try:
        market_price_decimal = Decimal(str(market_price))
        fee_buffer_decimal = Decimal(str(fee_buffer_pct))
        custom_price_decimal = Decimal(str(custom_sell_price)) if custom_sell_price is not None else None

        result = order_service.create_limit_sell_for_pairing(
            db,
            user_id,
            pairing_id,
            market_price_decimal,
            fee_buffer_decimal,
            custom_sell_price=custom_price_decimal,
        )

        return result
    except ValueError as e:
        logger.warning("Pairing validation failed for user=%s: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")


@router.delete("/{user_id}/{pairing_id}")
def delete_pairing_endpoint(
    user_id: str,
    pairing_id: str,
    db: Session = Depends(get_db)
):
    """
    Löscht ein Pairing (nur DRAFT Status)

    Args:
        user_id: User ID
        pairing_id: Pairing ID
        db: Database Session (injected)

    Returns:
        Deletion confirmation
    """
    try:
        delete_pairing(db, user_id, pairing_id)

        return {
            "status": "deleted",
            "pairing_id": pairing_id
        }
    except ValueError as e:
        logger.warning("Pairing validation failed for user=%s: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Pairing endpoint failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Interner Serverfehler")
