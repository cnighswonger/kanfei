/**
 * Shared authentication helper for E2E tests.
 * Injects the pre-baked session cookie from the test DB so that
 * auth-protected pages load without going through the login flow.
 */
import { TEST_ADMIN } from './values';
import type { Page } from '@playwright/test';

/**
 * Inject the test session cookie into the browser context.
 * Call this before navigating to auth-protected pages (e.g. /settings).
 * The cookie is pre-baked in build-test-db.py with a 30-day expiry.
 */
export async function injectAuthCookie(page: Page) {
  await page.context().addCookies([{
    name: 'knf_session',
    value: TEST_ADMIN.sessionToken,
    domain: 'localhost',
    path: '/',
    httpOnly: true,
    secure: false,
    sameSite: 'Lax',
  }]);
}
