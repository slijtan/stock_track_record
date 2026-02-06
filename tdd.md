# Technical Design Document: Stock Track Record

> See [prd.md](./prd.md) for product requirements, user stories, and UI wireframes.

---

## 1. Technical Architecture

### 1.1 Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+ with FastAPI |
| Database | Amazon Aurora Serverless v2 (MySQL-compatible) |
| Frontend | React 18 + Vite (PWA) |
| Charts | Chart.js |
| Stock Data | Yahoo Finance (yfinance) |
| Transcripts | youtube-transcript-api |
| Background Jobs | AWS SQS + Lambda |
| AI/LLM | OpenAI API (GPT-4o-mini) |
| Hosting | AWS (Lambda, Aurora Serverless, S3, CloudFront) |

### 1.2 System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React PWA     │────▶│   FastAPI       │────▶│ Aurora Serverless│
│   (CloudFront)  │     │   (Lambda)      │     │   (MySQL)       │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   AWS SQS       │
                        │   (Job Queue)   │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  Worker Lambda  │
                        │  - YouTube API  │
                        │  - OpenAI API   │
                        │  - yfinance     │
                        └─────────────────┘
```

---

## 2. Data Model

### 2.1 Database Schema (Aurora Serverless MySQL-compatible)

```sql
-- Channels table
CREATE TABLE channels (
    id VARCHAR(36) PRIMARY KEY,  -- UUID
    youtube_channel_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL,
    thumbnail_url VARCHAR(500),
    status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending',
    video_count INT DEFAULT 0,
    processed_video_count INT DEFAULT 0,
    time_range_months INT DEFAULT 12,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);

-- Videos table
CREATE TABLE videos (
    id VARCHAR(36) PRIMARY KEY,  -- UUID
    channel_id VARCHAR(36) NOT NULL,
    youtube_video_id VARCHAR(20) NOT NULL UNIQUE,
    title VARCHAR(500) NOT NULL,
    url VARCHAR(500) NOT NULL,
    published_at DATE NOT NULL,
    transcript_status ENUM('pending', 'fetched', 'failed') DEFAULT 'pending',
    analysis_status ENUM('pending', 'completed', 'failed') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    INDEX idx_channel_id (channel_id),
    INDEX idx_published_at (published_at)
);

-- Stocks table (reference data)
CREATE TABLE stocks (
    ticker VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255),
    exchange ENUM('NYSE', 'NASDAQ') NOT NULL,
    last_price DECIMAL(12, 4),
    price_updated_at TIMESTAMP,
    INDEX idx_exchange (exchange)
);

-- Stock mentions table
CREATE TABLE stock_mentions (
    id VARCHAR(36) PRIMARY KEY,  -- UUID
    video_id VARCHAR(36) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    sentiment ENUM('buy', 'hold', 'sell', 'mentioned') NOT NULL,
    price_at_mention DECIMAL(12, 4),
    confidence_score DECIMAL(3, 2),  -- 0.00 to 1.00
    context_snippet TEXT,  -- Excerpt from transcript
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker),
    INDEX idx_video_id (video_id),
    INDEX idx_ticker (ticker),
    UNIQUE KEY unique_video_ticker (video_id, ticker)
);

-- Processing logs table (for live progress UI)
CREATE TABLE processing_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    channel_id VARCHAR(36) NOT NULL,
    log_level ENUM('info', 'warning', 'error') DEFAULT 'info',
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    INDEX idx_channel_id_created (channel_id, created_at)
);
```

### 2.2 Entity Relationships

```
Channel (1) ──────< (N) Video
Video (1) ──────< (N) StockMention
Stock (1) ──────< (N) StockMention
Channel (1) ──────< (N) ProcessingLog
```

---

## 3. API Endpoints

### 3.1 Channels

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/channels` | Submit new channel for processing |
| GET | `/api/channels` | List all channels (paginated, sorted by created_at desc) |
| GET | `/api/channels/{id}` | Get channel details with summary stats |
| GET | `/api/channels/{id}/stocks` | Get all stocks mentioned in channel |
| GET | `/api/channels/{id}/timeline` | Get chronological list of all mentions |
| GET | `/api/channels/{id}/logs` | Get processing logs (for live progress) |
| DELETE | `/api/channels/{id}` | Delete channel and all related data |

