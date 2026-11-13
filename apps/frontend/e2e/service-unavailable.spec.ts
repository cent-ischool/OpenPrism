import { expect, test, type Page } from '@playwright/test';

// The sign-in page checks /api/status before offering the form (#189). Outages are simulated at the network.
const status = (postgres: string, redis = 'up') => ({
  ok: false, version: 'x', services: { postgres, redis, s3: 'up', workers: {} }, checkedAt: '2026-11-13T00:00:00Z'
});
const form = (page: Page) => page.getByRole('textbox', { name: 'Password' });
const unavailable = (page: Page) => page.getByRole('heading', { name: 'Service unavailable at this time.' });

test('the API not answering shows the message instead of the form, and the form comes back with it', async ({ page }) => {
  let down = true;
  await page.route('**/api/status', (route) => down
    ? route.fulfill({ status: 502, contentType: 'text/html', body: '<html>502 Bad Gateway</html>' })
    : route.continue());
  await page.goto('/login');
  await expect(unavailable(page)).toBeVisible();
  await expect(form(page)).toHaveCount(0);
  await page.screenshot({ path: 'test-results/service-unavailable.png' });

  down = false;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(form(page)).toBeVisible();
  await expect(unavailable(page)).toHaveCount(0);
});

test('a database outage blocks signing in; the page checks again by itself', async ({ page }) => {
  await page.clock.install();
  let body = status('down');
  await page.route('**/api/status', (route) => route.fulfill({ status: 503, json: body }));
  await page.goto('/login');
  await expect(unavailable(page)).toBeVisible();

  body = { ...status('up'), ok: false };   // S3 or a worker down would not matter: only postgres and redis
  body.services.s3 = 'down';
  await page.clock.fastForward(16_000);
  await expect(form(page)).toBeVisible();
});

test('a healthy service shows the form', async ({ page }) => {
  await page.goto('/login');
  await expect(form(page)).toBeVisible();
  await expect(unavailable(page)).toHaveCount(0);
});
