# Stock Track Record

A web application that analyzes YouTube channels focused on stock recommendations, extracts stock picks from video transcripts using AI, and tracks their historical performance.

## Features

- **Channel Analysis**: Submit YouTube channel URLs to analyze stock picks
- **AI-Powered Extraction**: Uses Google Gemini 2.0 Flash to directly analyze YouTube videos and extract stock tickers with sentiment
- **Performance Tracking**: Tracks stock prices from mention date vs current price
- **Sentiment Categories**: Buy, Hold, Sell, or Mentioned
- **Interactive Charts**: Stock price chart with recommendation points overlaid (Chart.js)
- **Real-time Progress**: Live log feed during channel processing
- **PWA Support**: Installable as a Progressive Web App on mobile devices

## How It Works

1. **Submit Channel** — User pastes a YouTube channel URL and selects a time range (6/12/24/36 months)
2. **Fetch Videos** — The system uses the YouTube Data API to list all videos in the time range
3. **AI Analysis** — For each video, Google Gemini AI analyzes the content and extracts stock mentions with sentiment (buy/hold/sell/mentioned)
4. **Price Lookup** — Historical prices are fetched from Yahoo Finance for each stock on the date it was mentioned
5. **Display Results** — The UI shows aggregated stock data with performance metrics, timelines, and drill-down charts

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.9+ with FastAPI |
| Database | MySQL 8.0 (Aurora Serverless compatible) |
| ORM | SQLAlchemy 2.0 with Alembic migrations |
| Frontend | React 19 + TypeScript + Vite |
| Styling | Tailwind CSS 4 |
| Charts | Chart.js via react-chartjs-2 |
| AI | Google Gemini 2.0 Flash |
| Video Data | YouTube Data API v3 |
| Stock Data | Yahoo Finance (yfinance) |
| Testing | pytest (backend), Playwright (frontend E2E) |

## Project Structure

```
stock_track_record/
├── backend/
│   ├── app/
│   │   ├── db/
│   │   │   ├── database.py          # SQLAlchemy engine & session
│   │   │   └── models.py            # ORM models (Channel, Video, Stock, StockMention, ProcessingLog)
│   │   ├── routers/
│   │   │   ├── channels.py          # Channel CRUD & analysis endpoints
│   │   │   └── stocks.py            # Stock price endpoints
│   │   ├── schemas/
│   │   │   ├── channel.py           # Pydantic request/response schemas
│   │   │   └── stock.py
│   │   ├── services/
│   │   │   ├── background_tasks.py  # Background task runner (local & Lambda)
│   │   │   ├── channel_service.py   # Channel business logic & aggregation
│   │   │   ├── gemini_service.py    # Google Gemini video analysis
│   │   │   ├── processing_service.py # Main processing pipeline
│   │   │   ├── stock_price_service.py # Yahoo Finance integration
│   │   │   └── youtube_service.py   # YouTube API integration
│   │   ├── config.py                # Pydantic settings management
│   │   └── main.py                  # FastAPI app entry point
│   ├── alembic/                     # Database migration scripts
│   ├── tests/                       # pytest test suite
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.ts            # Axios API client with retry logic
│   │   ├── components/
│   │   │   ├── AddChannelModal.tsx   # Channel submission form
│   │   │   ├── ErrorBoundary.tsx     # Global error boundary
│   │   │   ├── Layout.tsx            # App header & navigation
│   │   │   ├── PriceFetchModal.tsx   # Price refresh UI
│   │   │   ├── ProcessingProgress.tsx # Live progress bar & log feed
│   │   │   └── SentimentBadge.tsx    # Color-coded sentiment indicator
│   │   ├── pages/
│   │   │   ├── ChannelDetails.tsx    # Timeline & stocks views
│   │   │   ├── ChannelList.tsx       # Home page with channel cards
│   │   │   ├── NotFound.tsx          # 404 page
│   │   │   └── StockDrilldown.tsx    # Stock detail with price chart
│   │   ├── types/index.ts           # TypeScript interfaces
│   │   └── utils/priceCache.ts      # Client-side price caching
│   ├── tests/                       # Playwright E2E tests
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml               # MySQL for local development
├── prd.md                           # Product Requirements Document
├── tdd.md                           # Technical Design Document
└── tasks.md                         # Implementation task tracker
```

