// Shared Playwright test setup shim.
// Re-export test and expect so specs can import from './auth.setup'.
// This also gives us a central place to add fixtures later if needed.
import { test as base, expect } from '@playwright/test';

// You can extend fixtures here if needed in the future, e.g. authenticated context, etc.
// For now, keep it as a thin wrapper to avoid undefined imports in specs.
const test = base;

export { test, expect };

