# Product Requirements Document: Stock Track Record

> See [tdd.md](./tdd.md) for technical architecture, API specifications, and implementation details.

---

## 1. Overview & Goals

### 1.1 Purpose
Stock Track Record is a web application that analyzes YouTube channels focused on stock recommendations. It extracts stock picks from video transcripts using AI, tracks those picks over time, and displays historical performance data to help users evaluate the track record of financial content creators.

### 1.2 Goals
- Enable users to submit YouTube channels for analysis
- Automatically extract stock recommendations from video transcripts
- Track stock price performance from the date of each recommendation
- Provide clear visualizations of pick accuracy over time
- Create a mobile-friendly, installable PWA experience

### 1.3 Target Users
- Individual investors evaluating YouTube financial content creators
- Personal use (no authentication required)

---

## 2. User Stories

### Channel Submission
- As a user, I want to submit a YouTube channel URL so that the system can analyze their stock picks
- As a user, I want to specify a time range (default 1 year) to limit which videos are analyzed
- As a user, I want to see live progress/logs while my channel is being processed

### Channel Discovery
- As a user, I want to see a list of all parsed channels ordered by most recently added
- As a user, I want to click on a channel to see detailed analysis

### Channel Analysis
- As a user, I want to see a timeline of all stock mentions with links to the original videos
- As a user, I want to see a summary table of all stocks mentioned with performance metrics
- As a user, I want to see the sentiment (buy/hold/sell/mentioned) for each stock pick

### Stock Deep Dive
- As a user, I want to drill down into a specific stock to see all mentions over time
- As a user, I want to see a price chart with recommendation points overlaid
- As a user, I want to hover on data points to see video details

---

## 3. Functional Requirements

### 3.1 Stock Sentiment Categories
Each stock mention is classified into one of four categories:

| Category | Description |
|----------|-------------|
| Buy | Creator recommends purchasing the stock |
| Hold | Creator recommends maintaining current position |
| Sell | Creator recommends selling the stock |
| Mentioned | Stock discussed without explicit recommendation |

### 3.2 Supported Markets
- US stocks only (NYSE and NASDAQ exchanges)
- ETFs, crypto, and non-US stocks are excluded

### 3.3 Channel Processing
- Videos are processed in the background after submission
- Users see live progress updates during processing
- Time range options: 6, 12, 24, or 36 months (default: 12)

### 3.4 Price Data
- Stock prices refresh on page load (not cached long-term)
- Historical price captured at the date of each video

### 3.5 Error Handling (User-facing)
- If a video has no transcript, it is skipped (shown in progress log)
- If processing fails after retries, the video is skipped with a warning
- Users can see which videos were skipped and why

### 3.6 Authentication
- None required (personal use application)

---

## 4. UI Wireframes

### 4.1 Home / Channel List Page

```
┌──────────────────────────────────────────────────────────┐
│  Stock Track Record                      [+ Add Channel] │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 🎬 Finance Channel                    Added: Jan 15 │  │
│  │    42 videos analyzed • 156 stock picks            │  │
│  │    Status: ✅ Completed                             │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 🎬 Stock Tips Daily                   Added: Jan 14 │  │
│  │    Processing... 28/65 videos                      │  │
│  │    Status: 🔄 Processing                            │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 4.2 Add Channel Modal

```
┌──────────────────────────────────────────────────────────┐
│  Add YouTube Channel                              [X]    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Channel URL:                                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │ https://www.youtube.com/@FinanceChannel            │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Time Range:                                             │
│  ┌─────────────┐                                         │
│  │ 12 months ▼ │  (6, 12, 24, 36 months)                │
│  └─────────────┘                                         │
│                                                          │
│                              [Cancel]  [Start Analysis]  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 4.3 Channel Details Page