## Prerequisites

- **Python 3.9+**
- **Node.js 20+**
- **Docker** (for MySQL database)
- **Google Gemini API key** (required for AI video analysis)
- **YouTube Data API key** (optional but recommended — needed to fetch video lists from channels)

## Quick Start (Local Development)

### 1. Start the Database

From the project root:

```bash
docker compose up -d
```

This starts a MySQL 8.0 container on **port 3307** with:
- Root password: `root`
- Database: `stock_track_record`
- Data persisted in a Docker volume

Verify it's running:

```bash
docker compose ps
```

### 2. Set Up the Backend

```bash
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file from template
cp .env.example .env
```

Edit `backend/.env` with your API keys:

```bash
# Database (matches docker-compose.yml)
DATABASE_URL=mysql+pymysql://root:root@localhost:3307/stock_track_record

# Gemini API (REQUIRED - for AI video analysis)
GEMINI_API_KEY=your_gemini_api_key_here

# YouTube Data API (optional but recommended - for fetching video lists)
YOUTUBE_API_KEY=your_youtube_api_key_here

# Frontend URL (for CORS - default is correct for local dev)
FRONTEND_URL=http://localhost:5173

# Debug mode
DEBUG=true
```

Run database migrations:

```bash
alembic upgrade head
```

Start the backend server:

```bash
uvicorn app.main:app --reload
```

The API will be available at:
- **API root**: http://localhost:8000
- **Interactive docs (Swagger)**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

### 3. Set Up the Frontend

In a new terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The app will be available at **http://localhost:5173**

The Vite dev server automatically proxies `/api` requests to the backend at `http://localhost:8000`.

## API Key Setup

### Google Gemini API (Required)

The Gemini API is used to analyze YouTube videos and extract stock recommendations.

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. Click **"Get API Key"**
4. Create a new API key or use an existing one
5. Add to `backend/.env` as `GEMINI_API_KEY`

**Cost**: Gemini 2.0 Flash has a generous free tier suitable for personal use.

### YouTube Data API (Optional but Recommended)

Without this key, the app cannot fetch the list of videos from a channel. With it, the full channel analysis pipeline works end-to-end.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Navigate to **APIs & Services > Library**
4. Search for and enable **"YouTube Data API v3"**
5. Go to **Credentials > Create Credentials > API Key**
6. Add to `backend/.env` as `YOUTUBE_API_KEY`

**Cost**: Free tier includes 10,000 quota units/day (sufficient for personal use).

## Running Tests

### Backend Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

All 40 tests should pass:
- `test_health.py` — Health check and root endpoints
- `test_models.py` — Database model CRUD and relationships
- `test_channels_api.py` — Channel API endpoint tests (create, list, get, delete, stocks, timeline, drilldown)
- `test_services.py` — YouTube URL parsing, stock mention extraction, ticker validation

### Frontend Type Checking & Lint

```bash
cd frontend

# TypeScript type check
npx tsc --noEmit

# ESLint
npm run lint

# Production build (includes type check)
npm run build
```

### Frontend E2E Tests

```bash
cd frontend

# Install Playwright browsers (first time only)
npx playwright install

# Run E2E tests
npm run test:e2e

# Run with UI (interactive)
npm run test:e2e:ui
```

### Backend Lint

```bash
cd backend
source venv/bin/activate
pip install ruff
ruff check app/ tests/
```

## API Endpoints

### Channels

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/channels` | Submit a new channel for processing |
| `GET` | `/api/channels` | List all channels (paginated, sorted by newest) |
| `GET` | `/api/channels/{id}` | Get channel details |
| `DELETE` | `/api/channels/{id}` | Delete a channel and all related data |
| `POST` | `/api/channels/{id}/process` | Trigger reprocessing |
| `POST` | `/api/channels/{id}/cancel` | Cancel ongoing processing |
| `GET` | `/api/channels/{id}/logs` | Get processing logs (for live progress) |
| `GET` | `/api/channels/{id}/stocks` | Get aggregated stock data with performance metrics |
| `GET` | `/api/channels/{id}/timeline` | Get chronological video timeline with mentions |
| `GET` | `/api/channels/{id}/stocks/{ticker}` | Get stock drill-down (all mentions of a ticker) |
| `POST` | `/api/channels/{id}/refresh-prices` | Refresh current prices for all stocks |
| `POST` | `/api/channels/{id}/backfill-prices` | Backfill missing historical prices |

### Stocks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stocks/{ticker}/price` | Get current stock price (cached 5 min) |

