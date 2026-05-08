"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api, { ApiError } from "@/lib/api";
import { getClientId, b64urlToBuf, bufToB64url } from "@/lib/client";
import { setEphemeralAccessToken, setAccessToken, clearAccessToken, clearEphemeralAccessToken } from "@/lib/auth";
import { useRouter, useSearchParams } from "next/navigation";
import { logger } from "@/lib/logger";
import TurnstileWidget from "@/components/captcha/TurnstileWidget";

// Minimal outline icons (monochrome) for Show/Hide password
function EyeIcon({ className = "" }: { className?: string }) {
	return (
		<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
			<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z" strokeLinecap="round" strokeLinejoin="round" />
			<circle cx="12" cy="12" r="3" />
		</svg>
	);
}
function EyeOffIcon({ className = "" }: { className?: string }) {
	return (
		<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
			<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z" strokeLinecap="round" strokeLinejoin="round" />
			<circle cx="12" cy="12" r="3" />
			<path d="M4 4l16 16" strokeLinecap="round" />
		</svg>
	);
}

// Module-level variable to track Turnstile state across all component instances
let globalTsState: "idle" | "success" | "error" = "idle";

export default function LoginClient({ stackedButtons = false }: { stackedButtons?: boolean }) {
	const router = useRouter();
	const sp = useSearchParams();
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [showPw, setShowPw] = useState(false);
	const [alert, setAlert] = useState<{ kind: "info" | "success" | "error" | "warning"; text: string } | null>(null);
	const [showForgot, setShowForgot] = useState(false);
	const [forgotEmail, setForgotEmail] = useState("");
	const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);
	const [pending2, setPending2] = useState<string | null>(null); // pending_2fa token
	const [mfaCode, setMfaCode] = useState("");
	const [busy, setBusy] = useState(false);
	// Unverified gating after successful login but 403 on /users/me
	const [unverifiedMode, setUnverifiedMode] = useState<{ email: string; cooldownUntil?: number } | null>(null);
	const [resendBusy, setResendBusy] = useState(false);
	const [showCaptcha, setShowCaptcha] = useState(false);

	// Broadcast auth changes so other components can refresh their session state
	const emitAuth = useCallback((state: "logged-in" | "logged-out") => {
		try {
			window.dispatchEvent(new CustomEvent("rt-auth", { detail: { state } }));
			localStorage.setItem("__rt_auth_bump", String(Date.now()));
		} catch {}
	}, []);

	const xClient = useMemo(() => getClientId(), []);
	// Optional Cloudflare Turnstile captcha (site key from env). When available, render widget and post token with X-Client-Id.
	const siteKey = useMemo(() => (
		process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || process.env.NEXT_PUBLIC_CF_TURNSTILE_SITE_KEY || process.env.NEXT_PUBLIC_CLOUDFLARE_TURNSTILE_SITE_KEY || ""
	), []);
	const [tsState, setTsState] = useState<"idle" | "success" | "error">("idle");
	
	const handleTsStateChange = useCallback((newState: "idle" | "success" | "error") => {
		logger.debug("[LoginClient] handleTsStateChange called with:", newState);
		globalTsState = newState;
		logger.debug("[LoginClient] globalTsState is now:", globalTsState);
		setTsState(newState);
	}, []);

	// If user arrives with verified=1&token=..., we do not auto-login here in Next; server-side route handles gating.
	useEffect(() => {
		const verified = sp?.get("verified");
		const token = sp?.get("token");
		if (verified === "1" && token) {
			// Just show an info; server will redirect appropriately.
			setAlert({ kind: "success", text: "Email verified. Please log in." });
		}
	}, [sp]);

	// While the login form is rendered (logged out), disable native browser tooltips by
	// stripping title attributes (including from third‑party widgets). This applies on
	// both the dedicated /login route and the sidebar login.
	useEffect(() => {
		let disposed = false;
		const stripTitles = (root: ParentNode | Document = document) => {
			try {
				root.querySelectorAll?.('[title]')?.forEach((el) => {
					try {
						const node = el as HTMLElement;
						const t = node.getAttribute('title');
						if (t !== null) {
							// Preserve for possible restoration/debugging
							node.setAttribute('data-title', t);
							node.removeAttribute('title');
						}
					} catch {}
				});
			} catch {}
		};
		// Initial pass
		stripTitles(document);
		// Observe DOM mutations for late‑loaded content (e.g., captcha widgets)
		const mo = new MutationObserver((records) => {
			for (const r of records) {
				if (disposed) break;
				if (r.type === 'childList') {
					for (const n of Array.from(r.addedNodes)) {
						if ((n as Element)?.querySelectorAll) {
							stripTitles(n as unknown as ParentNode);
						}
						if ((n as Element)?.getAttribute && (n as Element).getAttribute('title') !== null) {
							try { (n as Element).removeAttribute('title'); } catch {}
						}
					}
				}
				if (r.type === 'attributes' && r.attributeName === 'title' && r.target) {
					try { (r.target as Element).removeAttribute('title'); } catch {}
				}
			}
		});
		try {
			mo.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['title'] });
		} catch {}
		return () => { disposed = true; try { mo.disconnect(); } catch {} };
	}, []);

	const doLogin = useCallback(async () => {
		setAlert(null);
		const u = (email || "").trim().toLowerCase();
		const p = (password || "").trim();
		if (!u || !p) {
			setAlert({ kind: "error", text: "Email and password are required." });
			return;
		}
		// Check Turnstile completion if configured
		logger.debug("[doLogin] siteKey:", siteKey, "globalTsState:", globalTsState, "tsState:", tsState);
		if (siteKey && globalTsState !== "success") {
			setShowCaptcha(true);
			setAlert({ kind: "warning", text: "Please complete the captcha verification before logging in." });
			return;
		}
		setBusy(true);
		try {
			const headers: Record<string, string> = { "Content-Type": "application/x-www-form-urlencoded", "X-Client-Id": xClient };
			// Optional UA forwarding like Streamlit
			if ((process.env.NEXT_PUBLIC_RT_FORWARD_UA || "").trim() === "1") {
				try { headers["X-Forwarded-User-Agent"] = navigator.userAgent; } catch {}
			}
			// Note: rt_trust cookie is sent automatically by the browser when credentials: "include" is set
			// POST /token same as Streamlit; backend sets cookies and may return pending_2fa token
			const body = new URLSearchParams({ username: u, password: p });
			const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
			const res = await fetch(`${apiBase}/token`, {
				method: "POST",
				headers,
				body,
				credentials: "include",
			});
			if (res.status === 429) {
				const ra = Number(res.headers.get("Retry-After") || "0");
				if (ra > 0) setAlert({ kind: "warning", text: `Too many attempts. Please wait ${ra} seconds and try again.` });
				else setAlert({ kind: "warning", text: "Too many attempts. Please try again later." });
				return;
			}
			if (res.status === 400) {
				let detail: any = null;
				try { detail = await res.json(); } catch {}
				const d = typeof detail === "object" && detail ? detail.detail : detail;
				if (typeof d === "string" && d.toLowerCase().includes("captcha")) setAlert({ kind: "warning", text: d });
				else setAlert({ kind: "error", text: "Incorrect email or password." });
				return;
			}
			if (!res.ok) {
				setAlert({ kind: "error", text: `Login failed${res.status ? ` (${res.status})` : ""}. Please try again.` });
				return;
			}
			// Note: rt_trust cookie is set automatically by the browser via Set-Cookie header
			// (Set-Cookie headers are not accessible to JavaScript for security reasons)
			const data = await res.json().catch(() => ({} as any));
			const tokenType = String(data?.token_type || "").toLowerCase();
			if (tokenType === "pending_2fa") {
				const token = String(data?.access_token || "").trim();
				setPending2(token);
				setAlert({ kind: "warning", text: "Additional verification required." });
				return;
			}
			// Backend has set rt_session and rt_refresh cookies via Set-Cookie headers.
			// No need to call /users/me - the cookies are now being processed by the browser
			// and will be available on the next page. Direct redirect to /resume.
			setAlert({ kind: "success", text: "Logged in successfully." });
			try { localStorage.setItem("__rt_auth_expect_true", String(Date.now())); } catch {}
			emitAuth("logged-in");
			router.replace("/resume");
		} finally {
			setBusy(false);
		}
	}, [email, password, router, xClient, siteKey, tsState]);

	// Streamlit-parity Register: submit /signup with email+password and show success inline; no navigation to a dedicated page
	const doRegister = useCallback(async () => {
		setAlert(null);
		const u = (email || "").trim().toLowerCase();
		const p = (password || "").trim();
		if (!u || !p) {
			setAlert({ kind: "error", text: "Email and password are required." });
			return;
		}
		// If captcha is required and not yet completed, block submission
		if (siteKey && globalTsState !== "success") {
			setShowCaptcha(true);
			setAlert({ kind: "warning", text: "Please complete the captcha verification before registering." });
			return;
		}
		setBusy(true);
		try {
			const headers: Record<string, string> = { "Content-Type": "application/json", "X-Client-Id": xClient };
			if ((process.env.NEXT_PUBLIC_RT_FORWARD_UA || "").trim() === "1") {
				try { headers["X-Forwarded-User-Agent"] = navigator.userAgent; } catch {}
			}
			// Optional fingerprint helper parity
			const visitorId = (() => { try { return (window as any).visitorId || null; } catch { return null; } })();
			const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
			const res = await fetch(`${apiBase}/signup`, {
				method: "POST",
				headers,
				credentials: "include",
				body: JSON.stringify({ username: u, password: p, visitorId }),
			});
			if (res.status === 429) {
				const ra = Number(res.headers.get("Retry-After") || "0");
				if (ra > 0) setAlert({ kind: "warning", text: `Too many signups from this IP. Please wait ${ra} seconds and try again.` });
				else setAlert({ kind: "warning", text: "Too many signups from this IP. Please try again later." });
				return;
			}
			if (res.ok) {
				// Check the response body for email sending status
				let emailStatus: { email_sent?: boolean; email_error?: string | null } | null = null;
				try {
					emailStatus = await res.json();
				} catch {}
				
				if (emailStatus?.email_sent === false || emailStatus?.email_error) {
					setAlert({ 
						kind: "warning", 
						text: `Registration successful, but verification email failed to send: ${emailStatus?.email_error || "Unknown error"}. Use 'Resend verification email' below.` 
					});
				} else {
					setAlert({ kind: "success", text: "Registration successful. Check your email to verify your account." });
				}
				
			// Best-effort: log in to establish a session so 'Resend verification email' can work
			try {
				const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
				const t = await fetch(`${apiBase}/token`, {
					method: "POST",
					headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Client-Id": xClient },
					credentials: "include",
					body: new URLSearchParams({ username: u, password: p }),
				});
				if (t.ok) setUnverifiedMode({ email: u });
			} catch {}
				return;
			}
			// Friendly validation messaging matching Streamlit
			let detail: any = null;
			try { detail = await res.json(); detail = (detail && detail.detail !== undefined) ? detail.detail : detail; } catch { detail = null; }
			if (res.status === 422) {
				setAlert({ kind: "error", text: "Please enter a valid email address and password." });
			} else if (res.status === 400 && typeof detail === "string" && /captcha/i.test(detail)) {
				setAlert({ kind: "warning", text: detail });
			} else if (res.status === 400 && typeof detail === "string" && /disposable/i.test(detail)) {
				setAlert({ kind: "error", text: "Disposable email addresses are not permitted." });
			} else if (res.status === 400 && typeof detail === "string" && /limit|already/i.test(detail)) {
				setAlert({ kind: "error", text: detail });
			} else {
				const txt = detail && typeof detail === "string" ? detail : (await res.text().catch(() => ""));
				setAlert({ kind: "error", text: txt ? String(txt).slice(0, 300) : "Registration failed. Please check your details and try again." });
			}
		} catch (e: any) {
			setAlert({ kind: "error", text: e?.message ? `Registration error: ${String(e.message)}` : "Registration error. Try again." });
		} finally {
			setBusy(false);
		}
	}, [email, password, xClient, siteKey, tsState]);

	const doForgot = useCallback(async () => {
		setBusy(true);
		setAlert(null);
		try {
			const r = await api.post("/users/request-password-reset", { email: (forgotEmail || "").trim().toLowerCase() });
			setAlert({ kind: "success", text: "If an account exists with that email, you will receive a password reset link." });
			setShowForgot(false);
		} catch (e) {
			const err = e as ApiError;
			if (err.status === 429) {
				const ra = (typeof err.detail === "object" && err.detail && (err.detail as any).headers?.["Retry-After"]) || null;
				const raNum = Number(ra || 0);
				const raHdr = raNum > 0 ? raNum : 60;
				setCooldownUntil(Date.now() / 1000 + raHdr);
				setAlert({ kind: "info", text: "Please wait before requesting another reset email." });
			} else {
				setAlert({ kind: "error", text: "Could not send reset link." });
			}
		} finally {
			setBusy(false);
		}
	}, [forgotEmail]);

	const doMfaVerify = useCallback(async () => {
		if (!pending2) return;
		setBusy(true);
		setAlert(null);
		try {
			const body: any = { remember_device: true };
			const code = (mfaCode || "").trim();
			if (code) body.code = code;
			const hdrs: Record<string, string> = { "Content-Type": "application/json", Accept: "application/json", Authorization: `Bearer ${pending2}`, "X-Client-Id": xClient };
			if ((process.env.NEXT_PUBLIC_RT_FORWARD_UA || "").trim() === "1") {
				try { hdrs["X-Forwarded-User-Agent"] = navigator.userAgent; } catch {}
			}
			// Use /api proxy to ensure cookies work (same-origin)
			const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
			const res = await fetch(`${apiBase}/auth/step2`, {
				method: "POST",
				headers: hdrs,
				credentials: "include",
				body: JSON.stringify(body),
			});
			if (res.ok) {
				// Prefer token from response if provided; fallback to cookie session
				let info: any = {};
				try { info = await res.json(); } catch {}
				const tokenType = String(info?.token_type || "").toLowerCase();
				const access = String(info?.access_token || "");
				if (tokenType === "bearer" && access) { setEphemeralAccessToken(access, 2 * 60 * 1000); setAccessToken(access); }
				// Set auth expectation BEFORE calling /users/me to avoid "Auth probe deferred" error
				try { localStorage.setItem("__rt_auth_expect_true", String(Date.now())); } catch {}
				// After step2, rely on cookie-based session
				await api.get("/users/me");
				// Clear 2FA UI and notify app
				setPending2(null);
				setMfaCode("");
				setAlert({ kind: "success", text: "Logged in." });
				emitAuth("logged-in");
				router.replace("/resume");
			} else if (res.status === 400) {
				let det: any = null; try { det = await res.json(); } catch {}
				setAlert({ kind: "error", text: det?.detail === "invalid_code" ? "Invalid code" : "Verification failed" });
			} else if (res.status === 429) {
				setAlert({ kind: "warning", text: "Too many attempts. Please try again later." });
			} else {
				setAlert({ kind: "error", text: "Verification failed. Try again." });
			}
		} catch (e: any) {
			setAlert({ kind: "error", text: e?.message ? `Network error: ${String(e.message)}` : "Network error. Try again." });
		} finally {
			setBusy(false);
		}
	}, [pending2, mfaCode, router, xClient]);

	const doMfaPasskey = useCallback(async () => {
		if (!pending2) return;
		setBusy(true);
		setAlert(null);
		try {
			// 1) options
			const optHeaders: Record<string, string> = { Authorization: `Bearer ${pending2}` };
			if ((process.env.NEXT_PUBLIC_RT_FORWARD_UA || "").trim() === "1") {
				try { optHeaders["X-Forwarded-User-Agent"] = navigator.userAgent; } catch {}
			}
			
			const rr: any = await api.post("/webauthn/authenticate/options", {}, { headers: optHeaders });
			const publicKey: PublicKeyCredentialRequestOptions = (rr?.publicKey as any) ?? ({} as any);
			// decode fields
			if (publicKey.challenge) publicKey.challenge = b64urlToBuf(String(publicKey.challenge));
			if (Array.isArray(publicKey.allowCredentials)) publicKey.allowCredentials = publicKey.allowCredentials.map((c: any) => ({ ...c, id: b64urlToBuf(String(c.id)) }));
			// 2) get
			const cred = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null;
			if (!cred) { setAlert({ kind: "error", text: "Passkey was cancelled or failed." }); return; }
			const res = cred.response as AuthenticatorAssertionResponse;
			const payload = {
				credential: {
					id: cred.id,
					rawId: bufToB64url(cred.rawId),
					type: cred.type,
					response: {
						authenticatorData: bufToB64url(res.authenticatorData),
						clientDataJSON: bufToB64url(res.clientDataJSON),
						signature: bufToB64url(res.signature),
						userHandle: res.userHandle ? bufToB64url(res.userHandle) : null,
					},
				},
				remember_device: true,
			};
			const vHeaders: Record<string, string> = { "Content-Type": "application/json", Authorization: `Bearer ${pending2}` };
			if ((process.env.NEXT_PUBLIC_RT_FORWARD_UA || "").trim() === "1") {
				try { vHeaders["X-Forwarded-User-Agent"] = navigator.userAgent; } catch {}
			}
			
			let rv: Response;
			try {
				const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
				rv = await fetch(`${apiBase}/webauthn/authenticate/verify`, {
					method: "POST",
					headers: vHeaders,
					credentials: "include",
					body: JSON.stringify(payload),
				});
			} catch (fetchErr: any) {
				// Network error during fetch - log and show user-friendly message
				console.error("[Login] WebAuthn verify network error:", fetchErr);
				setAlert({ kind: "error", text: "Network error during authentication. Please check your connection and try again." });
				return;
			}
			
			if (rv.ok) {
				let info: any = {};
				try { info = await rv.json(); } catch {}
				const tokenType = String(info?.token_type || "").toLowerCase();
				const access = String(info?.access_token || "");
				if (tokenType === "bearer" && access) { 
					setEphemeralAccessToken(access, 2 * 60 * 1000); 
					setAccessToken(access); 
				}
				setPending2(null);
				setMfaCode("");
				
				// Set auth expectation and emit logged-in event BEFORE calling /users/me
				// to ensure api.ts doesn't suppress the request
				try { localStorage.setItem("__rt_auth_expect_true", String(Date.now())); } catch {}
				emitAuth("logged-in");
				
				// Verify session with a small delay to ensure cookie propagation
				// This addresses race conditions where the rt_session cookie from the
				// verify response hasn't been fully processed by the browser yet
				await new Promise(resolve => setTimeout(resolve, 100));
				
				try { 
					await api.get("/users/me"); 
					setAlert({ kind: "success", text: "Logged in." });
					router.replace("/resume");
				} catch (meErr: any) {
					// If /users/me fails despite successful WebAuthn verify, log detailed error
					console.warn("[Login] /users/me failed after successful WebAuthn:", meErr);
					// Still navigate to resume - the session cookie is set and page refresh will work
					setAlert({ kind: "success", text: "Logged in." });
					router.replace("/resume");
				}
			} else {
				let det: any = null; try { det = await rv.json(); } catch {}
				const detail = det?.detail || "";
				console.error("[Login] WebAuthn verify failed:", { status: rv.status, detail, fullResponse: det });
				
				// Handle token expiry/invalidity with more helpful message
				if (detail === "invalid_pending_token" || detail === "missing_pending_token") {
					setAlert({ kind: "error", text: "Your login session expired. Please try refreshing the page or logging in again." });
					setPending2(null); // Clear expired token so user can retry from password step
				} else {
					setAlert({ kind: "error", text: detail ? `Verification failed: ${detail}` : "Verification failed." });
				}
			}
		} catch (e: any) {
			// Handle ApiError from api.post specifically
			console.error("[Login] WebAuthn flow exception:", e);
			
			if (e?.name === "ApiError" && e?.detail) {
				const detail = typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
				if (detail === "invalid_pending_token" || detail === "missing_pending_token") {
					setAlert({ kind: "error", text: "Your login session expired. Please try refreshing the page or logging in again." });
					setPending2(null); // Clear expired token
				} else {
					setAlert({ kind: "error", text: `Authentication failed: ${detail}` });
				}
			} else {
				setAlert({ kind: "error", text: e?.message ? `Network error: ${String(e.message)}` : "Network error. Try again." });
			}
		} finally {
			setBusy(false);
		}
	}, [pending2, router, xClient]);

	const resendVerify = useCallback(async () => {
		if (!unverifiedMode) return;
		setResendBusy(true);
		setAlert(null);
		try {
			await api.post("/users/request-verification-token", {});
			setAlert({ kind: "success", text: "Verification email sent. Check your inbox." });
		} catch (e) {
			const err = e as ApiError;
			if (err.status === 429) {
				// Respect Retry-After if present
				let retry = 60;
				try {
					const ra = (err.detail as any)?.headers?.["Retry-After"] ?? null;
					retry = Number(ra || retry) || retry;
				} catch {}
				setUnverifiedMode((m) => (m ? { ...m, cooldownUntil: Math.floor(Date.now() / 1000) + retry } : m));
				setAlert({ kind: "info", text: "You're sending requests too fast. Please wait and try again." });
			} else {
				setAlert({ kind: "error", text: "Could not send verification email." });
			}
		} finally {
			setResendBusy(false);
		}
	}, [unverifiedMode]);

	const doLogout = useCallback(() => {
		// Clear client-side fields, emit logout event, and perform full-page navigation to root for privacy
		try { clearAccessToken(); clearEphemeralAccessToken(); } catch {}
		try {
			// Clear local input store to prevent sensitive data from being visible
			localStorage.setItem("__rt_resume_text", "");
			localStorage.setItem("__rt_jd_text", "");
			localStorage.setItem("__rt_resume_ts", JSON.stringify(0));
			localStorage.setItem("__rt_jd_ts", JSON.stringify(0));
		} catch {}
		try { emitAuth("logged-out"); } catch {}
		// Full-page reload to root ensures all state (including React component state) is cleared
		window.location.href = "/";
	}, [emitAuth]);

	return (
		<div className="space-y-3">
			<h1 className="text-xl font-semibold">Login / Register</h1>
			{alert && (
				<div className={{ info: "text-blue-400", success: "text-green-400", error: "text-red-400", warning: "text-yellow-400" }[alert.kind]}>{alert.text}</div>
			)}
			{!pending2 && !unverifiedMode && (
				<form
					onSubmit={(e) => { e.preventDefault(); if (!busy) doLogin(); }}
					method="post"
					noValidate
					className="space-y-3"
				>
					<label className="block" htmlFor="login-email">Email</label>
					<input id="login-email" type="email" name="username" autoComplete="username" className="w-full rounded border border-slate-600 bg-transparent px-3 py-2" value={email} onChange={(e) => setEmail(e.target.value)} />
					<label className="block" htmlFor="login-password">Password</label>
					<div className="relative">
						<input id="login-password" name="current-password" autoComplete="current-password" type={showPw ? "text" : "password"} className="w-full rounded border border-slate-600 bg-transparent px-3 py-2 pr-10" value={password} onChange={(e) => setPassword(e.target.value)} />
						<button
							type="button"
							aria-label={showPw ? "Hide password" : "Show password"}
							className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-300 hover:text-white p-1 rounded btn-plain"
							onClick={() => setShowPw((v) => !v)}
						>
							{showPw ? <EyeOffIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
						</button>
					</div>
					{siteKey && showCaptcha ? (
						<div className="my-2">
							<div className="h-[147px] mb-4">
								<TurnstileWidget siteKey={siteKey} onState={handleTsStateChange} />
							</div>
							{tsState === "error" && (
								<div className="mt-2 rounded border border-yellow-600 bg-yellow-900/30 p-3 text-yellow-300 text-sm">Captcha unavailable. Check ad-blockers and reload.</div>
							)}
						</div>
					) : null}
					{stackedButtons ? (
						<div className="space-y-2 mt-4">
							<button type="submit" disabled={busy} className="w-full rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 transition-colors px-3 py-2.5 disabled:opacity-50">Login</button>
							<button type="button" disabled={busy} onClick={doRegister} className="w-full rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 transition-colors px-3 py-2.5">Register</button>
						</div>
					) : (
						<div className="grid grid-cols-2 gap-3 mt-4">
							<button type="submit" disabled={busy} className="rounded px-3 py-2.5">Login</button>
							<button type="button" disabled={busy} onClick={doRegister} className="rounded px-3 py-2.5">Register</button>
						</div>
					)}
					<div>
						<button type="button" disabled={busy} onClick={() => { setShowForgot(true); setForgotEmail(email); }} className="w-full text-left underline btn-plain">Forgot password?</button>
						{showForgot && (
							<div className="mt-2 rounded border border-slate-700 p-3">
								<div className="font-medium mb-2">Reset password</div>
								<label className="block" htmlFor="forgot-email">Email</label>
								<input id="forgot-email" type="email" autoComplete="username" className="w-full rounded border border-slate-600 bg-transparent px-3 py-2" value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)} />
								<button type="button" disabled={busy || Boolean(cooldownUntil && Date.now()/1000 < (cooldownUntil ?? 0))} onClick={doForgot} className="mt-2 w-full">Send reset link</button>
							</div>
						)}
					</div>
				</form>
			)}
			{unverifiedMode && (
				<div className="space-y-2">
					{unverifiedMode.email && <div className="text-slate-300">Welcome, {unverifiedMode.email}</div>}
					<div className="text-blue-400">Please verify your email to continue.</div>
					<div className="grid grid-cols-2 gap-3">
						<button disabled={resendBusy || Boolean(unverifiedMode.cooldownUntil && Date.now()/1000 < (unverifiedMode.cooldownUntil ?? 0))} onClick={resendVerify} className="rounded bg-slate-700 px-3 py-2 disabled:opacity-50">Resend verification email</button>
						<button onClick={doLogout} className="rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 transition-colors px-3 py-2.5">Logout</button>
					</div>
				</div>
			)}
			{pending2 && (
				<div className="space-y-2">
					<label className="block">6‑digit code</label>
					<input maxLength={6} placeholder="123456" className="w-full rounded border border-slate-600 bg-transparent px-3 py-2" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} />
					<div className="grid grid-cols-2 gap-3 mt-4">
						<button disabled={busy} onClick={doMfaVerify} className="rounded bg-blue-600 px-3 py-2 disabled:opacity-50">Verify</button>
						<button disabled={busy} onClick={doMfaPasskey} className="rounded bg-slate-700 px-3 py-2 disabled:opacity-50">Use passkey</button>
					</div>
					<div>
						<button disabled={busy} onClick={async () => {
							if (!pending2) return;
						setBusy(true); setAlert(null);
						try {
							const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
							const r = await fetch(`${apiBase}/auth/otp/email/request`, {
								method: "POST",
								headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: `Bearer ${pending2}`, "X-Client-Id": xClient },
								credentials: "include",
								body: JSON.stringify({}),
							});
							if (r.ok) setAlert({ kind: "info", text: "If enabled, a code has been sent to your email." });
								else if (r.status === 429) setAlert({ kind: "warning", text: "Too many requests. Try later." });
								else setAlert({ kind: "error", text: `Email code failed (${r.status}).` });
							} catch (e: any) { setAlert({ kind: "error", text: e?.message ? `Network error: ${String(e.message)}` : "Network error. Try again." }); }
							finally { setBusy(false); }
						}} className="w-full text-left underline">Email me a code</button>
					</div>
				</div>
			)}
		</div>
	);
}
