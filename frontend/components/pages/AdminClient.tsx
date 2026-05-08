"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api, { setAuthEstablished } from "@/lib/api";
import { getClientId } from "@/lib/client";
import { MODEL_OPTIONS } from "@/components/resume/models";
import { b64urlToBuf, bufToB64url } from "@/lib/client";
import UserTrialManager from "./UserTrialManager";

type Me = { role?: string; id?: string | number; email?: string } | null;

type PendingAction = {
	name: string;
	method: "GET" | "POST" | "PUT" | "DELETE";
	path: string;
	json?: any;
	params?: Record<string, string>;
};

export default function AdminClient({ initialMe }: { initialMe?: Me }) {
	const [me, setMe] = useState<Me>(initialMe || null);
	const [loading, setLoading] = useState(!initialMe);
	const [alert, setAlert] = useState<{ kind: "info" | "success" | "warning" | "error"; text: string } | null>(null);
	const [authPending, setAuthPending] = useState<boolean>(!initialMe);
	const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(initialMe ? true : null);

	// Step-up state
	const [showStepup, setShowStepup] = useState(false);
	const [stepupPending, setStepupPending] = useState(false);
	const [stepupToken, setStepupToken] = useState<string | null>(null);
	const [method, setMethod] = useState<"Email code" | "Authenticator app" | "Passkey">("Authenticator app");
	const [emailCode, setEmailCode] = useState("");
	const [totpCode, setTotpCode] = useState("");

	const pendingRef = useRef<PendingAction | null>(null);

	useEffect(() => {
		// Skip user fetch if SSR already provided user data (avoid cookie hydration race)
		if (initialMe) {
			setAuthEstablished(true);
			setAuthPending(false);
			setIsLoggedIn(true);
			return;
		}
		let cancelled = false;
		(async () => {
			try {
				const u = await api.get<Me>("/users/me");
				if (!cancelled) {
					setMe(u);
					setIsLoggedIn(true);
				}
			} catch { 
				if (!cancelled) {
					setMe(null);
					setIsLoggedIn(false);
				}
			}
			finally { 
				if (!cancelled) {
					setLoading(false);
					setAuthPending(false);
				}
			}
		})();
		return () => { cancelled = true; };
	}, [initialMe]);

	// Client-side redirect for /admin route (protected workspace)
	useEffect(() => {
		if (authPending) return; // Wait for auth check to complete
		if (isLoggedIn === false && typeof window !== 'undefined' && window.location.pathname === '/admin') {
			// Redirect logged-out users to homepage
			window.location.href = '/';
		}
	}, [authPending, isLoggedIn]);

	const isAdmin = useMemo(() => {
		return (me?.role || "").toLowerCase() === "admin";
	}, [me]);

		const callWithStepup = useCallback(async (pa: PendingAction, promptStepup: boolean): Promise<Response | null> => {
		const base = process.env.NEXT_PUBLIC_API_BASE_URL || "";
		const url = new URL(`${base}${pa.path}`);
		if (pa.params) Object.entries(pa.params).forEach(([k, v]) => url.searchParams.set(k, v));
		const headers: Record<string, string> = { "Accept": "application/json", "X-Client-Id": getClientId() };
		if (stepupToken) headers["X-Stepup-Token"] = stepupToken;
		if (pa.method !== "GET") headers["Content-Type"] = "application/json";
		const res = await fetch(url.toString(), {
			method: pa.method,
			credentials: "include",
			headers,
			body: pa.method === "GET" ? undefined : JSON.stringify(pa.json ?? {}),
		});
		if (res.status === 401 || res.status === 403) {
			let detail: any = undefined;
			try { detail = await res.clone().json(); } catch { try { detail = await res.clone().text(); } catch {} }
			const val = typeof detail === "string" ? detail : (detail?.detail ?? undefined);
			
			// Silently ignore auth probe deferral - this is intentional optimization
			if (val && (val.includes("Auth not established") || val.includes("Auth probe deferred"))) {
				return null;
			}
			
			const needs = val === "needs_stepup" || val === "admin_requires_2fa";
			if (needs) {
				if (val === "admin_requires_2fa") {
					setAlert({ kind: "error", text: "Admin account requires 2FA enrollment. Set up an authenticator app or passkey in Security, then retry." });
					return res;
				}
				if (promptStepup) {
					setAlert({ kind: "info", text: "Please complete 2FA step-up authentication to continue." });
					setShowStepup(true);
					setStepupPending(true);
					pendingRef.current = pa;
				} else {
					setAlert({ kind: "warning", text: "This action requires 2FA step-up authentication." });
				}
				return null;
			}
		}
		return res;
	}, [stepupToken]);

		const sendEmailCode = useCallback(async () => {
		try {
				const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/otp/email/request`, { method: "POST", credentials: "include", headers: { "X-Client-Id": getClientId() } });
			if (r.ok) {
				try {
					const data = await r.json().catch(() => ({}));
					if (data?.captcha === "required") setAlert({ kind: "warning", text: "Captcha required. Complete the login captcha and retry." });
					else if (data?.captcha === "failed") setAlert({ kind: "error", text: "Captcha verification failed. Please retry." });
					else if (data?.dev_code) setAlert({ kind: "info", text: `Dev-only: code ${data.dev_code}` });
					else setAlert({ kind: "info", text: "If email is configured, a code will arrive shortly." });
				} catch { setAlert({ kind: "info", text: "If email is configured, a code will arrive shortly." }); }
			} else {
				const t = await r.text();
				setAlert({ kind: "error", text: `Couldn't send email code: ${t}` });
			}
		} catch (e: any) {
			setAlert({ kind: "error", text: String(e?.message || e) });
		}
	}, []);

		const confirmStepup = useCallback(async () => {
		// Handle Passkey authentication separately
		if (method === "Passkey") {
			setAlert({ kind: "info", text: "Requesting passkey authentication..." });
			try {
				// 1) Get authentication options
				const rr: any = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/stepup/webauthn/options`, {
					method: "POST",
					credentials: "include",
					headers: { "Content-Type": "application/json", "X-Client-Id": getClientId() },
				});
				if (!rr.ok) {
					const errText = await rr.text();
					setAlert({ kind: "error", text: `Failed to get passkey options: ${errText}` });
					setStepupPending(true);
					return;
				}
				const opts = await rr.json();
				const publicKey: PublicKeyCredentialRequestOptions = (opts?.publicKey as any) ?? ({} as any);
				
				// Decode Base64URL fields
				if (publicKey.challenge) publicKey.challenge = b64urlToBuf(String(publicKey.challenge));
				if (Array.isArray(publicKey.allowCredentials)) {
					publicKey.allowCredentials = publicKey.allowCredentials.map((c: any) => ({ 
						...c, 
						id: b64urlToBuf(String(c.id)) 
					}));
				}
				
				// 2) Get credential from user
				const cred = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null;
				if (!cred) {
					setAlert({ kind: "error", text: "Passkey authentication was cancelled." });
					setStepupPending(true);
					return;
				}
				
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
				};
				
				// 3) Verify the credential
				const vr = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/stepup/webauthn/verify`, {
					method: "POST",
					credentials: "include",
					headers: { "Content-Type": "application/json", "X-Client-Id": getClientId() },
					body: JSON.stringify(payload),
				});
				
				if (vr.status === 200) {
					const tok = vr.headers.get("X-Stepup-Token");
					if (tok) setStepupToken(tok);
					setAlert({ kind: "success", text: "Passkey verified! Completing action..." });
					setShowStepup(false);
					setStepupPending(false);
					
					// Retry pending action
					const pa = pendingRef.current;
					pendingRef.current = null;
					if (pa) {
						try {
							await callWithStepup(pa, false);
						} catch (err) {
							setAlert({ kind: "error", text: `Failed to complete action: ${err}` });
						}
					}
				} else {
					const errText = await vr.text();
					setAlert({ kind: "error", text: `Passkey verification failed: ${errText}` });
					setStepupPending(true);
				}
			} catch (e: any) {
				setAlert({ kind: "error", text: `Passkey error: ${String(e?.message || e)}` });
				setStepupPending(true);
			}
			return;
		}
		
		// Handle Email code and Authenticator app
		const payload: Record<string, string> = {};
		if (method === "Email code" && emailCode.trim()) payload.email_otp_code = emailCode.trim();
		if (method === "Authenticator app" && totpCode.trim()) payload.totp_code = totpCode.trim();
		if (!Object.keys(payload).length) {
			setAlert({ kind: "warning", text: "Enter a code or choose a method." });
			setStepupPending(true);
			return;
		}
		setAlert({ kind: "info", text: "Verifying 2FA code..." });
		try {
					const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/stepup/start`, {
				method: "POST",
				credentials: "include",
						headers: { "Content-Type": "application/json", "X-Client-Id": getClientId() },
				body: JSON.stringify(payload),
			});
			if (r.status === 200) {
				const tok = r.headers.get("X-Stepup-Token");
				// If readable via CORS, use the header; otherwise fall back to the HttpOnly cookie the server set
				if (tok) setStepupToken(tok);
				setAlert({ kind: "success", text: "2FA verified! Completing action..." });
				setShowStepup(false);
				setStepupPending(false);
				// Retry pending action once regardless; backend accepts header or cookie
				const pa = pendingRef.current;
				pendingRef.current = null;
				if (pa) {
					try {
						await callWithStepup(pa, false);
					} catch (err) {
						setAlert({ kind: "error", text: `Failed to complete action: ${err}` });
					}
				}
			} else {
				const t = await r.text();
				setAlert({ kind: "error", text: `Verification failed: ${t}` });
				setStepupPending(true);
			}
		} catch (e: any) {
			setAlert({ kind: "error", text: String(e?.message || e) });
			setStepupPending(true);
		}
	}, [method, emailCode, totpCode, callWithStepup]);

	// Sections state + handlers
	// Single Gift
	const [giftIdent, setGiftIdent] = useState<"Email" | "User ID">("Email");
	const [giftEmail, setGiftEmail] = useState("");
	const [giftUserId, setGiftUserId] = useState("");
	const [giftAmountUsd, setGiftAmountUsd] = useState(5.0);
	const [giftReason, setGiftReason] = useState("");
	const [giftIsTrial, setGiftIsTrial] = useState(false);
	const [giftSendEmail, setGiftSendEmail] = useState(true);

	const onGift = useCallback(async () => {
		// Generate a new idempotency key for each gift action
		const idemKey = typeof crypto !== 'undefined' ? crypto.randomUUID() : null;
		
		const payload: any = {
			by_email: giftIdent === "Email" ? (giftEmail || null) : null,
			by_user_id: giftIdent === "User ID" ? (giftUserId || null) : null,
			amount_cents: Math.round(giftAmountUsd * 100),
			reason: giftReason || null,
			idempotency_key: idemKey,
			is_trial: giftIsTrial,
			send_email: giftSendEmail,
		};
		const pa: PendingAction = { name: "gift_single", method: "POST", path: "/admin/credits/gift", json: payload };
		const r = await callWithStepup(pa, true);
		if (r === null) return; // awaiting stepup
		if (r.status === 200) {
			const d = await r.json();
			const creditType = giftIsTrial ? "trial" : "regular";
			const emailStatus = d.email_sent === true ? " (email sent)" : d.email_sent === false ? " (email failed)" : "";
			setAlert({ kind: "success", text: `GIFT OK (${creditType}) → New balance: $${d.new_balance_usd}${emailStatus}` });
			// Only broadcast balance change if gifting self (recipient matches admin)
			const recipientEmail = giftIdent === "Email" ? giftEmail?.toLowerCase().trim() : null;
			const recipientUserId = giftIdent === "User ID" ? giftUserId?.trim() : null;
			const adminEmail = me?.email?.toLowerCase().trim();
			const adminUserId = String(me?.id || '').trim();
			const isSelfGift = (recipientEmail && recipientEmail === adminEmail) || (recipientUserId && recipientUserId === adminUserId);
			if (isSelfGift) {
				try { window.dispatchEvent(new CustomEvent("rt-balance", { detail: { balance_usd: d.new_balance_usd, balance_cents: d.new_balance_cents, currency: "USD" } })); } catch {}
			}
		} else if (r.status === 401 || r.status === 403) {
			let d: any = null; 
			let errorText = "";
			try { 
				const text = await r.text();
				try { d = JSON.parse(text); } catch { errorText = text; }
			} catch {}
			if ((d?.detail ?? d) === "admin_requires_2fa") {
				setAlert({ kind: "error", text: "Admin requires 2FA enrollment. Open the Security page to set up your authenticator, then retry." });
			} else {
				setAlert({ kind: "error", text: `Error ${r.status}: ${errorText || JSON.stringify(d)}` });
			}
		} else {
			const errorText = await r.text();
			setAlert({ kind: "error", text: `Error ${r.status}: ${errorText}` });
		}
	}, [giftIdent, giftEmail, giftUserId, giftAmountUsd, giftReason, giftIsTrial, giftSendEmail, callWithStepup]);

	// Signup Trial Grant
	const [sgLoaded, setSgLoaded] = useState(false);
	const [sg, setSg] = useState<any | null>(null);
	const [sgError, setSgError] = useState<string | null>(null);
	useEffect(() => {
		(async () => {
			if (!isAdmin) return;
			setSgLoaded(false);
			setSgError(null);
			setSg(null); // Clear previous data
			try {
				const r = await callWithStepup({ name: "sg_fetch", method: "GET", path: "/admin/credits/signup-grant" }, true);
				if (!r) {
					// Step-up needed - will be prompted, don't show error
					setSgLoaded(true);
					setSgError(null);
					return;
				}
				if (r.status === 200) {
					const data = await r.json();
					setSg(data);
					setSgError(null);
				} else if (r.status === 401 || r.status === 403) {
					let d: any = null; try { d = await r.json(); } catch {}
					const detail = (d?.detail ?? d);
					if (detail === "admin_requires_2fa") {
						setSgError("Admin accounts require 2FA enrollment. Go to Security page and set up an authenticator app or passkey first.");
					} else if (detail === "needs_stepup") {
						// Step-up will be prompted by callWithStepup, no error
						setSgError(null);
					} else {
						// Other auth errors - don't show, step-up handles it
						setSgError(null);
					}
				} else {
					// Server error (500, 404, etc) or network error (status 0) - extract error details
					let errorDetail = "";
					try {
						const errorData = await r.json();
						errorDetail = errorData?.detail || JSON.stringify(errorData);
					} catch {
						try {
							errorDetail = await r.text();
						} catch {
							errorDetail = r.statusText || "Unknown error";
						}
					}
					const statusText = r.status === 0 ? "Network/CORS error" : `HTTP ${r.status}`;
					setSgError(`${statusText}: ${errorDetail}`);
				}
		} catch (e: any) {
			console.error("[AdminClient] Signup grant fetch error:", e);
			const errorMsg = e?.message || String(e);
			// "Failed to fetch" can be either network error OR server crash (500)
			// Since we can't distinguish, show a generic error with both possibilities
			if (errorMsg === "Failed to fetch") {
				setSgError("Unable to load settings. This could be a network issue, server error, or CORS problem. Check browser console for details, then try refreshing the page.");
			} else if (errorMsg.includes("NetworkError")) {
				setSgError("Network error: Cannot reach server. Check your internet connection.");
			} else if (errorMsg.includes("CORS")) {
				setSgError("CORS error: Cross-origin request blocked. Check server configuration.");
			} else {
				setSgError(`Error loading settings: ${errorMsg}`);
			}
		} finally { setSgLoaded(true); }
		})();
	}, [isAdmin, stepupToken, callWithStepup]);

	const [sgEnabled, setSgEnabled] = useState(true);
	const [sgUsd, setSgUsd] = useState<number | string>(1.0);
	const [sgIpDays, setSgIpDays] = useState<number | string>(1);
	const [sgEmailDays, setSgEmailDays] = useState<number | string>(7);
	const [sgFpDays, setSgFpDays] = useState<number | string>(30);
	const [sgTrialDurationDays, setSgTrialDurationDays] = useState<number | null>(null);
	const [sgTrialEndDate, setSgTrialEndDate] = useState<string>("");
	const [sgTrialModelsSet, setSgTrialModelsSet] = useState<Set<string>>(new Set());
	const [sgTrialTotalSlots, setSgTrialTotalSlots] = useState<number | null>(null);
	const [sgTrialResetSlots, setSgTrialResetSlots] = useState(false);
	const [sgTrialClaimedCount, setSgTrialClaimedCount] = useState<number | null>(null);
	
	// Fetch trial availability to show current count
	useEffect(() => {
		if (!isAdmin || !sgTrialTotalSlots) return;
		let cancelled = false;
		(async () => {
			try {
				const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/public/trial-availability`);
				if (r.ok && !cancelled) {
					const data = await r.json().catch(() => null);
					if (data && typeof data.total === 'number' && typeof data.available === 'number') {
						setSgTrialClaimedCount(data.total - data.available);
					}
				}
			} catch {}
		})();
		return () => { cancelled = true; };
	}, [isAdmin, sgTrialTotalSlots, sg]);
	
	useEffect(() => {
		if (!sg) return;
		setSgEnabled(Boolean(sg.enable_signup_grant ?? true));
		setSgUsd(Number((sg.signup_grant_cents ?? 100) / 100));
		setSgIpDays(Number(sg.grant_window_ip_days ?? 1));
		setSgEmailDays(Number(sg.grant_window_email_days ?? 7));
		setSgFpDays(Number(sg.grant_window_fingerprint_days ?? 30));
		setSgTrialDurationDays(sg.trial_duration_days ?? null);
		setSgTrialEndDate(sg.trial_end_date ?? "");
		setSgTrialModelsSet(new Set(Array.isArray(sg.trial_models) ? sg.trial_models : []));
		setSgTrialTotalSlots(sg.trial_total_slots ?? null);
		setSgTrialResetSlots(false);
	}, [sg]);

	const onSaveSignupGrant = useCallback(async () => {
		const payload: any = {
			enable_signup_grant: Boolean(sgEnabled),
			signup_grant_cents: Math.round(Number(sgUsd) * 100),
			grant_window_ip_days: Number(sgIpDays),
			grant_window_email_days: Number(sgEmailDays),
			grant_window_fingerprint_days: Number(sgFpDays),
		};
		
		// Add trial duration or end date (mutually exclusive)
		if (sgTrialDurationDays && sgTrialDurationDays > 0) {
			payload.trial_duration_days = Number(sgTrialDurationDays);
			payload.trial_end_date = null;
		} else if (sgTrialEndDate && sgTrialEndDate.trim()) {
			payload.trial_end_date = sgTrialEndDate.trim();
			payload.trial_duration_days = null;
		} else {
			payload.trial_duration_days = null;
			payload.trial_end_date = null;
		}
		
		// Add trial models (from Set)
		if (sgTrialModelsSet.size > 0) {
			payload.trial_models = Array.from(sgTrialModelsSet);
		} else {
			payload.trial_models = null;
		}
		
		// Add trial slots
		if (sgTrialTotalSlots && sgTrialTotalSlots > 0) {
			payload.trial_total_slots = Number(sgTrialTotalSlots);
		} else {
			payload.trial_total_slots = null;
		}
		
		// Include reset flag
		payload.trial_slots_reset_on_save = Boolean(sgTrialResetSlots);
		
		setAlert({ kind: "info", text: "Saving trial settings..." });
		const r = await callWithStepup({ name: "signup_grant_save", method: "POST", path: "/admin/credits/signup-grant", json: payload }, true);
		if (r === null) return; // Step-up needed or failed
		if (r.status === 200) {
			try {
				const out = await r.json();
				const cents = Number(out.signup_grant_cents ?? 0);
				const modelsText = sgTrialModelsSet.size > 0 ? `; Models: ${sgTrialModelsSet.size}/${MODEL_OPTIONS.length}` : "; Models: All";
				setAlert({ kind: "success", text: `Saved. Trial: $${(cents/100).toFixed(2)}${modelsText}; Enabled: ${String(out.enable_signup_grant)}` });
				// Reset the reset flag after successful save and refetch trial count
				setSgTrialResetSlots(false);
				// Refetch trial availability to update claimed count
				if (sgTrialTotalSlots) {
					try {
						const r2 = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/public/trial-availability`);
						if (r2.ok) {
							const data = await r2.json().catch(() => null);
							if (data && typeof data.total === 'number' && typeof data.available === 'number') {
								setSgTrialClaimedCount(data.total - data.available);
							}
						}
					} catch {}
				}
			} catch { setAlert({ kind: "success", text: "Saved." }); }
		} else {
			const errorText = await r.text().catch(() => "Unknown error");
			setAlert({ kind: "error", text: `Save failed (HTTP ${r.status}): ${errorText || r.statusText}` });
		}
	}, [sgEnabled, sgUsd, sgIpDays, sgEmailDays, sgFpDays, sgTrialDurationDays, sgTrialEndDate, sgTrialModelsSet, sgTrialTotalSlots, sgTrialResetSlots, callWithStepup]);

	// Bulk Gift
	const [bulkCsv, setBulkCsv] = useState("alice@example.com,5.00,false,summer-promo\nbob@example.com,10.00,true");
	const [bulkDry, setBulkDry] = useState(true);
	const [bulkSendEmail, setBulkSendEmail] = useState(true);

	const onRunBulk = useCallback(async () => {
		// Auto-generate idempotency prefix for this bulk operation
		const bulkPrefix = `bulk-${(me?.email || "admin").toLowerCase()}-${String(me?.id ?? "me")}-${Date.now()}`;
		
		const items: Array<{ email: string; amount_cents: number; is_trial: boolean; reason?: string | null }> = [];
		for (const ln of bulkCsv.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)) {
			const parts = ln.split(",").map((p) => p.trim());
			if (parts.length < 2) continue;
			const email = parts[0];
			const amt = Number(parts[1]);
			if (!isFinite(amt)) { setAlert({ kind: "error", text: `Bad amount: ${parts[1]} in row '${ln}'` }); return; }
			const cents = Math.round(amt * 100);
			// Parse is_trial (column 3, optional, defaults to false)
			const isTrial = parts.length > 2 && (parts[2].toLowerCase() === 'true' || parts[2] === '1');
			// Parse reason (column 4 if is_trial present, otherwise column 3)
			const reasonIdx = parts.length > 2 && (parts[2].toLowerCase() === 'true' || parts[2].toLowerCase() === 'false' || parts[2] === '1' || parts[2] === '0') ? 3 : 2;
			const reason = parts[reasonIdx] ? parts[reasonIdx] : null;
			items.push({ email, amount_cents: cents, is_trial: isTrial, reason });
		}
		if (!items.length) { setAlert({ kind: "warning", text: "Nothing to send." }); return; }
		const payload = { items, dry_run: Boolean(bulkDry), idempotency_prefix: (bulkPrefix || null), send_email: bulkSendEmail };
		const r = await callWithStepup({ name: "gift_bulk", method: "POST", path: "/admin/credits/gift-bulk", json: payload }, true);
		if (r === null) { setAlert({ kind: "info", text: "Confirm the admin action above, then click Run bulk again." }); return; }
		if (r.status === 200) {
			const out = await r.json();
			setAlert({ kind: "success", text: `Bulk result: ${out.credited_rows} credited, ${out.failed_rows} failed / ${out.total_rows}` });
			setBulkDetails(out.details || []);
			// Only trigger balance refresh if admin gifted themselves
			const adminEmail = me?.email?.toLowerCase().trim();
			const adminUserId = String(me?.id || '').trim();
			const selfGifted = items.some(item => {
				const itemEmail = item.email?.toLowerCase().trim();
				return (adminEmail && itemEmail === adminEmail);
			});
			if (selfGifted) {
				try { window.dispatchEvent(new CustomEvent("rt-balance", { detail: {} })); } catch {}
			}
		} else {
			setAlert({ kind: "error", text: `Error ${r.status}: ${await r.text()}` });
		}
	}, [bulkCsv, bulkDry, bulkSendEmail, me, callWithStepup]);
	const [bulkDetails, setBulkDetails] = useState<any[]>([]);

	// Reverse Credit
	const [revId, setRevId] = useState("");
	const [revReason, setRevReason] = useState("");
	const onReverse = useCallback(async () => {
		if (!revId.trim()) { setAlert({ kind: "warning", text: "Enter a Ledger ID" }); return; }
		const payload = { credit_ledger_id: revId.trim(), reason: revReason || null };
		const r = await callWithStepup({ name: "reverse", method: "POST", path: "/admin/credits/reverse", json: payload }, true);
		if (r === null) { setAlert({ kind: "info", text: "Confirm the admin action above, then click Reverse again." }); return; }
		if (r.status === 200) {
			const d = await r.json();
			setAlert({ kind: "success", text: `REVERSED → New balance: $${d.new_balance_usd ?? '?'}` });
			// Note: We don't broadcast balance change here since we can't easily determine
			// if the reversed credit belongs to the admin. Admins should refresh if needed.
		} else {
			setAlert({ kind: "error", text: `Error ${r.status}: ${await r.text()}` });
		}
	}, [revId, revReason, callWithStepup]);

	// Balance & Ledger Inspector
	const [ident2, setIdent2] = useState<"Email" | "User ID">("Email");
	const [email2, setEmail2] = useState("");
	const [userId2, setUserId2] = useState("");
	const [inspectOut, setInspectOut] = useState<string>("");
		const fetchInspect = useCallback(async (which: "balance" | "ledger") => {
			const params: Record<string, string> = {};
			if (ident2 === "Email") params.email = email2; else params.user_id = userId2;
			const r = await callWithStepup({ name: `inspect_${which}`, method: "GET", path: `/admin/credits/${which}`, params }, true);
		if (r === null) { setAlert({ kind: "info", text: "Confirm the admin action above, then click again." }); return; }
		try {
			const js = await r.json();
			setInspectOut(JSON.stringify(js, null, 2));
		} catch { setInspectOut(await r.text()); }
	}, [ident2, email2, userId2, callWithStepup]);

	// Simulate Purchase / Refund
	const [ident3, setIdent3] = useState<"Email" | "User ID">("Email");
	const [email3, setEmail3] = useState("");
	const [userId3, setUserId3] = useState("");
	const [amountUsdSim, setAmountUsdSim] = useState(5.0);
	
	const onSim = useCallback(async (kind: "sim-purchase" | "sim-refund") => {
		// Generate a new idempotency key for each simulation action
		const idemKey = typeof crypto !== 'undefined' ? crypto.randomUUID() : null;
		const simPayload: any = { amount_cents: Math.round(amountUsdSim * 100), idempotency_key: idemKey };
		if (ident3 === "Email") simPayload.by_email = email3; else simPayload.by_user_id = userId3;
		
		const r = await callWithStepup({ name: kind, method: "POST", path: `/admin/credits/${kind}`, json: simPayload }, true);
		if (r === null) { setAlert({ kind: "info", text: "Confirm the admin action above, then click again." }); return; }
		try { 
			const js = await r.json(); 
			setInspectOut(JSON.stringify(js, null, 2)); 
			// Only broadcast balance change if simulating on self
			const recipientEmail = ident3 === "Email" ? email3?.toLowerCase().trim() : null;
			const recipientUserId = ident3 === "User ID" ? userId3?.trim() : null;
			const adminEmail = me?.email?.toLowerCase().trim();
			const adminUserId = String(me?.id || '').trim();
			const isSelf = (recipientEmail && recipientEmail === adminEmail) || (recipientUserId && recipientUserId === adminUserId);
			if (isSelf) {
				try { window.dispatchEvent(new CustomEvent("rt-balance", { detail: {} })); } catch {}
			}
		} catch { setInspectOut(await r.text()); }
	}, [amountUsdSim, ident3, email3, userId3, me, callWithStepup]);

	// Users List
	const [users, setUsers] = useState<any[]>([]);
	const [usersLoading, setUsersLoading] = useState(false);
	const [userSearch, setUserSearch] = useState("");
	const [usersPage, setUsersPage] = useState(0);
	
	const fetchUsers = useCallback(async () => {
		setUsersLoading(true);
		try {
			const params: any = { limit: 20, offset: usersPage * 20 };
			if (userSearch) params.search = userSearch;
			
			const r = await callWithStepup({ name: "list_users", method: "GET", path: "/admin/users", params }, true);
			if (r && r.ok) {
				const data = await r.json();
				setUsers(data);
			}
		} catch (e) {
			console.error(e);
		} finally {
			setUsersLoading(false);
		}
	}, [usersPage, userSearch, callWithStepup]);

	useEffect(() => {
		if (isAdmin) fetchUsers();
	}, [isAdmin, usersPage, fetchUsers]);

    const onSetTrialMode = useCallback(async (userId: number, override: "enabled" | "disabled" | null) => {
        const r = await callWithStepup({ 
            name: "set_trial_mode", 
            method: "POST", 
            path: `/admin/users/${userId}/trial-mode`, 
            json: { override } 
        }, true);
        
        if (r && r.ok) {
            setAlert({ kind: "success", text: `Trial mode updated for user ${userId}` });
            fetchUsers(); // Refresh list
        }
    }, [callWithStepup, fetchUsers]);


	if (loading) return null;
	if (!isAdmin) return <div className="mx-auto max-w-4xl text-yellow-300 px-4 md:px-0">You need to be logged in as an admin to use this page.</div>;

	return (
		<div className="mx-auto max-w-4xl space-y-4 px-4 md:px-0">
			<h1 className="text-2xl font-semibold">Admin</h1>

			{alert && (
				<div className={{ info: "text-blue-400", success: "text-green-400", warning: "text-yellow-400", error: "text-red-400" }[alert.kind]}>{alert.text}</div>
			)}

		{/* Step-up box */}
		<div className="rounded border border-slate-700 p-3 space-y-2">
			<h3 className="font-medium">Confirm admin action</h3>
			<div className="text-slate-400 text-sm">For security, confirm with a second factor.</div>
			<div className="flex flex-col md:flex-row gap-4 md:items-center">
				<label className="inline-flex items-center gap-2">
					<input type="radio" name="stepup_method" checked={method === "Email code"} onChange={() => setMethod("Email code")} /> Email code
				</label>
				<label className="inline-flex items-center gap-2">
					<input type="radio" name="stepup_method" checked={method === "Authenticator app"} onChange={() => setMethod("Authenticator app")} /> Authenticator app
				</label>
				<label className="inline-flex items-center gap-2">
					<input type="radio" name="stepup_method" checked={method === "Passkey"} onChange={() => setMethod("Passkey")} /> Passkey
				</label>
			</div>
			{method === "Email code" && (
				<div className="mt-2">
					<button className="rounded bg-slate-700 px-3 py-1" onClick={sendEmailCode}>Send email code</button>
					<div className="mt-2">
						<input className="rounded border border-slate-700 bg-transparent p-2 w-full md:w-60" placeholder="Email code" value={emailCode} onChange={(e) => setEmailCode(e.target.value)} />
					</div>
				</div>
			)}
			{method === "Authenticator app" && (
				<div className="mt-2">
					<input className="rounded border border-slate-700 bg-transparent p-2 w-full md:w-60" placeholder="6-digit code" value={totpCode} onChange={(e) => setTotpCode(e.target.value)} />
				</div>
			)}
			{method === "Passkey" && (
				<div className="text-slate-400 text-sm mt-2">Use the passkey prompt from your browser when available.</div>
			)}
			<div className="mt-3"><button className="rounded bg-blue-600 px-3 py-1" onClick={confirmStepup}>Confirm</button></div>
		</div>

			{/* Users List */}
			<div className="rounded border border-slate-700 p-3">
				<h2 className="text-xl font-semibold">Users</h2>
				<div className="mt-2 flex gap-2">
					<input 
						className="flex-1 rounded border border-slate-700 bg-transparent p-2" 
						placeholder="Search by email..." 
						value={userSearch} 
						onChange={(e) => setUserSearch(e.target.value)} 
						onKeyDown={(e) => e.key === 'Enter' && setUsersPage(0)}
					/>
					<button className="rounded bg-slate-700 px-3 py-2" onClick={() => setUsersPage(0)}>Search</button>
				</div>
				
				<div className="mt-3 overflow-x-auto">
					<table className="w-full text-sm text-left">
						<thead className="text-slate-400 border-b border-slate-700">
							<tr>
								<th className="p-2">ID</th>
								<th className="p-2">Email</th>
								<th className="p-2">Role</th>
								<th className="p-2">Credits</th>
								<th className="p-2">Trial Mode</th>
								<th className="p-2">Actions</th>
							</tr>
						</thead>
						<tbody>
							{usersLoading && <tr><td colSpan={6} className="p-4 text-center text-slate-500">Loading...</td></tr>}
							{!usersLoading && users.map(u => (
								<tr key={u.id} className="border-b border-slate-800 hover:bg-slate-800/30">
									<td className="p-2">{u.id}</td>
									<td className="p-2">{u.email}</td>
									<td className="p-2">{u.role}</td>
									<td className="p-2">{u.credits}</td>
									<td className="p-2">
										{u.trial_mode_override === "enabled" ? (
											<span className="text-yellow-400">Forced ON</span>
										) : u.trial_mode_override === "disabled" ? (
											<span className="text-red-400">Forced OFF</span>
										) : (
											<span className="text-slate-400">Auto</span>
										)}
									</td>
									<td className="p-2 flex gap-2">
										<button 
											className="text-xs bg-slate-700 px-2 py-1 rounded hover:bg-slate-600"
											onClick={() => onSetTrialMode(u.id, "enabled")}
											title="Force Trial Mode ON (restrict models)"
										>
											Force ON
										</button>
										<button 
											className="text-xs bg-slate-700 px-2 py-1 rounded hover:bg-slate-600"
											onClick={() => onSetTrialMode(u.id, "disabled")}
											title="Force Trial Mode OFF (allow all models)"
										>
											Force OFF
										</button>
										<button 
											className="text-xs bg-slate-700 px-2 py-1 rounded hover:bg-slate-600"
											onClick={() => onSetTrialMode(u.id, null)}
											title="Reset to Automatic (based on balance)"
										>
											Auto
										</button>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
				
				<div className="mt-3 flex justify-between items-center">
					<button 
						disabled={usersPage === 0}
						className="px-3 py-1 rounded bg-slate-800 disabled:opacity-50"
						onClick={() => setUsersPage(p => Math.max(0, p - 1))}
					>
						Prev
					</button>
					<span className="text-slate-400">Page {usersPage + 1}</span>
					<button 
						disabled={users.length < 20}
						className="px-3 py-1 rounded bg-slate-800 disabled:opacity-50"
						onClick={() => setUsersPage(p => p + 1)}
					>
						Next
					</button>
				</div>
			</div>

			<hr className="border-slate-700" />

			{/* Single Gift */}
			<div className="rounded border border-slate-700 p-3">
				<h2 className="text-xl font-semibold">Single Gift</h2>
				<div className="mt-2 flex flex-col md:flex-row gap-4 md:items-center">
					<label className="inline-flex items-center gap-2">
						<input type="radio" checked={giftIdent === "Email"} onChange={() => setGiftIdent("Email")} /> Email
					</label>
					<label className="inline-flex items-center gap-2">
						<input type="radio" checked={giftIdent === "User ID"} onChange={() => setGiftIdent("User ID")} /> User ID
					</label>
				</div>
				{giftIdent === "Email" ? (
					<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="Email" value={giftEmail} onChange={(e) => setGiftEmail(e.target.value)} />
				) : (
					<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="User ID" value={giftUserId} onChange={(e) => setGiftUserId(e.target.value)} />
				)}
				<div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
					<div>
						<label className="block">Amount (USD)</label>
						<input type="number" min={0.01} step={0.5} className="w-full rounded border border-slate-700 bg-transparent p-2" value={giftAmountUsd} onChange={(e) => setGiftAmountUsd(parseFloat(e.target.value || "0"))} />
					</div>
					<div>
						<label className="block">Reason (optional)</label>
						<input className="w-full rounded border border-slate-700 bg-transparent p-2" placeholder="promo, courtesy, bugfix, etc." value={giftReason} onChange={(e) => setGiftReason(e.target.value)} />
					</div>
				</div>
				<div className="mt-3 flex flex-col sm:flex-row gap-3">
					<label className="inline-flex items-center gap-2">
						<input type="checkbox" checked={giftIsTrial} onChange={(e) => setGiftIsTrial(e.target.checked)} />
						<span>Gift as trial credits</span>
					</label>
					<label className="inline-flex items-center gap-2">
						<input type="checkbox" checked={giftSendEmail} onChange={(e) => setGiftSendEmail(e.target.checked)} />
						<span>Send email notification</span>
					</label>
				</div>
				<div className="mt-3"><button className="rounded bg-blue-600 px-3 py-2" onClick={onGift}>Gift credits</button></div>
			</div>

			<hr className="border-slate-700" />

			{/* Signup Trial Grant */}
			<div className="rounded border border-slate-700 p-3">
				<h2 className="text-xl font-semibold">Signup Trial Grant</h2>
				<div className="text-slate-400 text-sm">Configure the trial granted after email verification. Requires admin login.</div>
				{!sgLoaded && (
					<div className="mt-2 text-slate-400">Loading...</div>
				)}
				{sgError && (
					<div className="mt-2 p-3 rounded bg-amber-900/30 border border-amber-700 text-amber-200">
						{sgError}
					</div>
				)}
				{sgLoaded && sg && (
					<div className="mt-2 space-y-3">
						{/* Basic Settings */}
						<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
							<div>
								<label className="inline-flex items-center gap-2">
									<input type="checkbox" checked={sgEnabled} onChange={(e) => setSgEnabled(e.target.checked)} />
									<span>Enable trial grant</span>
								</label>
							<div className="mt-2">
								<label className="block">Trial amount (USD)</label>
								<input type="number" min={0} step={0.25} className="w-full rounded border border-slate-700 bg-transparent p-2" value={sgUsd} onChange={(e) => setSgUsd(e.target.value === "" ? "" : parseFloat(e.target.value))} onWheel={(e) => e.currentTarget.blur()} />
								<div className="text-slate-400 text-xs">Displayed in USD; stored/sent as integer cents.</div>
							</div>
							</div>
							<div>
								<label className="block">IP window (days)</label>
								<input type="number" min={0} max={365} step={1} className="w-full rounded border border-slate-700 bg-transparent p-2 mb-2" value={sgIpDays} onChange={(e) => setSgIpDays(e.target.value === "" ? "" : parseInt(e.target.value))} onWheel={(e) => e.currentTarget.blur()} />
								<label className="block">Email window (days)</label>
								<input type="number" min={0} max={365} step={1} className="w-full rounded border border-slate-700 bg-transparent p-2 mb-2" value={sgEmailDays} onChange={(e) => setSgEmailDays(e.target.value === "" ? "" : parseInt(e.target.value))} onWheel={(e) => e.currentTarget.blur()} />
								<label className="block">Fingerprint window (days)</label>
								<input type="number" min={0} max={365} step={1} className="w-full rounded border border-slate-700 bg-transparent p-2" value={sgFpDays} onChange={(e) => setSgFpDays(e.target.value === "" ? "" : parseInt(e.target.value))} onWheel={(e) => e.currentTarget.blur()} />
							</div>
						</div>

						{/* Trial Duration & Expiry */}
						<div className="border-t border-slate-700 pt-3">
							<h3 className="text-lg font-semibold mb-2">Trial Duration & Expiry</h3>
							<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
								<div>
									<label className="block">Trial period (days)</label>
									<input 
										type="number" 
										min={0} 
										max={365} 
										step={1} 
										className="w-full rounded border border-slate-700 bg-transparent p-2" 
										value={sgTrialDurationDays ?? ""} 
										onChange={(e) => {
											const val = e.target.value ? parseInt(e.target.value) : null;
											setSgTrialDurationDays(val);
											if (val) setSgTrialEndDate("");
										}} 
										onWheel={(e) => e.currentTarget.blur()}
										placeholder="e.g., 30 (optional)"
									/>
									<div className="text-slate-400 text-xs">Trial credits expire after N days from grant.</div>
								</div>
								<div>
									<label className="block">OR Trial end date</label>
									<input 
										type="date" 
										className="w-full rounded border border-slate-700 bg-transparent p-2" 
										value={sgTrialEndDate} 
										onChange={(e) => {
											setSgTrialEndDate(e.target.value);
											if (e.target.value) setSgTrialDurationDays(null);
										}} 
										placeholder="YYYY-MM-DD"
									/>
									<div className="text-slate-400 text-xs">All trials end on this date (overrides period).</div>
								</div>
							</div>
						</div>

						{/* Trial Models */}
						<div className="border-t border-slate-700 pt-3">
							<div className="flex items-center justify-between mb-2">
								<h3 className="text-lg font-semibold">Models Allowed During Trial</h3>
								<button
									type="button"
									className="text-sm text-blue-400 hover:text-blue-300"
									onClick={() => {
										if (sgTrialModelsSet.size === MODEL_OPTIONS.length) {
											setSgTrialModelsSet(new Set());
										} else {
											setSgTrialModelsSet(new Set(MODEL_OPTIONS.map(m => m.model_id)));
										}
									}}
								>
								{sgTrialModelsSet.size === MODEL_OPTIONS.length ? "Deselect All" : "Select All"}
							</button>
						</div>
						<div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-64 overflow-y-auto hover-thin-scrollbar">
							{MODEL_OPTIONS.map((model) => (
									<label key={model.model_id} className="inline-flex items-center gap-2 cursor-pointer hover:bg-slate-800/50 p-1 rounded">
										<input
											type="checkbox"
											checked={sgTrialModelsSet.has(model.model_id)}
											onChange={(e) => {
												const newSet = new Set(sgTrialModelsSet);
												if (e.target.checked) {
													newSet.add(model.model_id);
												} else {
													newSet.delete(model.model_id);
												}
												setSgTrialModelsSet(newSet);
											}}
										/>
										<span className="text-sm">{model.alias}</span>
										<span className="text-xs text-slate-500">({model.provider_display})</span>
									</label>
								))}
							</div>
						</div>

						{/* Trial Availability */}
						<div className="border-t border-slate-700 pt-3">
							<h3 className="text-lg font-semibold mb-2">Trial Availability</h3>
							<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
								<div>
									<label className="block">Total trial slots available</label>
									<input 
										type="number" 
										min={0} 
										step={1} 
										className="w-full rounded border border-slate-700 bg-transparent p-2" 
										value={sgTrialTotalSlots ?? ""} 
										onChange={(e) => setSgTrialTotalSlots(e.target.value ? parseInt(e.target.value) : null)} 
										onWheel={(e) => e.currentTarget.blur()}
										placeholder="e.g., 50 (optional)"
									/>
									<div className="text-slate-400 text-xs">Leave empty for unlimited trials. Logged-out users see X/Y available.</div>
									{sgTrialTotalSlots !== null && sgTrialTotalSlots > 0 && sgTrialClaimedCount !== null && (
										<div className="mt-2 text-sm">
											<span className="text-slate-300">Current: </span>
											<span className="font-semibold text-blue-400">{sgTrialClaimedCount}</span>
											<span className="text-slate-400"> claimed / </span>
											<span className="font-semibold text-green-400">{sgTrialTotalSlots - sgTrialClaimedCount}</span>
											<span className="text-slate-400"> remaining</span>
										</div>
									)}
								</div>
								<div>
									<label className="inline-flex items-center gap-2 mt-7">
										<input type="checkbox" checked={sgTrialResetSlots} onChange={(e) => setSgTrialResetSlots(e.target.checked)} />
										<span>Reset claimed counter on save</span>
									</label>
									<div className="text-slate-400 text-xs mt-1">Check to reset the count back to 0 when saving.</div>
								</div>
							</div>
						</div>
					</div>
				)}
				{sgLoaded && (
					<div className="mt-3"><button className="rounded bg-blue-600 px-3 py-2" onClick={onSaveSignupGrant}>Save trial settings</button></div>
				)}
			</div>

			<hr className="border-slate-700" />

			{/* Bulk Gift */}
			<div className="rounded border border-slate-700 p-3">
				<h2 className="text-xl font-semibold">Bulk Gift</h2>
				<div className="text-slate-400 text-sm">
					One row per line: email,amount_usd,is_trial,reason(optional)
					<br />
					<span className="text-xs">Example: alice@example.com,5.00,false,promo OR bob@example.com,10.00,true</span>
				</div>
				<textarea className="mt-2 w-full h-40 rounded border border-slate-700 bg-transparent p-2 hover-thin-scrollbar" placeholder="alice@example.com,5.00,false,summer-promo&#10;bob@example.com,10.00,true" value={bulkCsv} onChange={(e) => setBulkCsv(e.target.value)} />
				<div className="mt-2 flex flex-col sm:flex-row items-start sm:items-center gap-3">
					<label className="inline-flex items-center gap-2">
						<input type="checkbox" checked={bulkDry} onChange={(e) => setBulkDry(e.target.checked)} /> 
						<span>Dry run</span>
					</label>
					<label className="inline-flex items-center gap-2">
						<input type="checkbox" checked={bulkSendEmail} onChange={(e) => setBulkSendEmail(e.target.checked)} /> 
						<span>Send email notifications</span>
					</label>
				</div>
				<div className="mt-3"><button className="rounded bg-slate-700 px-3 py-2" onClick={onRunBulk}>Run bulk</button></div>
				{bulkDetails.length > 0 && (
					<div className="mt-3 overflow-x-auto -mx-3 px-3">
						<table className="min-w-full text-sm">
							<thead>
								<tr>
									{Object.keys(bulkDetails[0]).map((k) => (<th key={k} className="text-left pr-3 whitespace-nowrap">{k}</th>))}
								</tr>
							</thead>
							<tbody>
								{bulkDetails.map((row) => {
									// Use email or first column plus amount as stable key; fallback to JSON hash slice.
									const primary = (row as any).email || (row as any).user || Object.values(row)[0];
									const amt = (row as any).amount_usd || (row as any).amount || '';
									const k = String(primary) + '::' + String(amt);
									return (
										<tr key={k}>{Object.keys(bulkDetails[0]).map((k2) => (<td key={k2} className="pr-3 whitespace-nowrap">{String((row as any)[k2])}</td>))}</tr>
									);
								})}
							</tbody>
						</table>
					</div>
				)}
			</div>

			<hr className="border-slate-700" />

			{/* Reverse Credit */}
			<div className="rounded border border-slate-700 p-3">
				<h2 className="text-xl font-semibold">Reverse Credit</h2>
				<div className="text-slate-400 text-sm">Reverse a prior grant/purchase by Ledger ID (UUID)</div>
				<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="Ledger ID (UUID)" value={revId} onChange={(e) => setRevId(e.target.value)} />
				<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="Reason (optional)" value={revReason} onChange={(e) => setRevReason(e.target.value)} />
				<div className="mt-2"><button className="rounded bg-slate-700 px-3 py-2" onClick={onReverse}>Reverse</button></div>
			</div>

			<hr className="border-slate-700" />

			{/* Balance & Ledger Inspector */}
			<div className="rounded border border-slate-700 p-3">
				<h2 className="text-xl font-semibold">Balance & Ledger Inspector</h2>
				<div className="mt-2 flex flex-col md:flex-row gap-4 md:items-center">
					<label className="inline-flex items-center gap-2"><input type="radio" checked={ident2 === "Email"} onChange={() => setIdent2("Email")} /> Email</label>
					<label className="inline-flex items-center gap-2"><input type="radio" checked={ident2 === "User ID"} onChange={() => setIdent2("User ID")} /> User ID</label>
				</div>
				{ident2 === "Email" ? (
					<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="Email" value={email2} onChange={(e) => setEmail2(e.target.value)} />
				) : (
					<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="User ID" value={userId2} onChange={(e) => setUserId2(e.target.value)} />
				)}
				<div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
					<button className="rounded bg-slate-700 px-3 py-2" onClick={() => fetchInspect("balance")}>Fetch Balance</button>
					<button className="rounded bg-slate-700 px-3 py-2" onClick={() => fetchInspect("ledger")}>Fetch Ledger</button>
				</div>
				{inspectOut && (
					<pre className="mt-3 overflow-auto hover-thin-scrollbar rounded border border-slate-800 bg-slate-900/60 p-3 text-sm">{inspectOut}</pre>
				)}
			</div>

			<hr className="border-slate-700" />

			{/* Simulate Purchase / Refund */}
			<div className="rounded border border-slate-700 p-3">
				<h2 className="text-xl font-semibold">Simulate Purchase / Refund</h2>
				<div className="mt-2 flex flex-col md:flex-row gap-4 md:items-center">
					<label className="inline-flex items-center gap-2"><input type="radio" checked={ident3 === "Email"} onChange={() => setIdent3("Email")} /> Email</label>
					<label className="inline-flex items-center gap-2"><input type="radio" checked={ident3 === "User ID"} onChange={() => setIdent3("User ID")} /> User ID</label>
				</div>
				{ident3 === "Email" ? (
					<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="Email" value={email3} onChange={(e) => setEmail3(e.target.value)} />
				) : (
					<input className="mt-2 w-full rounded border border-slate-700 bg-transparent p-2" placeholder="User ID" value={userId3} onChange={(e) => setUserId3(e.target.value)} />
				)}
				<div className="mt-2">
					<label className="block">Amount (USD)</label>
					<input type="number" min={0.01} step={0.5} className="w-full rounded border border-slate-700 bg-transparent p-2" value={amountUsdSim} onChange={(e) => setAmountUsdSim(parseFloat(e.target.value || "0"))} />
				</div>
				<div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
					<button className="rounded bg-blue-600 px-3 py-2" onClick={() => onSim("sim-purchase")}>Simulate Purchase</button>
					<button className="rounded bg-slate-700 px-3 py-2" onClick={() => onSim("sim-refund")}>Simulate Refund</button>
				</div>
			</div>

			<hr className="border-slate-700" />

			<UserTrialManager />
		</div>
	);
}