### Example: Create a Channel

```bash
curl -X POST http://localhost:8000/api/channels \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/@YourFinanceChannel", "time_range_months": 12}'
```

Response:
```json
{
  "id": "uuid-here",
  "youtube_channel_id": null,
  "name": "YourFinanceChannel",
  "url": "https://www.youtube.com/@YourFinanceChannel",
  "status": "pending",
  "video_count": 0,
  "processed_video_count": 0,
  "time_range_months": 12,
  "created_at": "2026-02-05T12:00:00"
}
```

## Sentiment Categories

| Sentiment | Description | UI Color |
|-----------|-------------|----------|
| **Buy** | Creator recommends purchasing | Green (#22c55e) |
| **Hold** | Creator recommends maintaining position | Yellow (#eab308) |
| **Sell** | Creator recommends selling | Red (#ef4444) |
| **Mentioned** | Stock discussed without recommendation | Blue (#3b82f6) |

## Database Schema

```
channels (1) ──< (N) videos
channels (1) ──< (N) processing_logs
videos   (1) ──< (N) stock_mentions
stocks   (1) ──< (N) stock_mentions
```

| Table | Key Columns |
|-------|------------|
| `channels` | id, youtube_channel_id, name, url, status, video_count, time_range_months |
| `videos` | id, channel_id (FK), youtube_video_id, title, published_at, transcript_status, analysis_status |
| `stocks` | ticker (PK), name, exchange (NYSE/NASDAQ), last_price |
| `stock_mentions` | id, video_id (FK), ticker (FK), sentiment, price_at_mention, context_snippet |
| `processing_logs` | id, channel_id (FK), log_level, message, created_at |

## Troubleshooting

### MySQL Connection Errors

Verify the container is running:
```bash
docker compose ps
```

If stopped, restart:
```bash
docker compose up -d
```

Check connectivity:
```bash
docker exec stock-track-mysql mysqladmin ping -h localhost
```

### Port Conflicts

The default setup uses:
- **3307** — MySQL (mapped from container's 3306)
- **8000** — Backend API (uvicorn)
- **5173** — Frontend dev server (Vite)

If port 3307 conflicts, change it in both `docker-compose.yml` (`ports`) and `backend/.env` (`DATABASE_URL`).

### Gemini API Errors

- Ensure your API key is valid at [Google AI Studio](https://aistudio.google.com/)
- Some videos may not be accessible (age-restricted, private, etc.)
- Check console output for specific error messages

### Missing Stock Prices

If prices show as null for some stocks:
- Use the **"Refresh Prices"** button on the channel details page
- The backfill runs automatically after processing completes
- Some tickers may be invalid (delisted, non-US, etc.)

### Alembic Migration Errors

If migrations fail, you can reset the database:
```bash
docker compose down -v   # Removes the MySQL volume
docker compose up -d     # Fresh database
cd backend && alembic upgrade head
```

## Limitations

- **US Stocks Only** — Only NYSE and NASDAQ tickers are tracked (ETFs, crypto, non-US excluded)
- **Video Accessibility** — Gemini needs access to the video; some may be restricted
- **API Rate Limits** — Processing is throttled to respect YouTube and Gemini API limits
- **Historical Prices** — Weekend/holiday prices use the nearest prior trading day
- **No Authentication** — Designed for personal/single-user use

## Development

### Adding Database Migrations

```bash
cd backend
source venv/bin/activate
alembic revision --autogenerate -m "description of change"
alembic upgrade head
```

### Code Style

- **Backend**: [ruff](https://docs.astral.sh/ruff/) for Python linting
- **Frontend**: ESLint + TypeScript for JavaScript/TypeScript linting

## License

MIT
