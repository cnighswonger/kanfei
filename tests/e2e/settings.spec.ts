import { test, expect } from '@playwright/test';
import { DRIVER_COUNT } from './helpers/values';
import { injectAuthCookie } from './helpers/auth';

test.describe('Settings page', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady;
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  });

  function driverSelect(page: import('@playwright/test').Page) {
    return page.locator('main select').first();
  }

  test('page loads with Station tab active', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Station' }).first()).toBeVisible();
    await expect(driverSelect(page)).toBeVisible();
  });

  test('driver dropdown has 7 options with legacy selected', async ({ page }) => {
    const select = driverSelect(page);
    await expect(select).toBeVisible();
    const options = select.locator('option');
    await expect(options).toHaveCount(DRIVER_COUNT);
    await expect(select).toHaveValue('legacy');
  });

  test('serial config visible for legacy driver', async ({ page }) => {
    const main = page.locator('main');
    await expect(main.getByText('Serial Port').first()).toBeVisible();
    await expect(main.getByText('Baud Rate').first()).toBeVisible();
  });

  test('switching to ecowitt shows Gateway IP field', async ({ page }) => {
    await driverSelect(page).selectOption('ecowitt');
    await expect(page.getByText('Gateway IP', { exact: false })).toBeVisible();
    await expect(page.locator('main').getByText('Serial Port')).toHaveCount(0);
  });

  test('switching to tempest shows Hub Serial Number', async ({ page }) => {
    await driverSelect(page).selectOption('tempest');
    await expect(page.getByText('Hub Serial Number', { exact: false })).toBeVisible();
  });

  test('switching to ambient shows Listen Port', async ({ page }) => {
    await driverSelect(page).selectOption('ambient');
    await expect(page.getByText('Listen Port')).toBeVisible();
  });

  test('switching to weatherlink_ip shows Device IP and TCP Port', async ({ page }) => {
    await driverSelect(page).selectOption('weatherlink_ip');
    await expect(page.getByText('Device IP Address')).toBeVisible();
    await expect(page.getByText('TCP Port')).toBeVisible();
  });

  test('WeatherLink section hidden for ecowitt', async ({ page }) => {
    await driverSelect(page).selectOption('ecowitt');
    await expect(page.getByText('Archive Period', { exact: false })).toHaveCount(0);
  });

  test('Backup tab is accessible', async ({ page }) => {
    await page.getByRole('button', { name: 'Backup' }).click();
    await expect(page.getByText('Backup', { exact: false }).first()).toBeVisible();
  });
});

