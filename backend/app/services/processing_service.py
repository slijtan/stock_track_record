from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from decimal import Decimal
from typing import Optional

import requests
from boto3.dynamodb.conditions import Key, Attr

from app.config import get_settings
from app.db.dynamodb import get_table, query_all_pages
from app.db.dynamodb_models import (
    Channel, Video, Stock, StockMention, ProcessingLog, _utcnow_iso,
)
from app.services import youtube_service, gemini_service, stock_price_service

settings = get_settings()

# Lock for thread-safe progress updates
progress_lock = Lock()

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def get_yahoo_historical_price(ticker: str, target_date: date) -> Optional[float]:
    """Get historical closing price from Yahoo Finance for a specific date."""
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not available, skipping historical price fetch")
        return None
    try:
        stock = yf.Ticker(ticker.upper())
        start_date = target_date - timedelta(days=7)
        end_date = target_date + timedelta(days=1)

        hist = stock.history(start=start_date.isoformat(), end=end_date.isoformat())

        if hist.empty:
            return None

        available_dates = hist.index.date
        valid_dates = [d for d in available_dates if d <= target_date]

        if not valid_dates:
            if len(available_dates) > 0:
                closest_date = min(available_dates)
            else:
                return None
        else:
            closest_date = max(valid_dates)

        row = hist[hist.index.date == closest_date]
        if row.empty:
            return None

        return float(row["Close"].iloc[0])
    except Exception as e:
        print(f"Yahoo historical error for {ticker}: {e}")
        return None


