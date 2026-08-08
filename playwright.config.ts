import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'python -m uvicorn vsrs.api.app:app --host 127.0.0.1 --port 8000',
    port: 8000,
    timeout: 15000,
    reuseExistingServer: true,
    cwd: '.',
  },
});
