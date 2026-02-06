import re
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.db.models import Channel, Video, StockMention, ProcessingLog, Stock


def extract_channel_identifier(url: str) -> Tuple[str, str]:
    """Extract channel identifier and type from URL."""
    patterns = [
        (r"youtube\.com/@([\w-]+)", "handle"),
        (r"youtube\.com/channel/([\w-]+)", "channel_id"),
        (r"youtube\.com/c/([\w-]+)", "custom"),
        (r"youtube\.com/user/([\w-]+)", "user"),
    ]
    for pattern, id_type in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), id_type
    raise ValueError("Could not extract channel identifier from URL")


def create_channel(
    db: Session, url: str, time_range_months: int = 12
) -> Channel:
    """Create a new channel for processing."""
    identifier, id_type = extract_channel_identifier(url)

    # For now, use the identifier as the youtube_channel_id
    # This will be updated when we actually fetch from YouTube
    youtube_channel_id = f"{id_type}:{identifier}"

    # Check if channel already exists
    existing = db.query(Channel).filter(
        Channel.youtube_channel_id == youtube_channel_id
    ).first()
    if existing:
        raise ValueError("Channel already exists")

    channel = Channel(
        youtube_channel_id=youtube_channel_id,
        name=identifier,  # Will be updated from YouTube
        url=url,
        time_range_months=time_range_months,
        status="pending",
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def get_channel(db: Session, channel_id: str) -> Optional[Channel]:
    """Get a channel by ID."""
    return db.query(Channel).filter(Channel.id == channel_id).first()


def list_channels(
    db: Session, page: int = 1, per_page: int = 20
) -> Tuple[List[Channel], int]:
    """List all channels with pagination."""
    total = db.query(func.count(Channel.id)).scalar()
    channels = (
        db.query(Channel)
        .order_by(desc(Channel.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return channels, total


def delete_channel(db: Session, channel_id: str) -> bool:
    """Delete a channel and all related data."""
    channel = get_channel(db, channel_id)
    if not channel:
        return False
    db.delete(channel)
    db.commit()
    return True


def get_channel_logs(
    db: Session, channel_id: str, since: Optional[str] = None
) -> List[ProcessingLog]:
    """Get processing logs for a channel."""
    query = db.query(ProcessingLog).filter(ProcessingLog.channel_id == channel_id)
    if since:
        query = query.filter(ProcessingLog.created_at > since)
    return query.order_by(ProcessingLog.created_at).all()


def add_processing_log(
    db: Session, channel_id: str, message: str, log_level: str = "info"
) -> ProcessingLog:
    """Add a processing log entry."""
    log = ProcessingLog(
        channel_id=channel_id,
        message=message,
        log_level=log_level,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_channel_stocks(db: Session, channel_id: str) -> List[dict]:
    """Get aggregated stock data for a channel."""
    # Get all videos for the channel
    videos = db.query(Video).filter(Video.channel_id == channel_id).all()
    video_ids = [v.id for v in videos]

    if not video_ids:
        return []

    # Get all stock mentions for these videos
    mentions = (
        db.query(StockMention)
        .filter(StockMention.video_id.in_(video_ids))
        .all()
    )

    # Aggregate by ticker
    stock_data = {}
    for mention in mentions:
        ticker = mention.ticker
        if ticker not in stock_data:
            stock_data[ticker] = {
                "ticker": ticker,
                "mentions": [],
                "buy_count": 0,
                "hold_count": 0,
                "sell_count": 0,
                "mentioned_count": 0,
            }
        stock_data[ticker]["mentions"].append(mention)
        if mention.sentiment == "buy":
            stock_data[ticker]["buy_count"] += 1
        elif mention.sentiment == "hold":
            stock_data[ticker]["hold_count"] += 1
        elif mention.sentiment == "sell":
            stock_data[ticker]["sell_count"] += 1
        else:
            stock_data[ticker]["mentioned_count"] += 1

    # Build response
    result = []
    for ticker, data in stock_data.items():
        mentions_sorted = sorted(
            data["mentions"],
            key=lambda m: m.video.published_at if m.video else m.created_at
        )
        first_mention = mentions_sorted[0] if mentions_sorted else None

        # Get stock info
        stock = db.query(Stock).filter(Stock.ticker == ticker).first()

        result.append({
            "ticker": ticker,
            "name": stock.name if stock else None,
            "first_mention_date": first_mention.video.published_at if first_mention and first_mention.video else None,
            "first_mention_video_id": first_mention.video_id if first_mention else None,
            "first_mention_video_title": first_mention.video.title if first_mention and first_mention.video else None,
            "price_at_first_mention": float(first_mention.price_at_mention) if first_mention and first_mention.price_at_mention else None,
            "current_price": float(stock.last_price) if stock and stock.last_price else None,
            "price_change_percent": None,  # Will be calculated
            "buy_count": data["buy_count"],
            "hold_count": data["hold_count"],
            "sell_count": data["sell_count"],
            "mentioned_count": data["mentioned_count"],
            "total_mentions": len(data["mentions"]),
            "yahoo_finance_url": f"https://finance.yahoo.com/quote/{ticker}",
        })

        # Calculate price change if we have both prices
        if result[-1]["price_at_first_mention"] and result[-1]["current_price"]:
            first_price = result[-1]["price_at_first_mention"]
            current_price = result[-1]["current_price"]
            result[-1]["price_change_percent"] = ((current_price - first_price) / first_price) * 100

    return result


def get_channel_timeline(db: Session, channel_id: str) -> List[dict]:
    """Get timeline of videos with their stock mentions."""
    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel_id)
        .order_by(desc(Video.published_at))
        .all()
    )

    timeline = []
    for video in videos:
        mentions = (
            db.query(StockMention)
            .filter(StockMention.video_id == video.id)
            .all()
        )
        if mentions:  # Only include videos with mentions
            timeline.append({
                "video": video,
                "mentions": mentions,
            })

    return timeline


def get_stock_drilldown(
    db: Session, channel_id: str, ticker: str
) -> List[StockMention]:
    """Get all mentions of a stock within a channel."""
    videos = db.query(Video).filter(Video.channel_id == channel_id).all()
    video_ids = [v.id for v in videos]

    if not video_ids:
        return []

    mentions = (
        db.query(StockMention)
        .filter(StockMention.video_id.in_(video_ids))
        .filter(StockMention.ticker == ticker)
        .all()
    )

    # Load video relationship
    for mention in mentions:
        _ = mention.video  # Force load

    return mentions
