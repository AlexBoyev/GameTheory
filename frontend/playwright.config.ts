import { defineConfig, devices } from '@playwright/test';

/**
 * Smoke tests run against the real stack, so start it first:
 *
 *     python driver.py --no-browser
 *     cd frontend && npm run e2e
 *
 * `reuseExistingServer` means Playwright attaches to the Vite the driver
 * already started, which matters because the driver picks the backend port
 * (8000 is taken by Apache on this machine) and passes it to Vite as
 * `VITE_BACKEND_URL`. Starting Vite here instead would proxy to the wrong
 * port and every test would fail for the wrong reason.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
