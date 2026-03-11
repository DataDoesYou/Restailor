import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e.visual',
  fullyParallel: false,
  timeout: 30_000,
  reporter: 'list',
  use: {
    baseURL: process.env.FRONTEND_BASE_URL || 'http://localhost:3100',
    headless: true,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'node ./e2e.visual/mock-api-server.cjs',
      port: 3101,
      reuseExistingServer: true,
      cwd: __dirname,
    },
    {
      command: 'npx next dev -p 3100',
      port: 3100,
      reuseExistingServer: true,
      cwd: __dirname,
      env: { NEXT_PUBLIC_API_BASE_URL: 'http://localhost:3101' },
    },
  ],
});
