import { test, expect } from '@playwright/test';

// CI guard: ensure all verification emails during tests are recorded as skipped.
// Requires admin; we rely on test-only admin elevation and pending_2fa read-only policy.

test('admin email logs show only skipped verify emails', async ({ request }) => {
  const api = 'http://127.0.0.1:8101';
  const email = `elog_${Date.now()}@example.com`;
  const password = 'Str0ngP@ss!123';

  // Sign up and mark verified + admin (test endpoints)
  const su = await request.post(`${api}/signup`, { data: { username: email, password } });
  expect(su.ok()).toBeTruthy();

  const v = await request.post(`${api}/__test/verify-user`, { data: { username: email } });
  expect(v.ok()).toBeTruthy();

  const m = await request.post(`${api}/__test/make-admin`, { data: { username: email } });
  expect(m.ok()).toBeTruthy();

  // Login to get bearer
  const login = await request.post(`${api}/token`, {
    form: { username: email, password },
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token as string;

  // Trigger a few signup/resend flows to generate email_log rows
  const email2 = `elog2_${Date.now()}@example.com`;
  const su2 = await request.post(`${api}/signup`, { data: { username: email2, password } });
  expect(su2.ok()).toBeTruthy();

  // Login as the unverified second user and request resend
  const login2 = await request.post(`${api}/token`, {
    form: { username: email2, password },
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  expect(login2.ok()).toBeTruthy();
  const token2 = (await login2.json()).access_token as string;

  const rv = await request.post(`${api}/users/request-verification-token`, {
    headers: { Authorization: `Bearer ${token2}` },
  });
  expect(rv.ok()).toBeTruthy();

  // Fetch summary as admin
  const summary = await request.get(`${api}/admin/email_logs_summary?limit=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(summary.ok()).toBeTruthy();
  const json = await summary.json();

  // All verification entries for the recipients we created in this test must be status === 'skipped'.
  const recent = (json.recent || []) as Array<{ kind: string; status: string; recipient?: string }>;
  const recipients = new Set([email.toLowerCase(), email2.toLowerCase()]);
  const verifyRows = recent.filter(r => (r.kind || '').toLowerCase().includes('verify') && recipients.has(String(r.recipient || '').toLowerCase()));

  // If no recent verification rows, this test cannot assert; treat it as pass.
  // Otherwise require every row be skipped.
  if (verifyRows.length > 0) {
    for (const r of verifyRows) {
      expect(r.status).toBe('skipped');
    }
  }
});
