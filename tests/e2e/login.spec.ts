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
    // Wait for the auth probe to settle before touching the form.  Login
    // renders no form until /api/setup/status resolves, and the form
    // re-mounts when it does — a fill() issued before that is silently
    // discarded, leaving empty fields and Sign In disabled.  Asserting the
    // filled values is not enough on its own: the re-mount can land after
    // those assertions pass (#272).
    const statusSettled = page.waitForResponse(
      (r) => r.url().includes('/api/setup/status') && r.status() === 200,
    );
    await page.goto('/settings');
    await statusSettled;
    await expect(page.getByText('Sign in to continue')).toBeVisible();

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
