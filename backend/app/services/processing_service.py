from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Channel, Video, Stock, StockMention, ProcessingLog
from app.services import youtube_service, gemini_service, stock_price_service

settings = get_settings()

# Lock for thread-safe progress updates
progress_lock = Lock()

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def get_yahoo_historical_price(ticker: str, target_date: date) -> Optional[float]:
    """Get historical closing price from Yahoo Finance for a specific date."""
    try:
        import yfinance as yf  # Lazy import to avoid loading in API Lambda
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

        # Find the closest date on or before target
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
    # Get cookies from main page
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

                # Build date -> price mapping
                prices = {}
                for ts, close in zip(timestamps, closes):
                    if close is not None:
                        dt = datetime.fromtimestamp(ts).date()
                        prices[dt] = close
                return prices
    except Exception as e:
        print(f"  Yahoo fetch error for {ticker}: {e}")

    return {}


def backfill_historical_prices(db: Session, channel_id: str) -> int:
    """Backfill missing historical prices using Yahoo Finance with session cookies."""
    import importlib.util
    if importlib.util.find_spec("yfinance") is None:
        print("yfinance not available, skipping historical price backfill")
        return 0
    import time as time_module

    # Get all mentions missing price_at_mention
    videos = db.query(Video).filter(Video.channel_id == channel_id).all()
    video_map = {v.id: v for v in videos}
    video_ids = list(video_map.keys())

    if not video_ids:
        return 0

    mentions = (
        db.query(StockMention)
        .filter(StockMention.video_id.in_(video_ids))
        .filter(StockMention.price_at_mention.is_(None))
        .all()
    )

    if not mentions:
        return 0

    # Group mentions by ticker
    ticker_mentions = {}
    for mention in mentions:
        video = video_map.get(mention.video_id)
        if video:
            ticker = mention.ticker.upper()
            # Skip invalid tickers
            if '.' in ticker and not (len(ticker.split('.')[1]) == 1):
                continue  # Skip non-US tickers like HO.PA
            if ticker not in ticker_mentions:
                ticker_mentions[ticker] = []
            ticker_mentions[ticker].append((mention, video.published_at))

    if not ticker_mentions:
        return 0

    tickers = list(ticker_mentions.keys())
    print(f"Backfilling historical data for {len(tickers)} tickers")

    # Create Yahoo session with cookies
    print("Creating Yahoo Finance session...")
    session = _get_yahoo_session()
    time_module.sleep(1)

    updated = 0

    # Process one ticker at a time
    for i, ticker in enumerate(tickers):
        mention_dates = ticker_mentions[ticker]
        print(f"[{i+1}/{len(tickers)}] Processing {ticker} ({len(mention_dates)} mentions)")

        # Add delay between requests
        if i > 0:
            time_module.sleep(0.5)

        # Get date range for this ticker
        all_dates = [d for _, d in mention_dates]
        min_date = min(all_dates) - timedelta(days=7)
        max_date = max(all_dates) + timedelta(days=1)

        # Fetch historical data
        prices = _fetch_yahoo_historical(session, ticker, min_date, max_date)

        if prices:
            available_dates = sorted(prices.keys())

            for mention, target_date in mention_dates:
                # Find closest date on or before target
                valid_dates = [d for d in available_dates if d <= target_date]
                if valid_dates:
                    closest_date = max(valid_dates)
                    price = prices.get(closest_date)
                    if price:
                        mention.price_at_mention = float(price)
                        updated += 1
        else:
            print(f"  No data for {ticker}")

        # Commit after each ticker
        db.commit()

    print(f"Backfill complete: {updated} prices updated out of {len(mentions)} mentions")
    return updated


def add_log(db: Session, channel_id: str, message: str, level: str = "info") -> None:
    """Add a processing log entry."""
    log = ProcessingLog(
        channel_id=channel_id,
        message=message,
        log_level=level,
    )
    db.add(log)
    db.commit()


