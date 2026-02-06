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

const mockDrilldown = {
  ticker: 'AAPL',
  channel_id: 'test-channel-1',
  mentions: [
    {
      id: 'mention-1',
      video_id: 'video-1',
      ticker: 'AAPL',
      sentiment: 'buy',
      price_at_mention: 185.5,
      context_snippet: 'I think Apple is a great buy here',
      created_at: '2024-01-20T00:00:00Z',
      video: {
        id: 'video-1',
        youtube_video_id: 'abc123',
        title: 'Apple Stock Analysis',
        url: 'https://youtube.com/watch?v=abc123',
        published_at: '2024-01-20',
      },
    },
    {
      id: 'mention-2',
      video_id: 'video-2',
      ticker: 'AAPL',
      sentiment: 'hold',
      price_at_mention: 190.0,
      context_snippet: 'Holding Apple for now',
      created_at: '2024-02-15T00:00:00Z',
      video: {
        id: 'video-2',
        youtube_video_id: 'def456',
        title: 'Market Update',
        url: 'https://youtube.com/watch?v=def456',
        published_at: '2024-02-15',
      },
    },
  ],
};

const mockPrice = {
  ticker: 'AAPL',
  price: 195.5,
  name: 'Apple Inc.',
  change: 2.5,
  change_percent: 1.29,
};

test.describe('Stock Drilldown Page', () => {
  test.beforeEach(async ({ page }) => {
    // Mock channel endpoint
    await page.route('**/api/channels/test-channel-1', async (route) => {
      if (!route.request().url().includes('/stocks/')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockChannel),
        });
      }
    });

    // Mock stock drilldown endpoint
    await page.route('**/api/channels/test-channel-1/stocks/AAPL', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockDrilldown),
      });
    });

    // Mock current price endpoint
    await page.route('**/api/stocks/AAPL/price', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockPrice),
      });
    });
  });

  test('should display stock ticker', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    await expect(page.getByRole('heading', { name: 'AAPL' })).toBeVisible();
  });

  test('should display current price', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    await expect(page.getByText('$195.50')).toBeVisible();
  });

  test('should show all mentions', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    // Should show both video titles
    await expect(page.getByText('Apple Stock Analysis')).toBeVisible();
    await expect(page.getByText('Market Update')).toBeVisible();
  });

  test('should display sentiment legend', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    // Should show sentiment legend (capitalized in the chart legend)
    await expect(page.getByText('Buy', { exact: true })).toBeVisible();
    await expect(page.getByText('Hold', { exact: true })).toBeVisible();
  });

  test('should have link to Yahoo Finance', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    // Should have Yahoo Finance link - link text is "Yahoo Finance →"
    const yahooLink = page.getByRole('link', { name: /yahoo finance/i });
    await expect(yahooLink).toBeVisible();
    await expect(yahooLink).toHaveAttribute('href', 'https://finance.yahoo.com/quote/AAPL');
  });

  test('should have back link to channel', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    // Back link says "← Back to {channel.name}"
    const backLink = page.getByRole('link', { name: /back to test finance channel/i });
    await expect(backLink).toBeVisible();
    await expect(backLink).toHaveAttribute('href', '/channels/test-channel-1');
  });

  test('should show price chart section', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    await expect(page.getByText('Price Chart with Mentions')).toBeVisible();
  });

  test('should show all mentions section', async ({ page }) => {
    await page.goto('/channels/test-channel-1/stocks/AAPL');

    await expect(page.getByRole('heading', { name: 'All Mentions' })).toBeVisible();
  });
});
