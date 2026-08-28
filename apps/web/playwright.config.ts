import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:5173', channel: process.env.CI ? undefined : 'chrome', viewport: { width: 1366, height: 768 }, trace: 'retain-on-failure' },
  webServer: [
    {
      command: 'python -m uvicorn recourse.main:app --host 127.0.0.1 --port 8000',
      cwd: '../..',
      env: {
        PYTHONPATH: 'apps/api/src',
        DATABASE_URL: 'sqlite:///./playwright.db',
        OPENROUTER_ENABLED: 'false',
        RAZORPAY_ENABLED: 'false',
      },
      url: 'http://127.0.0.1:8000/health/live',
      reuseExistingServer: true,
    },
    { command: 'npx vite --host 127.0.0.1', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
  ],
})
