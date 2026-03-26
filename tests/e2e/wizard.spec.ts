import { test, expect } from '@playwright/test';
import { API_BASE, DRIVER_COUNT } from './helpers/values';

/** Helper: set setup_complete and ensure the page sees the change. */
async function enterWizard(request: import('@playwright/test').APIRequestContext, page: import('@playwright/test').Page) {
  // Set config
  await request.put(`${API_BASE}/api/config`, {
    data: [{ key: 'setup_complete', value: 'false' }],
  });

  // Navigate and intercept the setup status API to guarantee the wizard appears.
  // This avoids any race between the config write and the frontend's fetch.
  await page.route('**/api/setup/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ setup_complete: false }),
    });
  });

  await page.goto('/');
  await page.waitForSelector('text=Weather Station Setup', { timeout: 15_000 });
  // Clear the route intercept for subsequent requests
  await page.unroute('**/api/setup/status');
}

async function restoreSetup(request: import('@playwright/test').APIRequestContext) {
  await request.put(`${API_BASE}/api/config`, {
    data: [{ key: 'setup_complete', value: 'true' }],
  });
}

test.describe('Setup Wizard', () => {
  test.afterEach(async ({ request }) => {
    await restoreSetup(request);
  });

  test('wizard appears when setup_complete is false', async ({ request, page }) => {
    await enterWizard(request, page);
    await expect(page.getByText('Weather Station Setup')).toBeVisible();
    await expect(page.getByText('Step 1 of 3: Station')).toBeVisible();
  });

  test('driver dropdown in step 1 has 7 options', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = page.locator('select').first();
    await page.waitForFunction(
      () => document.querySelector('select')!.options.length >= 7,
      { timeout: 15_000 },
    );
    await expect(driverSelect.locator('option')).toHaveCount(DRIVER_COUNT);
  });

  test('selecting ecowitt shows Gateway IP field', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = page.locator('select').first();
    await page.waitForFunction(
      () => document.querySelector('select')!.options.length >= 7,
      { timeout: 15_000 },
    );
    await driverSelect.selectOption('ecowitt');
    await expect(page.getByText('Gateway IP Address')).toBeVisible();
  });

  test('can navigate through all 3 steps', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = page.locator('select').first();
    await page.waitForFunction(
      () => document.querySelector('select')!.options.length >= 7,
      { timeout: 15_000 },
    );
    await driverSelect.selectOption('ecowitt');
    await page.locator('input[type="text"]').first().fill('192.168.1.100');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 2 of 3: Location')).toBeVisible();

    await page.locator('input[type="number"]').first().fill('35.78');
    await page.locator('input[type="number"]').nth(1).fill('-78.64');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 3 of 3: Preferences')).toBeVisible();
  });

  test('Back button navigates to previous steps', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = page.locator('select').first();
    await page.waitForFunction(
      () => document.querySelector('select')!.options.length >= 7,
      { timeout: 15_000 },
    );
    await driverSelect.selectOption('tempest');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 2 of 3')).toBeVisible();

    await page.locator('input[type="number"]').first().fill('35.78');
    await page.locator('input[type="number"]').nth(1).fill('-78.64');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 3 of 3')).toBeVisible();

    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page.getByText('Step 2 of 3')).toBeVisible();

    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page.getByText('Step 1 of 3')).toBeVisible();
  });

  test('Finish Setup completes wizard and shows dashboard', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = page.locator('select').first();
    await page.waitForFunction(
      () => document.querySelector('select')!.options.length >= 7,
      { timeout: 15_000 },
    );
    await driverSelect.selectOption('ecowitt');
    await page.locator('input[type="text"]').first().fill('192.168.1.100');
    await page.getByRole('button', { name: 'Next' }).click();

    await page.locator('input[type="number"]').first().fill('35.78');
    await page.locator('input[type="number"]').nth(1).fill('-78.64');
    await page.getByRole('button', { name: 'Next' }).click();

    await page.getByRole('button', { name: /finish/i }).click();
    await expect(page.getByText('Weather Station Setup')).toBeHidden({ timeout: 10_000 });
    await expect(page.locator('.dashboard-grid')).toBeVisible({ timeout: 10_000 });
  });
});
