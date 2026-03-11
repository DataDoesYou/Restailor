import { test, expect } from '@playwright/test';

test.describe('Trusted devices avoid duplicate entries and skip MFA on same PC', () => {
  test.setTimeout(180_000);

  test('remember device persists and does not create duplicates', async ({ page, request, context }) => {
    const ui = 'http://127.0.0.1:8501';
    const api = 'http://127.0.0.1:8101';
    const email = `td_${Date.now()}@example.com`;
    const password = 'Str0ngP@ss!123';

    // Signup via UI
    await page.goto(ui, { waitUntil: 'domcontentloaded' });
    await page.getByRole('textbox', { name: 'Email' }).first().fill(email);
    await page.locator('input[type="password"]').first().fill(password);
    await page.getByRole('button', { name: 'Register' }).click();
    await expect(page.getByText(/Registration successful/i)).toBeVisible({ timeout: 30000 });

    // Verify email (test helper)
    const v = await request.post(`${api}/__test/verify-user`, { data: { username: email } });
    expect(v.ok()).toBeTruthy();

    // Enable TOTP via API helpers to reduce UI flake
    const loginForm = new URLSearchParams();
    loginForm.set('username', email);
    loginForm.set('password', password);
    const pendingResp = await request.post(`${api}/token`, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      data: loginForm.toString(),
    });
    expect(pendingResp.ok()).toBeTruthy();
    const pendingTok = (await pendingResp.json()).access_token as string;
    const reauthTok = pendingResp.headers()['x-reauth-token'];

    const start = await request.post(`${api}/2fa/totp/start`, { headers: { Authorization: `Bearer ${pendingTok}` } });
    expect(start.ok()).toBeTruthy();
    const secret = (await start.json()).secret as string;
    const now = await request.post(`${api}/__test/totp-now`, { data: { secret, digits: 6, step: 30 } });
    expect(now.ok()).toBeTruthy();
    const code = (await now.json()).code as string;
    const conf = await request.post(`${api}/2fa/totp/confirm`, {
      data: { code },
      headers: { Authorization: `Bearer ${pendingTok}` },
    });
    expect(conf.ok()).toBeTruthy();

    // Log out in UI if logged in
    const logout = page.getByRole('button', { name: 'Logout' });
    if (await logout.isVisible().catch(() => false)) {
      await logout.click();
      await page.waitForTimeout(300);
    }

    // Perform pending login + step2 with remember via API to capture the trusted cookie value
    const form2 = new URLSearchParams();
    form2.set('username', email);
    form2.set('password', password);
    const pending3 = await request.post(`${api}/token`, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, data: form2.toString() });
    expect(pending3.ok()).toBeTruthy();
    const pendTok = (await pending3.json()).access_token as string;
    const code2 = (await (await request.post(`${api}/__test/totp-now`, { data: { secret, digits: 6, step: 30 } })).json()).code as string;
    const s2Remember = await request.post(`${api}/auth/step2`, {
      data: { code: code2, remember_device: true },
      headers: { Authorization: `Bearer ${pendTok}` },
    });
    expect(s2Remember.ok()).toBeTruthy();
    const setCookie = s2Remember.headers()['set-cookie'] || '';
    const m = /rt_trust=([^;]+)/i.exec(String(setCookie));
    expect(m).toBeTruthy();
    const rtTrust = m![1];

    // Query trusted devices count via API with a fresh token
    const pending2 = await request.post(`${api}/token`, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, data: `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}` });
    const p2 = (await pending2.json()).access_token as string;
    const code3 = (await (await request.post(`${api}/__test/totp-now`, { data: { secret, digits: 6, step: 30 } })).json()).code as string;
    const s2 = await request.post(`${api}/auth/step2`, { data: { code: code3, remember_device: false }, headers: { Authorization: `Bearer ${p2}` } });
    const bearer = (await s2.json()).access_token as string;
    const list1 = await request.get(`${api}/2fa/trusted-devices`, { headers: { Authorization: `Bearer ${bearer}` } });
    expect(list1.ok()).toBeTruthy();
    const rows1 = (await list1.json()) as any[];

    // Login again via API with the trusted cookie -> expect a full bearer (no pending_2fa)
    const pending4 = await request.post(`${api}/token`, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Cookie: `rt_trust=${rtTrust}` },
      data: form2.toString(),
    });
    expect(pending4.ok()).toBeTruthy();
    const j4 = await pending4.json();
    expect(String(j4.token_type || j4.scope || '')).toMatch(/bearer/i);

    // List devices again; count should be unchanged (no duplicate row for same PC)
  const pending5 = await request.post(`${api}/token`, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, data: form2.toString() });
  const p3 = (await pending5.json()).access_token as string;
  const code4 = (await (await request.post(`${api}/__test/totp-now`, { data: { secret, digits: 6, step: 30 } })).json()).code as string;
  const s3 = await request.post(`${api}/auth/step2`, { data: { code: code4, remember_device: false }, headers: { Authorization: `Bearer ${p3}` } });
    const bearer2 = (await s3.json()).access_token as string;
    const list2 = await request.get(`${api}/2fa/trusted-devices`, { headers: { Authorization: `Bearer ${bearer2}` } });
    expect(list2.ok()).toBeTruthy();
    const rows2 = (await list2.json()) as any[];
    expect(rows2.length).toBe(rows1.length);
  });
});
