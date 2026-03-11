import { test, expect } from '@playwright/test';

// This test triggers a verification email resend and asserts that the backend
// reports it as skipped (test mode / outbound disabled).

test('verification resend is skipped in test mode', async ({ request }) => {
  // 1) Sign up via API
  const email = `skipverify_${Date.now()}@example.com`;
  const password = 'Str0ngP@ss!123';
  const signup = await request.post('/signup', {
    data: { username: email, password },
    headers: { 'X-Client-Id': 'e2e' },
  });
  expect(signup.ok()).toBeTruthy();

  // 2) Login to get a token
  const login = await request.post('/token', {
    form: { username: email, password },
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Client-Id': 'e2e' },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token as string;
  expect(token).toBeTruthy();

  // 3) Request verification token (server should skip email send in test mode)
  const rv = await request.post('/users/request-verification-token', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(rv.ok()).toBeTruthy();
  const body = await rv.json();
  // sent === false indicates no outbound email attempted
  expect(body.sent).toBeFalsy();
});