test.describe('Barometer calibration panel', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
  });

  /** Serve a `supported` map with barometer_cal set as given. */
  async function stubCapability(page: import('@playwright/test').Page, barometerCal: boolean) {
    await page.route('**/api/weatherlink/config', async (route) => {
      await route.fulfill({
        json: {
          archive_period: 5,
          sample_period: 5,
          calibration: null,
          supported: {
            archive_period: true,
            sample_period: true,
            calibration: false,
            barometer_cal: barometerCal,
          },
        },
      });
    });
  }

  async function stubReference(
    page: import('@playwright/test').Page,
    body: Record<string, unknown>,
  ) {
    await page.route('**/api/station/barometer-reference', async (route) => {
      await route.fulfill({ json: body });
    });
  }

  async function stubCalibration(page: import('@playwright/test').Page) {
    await page.route('**/api/station/barometer-calibration', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          json: {
            barometer_inhg: 30.05,
            elevation_ft: 265,
            barcal_inhg: 0.0,
            gain: 0,
            offset: -36,
          },
        });
        return;
      }
      await route.fallback();
    });
  }

  function freshReference(overrides: Record<string, unknown> = {}) {
    return {
      references: [
        {
          station_id: 'KHRJ',
          station_name: 'Harnett Regional',
          distance_miles: 7.7,
          bearing_cardinal: 'W',
          observed_at: new Date(Date.now() - 5 * 60_000).toISOString(),
          altimeter_thousandths_inhg: 30030,
          altimeter_inhg: 30.03,
          raw_metar: 'METAR KHRJ 041935Z AUTO 20008KT 10SM CLR 28/22 A3003 RMK AO2',
          report_type: 'METAR',
        },
      ],
      location_configured: true,
      home_lat: 35.3809,
      home_lon: -78.5982,
      radius_miles: 60,
      fetched_at: new Date().toISOString(),
      ...overrides,
    };
  }

  test('explains itself rather than vanishing when unsupported', async ({ page }) => {
    // The #249 complaint: a hidden panel is indistinguishable from a
    // missing feature.
    await stubCapability(page, false);
    await page.goto('/settings');
    await expect(
      page.getByText('does not support barometer calibration', { exact: false }),
    ).toBeVisible();
  });

  test('renders console state and reference when supported', async ({ page }) => {
    await stubCapability(page, true);
    await stubCalibration(page);
    await stubReference(page, freshReference());
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Barometer Calibration' })).toBeVisible();
    await expect(page.getByText('30.050', { exact: false })).toBeVisible();
    // The station id appears twice (radio row + difference sentence), so
    // anchor on the radio's own cell rather than a bare text match.
    await expect(page.getByText('KHRJ', { exact: true })).toBeVisible();
    await expect(page.getByRole('radio')).toBeChecked();
    // console 30.050 vs reference 30.030 -> -0.020
    await expect(page.getByText('-0.020 inHg', { exact: false })).toBeVisible();
  });

  test('prompts for location when coordinates are unset', async ({ page }) => {
    await stubCapability(page, true);
    await stubCalibration(page);
    await stubReference(page, {
      references: [],
      location_configured: false,
      home_lat: 0,
      home_lon: 0,
      radius_miles: 60,
      fetched_at: new Date().toISOString(),
    });
    await page.goto('/settings');

    await expect(
      page.getByText("Set your station's location", { exact: false }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Apply Calibration' })).toBeDisabled();
  });

  test('blocks a stale reference until overridden', async ({ page }) => {
    await stubCapability(page, true);
    await stubCalibration(page);
    const stale = freshReference();
    (stale.references as Record<string, unknown>[])[0].observed_at =
      new Date(Date.now() - 90 * 60_000).toISOString();
    await stubReference(page, stale);
    await page.goto('/settings');

    const apply = page.getByRole('button', { name: 'Apply Calibration' });
    await expect(apply).toBeDisabled();
    await page.getByText('Use it anyway', { exact: false }).click();
    await expect(apply).toBeEnabled();
  });

  test('shows the elevation reconcile row for a sub-threshold difference', async ({ page }) => {
    // The fixture configures 315 ft; the console here reports 314 — one
    // foot apart.  The row used to require a >10 ft gap, which is
    // ~0.011 inHg, five times the difference the panel reports against the
    // reference it is calibrating against.  A 50 ft fixture mismatch would
    // have passed under the old rule too, so the console value is stubbed
    // to sit just inside it: this test fails if the threshold returns.
    await stubCapability(page, true);
    await stubReference(page, freshReference());
    await page.route('**/api/station/barometer-calibration', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          json: {
            barometer_inhg: 30.05, elevation_ft: 314,
            barcal_inhg: 0.0, gain: 0, offset: -36,
          },
        });
        return;
      }
      await route.fallback();
    });

    await page.goto('/settings');
    // Assert on the row element's full text rather than a substring: this
    // pins the configured value and the pressure-equivalent figure too, so
    // a regression dropping either fails here instead of passing on a
    // loose match.  Matched via the paragraph's text content because JSX
    // splits the line across several text nodes, which getByText's
    // per-node matching will not span.
    const row = page.locator('p', { hasText: 'Console: 314 ft' });
    await expect(row).toBeVisible();
    await expect(row).toContainText('Kanfei: 315 ft');
    await expect(row).toContainText('0.001 inHg');
  });

  test('compares elevation at the resolution the console can hold', async ({ page }) => {
    // The fixture stores 315.4 ft; the console reports 315.  Those agree
    // as far as the hardware is concerned — ELEVATION is whole feet — so
    // the reconcile row must stay hidden.  Without rounding the comparison
    // this shows a permanent disagreement no user can ever resolve: typing
    // 315.4 into a console that stores 315 leaves it reading 315 forever.
    await stubCapability(page, true);
    await stubReference(page, freshReference());
    await page.route('**/api/station/barometer-calibration', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          json: {
            barometer_inhg: 30.05, elevation_ft: 315,
            barcal_inhg: 0.0, gain: 0, offset: -36,
          },
        });
        return;
      }
      await route.fallback();
    });

    await page.goto('/settings');
    await expect(page.getByText('Barometer Calibration')).toBeVisible();
    await expect(page.locator('p', { hasText: 'Console: 315 ft' })).toHaveCount(0);
  });

  test('a failed reference refresh disables Apply rather than reusing the old one', async ({ page }) => {
    // Found by Codex on #256 R1. The panel used to keep the previously
    // selected METAR when a refresh failed, leaving Apply enabled against
    // a value it had just told the user it could not vouch for — a
    // hardware write against a stale reference.
    await stubCapability(page, true);
    await stubCalibration(page);

    let failNext = false;
    await page.route('**/api/station/barometer-reference', async (route) => {
      if (failNext) {
        await route.fulfill({ status: 503, json: { detail: 'upstream unavailable' } });
        return;
      }
      await route.fulfill({ json: freshReference() });
    });

    await page.goto('/settings');
    const apply = page.getByRole('button', { name: 'Apply Calibration' });
    await expect(apply).toBeEnabled();

    failNext = true;
    await page.getByRole('button', { name: 'Refresh' }).click();

    await expect(page.getByText('Could not fetch reference observations', { exact: false }))
      .toBeVisible();
    await expect(apply).toBeDisabled();
    // The stale row must be gone, not merely unusable.
    await expect(page.getByText('KHRJ', { exact: true })).toHaveCount(0);
  });

  test('a rejected write reports actual state, not the intended one', async ({ page }) => {
    // The #252 finding as UI: a refused BAR= still applies its elevation,
    // so the panel must re-read and say so rather than claim nothing moved.
    await stubCapability(page, true);
    await stubReference(page, freshReference());

    let posted = false;
    let getsAfterPost = 0;
    await page.route('**/api/station/barometer-calibration', async (route) => {
      const method = route.request().method();
      if (method === 'POST') {
        posted = true;
        await route.fulfill({
          status: 503,
          json: { detail: 'Station rejected the calibration (BAR= not acknowledged).' },
        });
        return;
      }
      if (posted) getsAfterPost += 1;
      await route.fulfill({
        json: {
          barometer_inhg: 30.05,
          // Elevation moved despite the refusal — the hardware behaviour.
          elevation_ft: posted ? 400 : 265,
          barcal_inhg: 0.0,
          gain: 0,
          offset: -36,
        },
      });
    });

    await page.goto('/settings');
    await page.getByRole('button', { name: 'Apply Calibration' }).click();

    await expect(page.getByText('Elevation changed from 265 ft to 400 ft', { exact: false }))
      .toBeVisible();
    // The re-read is the mechanism, not a nicety: without it the panel
    // would be reporting what it intended rather than what happened.
    expect(getsAfterPost).toBeGreaterThan(0);
  });
});
