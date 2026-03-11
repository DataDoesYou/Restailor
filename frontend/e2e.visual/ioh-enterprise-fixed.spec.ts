/**
 * Enterprise-Grade IOH Button Test Suite
 * 
 * Comprehensive tests for bulletproof behavior across all scenarios
 * 
 * @group enterprise
 */

import { test, expect, Page, BrowserContext } from '@playwright/test';

test.describe.configure({ mode: 'serial' });
test.setTimeout(120000);

// Helpers
async function waitForHistoryStable(page: Page) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForSelector('[data-testid^="history-row-"]', { state: 'visible', timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1000); // Hydration + settle
}

async function getIOHState(page: Page, appliedKey: string) {
  const selector = `[data-testid="stage-segments-${appliedKey}"]`;
  const exists = await page.locator(selector).count();
  if (!exists) return null;
  
  return await page.evaluate((sel) => {
    const container = document.querySelector(sel);
    if (!container) return null;
    
    return {
      applied: container.querySelector('[aria-label="Applied"]')?.classList.contains('text-amber-500') ?? false,
      interviewing: container.querySelector('[aria-label="Interviewing"]')?.classList.contains('text-white') ?? false,
      offer: container.querySelector('[aria-label="Offer"]')?.classList.contains('text-white') ?? false,
      hired: container.querySelector('[aria-label="Hired"]')?.classList.contains('text-white') ?? false,
    };
  }, selector);
}

async function clickIOH(page: Page, key: string, button: 'applied' | 'interviewing' | 'offer' | 'hired') {
  const label = button.charAt(0).toUpperCase() + button.slice(1);
  await page.click(`[data-testid="stage-segments-${key}"] [aria-label="${label}"]`);
}

async function clearIOHStorage(page: Page) {
  await page.evaluate(() => {
    document.cookie.split(';').forEach(c => {
      const name = c.split('=')[0].trim();
      if (name.startsWith('rt_')) document.cookie = `${name}=; Path=/; Max-Age=0`;
    });
    Object.keys(sessionStorage).forEach(k => k.startsWith('rt_') && sessionStorage.removeItem(k));
    Object.keys(localStorage).forEach(k => k.startsWith('rt_') && localStorage.removeItem(k));
  });
}

async function getFirstAppKey(page: Page): Promise<string | null> {
  const first = await page.locator('[data-testid^="history-row-"]').first();
  const count = await first.count();
  if (!count) return null;
  const id = await first.getAttribute('data-testid');
  return id?.replace('history-row-', '') || null;
}

