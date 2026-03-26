import { test, expect } from '@playwright/test';
import { ANCHOR, DAILY_EXTREMES } from './helpers/values';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for the REST /api/current fetch to populate the dashboard
    await page.waitForFunction(() => {
      const el = document.querySelector('.dashboard-grid');
      return el && el.children.length > 0;
    }, { timeout: 15_000 });
  });

  test('page loads with dashboard grid', async ({ page }) => {
    await expect(page.locator('.dashboard-grid')).toBeVisible();
  });

  test('outside temperature shows 75.2', async ({ page }) => {
    // TemperatureGauge renders "75.2°F" in the digital readout
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
    // Speed value (rendered as integer)
    await expect(grid.getByText(ANCHOR.windSpeed, { exact: true }).first()).toBeVisible();
    // Cardinal + direction in bottom readout
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

    // Rain rate display
    await expect(grid.getByText(ANCHOR.rainRate).first()).toBeVisible();
    // Rain totals — in full mode these are in separate "Today", "Yesterday", "Year" sections;
    // in compact mode they're combined as "Day X / Yest Y / Yr Z"
    await expect(grid.getByText(ANCHOR.rainYearly).first()).toBeVisible();
    await expect(grid.getByText(ANCHOR.rainYesterday).first()).toBeVisible();
  });

  test('daily extremes show high and low on outside temp', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');
    // TemperatureGauge shows high/low as either SVG whisker labels "H 81°" / "L 68°"
    // or compact card "H 81° / L 68°"
    await expect(grid.getByText(new RegExp(`H ${DAILY_EXTREMES.outsideTempHigh}°`)).first()).toBeVisible();
    await expect(grid.getByText(new RegExp(`L ${DAILY_EXTREMES.outsideTempLow}°`)).first()).toBeVisible();
  });

  test('solar-UV gauge does not render when data is null', async ({ page }) => {
    // TileRenderer returns null for solar-uv when both values are null.
    // The FlipTile wrapper may still exist with a hidden back face heading,
    // but the SolarUVGauge component itself should not render.
    // The gauge shows "W/m²" as a unit label — verify it's absent.
    const grid = page.locator('.dashboard-grid');
    await expect(grid.locator('text=W/m²')).toHaveCount(0);
  });
});
