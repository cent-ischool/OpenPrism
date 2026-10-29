import { defineConfig } from '@playwright/test';

// Browser tests. They drive a *running* stack (docker compose up -d --wait, then `npm run dev`, or the nginx image):
//   npx playwright install chromium && sudo npx playwright install-deps chromium   # once
//   npm run e2e                                                                      # from the repo root: npm --workspace apps/frontend run e2e
// E2E_BASE_URL selects the target (default: the Vite dev server). Each test creates its own account and project.
export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  workers: 1, // the tests share one backend and compile queue
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    viewport: { width: 1500, height: 900 },
    trace: 'retain-on-failure'
  }
});
