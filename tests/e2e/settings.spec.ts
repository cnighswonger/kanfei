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
    // exact: true — the WeatherLink card renders a heading containing
    // "settings could not be read" when no station is attached (the fixture's
    // normal state), which otherwise collides with the page heading.
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
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

  test('timezone dropdown is in Units section, not Display', async ({ page }) => {
    // Units and Display cards live under the Display tab.
    await page.getByRole('button', { name: 'Display' }).click();

    // Each card is a sibling <div style={cardStyle}> starting with an <h3>.
    // The parent-of-heading pattern scopes reliably to the card, unlike
    // a generic .filter({has:}) on 'div' which bubbles up to any ancestor.
    const unitsCard = page.getByRole('heading', { name: 'Units' }).locator('..');
    await expect(unitsCard.getByLabel('Timezone')).toBeVisible();

    const displayCard = page.getByRole('heading', { name: 'Display' }).locator('..');
    await expect(displayCard.getByLabel('Timezone')).toHaveCount(0);
  });
});

test.describe('Custom theme editor', () => {
  // Reset both localStorage and backend-persisted prefs.  ThemeContext
  // reconciles from /api/config on mount, so a stale backend value would
  // otherwise leak between tests.  The reset runs via an in-page fetch
  // so the injected knf_session cookie is attached automatically —
  // page.request runs in its own APIRequestContext where cookie handling
  // is unreliable.
  async function resetTheme(page: import('@playwright/test').Page) {
    const status = await page.evaluate(async () => {
      const resp = await fetch('/api/config', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([
          { key: 'ui_theme', value: 'dark' },
          { key: 'ui_custom_theme', value: '' },
        ]),
      });
      try {
        localStorage.removeItem('ui_custom_theme');
        localStorage.setItem('ui_theme', 'dark');
      } catch { /* localStorage unavailable */ }
      return { ok: resp.ok, status: resp.status };
    });
    if (!status.ok) {
      throw new Error(`resetTheme: PUT /api/config failed with ${status.status}`);
    }
  }

  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
    // Initial load so page.evaluate has a document to run in — then reset
    // and reload so ThemeContext picks up the clean state.
    const configReady1 = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.goto('/settings');
    await configReady1;
    await resetTheme(page);
    const configReady2 = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.reload();
    await configReady2;
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Display' }).click();
    await expect(page.getByLabel('Theme', { exact: true })).toBeVisible();
  });

  test.afterAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await injectAuthCookie(page);
    await page.goto('/settings');
    await resetTheme(page);
    await ctx.close();
  });

  test('selecting Custom reveals the editor', async ({ page }) => {
    await page.getByLabel('Theme', { exact: true }).selectOption('custom');
    await expect(page.getByLabel('Base theme')).toBeVisible();
    await expect(page.getByRole('button', { name: /Save Custom Theme|Saved!/ })).toBeVisible();
  });

  // The Accent color field row is a flex div whose first child is a
  // label div containing exactly "Accent" (fontWeight 500).  The
  // section header "Accent & Status" contains substring "Accent" but
  // not exact — exact-text plus a parent-hop lands us in the row.
  function accentHexInput(page: import('@playwright/test').Page) {
    const row = page.getByText('Accent', { exact: true }).locator('..');
    return row.locator('input[type="text"]');
  }

  test('changing accent color via hex input applies to DOM', async ({ page }) => {
    await page.getByLabel('Theme', { exact: true }).selectOption('custom');

    const input = accentHexInput(page);
    await input.fill('#ff0000');
    await input.blur();

    await expect.poll(() =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim(),
      ),
    ).toBe('#ff0000');
  });

  test('Save persists custom theme across reload', async ({ page }) => {
    await page.getByLabel('Theme', { exact: true }).selectOption('custom');

    await accentHexInput(page).fill('#00ff00');

    const configWrite = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/config') &&
        resp.request().method() === 'PUT' &&
        resp.status() === 200,
    );
    await page.getByRole('button', { name: 'Save Custom Theme' }).click();
    await configWrite;

    await expect(page.getByRole('button', { name: 'Saved!' })).toBeVisible();

    const configReady = page.waitForResponse(
      (resp) => resp.url().includes('/api/config') && resp.status() === 200,
    );
    await page.reload();
    await configReady;
    // Settings resets to the Station tab on reload — re-select Display.
    await page.getByRole('button', { name: 'Display' }).click();

    await expect(page.getByLabel('Theme', { exact: true })).toHaveValue('custom');
    await expect.poll(() =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim(),
      ),
    ).toBe('#00ff00');
  });

  test('switching to Dark then back to Custom restores the saved theme', async ({ page }) => {
    await page.getByLabel('Theme', { exact: true }).selectOption('custom');
    await accentHexInput(page).fill('#0000ff');

    const savedWrite = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/config') &&
        resp.request().method() === 'PUT' &&
        resp.status() === 200,
    );
    await page.getByRole('button', { name: 'Save Custom Theme' }).click();
    await savedWrite;

    await page.getByLabel('Theme', { exact: true }).selectOption('dark');
    // Dark preset accent is not #0000ff — confirm we actually left custom
    await expect.poll(() =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim(),
      ),
    ).not.toBe('#0000ff');

    await page.getByLabel('Theme', { exact: true }).selectOption('custom');
    await expect.poll(() =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim(),
      ),
    ).toBe('#0000ff');
  });

  test('Cancel discards draft without persisting', async ({ page }) => {
    // Establish a known baseline: dark preset's accent
    const baseline = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim(),
    );

    await page.getByLabel('Theme', { exact: true }).selectOption('custom');
    await accentHexInput(page).fill('#abcdef');

    await expect.poll(() =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim(),
      ),
    ).toBe('#abcdef');

    await page.getByRole('button', { name: 'Cancel' }).click();

    // No custom theme was saved, so Settings.tsx falls back to dark and the
    // committed theme's accent is reapplied.
    await expect(page.getByLabel('Theme', { exact: true })).toHaveValue('dark');
    await expect.poll(() =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim(),
      ),
    ).toBe(baseline);
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

  const THRESHOLDS = {
    min_stations: 2,
    cross_station_spread_threshold_hpa: 0.7,
    console_window_minutes: 15,
    min_console_samples: 20,
    max_station_distance_miles: 47,
    station_window_hours: 2,
    mad_rejection_multiplier: 2.5,
    mad_min_scale_hpa: 0.15,
    mad_max_iterations: 10,
    distance_weight_epsilon_miles: 1.0,
    station_limit_for_calibration: null,
    console_stdev_threshold_hpa: 0.2,
    rapid_trend_station_fraction: 0.30,
    recent_window_hours: 24,
    recent_unsettled_stdev_threshold_hpa: 0.5,
  };

  function station(
    station_id: string,
    altimeter_inhg: number,
    overrides: Record<string, unknown> = {},
  ) {
    const t = Math.round(altimeter_inhg * 1000);
    return {
      station_id,
      station_name: `${station_id} name`,
      distance_miles: 10,
      bearing_cardinal: 'N',
      n_obs: 5,
      median_altimeter_thousandths_inhg: t,
      median_altimeter_inhg: altimeter_inhg,
      obs_spread_thousandths_inhg: 20,
      newest_observed_at: new Date().toISOString(),
      is_outlier: false,
      has_rapid_trend: false,
      ...overrides,
    };
  }

  /** A reference response whose aggregate has both gates PASSING —
   *  render the "Use recommended offset" button.  Two tightly-agreeing
   *  stations (spread 0.03 hPa), a healthy console sample, and a
   *  median-of-medians of 30.020 inHg vs a 30.050 inHg console reading
   *  yield offset -0.030 inHg. */
  function freshReferenceApplyReady(overrides: Record<string, unknown> = {}) {
    return {
      references: [],
      location_configured: true,
      home_lat: 35.3809,
      home_lon: -78.5982,
      radius_miles: 60,
      fetched_at: new Date().toISOString(),
      aggregate: {
        console: {
          median_hpa: 1017.5,
          n_samples: 90,
          window_minutes: 15,
          stdev_hpa: 0.05,
          stdev_hpa_recent: 0.1,
          n_samples_recent: 500,
          recent_window_hours: 24,
          window_start: new Date(Date.now() - 15 * 60_000).toISOString(),
          window_end: new Date().toISOString(),
        },
        per_station_medians: [
          station('KHRJ', 30.020),
          station('KJNX', 30.021),
        ],
        n_stations_considered: 2,
        n_stations_used: 2,
        cross_station_spread_hpa: 0.03,
        recommendation: {
          should_apply: true,
          skip_reason: null,
          median_of_medians_thousandths_inhg: 30020,
          median_of_medians_inhg: 30.020,
          offset_thousandths_inhg: -30,
          offset_inhg: -0.030,
          hold_override_allowed: false,
        },
        thresholds: THRESHOLDS,
        reference_radius_miles: 47,
      },
      ...overrides,
    };
  }

  /** A reference response whose aggregate is HOLDING on cross-station
   *  disagreement.  Same shape as the smoke case: two stations that
   *  disagree by more than the (weighted) 0.7 hPa threshold, one
   *  flagged as outlier.  The autonomous Apply button must NOT
   *  render — but the "Accept anyway" override button SHOULD, since
   *  `hold_override_allowed=true` and a valid recommended value
   *  exists. */
  function freshReferenceHolding(overrides: Record<string, unknown> = {}) {
    return {
      references: [],
      location_configured: true,
      home_lat: 35.3809,
      home_lon: -78.5982,
      radius_miles: 60,
      fetched_at: new Date().toISOString(),
      aggregate: {
        console: {
          median_hpa: 1017.5,
          n_samples: 90,
          window_minutes: 15,
          stdev_hpa: 0.05,
          stdev_hpa_recent: 0.1,
          n_samples_recent: 500,
          recent_window_hours: 24,
          window_start: new Date(Date.now() - 15 * 60_000).toISOString(),
          window_end: new Date().toISOString(),
        },
        per_station_medians: [
          station('KHRJ', 30.020),
          station('KGSB', 29.935, { is_outlier: true, station_name: 'Goldsboro AFB' }),
          station('KSOP', 30.030),
        ],
        n_stations_considered: 3,
        n_stations_used: 2,
        // Weighted 2σ spread above the 0.7 hPa threshold so the
        // rendered gate badges and diagnostic agree with the
        // `cross_station_disagreement` skip below.
        cross_station_spread_hpa: 1.2,
        recommendation: {
          should_apply: false,
          skip_reason: 'cross_station_disagreement',
          // Populated even on HOLD now (#307) — this is the value
          // the override button commits to when the operator clicks
          // "Accept anyway".
          median_of_medians_thousandths_inhg: 30020,
          median_of_medians_inhg: 30.020,
          offset_thousandths_inhg: -30,
          offset_inhg: -0.030,
          hold_override_allowed: true,
        },
        thresholds: THRESHOLDS,
        reference_radius_miles: 47,
      },
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

  test('renders console state and the aggregate panel when supported', async ({ page }) => {
    await stubCapability(page, true);
    await stubCalibration(page);
    await stubReference(page, freshReferenceApplyReady());
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Barometer Calibration' })).toBeVisible();
    // Console reading.
    await expect(page.getByText('30.050', { exact: false })).toBeVisible();
    // Aggregate panel + its per-station table.
    await expect(page.getByRole('heading', { name: 'Multi-Station Aggregate' }))
      .toBeVisible();
    await expect(page.getByText('KHRJ', { exact: false })).toBeVisible();
    await expect(page.getByText('KJNX', { exact: false })).toBeVisible();
    // Both gates pass → Apply button renders.
    await expect(
      page.getByRole('button', { name: 'Use recommended offset' }),
    ).toBeVisible();
  });

  test('prompts for location when coordinates are unset', async ({ page }) => {
    // No aggregate is returned when location is unset — panel shows the
    // "set location" prompt and Apply is unreachable (button not rendered).
    await stubCapability(page, true);
    await stubCalibration(page);
    await stubReference(page, {
      references: [],
      location_configured: false,
      home_lat: 0,
      home_lon: 0,
      radius_miles: 60,
      fetched_at: new Date().toISOString(),
      aggregate: null,
    });
    await page.goto('/settings');

    await expect(
      page.getByText("Set your station's location", { exact: false }),
    ).toBeVisible();
    // Aggregate button must not exist — no aggregate to apply.
    await expect(
      page.getByRole('button', { name: 'Use recommended offset' }),
    ).toHaveCount(0);
  });

  test('on HOLD shows the diagnostic and an explicit override button (#307)', async ({ page }) => {
    // When the reference stations disagree beyond tolerance, the
    // autonomous Apply button must NOT render — the algorithm is not
    // confident enough to commit on its own.  But the override button
    // ("Accept anyway") IS offered so an operator with out-of-band
    // knowledge that the recommendation is right for their location
    // can commit to the SAME algorithm-computed weighted-median
    // value.  Different failure mode from the old picker: the write
    // VALUE is still algorithm-determined, only the write DECISION
    // is delegated to the operator.
    await stubCapability(page, true);
    await stubCalibration(page);
    await stubReference(page, freshReferenceHolding());
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Multi-Station Aggregate' }))
      .toBeVisible();
    // The skip reason renders as a targeted diagnostic.
    await expect(
      page.getByText('Stations disagree beyond tolerance', { exact: false }),
    ).toBeVisible();
    // Autonomous Apply button must be absent — HOLD means the
    // algorithm will not fire on its own.
    await expect(
      page.getByRole('button', { name: 'Use recommended offset' }),
    ).toHaveCount(0);
    // Override button IS present.
    await expect(
      page.getByRole('button', { name: 'Accept anyway (override HOLD)' }),
    ).toBeVisible();
    // Excluded stations still ride along in the table so the operator
    // can see WHY the count dropped.
    await expect(page.getByText('KGSB', { exact: false })).toBeVisible();
    await expect(page.getByText('outlier', { exact: false })).toBeVisible();
  });

  test('shows the elevation reconcile row for a sub-threshold difference', async ({ page }) => {
    // The fixture stores 315.4 ft, which the row displays as 315; the
    // console here reports 314 — one foot apart.  The row used to require
    // a >10 ft gap, which is ~0.011 inHg, five times the difference the
    // panel reports against the reference it is calibrating against.  A
    // 50 ft fixture mismatch would have passed under the old rule too, so
    // the console value is stubbed to sit just inside it: this test fails
    // if the threshold returns.
    await stubCapability(page, true);
    await stubReference(page, freshReferenceApplyReady());
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
    await stubReference(page, freshReferenceApplyReady());
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

  test('a failed reference refresh hides the aggregate rather than reusing the old one', async ({ page }) => {
    // Found by Codex on #256 R1. The panel used to keep the previously
    // selected METAR when a refresh failed, leaving Apply enabled
    // against a value it had just told the user it could not vouch for
    // — a hardware write against a stale reference.  Same invariant
    // applies to the aggregate: on refresh failure the aggregate is
    // dropped and Apply becomes unreachable.
    await stubCapability(page, true);
    await stubCalibration(page);

    let failNext = false;
    await page.route('**/api/station/barometer-reference', async (route) => {
      if (failNext) {
        await route.fulfill({ status: 503, json: { detail: 'upstream unavailable' } });
        return;
      }
      await route.fulfill({ json: freshReferenceApplyReady() });
    });

    await page.goto('/settings');
    const apply = page.getByRole('button', { name: 'Use recommended offset' });
    await expect(apply).toBeVisible();

    failNext = true;
    await page.getByRole('button', { name: 'Refresh' }).click();

    await expect(page.getByText('Could not fetch reference observations', { exact: false }))
      .toBeVisible();
    // The stale aggregate must be gone, not merely visually stale.
    await expect(apply).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Multi-Station Aggregate' }))
      .toHaveCount(0);
  });

  test('a rejected write reports actual state, not the intended one', async ({ page }) => {
    // The #252 finding as UI: a refused BAR= still applies its elevation,
    // so the panel must re-read and say so rather than claim nothing moved.
    await stubCapability(page, true);
    await stubReference(page, freshReferenceApplyReady());

    let posted = false;
    let getsAfterPost = 0;
    let postedBar: number | null = null;
    await page.route('**/api/station/barometer-calibration', async (route) => {
      const method = route.request().method();
      if (method === 'POST') {
        posted = true;
        const body = route.request().postDataJSON() as
          | { bar_thousandths_inhg?: number }
          | null;
        postedBar = body?.bar_thousandths_inhg ?? null;
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
    await page.getByRole('button', { name: 'Use recommended offset' }).click();

    await expect(page.getByText('Elevation changed from 265 ft to 400 ft', { exact: false }))
      .toBeVisible();
    // The re-read is the mechanism, not a nicety: without it the panel
    // would be reporting what it intended rather than what happened.
    expect(getsAfterPost).toBeGreaterThan(0);
    // The button posted the ABSOLUTE median-of-medians target
    // (30020 thousandths from freshReferenceApplyReady), NOT the signed
    // offset delta (-30).  This is the contract shift #306 introduced.
    expect(postedBar).toBe(30020);
  });
});
test.describe('Console data operations', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
  });

  async function stubSupport(page: import('@playwright/test').Page, ops: boolean) {
    await page.route('**/api/weatherlink/config', async (route) => {
      await route.fulfill({
        json: {
          archive_period: 5, sample_period: 5, calibration: null,
          supported: {
            archive_period: true, sample_period: true, calibration: false,
            barometer_cal: false, console_data_ops: ops,
          },
        },
      });
    });
  }

  async function stubPreflights(
    page: import('@playwright/test').Page,
    rain: Record<string, unknown>,
  ) {
    await page.route('**/api/station/rain-preflight', async (route) => {
      await route.fulfill({ json: rain });
    });
    await page.route('**/api/station/archive-preflight', async (route) => {
      await route.fulfill({
        json: { records_in_kanfei: 4211, latest_synced_at: new Date().toISOString() },
      });
    });
  }

  test('absent when the station cannot do these operations', async ({ page }) => {
    await stubSupport(page, false);
    await page.goto('/settings');
    await expect(page.getByText('Console Data', { exact: false })).toHaveCount(0);
  });

  test('names the rainfall that would be discarded', async ({ page }) => {
    // The whole design: show the cost before it is paid. 31.2 on the
    // console vs 29.5 recorded means 1.7 mm of real rain would vanish.
    await stubSupport(page, true);
    await stubPreflights(page, {
      console_mm: 31.2,
      last_stored_mm: 29.5,
      last_stored_at: new Date(Date.now() - 12 * 60_000).toISOString(),
      difference_mm: 1.7,
      collector_known: true,
    });
    await page.goto('/settings');

    // Split across a <strong> by JSX, so match the paragraph.
    const warning = page.locator('p', { hasText: 'that Kanfei has not recorded' });
    await expect(warning).toContainText('1.7 mm');
    await expect(warning).toContainText('discards that rainfall');
  });

  test('refuses to offer the write when the collector is unknown', async ({ page }) => {
    // The driver would refuse anyway rather than risk a 2x error; saying
    // so up front beats letting the user type a number and be rejected.
    await stubSupport(page, true);
    await stubPreflights(page, {
      console_mm: 31.2, last_stored_mm: 29.5,
      last_stored_at: new Date().toISOString(),
      difference_mm: 1.7, collector_known: false,
    });
    await page.goto('/settings');

    await expect(
      page.locator('p', { hasText: 'rain collector type is unknown' }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Overwrite total' })).toBeDisabled();
  });

  test('states what survives an archive clear', async ({ page }) => {
    // Kanfei's downloaded records are safe; only unsynced ones are lost.
    // Saying which is which is the difference between an informed choice
    // and a leap.
    await stubSupport(page, true);
    await stubPreflights(page, {
      console_mm: 10, last_stored_mm: 10,
      last_stored_at: new Date().toISOString(),
      difference_mm: 0, collector_known: true,
    });
    await page.goto('/settings');

    await expect(page.getByText('4,211', { exact: false })).toBeVisible();
    await expect(
      page.getByText('only records the console has not yet handed over', { exact: false }),
    ).toBeVisible();
  });

  test('a dismissed confirmation writes nothing', async ({ page }) => {
    // The confirm is the safety mechanism, so cancelling it must not
    // reach the wire at all.
    await stubSupport(page, true);
    await stubPreflights(page, {
      console_mm: 31.2, last_stored_mm: 29.5,
      last_stored_at: new Date().toISOString(),
      difference_mm: 1.7, collector_known: true,
    });
    let posted = false;
    await page.route('**/api/station/yearly-rain', async (route) => {
      posted = true;
      await route.fulfill({ json: { success: true, before_mm: 31.2, after_mm: 0 } });
    });
    page.on('dialog', (d) => d.dismiss());

    await page.goto('/settings');
    await page.getByLabel('New yearly rain total').fill('0');
    await page.getByRole('button', { name: 'Overwrite total' }).click();
    await page.waitForTimeout(500);

    expect(posted).toBe(false);  });
});

test.describe('Console highs and lows panel', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
  });

  async function stubSupport(page: import('@playwright/test').Page, highsLows: boolean) {
    await page.route('**/api/weatherlink/config', async (route) => {
      await route.fulfill({
        json: {
          archive_period: 5, sample_period: 5, calibration: null,
          supported: {
            archive_period: true, sample_period: true, calibration: false,
            barometer_cal: false, highs_lows: highsLows,
          },
        },
      });
    });
  }

  /** SI values, as the HILOWS endpoint returns them. */
  function siBlock() {
    const hiLo = (low: number | null, high: number | null) => ({
      low, high, time_low: '05:12', time_high: '14:35',
    });
    const hiOnly = (value: number | null) => ({ value, time: '14:35' });
    const period = (low: number | null, high: number | null) => ({
      day: hiLo(low, high), month: hiLo(null, null), year: hiLo(null, null),
    });
    const hiPeriod = (value: number | null) => ({
      day: hiOnly(value), month: hiOnly(null), year: hiOnly(null),
    });
    return {
      highs_lows: {
        barometer: period(1010.0, 1018.5),
        wind_speed: hiPeriod(8.9),          // 8.9 m/s ≈ 19.9 mph
        inside_temp: period(20.0, 24.0),
        inside_humidity: period(40, 55),
        outside_temp: period(18.2, 33.2),   // 33.2 °C = 91.8 °F
        dew_point: period(12.0, 22.0),
        wind_chill: hiPeriod(null),
        heat_index: hiPeriod(38.0),
        thsw_index: hiPeriod(null),
        solar_radiation: hiPeriod(null),
        uv_index: hiPeriod(null),
        rain_rate: hiPeriod(0),
        rain_rate_hour_hi: null,
        humidities: [period(41, 84)],
      },
    };
  }

  test('absent when the station cannot report highs and lows', async ({ page }) => {
    // A VP1 without LOOP2 genuinely cannot answer HILOWS, and the
    // dashboard still shows Kanfei's own extremes, so there is nothing
    // for the user to act on.
    await stubSupport(page, false);
    await page.goto('/settings');
    await expect(page.getByText('Console Highs', { exact: false })).toHaveCount(0);
  });

  test('converts the console SI values into Kanfei units', async ({ page }) => {
    // The endpoints disagree: HILOWS is SI, daily_extremes has already
    // been converted for display. Showing 33.2 beside 91.8 for the same
    // temperature would be worse than showing nothing.
    await stubSupport(page, true);
    await page.route('**/api/station/highs-lows', async (route) => {
      await route.fulfill({ json: siBlock() });
    });
    await page.route('**/api/current', async (route) => {
      const body = await (await route.fetch()).json();
      body.daily_extremes = {
        outside_temp_hi: { value: 91.8, unit: 'F', at: null },
        outside_temp_lo: { value: 64.8, unit: 'F', at: null },
        wind_speed_hi: { value: 19.9, unit: 'mph', at: null },
        barometer_hi: { value: 30.08, unit: 'inHg', at: null },
        barometer_lo: { value: 29.83, unit: 'inHg', at: null },
        humidity_hi: { value: 84, unit: '%', at: null },
        humidity_lo: { value: 41, unit: '%', at: null },
      };
      await route.fulfill({ json: body });
    });
    await page.goto('/settings');

    const row = page.locator('tr', { hasText: 'Outside temperature' });
    // 33.2 °C must render as 91.8 F, matching Kanfei's own figure.
    await expect(row).toContainText('91.8');
    await expect(row).not.toContainText('33.2');
    await expect(row).toContainText('14:35');

    // 8.9 m/s -> 19.9 mph, not 8.9.
    const wind = page.locator('tr', { hasText: 'Wind speed' });
    await expect(wind).toContainText('19.9');
  });

  test('renders the console column alone when ours is unavailable', async ({ page }) => {
    await stubSupport(page, true);
    await page.route('**/api/station/highs-lows', async (route) => {
      await route.fulfill({ json: siBlock() });
    });
    await page.route('**/api/current', async (route) => {
      await route.fulfill({ status: 503, json: { detail: 'down' } });
    });
    await page.goto('/settings');

    await expect(
      page.getByText("Kanfei's own extremes could not be loaded", { exact: false }),
    ).toBeVisible();
    // The console figure still converts, using the fallback unit.
    await expect(page.locator('tr', { hasText: 'Outside temperature' })).toContainText('91.8');
  });
});

test.describe('Vantage sensor calibration panel', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
  });

  async function stubSupport(
    page: import('@playwright/test').Page,
    sensorCalibration: boolean,
  ) {
    await page.route('**/api/weatherlink/config', async (route) => {
      await route.fulfill({
        json: {
          archive_period: 5, sample_period: 5, calibration: null,
          supported: {
            archive_period: true, sample_period: true, calibration: false,
            barometer_cal: false, sensor_calibration: sensorCalibration,
          },
        },
      });
    });
  }

  async function stubCal(
    page: import('@playwright/test').Page,
    offsets: Record<string, number>,
  ) {
    await page.route('**/api/station/calibration', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          json: { offsets, temp_units: 'tenths_f', humidity_units: 'percent' },
        });
        return;
      }
      await route.fallback();
    });
  }

  test('explains itself rather than vanishing when unsupported', async ({ page }) => {
    // #249: this is the panel a Vantage user goes looking for, so
    // silence would read as a missing feature.
    await stubSupport(page, false);
    await page.goto('/settings');
    await expect(
      page.getByText('does not support per-sensor calibration', { exact: false }),
    ).toBeVisible();
  });

  test('shows tenths of a degree as whole degrees', async ({ page }) => {
    // The console stores 25 meaning +2.5 °F. Showing the raw integer
    // would read as a 25-degree trim — a tenfold error in the direction
    // that looks plausible.
    await stubSupport(page, true);
    await stubCal(page, { outside_temp: 25, inside_temp: -6, outside_humidity: 3 });
    await page.goto('/settings');

    await expect(page.getByText('+2.5 °F', { exact: false })).toBeVisible();
    await expect(page.getByText('-0.6 °F', { exact: false })).toBeVisible();
    // Humidity is whole percent, not tenths — the same number must not
    // be divided by ten here.
    await expect(page.getByText('+3 %', { exact: false })).toBeVisible();
  });

  test('an unreadable field says so rather than showing zero', async ({ page }) => {
    // Zero is a real calibration. Rendering an absent field as 0 would
    // make "no offset" and "could not read" identical on screen.
    await stubSupport(page, true);
    await stubCal(page, { outside_temp: 0 });
    await page.goto('/settings');

    // Zero renders unsigned — a "+" on nothing reads oddly.
    await expect(page.getByText('0.0 °F', { exact: false })).toBeVisible();
    // The three fields the stub omitted must say so, not show 0.
    await expect(page.getByText('unreadable', { exact: false })).toHaveCount(3);
  });

  test('sends tenths, not degrees', async ({ page }) => {
    await stubSupport(page, true);
    let sent: Record<string, unknown> | null = null;
    await page.route('**/api/station/calibration', async (route) => {
      if (route.request().method() === 'POST') {
        sent = route.request().postDataJSON();
        await route.fulfill({
          json: {
            success: true,
            before: { outside_temp: 0 },
            after: { outside_temp: 25 },
          },
        });
        return;
      }
      await route.fulfill({
        json: {
          offsets: { outside_temp: 0 },
          temp_units: 'tenths_f', humidity_units: 'percent',
        },
      });
    });
    await page.goto('/settings');

    await page.getByLabel('Outside temperature offset').fill('2.5');
    await page.getByRole('button', { name: 'Apply' }).first().click();

    await expect(page.getByText('set to 2.5 °F', { exact: false })).toBeVisible();
    // 2.5 °F must reach the wire as 25 tenths.
    expect(sent).toEqual({ field: 'outside_temp', offset: 25 });

    // Outside temperature applied in ~1s on hardware, so the lag note
    // would be misleading here (#276).
    await expect(
      page.getByText('may take up to a minute', { exact: false }),
    ).toHaveCount(0);
  });

  test('warns that an onboard sensor reading lags the offset', async ({ page }) => {
    // Inside temp/humidity come from the console's own sensor, which
    // reports about once a minute — measured at ~30s on fw 3.0.  The
    // offset changes at once but the reading does not, and without
    // saying so a user concludes the write failed (#276).
    await stubSupport(page, true);
    await page.route('**/api/station/calibration', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          json: {
            success: true,
            before: { inside_humidity: 0 },
            after: { inside_humidity: 3 },
          },
        });
        return;
      }
      await route.fulfill({
        json: {
          offsets: { inside_humidity: 0 },
          temp_units: 'tenths_f', humidity_units: 'percent',
        },
      });
    });
    await page.goto('/settings');

    await page.getByLabel('Inside humidity offset').fill('3');
    await page.getByRole('button', { name: 'Apply' }).last().click();

    await expect(page.getByText('set to 3 %', { exact: false })).toBeVisible();
    await expect(
      page.getByText('may take up to a minute', { exact: false }),
    ).toBeVisible();
  });
});

