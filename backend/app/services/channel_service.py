import re
from typing import Optional, List, Tuple

from boto3.dynamodb.conditions import Key, Attr

from app.db.dynamodb import get_table, query_all_pages, query_count, batch_delete_items
from app.db.dynamodb_models import (
    Channel, Video, StockMention, ProcessingLog, Stock, _utcnow_iso,
)


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


def create_channel(url: str, time_range_months: int = 12) -> Channel:
    """Create a new channel for processing."""
    identifier, id_type = extract_channel_identifier(url)
    youtube_channel_id = f"{id_type}:{identifier}"

    table = get_table()

    # Check if channel already exists via GSI2
    response = table.query(
        IndexName="GSI2-index",
        KeyConditionExpression=Key("GSI2PK").eq(f"YT#{youtube_channel_id}"),
        Limit=1,
    )
    if response.get("Items"):
        raise ValueError("Channel already exists")

    channel = Channel(
        youtube_channel_id=youtube_channel_id,
        name=identifier,
        url=url,
        time_range_months=time_range_months,
        status="pending",
    )
    table.put_item(Item=channel.to_item())
    return channel


def get_channel(channel_id: str) -> Optional[Channel]:
    """Get a channel by ID."""
    table = get_table()
    response = table.get_item(
        Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"}
    )
    item = response.get("Item")
    if not item:
        return None
    return Channel.from_item(item)


def list_channels(page: int = 1, per_page: int = 20) -> Tuple[List[Channel], int]:
    """List all channels with pagination."""
    table = get_table()

    # Get total count
    total = query_count(
        table,
        IndexName="GSI1-index",
        KeyConditionExpression=Key("GSI1PK").eq("CHANNELS"),
    )

    # Query with pagination (newest first)
    query_kwargs = {
        "IndexName": "GSI1-index",
        "KeyConditionExpression": Key("GSI1PK").eq("CHANNELS"),
        "ScanIndexForward": False,
        "Limit": per_page,
    }

    # Skip forward for page > 1
    response = table.query(**query_kwargs)

    pages_to_skip = page - 1
    for _ in range(pages_to_skip):
        if "LastEvaluatedKey" not in response:
            return [], total  # Past last page
        query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.query(**query_kwargs)

    items = response.get("Items", [])
    channels = [Channel.from_item(item) for item in items]
    return channels, total


def delete_channel(channel_id: str) -> bool:
    """Delete a channel and all related data (cascade)."""
    table = get_table()

    # Verify channel exists
    response = table.get_item(
        Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"}
    )
    if "Item" not in response:
        return False

    # Query all items under CHANNEL#{channel_id} partition
    # Gets: channel record, all videos, all logs
    channel_items = query_all_pages(
        table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}"),
    )

    # For each video, query its mentions
    all_items = list(channel_items)
    for item in channel_items:
        if item.get("SK", "").startswith("VIDEO#"):
            video_id = item["id"]
            mentions = query_all_pages(
                table,
                KeyConditionExpression=Key("PK").eq(f"VIDEO#{video_id}")
                & Key("SK").begins_with("MENTION#"),
            )
            all_items.extend(mentions)

    # Batch delete all items
    if all_items:
        batch_delete_items(table, all_items)

    return True


def get_channel_logs(
    channel_id: str, since: Optional[str] = None
) -> List[ProcessingLog]:
    """Get processing logs for a channel."""
    table = get_table()

    if since:
        key_condition = Key("PK").eq(f"CHANNEL#{channel_id}") & Key("SK").between(
            f"LOG#{since}", f"LOG#\xff"
        )
    else:
        key_condition = Key("PK").eq(f"CHANNEL#{channel_id}") & Key("SK").begins_with(
            "LOG#"
        )

    items = query_all_pages(
        table,
        KeyConditionExpression=key_condition,
        ScanIndexForward=True,
    )
    return [ProcessingLog.from_item(item) for item in items]


def add_processing_log(
    channel_id: str, message: str, log_level: str = "info"
) -> ProcessingLog:
    """Add a processing log entry."""
    table = get_table()
    log = ProcessingLog(
        channel_id=channel_id,
        message=message,
        log_level=log_level,
    )
    table.put_item(Item=log.to_item())
    return log


