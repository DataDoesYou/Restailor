"use client";
import { useCallback, useEffect, useState } from "react";
import api, { ApiError } from "@/lib/api";
import { b64urlToBuf, bufToB64url } from "@/lib/client";

export default function SecurityClient() {
  const [state, setState] = useState<any | null>(null);
  const [started, setStarted] = useState<any | null>(null);
  const [code, setCode] = useState("");
  const [alert, setAlert] = useState<{ kind: "info" | "success" | "error" | "warning"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [authPending, setAuthPending] = useState<boolean>(true);
  const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(null);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);

  // Reauth token for sensitive actions
  const [reauthToken, setReauthToken] = useState<string | null>(null);
  const [reauthPwDis, setReauthPwDis] = useState("");
  const [reauthCodeDis, setReauthCodeDis] = useState("");

  // Track loading separately so we don't show perpetual "Loading" if suppressed pre-auth
  const [loading2fa, setLoading2fa] = useState(true);
  const loadState = useCallback(async () => {
    try {
      const s = await api.get("/2fa/state");
      setState(s);
      return s;
    } catch (e) {
      setState(null);
      throw e;
    }
  }, []);

  // Attempt to load 2FA state with small retry loop to survive deferred auth probe
  const attemptLoad2fa = useCallback(() => {
    let cancelled = false;
    setLoading2fa(true);
    (async () => {
      for (let attempt = 0; attempt < 5 && !cancelled; attempt++) {
        try {
          await loadState();
          if (!cancelled) setIsLoggedIn(true);
          break; // success
        } catch (e: any) {
          const detail = String((e as any)?.detail || "");
          // For first attempts, try to nudge auth establishment by probing /users/me (ignore errors)
          if (attempt < 4 && (detail.includes("Auth probe deferred") || detail.includes("Auth not established") || (e as any)?.status === 401)) {
            try { await api.get("/users/me").catch(() => {}); } catch {}
            await new Promise(r => setTimeout(r, 400 + attempt * 250));
            continue;
          }
          // Non-401 or exhausted attempts -> stop
          if (!cancelled && ((e as any)?.status === 401 || (e as any)?.status === 403)) {
            setIsLoggedIn(false);
          }
          break;
        }
      }
      if (!cancelled) {
        setLoading2fa(false);
        setAuthPending(false);
      }
    })();
    return () => { cancelled = true; };
  }, [loadState]);

  useEffect(() => {
    const cleanup = attemptLoad2fa();
    return cleanup;
  }, [attemptLoad2fa]);

  // Fetch user role to determine if admin
  useEffect(() => {
    if (isLoggedIn) {
      api.get("/users/me").then((user: any) => {
        setIsAdmin(user?.role === "admin");
      }).catch(() => {});
    }
  }, [isLoggedIn]);

  // Client-side redirect for /security route (protected workspace)
  useEffect(() => {
    if (authPending) return; // Wait for auth check to complete
    if (isLoggedIn === false && typeof window !== 'undefined' && window.location.pathname === '/security') {
      // Redirect logged-out users to homepage
      window.location.href = '/';
    }
  }, [authPending, isLoggedIn]);

  const startTotp = useCallback(async () => {
    setBusy(true);
    try { const r = await api.post("/2fa/totp/start", {}); setStarted(r); }
    catch { setAlert({ kind: "error", text: "Could not start 2FA setup." }); }
    finally { setBusy(false); }
  }, []);

  const confirmTotp = useCallback(async () => {
    setBusy(true);
    try {
      const r: any = await api.post("/2fa/totp/confirm", { code });
      setStarted(null);
      setAlert({ kind: "success", text: "2FA enabled successfully." });
      loadState();
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 400) setAlert({ kind: "error", text: "Invalid code." });
      else setAlert({ kind: "error", text: "Could not confirm 2FA." });
    } finally { setBusy(false); }
  }, [code, loadState]);

  // Auto-fetch start payload when needed (parity with Streamlit implicit start)
  useEffect(() => {
    const needStart = state && !state.two_factor_enabled;
    if (needStart && !started) {
      // fire and forget; avoid alert spam
      (async () => {
        try { const r = await api.post("/2fa/totp/start", {}); setStarted(r); } catch {}
      })();
    }
  }, [state, started]);

  // Disable 2FA (reauth)
  const disable2fa = useCallback(async () => {
    setBusy(true);
    setAlert(null);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/2fa/disable`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(reauthToken ? { "X-Reauth-Token": reauthToken } : {}) },
        body: JSON.stringify({ password: reauthPwDis, code: reauthCodeDis || null }),
      });
      if (res.ok) {
        const rt = res.headers.get("X-Reauth-Token");
        if (rt) setReauthToken(rt);
        setAlert({ kind: "success", text: "2FA disabled." });
        loadState();
      } else if (res.status === 401) {
        setAlert({ kind: "warning", text: "Reauth required. Try again after logging in." });
      } else {
        setAlert({ kind: "error", text: "Could not disable 2FA." });
      }
    } catch {
      setAlert({ kind: "error", text: "Network error." });
    } finally { setBusy(false); }
  }, [reauthPwDis, reauthCodeDis, reauthToken, loadState]);

  // Trusted devices
  const [policy, setPolicy] = useState<any | null>(null);
  const [devices, setDevices] = useState<any[]>([]);
  const loadTrusted = useCallback(async () => {
    try {
      const p = await api.get("/2fa/trusted-devices/policy");
      setPolicy(p);
    } catch {}
    try {
      const rows = await api.get<any[]>("/2fa/trusted-devices");
      setDevices(rows || []);
    } catch { setDevices([]); }
  }, []);
  useEffect(() => { loadTrusted(); }, [loadTrusted]);
  const revokeDevice = useCallback(async (id: string) => {
    setBusy(true);
    try { await api.post("/2fa/trusted-devices/revoke", { device_id: id }); setAlert({ kind: "success", text: "Revoked." }); loadTrusted(); }
    catch { setAlert({ kind: "error", text: "Could not revoke." }); }
    finally { setBusy(false); }
  }, [loadTrusted]);

  // Passkeys section
  const [creds, setCreds] = useState<any[]>([]);
  const loadCreds = useCallback(async () => {
    try {
      const rows = await api.get<any[]>("/webauthn/credentials");
      setCreds(rows || []);
    } catch { setAlert({ kind: "warning", text: "Could not load passkeys for your account." }); }
  }, []);
  useEffect(() => { loadCreds(); }, [loadCreds]);
  const waDelete = useCallback(async (id: string) => {
    setBusy(true);
    try { await api.delete(`/webauthn/credentials/${id}`); setAlert({ kind: "success", text: "Deleted." }); loadCreds(); }
    catch { setAlert({ kind: "error", text: "Delete failed." }); }
    finally { setBusy(false); }
  }, [loadCreds]);
  const waCreate = useCallback(async () => {
    setBusy(true);
    try {
      const opts: any = await api.post("/webauthn/register/options", {});
      const publicKey = opts?.publicKey ?? {};
      if (publicKey.challenge) publicKey.challenge = b64urlToBuf(String(publicKey.challenge));
      if (publicKey.user?.id) publicKey.user.id = b64urlToBuf(String(publicKey.user.id));
      if (Array.isArray(publicKey.excludeCredentials)) publicKey.excludeCredentials = publicKey.excludeCredentials.map((c: any) => ({ ...c, id: b64urlToBuf(String(c.id)) }));
      const cred = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null;
      if (!cred) { setAlert({ kind: "error", text: "Passkey creation was cancelled or failed." }); return; }
      const att = cred.response as AuthenticatorAttestationResponse;
      
      // Generate automatic device name from user agent
      const ua = navigator.userAgent;
      let osName = "Unknown Device";
      if (ua.includes("Windows")) osName = "Windows PC";
      else if (ua.includes("Macintosh")) osName = "Mac";
      else if (ua.includes("iPhone")) osName = "iPhone";
      else if (ua.includes("iPad")) osName = "iPad";
      else if (ua.includes("Android")) osName = "Android";
      else if (ua.includes("Linux")) osName = "Linux";
      
      // Add browser info
      let browserName = "";
      if (ua.includes("Chrome") && !ua.includes("Edg")) browserName = "Chrome";
      else if (ua.includes("Firefox")) browserName = "Firefox";
      else if (ua.includes("Safari") && !ua.includes("Chrome")) browserName = "Safari";
      else if (ua.includes("Edg")) browserName = "Edge";
      
      // Get hostname (machine name) if available
      let hostname = "";
      try {
        // Try to get hostname from window.location
        hostname = window.location.hostname;
        // If it's localhost or an IP, try to use a better identifier
        if (hostname === "localhost" || hostname.match(/^\d+\.\d+\.\d+\.\d+$/)) {
          hostname = ""; // Don't include localhost/IP in the name
        }
      } catch {
        hostname = "";
      }
      
      // Construct final name: "hostname - OS (Browser)" or "OS (Browser)"
      const deviceInfo = browserName ? `${osName} (${browserName})` : osName;
      const finalName = hostname ? `${hostname} - ${deviceInfo}` : deviceInfo;
      
      const payload = {
        credential: {
          id: cred.id,
          rawId: bufToB64url(cred.rawId),
          type: cred.type,
          response: {
            attestationObject: bufToB64url(att.attestationObject),
            clientDataJSON: bufToB64url(att.clientDataJSON),
          },
        },
        nickname: finalName,
      };
      await api.post("/webauthn/register/verify", payload);
      setAlert({ kind: "success", text: "Passkey added." });
      loadCreds();
    } catch (e) {
      const det = (e as any)?.detail;
      setAlert({ kind: "error", text: typeof det === "string" && det ? `Registration failed: ${det}` : "Registration failed." });
    } finally { setBusy(false); }
  }, [loadCreds]);

  return (
    <div className="space-y-3 px-4 md:px-0">
      <h1 className="text-xl font-semibold">Security</h1>

      <h2 className="text-lg font-semibold">Two‑Factor Authentication (2FA)</h2>
      {loading2fa ? (
        <div className="text-slate-300">Loading 2FA status…</div>
      ) : !state ? (
        <div className="text-slate-300">Could not load 2FA status. <button className="underline" onClick={attemptLoad2fa}>Retry</button></div>
      ) : (
        <>
          {state.two_factor_enabled && state.has_totp ? (
            <div className="space-y-2">
              <div className="text-green-400 font-medium">✓ Two-factor authentication is enabled</div>
              <div className="text-sm text-slate-400">Your account is protected. You'll need your authenticator app code when logging in.</div>
            </div>
          ) : !state.two_factor_enabled ? (
            <>
              <div className="mb-3">Protect your account with an authenticator app like Google Authenticator or Authy.</div>
              <div className="text-sm text-slate-400 mb-4">Scan the QR code below with your authenticator app, then enter the 6-digit code to complete setup.</div>
            </>
          ) : null}

          {(started || !state.two_factor_enabled) && (
            <div className="space-y-2">
              {(() => {
                const d = started;
                const b64raw = String(d?.qr_png_base64 || "").trim();
                return b64raw ? (
                  <img src={b64raw} alt="QR Code for 2FA" className="max-w-xs border border-slate-700 rounded p-2" />
                ) : (
                  <div className="text-yellow-400">Loading QR code…</div>
                );
              })()}
              <label className="block text-sm font-medium">Enter the 6‑digit code from your app</label>
              <input 
                maxLength={6} 
                placeholder="000000"
                className="w-full md:max-w-xs rounded border border-slate-600 bg-slate-800 px-3 py-2 font-mono text-lg tracking-widest" 
                value={code} 
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} 
              />
              <button disabled={busy || code.length !== 6} onClick={confirmTotp} className="rounded bg-green-600 px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed font-medium">
                Confirm & Enable 2FA
              </button>
            </div>
          )}

          {state.two_factor_enabled && state.has_totp && (
            <>
              <div className="border border-slate-700 rounded p-3">
                <h3 className="font-medium mb-2">Disable 2FA</h3>
                <form
                  onSubmit={(e) => { e.preventDefault(); disable2fa(); }}
                  method="post"
                  noValidate
                  className="space-y-2"
                >
                  <input type="text" autoComplete="username" tabIndex={-1} aria-hidden="true" className="sr-only opacity-0 pointer-events-none" readOnly value="" />
                  <label className="block" htmlFor="reauth-pw-dis">Password</label>
                  <input
                    id="reauth-pw-dis"
                    name="current-password"
                    type="password"
                    autoComplete="current-password"
                    className="w-full md:max-w-md rounded border border-slate-600 bg-transparent px-3 py-2"
                    value={reauthPwDis}
                    onChange={(e) => setReauthPwDis(e.target.value)}
                  />
                  <label className="block" htmlFor="reauth-code-dis">6‑digit code</label>
                  <input
                    id="reauth-code-dis"
                    name="one-time-code"
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    className="w-full md:max-w-md rounded border border-slate-600 bg-transparent px-3 py-2"
                    value={reauthCodeDis}
                    onChange={(e) => setReauthCodeDis(e.target.value)}
                  />
                  <button type="submit" disabled={busy} className="mt-2 rounded bg-blue-600 px-3 py-2 disabled:opacity-50">Disable 2FA</button>
                </form>
              </div>
            </>
          )}
        </>
      )}

      <div className="border border-slate-700 rounded p-3">
        <h3 className="font-medium mb-2">Trusted devices</h3>
        {policy && (
          <div className="text-slate-400 text-sm">
            Max devices: {isAdmin ? (policy.admin_max_devices ?? 2) : (policy.max_devices_per_user ?? 5)} · Remember window: {isAdmin ? (policy.admin_days ?? 7) : (policy.days ?? 30)} days
          </div>
        )}
        {devices.length === 0 ? (
          <div>No trusted devices.</div>
        ) : (
          <div className="mt-2 overflow-x-auto -mx-3 px-3">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left pr-3 whitespace-nowrap">Created</th>
                  <th className="text-left pr-3 whitespace-nowrap">Last used</th>
                  <th className="text-left pr-3 whitespace-nowrap">Expires</th>
                  <th className="text-left pr-3 whitespace-nowrap">User agent</th>
                  <th className="text-left pr-3 whitespace-nowrap">IP prefix</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {devices.map((row) => (
                  <tr key={row.id}>
                    <td className="pr-3 whitespace-nowrap">{String(row.created_at || "")}</td>
                    <td className="pr-3 whitespace-nowrap">{String(row.last_used_at || "—")}</td>
                    <td className="pr-3 whitespace-nowrap">{String(row.expires_at || "—")}</td>
                    <td className="pr-3 whitespace-nowrap">{String(row.user_agent || "")}</td>
                    <td className="pr-3 whitespace-nowrap">{String(row.ip_prefix || "")}</td>
                    <td><button className="rounded bg-slate-700 px-2 py-1 whitespace-nowrap" onClick={() => revokeDevice(row.id)}>Revoke</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="border border-slate-700 rounded p-3">
        <h3 className="font-medium mb-2">Passkeys (WebAuthn)</h3>
        <div className="text-slate-300 mb-2">Register a passkey for phishing-resistant 2FA. Works with platform authenticators (Windows Hello, Touch ID) and security keys.</div>

        {creds.length === 0 ? (
          <div className="text-slate-300">No passkeys registered yet.</div>
        ) : (
          <div className="mt-2 overflow-x-auto -mx-3 px-3">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left pr-3 whitespace-nowrap">Device</th>
                  <th className="text-left pr-3 whitespace-nowrap">Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {creds.map((row) => (
                  <tr key={row.credential_id}>
                    <td className="pr-3">{row.nickname || "Unnamed device"}</td>
                    <td className="pr-3 whitespace-nowrap">{String(row.created_at || "")}</td>
                    <td><button className="rounded bg-slate-700 px-2 py-1 whitespace-nowrap" onClick={() => waDelete(row.credential_id)} disabled={busy}>Delete</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <hr className="border-slate-700 my-3" />
        <div className="space-y-2">
          <h3 className="font-medium">Register a new passkey</h3>
          <p className="text-slate-300 text-sm">Your device will be automatically named based on your browser and operating system.</p>
          <button disabled={busy} onClick={waCreate} className="mt-2 rounded bg-blue-600 px-3 py-2 disabled:opacity-50">Create passkey</button>
        </div>
      </div>

      {alert && <div className={{ info: "text-blue-400", success: "text-green-400", error: "text-red-400", warning: "text-yellow-400" }[alert.kind]}>{alert.text}</div>}
    </div>
  );
}
