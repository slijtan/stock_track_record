from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.stock import StockPriceResponse
from app.services import stock_price_service

router = APIRouter()


@router.get("/stocks/{ticker}/price", response_model=StockPriceResponse)
async def get_stock_price(ticker: str, db: Session = Depends(get_db)):
    """Get current stock price."""
    try:
        price_data = stock_price_service.get_current_price(db, ticker.upper())
        return StockPriceResponse(
            ticker=ticker.upper(),
            price=price_data.get("price"),
            updated_at=price_data.get("updated_at"),
        )
    except Exception as e:
        return StockPriceResponse(
            ticker=ticker.upper(),
            error=str(e),
        )