def _get_yahoo_session():
    """Create a Yahoo Finance session with cookies to avoid rate limiting."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    })
    try:
        session.get('https://finance.yahoo.com', timeout=10)
    except Exception:
        pass
    return session


def _fetch_yahoo_historical(session, ticker: str, start_date: date, end_date: date) -> dict:
    """Fetch historical data from Yahoo Finance using session with cookies."""
    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date, datetime.min.time()).timestamp())

    url = f'https://query2.finance.yahoo.com/v8/finance/chart/{ticker}'
    params = {
        'period1': start_ts,
        'period2': end_ts,
        'interval': '1d',
        'events': 'history'
    }

    try:
        response = session.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                timestamps = result[0].get('timestamp', [])
                closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])

                prices = {}
                for ts, close in zip(timestamps, closes):
                    if close is not None:
                        dt = datetime.fromtimestamp(ts).date()
                        prices[dt] = close
                return prices
    except Exception as e:
        print(f"  Yahoo fetch error for {ticker}: {e}")

    return {}


def add_log(channel_id: str, message: str, level: str = "info") -> None:
    """Add a processing log entry."""
    table = get_table()
    log = ProcessingLog(
        channel_id=channel_id,
        message=message,
        log_level=level,
    )
    table.put_item(Item=log.to_item())


def _update_channel_attr(channel_id: str, **updates):
    """Update specific attributes on a channel item."""
    table = get_table()
    updates["updated_at"] = _utcnow_iso()

    expr_parts = []
    attr_names = {}
    attr_values = {}
    for i, (key, value) in enumerate(updates.items()):
        placeholder_name = f"#k{i}"
        placeholder_value = f":v{i}"
        expr_parts.append(f"{placeholder_name} = {placeholder_value}")
        attr_names[placeholder_name] = key
        attr_values[placeholder_value] = value

    table.update_item(
        Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


def backfill_historical_prices(channel_id: str) -> int:
    """Backfill missing historical prices using Yahoo Finance with session cookies."""
    import importlib.util
    if importlib.util.find_spec("yfinance") is None:
        print("yfinance not available, skipping historical price backfill")
        return 0
    import time as time_module

    table = get_table()

    # Get all videos for the channel
    video_items = query_all_pages(
        table,
        KeyConditionExpression=Key("PK").eq(f"CHANNEL#{channel_id}")
        & Key("SK").begins_with("VIDEO#"),
    )
    videos = [Video.from_item(item) for item in video_items]
    video_map = {v.id: v for v in videos}

    if not videos:
        return 0

    # Get all mentions missing price_at_mention
    mentions = []
    for video in videos:
        mention_items = query_all_pages(
            table,
            KeyConditionExpression=Key("PK").eq(f"VIDEO#{video.id}")
            & Key("SK").begins_with("MENTION#"),
            FilterExpression=Attr("price_at_mention").not_exists(),
        )
        mentions.extend([StockMention.from_item(item) for item in mention_items])

    if not mentions:
        return 0

    # Group mentions by ticker
    ticker_mentions = {}
    for mention in mentions:
        video = video_map.get(mention.video_id)
        if video:
            ticker = mention.ticker.upper()
            if '.' in ticker and not (len(ticker.split('.')[1]) == 1):
                continue
            if ticker not in ticker_mentions:
                ticker_mentions[ticker] = []
            ticker_mentions[ticker].append((mention, date.fromisoformat(video.published_at)))

    if not ticker_mentions:
        return 0

    tickers = list(ticker_mentions.keys())
    print(f"Backfilling historical data for {len(tickers)} tickers")

    print("Creating Yahoo Finance session...")
    session = _get_yahoo_session()
    time_module.sleep(1)

    updated = 0

    for i, ticker in enumerate(tickers):
        mention_dates = ticker_mentions[ticker]
        print(f"[{i+1}/{len(tickers)}] Processing {ticker} ({len(mention_dates)} mentions)")

        if i > 0:
            time_module.sleep(0.5)

        all_dates = [d for _, d in mention_dates]
        min_date = min(all_dates) - timedelta(days=7)
        max_date = max(all_dates) + timedelta(days=1)

        prices = _fetch_yahoo_historical(session, ticker, min_date, max_date)

        if prices:
            available_dates = sorted(prices.keys())

            for mention, target_date in mention_dates:
                valid_dates = [d for d in available_dates if d <= target_date]
                if valid_dates:
                    closest_date = max(valid_dates)
                    price = prices.get(closest_date)
                    if price:
                        # Update mention in DynamoDB
                        table.update_item(
                            Key={"PK": f"VIDEO#{mention.video_id}", "SK": f"MENTION#{mention.id}"},
                            UpdateExpression="SET price_at_mention = :price",
                            ExpressionAttributeValues={":price": Decimal(str(float(price)))},
                        )
                        updated += 1
        else:
            print(f"  No data for {ticker}")

    print(f"Backfill complete: {updated} prices updated out of {len(mentions)} mentions")
    return updated


def process_channel(channel_id: str) -> None:
    """Process a channel: fetch videos and analyze with Gemini in parallel."""
    table = get_table()

    # Get channel
    response = table.get_item(
        Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"}
    )
    if "Item" not in response:
        raise ValueError(f"Channel not found: {channel_id}")

    channel = Channel.from_item(response["Item"])

    try:
        # Update status to processing
        _update_channel_attr(channel_id, status="processing")
        add_log(channel_id, "Starting channel processing...")

        # Extract channel info from URL
        channel_info = youtube_service.extract_channel_info_from_url(channel.url)
        add_log(channel_id, f"Extracted channel info: {channel_info['identifier']}")

        youtube_api_key = settings.youtube_api_key
        videos_data = []

        if youtube_api_key:
            try:
                add_log(channel_id, "Resolving channel ID...")
                resolved_channel_id = youtube_service.resolve_channel_id(
                    youtube_api_key,
                    channel_info["identifier"],
                    channel_info["type"],
                )

                metadata = youtube_service.get_channel_metadata(youtube_api_key, resolved_channel_id)

                # Update channel metadata
                _update_channel_attr(
                    channel_id,
                    youtube_channel_id=resolved_channel_id,
                    name=metadata.get("name", channel.name),
                    thumbnail_url=metadata.get("thumbnail_url", ""),
                )
                # Also update GSI2PK for the new youtube_channel_id
                table.update_item(
                    Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"},
                    UpdateExpression="SET GSI2PK = :gsi2pk",
                    ExpressionAttributeValues={":gsi2pk": f"YT#{resolved_channel_id}"},
                )

                channel_name = metadata.get("name", channel.name)
                add_log(channel_id, f"Channel name: {channel_name}")

                add_log(channel_id, f"Fetching videos from last {channel.time_range_months} months...")
                videos_data = youtube_service.get_channel_videos_with_api(
                    youtube_api_key,
                    resolved_channel_id,
                    channel.time_range_months,
                )
                add_log(channel_id, f"Found {len(videos_data)} videos")

            except Exception as e:
                add_log(channel_id, f"YouTube API error: {str(e)}", "warning")
                add_log(channel_id, "Continuing without video list (manual entry may be needed)")

        if not videos_data:
            add_log(channel_id, "No videos found or YouTube API not configured", "warning")
            _update_channel_attr(channel_id, status="completed", video_count=0, processed_video_count=0)
            add_log(channel_id, "Channel processing complete (no videos)")
            return

        # Update video count
        _update_channel_attr(channel_id, video_count=len(videos_data))

        gemini_api_key = settings.gemini_api_key
        if not gemini_api_key:
            add_log(channel_id, "Gemini API key not configured", "error")
            _update_channel_attr(channel_id, status="failed")
            return

        add_log(channel_id, "Processing videos in parallel (10 at a time)...")

        processed_count = [0]

        def process_video_task(video_data):
            return process_video_threadsafe(channel_id, video_data, gemini_api_key)

        # Filter out already processed videos
        videos_to_process = []
        for video_data in videos_data:
            video_id = video_data.get("video_id")
            # Check via GSI3
            check = table.query(
                IndexName="GSI3-index",
                KeyConditionExpression=Key("GSI3PK").eq(f"YTVID#{video_id}"),
                Limit=1,
            )
            if not check.get("Items"):
                videos_to_process.append(video_data)
            else:
                processed_count[0] += 1

        if processed_count[0] > 0:
            add_log(channel_id, f"Skipping {processed_count[0]} already processed videos")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_video_task, vd): vd for vd in videos_to_process}

            for future in as_completed(futures):
                video_data = futures[future]
                try:
                    future.result()
                    with progress_lock:
                        processed_count[0] += 1
                        _update_channel_attr(channel_id, processed_video_count=processed_count[0])

                        # Check for cancellation
                        check_resp = table.get_item(
                            Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"}
                        )
                        if check_resp.get("Item", {}).get("status") == "cancelled":
                            add_log(channel_id, "Processing cancelled by user")
                            executor.shutdown(wait=False, cancel_futures=True)
                            return

                except Exception as e:
                    add_log(
                        channel_id,
                        f"Error processing video '{video_data.get('title', 'unknown')}': {str(e)}",
                        "warning",
                    )
                    with progress_lock:
                        processed_count[0] += 1
                        _update_channel_attr(channel_id, processed_video_count=processed_count[0])

        # Check one more time before marking complete
        check_resp = table.get_item(
            Key={"PK": f"CHANNEL#{channel_id}", "SK": f"CHANNEL#{channel_id}"}
        )
        if check_resp.get("Item", {}).get("status") == "cancelled":
            add_log(channel_id, "Processing cancelled by user")
            return

        _update_channel_attr(channel_id, status="completed")
        add_log(channel_id, f"Channel processing complete! Processed {processed_count[0]} videos.")

        # Backfill historical prices
        add_log(channel_id, "Backfilling historical prices...")
        try:
            backfill_historical_prices(channel_id)
            add_log(channel_id, "Historical prices backfill complete.")
        except Exception as e:
            add_log(channel_id, f"Historical prices backfill failed: {str(e)}", "warning")

    except Exception as e:
        add_log(channel_id, f"Processing failed: {str(e)}", "error")
        _update_channel_attr(channel_id, status="failed")
        raise


def process_video_threadsafe(
    channel_id: str,
    video_data: dict,
    gemini_api_key: str,
) -> dict:
    """Process a single video in a thread-safe manner."""
    table = get_table()
    stocks_table = get_table("-Stocks")

    video_id = video_data.get("video_id")
    title = video_data.get("title", "Unknown")
    video_url = video_data.get("url", f"https://www.youtube.com/watch?v={video_id}")

    add_log(channel_id, f"Processing: \"{title[:50]}...\"" if len(title) > 50 else f"Processing: \"{title}\"")

    # Check if video already exists (double-check for race condition)
    check = table.query(
        IndexName="GSI3-index",
        KeyConditionExpression=Key("GSI3PK").eq(f"YTVID#{video_id}"),
        Limit=1,
    )
    if check.get("Items"):
        add_log(channel_id, f"Video already processed, skipping: {title[:30]}...")
        return {"status": "skipped", "video_id": video_id}

    # Parse published_at
    published_str = video_data.get("published_at", "")
    try:
        if "T" in published_str:
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00")).date().isoformat()
        else:
            published_at = date.fromisoformat(published_str).isoformat()
    except Exception:
        published_at = date.today().isoformat()

    # Create video record
    video = Video(
        channel_id=channel_id,
        youtube_video_id=video_id,
        title=title,
        url=video_url,
        published_at=published_at,
        transcript_status="fetched",
        analysis_status="pending",
    )
    table.put_item(Item=video.to_item())

    # Extract stock mentions using Gemini
    try:
        mentions_data = gemini_service.extract_stock_mentions_from_video(
            gemini_api_key,
            video_url,
        )
    except Exception as e:
        # Update video analysis status to failed
        table.update_item(
            Key={"PK": f"CHANNEL#{channel_id}", "SK": f"VIDEO#{video.id}"},
            UpdateExpression="SET analysis_status = :status",
            ExpressionAttributeValues={":status": "failed"},
        )
        add_log(channel_id, f"Gemini analysis failed for '{title[:30]}...': {str(e)}", "warning")
        return {"status": "failed", "video_id": video_id, "error": str(e)}

    # Update video analysis status
    table.update_item(
        Key={"PK": f"CHANNEL#{channel_id}", "SK": f"VIDEO#{video.id}"},
        UpdateExpression="SET analysis_status = :status",
        ExpressionAttributeValues={":status": "completed"},
    )

    if not mentions_data:
        add_log(channel_id, f"No stock mentions found in: {title[:40]}...")
        return {"status": "completed", "video_id": video_id, "mentions": 0}

    # Save mentions
    mention_count = 0
    for mention_data in mentions_data:
        ticker = mention_data.get("ticker", "").upper()
        if not ticker or len(ticker) > 5:
            continue

        # Ensure stock exists in stocks table
        stock_resp = stocks_table.get_item(Key={"ticker": ticker})
        if "Item" not in stock_resp:
            stock_info = stock_price_service.get_stock_info(ticker)
            if stock_info:
                stock = Stock(
                    ticker=ticker,
                    name=stock_info.get("name"),
                    exchange=stock_info.get("exchange", "NYSE"),
                )
            else:
                stock = Stock(ticker=ticker, name=ticker, exchange="NYSE")
            stocks_table.put_item(Item=stock.to_item())

        mention = StockMention(
            video_id=video.id,
            ticker=ticker,
            sentiment=mention_data.get("sentiment", "mentioned"),
            context_snippet=mention_data.get("context"),
            published_at=published_at,
        )
        table.put_item(Item=mention.to_item())
        mention_count += 1

    add_log(channel_id, f"Found {mention_count} stock mentions in: {title[:40]}...")
    return {"status": "completed", "video_id": video_id, "mentions": mention_count}


def process_channel_sync(channel_id: str) -> None:
    """Synchronous wrapper for process_channel (for testing)."""
    process_channel(channel_id)