def get_channel_stocks(channel_id: str) -> List[dict]:
    """Get aggregated stock data for a channel."""
    table = get_table()
    stocks_table = get_table("-Stocks")

    # Get all videos for the channel
    video_items = query_all_pages(
        table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}")
        & Key("SK").begins_with("VIDEO#"),
    )
    videos = [Video.from_item(item) for item in video_items]
    video_map = {v.id: v for v in videos}

    if not videos:
        return []

    # Get all stock mentions for these videos
    all_mentions = []
    for video in videos:
        mention_items = query_all_pages(
            table,
            KeyConditionExpression=Key("PK").eq(f"VIDEO#{video.id}")
            & Key("SK").begins_with("MENTION#"),
        )
        all_mentions.extend(
            [StockMention.from_item(item) for item in mention_items]
        )

    # Aggregate by ticker
    stock_data = {}
    for mention in all_mentions:
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
            key=lambda m: video_map[m.video_id].published_at
            if m.video_id in video_map
            else m.created_at,
        )
        first_mention = mentions_sorted[0] if mentions_sorted else None
        first_video = video_map.get(first_mention.video_id) if first_mention else None

        # Get stock info from stocks table
        stock_response = stocks_table.get_item(Key={"ticker": ticker})
        stock = (
            Stock.from_item(stock_response["Item"])
            if "Item" in stock_response
            else None
        )

        result.append(
            {
                "ticker": ticker,
                "name": stock.name if stock else None,
                "first_mention_date": first_video.published_at
                if first_video
                else None,
                "first_mention_video_id": first_mention.video_id
                if first_mention
                else None,
                "first_mention_video_title": first_video.title
                if first_video
                else None,
                "price_at_first_mention": first_mention.price_at_mention
                if first_mention
                else None,
                "current_price": stock.last_price if stock else None,
                "price_change_percent": None,
                "buy_count": data["buy_count"],
                "hold_count": data["hold_count"],
                "sell_count": data["sell_count"],
                "mentioned_count": data["mentioned_count"],
                "total_mentions": len(data["mentions"]),
                "yahoo_finance_url": f"https://finance.yahoo.com/quote/{ticker}",
            }
        )

        # Calculate price change
        if result[-1]["price_at_first_mention"] and result[-1]["current_price"]:
            first_price = result[-1]["price_at_first_mention"]
            current_price = result[-1]["current_price"]
            result[-1]["price_change_percent"] = (
                (current_price - first_price) / first_price
            ) * 100

    return result


def get_channel_timeline(channel_id: str) -> List[dict]:
    """Get timeline of videos with their stock mentions."""
    table = get_table()

    # Get all videos sorted by published_at descending
    video_items = query_all_pages(
        table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}")
        & Key("SK").begins_with("VIDEO#"),
    )
    videos = sorted(
        [Video.from_item(item) for item in video_items],
        key=lambda v: v.published_at,
        reverse=True,
    )

    timeline = []
    for video in videos:
        mention_items = query_all_pages(
            table,
            KeyConditionExpression=Key("PK").eq(f"VIDEO#{video.id}")
            & Key("SK").begins_with("MENTION#"),
        )
        mentions = [StockMention.from_item(item) for item in mention_items]
        if mentions:
            timeline.append({"video": video, "mentions": mentions})

    return timeline


def get_stock_drilldown(channel_id: str, ticker: str) -> List[dict]:
    """Get all mentions of a stock within a channel, with video info."""
    table = get_table()

    # Get all videos for channel
    video_items = query_all_pages(
        table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}")
        & Key("SK").begins_with("VIDEO#"),
    )
    video_map = {Video.from_item(item).id: Video.from_item(item) for item in video_items}

    if not video_map:
        return []

    # Get mentions for each video, filtered by ticker
    result = []
    for video_id, video in video_map.items():
        mention_items = query_all_pages(
            table,
            KeyConditionExpression=Key("PK").eq(f"VIDEO#{video_id}")
            & Key("SK").begins_with("MENTION#"),
            FilterExpression=Attr("ticker").eq(ticker),
        )
        for item in mention_items:
            mention = StockMention.from_item(item)
            result.append({"mention": mention, "video": video})

    return result
