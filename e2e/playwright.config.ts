import { defineConfig, devices } from '@playwright/test';
import path from 'path';

const ROOT_DIR = path.resolve(__dirname, '..');

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  globalTeardown: './global.teardown.ts',
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
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
  command: process.env.PW_UVICORN_CMD || 'poetry run uvicorn main:app --host 127.0.0.1 --port 8101',
  url: 'http://127.0.0.1:8101/healthz',
  reuseExistingServer: true,
      timeout: 90_000,
      env: {
        ...process.env,
        // Ensure Python can import modules from repo root even though CWD is e2e
        PYTHONPATH: `${ROOT_DIR}${path.delimiter}${process.env.PYTHONPATH || ''}`,
        // So tests can bypass CAPTCHA and mark users verified via test-only endpoint
        E2E_TEST_MODE: '1',
  DISABLE_OUTBOUND_EMAIL: '1',
        LOGIN_CAPTCHA_REQUIRED: '0',
        SIGNUP_CAPTCHA_REQUIRED: '0',
        STRICT_SECRETS: '0',
        // Make Turnstile optional during tests
        TURNSTILE_SECRET_KEY: process.env.TURNSTILE_SECRET_KEY || '',
        // WebAuthn RP/origin for Next.js dev server
        WEBAUTHN_RP_ID: 'localhost',
        WEBAUTHN_ORIGIN: 'http://localhost:3000',
      },
    },
    {
      command: process.env.PW_NEXT_CMD || 'npm --prefix ../frontend run dev',
      url: 'http://localhost:3000',
  reuseExistingServer: true,
      timeout: 180_000,
      env: {
        ...process.env,
        BACKEND_BASE_URL: 'http://127.0.0.1:8101',
  E2E_TEST_MODE: '1',
  DISABLE_OUTBOUND_EMAIL: '1',
  NEXT_PUBLIC_API_BASE_URL: 'http://127.0.0.1:8101',
  // Propagate WebAuthn expected origin and RP ID to the UI so it can set correct headers
  WEBAUTHN_RP_ID: 'localhost',
  WEBAUTHN_ORIGIN: 'http://localhost:3000',
      },
    },
  ],
});