def process_channel(db: Session, channel_id: str) -> None:
    """
    Process a channel: fetch videos and analyze with Gemini in parallel.

    This is the main processing pipeline.
    """
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise ValueError(f"Channel not found: {channel_id}")

    try:
        # Update status to processing
        channel.status = "processing"
        db.commit()
        add_log(db, channel_id, "Starting channel processing...")

        # Extract channel info from URL
        channel_info = youtube_service.extract_channel_info_from_url(channel.url)
        add_log(db, channel_id, f"Extracted channel info: {channel_info['identifier']}")

        # Try to get channel metadata using API
        youtube_api_key = settings.youtube_api_key
        videos_data = []

        if youtube_api_key:
            try:
                # Resolve channel ID
                add_log(db, channel_id, "Resolving channel ID...")
                resolved_channel_id = youtube_service.resolve_channel_id(
                    youtube_api_key,
                    channel_info["identifier"],
                    channel_info["type"],
                )

                # Get metadata
                metadata = youtube_service.get_channel_metadata(youtube_api_key, resolved_channel_id)
                channel.youtube_channel_id = resolved_channel_id
                channel.name = metadata.get("name", channel.name)
                channel.thumbnail_url = metadata.get("thumbnail_url")
                db.commit()

                add_log(db, channel_id, f"Channel name: {channel.name}")

                # Get videos
                add_log(db, channel_id, f"Fetching videos from last {channel.time_range_months} months...")
                videos_data = youtube_service.get_channel_videos_with_api(
                    youtube_api_key,
                    resolved_channel_id,
                    channel.time_range_months,
                )
                add_log(db, channel_id, f"Found {len(videos_data)} videos")

            except Exception as e:
                add_log(db, channel_id, f"YouTube API error: {str(e)}", "warning")
                add_log(db, channel_id, "Continuing without video list (manual entry may be needed)")

        if not videos_data:
            add_log(db, channel_id, "No videos found or YouTube API not configured", "warning")
            channel.status = "completed"
            channel.video_count = 0
            channel.processed_video_count = 0
            db.commit()
            add_log(db, channel_id, "Channel processing complete (no videos)")
            return

        # Update video count
        channel.video_count = len(videos_data)
        db.commit()

        # Check for Gemini API key
        gemini_api_key = settings.gemini_api_key
        if not gemini_api_key:
            add_log(db, channel_id, "Gemini API key not configured", "error")
            channel.status = "failed"
            db.commit()
            return

        # Process videos in parallel (10 at a time)
        add_log(db, channel_id, "Processing videos in parallel (10 at a time)...")

        processed_count = [0]  # Use list for mutable reference in closure

        def process_video_task(video_data):
            """Task to process a single video in a thread."""
            # Each thread gets its own DB session
            thread_db = SessionLocal()
            try:
                result = process_video_threadsafe(
                    thread_db,
                    channel_id,
                    video_data,
                    gemini_api_key,
                )
                return result
            finally:
                thread_db.close()

        # Filter out already processed videos first
        videos_to_process = []
        for video_data in videos_data:
            video_id = video_data.get("video_id")
            existing = db.query(Video).filter(Video.youtube_video_id == video_id).first()
            if not existing:
                videos_to_process.append(video_data)
            else:
                processed_count[0] += 1

        if processed_count[0] > 0:
            add_log(db, channel_id, f"Skipping {processed_count[0]} already processed videos")

        # Process remaining videos in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_video_task, vd): vd for vd in videos_to_process}

            for future in as_completed(futures):
                video_data = futures[future]
                try:
                    future.result()  # Get result to check for exceptions
                    with progress_lock:
                        processed_count[0] += 1
                        # Update progress in main db session
                        db.refresh(channel)
                        channel.processed_video_count = processed_count[0]
                        db.commit()

                        # Check for cancellation
                        if channel.status == "cancelled":
                            add_log(db, channel_id, "Processing cancelled by user")
                            executor.shutdown(wait=False, cancel_futures=True)
                            return

                except Exception as e:
                    add_log(
                        db, channel_id,
                        f"Error processing video '{video_data.get('title', 'unknown')}': {str(e)}",
                        "warning"
                    )
                    with progress_lock:
                        processed_count[0] += 1
                        channel.processed_video_count = processed_count[0]
                        db.commit()

        # Check one more time before marking complete
        db.refresh(channel)
        if channel.status == "cancelled":
            add_log(db, channel_id, "Processing cancelled by user")
            return

        # Mark as completed
        channel.status = "completed"
        db.commit()
        add_log(db, channel_id, f"Channel processing complete! Processed {channel.processed_video_count} videos.")

        # Backfill historical prices for all mentions
        add_log(db, channel_id, "Backfilling historical prices...")
        try:
            backfill_historical_prices(db, channel_id)
            add_log(db, channel_id, "Historical prices backfill complete.")
        except Exception as e:
            add_log(db, channel_id, f"Historical prices backfill failed: {str(e)}", "warning")

    except Exception as e:
        add_log(db, channel_id, f"Processing failed: {str(e)}", "error")
        channel.status = "failed"
        db.commit()
        raise


