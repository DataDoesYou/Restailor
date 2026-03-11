/**
 * Environment-aware logging utility
 * 
 * Only logs in development mode by default.
 * Can be overridden with NEXT_PUBLIC_DEBUG_LOGS=1 for production debugging.
 */

const IS_DEV = process.env.NODE_ENV === 'development';
const DEBUG_LOGS = process.env.NEXT_PUBLIC_DEBUG_LOGS === '1';

export const logger = {
  /**
   * Debug logs - only in development or when explicitly enabled
   */
  debug: (...args: any[]) => {
    if (IS_DEV || DEBUG_LOGS) {
      console.log(...args);
    }
  },

  /**
   * Info logs - only in development or when explicitly enabled
   */
  info: (...args: any[]) => {
    if (IS_DEV || DEBUG_LOGS) {
      console.log(...args);
    }
  },

  /**
   * Warnings - always shown (but can be filtered in browser devtools)
   */
  warn: (...args: any[]) => {
    console.warn(...args);
  },

  /**
   * Errors - always shown
   */
  error: (...args: any[]) => {
    console.error(...args);
  },

  /**
   * Force log - always shown regardless of environment
   */
  force: (...args: any[]) => {
    console.log(...args);
  }
};

/**
 * Check if debug logs are enabled
 */
export function isDebugEnabled(): boolean {
  return IS_DEV || DEBUG_LOGS;
}
