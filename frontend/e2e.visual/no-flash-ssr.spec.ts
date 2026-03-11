import { test, expect } from '@playwright/test';

// e2e: assert that the SSR HTML already shows the authenticated sidebar (no login block) when a token cookie is present.
// test('SSR: sidebar shows Account (no login flash) when auth cookie is present', async ({ browser, baseURL }) => {
//   const url = baseURL!;
//   // Create an auth context that sets the cookie before navigation (no JS needed later)
//   const ctx = await browser.newContext({ baseURL: url });
//   await ctx.addCookies([{ name: 'rt_access', value: 'PLAYWRIGHT_FAKE_TOKEN', url }]);
//   const page = await ctx.newPage();
//   // API requests are handled by the mock API server via NEXT_PUBLIC_API_BASE_URL

//   // Disable JS to validate the pure SSR output
//   const noJs = await browser.newContext({ baseURL: url, javaScriptEnabled: false, storageState: await ctx.storageState() });
//   const p2 = await noJs.newPage();
//   await p2.goto('/');
//   await expect(p2.locator('text=Account')).toBeVisible();
//   await expect(p2.locator('text=Login / Register')).toHaveCount(0);
//   await noJs.close();
//   await ctx.close();
// });
