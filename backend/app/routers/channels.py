import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db, SessionLocal
from app.schemas.channel import (
    ChannelCreate,
    ChannelResponse,
    ChannelListResponse,
    LogsResponse,
)
from app.schemas.stock import (
    ChannelStocksResponse,
    ChannelStockResponse,
    TimelineResponse,
    TimelineItem,
    StockDrilldownResponse,
    StockMentionResponse,
    VideoResponse,
    BatchPricesResponse,
)
from app.services import channel_service, stock_price_service
from app.services.processing_service import process_channel, backfill_historical_prices as backfill_prices_service
from app.db.models import Video, StockMention, Stock
from datetime import datetime

router = APIRouter()
settings = get_settings()


def run_channel_processing(channel_id: str):
    """Background task to process a channel."""
    db = SessionLocal()
    try:
        process_channel(db, channel_id)
    except Exception as e:
        print(f"Processing error for channel {channel_id}: {e}")
    finally:
        db.close()


def queue_to_sqs(channel_id: str):
    """Send channel processing job to SQS."""
    import boto3
    sqs = boto3.client('sqs', region_name=settings.aws_region)
    sqs.send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=json.dumps({'channel_id': channel_id}),
    )


@router.post("/channels", response_model=ChannelResponse, status_code=201)
async def create_channel(
    channel: ChannelCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Create a new channel for processing."""
    try:
        result = channel_service.create_channel(
            db, channel.url, channel.time_range_months
        )
        # Queue background processing - use SQS in Lambda, BackgroundTasks locally
        if settings.is_lambda and settings.sqs_queue_url:
            queue_to_sqs(result.id)
        else:
            background_tasks.add_task(run_channel_processing, result.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/channels", response_model=ChannelListResponse)
async def list_channels(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List all channels with pagination."""
    channels, total = channel_service.list_channels(db, page, per_page)
    return ChannelListResponse(
        items=[ChannelResponse.model_validate(c) for c in channels],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: str, db: Session = Depends(get_db)):
    """Get channel details."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    """Delete a channel and all related data."""
    if not channel_service.delete_channel(db, channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    return None


@router.post("/channels/{channel_id}/process", response_model=ChannelResponse)
async def process_channel_endpoint(
    channel_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger processing for an existing channel."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status == "processing":
        raise HTTPException(status_code=400, detail="Channel is already processing")

    # Reset status and queue processing
    channel.status = "pending"
    db.commit()
    background_tasks.add_task(run_channel_processing, channel_id)
    db.refresh(channel)
    return channel


@router.post("/channels/{channel_id}/cancel", response_model=ChannelResponse)
async def cancel_channel_processing(
    channel_id: str,
    db: Session = Depends(get_db),
):
    """Cancel processing for a channel."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status != "processing":
        raise HTTPException(status_code=400, detail="Channel is not processing")

    # Set status to cancelled (will be picked up by processing loop)
    channel.status = "cancelled"
    db.commit()
    db.refresh(channel)
    return channel


@router.get("/channels/{channel_id}/logs", response_model=LogsResponse)
async def get_channel_logs(
    channel_id: str,
    since: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get processing logs for a channel."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    logs = channel_service.get_channel_logs(db, channel_id, since)
    return LogsResponse(logs=logs)


@router.get("/channels/{channel_id}/stocks", response_model=ChannelStocksResponse)
async def get_channel_stocks(channel_id: str, db: Session = Depends(get_db)):
    """Get aggregated stock data for a channel."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    stocks = channel_service.get_channel_stocks(db, channel_id)
    return ChannelStocksResponse(
        channel_id=channel_id,
        stocks=[ChannelStockResponse(**s) for s in stocks],
    )


@router.get("/channels/{channel_id}/timeline", response_model=TimelineResponse)
async def get_channel_timeline(channel_id: str, db: Session = Depends(get_db)):
    """Get timeline of videos with their stock mentions."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    timeline = channel_service.get_channel_timeline(db, channel_id)
    return TimelineResponse(
        timeline=[
            TimelineItem(
                video=VideoResponse.model_validate(item["video"]),
                mentions=[StockMentionResponse.model_validate(m) for m in item["mentions"]],
            )
            for item in timeline
        ]
    )


@router.get("/channels/{channel_id}/stocks/{ticker}", response_model=StockDrilldownResponse)
async def get_stock_drilldown(
    channel_id: str, ticker: str, db: Session = Depends(get_db)
):
    """Get all mentions of a stock within a channel."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    mentions = channel_service.get_stock_drilldown(db, channel_id, ticker.upper())
    return StockDrilldownResponse(
        ticker=ticker.upper(),
        channel_id=channel_id,
        mentions=[StockMentionResponse.model_validate(m) for m in mentions],
    )


def run_price_refresh(channel_id: str, tickers: list):
    """Background task to refresh prices."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        prices = stock_price_service.get_batch_current_prices(tickers)
        now = datetime.utcnow()
        for ticker, price in prices.items():
            stock = db.query(Stock).filter(Stock.ticker == ticker).first()
            if stock:
                stock.last_price = price
                stock.price_updated_at = now
        db.commit()
        print(f"Background price refresh complete: {len(prices)} prices updated")
    except Exception as e:
        print(f"Background price refresh error: {e}")
    finally:
        db.close()


@router.post("/channels/{channel_id}/refresh-prices", response_model=BatchPricesResponse)
async def refresh_channel_prices(
    channel_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Refresh current prices for all stocks in a channel."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Get all unique tickers for this channel
    videos = db.query(Video).filter(Video.channel_id == channel_id).all()
    video_ids = [v.id for v in videos]

    if not video_ids:
        return BatchPricesResponse(prices={}, updated_at=datetime.utcnow())

    mentions = db.query(StockMention).filter(StockMention.video_id.in_(video_ids)).all()
    tickers = list(set(m.ticker for m in mentions))

    if not tickers:
        return BatchPricesResponse(prices={}, updated_at=datetime.utcnow())

    # Check how many prices we have cached
    prices = {}
    missing_tickers = []
    for ticker in tickers:
        stock = db.query(Stock).filter(Stock.ticker == ticker).first()
        if stock and stock.last_price:
            prices[ticker] = float(stock.last_price)
        else:
            missing_tickers.append(ticker)

    # If many prices missing, fetch them synchronously (up to 50)
    if len(missing_tickers) > len(prices):
        print(f"Fetching {min(50, len(missing_tickers))} missing prices synchronously")
        fresh_prices = stock_price_service.get_batch_current_prices(missing_tickers[:50])
        now = datetime.utcnow()
        for ticker, price in fresh_prices.items():
            prices[ticker] = price
            # Update DB
            stock = db.query(Stock).filter(Stock.ticker == ticker).first()
            if stock:
                stock.last_price = price
                stock.price_updated_at = now
        db.commit()

    # Queue background refresh for remaining tickers
    remaining = [t for t in tickers if t not in prices]
    if remaining:
        background_tasks.add_task(run_price_refresh, channel_id, remaining)

    return BatchPricesResponse(prices=prices, updated_at=datetime.utcnow())


@router.post("/channels/{channel_id}/backfill-prices")
async def backfill_historical_prices(
    channel_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Backfill missing historical prices for all mentions in a channel."""
    channel = channel_service.get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Count mentions needing backfill
    videos = db.query(Video).filter(Video.channel_id == channel_id).all()
    video_ids = [v.id for v in videos]

    if not video_ids:
        return {"status": "no_videos"}

    missing_count = (
        db.query(StockMention)
        .filter(StockMention.video_id.in_(video_ids))
        .filter(StockMention.price_at_mention.is_(None))
        .count()
    )

    if missing_count == 0:
        return {"status": "complete", "missing": 0}

    # Run backfill in background
    def run_backfill():
        from app.db.database import SessionLocal
        bg_db = SessionLocal()
        try:
            updated = backfill_prices_service(bg_db, channel_id)
            print(f"Backfill complete: {updated} prices updated")
        except Exception as e:
            print(f"Backfill error: {e}")
        finally:
            bg_db.close()

    background_tasks.add_task(run_backfill)

    return {"status": "started", "missing": missing_count}
