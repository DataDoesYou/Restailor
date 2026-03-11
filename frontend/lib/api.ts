import { logger } from './logger';

export type HttpMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";

export interface ApiOptions {
  headers?: Record<string, string>;
  query?: Record<string, string | number | boolean | null | undefined>;
  xClientId?: string; // provided by caller
  xJobToken?: string; // per-job
  signal?: AbortSignal;
  skipRefresh?: boolean; // internal flag to prevent infinite refresh loops
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    super(msg);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// Lightweight global auth lock to suppress request storms after the first
// definitive authenticated 401 (session expiry). We purposely keep this
// module-local (not React state) so any caller using the api helper benefits
// automatically without wiring extra context.
// Window flags (for debugging):
//   window.__rt_was_logged_in  -> we have seen a successful /users/me (or other 2xx)
//   window.__rt_auth_locked    -> we've emitted a logout event and will short‑circuit further calls
//   window.__rt_last_401_ts    -> timestamp of last handled 401 for throttling
// The lock reduces redundant network traffic & noisy console errors when a tab
// continues polling after logout / expiry.
let authLocked = false;
// Track whether we've positively confirmed an authenticated session this tab.
// We purposefully keep this separate from was_logged_in (which persists even after
// expiry) so we can decide whether to call certain protected endpoints at all
// on first render. This prevents the "never-logged-in" console from showing an
// initial burst of 401s for balance, 2fa state, etc.
let authEstablished = false; // becomes true after first successful /users/me

export function setAuthEstablished(value: boolean) {
  authEstablished = value;
  if (typeof window !== "undefined" && value) {
    (window as any).__rt_was_logged_in = true;
  }
}

// ---------------- Auth Probe Single-Flight & Gating -----------------
// We want at most one in-flight /users/me network request, only when there is
// a strong heuristic that a session might actually exist. Otherwise we defer
// the probe until first user interaction to keep the logged-out console clean
// and eliminate unnecessary 401s (perf + minor side‑channel reduction).
let meProbePromise: Promise<any> | null = null;
let meProbeCache: { value: any; ts: number; ok: boolean } | null = null;
const ME_PROBE_TTL_MS = 2500; // short cache to collapse bursts
let meInteractionListenersInstalled = false;
let meDeferredTriggered = false; // set true once interaction triggers a probe

function likelyHasSessionCookie(): boolean {
  if (typeof document === "undefined") return false;
  try {
    // Check if we just logged in (set by LoginClient after successful auth)
    if (typeof localStorage !== "undefined") {
      const expectAuth = localStorage.getItem("__rt_auth_expect_true");
      if (expectAuth) {
        const ts = parseInt(expectAuth, 10);
        // Valid for 30 days (matches refresh token lifetime)
        if (!isNaN(ts) && (Date.now() - ts) < 2592000000) return true;
      }
    }
    // Fallback: check for session cookies
    const raw = document.cookie || "";
    if (!raw) return false;
    // Broad patterns for common session cookie names. Adjust if backend changes.
    return /(session|auth|sid|rt_session)/i.test(raw);
  } catch { return false; }
}

function installDeferredProbeListeners() {
  if (meInteractionListenersInstalled || typeof window === "undefined") return;
  meInteractionListenersInstalled = true;
  const trigger = () => {
    if (meDeferredTriggered) return; // only once
    meDeferredTriggered = true;
    try { window.removeEventListener("click", trigger); window.removeEventListener("keydown", trigger); window.removeEventListener("focus", trigger, true); } catch {}
    // Only run probe if still not established & not locked
    if (!authEstablished && !authLocked) {
      // Fire and intentionally ignore errors (components will retry manually as needed)
      meProbe(true).catch(() => {});
    }
  };
  window.addEventListener("click", trigger, { passive: true });
  window.addEventListener("keydown", trigger, { passive: true });
  window.addEventListener("focus", trigger, true);
}

async function meProbe(forceNetwork: boolean): Promise<any> {
  // Return cached result if fresh
  if (!forceNetwork && meProbeCache && (Date.now() - meProbeCache.ts) < ME_PROBE_TTL_MS) {
    if (meProbeCache.ok) return meProbeCache.value;
    throw meProbeCache.value; // value holds error
  }
  if (meProbePromise) return meProbePromise;
  meProbePromise = (async () => {
    try {
      const val = await requestJSON<any>("GET", "/users/me", undefined, undefined);
      meProbeCache = { value: val, ts: Date.now(), ok: true };
      return val;
    } catch (e) {
      meProbeCache = { value: e, ts: Date.now(), ok: false };
      throw e;
    } finally {
      meProbePromise = null;
    }
  })();
  return meProbePromise;
}

function isAuthLocked(): boolean {
  if (authLocked) return true;
  if (typeof window !== "undefined") {
    // sync with window flag if set elsewhere (e.g. another bundle instance)
    // @ts-ignore
    authLocked = !!(window as any).__rt_auth_locked;
  }
  return authLocked;
}

function lockAuth(reason: string) {
  if (authLocked) return;
  authLocked = true;
  try {
    if (typeof window !== "undefined") {
      // @ts-ignore
      (window as any).__rt_auth_locked = true;
      
      // CRITICAL: Clear all sensitive data SYNCHRONOUSLY before navigation
      // PII scope: resume/jd inputs + judge ephemeral cache (outputs now managed via database snapshots)
      const keysToRemove = [
        '__rt_judge_cache_ephemeral',
        '__rt_resume_text', '__rt_jd_text',
        '__rt_resume_ts', '__rt_jd_ts'
      ];
      for (const key of keysToRemove) {
        try { localStorage.removeItem(key); } catch {}
      }
      
      // Clear auth tokens
      try { localStorage.removeItem('__rt_access_token'); } catch {}
      try { localStorage.removeItem('__rt_ephemeral_token'); } catch {}
      
      // Double-verify critical PII is cleared by setting to empty strings
      try {
        localStorage.setItem('__rt_resume_text', '');
        localStorage.setItem('__rt_jd_text', '');
        localStorage.setItem('__rt_resume_ts', '0');
        localStorage.setItem('__rt_jd_ts', '0');
      } catch {}
      
      // Call /logout endpoint to clear server-side encrypted data (best-effort, don't wait)
      try {
        const base = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "";
        if (base) {
          fetch(`${base}/logout`, { 
            method: 'POST', 
            credentials: 'include',
            keepalive: true // Ensure request completes even if page unloads
          }).catch(() => {}); // Fire and forget
        }
      } catch {}
      
      // Dispatch rt-inputs event to immediately clear any mounted input components
      try {
        window.dispatchEvent(new CustomEvent("rt-inputs", { 
          detail: { resumeText: "", jdText: "", rTs: 0, jTs: 0 } 
        }));
      } catch {}
      
      // Dispatch auth event for any remaining listeners (outputs, etc.)
      window.dispatchEvent(new CustomEvent("rt-auth", { detail: { state: "logged-out", reason } }));
      
      // Navigate to root page for privacy - prevents sensitive data from remaining visible
      // Increased timeout to ensure localStorage writes complete
      setTimeout(() => {
        try {
          console.warn('[lockAuth] Redirecting to / due to logout. Reason:', reason);
          window.location.href = "/";
        } catch (e) {
          console.error('[lockAuth] Failed to redirect:', e);
        }
      }, 100);
    }
  } catch {}
}

function getBaseUrl(): string {
  const base =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "";
  if (!base) {
    throw new Error("NEXT_PUBLIC_API_URL (or NEXT_PUBLIC_API_BASE_URL) is not set");
  }
  return base.replace(/\/$/, "");
}

function buildUrl(path: string, query?: ApiOptions["query"]): string {
  const isAbsolute = /^https?:\/\//i.test(path);
  const base = isAbsolute ? "" : getBaseUrl();
  const url = new URL(isAbsolute ? path : `${base}${path.startsWith("/") ? path : "/" + path}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue;
      url.searchParams.append(k, String(v));
    }
  }
  return url.toString();
}

function mergeHeaders(opts?: ApiOptions): Headers {
  const h = new Headers();
  // JSON defaults; multipart helper will override and not set Content-Type
  h.set("Accept", "application/json");
  // With HttpOnly sessions, do not inject Authorization; rely on credentials: 'include'.
  if (opts?.headers) {
    for (const [k, v] of Object.entries(opts.headers)) {
      if (v !== undefined && v !== null) h.set(k, v);
    }
  }
  if (opts?.xClientId && !h.has("X-Client-Id")) {
    h.set("X-Client-Id", opts.xClientId);
  }
  if (opts?.xJobToken && !h.has("X-Job-Token")) {
    h.set("X-Job-Token", opts.xJobToken);
  }
  return h;
}

async function parseResponse<T>(res: Response): Promise<T> {
  if (res.ok) {
    const ct = res.headers.get("content-type") || "";
    if (res.status === 204) return undefined as unknown as T; // no content
    if (ct.includes("application/json")) return (await res.json()) as T;
    const text = await res.text();
    // Best effort cast
    try {
      // handle servers that send JSON but missing content-type
      return JSON.parse(text) as T;
    } catch {
      return text as unknown as T;
    }
  }
  // Non-2xx: try to extract detail
  let detail: unknown;
  const ct = res.headers.get("content-type") || "";
  try {
    if (ct.includes("application/json")) {
      const body = await res.json();
      detail = (body && (body.detail ?? body)) ?? body;
    } else {
      const text = await res.text();
      try {
        const body = JSON.parse(text);
        detail = body.detail ?? body;
      } catch {
        detail = text || res.statusText;
      }
    }
  } catch {
    detail = res.statusText;
  }
  throw new ApiError(res.status, detail);
}

// Token refresh state
let refreshPromise: Promise<boolean> | null = null;
let lastRefreshAttempt = 0;
const REFRESH_COOLDOWN_MS = 5000; // Prevent refresh spam

/**
 * Attempt to refresh access token using the refresh token.
 * Returns true if refresh succeeded, false otherwise.
 * Uses a shared promise to prevent concurrent refresh attempts.
 */
async function tryRefreshToken(): Promise<boolean> {
  // Prevent refresh spam
  const now = Date.now();
  if (now - lastRefreshAttempt < REFRESH_COOLDOWN_MS) {
    // If we recently attempted a refresh, assume it succeeded (or is about to)
    // and tell the caller to retry their request. If the retry fails, 
    // the caller's own logic (skipRefresh: true) will handle the final failure.
    return true;
  }
  
  // If already refreshing, wait for that attempt
  if (refreshPromise) {
    return refreshPromise;
  }
  
  lastRefreshAttempt = now;
  
  refreshPromise = (async () => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/auth/refresh`, {
        method: 'POST',
        credentials: 'include', // Send HttpOnly cookies (rt_refresh)
        headers: { 'Content-Type': 'application/json' },
      });
      
      if (res.ok) {
        // Refresh succeeded - new cookies have been set
        const data = await res.json();
        // Update local storage heuristic to keep "likely logged in" state fresh
        try {
          if (typeof localStorage !== 'undefined') {
            localStorage.setItem("__rt_auth_expect_true", String(Date.now()));
          }
        } catch (e) {
            // ignore
        }

        // Optionally store access token in localStorage as backup
        if (data.access_token) {
          try {
            const { setAccessToken } = require('./auth');
            setAccessToken?.(data.access_token);
          } catch {}
        }
        console.log('[API] Token refresh succeeded');
        return true;
      } else {
        console.warn('[API] Token refresh failed:', res.status);
        return false;
      }
    } catch (err) {
      console.error('[API] Token refresh error:', err);
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  
  return refreshPromise;
}

async function requestJSON<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  options?: ApiOptions
): Promise<T> {
  const url = buildUrl(path, options?.query);
  const headers = mergeHeaders(options);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  
  // CRITICAL: Use keepalive for mutations to ensure they complete even if user navigates away
  // This is essential for apply/unapply/update flows where user might navigate immediately
  const shouldKeepAlive = method === "POST" || method === "DELETE" || method === "PATCH" || method === "PUT";
  
  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: options?.signal,
    keepalive: shouldKeepAlive, // Ensures request completes even if page unloads
  });
  // 401 handling refinement:
  // - Only emit logout event if we have previously confirmed an authenticated session (w.__rt_was_logged_in)
  //   to avoid spurious clears on anonymous first-load polling or transient 401s.
  // - Still throttle events (>=300ms apart) to prevent storms.
  try {
    if (typeof window !== "undefined") {
      const w: any = window as any;
  if (res.ok) {
        // Mark that this tab has seen an authenticated response (used to decide if future 401 implies session expiry)
        if (path === "/users/me") {
          w.__rt_was_logged_in = true;
          authEstablished = true;
          // Refresh the heuristic flag to keep "likely logged in" state alive across sessions
          try { localStorage.setItem("__rt_auth_expect_true", String(Date.now())); } catch {}
        }
      } else if (res.status === 401) {
        const wasLogged = !!w.__rt_was_logged_in;
        // Try to refresh token if:
        // 1. We were previously logged in (session expired)
        // 2. OR this is the auth probe (/users/me) and we might have a valid refresh token even if unknown to JS
        if ((wasLogged || path === "/users/me") && path !== "/auth/refresh" && !options?.skipRefresh) {
            logger.debug('[API] 401 detected, attempting token refresh...');
            const refreshed = await tryRefreshToken();
            if (refreshed) {
              logger.debug('[API] Token refreshed successfully, retrying request...');
              // Retry the original request with new token
              return requestJSON<T>(method, path, body, { ...options, skipRefresh: true });
            }
            if (wasLogged) logger.warn('[API] Token refresh failed, logging out');
        }
          
        if (wasLogged && (!w.__rt_last_401_ts || (Date.now() - w.__rt_last_401_ts) > 300)) {
            w.__rt_last_401_ts = Date.now();
            logger.warn('[API] 401 detected for previously logged-in user. Engaging lockAuth.');
            // Engage global lock so subsequent API calls get short‑circuited quickly.
            lockAuth("401");
          } else if (wasLogged) {
            logger.debug('[API] 401 detected but debounced (< 300ms since last)');
          } else {
            logger.debug('[API] 401 detected but user was never logged in - suppressing lockAuth');
            // Anonymous 401: suppress logout event to preserve user-entered text & avoid noisy clears.
          // Optionally could set a flag (w.__rt_saw_anonymous_401) for diagnostics.
        }
        // No auto-reload to avoid loops.
      }
    }
  } catch {}
  // TEMPORARILY DISABLED FOR DEBUGGING
  // if ((process.env.NEXT_PUBLIC_RT_DEBUG_AUTH || "").trim() === "1") {
  //   // eslint-disable-next-line no-console
  //   console.debug(`[api] ${method} ${url} -> ${res.status}`);
  // }
  // If we get a 2xx, clear the ephemeral token (session established)
  try {
    if (res.ok) {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { clearEphemeralAccessToken } = require("./auth");
      clearEphemeralAccessToken?.();
      // TEMPORARILY DISABLED FOR DEBUGGING
      // if ((process.env.NEXT_PUBLIC_RT_DEBUG_AUTH || "").trim() === "1") {
      //   // eslint-disable-next-line no-console
      //   console.debug("[api] cleared ephemeral token after successful response");
      // }
    }
  } catch {}
  return parseResponse<T>(res);
}

