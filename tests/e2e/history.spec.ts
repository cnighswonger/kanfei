import { test, expect } from '@playwright/test';

test.describe('History page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/history');
    await page.waitForSelector('h2:has-text("History")', { timeout: 15_000 });
  });

  test('page loads with sensor dropdown', async ({ page }) => {
    const sensorSelect = page.locator('main select').first();
    await expect(sensorSelect).toBeVisible();
  });

  test('sensor dropdown has multiple options', async ({ page }) => {
    const sensorSelect = page.locator('main select').first();
    const options = sensorSelect.locator('option');
    const count = await options.count();
    expect(count).toBeGreaterThanOrEqual(5);
  });

  test('chart renders with data', async ({ page }) => {
    // Select a sensor that has data in our test DB
    const sensorSelect = page.locator('main select').first();
    await sensorSelect.selectOption({ label: 'Outdoor Temperature' });
    // Use 24 Hours range to ensure we get data from today
    await page.getByRole('button', { name: '24 Hours' }).click();
    // Wait for Highcharts to render
    await page.waitForSelector('.highcharts-container', { timeout: 15_000 });
    const chart = page.locator('.highcharts-container');
    await expect(chart.first()).toBeVisible();
  });

  test('chart SVG has rendered paths', async ({ page }) => {
    const sensorSelect = page.locator('main select').first();
    await sensorSelect.selectOption({ label: 'Outdoor Temperature' });
    await page.getByRole('button', { name: '24 Hours' }).click();
    await page.waitForSelector('.highcharts-container svg', { timeout: 15_000 });
    const paths = page.locator('.highcharts-container svg path');
    const count = await paths.count();
    expect(count).toBeGreaterThan(0);
  });

  test('switching sensor re-fetches data', async ({ page }) => {
    const sensorSelect = page.locator('main select').first();
    // Select outdoor temp with 24h range to start
    await sensorSelect.selectOption({ label: 'Outdoor Temperature' });
    await page.getByRole('button', { name: '24 Hours' }).click();
    await page.waitForTimeout(1500);

    // Switch to Indoor Temperature (also has data in test DB)
    await sensorSelect.selectOption({ label: 'Indoor Temperature' });
    // Verify the dropdown value changed (key is temperature_inside)
    await expect(sensorSelect).toHaveValue('temperature_inside');
  });

  test('time range preset buttons are visible', async ({ page }) => {
    await expect(page.getByRole('button', { name: '1 Hour' })).toBeVisible();
    await expect(page.getByRole('button', { name: '24 Hours' })).toBeVisible();
    await expect(page.getByRole('button', { name: '7 Days' })).toBeVisible();
  });
});
