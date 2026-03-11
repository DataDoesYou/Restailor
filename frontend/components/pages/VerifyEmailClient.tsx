"use client";
import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import api, { ApiError } from "@/lib/api";

export default function VerifyEmailClient() {
	const sp = useSearchParams();
	const router = useRouter();
	const [msg, setMsg] = useState<string>("Verifying…");
	const [ok, setOk] = useState<boolean | null>(null);

	useEffect(() => {
		const token = sp?.get("token");
		if (!token) { setOk(false); setMsg("Invalid verification link."); return; }
		(async () => {
			try {
				const resp = await api.get<{ ok: boolean; message: string }>(`/users/verify-email`, { query: { token } });
				setOk(true);
				setMsg(resp?.message || "Email verification successful. You can now use the app.");
			} catch (e) {
				const err = e as ApiError;
				if (err.status === 404) { setMsg("User not found"); }
				else if (err.status === 400) { setMsg(typeof err.detail === "string" ? err.detail : "Invalid or expired token"); }
				else { setMsg("Verification failed."); }
				setOk(false);
			}
		})();
	}, [sp]);

	return (
		<div className="space-y-3">
			<h1 className="text-xl font-semibold">Verify Email</h1>
			<div className={ok ? "text-green-400" : ok === null ? "text-slate-300" : "text-red-400"}>{msg}</div>
			<button className="rounded bg-slate-700 px-3 py-2" onClick={() => router.push("/")}>Close</button>
		</div>
	);
}

