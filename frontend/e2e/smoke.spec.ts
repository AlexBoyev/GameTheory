import { expect, test } from '@playwright/test';

/**
 * The shell: the page loads, WebGL renders and the socket connects.
 *
 * Start the stack first (`python driver.py --no-browser`); see
 * `playwright.config.ts`. Control-bar and panel tests live in
 * `controls.spec.ts`.
 *
 * Note the `.first()` on the canvas: the minimap is a canvas too, so a bare
 * `locator('canvas')` is ambiguous under Playwright's strict mode - which is
 * how adding the minimap broke this test.
 */
test.describe('shell', () => {
  test('renders the canvas and the status bar', async ({ page }) => {
    await page.goto('/?menu=0');

    await expect(page.locator('canvas').first()).toBeVisible();
    // Exact, and with the front screen skipped: its <h1> says the same words
    // as the status bar's <span>, and two matches is a strict-mode failure -
    // the same shape of breakage the minimap caused for `locator('canvas')`.
    await expect(page.getByText('Game Theory', { exact: true })).toBeVisible();
  });

  test('the front screen explains itself and starts the world', async ({ page, request }) => {
    await request.post('/api/sim/pause', { data: {} });
    await page.goto('/');

    const menu = page.getByRole('heading', { name: 'Game Theory', level: 1 });
    await expect(menu).toBeVisible();
    await expect(page.getByText('Controls')).toBeVisible();

    await page.getByRole('button', { name: 'Start' }).click();

    await expect(menu).toBeHidden();
    await expect(async () => {
      const state = (await (await request.get('/api/sim/state')).json()) as { status: string };
      expect(state.status).toBe('running');
    }).toPass({ timeout: 10_000 });
  });

  test('escape brings the menu back and pauses', async ({ page, request }) => {
    await page.goto('/?menu=0');
    await expect(page.locator('canvas').first()).toBeVisible();

    await page.keyboard.press('Escape');

    await expect(page.getByRole('heading', { name: 'Game Theory', level: 1 })).toBeVisible();
    await expect(async () => {
      const state = (await (await request.get('/api/sim/state')).json()) as { status: string };
      expect(state.status).toBe('paused');
    }).toPass({ timeout: 10_000 });
  });

  test('connects to the world socket and receives frames', async ({ page, request }) => {
    // Load first, then start, then confirm it is running before measuring.
    //
    // Starting before the navigation looks tidier and races: the previous
    // spec's page fires `pause` as it closes (Escape opens the menu, which
    // pauses), and that request can land *after* this one's start. The
    // engine is right to honour it; the test was wrong to assume order
    // across pages that share one backend.
    await page.goto('/?menu=0');
    await expect(page.getByText('live')).toBeVisible({ timeout: 15_000 });
    await request.post('/api/sim/start', { data: {} });
    await expect(async () => {
      const state = (await (await request.get('/api/sim/state')).json()) as { status: string };
      expect(state.status).toBe('running');
    }).toPass({ timeout: 10_000 });

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
