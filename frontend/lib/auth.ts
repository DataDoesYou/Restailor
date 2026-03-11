"use client";

// Access token storage utilities
// - Persistent token: used for normal authenticated API calls
// - Ephemeral token: short-lived bridge immediately after 2FA while cookies (if any) propagate

const KEY_PERSIST = "__rt_access_token";
const KEY = "__rt_ephemeral_token";

export function setAccessToken(token: string) {
  try {
    localStorage.setItem(KEY_PERSIST, JSON.stringify({ t: token, ts: Date.now() }));
  } catch {}
}

export function getAccessToken(): string | null {
  try {
    const raw = localStorage.getItem(KEY_PERSIST);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    const t = typeof obj?.t === "string" ? obj.t : null;
    return t || null;
  } catch {
    return null;
  }
}

export function clearAccessToken() {
  try { localStorage.removeItem(KEY_PERSIST); } catch {}
}

export function setEphemeralAccessToken(token: string, ttlMs: number = 5 * 60 * 1000) {
  try {
    const exp = Date.now() + Math.max(10_000, ttlMs); // min 10s
    localStorage.setItem(KEY, JSON.stringify({ t: token, e: exp }));
  } catch {}
}

export function getEphemeralAccessToken(): string | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const j = JSON.parse(raw);
    if (!j || typeof j.t !== "string" || typeof j.e !== "number") { localStorage.removeItem(KEY); return null; }
    if (Date.now() >= j.e) { localStorage.removeItem(KEY); return null; }
    return j.t as string;
  } catch {
    return null;
  }
}

export function clearEphemeralAccessToken() {
  try { localStorage.removeItem(KEY); } catch {}
}
