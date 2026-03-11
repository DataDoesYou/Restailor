/**
 * Proactive Token Refresh
 * 
 * Automatically refreshes access tokens in the background before they expire.
 * This keeps users logged in indefinitely as long as:
 * 1. The browser tab remains open
 * 2. The refresh token is still valid (7-30 days)
 * 
 * The timer refreshes at 75% of the access token lifetime to ensure
 * the token is always fresh before expiration.
 */
import { logger } from './logger';

// Access token lifetime from backend (should match security.py)
// Default: 60 minutes (can be overridden via NEXT_PUBLIC_ACCESS_TOKEN_MINUTES env var)
const ACCESS_TOKEN_MINUTES = parseInt(process.env.NEXT_PUBLIC_ACCESS_TOKEN_MINUTES || '60', 10);
const REFRESH_INTERVAL_MS = ACCESS_TOKEN_MINUTES * 60 * 1000 * 0.75; // Refresh at 75% of lifetime (45 min for 60 min token)

let refreshTimer: NodeJS.Timeout | null = null;
let isRefreshing = false;

/**
 * Perform a background token refresh
 */
async function backgroundRefresh(): Promise<void> {
  logger.debug('[TokenRefresh] ⏰ Timer fired! Starting refresh...');
  
  if (isRefreshing) {
    logger.debug('[TokenRefresh] Already refreshing, skipping');
    return;
  }

  isRefreshing = true;
  
  try {
    logger.debug('[TokenRefresh] Starting proactive token refresh');
    
    // Log current cookies (but not values, since HttpOnly cookies won't be visible)
    logger.debug('[TokenRefresh] document.cookie available:', document.cookie ? 'yes (but HttpOnly cookies hidden)' : 'no cookies visible');
    
    // Use relative /api path to go through Next.js proxy (ensures cookies work on localhost)
    // In production, this will use the full API URL if NEXT_PUBLIC_API_BASE_URL is set
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
    logger.debug('[TokenRefresh] Using API base:', baseUrl);
    
    const refreshUrl = `${baseUrl}/auth/refresh`;
    logger.debug('[TokenRefresh] Calling refresh endpoint:', refreshUrl);
    
    const res = await fetch(refreshUrl, {
      method: 'POST',
      credentials: 'include', // Send HttpOnly cookies (rt_refresh)
      headers: { 'Content-Type': 'application/json' },
    });
    
    logger.debug('[TokenRefresh] Refresh response status:', res.status);
    logger.debug('[TokenRefresh] Response has Set-Cookie header:', res.headers.has('set-cookie'));
    
    if (res.ok) {
      logger.debug('[TokenRefresh] ✅ Token refresh successfully');
      // Update local storage heuristic to keep "likely logged in" state fresh
      try {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem("__rt_auth_expect_true", String(Date.now()));
        }
      } catch (e) {
        // ignore
      }

      // New cookies have been set automatically via Set-Cookie headers
      logger.debug('[TokenRefresh] New cookies should now be set by the browser');
      // Schedule next refresh
      scheduleNextRefresh();
    } else {
      logger.warn('[TokenRefresh] ❌ Token refresh failed:', res.status);
      const body = await res.text();
      logger.warn('[TokenRefresh] Response body:', body);
      
      // Only stop the timer if it's a terminal auth error (401/403)
      // For 5xx server errors or rate limits, we should keep trying
      if (res.status === 401 || res.status === 403) {
        logger.warn('[TokenRefresh] Terminal auth error, stopping refresh timer');
        stopTokenRefresh();
      } else {
        logger.warn('[TokenRefresh] Transient error, scheduling retry');
        scheduleNextRefresh();
      }
    }
  } catch (err) {
    console.error('[TokenRefresh] Error during refresh:', err);
    // Network error - try again next cycle
    scheduleNextRefresh();
  } finally {
    isRefreshing = false;
  }
}

/**
 * Schedule the next token refresh
 */
function scheduleNextRefresh(): void {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
  }
  
  const intervalSeconds = Math.round(REFRESH_INTERVAL_MS / 1000);
  const nextRefreshTime = new Date(Date.now() + REFRESH_INTERVAL_MS);
  logger.debug(`[TokenRefresh] ⏰ Next refresh in ${intervalSeconds}s (at ${nextRefreshTime.toLocaleTimeString()})`);
  
  refreshTimer = setTimeout(() => {
    backgroundRefresh();
  }, REFRESH_INTERVAL_MS);
}

/**
 * Start the automatic token refresh timer
 * Call this after successful login
 */
export function startTokenRefresh(): void {
  // Prevent double-start (if timer already running, don't restart)
  if (refreshTimer) {
    logger.debug('[TokenRefresh] Timer already running, skipping start');
    return;
  }
  
  logger.debug('[TokenRefresh] Starting automatic token refresh');
  scheduleNextRefresh();
}

/**
 * Stop the automatic token refresh timer
 * Call this on logout
 */
export function stopTokenRefresh(): void {
  logger.debug('[TokenRefresh] Stopping automatic token refresh');
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

/**
 * Check if user is likely authenticated based on localStorage flag.
 * Note: We cannot check document.cookie for rt_session/rt_refresh because they are HttpOnly.
 */
function likelyAuthenticated(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    // Check localStorage flag set by LoginClient after successful auth
    const expectAuth = localStorage.getItem("__rt_auth_expect_true");
    if (expectAuth) {
      const ts = parseInt(expectAuth, 10);
      // Valid for 30 days after login (matches refresh token lifetime)
      if (!isNaN(ts) && (Date.now() - ts) < 2592000000) return true;
    }
    // Also check if we've previously confirmed auth in this session
    return !!(window as any).__rt_was_logged_in;
  } catch {
    return false;
  }
}

/**
 * Initialize token refresh on page load if user is logged in
 */
export function initTokenRefresh(): void {
  if (typeof window === 'undefined') return;
  
  logger.debug('[TokenRefresh] Initializing...');
  
  // Check if user appears to be logged in
  // Note: We cannot check document.cookie for rt_session/rt_refresh because they are HttpOnly cookies
  const isAuthenticated = likelyAuthenticated();
  
  logger.debug('[TokenRefresh] Auth check:', { 
    isAuthenticated,
    hasLocalStorageFlag: !!localStorage.getItem("__rt_auth_expect_true"),
    wasLoggedIn: !!(window as any).__rt_was_logged_in
  });
  
  if (isAuthenticated) {
    logger.debug('[TokenRefresh] User appears logged in, starting refresh timer');
    startTokenRefresh();
  } else {
    logger.debug('[TokenRefresh] No auth indicators found, waiting for login');
  }
  
  // Listen for login/logout events
  window.addEventListener('rt-auth', (e: Event) => {
    const event = e as CustomEvent;
    const state = event.detail?.state;
    
    logger.debug('[TokenRefresh] rt-auth event:', state);
    
    if (state === 'logged-in') {
      startTokenRefresh();
    } else if (state === 'logged-out') {
      stopTokenRefresh();
    }
  });
}

// Note: Do NOT auto-initialize here - let TokenRefreshInitializer component handle it
// This ensures proper React lifecycle and prevents double initialization
