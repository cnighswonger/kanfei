import { test, expect } from '@playwright/test';
import { TEST_ADMIN } from './helpers/values';

test.describe('Login page', () => {
  // The fixture DB pre-inserts a valid session so other specs can inject
  // the cookie via injectAuthCookie().  Auth-flow tests need the opposite —
  // an unauthenticated context — so they explicitly clear cookies first.
  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
  });

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

    await page.locator('input[autocomplete="username"]').fill(TEST_ADMIN.username);
    await page.locator('input[autocomplete="current-password"]').fill(TEST_ADMIN.password);
    await page.getByRole('button', { name: 'Sign In' }).click();

    // exact: true — the WeatherLink card renders "WeatherLink settings
    // could not be read" when no station is attached (the fixture's
    // normal state), which otherwise collides with the page heading.
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
