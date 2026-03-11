"use client";
import { useCallback, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import api from "@/lib/api";

export default function ResetPasswordClient() {
	const sp = useSearchParams();
	const router = useRouter();
	const token = sp?.get("token");
	const [npw, setNpw] = useState("");
	const [cpw, setCpw] = useState("");
	const [alert, setAlert] = useState<{ kind: "success" | "error"; text: string } | null>(null);
	const [busy, setBusy] = useState(false);

	const doReset = useCallback(async () => {
		if (!token) { setAlert({ kind: "error", text: "Invalid verification link." }); return; }
		if (!npw || !cpw) { setAlert({ kind: "error", text: "Please enter and confirm your new password." }); return; }
		if (npw !== cpw) { setAlert({ kind: "error", text: "Passwords do not match." }); return; }
		if (npw.length < 8) { setAlert({ kind: "error", text: "Please use at least 8 characters." }); return; }
		setBusy(true);
		try {
			await api.post("/users/reset-password", { token, new_password: npw });
			setAlert({ kind: "success", text: "Your password has been updated. You can now sign in from the sidebar." });
			setNpw(""); setCpw("");
		} catch (e) {
			const detail = (e as any)?.detail;
			setAlert({ kind: "error", text: typeof detail === "string" && detail ? detail : "Failed to update password." });
		} finally { setBusy(false); }
	}, [token, npw, cpw]);

	if (!token) {
		return (
			<div className="space-y-4">
				<div className="text-slate-300">No reset token provided. Returning to the app…</div>
				<button className="rounded bg-slate-700 px-3 py-2" onClick={() => router.push("/resume")}>Back to app</button>
			</div>
		);
	}

	return (
		<div className="max-w-xl mx-auto mt-16 border border-slate-700 rounded p-6">
			<div className="text-lg font-semibold mb-1">Reset your password</div>
			<div className="opacity-90 mb-4">Set a new password for your account. For security, the link expires shortly.</div>
			<label className="block">New password</label>
			<input type="password" className="w-full rounded border border-slate-600 bg-transparent px-3 py-2 mb-2" value={npw} onChange={(e) => setNpw(e.target.value)} />
			<label className="block">Confirm new password</label>
			<input type="password" className="w-full rounded border border-slate-600 bg-transparent px-3 py-2" value={cpw} onChange={(e) => setCpw(e.target.value)} />
			<button disabled={busy} onClick={doReset} className="mt-3 rounded bg-blue-600 px-3 py-2 disabled:opacity-50 w-full">Update password</button>
			{alert && <div className={`mt-3 ${alert.kind === "success" ? "text-green-400" : "text-red-400"}`}>{alert.text}</div>}
			{/* The app UI is visible alongside the form in the sidebar layout; no extra navigation button needed. */}
		</div>
	);
}

