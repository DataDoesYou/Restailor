"use client";

import { useEffect, useRef } from "react";
import { authState, getApiBaseUrl } from "./api"; // global 401 lock & establishment awareness

/**
 * useSSE
 * - Opens an EventSource to the provided FastAPI SSE endpoint
 * - Sends cookies (withCredentials)
 * - Reconnects on network error with exponential backoff (capped)
 * - Cleans up on unmount or URL change
 * - No polling fallback
 */
export function useSSE(
  url: string,
  onMessage: (event: MessageEvent) => void,
  onError?: (err: unknown) => void
) {
  const urlRef = useRef(url);
  const msgRef = useRef(onMessage);
  const errRef = useRef(onError);
  const esRef = useRef<EventSource | null>(null);
  const stopRef = useRef(false);

  // Keep latest callbacks without resubscribing the EventSource unnecessarily
  useEffect(() => {
    urlRef.current = url;
  }, [url]);
  useEffect(() => {
    msgRef.current = onMessage;
  }, [onMessage]);
  useEffect(() => {
    errRef.current = onError;
  }, [onError]);

  useEffect(() => {
    stopRef.current = false;

    let backoffMs = 500; // start small
    const maxBackoffMs = 10_000; // cap
    const pauseUntilRef = { current: 0 }; // epoch ms until which we suppress reconnects (e.g. right after logout)
    const retryTimerRef: { current: ReturnType<typeof setTimeout> | null } = { current: null };

    // Best-effort probe to ensure the target responds with text/event-stream before creating EventSource.
    // Uses HEAD to avoid opening a hanging stream. Falls back to false on error/timeout.
  const PROBE = (process.env.NEXT_PUBLIC_SSE_PROBE || "").trim() === "1";
  const probeHeaders = async (targetUrl: string, timeoutMs = 1500): Promise<boolean> => {
      if (!/^https?:\/\//i.test(targetUrl)) return false;
      try {
        const ac = new AbortController();
        const timer = setTimeout(() => ac.abort(), timeoutMs);
        const res = await fetch(targetUrl, { method: "HEAD", credentials: "include", signal: ac.signal, cache: "no-store" as RequestCache });
        clearTimeout(timer);
    // Many SSE endpoints do not implement HEAD and return 405; treat that as acceptable
    if (res.status === 405) return true;
    if (!res.ok) return false;
        const ct = (res.headers.get("content-type") || "").toLowerCase();
        return ct.includes("text/event-stream");
      } catch {
        return false;
      }
    };

    const schedule = (ms: number) => {
      if (stopRef.current) return;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      retryTimerRef.current = setTimeout(() => {
        retryTimerRef.current = null;
        connect();
      }, ms);
    };

    const connect = async () => {
      if (stopRef.current) return;

      const now = Date.now();
      if (pauseUntilRef.current && now < pauseUntilRef.current) {
        schedule(pauseUntilRef.current - now);
        return;
      }

      // Do not attempt to connect without a valid SSE URL
      const target = String(urlRef.current || "").trim();
      if (!target) {
        // Wait for a non-empty URL (e.g., jobId assignment) — effect will re-run on url change
        return;
      }
      // Optional: only allow http/https schemes to avoid accidental "about:blank"/page URLs
      if (!/^https?:\/\//i.test(target)) {
        // If you intend to use relative URLs, adjust this guard accordingly
        return;
      }
      // Ensure target origin matches our API base to avoid hitting Next.js pages that return HTML
      try {
        const apiOrigin = new URL(getApiBaseUrl()).origin;
        const targetOrigin = new URL(target).origin;
        if (apiOrigin !== targetOrigin) {
          // Mismatched origin; skip to prevent HTML responses
          schedule(1500);
          return;
        }
      } catch {}

      // Gate on auth establishment & lock: if not yet established, poll slowly waiting for login
      try {
        if (authState.isLocked()) {
          // Locked after 401 storm; stop permanently until a fresh login event toggles state.
          return;
        }
        if (!authState.isEstablished()) {
          // User not logged in yet (first visit) – suppress SSE noise; retry modestly.
          schedule(1500);
          return;
        }
      } catch {
        // If authState introspection fails, back off a bit to avoid tight loop.
        schedule(2000);
        return;
      }

      // MIME/type guard (optional): only when explicitly enabled via NEXT_PUBLIC_SSE_PROBE=1
      if (PROBE) {
        const ok = await probeHeaders(target);
        if (!ok) {
          const delay = backoffMs;
          backoffMs = Math.min(maxBackoffMs, Math.floor(backoffMs * 2));
          schedule(delay);
          return;
        }
      }
      try {
        // Close any prior connection before opening new one
        if (esRef.current) {
          try { esRef.current.close(); } catch {}
        }
        const src = new EventSource(urlRef.current, { withCredentials: true });
        esRef.current = src;

        // Reset backoff when connection opens
        src.onopen = () => {
          backoffMs = 500;
        };

        src.onmessage = (ev) => {
          try {
            msgRef.current?.(ev);
          } catch (e) {
            // Swallow handler exceptions to avoid tearing down the stream
            console.error("useSSE onMessage handler error", e);
          }
        };

        src.onerror = (ev) => {
          // Network or server error; allow reconnect with backoff
          try {
            errRef.current?.(ev);
          } catch (e) {
            console.error("useSSE onError handler error", e);
          }
          // Some browsers keep readyState=CLOSED after fatal; proactively close and reconnect
          try { src.close(); } catch {}
          esRef.current = null;
          if (!stopRef.current) {
            try {
              if (authState.isLocked()) {
                // Do not spin while locked; wait for login event.
                return;
              }
            } catch {}
            const delay = backoffMs;
            backoffMs = Math.min(maxBackoffMs, Math.floor(backoffMs * 2));
      schedule(delay);
          }
        };
      } catch (e) {
        // Immediate failure (e.g., bad URL); schedule another attempt
        errRef.current?.(e);
        if (!stopRef.current) {
          try { if (authState.isLocked()) { return; } } catch {}
          const delay = backoffMs;
          backoffMs = Math.min(maxBackoffMs, Math.floor(backoffMs * 2));
          schedule(delay);
        }
      }
    };

    // Kick off (async-safe)
    connect();

    // Listen for auth events to manage lifecycle
    const onAuth = (e: Event) => {
      try {
        const d: any = (e as CustomEvent).detail || {};
        const state = String(d?.state || "").toLowerCase();
        if (state === "logged-out") {
          // Close and pause reconnect attempts for a short privacy window
            try { esRef.current?.close(); } catch {}
            esRef.current = null;
            // 45s suppression window (short; user may immediately log back in) – adjustable
            pauseUntilRef.current = Date.now() + 45_000;
            // Allow future attempts (do not set stopRef) but schedule next check
            schedule(45_000);
        } else if (state === "logged-in") {
          // Resume immediately
          pauseUntilRef.current = 0;
          backoffMs = 500;
          // Do not duplicate connection if already alive
          if (!esRef.current) {
            connect();
          }
        }
      } catch {}
    };
    window.addEventListener("rt-auth", onAuth as EventListener);

    return () => {
      stopRef.current = true;
      if (esRef.current) {
        try { esRef.current.close(); } catch {}
        esRef.current = null;
      }
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      window.removeEventListener("rt-auth", onAuth as EventListener);
    };
  }, [url]);
}

export default useSSE;
