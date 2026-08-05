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
    // "Sign in to continue" only renders once Login's own /api/auth/me
    // probe has resolved (setupRequired === null returns null), so its
    // visibility is the synchronisation point — no explicit response wait
    // is needed or sufficient.  Even so the form can still be re-mounted
    // out from under a fill(), leaving empty fields and Sign In disabled,
    // so the values are asserted and re-filled below rather than typed
    // once and trusted (#272).
    await page.goto('/settings');
    await expect(page.getByText('Sign in to continue')).toBeVisible();

    const user = page.locator('input[autocomplete="username"]');
    const pass = page.locator('input[autocomplete="current-password"]');
    const signIn = page.getByRole('button', { name: 'Sign In' });

    // Re-fill until it sticks.  A single fill() plus assertions is not
    // enough: the assertions can pass and a later re-mount still clears
    // the fields.
    //
    // This does not make the test deterministic — it still fails perhaps
    // a third of the time, and the retry loop only narrows the window.
    // The observed failure is an empty form with Sign In disabled and NO
    // backend error, i.e. a re-mount landing after the loop and before
    // the click.  Cause not yet identified (#272).
    //
    // An earlier version of this comment blamed #275, a StaleDataError
    // race in validate_session().  That was wrong: fixing #275 did not
    // improve the pass rate, and the failing runs show no server-side
    // exception at all.
    await expect(async () => {
      await user.fill(TEST_ADMIN.username);
      await pass.fill(TEST_ADMIN.password);
      await expect(user).toHaveValue(TEST_ADMIN.username, { timeout: 1000 });
      await expect(pass).toHaveValue(TEST_ADMIN.password, { timeout: 1000 });
      await expect(signIn).toBeEnabled({ timeout: 1000 });
    }).toPass({ timeout: 15000 });

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
