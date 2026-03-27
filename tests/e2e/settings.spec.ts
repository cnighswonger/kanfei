import { test, expect } from '@playwright/test';
import { DRIVER_COUNT } from './helpers/values';

test.describe('Settings page', () => {
  test.beforeEach(async ({ page }) => {
    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady;
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  });

  /** The driver type dropdown is in the Station tab under "Driver Type" label. */
  function driverSelect(page: import('@playwright/test').Page) {
    return page.locator('main select').first();
  }

  test('page loads with Station tab active', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Station' }).first()).toBeVisible();
    await expect(driverSelect(page)).toBeVisible();
  });

  test('driver dropdown has 7 options with legacy selected', async ({ page }) => {
    const select = driverSelect(page);
    await expect(select).toBeVisible();
    const options = select.locator('option');
    await expect(options).toHaveCount(DRIVER_COUNT);
    await expect(select).toHaveValue('legacy');
  });

  test('serial config visible for legacy driver', async ({ page }) => {
    const main = page.locator('main');
    await expect(main.getByText('Serial Port').first()).toBeVisible();
    await expect(main.getByText('Baud Rate').first()).toBeVisible();
  });

  test('switching to ecowitt shows Gateway IP field', async ({ page }) => {
    await driverSelect(page).selectOption('ecowitt');
    await expect(page.getByText('Gateway IP', { exact: false })).toBeVisible();
    await expect(page.locator('main').getByText('Serial Port')).toHaveCount(0);
  });

  test('switching to tempest shows Hub Serial Number', async ({ page }) => {
    await driverSelect(page).selectOption('tempest');
    await expect(page.getByText('Hub Serial Number', { exact: false })).toBeVisible();
  });

  test('switching to ambient shows Listen Port', async ({ page }) => {
    await driverSelect(page).selectOption('ambient');
    await expect(page.getByText('Listen Port')).toBeVisible();
  });

  test('switching to weatherlink_ip shows Device IP and TCP Port', async ({ page }) => {
    await driverSelect(page).selectOption('weatherlink_ip');
    await expect(page.getByText('Device IP Address')).toBeVisible();
    await expect(page.getByText('TCP Port')).toBeVisible();
  });

  test('WeatherLink section hidden for ecowitt', async ({ page }) => {
    await driverSelect(page).selectOption('ecowitt');
    await expect(page.getByText('Archive Period', { exact: false })).toHaveCount(0);
  });

  test('Backup tab is accessible', async ({ page }) => {
    await page.getByRole('button', { name: 'Backup' }).click();
    await expect(page.getByText('Backup', { exact: false }).first()).toBeVisible();
  });
});
