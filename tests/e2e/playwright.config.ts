import { defineConfig, devices } from '@playwright/test';
import path from 'path';

// Overridable because 8765 is not reserved — any other service on the
// dev box that happens to bind it makes the whole suite fail to start,
// and the failure surfaces as "0 tests ran, PASS" in the report script.
const PORT = Number(process.env.KANFEI_E2E_PORT) || 8765;
const BASE_URL = `http://localhost:${PORT}`;
const IS_CI = !!process.env.CI;

// Resolve paths relative to project root
const projectRoot = path.resolve(__dirname, '../..');
const venvPython = path.join(projectRoot, 'backend', '.venv', 'bin', 'python');

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  fullyParallel: false,
  forbidOnly: IS_CI,
  retries: IS_CI ? 1 : 0,
  workers: 1,
  reporter: IS_CI ? 'github' : 'html',
  timeout: IS_CI ? 60_000 : 30_000,

  expect: {
    // CI runners (headless Chrome, no GPU) need more time for React hydration
    timeout: IS_CI ? 15_000 : 5_000,
  },

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  globalSetup: './global-setup.ts',

  webServer: {
    // The DB rebuild lives INSIDE `command` (before uvicorn starts) rather
    // than in `globalSetup`.  Playwright starts `webServer` before
    // `globalSetup`, so a rebuild in globalSetup would replace the DB
    // *after* uvicorn's SQLAlchemy pool (default QueuePool, 5 connections)
    // already had file handles open to the previous inode.  Those stale
    // handles cause `attempt to write a readonly database` on POST /api/auth/login
    // and stale-inode `validate_session` misses that 401 post-login
    // requests, bouncing the freshly authenticated user back to /login.
    // Rebuilding before startup means the pool opens against the current
    // file.  Paired with `reuseExistingServer: false` below so a stale
    // uvicorn from a prior invocation cannot linger.  See #286.
    command: [
      venvPython, path.join(__dirname, 'build-test-db.py'), path.join(__dirname, 'fixtures'),
      '&&',
      venvPython, '-m', 'uvicorn', 'app.main:app',
      '--host', '127.0.0.1', '--port', String(PORT), '--log-level', 'info',
    ].join(' '),
    cwd: path.join(projectRoot, 'backend'),
    url: `${BASE_URL}/api/setup/status`,
    reuseExistingServer: false,
    timeout: IS_CI ? 60_000 : 30_000,
    env: {
      ...process.env,
      KANFEI_DB_PATH: path.resolve(__dirname, 'fixtures', 'test.db'),
      KANFEI_PORT: String(PORT),
      KANFEI_HOST: '127.0.0.1',
    },
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
    },
  ],
});
