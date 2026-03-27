import { test, expect } from '@playwright/test';

test.describe('Telegram Bot settings', () => {
  test.beforeEach(async ({ page }) => {
    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady;
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    // Navigate to Services tab where Telegram settings live
    await page.getByRole('button', { name: 'Services' }).click();
    await expect(page.getByRole('heading', { name: 'Telegram Bot' })).toBeVisible();
  });

  test('Telegram Bot section is visible on Services tab', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Telegram Bot' })).toBeVisible();
  });

  test('enable checkbox toggles Telegram bot', async ({ page }) => {
    const enableCheckbox = page.getByRole('checkbox', { name: 'Enable Telegram bot' });
    await expect(enableCheckbox).toBeVisible();
    // Toggle on
    await enableCheckbox.check();
    await expect(enableCheckbox).toBeChecked();
    // Toggle off
    await enableCheckbox.uncheck();
    await expect(enableCheckbox).not.toBeChecked();
  });

  test('Bot Token and Chat ID fields are present', async ({ page }) => {
    await expect(page.getByText('Bot Token')).toBeVisible();
    await expect(page.getByText('Chat ID')).toBeVisible();
    // Token field is a password input with placeholder "From @BotFather"
    await expect(page.locator('input[placeholder="From @BotFather"]')).toBeVisible();
    // Chat ID field with placeholder
    await expect(page.locator('input[placeholder="Target chat or group ID"]')).toBeVisible();
  });

  test('command checkboxes are present', async ({ page }) => {
    await expect(page.getByText('Commands')).toBeVisible();
    await expect(page.getByRole('checkbox', { name: '/current' })).toBeVisible();
    await expect(page.getByRole('checkbox', { name: '/status' })).toBeVisible();
    await expect(page.getByRole('checkbox', { name: '/help' })).toBeVisible();
  });

  test('notification checkboxes are present', async ({ page }) => {
    await expect(page.getByText('Notifications')).toBeVisible();
    await expect(page.getByRole('checkbox', { name: 'Nowcast updates' })).toBeVisible();
    await expect(page.getByRole('checkbox', { name: 'Alert thresholds' })).toBeVisible();
  });

  test('Send Test Message button is disabled without credentials', async ({ page }) => {
    const sendBtn = page.getByRole('button', { name: /send test message/i });
    await expect(sendBtn).toBeVisible();
    await expect(sendBtn).toBeDisabled();
  });

  test('Send Test Message button enables with token and chat ID', async ({ page }) => {
    // Enable Telegram first
    await page.getByRole('checkbox', { name: 'Enable Telegram bot' }).check();
    // Fill in credentials
    await page.locator('input[placeholder="From @BotFather"]').fill('123456:ABC-DEF');
    await page.locator('input[placeholder="Target chat or group ID"]').fill('987654321');
    // Button should now be enabled
    const sendBtn = page.getByRole('button', { name: /send test message/i });
    await expect(sendBtn).toBeEnabled();
  });
});
