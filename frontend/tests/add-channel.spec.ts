import { test, expect } from '@playwright/test';

test.describe('Add Channel Modal', () => {
  test.beforeEach(async ({ page }) => {
    // Mock empty channel list
    await page.route('**/api/channels', async (route) => {
      if (route.request().method() === 'GET') {
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
      } else if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON();
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'new-channel-id',
            youtube_channel_id: 'UC123',
            name: 'New Channel',
            url: body.url,
            status: 'pending',
            video_count: 0,
            processed_video_count: 0,
            time_range_months: body.time_range_months || 12,
            created_at: new Date().toISOString(),
          }),
        });
      }
    });
  });

  test('should open modal when Add Channel button clicked', async ({ page }) => {
    await page.goto('/');

    // Click Add Channel button
    await page.getByRole('button', { name: /add channel/i }).click();

    // Modal should be visible - check for the modal heading
    await expect(page.getByText('Add YouTube Channel')).toBeVisible();
  });

  test('should have URL input and time range selector', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /add channel/i }).click();

    // Check form elements - use label text or placeholder
    await expect(page.getByPlaceholder(/youtube.com/i)).toBeVisible();
    await expect(page.locator('select#timeRange')).toBeVisible();
  });

  test('should close modal when Cancel clicked', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /add channel/i }).click();

    // Click Cancel
    await page.getByRole('button', { name: /cancel/i }).click();

    // Modal should be hidden
    await expect(page.getByText('Add YouTube Channel')).not.toBeVisible();
  });

  test('should submit valid YouTube URL', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /add channel/i }).click();

    // Fill in URL
    await page.getByPlaceholder(/youtube.com/i).fill('https://www.youtube.com/@TestChannel');

    // Submit - button says "Start Analysis"
    await page.getByRole('button', { name: /start analysis/i }).click();

    // Modal should close after successful submission
    await expect(page.getByText('Add YouTube Channel')).not.toBeVisible({ timeout: 5000 });
  });

  test('should show validation error for invalid URL', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /add channel/i }).click();

    // Fill in invalid URL
    await page.getByPlaceholder(/youtube.com/i).fill('https://google.com');

    // Try to submit
    await page.getByRole('button', { name: /start analysis/i }).click();

    // Should show error message
    await expect(page.getByText(/valid youtube channel url/i)).toBeVisible();
  });
});