test.describe('Console location reconcile', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthCookie(page);
  });

  async function stubSupport(page: import('@playwright/test').Page, location: boolean) {
    await page.route('**/api/weatherlink/config', async (route) => {
      await route.fulfill({
        json: {
          archive_period: 5,
          sample_period: 5,
          calibration: null,
          supported: {
            archive_period: true, sample_period: true,
            calibration: false, barometer_cal: false, location,
          },
        },
      });
    });
  }

  async function stubLocation(
    page: import('@playwright/test').Page,
    latitude: number,
    longitude: number,
  ) {
    await page.route('**/api/station/location', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { latitude, longitude, resolution_deg: 0.1 } });
        return;
      }
      await route.fallback();
    });
  }

  test('absent entirely when the station has no console location', async ({ page }) => {
    // Unlike the calibration panel, silence is right here: the Location
    // card itself still works, and there is nothing a legacy user could
    // act on.
    //
    // Asserting absence alone would pass if the whole card failed to
    // render, so this also pins that the card IS there, that no
    // "unsupported" message appears, and that the endpoint is never
    // called — Codex flagged the weaker version on #265 R1.
    const requests: string[] = [];
    await page.route('**/api/station/location', async (route) => {
      requests.push(route.request().method());
      await route.fulfill({ json: { latitude: 0, longitude: 0, resolution_deg: 0.1 } });
    });
    await stubSupport(page, false);
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Location' })).toBeVisible();
    await expect(page.getByText('Console holds', { exact: false })).toHaveCount(0);
    // Scoped to location: the barometer panel legitimately renders its
    // own "does not support" message under this same stub, and a bare
    // match caught that instead.
    await expect(
      page.getByText('does not support setting its location', { exact: false }),
    ).toHaveCount(0);
    await expect(page.getByText('console cannot store', { exact: false })).toHaveCount(0);
    expect(requests).toEqual([]);
  });

  test('half-step coordinates still read as agreement', async ({ page }) => {
    // The #265 R1 blocker.  Python's round() is banker's rounding, so
    // 35.85 and 35.75 both store as 358 tenths; JavaScript's Math.round
    // goes half-up toward +Infinity, giving 35.9 and 35.8.  Re-deriving
    // the rounding in the comparator therefore disagreed with the writer
    // at exactly these values, and a console that had just been written
    // correctly showed as permanently wrong.
    await stubSupport(page, true);
    await page.route('**/api/config', async (route) => {
      const body = await (await route.fetch()).json();
      for (const item of body) {
        if (item.key === 'latitude') item.value = 35.85;
        if (item.key === 'longitude') item.value = -78.75;
      }
      await route.fulfill({ json: body });
    });
    // What Python's banker's rounding actually writes for those inputs.
    await stubLocation(page, 35.8, -78.8);
    await page.goto('/settings');

    const row = page.locator('p', { hasText: 'Console holds' });
    await expect(row).toContainText('matches your location');
  });

  test('agrees when the console holds the rounded value', async ({ page }) => {
    // The fixture configures 35.7796 / -78.6382, which the console can
    // only store as 35.8 / -78.6.  That is agreement, not a mismatch —
    // comparing for equality here would nag permanently on a correctly
    // configured station.
    await stubSupport(page, true);
    await stubLocation(page, 35.8, -78.6);
    await page.goto('/settings');

    // Split across spans by JSX, so match the paragraph rather than a
    // text node — getByText will not span children.
    const row = page.locator('p', { hasText: 'Console holds' });
    await expect(row).toContainText('35.8, -78.6');
    await expect(row).toContainText('matches your location');
    await expect(
      page.getByRole('button', { name: 'Send my location to the console' }),
    ).toHaveCount(0);
  });

  test('offers the push when the console holds something else', async ({ page }) => {
    await stubSupport(page, true);
    await stubLocation(page, 12.3, 45.6);
    await page.goto('/settings');

    const row = page.locator('p', { hasText: 'Console holds' });
    await expect(row).toContainText('12.3, 45.6');
    await expect(row).toContainText('does not match your location');
    await expect(
      page.getByRole('button', { name: 'Send my location to the console' }),
    ).toBeVisible();
  });

  test('reports what the console rounded to, not what was sent', async ({ page }) => {
    await stubSupport(page, true);
    let written = false;
    await page.route('**/api/station/location', async (route) => {
      if (route.request().method() === 'POST') {
        written = true;
        await route.fulfill({
          json: {
            success: true,
            before: { latitude: 12.3, longitude: 45.6 },
            after: { latitude: 35.8, longitude: -78.6 },
          },
        });
        return;
      }
      await route.fulfill({
        json: written
          ? { latitude: 35.8, longitude: -78.6, resolution_deg: 0.1 }
          : { latitude: 12.3, longitude: 45.6, resolution_deg: 0.1 },
      });
    });

    await page.goto('/settings');
    await page.getByRole('button', { name: 'Send my location to the console' }).click();
    // 35.7796 was sent; 35.8 is what the station has.
    await expect(page.getByText('Console now reads 35.8', { exact: false })).toBeVisible();  });
});