```
┌──────────────────────────────────────────────────────────┐
│  ← Back    Finance Channel                               │
├──────────────────────────────────────────────────────────┤
│  [Timeline] [Stocks]                                     │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  STOCKS VIEW:                                            │
│  ┌────────┬────────────┬────────┬────────┬─────────────┐ │
│  │ Ticker │ First Pick │ Then   │ Now    │ Change  │ B │ │
│  ├────────┼────────────┼────────┼────────┼─────────┼───┤ │
│  │ AAPL   │ Jan 15     │ $185   │ $195   │ +5.25%  │ 3 │ │
│  │ NVDA   │ Jan 20     │ $450   │ $520   │ +15.5%  │ 5 │ │
│  │ TSLA   │ Feb 1      │ $220   │ $180   │ -18.2%  │ 1 │ │
│  └────────┴────────────┴────────┴────────┴─────────┴───┘ │
│                                                          │
│  TIMELINE VIEW:                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Jan 20, 2024                                       │  │
│  │ "Top 5 AI Stocks to Buy Now"                       │  │
│  │ 🟢 BUY: NVDA, AMD  🔵 MENTIONED: GOOGL            │  │
│  ├────────────────────────────────────────────────────┤  │
│  │ Jan 15, 2024                                       │  │
│  │ "My Portfolio Update"                              │  │
│  │ 🟢 BUY: AAPL  🟡 HOLD: MSFT  🔴 SELL: META        │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 4.4 Stock Drill-down Page

```
┌──────────────────────────────────────────────────────────┐
│  ← Back    NVDA - NVIDIA Corporation     [Yahoo Finance] │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Price Chart with Mentions                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │     $520 ┤                              ●          │  │
│  │          │                           ╱             │  │
│  │     $480 ┤               ●        ╱                │  │
│  │          │            ╱  ╲     ╱                   │  │
│  │     $450 ┤    ●    ╱      ╲╱                       │  │
│  │          │     ╲╱                                  │  │
│  │     $420 ┤                                         │  │
│  │          └────────────────────────────────────────  │  │
│  │           Jan    Feb    Mar    Apr    May          │  │
│  └────────────────────────────────────────────────────┘  │
│  ● = BUY  ○ = HOLD  ✕ = SELL  ◇ = MENTIONED             │
│                                                          │
│  Hover tooltip:                                          │
│  ┌──────────────────────────────┐                        │
│  │ Jan 20, 2024 - $450.25       │                        │
│  │ 🟢 BUY                        │                        │
│  │ "Top 5 AI Stocks to Buy Now" │                        │
│  │ [Watch Video]                │                        │
│  └──────────────────────────────┘                        │
│                                                          │
│  All Mentions:                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 🟢 Jan 20 - BUY @ $450 - "Top 5 AI Stocks..."     │  │
│  │ 🟢 Feb 15 - BUY @ $480 - "Why NVDA Will..."       │  │
│  │ 🟡 Mar 10 - HOLD @ $475 - "Portfolio Review"       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 4.5 Processing Progress View

```
┌──────────────────────────────────────────────────────────┐
│  Processing: Finance Channel                             │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Progress: ████████████░░░░░░░░  28/65 videos (43%)     │
│                                                          │
│  Live Log:                                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │ [10:32:15] Fetching video list...                  │  │
│  │ [10:32:18] Found 65 videos in date range           │  │
│  │ [10:32:20] Processing: "My Top Picks for 2024"     │  │
│  │ [10:32:25] ✓ Found 5 stock mentions                │  │
│  │ [10:32:26] Processing: "Why I Sold TSLA"           │  │
│  │ [10:32:30] ✓ Found 2 stock mentions                │  │
│  │ [10:32:31] Processing: "Market Analysis Jan"       │  │
│  │ [10:32:35] ⚠ No transcript available, skipping     │  │
│  │ ...                                                │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Future Considerations

### 5.1 Potential Enhancements
- **Authentication:** Add user accounts for multi-user deployment
- **Notifications:** Alert when new videos are processed
- **Comparison:** Compare track records across multiple channels
- **Export:** Export data as CSV/PDF reports
- **Watchlist:** Track specific stocks across all channels
- **Social sharing:** Share channel track records publicly

---

## Appendix: Sentiment Color Coding

| Sentiment | Color | Icon |
|-----------|-------|------|
| Buy | Green (#22c55e) | 🟢 |
| Hold | Yellow (#eab308) | 🟡 |
| Sell | Red (#ef4444) | 🔴 |
| Mentioned | Blue (#3b82f6) | 🔵 |