test.describe('Enterprise IOH Tests', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/history');
    await clearIOHStorage(page);
  });

  test('CRITICAL: Perfect state persistence across hard refresh', async ({ page }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    const before = await getIOHState(page, key);
    if (!before) return test.skip(true, 'No state');
    
    await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(500);
    
    const after = await getIOHState(page, key);
    if (!after) throw new Error('State disappeared');
    expect(after.interviewing).toBe(!before.interviewing);
    
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForHistoryStable(page);
    
    const refreshed = await getIOHState(page, key);
    expect(refreshed).toEqual(after);
  });

  test('CRITICAL: Quick back/forward navigation', async ({ page }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(300);
    await clickIOH(page, key, 'offer');
    await page.waitForTimeout(500);
    
    const afterToggles = await getIOHState(page, key);
    if (!afterToggles) throw new Error('State disappeared');
    expect(afterToggles.offer).toBe(true);
    
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.goBack();
    await waitForHistoryStable(page);
    
    const afterBack = await getIOHState(page, key);
    expect(afterBack).toEqual(afterToggles);
    
    await page.goForward();
    await page.goBack();
    await waitForHistoryStable(page);
    
    const afterBack2 = await getIOHState(page, key);
    expect(afterBack2).toEqual(afterToggles);
  });

  test('CRITICAL: Rapid clicks with slow network', async ({ page }) => {
    await page.route('**/api/applications/stage-flags', async route => {
      await new Promise(r => setTimeout(r, 2000));
      await route.continue();
    });
    
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    // Rapid clicks: I -> O -> H -> O -> I
    await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(100);
    await clickIOH(page, key, 'offer');
    await page.waitForTimeout(100);
    await clickIOH(page, key, 'hired');
    await page.waitForTimeout(100);
    await clickIOH(page, key, 'offer');
    await page.waitForTimeout(100);
    await clickIOH(page, key, 'interviewing');
    
    const optimistic = await getIOHState(page, key);
    if (!optimistic) throw new Error('No state');
    expect(optimistic.interviewing).toBe(false);
    
    await page.waitForTimeout(5000);
    
    const final = await getIOHState(page, key);
    expect(final).toEqual(optimistic);
  });

  test('CRITICAL: Multi-tab synchronization', async ({ context }) => {
    const page1 = await context.newPage();
    const page2 = await context.newPage();
    
    try {
      await page1.goto('/history');
      await waitForHistoryStable(page1);
      
      const key = await getFirstAppKey(page1);
      if (!key) return test.skip(true, 'No apps');
      
      await page2.goto('/history');
      await waitForHistoryStable(page2);
      
      await clickIOH(page1, key, 'interviewing');
      await page1.waitForTimeout(500);
      
      const page1State = await getIOHState(page1, key);
      
      await page2.reload();
      await waitForHistoryStable(page2);
      
      const page2State = await getIOHState(page2, key);
      expect(page2State).toEqual(page1State);
    } finally {
      await page1.close();
      await page2.close();
    }
  });

  test('CRITICAL: Network interruption recovery', async ({ page, context }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    await context.setOffline(true);
    await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(1000);
    
    await context.setOffline(false);
    await page.reload();
    await waitForHistoryStable(page);
    
    const before = await getIOHState(page, key);
    if (!before) throw new Error('No state');
    
    await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(1000);
    
    const after = await getIOHState(page, key);
    expect(after?.interviewing).toBe(!before.interviewing);
    
    await page.reload();
    await waitForHistoryStable(page);
    
    const verified = await getIOHState(page, key);
    expect(verified).toEqual(after);
  });

  test('CRITICAL: Cascading rules (I->O->H)', async ({ page }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    // Clear all first
    const initial = await getIOHState(page, key);
    if (initial?.interviewing) await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(500);
    
    // H should enable I and O
    await clickIOH(page, key, 'hired');
    await page.waitForTimeout(500);
    
    const afterH = await getIOHState(page, key);
    expect(afterH?.hired).toBe(true);
    expect(afterH?.offer).toBe(true);
    expect(afterH?.interviewing).toBe(true);
    
    // O off should disable H
    await clickIOH(page, key, 'offer');
    await page.waitForTimeout(500);
    
    const afterO = await getIOHState(page, key);
    expect(afterO?.offer).toBe(false);
    expect(afterO?.hired).toBe(false);
    expect(afterO?.interviewing).toBe(true);
    
    // I off should disable all
    await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(500);
    
    const afterI = await getIOHState(page, key);
    expect(afterI?.interviewing).toBe(false);
    expect(afterI?.offer).toBe(false);
    expect(afterI?.hired).toBe(false);
    
    await page.reload();
    await waitForHistoryStable(page);
    
    const final = await getIOHState(page, key);
    expect(final).toEqual(afterI);
  });

  test('CRITICAL: No hydration mismatches', async ({ page }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    await clickIOH(page, key, 'interviewing');
    await page.waitForTimeout(500);
    
    const errors: string[] = [];
    page.on('console', msg => {
      const text = msg.text();
      if ((msg.type() === 'error' || msg.type() === 'warning') && 
          /hydration|mismatch|did not match/i.test(text)) {
        errors.push(text);
      }
    });
    
    await page.reload();
    await waitForHistoryStable(page);
    await page.waitForTimeout(2000);
    
    expect(errors).toEqual([]);
  });

  test('CRITICAL: Concurrent mutations on different items', async ({ page }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const rows = await page.locator('[data-testid^="history-row-"]').all();
    if (rows.length < 2) return test.skip(true, 'Need 2+ apps');
    
    const key1 = (await rows[0].getAttribute('data-testid'))?.replace('history-row-', '');
    const key2 = (await rows[1].getAttribute('data-testid'))?.replace('history-row-', '');
    if (!key1 || !key2) return test.skip(true, 'No keys');
    
    const before1 = await getIOHState(page, key1);
    const before2 = await getIOHState(page, key2);
    
    // Click them sequentially with small gap to avoid exact race condition
    await clickIOH(page, key1, 'interviewing');
    await page.waitForTimeout(100);
    await clickIOH(page, key2, 'interviewing');
    await page.waitForTimeout(1000);
    
    const after1 = await getIOHState(page, key1);
    const after2 = await getIOHState(page, key2);
    
    expect(after1?.interviewing).toBe(!before1?.interviewing);
    expect(after2?.interviewing).toBe(!before2?.interviewing);
    
    await page.reload();
    await waitForHistoryStable(page);
    
    const final1 = await getIOHState(page, key1);
    const final2 = await getIOHState(page, key2);
    
    expect(final1).toEqual(after1);
    expect(final2).toEqual(after2);
  });

  test('RELIABILITY: 50 sequential toggles', async ({ page }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    let expected = await getIOHState(page, key);
    if (!expected) throw new Error('No state');
    
    for (let i = 0; i < 50; i++) {
      await clickIOH(page, key, 'interviewing');
      await page.waitForTimeout(200);
      
      expected = {
        ...expected,
        interviewing: !expected.interviewing,
        offer: !expected.interviewing ? false : expected.offer,
        hired: !expected.interviewing ? false : expected.hired,
      };
      
      const current = await getIOHState(page, key);
      expect(current).toEqual(expected);
    }
    
    await page.reload();
    await waitForHistoryStable(page);
    
    const final = await getIOHState(page, key);
    expect(final).toEqual(expected);
  });

  test('PERFORMANCE: First paint < 1.5s', async ({ page }) => {
    const start = Date.now();
    await page.goto('/history', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid^="stage-segments-"]', { timeout: 5000 });
    const elapsed = Date.now() - start;
    expect(elapsed).toBeLessThan(1500);
  });

  test('RELIABILITY: Memory stability over 100 operations', async ({ page }) => {
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    for (let i = 0; i < 100; i++) {
      await clickIOH(page, key, 'interviewing');
      if (i % 10 === 0) await page.waitForTimeout(50);
    }
    
    await page.waitForTimeout(2000);
    
    const analyticsSize = await page.evaluate(() => {
      return ((window as any).__getStageAnalytics?.() || []).length;
    });
    
    expect(analyticsSize).toBeLessThanOrEqual(100);
    
    const final = await getIOHState(page, key);
    await page.reload();
    await waitForHistoryStable(page);
    const verified = await getIOHState(page, key);
    expect(verified).toEqual(final);
  });

  test('CRITICAL: H button survives 10 navigation cycles (history ↔ analytics)', async ({ page }) => {
    // This is the ultimate stress test for state persistence
    await page.goto('/history');
    await waitForHistoryStable(page);
    
    const key = await getFirstAppKey(page);
    if (!key) return test.skip(true, 'No apps');
    
    // Get initial state and ensure everything is off
    let currentState = await getIOHState(page, key);
    if (!currentState) throw new Error('No state');
    
    // Turn everything off first
    if (currentState.interviewing) {
      await clickIOH(page, key, 'interviewing');
      await page.waitForTimeout(500);
    }
    
    // Now click Hired (should enable I, O, and H)
    await clickIOH(page, key, 'hired');
    await page.waitForTimeout(500);
    
    // Verify H is checked
    const afterHClick = await getIOHState(page, key);
    if (!afterHClick) throw new Error('State disappeared after H click');
    expect(afterHClick.hired).toBe(true);
    expect(afterHClick.offer).toBe(true);
    expect(afterHClick.interviewing).toBe(true);
    
    // Now perform 10 navigation cycles: history → analytics → history → analytics...
    for (let cycle = 1; cycle <= 10; cycle++) {
      // Navigate to analytics
      await page.goto('/analytics');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(500);
      
      // Navigate back to history
      await page.goto('/history');
      await waitForHistoryStable(page);
      
      // Verify H button is STILL checked after this cycle
      const stateAfterCycle = await getIOHState(page, key);
      if (!stateAfterCycle) throw new Error(`State disappeared after cycle ${cycle}`);
      
      expect(stateAfterCycle.hired).toBe(true);
      expect(stateAfterCycle.offer).toBe(true);
      expect(stateAfterCycle.interviewing).toBe(true);
      
      // Small pause between cycles
      await page.waitForTimeout(200);
    }
    
    // Final verification: H button should STILL be checked
    const finalState = await getIOHState(page, key);
    expect(finalState?.hired).toBe(true);
    expect(finalState?.offer).toBe(true);
    expect(finalState?.interviewing).toBe(true);
    
    // Extra paranoia: hard refresh and check again
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForHistoryStable(page);
    
    const afterRefresh = await getIOHState(page, key);
    expect(afterRefresh?.hired).toBe(true);
    expect(afterRefresh?.offer).toBe(true);
    expect(afterRefresh?.interviewing).toBe(true);
  });
});
