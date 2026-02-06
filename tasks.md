# Stock Track Record - Implementation Tasks

> This document breaks down the project into executable tasks. Each task should be completed and validated before moving to the next.

---

## Phase 1: Project Foundation

### Task 1.1: Backend Project Setup ✅
**Goal:** Initialize Python/FastAPI backend with project structure

**Subtasks:**
- [x] Create `backend/` directory structure
- [x] Set up Python virtual environment
- [x] Create `requirements.txt` with dependencies (fastapi, uvicorn, sqlalchemy, pymysql, pydantic, python-dotenv)
- [x] Create FastAPI app scaffold (`app/main.py`)
- [x] Set up configuration management (`app/config.py`)
- [x] Create health check endpoint (`GET /health`)
- [x] Set up pytest and create first test

**Validation:**
- `uvicorn app.main:app --reload` starts successfully
- `GET /health` returns `{"status": "ok"}`
- `pytest` passes

---

### Task 1.2: Database Setup ✅
**Goal:** Set up MySQL database with SQLAlchemy models and migrations

**Subtasks:**
- [x] Add SQLAlchemy and alembic to requirements
- [x] Create database connection module (`app/db/database.py`)
- [x] Create SQLAlchemy models (`app/db/models.py`):
  - Channel
  - Video
  - Stock
  - StockMention
  - ProcessingLog
- [x] Set up Alembic for migrations
- [x] Create initial migration with all tables
- [x] Create database seeding script for development

**Validation:**
- Docker MySQL container starts successfully
- Migrations run without errors
- All tables created with correct schema
- Unit tests for model relationships pass

---

### Task 1.3: Frontend Project Setup ✅
**Goal:** Initialize React + Vite frontend as PWA

**Subtasks:**
- [x] Create `frontend/` directory with Vite + React + TypeScript
- [x] Configure PWA with vite-plugin-pwa
- [x] Set up Tailwind CSS
- [x] Create basic app structure (routes, layouts)
- [x] Set up API client with fetch/axios
- [x] Configure environment variables
- [x] Add Chart.js dependency

**Validation:**
- `npm run dev` starts development server
- App loads in browser without errors
- PWA manifest is generated
- Tailwind styles apply correctly

---

## Phase 2: Core Backend API

### Task 2.1: Channel API Endpoints ✅
**Goal:** Implement channel CRUD operations

**Subtasks:**
- [x] Create Pydantic schemas for Channel (`app/schemas/channel.py`)
- [x] Create Channel repository/service (`app/services/channel_service.py`)
- [x] Implement endpoints:
  - `POST /api/channels` - Create channel (validate YouTube URL)
  - `GET /api/channels` - List channels (paginated, sorted by created_at desc)
  - `GET /api/channels/{id}` - Get channel details
  - `DELETE /api/channels/{id}` - Delete channel
- [x] Add request validation and error handling
- [x] Write unit tests for each endpoint
- [x] Write integration tests with test database

**Validation:**
- All endpoints return correct status codes
- Pagination works correctly
- Invalid YouTube URLs are rejected
- Delete cascades to related records
- All tests pass with >90% coverage

---

### Task 2.2: Channel Stocks & Timeline Endpoints ✅
**Goal:** Implement stock aggregation and timeline endpoints

**Subtasks:**
- [x] Create Pydantic schemas for Stock and StockMention
- [x] Implement `GET /api/channels/{id}/stocks`:
  - Aggregate stock mentions per channel
  - Calculate first mention, price change, sentiment counts
  - Include Yahoo Finance URL
- [x] Implement `GET /api/channels/{id}/timeline`:
  - Return chronological list of videos with their stock mentions
  - Include video title, date, link
- [x] Implement `GET /api/channels/{id}/logs`:
  - Return processing logs for live progress
  - Support polling/long-polling
- [x] Write unit and integration tests

**Validation:**
- Stock aggregation calculates correctly
- Timeline is sorted by date descending
- Logs endpoint returns real-time updates
- All tests pass

---

### Task 2.3: Stock Drill-down & Price Endpoints ✅
**Goal:** Implement stock detail and price refresh endpoints

**Subtasks:**
- [x] Implement `GET /api/channels/{id}/stocks/{ticker}`:
  - Return all mentions of a stock within a channel
  - Include video details for each mention
  - Calculate price at mention vs current
- [x] Implement `GET /api/stocks/{ticker}/price`:
  - Fetch current price from Yahoo Finance
  - Cache for 5 minutes
