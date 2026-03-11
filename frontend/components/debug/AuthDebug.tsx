"use client";
import { useEffect, useMemo, useState } from "react";
import { getEphemeralAccessToken, getAccessToken } from "@/lib/auth";

export default function AuthDebug() {
  const enabled = (process.env.NEXT_PUBLIC_RT_DEBUG_AUTH || "").trim() === "1";
  const [cookieStatus, setCookieStatus] = useState<string>("pending");
  const [bearerStatus, setBearerStatus] = useState<string>("pending");
  const [ephem, setEphem] = useState<string | null>(null);
  const [persist, setPersist] = useState<string | null>(null);
  const apiBase = useMemo(() => (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, ""), []);
  const loc = typeof window !== "undefined" ? window.location.origin : "";
  const hostOk = useMemo(() => {
    try {
      const a = new URL(apiBase);
      const b = new URL(loc);
      return a.hostname === b.hostname && a.port === b.port && a.protocol === b.protocol;
    } catch {
      return false;
    }
  }, [apiBase, loc]);

  useEffect(() => {
    if (!enabled) return;
  setEphem(getEphemeralAccessToken());
  setPersist(getAccessToken());
    const test = async () => {
      // Cookie-only
      try {
        const r = await fetch(`${apiBase}/users/me`, { credentials: "include" });
        setCookieStatus(`${r.status}`);
      } catch (e: any) {
        setCookieStatus(`ERR ${String(e?.message || "")}`);
      }
      // Bearer (ephemeral) if available
      const t = getEphemeralAccessToken();
      if (t) {
        try {
          const rb = await fetch(`${apiBase}/users/me`, {
            credentials: "include",
            headers: { Authorization: `Bearer ${t}` },
          });
          setBearerStatus(`${rb.status}`);
        } catch (e: any) {
          setBearerStatus(`ERR ${String(e?.message || "")}`);
        }
      } else {
        // Try persistent token
        const p = getAccessToken();
        if (p) {
          try {
            const rp = await fetch(`${apiBase}/users/me`, {
              credentials: "include",
              headers: { Authorization: `Bearer ${p}` },
            });
            setBearerStatus(`${rp.status}`);
          } catch (e: any) {
            setBearerStatus(`ERR ${String(e?.message || "")}`);
          }
        } else {
          setBearerStatus("no token");
        }
      }
    };
    test();
  }, [enabled, apiBase]);

  if (!enabled) return null;
  return (
    <div className="mt-4 rounded border border-slate-700 p-2 text-xs text-slate-300 space-y-1">
      <div className="font-semibold">Auth Debug</div>
      <div>API base: <span className="text-slate-400">{apiBase}</span></div>
      <div>App origin: <span className="text-slate-400">{loc}</span></div>
      <div>Host match: <span className={hostOk ? "text-green-400" : "text-yellow-400"}>{String(hostOk)}</span></div>
      <div>Cookie /users/me: <span className="text-slate-400">{cookieStatus}</span></div>
      <div>Bearer /users/me: <span className="text-slate-400">{bearerStatus}</span></div>
  <div>Ephemeral token: <span className="text-slate-400">{ephem ? "present" : "none"}</span></div>
  <div>Persistent token: <span className="text-slate-400">{persist ? "present" : "none"}</span></div>
    </div>
  );
}
