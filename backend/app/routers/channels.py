import json
from datetime import datetime
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from boto3.dynamodb.conditions import Key, Attr

from app.config import get_settings
from app.db.dynamodb import get_table, query_all_pages
from app.db.dynamodb_models import Video, StockMention, Stock
from app.schemas.channel import (
    ChannelCreate,
    ChannelResponse,
    ChannelListResponse,
    LogsResponse,
    ProcessingLogResponse,
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

router = APIRouter()
settings = get_settings()


def run_channel_processing(channel_id: str):
    """Background task to process a channel."""
    try:
        process_channel(channel_id)
    except Exception as e:
        print(f"Processing error for channel {channel_id}: {e}")


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
):
    """Create a new channel for processing."""
    try:
        result = channel_service.create_channel(
            channel.url, channel.time_range_months
        )
        # Queue background processing - use SQS in Lambda, BackgroundTasks locally
        if settings.is_lambda and settings.sqs_queue_url:
            queue_to_sqs(result.id)
        else:
            background_tasks.add_task(run_channel_processing, result.id)
        return ChannelResponse(**result.to_response_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/channels", response_model=ChannelListResponse)
async def list_channels(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all channels with pagination."""
    channels, total = channel_service.list_channels(page, per_page)
    return ChannelListResponse(
        items=[ChannelResponse(**c.to_response_dict()) for c in channels],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: str):
    """Get channel details."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse(**channel.to_response_dict())


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: str):
    """Delete a channel and all related data."""
    if not channel_service.delete_channel(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    return None


@router.post("/channels/{channel_id}/process", response_model=ChannelResponse)
async def process_channel_endpoint(
    channel_id: str,
    background_tasks: BackgroundTasks,
):
    """Trigger processing for an existing channel."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status == "processing":
        raise HTTPException(status_code=400, detail="Channel is already processing")

    # Reset status and queue processing
    table = get_table()
    table.update_item(
        Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"},
        UpdateExpression="SET #s = :status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":status": "pending"},
    )
    background_tasks.add_task(run_channel_processing, channel_id)

    # Re-fetch to return updated state
    channel = channel_service.get_channel(channel_id)
    return ChannelResponse(**channel.to_response_dict())


@router.post("/channels/{channel_id}/cancel", response_model=ChannelResponse)
async def cancel_channel_processing(channel_id: str):
    """Cancel processing for a channel."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status != "processing":
        raise HTTPException(status_code=400, detail="Channel is not processing")

    # Set status to cancelled
    table = get_table()
    table.update_item(
        Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"},
        UpdateExpression="SET #s = :status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":status": "cancelled"},
    )

    channel = channel_service.get_channel(channel_id)
    return ChannelResponse(**channel.to_response_dict())


@router.get("/channels/{channel_id}/logs", response_model=LogsResponse)
async def get_channel_logs(
    channel_id: str,
    since: Optional[str] = None,
):
    """Get processing logs for a channel."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    logs = channel_service.get_channel_logs(channel_id, since)
    return LogsResponse(
        logs=[ProcessingLogResponse(**log.to_response_dict()) for log in logs]
    )


@router.get("/channels/{channel_id}/stocks", response_model=ChannelStocksResponse)
async def get_channel_stocks(channel_id: str):
    """Get aggregated stock data for a channel."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    stocks = channel_service.get_channel_stocks(channel_id)
    return ChannelStocksResponse(
        channel_id=channel_id,
        stocks=[ChannelStockResponse(**s) for s in stocks],
    )


@router.get("/channels/{channel_id}/timeline", response_model=TimelineResponse)
async def get_channel_timeline(channel_id: str):
    """Get timeline of videos with their stock mentions."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    timeline = channel_service.get_channel_timeline(channel_id)
    return TimelineResponse(
        timeline=[
            TimelineItem(
                video=VideoResponse(**item["video"].to_response_dict()),
                mentions=[
                    StockMentionResponse(**m.to_response_dict())
                    for m in item["mentions"]
                ],
            )
            for item in timeline
        ]
    )


@router.get("/channels/{channel_id}/stocks/{ticker}", response_model=StockDrilldownResponse)
async def get_stock_drilldown(channel_id: str, ticker: str):
    """Get all mentions of a stock within a channel."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    drilldown = channel_service.get_stock_drilldown(channel_id, ticker.upper())
    return StockDrilldownResponse(
        ticker=ticker.upper(),
        channel_id=channel_id,
        mentions=[
            StockMentionResponse(**item["mention"].to_response_dict(video=item["video"]))
            for item in drilldown
        ],
    )


def run_price_refresh(channel_id: str, tickers: list):
    """Background task to refresh prices."""
    try:
        stocks_table = get_table("-Stocks")
        prices = stock_price_service.get_batch_current_prices(tickers)
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        for ticker, price in prices.items():
            stocks_table.update_item(
                Key={"ticker": ticker},
                UpdateExpression="SET last_price = :price, price_updated_at = :updated",
                ExpressionAttributeValues={
                    ":price": Decimal(str(price)),
                    ":updated": now_iso,
                },
            )
        print(f"Background price refresh complete: {len(prices)} prices updated")
    except Exception as e:
        print(f"Background price refresh error: {e}")


@router.post("/channels/{channel_id}/refresh-prices", response_model=BatchPricesResponse)
async def refresh_channel_prices(
    channel_id: str,
    background_tasks: BackgroundTasks,
):
    """Refresh current prices for all stocks in a channel."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    table = get_table()
    stocks_table = get_table("-Stocks")

    # Get all unique tickers for this channel
    video_items = query_all_pages(
        table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}")
        & Key("SK").begins_with("VIDEO#"),
    )
    videos = [Video.from_item(item) for item in video_items]

    if not videos:
        return BatchPricesResponse(prices={}, updated_at=datetime.utcnow())

    # Get mentions for all videos
    tickers_set = set()
    for video in videos:
        mention_items = query_all_pages(
            table,
            KeyConditionExpression=Key("PK").eq(f"VIDEO#{video.id}")
            & Key("SK").begins_with("MENTION#"),
        )
        for item in mention_items:
            tickers_set.add(item["ticker"])

    tickers = list(tickers_set)

    if not tickers:
        return BatchPricesResponse(prices={}, updated_at=datetime.utcnow())

    # Check how many prices we have cached in stocks table
    prices = {}
    missing_tickers = []
    for ticker in tickers:
        stock_resp = stocks_table.get_item(Key={"ticker": ticker})
        if "Item" in stock_resp:
            stock = Stock.from_item(stock_resp["Item"])
            if stock.last_price:
                prices[ticker] = stock.last_price
            else:
                missing_tickers.append(ticker)
        else:
            missing_tickers.append(ticker)

    # If many prices missing, fetch them synchronously (up to 50)
    if len(missing_tickers) > len(prices):
        print(f"Fetching {min(50, len(missing_tickers))} missing prices synchronously")
        fresh_prices = stock_price_service.get_batch_current_prices(missing_tickers[:50])
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        for ticker, price in fresh_prices.items():
            prices[ticker] = price
            stocks_table.update_item(
                Key={"ticker": ticker},
                UpdateExpression="SET last_price = :price, price_updated_at = :updated",
                ExpressionAttributeValues={
                    ":price": Decimal(str(price)),
                    ":updated": now_iso,
                },
            )

    # Queue background refresh for remaining tickers
    remaining = [t for t in tickers if t not in prices]
    if remaining:
        background_tasks.add_task(run_price_refresh, channel_id, remaining)

    return BatchPricesResponse(prices=prices, updated_at=datetime.utcnow())


@router.post("/channels/{channel_id}/backfill-prices")
async def backfill_historical_prices(
    channel_id: str,
    background_tasks: BackgroundTasks,
):
    """Backfill missing historical prices for all mentions in a channel."""
    channel = channel_service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    table = get_table()

    # Get all videos for the channel
    video_items = query_all_pages(
        table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}")
        & Key("SK").begins_with("VIDEO#"),
    )
    videos = [Video.from_item(item) for item in video_items]

    if not videos:
        return {"status": "no_videos"}

    # Count mentions needing backfill
    missing_count = 0
    for video in videos:
        mention_items = query_all_pages(
            table,
            KeyConditionExpression=Key("PK").eq(f"VIDEO#{video.id}")
            & Key("SK").begins_with("MENTION#"),
            FilterExpression=Attr("price_at_mention").not_exists(),
        )
        missing_count += len(list(mention_items))

    if missing_count == 0:
        return {"status": "complete", "missing": 0}

    # Run backfill in background
    def run_backfill():
        try:
            updated = backfill_prices_service(channel_id)
            print(f"Backfill complete: {updated} prices updated")
        except Exception as e:
            print(f"Backfill error: {e}")

    background_tasks.add_task(run_backfill)

    return {"status": "started", "missing": missing_count}