- [x] Create price caching mechanism
- [x] Write unit and integration tests

**Validation:**
- Drill-down returns all mentions with correct data
- Price endpoint returns current price
- Caching works (second request within 5 min doesn't hit Yahoo)
- All tests pass

---

## Phase 3: External Integrations

### Task 3.1: YouTube Integration ✅
**Goal:** Fetch channel metadata, video lists, and transcripts

**Subtasks:**
- [x] Create YouTube service (`app/services/youtube_service.py`)
- [x] Implement channel metadata fetching:
  - Extract channel ID from various URL formats
  - Fetch channel name, thumbnail
- [x] Implement video list fetching:
  - List videos within date range
  - Extract video ID, title, published date
- [x] Implement transcript fetching:
  - Use youtube-transcript-api
  - Handle missing transcripts gracefully
- [x] Add rate limiting and polite delays
- [x] Write unit tests with mocked responses
- [x] Write integration test with real YouTube channel (optional, manual)

**Validation:**
- Various YouTube URL formats are parsed correctly
- Video list respects date range filter
- Transcripts are fetched successfully
- Missing transcripts don't crash the service
- All unit tests pass

---

### Task 3.2: OpenAI Integration ✅
**Goal:** Extract stock tickers and sentiment from transcripts

**Subtasks:**
- [x] Create OpenAI service (`app/services/openai_service.py`)
- [x] Implement transcript analysis:
  - System prompt for stock extraction
  - Parse JSON response
  - Handle rate limits with backoff
- [x] Implement ticker validation:
  - Verify ticker exists (NYSE/NASDAQ)
  - Filter out invalid tickers
- [x] Add retry logic (3 attempts with exponential backoff)
- [x] Write unit tests with mocked OpenAI responses
- [x] Write integration test with real API (optional, manual)

**Validation:**
- Stock mentions are extracted correctly from sample transcripts
- Invalid tickers are filtered out
- Rate limiting doesn't cause failures
- Retry logic works on transient errors
- All unit tests pass

---

### Task 3.3: Yahoo Finance Integration ✅
**Goal:** Fetch historical and current stock prices

**Subtasks:**
- [x] Create Yahoo Finance service (`app/services/stock_price_service.py`)
- [x] Implement historical price fetching:
  - Get closing price for a specific date
  - Handle weekends/holidays (use nearest trading day)
- [x] Implement current price fetching:
  - Get real-time price
  - Implement 5-minute cache
- [x] Handle invalid tickers gracefully
- [x] Write unit tests with mocked responses

**Validation:**
- Historical prices are fetched for valid dates
- Weekend dates return Friday's price
- Current prices are cached correctly
- Invalid tickers return appropriate error
- All unit tests pass

---

## Phase 4: Background Processing

### Task 4.1: Channel Processing Worker ✅
**Goal:** Implement background job to process channels

**Subtasks:**
- [x] Create processing service (`app/services/processing_service.py`)
- [x] Implement channel processing pipeline:
  1. Update status to 'processing'
  2. Fetch channel metadata
  3. List videos in date range
  4. For each video:
     - Log progress
     - Fetch transcript
     - Extract stock mentions via OpenAI
     - Fetch historical prices
     - Save to database
  5. Update status to 'completed'
- [x] Implement logging to processing_logs table
- [x] Add error handling and retry logic
- [x] Write unit tests for pipeline steps
- [x] Write integration test for full pipeline (with mocks)

**Validation:**
- Pipeline processes channel end-to-end
- Progress logs are created correctly
- Failed videos are skipped with warning
- Status transitions correctly
- All tests pass

---

### Task 4.2: Job Queue Integration (Local) ✅
**Goal:** Implement async job processing for local development

**Subtasks:**
- [x] Create simple background task runner for local dev
- [x] Modify `POST /api/channels` to queue processing job
- [x] Implement job status tracking
- [x] Add endpoint to check job status
- [x] Write tests for async behavior

**Validation:**
- Channel creation returns immediately
- Processing happens in background
- Status updates are visible via API
- Multiple channels can be queued

---

### Task 4.3: AWS SQS + Lambda Integration
**Goal:** Set up production-ready background processing

**Subtasks:**
- [ ] Create SQS queue configuration
- [ ] Create Lambda function for worker
- [ ] Package worker code for Lambda deployment
- [ ] Implement SQS message handling
- [ ] Add CloudWatch logging
- [ ] Create deployment scripts/IaC (SAM or CDK)
- [ ] Write integration tests

**Validation:**
- Messages are sent to SQS on channel creation
- Lambda processes messages correctly
- Failed messages go to DLQ
- Logs appear in CloudWatch
- End-to-end flow works in AWS

---

## Phase 5: Frontend Implementation

### Task 5.1: Channel List Page ✅
**Goal:** Implement home page with list of channels

**Subtasks:**
- [x] Create ChannelList component
- [x] Create ChannelCard component (shows name, stats, status)
- [x] Implement API integration to fetch channels
- [x] Add loading and empty states
- [x] Implement pull-to-refresh (mobile)
- [x] Add "Add Channel" button
- [x] Style with Tailwind (mobile-first)
- [x] Write component tests

**Validation:**
- Channels display correctly
- Status indicators show correct state
- Empty state shows when no channels
- Loading state shows while fetching
- Responsive on mobile and desktop

---

### Task 5.2: Add Channel Modal ✅
**Goal:** Implement channel submission form

**Subtasks:**
- [x] Create AddChannelModal component
- [x] Create form with URL input and time range dropdown
- [x] Implement URL validation (client-side)
- [x] Implement form submission to API
- [x] Add loading state during submission
- [x] Handle success (close modal, refresh list)
- [x] Handle errors (show error message)
- [x] Write component tests

**Validation:**
- Modal opens and closes correctly
- Invalid URLs show validation error
- Successful submission closes modal
- New channel appears in list
- Error messages display correctly

---

### Task 5.3: Processing Progress View ✅
**Goal:** Implement live progress display during channel processing

**Subtasks:**
- [x] Create ProcessingProgress component
- [x] Implement progress bar (videos processed / total)
- [x] Implement live log feed
- [x] Set up polling for log updates
- [x] Auto-scroll log to bottom
- [x] Show completion state
- [x] Style log entries by level (info, warning, error)
- [x] Write component tests

**Validation:**
- Progress bar updates in real-time
- Logs appear as processing happens
- Different log levels have different styles
- Auto-scroll works correctly
- Completion is clearly indicated

---

### Task 5.4: Channel Details Page - Timeline View ✅
**Goal:** Implement timeline of stock mentions

**Subtasks:**
- [x] Create ChannelDetails page component
- [x] Create tab navigation (Timeline / Stocks)
- [x] Create TimelineView component
- [x] Create TimelineItem component (video with mentions)
- [x] Implement API integration
- [x] Add links to YouTube videos
- [x] Style sentiment badges
- [x] Write component tests

**Validation:**
- Timeline shows all videos with mentions
- Videos are sorted by date descending
- Sentiment badges show correct colors
- Video links open YouTube
- Tab navigation works

---

### Task 5.5: Channel Details Page - Stocks View ✅
**Goal:** Implement stock summary table

**Subtasks:**
- [x] Create StocksView component
- [x] Create StocksTable component
- [x] Display columns: Ticker, First Pick, Price Then, Price Now, Change %, Sentiment counts
- [x] Implement sorting by columns
- [x] Add links to stock drill-down page
- [x] Add links to Yahoo Finance
- [x] Color-code price changes (green/red)
- [x] Write component tests

**Validation:**
- All stocks display with correct data
- Sorting works on all columns
- Price changes show correct colors
- Links work correctly
- Table is responsive on mobile

---

### Task 5.6: Stock Drill-down Page ✅
**Goal:** Implement stock detail view with chart

**Subtasks:**
- [x] Create StockDrilldown page component
- [x] Create PriceChart component with Chart.js:
  - Price line over time
  - Mention points overlaid (different markers for sentiment)
  - Tooltips on hover
- [x] Create MentionsList component
- [x] Implement API integration
- [x] Add Yahoo Finance link
- [x] Add back navigation
- [x] Write component tests

**Validation:**
- Chart displays price history correctly
- Mention points appear at correct positions
- Different sentiments have different markers
- Tooltips show video info
- Mentions list shows all entries

---

### Task 5.7: PWA Features ✅
**Goal:** Complete PWA setup for mobile installation

**Subtasks:**
- [x] Configure service worker for offline support
- [x] Create app icons (all sizes)
- [x] Configure manifest.json (name, colors, display)
- [x] Add install prompt handling
- [x] Test offline functionality
- [x] Test installation on iOS and Android

**Validation:**
- App can be installed on mobile devices
- App works offline (shows cached data)
- Icons display correctly
- Splash screen appears on launch

---

## Phase 6: Integration & Polish

### Task 6.1: End-to-End Testing ✅
**Goal:** Verify complete user flows work correctly

**Subtasks:**
- [x] Set up Playwright or Cypress for E2E tests
- [x] Write test: Submit channel → View progress → See results
- [x] Write test: Browse channels → View details → Drill into stock
- [x] Write test: Error handling (invalid URL, failed processing)
- [ ] Set up CI pipeline to run E2E tests (deferred for AWS deployment phase)

**Validation:**
- All E2E tests pass
- Tests run in CI pipeline
- Coverage of main user flows

---

### Task 6.2: Error Handling & Edge Cases ✅
**Goal:** Handle all error scenarios gracefully

**Subtasks:**
- [x] Add global error boundary in React
- [x] Handle network errors with retry UI
- [x] Handle 404s (channel not found, stock not found)
- [x] Handle rate limiting from external APIs
- [x] Add user-friendly error messages
- [x] Log errors for debugging

**Validation:**
- No unhandled exceptions crash the app
- Users see helpful error messages
- Retry options are available where appropriate

---

### Task 6.3: Performance Optimization ✅
**Goal:** Ensure app performs well

**Subtasks:**
- [x] Add database indexes (verify existing)
- [x] Implement API response caching where appropriate (stock price 5-min cache)
- [x] Optimize frontend bundle size (code splitting)
- [x] Add lazy loading for routes
- [x] Optimize chart rendering for large datasets
- [ ] Test with large channel (100+ videos) - requires real API keys

**Validation:**
- Page load time < 3 seconds
- API responses < 500ms
- Chart renders smoothly
- No memory leaks

---

## Phase 7: Deployment

### Task 7.1: AWS Infrastructure Setup
**Goal:** Set up production AWS environment

**Subtasks:**
- [ ] Create Aurora Serverless v2 cluster
- [ ] Create S3 bucket for frontend
- [ ] Create CloudFront distribution
- [ ] Create Lambda functions (API + Worker)
- [ ] Create SQS queue
- [ ] Create API Gateway
- [ ] Set up Secrets Manager for credentials
- [ ] Configure VPC and security groups

**Validation:**
- All AWS resources created successfully
- Network connectivity works
- Secrets are accessible from Lambda

---

### Task 7.2: CI/CD Pipeline
**Goal:** Automate build and deployment

**Subtasks:**
- [ ] Create GitHub Actions workflow
- [ ] Build and test backend on PR
- [ ] Build and test frontend on PR
- [ ] Deploy backend to Lambda on merge to main
- [ ] Deploy frontend to S3/CloudFront on merge to main
- [ ] Run database migrations on deploy
- [ ] Add deployment notifications

**Validation:**
- PRs trigger build and test
- Merges to main trigger deployment
- Rollback is possible

---

### Task 7.3: Production Deployment & Monitoring
**Goal:** Deploy to production and set up monitoring

**Subtasks:**
- [ ] Deploy all components to production
- [ ] Run smoke tests in production
- [ ] Set up CloudWatch alarms (errors, latency)
- [ ] Set up cost monitoring
- [ ] Document runbooks for common issues
- [ ] Create backup strategy for database

**Validation:**
- App is accessible at production URL
- Monitoring alerts work
- Costs are within expected range
- Backup/restore works

---

## Task Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1.1 - 1.3 | Project foundation (backend, database, frontend setup) |
| 2 | 2.1 - 2.3 | Core backend API endpoints |
| 3 | 3.1 - 3.3 | External integrations (YouTube, OpenAI, Yahoo Finance) |
| 4 | 4.1 - 4.3 | Background processing (worker, queues) |
| 5 | 5.1 - 5.7 | Frontend implementation |
| 6 | 6.1 - 6.3 | Integration, testing, and polish |
| 7 | 7.1 - 7.3 | AWS deployment and monitoring |

**Total Tasks:** 22

---

## Execution Notes

1. **Dependencies:** Complete tasks in order within each phase. Phases 1-4 should be completed before Phase 5.

2. **Testing:** Each task includes testing requirements. Do not mark a task complete until tests pass.

3. **Validation:** Each task has validation criteria. Verify all criteria before moving on.

4. **Commits:** Make atomic commits for each subtask. Use conventional commit messages.

5. **Documentation:** Update README.md as features are completed.
