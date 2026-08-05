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
    // The fixture stores 315.4 ft, which the row displays as 315; the
    // console here reports 314 — one foot apart.  The row used to require
    // a >10 ft gap, which is ~0.011 inHg, five times the difference the
    // panel reports against the reference it is calibrating against.  A
    // 50 ft fixture mismatch would have passed under the old rule too, so
    // the console value is stubbed to sit just inside it: this test fails
    // if the threshold returns.
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
    await expect(page.getByText('Console now reads 35.8', { exact: false })).toBeVisible();
  });
});
