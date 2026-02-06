import { test, expect } from '@playwright/test';

test.describe('Home Page', () => {
  test('should display the app header', async ({ page }) => {
    // Mock empty channels
    await page.route('**/api/channels*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          per_page: 20,
        }),
      });
    });

    await page.goto('/');

    // Check header is visible - it says "Channels"
    await expect(page.locator('h1')).toContainText('Channels');
  });

  test('should show Add Channel button', async ({ page }) => {
    await page.route('**/api/channels*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          per_page: 20,
        }),
      });
    });

    await page.goto('/');

    // Check Add Channel button exists - text is "+ Add Channel"
    const addButton = page.getByRole('button', { name: /add channel/i });
    await expect(addButton).toBeVisible();
  });

  test('should show empty state when no channels', async ({ page }) => {
    // Mock the API to return empty channels
    await page.route('**/api/channels*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          per_page: 20,
        }),
      });
    });

    await page.goto('/');

    // Should show empty state message
    await expect(page.getByText(/no channels yet/i)).toBeVisible();
  });

  test('should display channel list when channels exist', async ({ page }) => {
    // Mock the API to return channels
    await page.route('**/api/channels*', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [
              {
                id: 'test-channel-1',
                youtube_channel_id: 'UC123',
                name: 'Test Finance Channel',
                url: 'https://youtube.com/@testchannel',
                status: 'completed',
                video_count: 10,
                processed_video_count: 10,
                time_range_months: 12,
                created_at: '2024-01-15T10:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            per_page: 20,
          }),
        });
      }
    });

    await page.goto('/');

    // Should show the channel
    await expect(page.getByText('Test Finance Channel')).toBeVisible();
    await expect(page.getByText('Completed')).toBeVisible();
  });
});