### 3.2 Stocks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/channels/{id}/stocks/{ticker}` | Get stock drill-down for a channel |
| GET | `/api/stocks/{ticker}/price` | Get current price (triggers refresh) |

### 3.3 Request/Response Examples

#### POST /api/channels
```json
// Request
{
    "url": "https://www.youtube.com/@FinanceChannel",
    "time_range_months": 12
}

// Response
{
    "id": "uuid-here",
    "youtube_channel_id": "UC...",
    "name": "Finance Channel",
    "status": "pending",
    "created_at": "2024-01-15T10:30:00Z"
}
```

#### GET /api/channels/{id}/stocks
```json
// Response
{
    "channel_id": "uuid-here",
    "stocks": [
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "first_mention_date": "2024-01-15",
            "first_mention_video_id": "video-uuid",
            "first_mention_video_title": "Top Picks for 2024",
            "price_at_first_mention": 185.50,
            "current_price": 195.25,
            "price_change_percent": 5.25,
            "buy_count": 3,
            "hold_count": 1,
            "sell_count": 0,
            "mentioned_count": 2,
            "total_mentions": 6,
            "yahoo_finance_url": "https://finance.yahoo.com/quote/AAPL"
        }
    ]
}
```

---

## 4. Background Job Flow

### 4.1 Channel Processing Pipeline

```
1. User submits channel URL
   └─▶ API creates channel record (status: pending)
   └─▶ API sends message to SQS queue

2. Worker Lambda picks up job
   └─▶ Update channel status to 'processing'
   └─▶ Fetch channel metadata from YouTube
   └─▶ List all videos within time range
   └─▶ Store video records (status: pending)

3. For each video:
   └─▶ Log: "Processing: {video_title}"
   └─▶ Fetch transcript via youtube-transcript-api
       ├─▶ Success: Update transcript_status to 'fetched'
       └─▶ Failure: Retry 3x, then mark 'failed' and skip

   └─▶ Send transcript to OpenAI for analysis
       Prompt: Extract stock tickers and sentiment
       ├─▶ Success: Store stock mentions
       └─▶ Failure: Retry 3x, then mark analysis 'failed'

   └─▶ For each extracted ticker:
       └─▶ Validate ticker exists (NYSE/NASDAQ)
       └─▶ Fetch historical price for video date
       └─▶ Store stock mention record

   └─▶ Update processed_video_count
   └─▶ Log: "✓ Found {n} stock mentions"

4. After all videos processed:
   └─▶ Update channel status to 'completed'
   └─▶ Log: "Channel processing complete"
```

### 4.2 Error Handling

| Scenario | Behavior |
|----------|----------|
| Transcript unavailable | Log warning, skip video, continue |
| OpenAI API error | Retry 3x with exponential backoff, then skip |
| Invalid ticker | Skip ticker, log warning |
| Price data unavailable | Store mention without price, log warning |
| Rate limiting | Implement backoff, respect API limits |

### 4.3 Retry Configuration

```python
RETRY_CONFIG = {
    "max_attempts": 3,
    "base_delay_seconds": 1,
    "max_delay_seconds": 30,
    "exponential_base": 2
}
```

---

## 5. External Integrations

### 5.1 YouTube Data API / youtube-transcript-api

**Purpose:** Fetch channel metadata, video lists, and transcripts

**Libraries:**
- `youtube-transcript-api` for transcripts (no API key needed)
- `google-api-python-client` for channel/video metadata

**Rate Limits:**
- YouTube Data API: 10,000 quota units/day
- Transcript API: No official limits, implement polite delays

### 5.2 OpenAI API

**Purpose:** Extract stock tickers and sentiment from transcripts

**Model:** `gpt-4o-mini` (fast, cost-effective)

**Setup Requirements:**
1. Create OpenAI account at https://platform.openai.com/
2. Add billing information
3. Generate API key in API Keys section
4. Set `OPENAI_API_KEY` environment variable

