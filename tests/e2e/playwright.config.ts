import { defineConfig, devices } from '@playwright/test';
import path from 'path';

const PORT = 8765;
const BASE_URL = `http://localhost:${PORT}`;

// Resolve paths relative to project root
const projectRoot = path.resolve(__dirname, '../..');
const venvPython = path.join(projectRoot, 'backend', '.venv', 'bin', 'python');

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'html',
  timeout: 30_000,

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  globalSetup: './global-setup.ts',

  webServer: {
    // Call uvicorn directly (station.py hardcodes port 8000)
    command: [
      venvPython, '-m', 'uvicorn', 'app.main:app',
      '--host', '127.0.0.1', '--port', String(PORT), '--log-level', 'info',
    ].join(' '),
    cwd: path.join(projectRoot, 'backend'),
    url: `${BASE_URL}/api/setup/status`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
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
