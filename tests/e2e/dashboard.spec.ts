import { test, expect } from '@playwright/test';
import { ANCHOR, DAILY_EXTREMES } from './helpers/values';
import { injectAuthCookie } from './helpers/auth';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    const currentReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/current') && resp.status() === 200,
    );
    await page.goto('/');
    await currentReady;
    // Wait for React to fully render gauges with data
    await expect(page.getByText(`${ANCHOR.outsideTemp}°F`).first()).toBeVisible();
  });

  test('page loads with dashboard grid', async ({ page }) => {
    await expect(page.locator('.dashboard-grid')).toBeVisible();
  });

  test('outside temperature shows 75.2', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(`${ANCHOR.outsideTemp}°F`).first()).toBeVisible();
  });

  test('inside temperature shows 70.0', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(`${ANCHOR.insideTemp}°F`).first()).toBeVisible();
  });

  test('barometer shows 30.02 inHg', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(ANCHOR.barometer).first()).toBeVisible();
    await expect(grid.getByText(ANCHOR.barometerUnit).first()).toBeVisible();
  });

  test('barometer shows rising trend arrow', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(ANCHOR.trendArrowUp).first()).toBeVisible();
  });

  test('wind compass shows 8 mph SW', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(ANCHOR.windSpeed, { exact: true }).first()).toBeVisible();
    await expect(grid.getByText(`${ANCHOR.windCardinal} ${ANCHOR.windDirection}°`).first()).toBeVisible();
  });

  test('outside humidity shows 62%', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(`${ANCHOR.outsideHumidity}%`).first()).toBeVisible();
  });

  test('inside humidity shows 45%', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(`${ANCHOR.insideHumidity}%`).first()).toBeVisible();
  });

  test('rain gauge shows correct values', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(ANCHOR.rainRate).first()).toBeVisible();
    await expect(grid.getByText(ANCHOR.rainYearly).first()).toBeVisible();
    await expect(grid.getByText(ANCHOR.rainYesterday).first()).toBeVisible();
  });

  test('daily extremes show high and low on outside temp', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText(new RegExp(`H ${DAILY_EXTREMES.outsideTempHigh}°`)).first()).toBeVisible();
    await expect(grid.getByText(new RegExp(`L ${DAILY_EXTREMES.outsideTempLow}°`)).first()).toBeVisible();
  });

  test('solar-UV gauge does not render when data is null', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    await expect(grid.locator('text=W/m²')).toHaveCount(0);
  });
});

test.describe('Wind tile display toggle', () => {
  // Auth cookie so writeUIPref's PUT /api/config succeeds and layout
  // preferences round-trip through the backend rather than only sitting
  // in localStorage.
  async function resetLayout(page: import('@playwright/test').Page) {
    // Reset backend-persisted layout via a page-context fetch — the
    // browser attaches the injected knf_session cookie automatically,
    // whereas page.request runs in its own APIRequestContext where the
    // cookie handling is unreliable.
    await page.evaluate(async () => {
      await fetch('/api/config', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([{ key: 'ui_dashboard_layout', value: '' }]),
      });
      try { localStorage.removeItem('ui_dashboard_layout'); } catch {}
    });
  }

  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
    // First navigation is needed so page.evaluate has a document to run in.
    const currentReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/current') && resp.status() === 200,
    );
    await page.goto('/');
    await currentReady;
    await expect(page.getByText(`${ANCHOR.outsideTemp}°F`).first()).toBeVisible();

    await resetLayout(page);

    // Reload so the reset takes effect — the initial load already synced
    // the pre-reset value from the backend into React state.
    await page.reload();
    await expect(page.getByText(`${ANCHOR.outsideTemp}°F`).first()).toBeVisible();
  });

  test.afterAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await injectAuthCookie(page);
    await page.goto('/');
    await resetLayout(page);
    await ctx.close();
  });

  async function enterEditMode(page: import('@playwright/test').Page) {
    await page.getByRole('button', { name: 'Edit dashboard layout' }).click();
    // The Compass/Rose toggle only renders in edit mode.
    await expect(page.getByRole('button', { name: 'Switch to Rose' })).toBeVisible();
  }

  async function exitEditMode(page: import('@playwright/test').Page) {
    await page.getByRole('button', { name: 'Done' }).click();
    await expect(page.getByRole('button', { name: /^Switch to (Rose|Compass)$/ })).toHaveCount(0);
  }

  test('toggle button is edit-mode only', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Switch to Rose' })).toHaveCount(0);
    await enterEditMode(page);
    await expect(page.getByRole('button', { name: 'Switch to Rose' })).toBeVisible();
  });

  test('toggling flips front face from compass to rose and back', async ({ page }) => {
    await enterEditMode(page);

    // Compass shown initially — its cardinal + direction text is a
    // stand-in for "the compass face is mounted".
    await expect(
      page.getByText(`${ANCHOR.windCardinal} ${ANCHOR.windDirection}°`).first(),
    ).toBeVisible();

    await page.getByRole('button', { name: 'Switch to Rose' }).click();

    // WindRose renders a Highcharts polar chart; assert the container
    // mounts rather than what the chart drew (per #128 out-of-scope).
    await expect(page.locator('.highcharts-container').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Switch to Compass' })).toBeVisible();

    await page.getByRole('button', { name: 'Switch to Compass' }).click();
    await expect(
      page.getByText(`${ANCHOR.windCardinal} ${ANCHOR.windDirection}°`).first(),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Switch to Rose' })).toBeVisible();
  });

  test('rose selection persists across reload via backend', async ({ page }) => {
    await enterEditMode(page);

    const layoutWrite = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/config') &&
        resp.request().method() === 'PUT' &&
        resp.status() === 200,
    );
    await page.getByRole('button', { name: 'Switch to Rose' }).click();
    await layoutWrite;

    await exitEditMode(page);

    const currentReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/current') && resp.status() === 200,
    );
    await page.reload();
    await currentReady;

    // Rose survives reload — assert the mount, not the drawing.
    await expect(page.locator('.highcharts-container').first()).toBeVisible();

    // Poll on the persisted layout — .highcharts-container mounting only
    // proves React state is rose (populated by the async syncUIPrefs).
    // The localStorage reconcile happens in the same syncUIPrefs pass but
    // isn't necessarily observable in the same microtask.
    await expect.poll(() =>
      page.evaluate(() => {
        const raw = localStorage.getItem('ui_dashboard_layout');
        if (!raw) return null;
        try {
          const layout = JSON.parse(raw);
          return layout.tiles.find((t: { tileId: string }) => t.tileId === 'wind')?.windDisplay ?? null;
        } catch {
          return null;
        }
      }),
    ).toBe('rose');
  });

  test('compass state is stored as absent windDisplay, not "compass"', async ({ page }) => {
    // Round-trip: rose -> compass, then inspect what actually got saved.
    await enterEditMode(page);
    await page.getByRole('button', { name: 'Switch to Rose' }).click();

    const backToCompass = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/config') &&
        resp.request().method() === 'PUT' &&
        resp.status() === 200,
    );
    await page.getByRole('button', { name: 'Switch to Compass' }).click();
    await backToCompass;

    const stored = await page.evaluate(() =>
      localStorage.getItem('ui_dashboard_layout'),
    );
    expect(stored).not.toBeNull();
    const layout = JSON.parse(stored!);
    const wind = layout.tiles.find((t: { tileId: string }) => t.tileId === 'wind');
    expect(wind).toBeDefined();
    // Compass is stored as absence — asserting === "compass" would be wrong.
    expect(wind).not.toHaveProperty('windDisplay');
  });
});
