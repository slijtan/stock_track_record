import json
import time
from typing import List, Dict, Any


PROMPT = """Analyze this video and extract ALL stocks discussed. Pay close attention to the speaker's tone, enthusiasm, and any ownership disclosures.

For each stock, classify the sentiment as:

**BUY** - Use when ANY of these apply:
- Speaker says they own the stock or are buying it
- Speaker expresses strong enthusiasm ("I love this stock", "this is a great opportunity")
- Speaker gives a bullish thesis or price target
- Speaker recommends viewers consider buying or adding
- Speaker says they're "bullish" on the stock

**SELL** - Use when ANY of these apply:
- Speaker says they sold or are selling
- Speaker warns against the stock ("stay away", "be careful", "overvalued")
- Speaker expresses bearish outlook
- Speaker recommends viewers consider selling

**HOLD** - Use when:
- Speaker owns but isn't adding or selling
- Speaker says to "wait and see" or "hold your position"
- Mixed outlook - some positives and negatives balanced

**MENTIONED** - Use ONLY when:
- Stock is referenced purely for context or comparison
- No opinion or recommendation is expressed
- Just stating facts without any sentiment

Return a JSON object with a "stocks" array. Each stock should have:
- ticker: Stock symbol (US stocks only - NYSE/NASDAQ)
- sentiment: "buy", "sell", "hold", or "mentioned"
- context: Brief quote or summary capturing WHY you chose this sentiment (max 150 chars)

Example:
{"stocks": [{"ticker": "KTOS", "sentiment": "buy", "context": "I own this stock and think defense spending will drive growth"}]}

Rules:
- Include ALL stocks discussed, even briefly
- Err on the side of inclusion - if a stock is named, include it
- Only valid US stock tickers (NYSE/NASDAQ)
- Ignore ETFs (SPY, QQQ, etc.), crypto, and non-US stocks
- If no stocks mentioned, return: {"stocks": []}
- The context should justify your sentiment classification"""


def extract_stock_mentions_from_video(
    api_key: str,
    youtube_url: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Extract stock mentions and sentiment from a YouTube video using Gemini.

    Uses the google-genai package which can directly analyze YouTube videos.

    Args:
        api_key: Google Gemini API key
        youtube_url: Full YouTube video URL
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (exponential backoff)

    Returns:
        List of stock mentions with ticker, sentiment, and context
    """
    if not api_key:
        raise ValueError("Gemini API key is required")

    if not youtube_url:
        raise ValueError("YouTube URL is required")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    for attempt in range(max_retries):
        try:
            # Use the proper video analysis API
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=[
                    types.Content(
                        parts=[
                            types.Part(
                                file_data=types.FileData(
                                    file_uri=youtube_url,
                                    mime_type='video/mp4'
                                )
                            ),
                            types.Part(text=PROMPT)
                        ]
                    )
                ]
            )

            content = response.text
            if not content:
                return []

            # Extract JSON from response (handle markdown code blocks)
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]

            result = json.loads(json_str.strip())
            stocks = result.get("stocks", [])

            # Validate and clean results
            valid_stocks = []
            for stock in stocks:
                ticker = stock.get("ticker", "").upper().strip()
                # Handle both "sentiment" and "recommendation" field names
                sentiment = stock.get("sentiment") or stock.get("recommendation") or ""
                sentiment = sentiment.lower().strip()
                context = stock.get("context", "")

                # Validate
                if not ticker or len(ticker) > 5:
                    continue
                if sentiment not in ["buy", "hold", "sell", "mentioned"]:
                    sentiment = "mentioned"

                valid_stocks.append({
                    "ticker": ticker,
                    "sentiment": sentiment,
                    "context": context[:200] if context else None,
                })

            return valid_stocks

        except json.JSONDecodeError:
            # Invalid JSON response, retry
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))
                continue
            return []

        except Exception as e:
            error_str = str(e).lower()
            # Rate limiting or server errors - retry
            if any(term in error_str for term in ["rate", "limit", "429", "500", "503", "quota", "resource"]):
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
            # Video processing errors - don't retry
            if "video" in error_str and ("process" in error_str or "access" in error_str):
                return []
            raise

    return []