**Example Prompt (System):**
```
You are a financial analyst assistant. Analyze YouTube video transcripts and extract stock recommendations.

For each stock mentioned, determine:
- Ticker symbol (US stocks only - NYSE/NASDAQ)
- Sentiment: "buy" (recommending purchase), "hold" (keep position),
  "sell" (recommending to sell), or "mentioned" (discussed without recommendation)

Return ONLY a JSON array with no additional text:
[{"ticker": "AAPL", "sentiment": "buy", "context": "brief quote from transcript"}]

Only include valid US stock tickers. Ignore ETFs, crypto, and non-US stocks.
If no stocks are mentioned, return an empty array: []
```

**Example Prompt (User):**
```
Analyze this transcript and extract stock picks:

{transcript_text}
```

**Python Usage:**
```python
from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze this transcript and extract stock picks:\n\n{transcript}"}
    ],
    response_format={"type": "json_object"},
    temperature=0.1
)

stock_picks = json.loads(response.choices[0].message.content)
```

**Rate Limits:**
- Tier 1: 500 RPM, 200,000 TPM
- Implement queuing for large channels

### 5.3 Yahoo Finance (yfinance)

**Purpose:** Fetch historical and current stock prices

**Library:** `yfinance`

**Usage:**
```python
import yfinance as yf

# Get historical price for a date
ticker = yf.Ticker("AAPL")
hist = ticker.history(start="2024-01-15", end="2024-01-16")
price = hist['Close'].iloc[0]

# Get current price
current_price = ticker.info['regularMarketPrice']
```

**Behavior:**
- Prices refresh on page load (not stored long-term)
- Cache current prices for 5 minutes to reduce API calls

---

## 6. Setup Requirements

### 6.1 Environment Variables

```bash
# Database (Aurora Serverless)
DATABASE_URL=mysql+pymysql://user:pass@cluster.cluster-xxx.us-east-1.rds.amazonaws.com:3306/stock_track_record

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/xxx/stock-track-record

# YouTube
YOUTUBE_API_KEY=xxx

# OpenAI
OPENAI_API_KEY=sk-xxx

# App
FRONTEND_URL=https://app.example.com
```

### 6.2 OpenAI API Setup Guide

1. **Create OpenAI Account**
   - Go to https://platform.openai.com/
   - Sign up or log in

2. **Add Billing**
   - Navigate to Settings > Billing
   - Add payment method
   - Set usage limits (recommended: $20/month for personal use)

3. **Create API Key**
   - Go to API Keys section
   - Click "Create new secret key"
   - Name it "Stock Track Record"
   - Copy the key immediately (it won't be shown again)

4. **Test API Key**
   ```bash
   curl https://api.openai.com/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_KEY" \
     -d '{
       "model": "gpt-4o-mini",
       "messages": [{"role": "user", "content": "Hello"}]
     }'
   ```

### 6.3 Aurora Serverless Setup Guide

1. **Create Aurora Serverless v2 Cluster**
   - Go to AWS RDS Console
   - Click "Create database"
   - Select "Amazon Aurora" > "Aurora (MySQL Compatible)"
   - Choose "Serverless v2"
   - Set min/max ACUs (0.5-2 ACU for personal use)

2. **Configure Security**
   - Create VPC security group allowing port 3306
   - Enable Data API for Lambda access (optional)
   - Store credentials in AWS Secrets Manager

3. **Create Database**
   ```sql
   CREATE DATABASE stock_track_record;
   ```

### 6.4 Local Development Setup

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Database (local MySQL for development)
docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=stock_track_record mysql:8
```

---

## 7. Scalability & Limitations

### 7.1 Scalability Considerations
- Lambda concurrency limits for large channels
- Database connection pooling for high traffic
- CDN caching for static assets and common API responses
- Consider batch processing for channels with 500+ videos

### 7.2 Known Limitations
- US stocks only (NYSE/NASDAQ)
- Relies on transcript availability
- OpenAI extraction accuracy varies with transcript quality
- Historical prices may have gaps for delisted stocks
- No real-time price streaming
- Aurora Serverless cold starts may cause initial latency
