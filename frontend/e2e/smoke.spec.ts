import { expect, test } from '@playwright/test';

/**
 * Phase 1 smoke test: the page loads, WebGL renders and the socket connects.
 * Phase 3 adds control-bar and camera tests on top of this.
 *
 * Requires the backend on :8000 (Vite proxies /api and /ws to it).
 */
test.describe('shell', () => {
  test('renders the canvas and the status bar', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('canvas')).toBeVisible();
    await expect(page.getByText('Game Theory')).toBeVisible();
  });

  test('connects to the world socket and receives frames', async ({ page }) => {
    await page.goto('/');

    // "live" appears only once the socket is open.
    await expect(page.getByText('live')).toBeVisible({ timeout: 15_000 });

    // The tick counter must move on its own.
    const tick = page.locator('span.font-mono').first();
    const first = await tick.innerText();
    await expect(async () => {
      expect(await tick.innerText()).not.toBe(first);
    }).toPass({ timeout: 10_000 });
  });

  test('the backend is reachable through the proxy', async ({ request }) => {
    const response = await request.get('/api/health');

    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as { status: string; llm: { provider: string } };
    expect(body.status).toBe('ok');
    expect(body.llm.provider).toMatch(/mock|ollama/);
  });
});
