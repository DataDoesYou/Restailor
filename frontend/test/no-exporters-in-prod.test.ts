/**
 * Security Test: No Exporters in Production Build
 * 
 * This test ensures that production builds do not contain any forbidden
 * export/debug code that could leak analytics data to the browser.
 * 
 * Run this test AFTER building the app:
 *   npm run build
 *   npm test -- no-exporters-in-prod.test.ts
 */

import { describe, it, expect } from 'vitest';
import { existsSync } from 'fs';
import { execSync } from 'child_process';
import path from 'path';

describe('Production Build Security', () => {
  const buildDir = path.join(process.cwd(), '.next');
  const staticDir = path.join(buildDir, 'static');

  it('should have .next build directory', () => {
    expect(existsSync(buildDir)).toBe(true);
  });

  it('should not contain __exportStageAnalytics in built artifacts', () => {
    if (!existsSync(staticDir)) {
      // Build hasn't been run yet - skip test
      console.warn('⚠️  .next/static not found - run `npm run build` first');
      return;
    }

    try {
      // Use grep to search for forbidden patterns in all JS files
      // We expect this to throw (exit code 1) when no matches are found
      const result = execSync(
        `grep -r "__exportStageAnalytics" "${staticDir}" || exit 0`,
        { encoding: 'utf-8', shell: 'bash' }
      );

      // If we found any matches, fail the test
      if (result.trim().length > 0) {
        throw new Error(
          `❌ Found forbidden pattern "__exportStageAnalytics" in production build:\n${result}`
        );
      }
    } catch (error: any) {
      // grep returns exit code 1 when no matches found, which throws in execSync
      // This is actually what we want - no matches means test passes
      if (error.stdout && error.stdout.trim().length > 0) {
        throw new Error(
          `❌ Found forbidden pattern "__exportStageAnalytics" in production build:\n${error.stdout}`
        );
      }
      // No matches found - test passes
    }
  });

  it('should not contain exportCsv in built artifacts', () => {
    if (!existsSync(staticDir)) {
      console.warn('⚠️  .next/static not found - run `npm run build` first');
      return;
    }

    try {
      const result = execSync(
        `grep -ri "exportCsv\\|exportCSV\\|downloadCSV" "${staticDir}" || exit 0`,
        { encoding: 'utf-8', shell: 'bash' }
      );

      if (result.trim().length > 0) {
        throw new Error(
          `❌ Found forbidden export patterns in production build:\n${result}`
        );
      }
    } catch (error: any) {
      if (error.stdout && error.stdout.trim().length > 0) {
        throw new Error(
          `❌ Found forbidden export patterns in production build:\n${error.stdout}`
        );
      }
    }
  });

  it('should not contain getAnalyticsExportUrl in built artifacts', () => {
    if (!existsSync(staticDir)) {
      console.warn('⚠️  .next/static not found - run `npm run build` first');
      return;
    }

    try {
      const result = execSync(
        `grep -r "getAnalyticsExportUrl" "${staticDir}" || exit 0`,
        { encoding: 'utf-8', shell: 'bash' }
      );

      if (result.trim().length > 0) {
        throw new Error(
          `❌ Found "getAnalyticsExportUrl" in production build:\n${result}`
        );
      }
    } catch (error: any) {
      if (error.stdout && error.stdout.trim().length > 0) {
        throw new Error(
          `❌ Found "getAnalyticsExportUrl" in production build:\n${error.stdout}`
        );
      }
    }
  });

  it('should not contain /analytics/export.csv endpoint in built artifacts', () => {
    if (!existsSync(staticDir)) {
      console.warn('⚠️  .next/static not found - run `npm run build` first');
      return;
    }

    try {
      const result = execSync(
        `grep -r "/analytics/export\\.csv" "${staticDir}" || exit 0`,
        { encoding: 'utf-8', shell: 'bash' }
      );

      if (result.trim().length > 0) {
        throw new Error(
          `❌ Found "/analytics/export.csv" endpoint in production build:\n${result}`
        );
      }
    } catch (error: any) {
      if (error.stdout && error.stdout.trim().length > 0) {
        throw new Error(
          `❌ Found "/analytics/export.csv" endpoint in production build:\n${error.stdout}`
        );
      }
    }
  });
});
