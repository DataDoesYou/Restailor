"use client";

// Global client-side fetch guard to further reduce 401 noise after the auth
// lock engages. This complements the api.ts helpers by short‑circuiting any
// remaining raw fetch() calls that target the backend base URL directly
// (e.g. legacy code using interpolated `${process.env.NEXT_PUBLIC_API_URL}`) so
// they don't keep hitting the network post-expiry.
//
// Design:
// - Installs once per tab; idempotent.
// - If authState.isLocked() and request URL targets API origin, returns a
//   synthetic 401 JSON Response immediately (mimicking backend shape) so
//   existing code paths that rely on `res.ok` checks behave consistently.
// - Allows token/signup endpoints to proceed (should they be attempted) so the
//   user can still log back in without a full reload.
// - Skips intercepting relative URLs (Next.js internal /app or /api routes)
//   to avoid side effects on framework internals.

import { useEffect } from "react";
import { authState } from "@/lib/api";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

// Heuristic list of obviously protected endpoints that we should *not* hit
// pre‑login (before we have positively established a session). This mirrors the
// suppression logic in `api.ts` for callers using the helper, but also guards
// any legacy / raw `fetch()` calls still lingering in the codebase. Returning a
// synthetic 401 keeps calling code paths predictable while avoiding a burst of
// network 401s in the browser console (cleaner DX + avoids wasted RTTs).
const PROTECTED_PREFIXES = [
  "/users/me/balance",
  "/users/me/inputs",
  "/users/me/settings",
  "/users/me/model-settings",
  "/2fa/",
  "/2fa", // exact
  "/jobs/",
  "/applications/",
  "/admin",
  "/billing",
  "/pricing/averages",
];

function isApiAbsolute(url: string): boolean {
  if (!API_BASE) return false;
  return url.startsWith(API_BASE);
}

export default function AuthFetchGuard() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const w: any = window as any;
    if (w.__rt_fetch_guard_installed) return;
    w.__rt_fetch_guard_installed = true;
    const originalFetch: typeof fetch = window.fetch.bind(window);

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      try {
        // Derive URL string early for all logic branches
        let urlStr: string;
        if (typeof input === "string") urlStr = input;
        else if (input instanceof URL) urlStr = input.toString();
        else if (input && typeof (input as Request).url === "string") urlStr = (input as Request).url;
        else urlStr = "";

        // Only consider absolute backend calls; let relative/internal routes proceed untouched.
        const isApi = urlStr && isApiAbsolute(urlStr);

        // 1) Pre-login suppression (auth NOT established, NOT locked, clearly protected endpoint)
        //    We short‑circuit with a lightweight synthetic 401 so components relying
        //    on `res.ok` continue to behave, but we avoid network noise.
        if (isApi && !authState.isLocked() && !(window as any).__rt_was_logged_in) {
          try {
            const path = urlStr.slice(API_BASE.length) || "/";
            if (path !== "/users/me" && PROTECTED_PREFIXES.some(p => path.startsWith(p))) {
              return new Response(JSON.stringify({ detail: "Auth not established (suppressed pre-login fetch)" }), {
                status: 401,
                headers: { "Content-Type": "application/json", "X-RT-Suppressed": "1" },
              });
            }
          } catch {}
        }

        // 2) Post-expiry suppression (global auth lock engaged). For re‑entry endpoints
        //    (/token, /signup) we still allow the real network call.
        if (API_BASE && authState.isLocked() && isApi) {
          if (/\/token$/.test(urlStr) || /\/signup$/.test(urlStr)) {
            return originalFetch(input as any, init);
          }
          return new Response(JSON.stringify({ detail: "Session expired" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          });
        }

        // Fall through: perform original fetch.
        return originalFetch(input as any, init);
      } catch (error) {
        // Catch any errors in guard logic and fall through to original fetch
        // But wrap it in try-catch since originalFetch itself might throw
        try {
          return originalFetch(input as any, init);
        } catch (fetchError) {
          // If originalFetch throws, return a synthetic error response instead of throwing
          console.error('[AuthFetchGuard] Original fetch failed:', fetchError);
          return new Response(JSON.stringify({ 
            detail: `Network error: ${fetchError instanceof Error ? fetchError.message : String(fetchError)}` 
          }), {
            status: 0, // Network error status
            headers: { "Content-Type": "application/json" },
          });
        }
      }
    };
  }, []);
  return null;
}