export async function apiGet<T>(path: string, options?: ApiOptions): Promise<T> {
  if (isAuthLocked() && path !== "/token" && path !== "/signup") {
    // Fast-fail with consistent error; caller can decide to surface a single UI toast.
    throw new ApiError(401, "Session expired");
  }
  // Specialized handling for the /users/me probe.
  if (path === "/users/me") {
    // If already established, use single-flight probe with short cache (ensures consumers can always call transparently)
    if (authEstablished) {
      try { return await meProbe(false) as T; } catch (e: any) { throw e; }
    }
    // Not established yet: decide whether to attempt network based on heuristics
    const heuristic = (typeof window !== "undefined" && (window as any).__rt_was_logged_in) || likelyHasSessionCookie();
    if (heuristic) {
      try { return await meProbe(false) as T; } catch (e: any) { throw e; }
    }
    // Defer: attach interaction listeners (once) and short-circuit with synthetic 401 (clean, no network)
    installDeferredProbeListeners();
    throw new ApiError(401, "Auth probe deferred");
  }
  // If we have NEVER established auth yet, avoid firing obviously protected endpoints
  // that would 401 (balance, 2fa state, etc.) until /users/me succeeds once. This
  // keeps the logged-out console cleaner & avoids MIME warnings for SSE preflights.
  if (!authEstablished) {
    const protectedPrefixes = ["/users/me/balance", "/2fa/", "/2fa", "/jobs/", "/applications/", "/admin", "/users/me/settings", "/users/me/model-settings"];
    // Only allow the /users/me probe itself and /pricing/* and /billing/summary before auth is established (for early tooltip data)
    const allowedPaths = ["/users/me", "/billing/summary"];
    const allowedPrefixes = ["/pricing/"];
    const isAllowed = allowedPaths.includes(path) || allowedPrefixes.some(p => path.startsWith(p));
    if (!isAllowed && protectedPrefixes.some(p => path.startsWith(p) || p === path)) {
      throw new ApiError(401, "Auth not established (suppressed pre-login fetch)");
    }
  }
  return requestJSON<T>("GET", path, undefined, options);
}

