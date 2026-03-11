// Playwright config in JS to avoid TS type issues in some environments
// Orchestrates FastAPI (uvicorn) and Next.js dev server for E2E.

// @ts-check
const path = require('path');
const { defineConfig, devices } = require('@playwright/test');

const ROOT_DIR = path.resolve(__dirname, '..');
const REUSE_UI = (process.env.REUSE_UI ?? '1').toString().trim() === '1';

module.exports = defineConfig({
  // Ensure any stray servers on our ports are killed before starting tests
  globalSetup: path.join(__dirname, 'scripts', 'global-setup.js'),
  testDir: './tests',
  timeout: 45_000,
  use: {
    baseURL: 'http://127.0.0.1:8101',
    headless: true,
    trace: 'on-first-retry',
  },
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'poetry run uvicorn main:app --host 127.0.0.1 --port 8101',
      url: 'http://127.0.0.1:8101/healthz',
  reuseExistingServer: true,
      timeout: 120_000,
      env: {
        ...process.env,
        // Ensure Python can import modules from repo root even though CWD is e2e
        PYTHONPATH: `${ROOT_DIR}${path.delimiter}${process.env.PYTHONPATH || ''}`,
        E2E_TEST_MODE: '1',
  // Explicitly disable any outbound emails in web server processes
  DISABLE_OUTBOUND_EMAIL: '1',
  // Avoid Redis connection attempts in CI; use in-memory/test fallbacks
  DISABLE_REDIS: '1',
  // Allow admin endpoints without 2FA in E2E to keep tests simple (step-up enforced separately)
  REQUIRE_ADMIN_2FA: '0',
        LOGIN_CAPTCHA_REQUIRED: '0',
        SIGNUP_CAPTCHA_REQUIRED: '0',
        STRICT_SECRETS: '0',
        TURNSTILE_SECRET_KEY: process.env.TURNSTILE_SECRET_KEY || '',
        WEBAUTHN_RP_ID: 'localhost',
        WEBAUTHN_ORIGIN: 'http://localhost:3000',
      },
    },
    {
  command: 'npm --prefix ../frontend run dev',
      url: 'http://localhost:3000',
  reuseExistingServer: REUSE_UI,
      timeout: 240_000,
      env: {
        ...process.env,
        BACKEND_BASE_URL: 'http://127.0.0.1:8101',
  // UI process also marks test mode so it won’t attempt email via any client-side triggers
  E2E_TEST_MODE: '1',
  DISABLE_OUTBOUND_EMAIL: '1',
        NEXT_PUBLIC_API_BASE_URL: 'http://127.0.0.1:8101',
        NEXT_TELEMETRY_DISABLED: '1',
      },
    },
  ],
});
