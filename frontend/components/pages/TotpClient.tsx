"use client";
import { useCallback, useEffect, useState } from "react";
import api, { ApiError } from "@/lib/api";

export default function TotpClient() {
	const [state, setState] = useState<any | null>(null);
	const [started, setStarted] = useState<any | null>(null);
	const [code, setCode] = useState("");
	const [alert, setAlert] = useState<{ kind: "info" | "success" | "error" | "warning"; text: string } | null>(null);
	const [busy, setBusy] = useState(false);

	const load = useCallback(async () => {
		try { const s = await api.get("/2fa/state"); setState(s); }
		catch { setState(null); }
	}, []);
	useEffect(() => { load(); }, [load]);

	const start = useCallback(async () => {
		setBusy(true);
		try { const r = await api.post("/2fa/totp/start", {}); setStarted(r); }
		catch { setAlert({ kind: "error", text: "Could not start 2FA setup." }); }
		finally { setBusy(false); }
	}, []);
	const confirm = useCallback(async () => {
		setBusy(true);
		try {
			const r: any = await api.post("/2fa/totp/confirm", { code });
			setStarted(null);
			setAlert({ kind: "success", text: "✓ 2FA is now enabled and protecting your account." });
			load();
		} catch (e) {
			const err = e as ApiError;
			if (err.status === 400) setAlert({ kind: "error", text: "Invalid code." });
			else setAlert({ kind: "error", text: "Could not confirm 2FA." });
		} finally { setBusy(false); }
	}, [code, load]);

	return (
		<div className="space-y-3">
			<h1 className="text-xl font-semibold">Two‑Factor Authentication (2FA)</h1>
			{!state ? (
				<div className="text-slate-300">Loading 2FA status…</div>
			) : (
				<>
					{state.two_factor_enabled && state.has_totp ? (
						<div className="space-y-2">
							<div className="text-green-400 font-medium">✓ Two-factor authentication is enabled</div>
							<div className="text-sm text-slate-400">Your account is protected. You'll need your authenticator app code when logging in.</div>
						</div>
					) : !state.two_factor_enabled || !state.has_totp ? (
						<>
							<div className="mb-3">Protect your account with an authenticator app like Google Authenticator or Authy.</div>
							<div className="text-sm text-slate-400 mb-4">Scan the QR code below with your authenticator app, then enter the 6-digit code to complete setup.</div>
							{!started && (
								<button disabled={busy} onClick={start} className="rounded bg-blue-600 px-3 py-2 disabled:opacity-50 mb-4">Set up 2FA</button>
							)}
						</>
					) : null}

					{(started || !state.two_factor_enabled) && (
						<div className="space-y-2">
							{(() => {
								const d = started;
								const b64raw = String(d?.qr_png_base64 || "").trim();
								return b64raw ? (
									<>
										<img src={b64raw} alt="QR Code for 2FA" className="max-w-xs border border-slate-700 rounded p-2" />
										<div className="text-xs text-slate-500">Scan this QR code with your authenticator app</div>
									</>
								) : (
									<div className="text-yellow-400">Loading QR code…</div>
								);
							})()}
							<label className="block text-sm font-medium">Enter the 6‑digit code from your app</label>
							<input 
								maxLength={6} 
								placeholder="000000"
								className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 font-mono text-lg tracking-widest" 
								value={code} 
								onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} 
							/>
							<button disabled={busy || code.length !== 6} onClick={confirm} className="rounded bg-green-600 px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed font-medium">
								Confirm & Enable 2FA
							</button>
						</div>
					)}
				</>
			)}
			{alert && <div className={{ info: "text-blue-400", success: "text-green-400", error: "text-red-400", warning: "text-yellow-400" }[alert.kind]}>{alert.text}</div>}
		</div>
	);
}