export async function apiPost<T>(path: string, json: unknown, options?: ApiOptions): Promise<T> {
  if (isAuthLocked() && path !== "/token" && path !== "/signup") {
    throw new ApiError(401, "Session expired");
  }
  return requestJSON<T>("POST", path, json, options);
}

export async function apiPut<T>(path: string, json: unknown, options?: ApiOptions): Promise<T> {
  if (isAuthLocked()) throw new ApiError(401, "Session expired");
  return requestJSON<T>("PUT", path, json, options);
}

export async function apiDelete<T>(path: string, json?: unknown, options?: ApiOptions): Promise<T> {
  if (isAuthLocked()) throw new ApiError(401, "Session expired");
  return requestJSON<T>("DELETE", path, json, options);
}

export async function apiPatch<T>(path: string, json?: unknown, options?: ApiOptions): Promise<T> {
  if (isAuthLocked()) throw new ApiError(401, "Session expired");
  return requestJSON<T>("PATCH", path, json, options);
}

export type FormValue = string | Blob | File | (string | Blob | File)[] | null | undefined;

export interface MultipartOptions extends ApiOptions {
  // Provide either a ready FormData or a map of fields -> values
  form?: FormData;
}

function appendFormField(fd: FormData, key: string, value: FormValue) {
  if (value === undefined || value === null) return;
  if (Array.isArray(value)) {
    for (const v of value) appendFormField(fd, key, v as string | Blob | File);
    return;
  }
  fd.append(key, value as string | Blob);
}

