import json
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI

SYSTEM_PROMPT = """You are a financial analyst assistant. Analyze YouTube video transcripts and extract stock recommendations.

For each stock mentioned, determine:
- Ticker symbol (US stocks only - NYSE/NASDAQ)
- Sentiment: "buy" (recommending purchase), "hold" (keep position), "sell" (recommending to sell), or "mentioned" (discussed without recommendation)

Return ONLY a JSON object with a "stocks" array containing objects with these fields:
- ticker: The stock ticker symbol (e.g., "AAPL", "TSLA")
- sentiment: One of "buy", "hold", "sell", or "mentioned"
- context: A brief quote or summary from the transcript (max 100 chars)

Example response:
{"stocks": [{"ticker": "AAPL", "sentiment": "buy", "context": "I think Apple is a great buy right now"}]}

Rules:
- Only include valid US stock tickers from NYSE or NASDAQ
- Ignore ETFs (like SPY, QQQ), crypto, and non-US stocks
- If no stocks are mentioned, return: {"stocks": []}
- Be conservative with sentiment - only use "buy"/"sell" for clear recommendations
- Use "mentioned" when a stock is discussed without a clear recommendation"""


def extract_stock_mentions(
    api_key: str,
    transcript: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Extract stock mentions and sentiment from transcript using OpenAI.

    Args:
        api_key: OpenAI API key
        transcript: Video transcript text
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (exponential backoff)

    Returns:
        List of stock mentions with ticker, sentiment, and context
    """
    if not api_key:
        raise ValueError("OpenAI API key is required")

    if not transcript or len(transcript.strip()) < 50:
        return []

    # Truncate very long transcripts
    max_transcript_length = 15000
    if len(transcript) > max_transcript_length:
        transcript = transcript[:max_transcript_length] + "..."

    client = OpenAI(api_key=api_key)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Analyze this transcript and extract stock picks:\n\n{transcript}",
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1000,
            )

            content = response.choices[0].message.content
            if not content:
                return []

            result = json.loads(content)
            stocks = result.get("stocks", [])

            # Validate and clean results
            valid_stocks = []
            for stock in stocks:
                ticker = stock.get("ticker", "").upper().strip()
                sentiment = stock.get("sentiment", "").lower().strip()
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
            if any(term in error_str for term in ["rate", "limit", "429", "500", "503"]):
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
            raise

    return []


def validate_stock_mentions(
    mentions: List[Dict[str, Any]],
    valid_tickers: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Validate extracted stock mentions against known tickers.

    Args:
        mentions: List of extracted mentions
        valid_tickers: Optional list of valid ticker symbols

    Returns:
        Filtered list of valid mentions
    """
    if not valid_tickers:
        # If no list provided, do basic validation
        return [
            m for m in mentions
            if m.get("ticker") and len(m["ticker"]) <= 5
        ]

    valid_set = set(t.upper() for t in valid_tickers)
    return [m for m in mentions if m.get("ticker", "").upper() in valid_set]
