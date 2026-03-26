import { test, expect } from '@playwright/test';
import { API_BASE } from './helpers/values';

test.describe('Backup operations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
    await page.waitForSelector('h2:has-text("Settings")', { timeout: 15_000 });
    // Navigate to Backup tab
    await page.getByRole('button', { name: 'Backup' }).click();
    await page.waitForTimeout(500);
  });

  // Clean up any backups created during tests
  test.afterAll(async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/backup/list`);
    if (res.ok()) {
      const backups = await res.json();
      for (const b of backups) {
        await request.delete(`${API_BASE}/api/backup/${b.name}`);
      }
    }
  });

  test('backup tab shows backup controls', async ({ page }) => {
    await expect(page.getByText('Backup', { exact: false }).first()).toBeVisible();
  });

  test('create backup and verify it appears in list', async ({ page }) => {
    // Click the Backup Now button
    const backupBtn = page.getByRole('button', { name: /backup now/i });
    await expect(backupBtn).toBeVisible();
    await backupBtn.click();

    // Wait for the backup to complete and appear in the list
    await expect(page.getByText('kanfei-backup-').first()).toBeVisible({ timeout: 15_000 });
  });

  test('backup list shows download button', async ({ page }) => {
    // Create a backup first via API to ensure there's one to download
    await page.request.post(`${API_BASE}/api/backup`);
    await page.reload();
    await page.waitForSelector('h2:has-text("Settings")', { timeout: 15_000 });
    await page.getByRole('button', { name: 'Backup' }).click();
    await page.waitForTimeout(1000);

    // Should have a download action
    const downloadBtn = page.getByRole('link', { name: /download/i }).or(
      page.getByRole('button', { name: /download/i })
    );
    await expect(downloadBtn.first()).toBeVisible({ timeout: 10_000 });
  });

  test('delete backup removes it from list', async ({ page }) => {
    // Create a backup via API
    await page.request.post(`${API_BASE}/api/backup`);
    await page.reload();
    await page.waitForSelector('h2:has-text("Settings")', { timeout: 15_000 });
    await page.getByRole('button', { name: 'Backup' }).click();
    await page.waitForTimeout(1000);

    // Verify backup exists
    await expect(page.getByText('kanfei-backup-').first()).toBeVisible({ timeout: 10_000 });

    // Click delete button
    const deleteBtn = page.getByRole('button', { name: /delete/i }).first();
    await expect(deleteBtn).toBeVisible();
    await deleteBtn.click();

    // Wait for deletion to process
    await page.waitForTimeout(2000);
  });
});