export async function apiPostMultipart<T>(
  path: string,
  fields: Record<string, FormValue> | FormData,
  options?: MultipartOptions
): Promise<T> {
  if (isAuthLocked()) throw new ApiError(401, "Session expired");
  const url = buildUrl(path, options?.query);
  const headers = mergeHeaders(options);
  // Important: do NOT set Content-Type here so the browser sets the boundary
  if (headers.has("Content-Type")) headers.delete("Content-Type");

  const fd = fields instanceof FormData ? fields : new FormData();
  if (!(fields instanceof FormData)) {
    for (const [k, v] of Object.entries(fields)) {
      // Preserve exact field names as provided by caller (match Streamlit forms)
      appendFormField(fd, k, v);
    }
  }

  const res = await fetch(url, {
    method: "POST",
    headers,
    credentials: "include",
    body: fd,
    signal: options?.signal,
  });
  return parseResponse<T>(res);
}

export function withClientHeaders(base: ApiOptions, xClientId?: string, xJobToken?: string): ApiOptions {
  return {
    ...base,
    xClientId: xClientId ?? base.xClientId,
    xJobToken: xJobToken ?? base.xJobToken,
  };
}

export const api = {
  get: apiGet,
  post: apiPost,
  put: apiPut,
  delete: apiDelete,
  patch: apiPatch,
  postMultipart: apiPostMultipart,
};

// Expose minimal helpers for advanced callers / debugging
export const authState = { isLocked: isAuthLocked, isEstablished: () => authEstablished };

// Export base URL getter for consumers that must construct absolute URLs (e.g., EventSource)
export function getApiBaseUrl(): string { return getBaseUrl(); }

// Sync authEstablished with global rt-auth events so components can gate streams immediately post-login
try {
  if (typeof window !== "undefined") {
    window.addEventListener("rt-auth", ((e: Event) => {
      try {
        const d: any = (e as CustomEvent).detail || {};
        const st = String(d?.state || "").toLowerCase();
        if (st === "logged-in") {
          authEstablished = true;
          // @ts-ignore
          (window as any).__rt_was_logged_in = true;
        }
      } catch {}
    }) as EventListener);
  }
} catch {}

export default api;
