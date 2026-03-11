import { request, chromium, FullConfig } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// Creates a test user (if not exists), logs in, and saves browser storage state including
// cookies plus localStorage __rt_access_token so UI is authenticated.

async function ensureSignupAndLogin(apiBase: string, email: string, password: string) {
  const context = await request.newContext({ baseURL: apiBase });
  // Attempt signup (idempotent-ish: if already exists, ignore 400)
  const signup = await context.post('/signup', { data: { username: email, password } , headers: { 'X-Client-Id': 'test-client' }});
  if (signup.status() !== 200 && signup.status() !== 400) {
    throw new Error(`Signup failed: ${signup.status()} ${await signup.text()}`);
  }
  // Mark verified (test helper enabled under E2E_TEST_MODE)
  await context.post('/__test/verify-user', { data: { username: email } });
  // Login to obtain bearer token (also sets rt_session cookie via response if implemented)
  const login = await context.post('/token', { form: { username: email, password }, headers: { 'X-Client-Id': 'test-client' } });
  if (login.status() !== 200) throw new Error(`Login failed: ${login.status()} ${await login.text()}`);
  const data = await login.json();
  const tokenType = String(data?.token_type || '').toLowerCase();
  const access = String(data?.access_token || '');
  if (tokenType !== 'bearer' || !access) throw new Error('Missing bearer token in /token response');

  // Create a temporary page-like storageState by visiting a blank page on Next.js origin to set localStorage
  // We can't set localStorage via request context; instead write a storageState file for cookies only,
  // then Playwright test can inject localStorage before navigation using a fixture (or we persist via JSON file).
  // Simpler: write a JSON file with token for a beforeEach script to read. For now we rely on cookie session presence.
  // But to ensure API header-based auth fallback works, we store token in a file consumed by a test fixture.
  const authDir = path.join(__dirname, '.auth');
  fs.mkdirSync(authDir, { recursive: true });
  fs.writeFileSync(path.join(authDir, 'bearer.json'), JSON.stringify({ access }, null, 2));

  await context.dispose();
  // Launch a headedless browser to perform UI login so Next.js server sees cookie on SSR pages requiring session
  const browser = await chromium.launch();
  const uiCtx = await browser.newContext();
  const page = await uiCtx.newPage();
  await page.goto('http://localhost:3000/');
  await page.fill('input[name="username"], input[type="email"], [placeholder="Email"]', email).catch(()=>{});
  await page.fill('input[type="password"], [placeholder="Password"]', password).catch(()=>{});
  // Some forms use role button Login
  const loginButtons = page.getByRole('button', { name: /Login/i });
  const count = await loginButtons.count();
  if (count > 0) {
    await loginButtons.nth(0).click();
  } else {
    await page.press('body', 'Enter');
  }
  // Wait a moment for cookie to set
  await page.waitForTimeout(500);
  // Save storage state including cookies/localStorage for reuse by tests
  try {
    const statePath = path.join(__dirname, '.auth', 'state.json');
    await uiCtx.storageState({ path: statePath });
  } catch {}
  await browser.close();
}

async function globalSetup(config: FullConfig) {
  const baseURL = process.env.PW_API_BASE_URL || 'http://127.0.0.1:8101';
  const email = process.env.E2E_USER_EMAIL || 'e2e_user@example.com';
  const password = process.env.E2E_USER_PASSWORD || 'Str0ngP@ss!123';
  await ensureSignupAndLogin(baseURL, email, password);
}

export default globalSetup;
