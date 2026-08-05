import { test, expect } from '@playwright/test';
import { TEST_ADMIN } from './helpers/values';

test.describe('Login page', () => {
  test('settings redirects to login when not authenticated', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByText('Sign in to continue')).toBeVisible();
  });

  test('login form has username and password fields', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByText('Username')).toBeVisible();
    await expect(page.getByText('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('Sign In button disabled without credentials', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeDisabled();
  });

  test('successful login redirects to settings', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByText('Sign in to continue')).toBeVisible();

    // Fill, then assert the values landed before clicking.  The form
    // re-mounts as the auth check resolves, which silently clears an
    // early fill() and leaves Sign In disabled — the failure was a login
    // page with empty fields, not a redirect that went wrong (#272).
    const user = page.locator('input[autocomplete="username"]');
    const pass = page.locator('input[autocomplete="current-password"]');
    await user.fill(TEST_ADMIN.username);
    await pass.fill(TEST_ADMIN.password);
    await expect(user).toHaveValue(TEST_ADMIN.username);
    await expect(pass).toHaveValue(TEST_ADMIN.password);

    const signIn = page.getByRole('button', { name: 'Sign In' });
    await expect(signIn).toBeEnabled();
    await signIn.click();

    // exact: true, or this matches a second heading whose text merely
    // contains "settings" — the WeatherLink card renders
    // "WeatherLink settings could not be read" when no station is
    // attached, which is the normal state for the fixture (#272).
    await expect(
      page.getByRole('heading', { name: 'Settings', exact: true }),
    ).toBeVisible();
  });

  test('invalid credentials show error', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[autocomplete="username"]').fill('admin');
    await page.locator('input[autocomplete="current-password"]').fill('wrongpassword');
    await page.getByRole('button', { name: 'Sign In' }).click();

    await expect(page.getByText(/invalid username|login failed/i)).toBeVisible();
  });
});
