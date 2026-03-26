import { test, expect } from '@playwright/test';

test.describe('History page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/history', { waitUntil: 'networkidle' });
    await expect(page.getByRole('heading', { name: 'History' })).toBeVisible();
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
    const sensorSelect = page.locator('main select').first();
    await sensorSelect.selectOption({ label: 'Outdoor Temperature' });
    await page.getByRole('button', { name: '24 Hours' }).click();
    await expect(page.locator('.highcharts-container').first()).toBeVisible();
  });

  test('chart SVG has rendered paths', async ({ page }) => {
    const sensorSelect = page.locator('main select').first();
    await sensorSelect.selectOption({ label: 'Outdoor Temperature' });
    await page.getByRole('button', { name: '24 Hours' }).click();
    await page.waitForSelector('.highcharts-container svg');
    const paths = page.locator('.highcharts-container svg path');
    const count = await paths.count();
    expect(count).toBeGreaterThan(0);
  });

  test('switching sensor re-fetches data', async ({ page }) => {
    const sensorSelect = page.locator('main select').first();
    await sensorSelect.selectOption({ label: 'Outdoor Temperature' });
    await page.getByRole('button', { name: '24 Hours' }).click();
    await page.waitForLoadState('networkidle');

    await sensorSelect.selectOption({ label: 'Indoor Temperature' });
    await expect(sensorSelect).toHaveValue('temperature_inside');
  });

  test('time range preset buttons are visible', async ({ page }) => {
    await expect(page.getByRole('button', { name: '1 Hour' })).toBeVisible();
    await expect(page.getByRole('button', { name: '24 Hours' })).toBeVisible();
    await expect(page.getByRole('button', { name: '7 Days' })).toBeVisible();
  });
});