def process_video_threadsafe(
    db: Session,
    channel_id: str,
    video_data: dict,
    gemini_api_key: str,
) -> dict:
    """Process a single video in a thread-safe manner with its own DB session."""
    video_id = video_data.get("video_id")
    title = video_data.get("title", "Unknown")
    video_url = video_data.get("url", f"https://www.youtube.com/watch?v={video_id}")

    add_log(db, channel_id, f"Processing: \"{title[:50]}...\"" if len(title) > 50 else f"Processing: \"{title}\"")

    # Check if video already exists (double-check in case of race condition)
    existing = db.query(Video).filter(Video.youtube_video_id == video_id).first()
    if existing:
        add_log(db, channel_id, f"Video already processed, skipping: {title[:30]}...")
        return {"status": "skipped", "video_id": video_id}

    # Create video record
    published_str = video_data.get("published_at", "")
    try:
        if "T" in published_str:
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00")).date()
        else:
            published_at = date.fromisoformat(published_str)
    except Exception:
        published_at = date.today()

    video = Video(
        channel_id=channel_id,
        youtube_video_id=video_id,
        title=title,
        url=video_url,
        published_at=published_at,
        transcript_status="fetched",
        analysis_status="pending",
    )
    db.add(video)
    db.commit()

    # Extract stock mentions using Gemini
    try:
        mentions = gemini_service.extract_stock_mentions_from_video(
            gemini_api_key,
            video_url,
        )
    except Exception as e:
        video.analysis_status = "failed"
        db.commit()
        add_log(db, channel_id, f"Gemini analysis failed for '{title[:30]}...': {str(e)}", "warning")
        return {"status": "failed", "video_id": video_id, "error": str(e)}

    video.analysis_status = "completed"
    db.commit()

    if not mentions:
        add_log(db, channel_id, f"No stock mentions found in: {title[:40]}...")
        return {"status": "completed", "video_id": video_id, "mentions": 0}

    # Save mentions
    mention_count = 0
    for mention_data in mentions:
        ticker = mention_data.get("ticker", "").upper()
        if not ticker or len(ticker) > 5:
            continue

        # Ensure stock exists in database
        stock = db.query(Stock).filter(Stock.ticker == ticker).first()
        if not stock:
            # Try to get stock info, but don't skip if Yahoo fails
            stock_info = stock_price_service.get_stock_info(ticker)
            if stock_info:
                stock = Stock(
                    ticker=ticker,
                    name=stock_info.get("name"),
                    exchange=stock_info.get("exchange", "NYSE"),
                )
            else:
                # Yahoo failed, create stock with minimal info
                stock = Stock(
                    ticker=ticker,
                    name=ticker,
                    exchange="NYSE",
                )
            db.add(stock)
            db.commit()

        # Create mention (price will be backfilled in bulk after processing)
        mention = StockMention(
            video_id=video.id,
            ticker=ticker,
            sentiment=mention_data.get("sentiment", "mentioned"),
            price_at_mention=None,  # Backfilled in bulk post-processing
            context_snippet=mention_data.get("context"),
        )
        db.add(mention)
        mention_count += 1

    db.commit()
    add_log(db, channel_id, f"Found {mention_count} stock mentions in: {title[:40]}...")

    return {"status": "completed", "video_id": video_id, "mentions": mention_count}


def process_channel_sync(db: Session, channel_id: str) -> None:
    """Synchronous wrapper for process_channel (for testing)."""
    process_channel(db, channel_id)
