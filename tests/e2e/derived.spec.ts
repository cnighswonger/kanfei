import { test, expect } from '@playwright/test';
import { ANCHOR } from './helpers/values';

test.describe('Derived Conditions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    await expect(page.getByText('Derived Conditions')).toBeVisible();
  });

  test('panel header shows "Derived Conditions"', async ({ page }) => {
    await expect(page.getByText('Derived Conditions')).toBeVisible();
  });

  async function assertDerived(page: import('@playwright/test').Page, label: string, expected: string) {
    await expect(page.getByText(label)).toBeVisible();
    const container = page.locator(`text=${label}`).locator('..').locator(`text=${expected}`);
    await expect(container).toBeVisible();
  }

  test('Feels Like shows 77.0 F', async ({ page }) => {
    await assertDerived(page, 'Feels Like', ANCHOR.feelsLike);
  });

  test('Heat Index shows 77.0 F', async ({ page }) => {
    await assertDerived(page, 'Heat Index', ANCHOR.heatIndex);
  });

  test('Dew Point shows 62.6 F', async ({ page }) => {
    await assertDerived(page, 'Dew Point', ANCHOR.dewPoint);
  });

  test('Wind Chill shows 75.2 F', async ({ page }) => {
    await assertDerived(page, 'Wind Chill', ANCHOR.windChill);
  });

  test('Theta-E shows 330.0 K', async ({ page }) => {
    await assertDerived(page, 'Theta-E', ANCHOR.thetaE);
  });
});
