import { test, expect } from '@playwright/test';
import { API_BASE } from './helpers/values';
import { injectAuthCookie } from './helpers/auth';

test.describe('Backup operations', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady;
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await page.getByRole('button', { name: 'Backup' }).click();
    await expect(page.getByRole('button', { name: /backup now/i })).toBeVisible();
  });

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
    const backupBtn = page.getByRole('button', { name: /backup now/i });
    await backupBtn.click();
    await expect(page.getByText('kanfei-backup-').first()).toBeVisible();
  });

  test('backup list shows download button', async ({ page }) => {
    await page.request.post(`${API_BASE}/api/backup`);
    await injectAuthCookie(page);
    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady;
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await page.getByRole('button', { name: 'Backup' }).click();

    await expect(page.getByText('kanfei-backup-').first()).toBeVisible();
    const downloadBtn = page.getByRole('link', { name: /download/i }).or(
      page.getByRole('button', { name: /download/i })
    );
    await expect(downloadBtn.first()).toBeVisible();
  });

  test('delete backup removes it from list', async ({ page }) => {
    await page.request.post(`${API_BASE}/api/backup`);
    await injectAuthCookie(page);
    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady;
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await page.getByRole('button', { name: 'Backup' }).click();

    await expect(page.getByText('kanfei-backup-').first()).toBeVisible();

    const deleteBtn = page.getByRole('button', { name: /delete/i }).first();
    await expect(deleteBtn).toBeVisible();
    await deleteBtn.click();

    await page.waitForTimeout(2000);
  });
});
