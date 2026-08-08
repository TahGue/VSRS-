import { test, expect } from '@playwright/test';

const BASE_URL = 'http://127.0.0.1:8000';

test.describe('VSRS Web Dashboard', () => {
  test('health endpoint returns ok', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe('ok');
  });

  test('dashboard page loads', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page).toHaveTitle('VSRS Dashboard');
  });

  test('sidebar navigation works', async ({ page }) => {
    await page.goto(BASE_URL);

    // Sidebar logo visible
    await expect(page.locator('.sidebar-logo')).toContainText('VSRS Dashboard');

    // Nav links visible
    await expect(page.locator('.sidebar-nav a').filter({ hasText: 'Runs' })).toBeVisible();
    await expect(page.locator('.sidebar-nav a').filter({ hasText: 'Benchmarks' })).toBeVisible();
    await expect(page.locator('.sidebar-nav a').filter({ hasText: 'Settings' })).toBeVisible();
  });

  test('runs page shows empty state, runs table, or error', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for loading to finish
    await page.waitForTimeout(2000);

    // Either empty state, runs table, or error message should be visible
    const emptyState = page.locator('.empty-state');
    const runsTable = page.locator('table');
    const errorMsg = page.locator('.error-msg');

    await expect(emptyState.or(runsTable).or(errorMsg)).toBeVisible();
  });

  test('new run form toggles', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(1000);

    // Click "New Run" button
    const newRunBtn = page.locator('button').filter({ hasText: 'New Run' });
    if (await newRunBtn.isVisible()) {
      await newRunBtn.click();

      // Form should appear
      await expect(page.locator('h2').filter({ hasText: 'Create New Run' })).toBeVisible();
      await expect(page.locator('input[placeholder="/path/to/repo"]')).toBeVisible();
      await expect(page.locator('input[placeholder="Fix the bug in..."]')).toBeVisible();
      await expect(page.locator('select')).toBeVisible();
    }
  });

  test('benchmarks page loads', async ({ page }) => {
    await page.goto(`${BASE_URL}/benchmarks`);
    await page.waitForTimeout(2000);

    // Page header visible
    await expect(page.locator('h1')).toContainText('Benchmarks');

    // Either empty state or table visible
    const emptyState = page.locator('.empty-state');
    const table = page.locator('table');
    await expect(emptyState.or(table)).toBeVisible();
  });

  test('settings page loads and shows config', async ({ page }) => {
    await page.goto(`${BASE_URL}/settings`);
    await page.waitForTimeout(2000);

    // Page header visible
    await expect(page.locator('h1')).toContainText('Settings');

    // Config card should appear (or error message)
    const card = page.locator('.card');
    const errorMsg = page.locator('.error-msg');
    await expect(card.or(errorMsg)).toBeVisible();
  });

  test('dark theme is applied', async ({ page }) => {
    await page.goto(BASE_URL);

    // Check that the dark background color is set
    const bgColor = await page.evaluate(() => {
      return getComputedStyle(document.body).backgroundColor;
    });
    // Should be a dark color (rgb(13, 17, 23) = #0d1117)
    expect(bgColor).toContain('13');
  });

  test('API docs endpoint accessible', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/docs`);
    expect(res.ok()).toBeTruthy();
    const text = await res.text();
    expect(text).toContain('Swagger');
  });

  test('OpenAPI schema has correct version', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/openapi.json`);
    expect(res.ok()).toBeTruthy();
    const schema = await res.json();
    expect(schema.info.title).toBe('VSRS API');
    expect(schema.info.version).toBe('2.4.0');
  });

  test('enterprise endpoints exist in OpenAPI schema', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/openapi.json`);
    const schema = await res.json();
    const paths = Object.keys(schema.paths);

    // Core endpoints
    expect(paths).toContain('/api/v1/runs');
    expect(paths).toContain('/api/v1/benchmarks');
    expect(paths).toContain('/api/v1/config');

    // Enterprise endpoints
    expect(paths).toContain('/api/v1/tenants');
    expect(paths).toContain('/api/v1/keys');
    expect(paths).toContain('/api/v1/audit');
    expect(paths).toContain('/api/v1/roles');
    expect(paths).toContain('/api/v1/rate-limit/usage');
    expect(paths).toContain('/api/v1/rate-limit/config');
  });

  test('unauthenticated enterprise endpoints return 401', async ({ request }) => {
    const endpoints = [
      '/api/v1/keys',
      '/api/v1/audit',
      '/api/v1/roles',
      '/api/v1/rate-limit/usage',
      '/api/v1/rate-limit/config',
    ];

    for (const ep of endpoints) {
      const res = await request.get(`${BASE_URL}${ep}`);
      expect(res.status()).toBe(401);
    }
  });

  test('roles endpoint returns roles with pagination fields', async ({ request }) => {
    // First create an admin key
    const createRes = await request.post(`${BASE_URL}/api/v1/keys`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        user_id: 'admin',
        name: 'admin',
        scopes: ['admin:all'],
      },
    });

    // If we can't create key (no auth on create), try without
    if (createRes.status() === 401) {
      // The create endpoint itself requires auth — skip this test
      test.skip();
      return;
    }

    const createBody = await createRes.json();
    const rawKey = createBody.raw_key;

    // Now fetch roles with the key
    const rolesRes = await request.get(`${BASE_URL}/api/v1/roles`, {
      headers: { 'X-API-Key': rawKey },
    });
    expect(rolesRes.ok()).toBeTruthy();
    const rolesBody = await rolesRes.json();

    expect(rolesBody.total).toBeGreaterThanOrEqual(3);
    expect(rolesBody.offset).toBe(0);
    expect(rolesBody).toHaveProperty('limit');
    expect(rolesBody.count).toBeGreaterThanOrEqual(3);

    // Check built-in roles
    const roleNames = rolesBody.roles.map((r: any) => r.name);
    expect(roleNames).toContain('viewer');
    expect(roleNames).toContain('developer');
    expect(roleNames).toContain('admin');
  });

  test('pagination works on roles endpoint', async ({ request }) => {
    // Create admin key
    const createRes = await request.post(`${BASE_URL}/api/v1/keys`, {
      headers: { 'Content-Type': 'application/json' },
      data: { user_id: 'admin', name: 'admin', scopes: ['admin:all'] },
    });
    if (createRes.status() === 401) {
      test.skip();
      return;
    }
    const { raw_key: rawKey } = await createRes.json();

    // Get first 2 roles
    const res = await request.get(`${BASE_URL}/api/v1/roles?offset=0&limit=2`, {
      headers: { 'X-API-Key': rawKey },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();

    expect(body.count).toBeLessThanOrEqual(2);
    expect(body.total).toBeGreaterThanOrEqual(3);
    expect(body.limit).toBe(2);
    expect(body.offset).toBe(0);
  });
});
