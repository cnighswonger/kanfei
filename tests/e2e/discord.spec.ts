import { test, expect } from '@playwright/test';

test.describe('Discord Bot settings', () => {
  test.beforeEach(async ({ page }) => {
    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady;
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    // Navigate to Services tab where Discord settings live
    await page.getByRole('button', { name: 'Services' }).click();
    await expect(page.getByRole('heading', { name: 'Discord Bot' })).toBeVisible();
  });

  test('Discord Bot section is visible on Services tab', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Discord Bot' })).toBeVisible();
  });

  test('enable checkbox toggles Discord bot', async ({ page }) => {
    const enableCheckbox = page.getByRole('checkbox', { name: 'Enable Discord bot' });
    await expect(enableCheckbox).toBeVisible();
    // Toggle on
    await enableCheckbox.check();
    await expect(enableCheckbox).toBeChecked();
    // Toggle off
    await enableCheckbox.uncheck();
    await expect(enableCheckbox).not.toBeChecked();
  });

  test('Bot Token, Guild ID, and Channel ID fields are present', async ({ page }) => {
    await expect(page.locator('input[placeholder="From Discord Developer Portal"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Target server ID"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Notification channel ID"]')).toBeVisible();
  });

  test('command checkboxes are present', async ({ page }) => {
    const card = page.getByRole('heading', { name: 'Discord Bot' }).locator('..');
    await expect(card.getByRole('checkbox', { name: '/current' })).toBeVisible();
    await expect(card.getByRole('checkbox', { name: '/status' })).toBeVisible();
    await expect(card.getByRole('checkbox', { name: '/help' })).toBeVisible();
  });

  test('notification checkboxes are present', async ({ page }) => {
    const card = page.getByRole('heading', { name: 'Discord Bot' }).locator('..');
    await expect(card.getByRole('checkbox', { name: 'Nowcast updates' })).toBeVisible();
    await expect(card.getByRole('checkbox', { name: 'Alert thresholds' })).toBeVisible();
  });

  test('Send Test Message button is disabled without credentials', async ({ page }) => {
    const card = page.getByRole('heading', { name: 'Discord Bot' }).locator('..');
    const sendBtn = card.getByRole('button', { name: /send test message/i });
    await expect(sendBtn).toBeVisible();
    await expect(sendBtn).toBeDisabled();
  });

  test('Send Test Message button enables with token and channel ID', async ({ page }) => {
    // Enable Discord first
    await page.getByRole('checkbox', { name: 'Enable Discord bot' }).check();
    // Fill in credentials
    await page.locator('input[placeholder="From Discord Developer Portal"]').fill('MTIz.abc.xyz');
    await page.locator('input[placeholder="Notification channel ID"]').fill('123456789');
    // Button should now be enabled
    const card = page.getByRole('heading', { name: 'Discord Bot' }).locator('..');
    const sendBtn = card.getByRole('button', { name: /send test message/i });
    await expect(sendBtn).toBeEnabled();
  });
});
