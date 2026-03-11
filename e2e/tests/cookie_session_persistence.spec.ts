import { test, expect } from '@playwright/test';

// Verifies HttpOnly rt_session cookie is set on login, persists across refresh, and is cleared on logout.
// Uses UI interactions where possible; falls back to API calls for stability.

test.describe('Cookie session persistence', () => {
  test.setTimeout(120_000);

  test('login sets rt_session; refresh persists; logout clears', async ({ page, request, context }) => {
  const ui = 'http://localhost:3000';
    const api = 'http://127.0.0.1:8101';
    const email = `cookie_${Date.now()}@example.com`;
    const password = 'Str0ngP@ss!123';

    // 1) Open UI and sign up via Next.js /signup page
    await page.goto(`${ui}/signup`, { waitUntil: 'domcontentloaded' });
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill(password);
    await page.getByRole('button', { name: 'Register' }).click();
    await expect(page.getByText(/Registration successful/i)).toBeVisible({ timeout: 30000 });

    // 2) Verify email (test-only helper)
    const v = await request.post(`${api}/__test/verify-user`, { data: { username: email } });
    expect(v.ok()).toBeTruthy();

  // 3) Login via UI on root page
  await page.goto(`${ui}/`, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Login' }).click();

    // 4) Expect rt_session cookie present for API domain (127.0.0.1)
    // Playwright cookie storage is per-domain; pull cookies for API and UI origins.
    const cookiesBefore = await context.cookies();
    const rtSession = cookiesBefore.find(c => c.name === 'rt_session');
    expect(rtSession).toBeTruthy();

    // 5) Trigger a user info call to confirm session works
    const me = await request.get(`${api}/users/me`, { headers: { Cookie: `${rtSession!.name}=${rtSession!.value}` } });
    expect(me.ok()).toBeTruthy();

  // 6) Refresh UI and ensure still logged in (Sidebar shows Logout)
  await page.goto(`${ui}/resume`, { waitUntil: 'domcontentloaded' });
  const logoutBtn = page.getByRole('button', { name: 'Logout' });
    await expect(logoutBtn).toBeVisible({ timeout: 30000 });

    // 7) Click logout and verify cookie cleared
    await logoutBtn.click();
    // Give backend a moment to set clearing cookie
    await page.waitForTimeout(300);
    const cookiesAfter = await context.cookies();
    const hasRtAfter = cookiesAfter.some(c => c.name === 'rt_session' && c.value);
    expect(hasRtAfter).toBeFalsy();

    // Sidebar should show Login again
    await expect(page.getByRole('button', { name: /Login|Register/i })).toBeVisible({ timeout: 30000 });
  });
});
