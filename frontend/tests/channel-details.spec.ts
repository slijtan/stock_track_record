import { test, expect } from '@playwright/test';

const mockChannel = {
  id: 'test-channel-1',
  youtube_channel_id: 'UC123',
  name: 'Test Finance Channel',
  url: 'https://youtube.com/@testchannel',
  status: 'completed',
  video_count: 5,
  processed_video_count: 5,
  time_range_months: 12,
  created_at: '2024-01-15T10:00:00Z',
};

const mockStocks = {
  channel_id: 'test-channel-1',
  stocks: [
    {
      ticker: 'AAPL',
      name: 'Apple Inc.',
      first_mention_date: '2024-01-20',
      first_mention_video_id: 'video-1',
      first_mention_video_title: 'Apple Analysis',
      price_at_first_mention: 185.5,
      current_price: 195.0,
      price_change_percent: 5.12,
      total_mentions: 3,
      buy_count: 2,
      hold_count: 1,
      sell_count: 0,
      mentioned_count: 0,
    },
    {
      ticker: 'TSLA',
      name: 'Tesla Inc.',
      first_mention_date: '2024-02-10',
      first_mention_video_id: 'video-2',
      first_mention_video_title: 'Tesla Review',
      price_at_first_mention: 200.0,
      current_price: 180.0,
      price_change_percent: -10.0,
      total_mentions: 2,
      buy_count: 0,
      hold_count: 0,
      sell_count: 1,
      mentioned_count: 1,
    },
  ],
};

const mockTimeline = {
  timeline: [
    {
      video: {
        id: 'video-1',
        youtube_video_id: 'abc123',
        title: 'Apple Analysis Video',
        url: 'https://youtube.com/watch?v=abc123',
        published_at: '2024-01-20',
        analysis_status: 'completed',
      },
      mentions: [
        {
          id: 'mention-1',
          ticker: 'AAPL',
          sentiment: 'buy',
          price_at_mention: 185.5,
          context_snippet: 'Apple is looking great',
        },
      ],
    },
  ],
};

test.describe('Channel Details Page', () => {
  test.beforeEach(async ({ page }) => {
    // Mock channel details
    await page.route('**/api/channels/test-channel-1', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockChannel),
      });
    });

    // Mock stocks endpoint
    await page.route('**/api/channels/test-channel-1/stocks', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockStocks),
      });
    });

    // Mock timeline endpoint
    await page.route('**/api/channels/test-channel-1/timeline', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockTimeline),
      });
    });

    // Mock logs endpoint
    await page.route('**/api/channels/test-channel-1/logs*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ logs: [] }),
      });
    });

    // Mock stock price endpoints
    await page.route('**/api/stocks/*/price', async (route) => {
      const url = route.request().url();
      const ticker = url.match(/\/stocks\/([^/]+)\/price/)?.[1] ?? '';
      const prices: Record<string, number> = { AAPL: 195.0, TSLA: 180.0 };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ticker, price: prices[ticker] ?? 100.0 }),
      });
    });

    // Mock backfill-prices endpoint
    await page.route('**/api/channels/test-channel-1/backfill-prices', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ updated: 0 }),
      });
    });
  });

  test('should display channel name', async ({ page }) => {
    await page.goto('/channels/test-channel-1');

    await expect(page.getByRole('heading', { name: 'Test Finance Channel' })).toBeVisible();
  });

  test('should show Stocks and Timeline tabs', async ({ page }) => {
    await page.goto('/channels/test-channel-1');

    await expect(page.getByRole('button', { name: 'Stocks' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Timeline' })).toBeVisible();
  });

  test('should display stocks in Stocks tab by default', async ({ page }) => {
    await page.goto('/channels/test-channel-1');

    // Stocks tab is active by default, should show stock tickers
    await expect(page.getByText('AAPL')).toBeVisible();
    await expect(page.getByText('TSLA')).toBeVisible();
  });

  test('should show positive price change in green', async ({ page }) => {
    await page.goto('/channels/test-channel-1');

    // AAPL has positive change, should show +5.12%
    await expect(page.getByText('+5.12%')).toBeVisible();
  });

  test('should show negative price change in red', async ({ page }) => {
    await page.goto('/channels/test-channel-1');

    // TSLA has negative change
    await expect(page.getByText('-10.00%')).toBeVisible();
  });

  test('should display timeline when Timeline tab clicked', async ({ page }) => {
    await page.goto('/channels/test-channel-1');

    // Wait for the price fetch modal to appear, then dismiss it via Escape
    const modal = page.getByText('Fetching Prices');
    await modal.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    await page.keyboard.press('Escape');
    await modal.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});

    // Click Timeline tab
    await page.getByRole('button', { name: 'Timeline' }).click();

    // Should show video title
    await expect(page.getByText('Apple Analysis Video')).toBeVisible();
  });

  test('should have back link to channel list', async ({ page }) => {
    await page.goto('/channels/test-channel-1');

    // Check back link exists
    const backLink = page.getByRole('link', { name: /back to channels/i });
    await expect(backLink).toBeVisible();
    await expect(backLink).toHaveAttribute('href', '/');
  });
});
