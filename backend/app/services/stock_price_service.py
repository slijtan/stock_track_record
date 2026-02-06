from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List
import httpx
from sqlalchemy.orm import Session

from app.db.models import Stock
from app.config import get_settings

# Simple in-memory cache for prices
_price_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_MINUTES = 5

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def get_finnhub_quote(ticker: str, api_key: str) -> Optional[float]:
    """Get current price from Finnhub for a single ticker."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{FINNHUB_BASE_URL}/quote",
                params={"symbol": ticker, "token": api_key}
            )
            if response.status_code == 200:
                data = response.json()
                # 'c' is current price
                price = data.get("c")
                if price and price > 0:
                    return float(price)
    except Exception as e:
        print(f"Finnhub error for {ticker}: {e}")
    return None


def get_batch_current_prices_finnhub(tickers: List[str], api_key: str, max_tickers: int = 55) -> Dict[str, float]:
    """Get current prices from Finnhub respecting 60 calls/min rate limit."""
    import time

    prices = {}

    # Limit to max_tickers to stay within rate limits and Lambda timeout
    tickers_to_fetch = tickers[:max_tickers]

    if len(tickers) > max_tickers:
        print(f"Limiting price fetch to {max_tickers} tickers (of {len(tickers)})")

    with httpx.Client(timeout=5.0) as client:
        for i, ticker in enumerate(tickers_to_fetch):
            try:
                response = client.get(
                    f"{FINNHUB_BASE_URL}/quote",
                    params={"symbol": ticker.upper(), "token": api_key}
                )
                if response.status_code == 200:
                    data = response.json()
                    price = data.get("c")
                    if price and price > 0:
                        prices[ticker.upper()] = float(price)
                elif response.status_code == 429:
                    print(f"Rate limited at ticker {i+1}/{len(tickers_to_fetch)}")
                    time.sleep(5)  # Wait longer on rate limit
            except Exception as e:
                print(f"Error fetching {ticker}: {e}")

            # Wait 1.1 seconds between calls to stay under 60/min
            if i < len(tickers_to_fetch) - 1:
                time.sleep(1.1)

    return prices


def is_valid_us_ticker(ticker: str) -> bool:
    """Check if ticker is a valid US stock ticker."""
    ticker = ticker.upper()
    # Allow BRK.A, BRK.B style tickers
    if '.' in ticker:
        parts = ticker.split('.')
        if len(parts) == 2 and len(parts[0]) <= 4 and len(parts[1]) == 1:
            return True  # e.g., BRK.A, BRK.B
        return False  # e.g., HO.PA (Paris exchange)
    return len(ticker) <= 5


def get_batch_current_prices(tickers: List[str]) -> Dict[str, float]:
    """Get current prices for multiple tickers. Uses Finnhub if available, falls back to Yahoo."""
    if not tickers:
        return {}

    # Filter out invalid tickers (non-US exchanges, too long, etc.)
    valid_tickers = [t.upper() for t in tickers if is_valid_us_ticker(t)]

    if not valid_tickers:
        return {}

    # Try Finnhub first (better rate limits)
    settings = get_settings()
    if settings.finnhub_api_key:
        prices = get_batch_current_prices_finnhub(valid_tickers, settings.finnhub_api_key)
        if prices:
            return prices

    # Fall back to Yahoo Finance
    return get_batch_current_prices_yahoo(valid_tickers)


def get_batch_current_prices_yahoo(tickers: List[str]) -> Dict[str, float]:
    """Get current prices from Yahoo Finance (batch API call)."""
    try:
        import yfinance as yf  # Lazy import
    except ImportError:
        print("yfinance not available, cannot fetch Yahoo prices")
        return {}
    if not tickers:
        return {}

    ticker_str = " ".join(tickers)

    try:
        # Use download with period="5d" to get recent prices (more reliable than 1d)
        data = yf.download(ticker_str, period="5d", progress=False, threads=False)

        if data.empty:
            return {}

        prices = {}
        # Handle single ticker (returns Series) vs multiple (returns DataFrame with MultiIndex)
        if len(tickers) == 1:
            ticker = tickers[0]
            if "Close" in data.columns and not data["Close"].empty:
                prices[ticker] = float(data["Close"].iloc[-1])
        else:
            # Multiple tickers - Close column has ticker sub-columns
            if "Close" in data.columns:
                close_data = data["Close"]
                for ticker in tickers:
                    if ticker in close_data.columns:
                        val = close_data[ticker].iloc[-1]
                        if not (val != val):  # Check for NaN
                            prices[ticker] = float(val)

        return prices
    except Exception as e:
        print(f"Yahoo batch price fetch error: {e}")
        return {}


def get_batch_historical_prices(ticker_dates: List[tuple]) -> Dict[str, float]:
    """
    Get historical prices for multiple ticker/date pairs.

    Args:
        ticker_dates: List of (ticker, date, mention_id) tuples

    Returns:
        Dict mapping mention_id to price
    """
    try:
        import yfinance as yf  # Lazy import
    except ImportError:
        print("yfinance not available, cannot fetch historical prices")
        return {}
    if not ticker_dates:
        return {}

    # Group by ticker to minimize API calls
    ticker_groups: Dict[str, List[tuple]] = {}
    for ticker, target_date, mention_id in ticker_dates:
        ticker = ticker.upper()
        if ticker not in ticker_groups:
            ticker_groups[ticker] = []
        ticker_groups[ticker].append((target_date, mention_id))

    results = {}

    # Find overall date range needed
    all_dates = [d for _, dates in ticker_groups.items() for d, _ in dates]
    if not all_dates:
        return {}

    min_date = min(all_dates) - timedelta(days=7)
    max_date = max(all_dates) + timedelta(days=1)

    try:
        # Single API call for all tickers across the full date range
        tickers_list = list(ticker_groups.keys())
        ticker_str = " ".join(tickers_list)

        data = yf.download(
            ticker_str,
            start=min_date.isoformat(),
            end=max_date.isoformat(),
            progress=False
        )

        if data.empty:
            return results

        # Process each ticker's dates
        for ticker, date_mentions in ticker_groups.items():
            for target_date, mention_id in date_mentions:
                try:
                    # Get close prices for this ticker
                    if len(tickers_list) == 1:
                        close_series = data["Close"]
                    else:
                        if "Close" not in data.columns or ticker not in data["Close"].columns:
                            continue
                        close_series = data["Close"][ticker]

                    # Find closest date on or before target
                    available_dates = close_series.dropna().index.date
                    valid_dates = [d for d in available_dates if d <= target_date]

                    if valid_dates:
                        closest_date = max(valid_dates)
                        mask = close_series.index.date == closest_date
                        if mask.any():
                            price = float(close_series[mask].iloc[0])
                            results[mention_id] = price
                except Exception:
                    continue

        return results
    except Exception as e:
        print(f"Batch historical price fetch error: {e}")
        return {}


def get_current_price(db: Session, ticker: str) -> Dict[str, Any]:
    """Get current stock price - returns from DB or fetches from Finnhub."""
    ticker = ticker.upper()

    # Check memory cache first
    if ticker in _price_cache:
        cached = _price_cache[ticker]
        if datetime.utcnow() - cached["cached_at"] < timedelta(minutes=CACHE_TTL_MINUTES):
            return {
                "price": cached["price"],
                "updated_at": cached["updated_at"],
            }

    # Check database for recent price (within 1 hour)
    db_stock = db.query(Stock).filter(Stock.ticker == ticker).first()
    if db_stock and db_stock.last_price and db_stock.price_updated_at:
        age = datetime.utcnow() - db_stock.price_updated_at
        if age < timedelta(hours=1):
            # Cache it and return
            _price_cache[ticker] = {
                "price": float(db_stock.last_price),
                "updated_at": db_stock.price_updated_at,
                "cached_at": datetime.utcnow(),
            }
            return {
                "price": float(db_stock.last_price),
                "updated_at": db_stock.price_updated_at,
            }

    # Fetch from Finnhub (fast, good rate limits)
    settings = get_settings()
    if settings.finnhub_api_key:
        price = get_finnhub_quote(ticker, settings.finnhub_api_key)
        if price:
            now = datetime.utcnow()
            # Update cache
            _price_cache[ticker] = {
                "price": price,
                "updated_at": now,
                "cached_at": now,
            }
            # Update database
            if db_stock:
                db_stock.last_price = price
                db_stock.price_updated_at = now
                db.commit()
            return {"price": price, "updated_at": now}

    # Return stale DB price if available
    if db_stock and db_stock.last_price:
        return {
            "price": float(db_stock.last_price),
            "updated_at": db_stock.price_updated_at,
        }

    raise ValueError(f"Could not fetch price for {ticker}")


def get_historical_price_alpha_vantage(ticker: str, target_date: date, api_key: str) -> Optional[float]:
    """Get historical closing price from Alpha Vantage."""
    try:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker.upper(),
            "outputsize": "compact",  # Last 100 days
            "apikey": api_key
        }
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                time_series = data.get("Time Series (Daily)", {})
                if not time_series:
                    return None

                # Find closest date on or before target
                available_dates = sorted([datetime.strptime(d, "%Y-%m-%d").date() for d in time_series.keys()], reverse=True)
                valid_dates = [d for d in available_dates if d <= target_date]

                if not valid_dates:
                    return None

                closest_date = valid_dates[0]
                day_data = time_series.get(closest_date.isoformat())
                if day_data:
                    return float(day_data.get("4. close", 0))
    except Exception as e:
        print(f"Alpha Vantage error for {ticker}: {e}")
    return None


def get_historical_price(ticker: str, target_date: date) -> Optional[float]:
    """Get historical closing price for a specific date."""
    try:
        import yfinance as yf  # Lazy import
    except ImportError:
        print("yfinance not available, cannot fetch historical price")
        return None
    ticker = ticker.upper()
    settings = get_settings()

    # Try Yahoo Finance first
    try:
        stock = yf.Ticker(ticker)

        # Fetch data for a range around the target date to handle weekends/holidays
        start_date = target_date - timedelta(days=7)
        end_date = target_date + timedelta(days=1)

        hist = stock.history(start=start_date.isoformat(), end=end_date.isoformat())

        if not hist.empty:
            # Find the closest date that's on or before the target date
            available_dates = hist.index.date
            valid_dates = [d for d in available_dates if d <= target_date]

            if valid_dates:
                closest_date = max(valid_dates)
                row = hist[hist.index.date == closest_date]
                if not row.empty:
                    return float(row["Close"].iloc[0])
    except Exception:
        pass

    # Fall back to Alpha Vantage if configured
    if settings.alpha_vantage_api_key:
        return get_historical_price_alpha_vantage(ticker, target_date, settings.alpha_vantage_api_key)

    return None


def validate_ticker(ticker: str) -> bool:
    """Validate if a ticker exists on NYSE or NASDAQ."""
    try:
        import yfinance as yf  # Lazy import
    except ImportError:
        # Can't validate without yfinance, assume valid
        return True
    ticker = ticker.upper()

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Check if it's a valid stock
        if info.get("quoteType") not in ["EQUITY"]:
            return False

        # Check exchange
        exchange = info.get("exchange", "")
        valid_exchanges = ["NYQ", "NMS", "NGM", "NYSE", "NASDAQ"]

        return any(ex in exchange.upper() for ex in valid_exchanges)
    except Exception:
        return False


def get_stock_info(ticker: str) -> Optional[Dict[str, Any]]:
    """Get stock information."""
    try:
        import yfinance as yf  # Lazy import
    except ImportError:
        # Return minimal info without yfinance
        return {"ticker": ticker.upper(), "name": ticker.upper(), "exchange": "NYSE", "current_price": None}
    ticker = ticker.upper()

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName"),
            "exchange": "NASDAQ" if "NAS" in info.get("exchange", "").upper() else "NYSE",
            "current_price": info.get("regularMarketPrice"),
        }
    except Exception:
        return None
