"use client";
import { useCallback, useMemo, useState } from "react";
import api, { ApiError } from "@/lib/api";
import { getClientId } from "@/lib/client";

interface SignupResponse {
	ok: boolean;
	user: any;
	email_sent?: boolean;
	email_error?: string | null;
}

export default function SignupClient() {
	const xClient = useMemo(() => getClientId(), []);
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [alert, setAlert] = useState<{ kind: "info" | "success" | "error" | "warning"; text: string } | null>(null);
	const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);
	const [busy, setBusy] = useState(false);
	const [showSuccess, setShowSuccess] = useState(false);

	const onSignup = useCallback(async () => {
		setAlert(null);
		const u = (email || "").trim();
		const p = (password || "").trim();
		if (!u || !p) { setAlert({ kind: "error", text: "Email and password are required to register." }); return; }
		if (!u.includes("@")) { setAlert({ kind: "error", text: "Please enter a valid email address." }); return; }
		setBusy(true);
		try {
			const response = await api.post<SignupResponse>("/signup", { username: u.toLowerCase(), password: p }, { headers: { "X-Client-Id": xClient } });
			setShowSuccess(true);
			
			// Check if email was sent successfully
			if (response?.email_sent === false || response?.email_error) {
				setAlert({ 
					kind: "warning", 
					text: `Registration successful, but verification email failed to send: ${response?.email_error || "Unknown error"}. You can try resending below.` 
				});
			} else {
				setAlert({ kind: "success", text: "Registration successful. Check your email to verify your account." });
			}
		} catch (e) {
			const err = e as ApiError;
			const sc = err.status;
			const detail = typeof err.detail === "string" ? err.detail : (err.detail as any)?.detail;
			if (sc === 422) setAlert({ kind: "error", text: "Please enter a valid email address and password." });
			else if (sc === 400 && typeof detail === "string" && detail.toLowerCase().includes("captcha")) setAlert({ kind: "warning", text: detail });
			else if (sc === 400 && typeof detail === "string" && detail.toLowerCase().includes("disposable")) setAlert({ kind: "error", text: "Disposable email addresses are not permitted." });
			else if (sc === 400 && typeof detail === "string" && detail.toLowerCase().includes("limit")) setAlert({ kind: "error", text: detail });
			else if (sc === 400 && typeof detail === "string" && detail.toLowerCase().includes("already")) setAlert({ kind: "error", text: "That email is already registered." });
			else setAlert({ kind: "error", text: typeof detail === "string" && detail.trim() ? detail : "Registration failed. Please check your details and try again." });
			setShowSuccess(false);
		} finally {
			setBusy(false);
		}
	}, [email, password, xClient]);

	const onResend = useCallback(async () => {
		try {
			await api.post("/users/request-verification-token", {});
			setAlert({ kind: "success", text: "Verification email sent. Check your inbox." });
		} catch (e) {
			const err = e as ApiError;
			if (err.status === 429) setAlert({ kind: "warning", text: "You're sending requests too fast. Please wait and try again." });
			else setAlert({ kind: "error", text: "Could not send verification email." });
		}
	}, []);

	return (
		<div className="space-y-3">
			<h1 className="text-xl font-semibold">Register</h1>
			{alert && (
				<div className={{ info: "text-blue-400", success: "text-green-400", error: "text-red-400", warning: "text-yellow-400" }[alert.kind]}>{alert.text}</div>
			)}
			<label className="block">Email</label>
			<input className="w-full rounded border border-slate-600 bg-transparent px-3 py-2" value={email} onChange={(e) => setEmail(e.target.value)} />
			<label className="block">Password</label>
			<input type="password" className="w-full rounded border border-slate-600 bg-transparent px-3 py-2" value={password} onChange={(e) => setPassword(e.target.value)} />
			<div className="grid grid-cols-2 gap-3">
				<button disabled={busy} onClick={onSignup} className="rounded bg-blue-600 px-3 py-2 disabled:opacity-50">Register</button>
				<span />
			</div>
			{showSuccess && (
				<div className="space-y-2">
					<button onClick={onResend} className="w-full rounded bg-slate-700 px-3 py-2">Resend verification email</button>
				</div>
			)}
		</div>
	);
}

