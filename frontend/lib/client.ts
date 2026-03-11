"use client";

// Generate a stable, non-secret client id for headers like X-Client-Id.
// Stored in a non-HttpOnly cookie to persist between reloads.
export function getClientId(): string {
  // Never generate or read cookies during SSR. Return a stable empty string
  // so callers can defer usage until after mount.
  if (typeof document === "undefined") return "";
  try {
    // Prefer existing cookie
    const m = document.cookie.match(/(?:^|; )rt_client_id=([^;]+)/);
    if (m && m[1]) return decodeURIComponent(m[1]);
  } catch {}
  // Generate a new id on the client only
  const id = (typeof crypto !== "undefined" && (crypto as any).randomUUID)
    ? (crypto as any).randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  try {
    // Set cookie for ~1 year
    const oneYear = 365 * 24 * 60 * 60;
    document.cookie = `rt_client_id=${encodeURIComponent(id)}; Path=/; Max-Age=${oneYear}; SameSite=Lax`;
  } catch {}
  return id;
}

// WebAuthn helpers: base64url <-> ArrayBuffer
export function b64urlToBuf(b64url: string): ArrayBuffer {
  const pad = (s: string) => s + "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = pad(String(b64url).replace(/-/g, "+").replace(/_/g, "/"));
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr.buffer;
}

export function bufToB64url(buf: ArrayBuffer): string {
  const arr = new Uint8Array(buf);
  let str = "";
  for (let i = 0; i < arr.length; i++) str += String.fromCharCode(arr[i]);
  const b64 = btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  return b64;
}
