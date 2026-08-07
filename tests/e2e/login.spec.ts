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

  test('a 401 issued before login does not eject the user after it', async ({ page }) => {
    // Regression for the class of "pre-login request whose 401 arrives after
    // login" — the frontend guard in `client.ts` snapshots auth state at
    // send time.  Hold `/api/mute/status` (a request AppShell fires on mount)
    // and release its 401 AFTER the user is on /settings.  Without the
    // request-time snapshot, the guard would read the post-login flag,
    // dispatch `kanfei:auth-required`, and bounce the user back to /login.
    //
    // times:1 is load-bearing.  useMuteStatus polls every 30 s; a handler
    // without the limit would also intercept a request issued AFTER login,
    // whose 401 is a legitimate ejection signal, not this bug.
    //
    // The paired backend/harness fix that makes this test's setup reliable
    // (fresh uvicorn per invocation, so the SQLAlchemy pool doesn't hold
    // stale file handles across DB rebuilds) is in this same PR — see #286.
    let release: (() => void) | undefined;
    const held = new Promise<void>((resolve) => (release = resolve));
    await page.route(
      '**/api/mute/status',
      async (route) => {
        await held;
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Authentication required' }),
        });
      },
      { times: 1 },
    );

    await page.goto('/settings');
    await expect(page.getByText('Sign in to continue')).toBeVisible();
    await page.locator('input[autocomplete="username"]').fill(TEST_ADMIN.username);
    await page.locator('input[autocomplete="current-password"]').fill(TEST_ADMIN.password);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();

    release!();

    await expect(page.getByText('Sign in to continue')).toHaveCount(0);
    expect(new URL(page.url()).pathname).toBe('/settings');
  });
});
