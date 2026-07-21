import { defineConfig, devices } from '@playwright/test';

const webServer = process.env.FINANCE_SKIP_PLAYWRIGHT_WEBSERVER
  ? undefined
  : [
      {
        command: 'node e2e/mock-api.mjs',
        url: 'http://127.0.0.1:8123/api/health',
        reuseExistingServer: !process.env.CI,
        timeout: 30000,
      },
      {
        command: 'node ./node_modules/vite/bin/vite.js --host 127.0.0.1',
        url: 'http://127.0.0.1:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 30000,
      },
    ];

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: process.env.FINANCE_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 768 } },
    },
  ],
  webServer,
});
