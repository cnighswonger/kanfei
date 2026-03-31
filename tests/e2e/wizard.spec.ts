import { test, expect } from '@playwright/test';
import { API_BASE, DRIVER_COUNT } from './helpers/values';

/** Intercept setup status to force the wizard to appear. */
async function enterWizard(request: import('@playwright/test').APIRequestContext, page: import('@playwright/test').Page) {
  await request.put(`${API_BASE}/api/config`, {
    data: [{ key: 'setup_complete', value: 'false' }],
  });

  await page.route('**/api/setup/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ setup_complete: false }),
    });
  });

  await page.goto('/');
  await expect(page.getByText('Weather Station Setup')).toBeVisible();
  await page.unroute('**/api/setup/status');
}

/** Wait for the driver catalog to populate the dropdown. */
async function waitForDrivers(page: import('@playwright/test').Page) {
  const driverSelect = page.locator('select').first();
  await expect(driverSelect).toBeVisible();
  await page.waitForFunction(
    () => document.querySelector('select')!.options.length >= 7,
  );
  return driverSelect;
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
    await expect(page.getByText('Step 1 of 4: Station')).toBeVisible();
  });

  test('driver dropdown in step 1 has 7 options', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = await waitForDrivers(page);
    await expect(driverSelect.locator('option')).toHaveCount(DRIVER_COUNT);
  });

  test('selecting ecowitt shows Gateway IP field', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = await waitForDrivers(page);
    await driverSelect.selectOption('ecowitt');
    await expect(page.getByText('Gateway IP Address')).toBeVisible();
  });

  test('can navigate through all 4 steps', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = await waitForDrivers(page);
    await driverSelect.selectOption('ecowitt');
    await page.locator('input[type="text"]').first().fill('192.168.1.100');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 2 of 4: Location')).toBeVisible();

    await page.locator('input[type="number"]').first().fill('35.78');
    await page.locator('input[type="number"]').nth(1).fill('-78.64');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 3 of 4: Preferences')).toBeVisible();

    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 4 of 4: Account')).toBeVisible();
  });

  test('Account step requires valid credentials', async ({ request, page }) => {
    await enterWizard(request, page);
    // Navigate to step 4
    const driverSelect = await waitForDrivers(page);
    await driverSelect.selectOption('ecowitt');
    await page.locator('input[type="text"]').first().fill('192.168.1.100');
    await page.getByRole('button', { name: 'Next' }).click();
    await page.locator('input[type="number"]').first().fill('35.78');
    await page.locator('input[type="number"]').nth(1).fill('-78.64');
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 4 of 4: Account')).toBeVisible();

    // Admin Account heading and fields
    await expect(page.getByRole('heading', { name: 'Admin Account' })).toBeVisible();
    await expect(page.locator('input[autocomplete="username"]')).toBeVisible();
    await expect(page.locator('input[autocomplete="new-password"]').first()).toBeVisible();

    // Username pre-filled with "admin"
    await expect(page.locator('input[autocomplete="username"]')).toHaveValue('admin');

    // Password hint text visible
    await expect(page.getByText('At least 8 characters')).toBeVisible();
    // Confirm Password field visible
    await expect(page.getByText('Confirm Password')).toBeVisible();
  });

  test('Back button navigates to previous steps', async ({ request, page }) => {
    await enterWizard(request, page);
    const driverSelect = await waitForDrivers(page);
    await driverSelect.selectOption('tempest');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 2 of 4')).toBeVisible();

    await page.locator('input[type="number"]').first().fill('35.78');
    await page.locator('input[type="number"]').nth(1).fill('-78.64');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('Step 3 of 4')).toBeVisible();

    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page.getByText('Step 2 of 4')).toBeVisible();

    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page.getByText('Step 1 of 4')).toBeVisible();
  });
});
