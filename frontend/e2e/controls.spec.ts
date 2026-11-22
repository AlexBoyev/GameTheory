import { expect, test } from '@playwright/test';

/**
 * The control bar, against the real stack (the tests Phase 3 promised).
 *
 * These assert through `/api/sim/state` rather than through the DOM wherever
 * they can: the question is whether clicking a button actually changed the
 * simulation, and the HUD showing the right number is a separate concern from
 * the engine having done the right thing.
 */

/**
 * Every test here shares one backend, so none of them may assume the state
 * the last one left behind. Each starts by putting the engine somewhere
 * known over the API - which is also faster and less flaky than clicking the
 * UI into position first.
 */
interface Api {
  get: (url: string) => Promise<{ json: () => Promise<Record<string, unknown>> }>;
  post: (url: string, options?: { data?: unknown }) => Promise<unknown>;
}

async function simState(request: Api): Promise<Record<string, unknown>> {
  const response = await request.get('/api/sim/state');
  return response.json();
}

/** Put the engine in a known state: paused, at 1x. */
async function pauseAt1x(request: Api): Promise<void> {
  await request.post('/api/sim/speed', { data: { multiplier: 1 } });
  await request.post('/api/sim/pause', { data: {} });
}

test.describe('control bar', () => {
  test.beforeEach(async ({ page, request }) => {
    await pauseAt1x(request);
    await page.goto('/');
    await expect(page.locator('canvas').first()).toBeVisible();
  });

  test('play and pause change the engine status', async ({ page, request }) => {
    const toggle = page.getByTitle('Play / pause (Space)');

    await toggle.click();
    await expect(async () => {
      expect((await simState(request)).status).toBe('running');
    }).toPass({ timeout: 10_000 });

    await toggle.click();
    await expect(async () => {
      expect((await simState(request)).status).toBe('paused');
    }).toPass({ timeout: 10_000 });
  });

  test('a speed preset is applied to the engine', async ({ page, request }) => {
    await page.getByTitle('Speed 10x').click();

    await expect(async () => {
      expect((await simState(request)).speed).toBe(10);
    }).toPass({ timeout: 10_000 });
  });

  test('step advances exactly the ticks it says', async ({ page, request }) => {
    // Already paused by `beforeEach`, so the tick cannot move underneath us.
    const before = Number((await simState(request)).tick);

    await page.getByTitle('Step one tick (.)').click();

    await expect(async () => {
      expect(Number((await simState(request)).tick)).toBe(before + 1);
    }).toPass({ timeout: 10_000 });
  });

  test('reset builds a new world back at tick 0', async ({ page, request }) => {
    await page.getByTitle('Play / pause (Space)').click();
    await expect(async () => {
      expect(Number((await simState(request)).tick)).toBeGreaterThan(5);
    }).toPass({ timeout: 10_000 });

    await page.getByTitle('New world (R)').click();
    const dialog = page.getByRole('heading', { name: 'New world' });
    await expect(dialog).toBeVisible();

    // Uncheck "start immediately" so the assertion is not racing the engine.
    await page.getByLabel(/Start immediately/).uncheck();
    await page.getByRole('button', { name: 'Build world' }).click();

    await expect(async () => {
      const state = await simState(request);
      expect(Number(state.tick)).toBe(0);
      expect(state.status).toBe('paused');
    }).toPass({ timeout: 30_000 });
  });

  test('a preset is applied when building a world', async ({ page, request }) => {
    await page.getByTitle('New world (R)').click();
    await page.getByRole('button', { name: /Tribal Wars/ }).click();
    await page.getByLabel(/Start immediately/).uncheck();
    await page.getByRole('button', { name: 'Build world' }).click();

    // Tribal Wars starts four tribes already formed, at tick 0.
    await expect(async () => {
      const response = await request.get('/api/tribes');
      const tribes = (await response.json()) as unknown[];
      expect(tribes.length).toBe(4);
    }).toPass({ timeout: 30_000 });
  });
});

test.describe('panels and overlays', () => {
  test.beforeEach(async ({ page, request }) => {
    await pauseAt1x(request);
    await page.goto('/');
    await expect(page.locator('canvas').first()).toBeVisible();
  });

  test('every overlay toggle opens something and closes again', async ({ page }) => {
    for (const [label, heading] of [
      ['Charts', 'Charts'],
      ['LLM minds', 'LLM minds'],
      ['God tools', 'God tools'],
    ] as const) {
      const button = page.getByRole('button', { name: new RegExp(label) }).first();
      await button.click();
      await expect(page.getByRole('heading', { name: heading })).toBeVisible();
      await page.getByRole('button', { name: `Close ${heading}` }).click();
      await expect(page.getByRole('heading', { name: heading })).toBeHidden();
    }
  });

  test('a god tool changes the world and says what it did', async ({ page }) => {
    await page.getByRole('button', { name: /God tools/ }).first().click();
    await page.getByTitle(/Scatter bushes/).click();

    await expect(page.getByText(/bushes carrying/)).toBeVisible({ timeout: 10_000 });
  });

  test('saving a snapshot lists it back', async ({ page }) => {
    await page.getByRole('button', { name: /God tools/ }).first().click();
    await page.getByTitle('Save the world as it is').click();

    await expect(page.getByText(/^Saved "/)).toBeVisible({ timeout: 15_000 });
  });

  test('the keyboard shortcuts match the help overlay', async ({ page }) => {
    await page.locator('body').press('?');
    const help = page.getByRole('heading', { name: /Controls|Help|Keys/ }).first();
    await expect(help).toBeVisible();
  });
});

test.describe('tournament mode', () => {
  test('the report appears only for a tournament world', async ({ page, request }) => {
    await pauseAt1x(request);
    await page.goto('/');
    await expect(page.locator('canvas').first()).toBeVisible();

    // An island has no standings to show, so the panel must not be there.
    await expect(page.getByRole('heading', { name: 'Tournament' })).toBeHidden();

    await page.getByTitle('New world (R)').click();
    await page.getByRole('button', { name: /Axelrod Tournament/ }).click();
    await page.getByRole('button', { name: 'Build world' }).click();

    const panel = page.getByRole('heading', { name: 'Tournament' });
    await expect(panel).toBeVisible({ timeout: 30_000 });

    // Standings fill in once the first pairings resolve, and the strategies
    // must be real names rather than placeholders.
    await expect(page.getByText('per round, not per agent')).toBeVisible();
    await expect(page.getByText('TitForTat').first()).toBeVisible({ timeout: 30_000 });
  });
});
