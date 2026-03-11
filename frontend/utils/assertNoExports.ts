/**
 * Production guard: Assert no export helpers exist on window object
 * 
 * This module prevents accidental data leakage by ensuring no debug export
 * functions are available in production builds. Tree-shaking will eliminate
 * this code in development builds.
 */

/**
 * Check for forbidden export helpers on window object.
 * Throws in production if any are found.
 */
export function assertNoExports(): void {
  // No-op in development
  if (process.env.NODE_ENV !== 'production') {
    return;
  }

  if (typeof window === 'undefined') {
    return;
  }

  const forbiddenKeys = Object.keys(window).filter(key => 
    key.startsWith('__export') || 
    key.startsWith('__EXPORT') ||
    key === 'exportCsv' ||
    key === 'exportCSV' ||
    key === 'toCSV' ||
    key === 'downloadCSV'
  );

  if (forbiddenKeys.length > 0) {
    const error = new Error(
      `[SECURITY] Forbidden export helpers detected in production: ${forbiddenKeys.join(', ')}`
    );
    
    // Log to console for visibility
    console.error(error.message);
    
    // Throw to fail fast
    throw error;
  }
}

/**
 * Auto-run assertion in production builds
 * Tree-shaking will remove this block in development
 */
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'production') {
  // Run immediately
  assertNoExports();
  
  // Also run after DOMContentLoaded to catch lazy-loaded scripts
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', assertNoExports);
  } else {
    // DOM already loaded, run after a short delay
    setTimeout(assertNoExports, 100);
  }
}
