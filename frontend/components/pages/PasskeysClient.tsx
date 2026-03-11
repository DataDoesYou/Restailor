"use client";
import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { b64urlToBuf, bufToB64url } from "@/lib/client";

export default function PasskeysClient() {
	const [creds, setCreds] = useState<any[]>([]);
	const [nickById, setNickById] = useState<Record<string, string>>({});
	const [alert, setAlert] = useState<{ kind: "info" | "success" | "error" | "warning"; text: string } | null>(null);
	const [busy, setBusy] = useState(false);
	const [newNick, setNewNick] = useState("");

	const load = async () => {
		try {
			const rows = await api.get<any[]>("/webauthn/credentials");
			setCreds(rows || []);
			const init: Record<string, string> = {};
			(rows || []).forEach((r) => { init[r.credential_id] = r.nickname || ""; });
			setNickById(init);
		} catch { setAlert({ kind: "warning", text: "Could not load passkeys for your account." }); }
	};

	useEffect(() => { load(); }, []);

	const onSave = async (id: string) => {
		setBusy(true);
		try {
			await api.patch(`/webauthn/credentials/${id}`, { nickname: nickById[id] || null } as any);
			setAlert({ kind: "success", text: "Saved." });
			load();
		} catch { setAlert({ kind: "error", text: "Save failed." }); }
		finally { setBusy(false); }
	};
	const onDelete = async (id: string) => {
		setBusy(true);
		try { await api.delete(`/webauthn/credentials/${id}`); setAlert({ kind: "success", text: "Deleted." }); load(); }
		catch { setAlert({ kind: "error", text: "Delete failed." }); }
		finally { setBusy(false); }
	};
	const onCreate = async () => {
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
				nickname: newNick || null,
			};
			const rv = await api.post("/webauthn/register/verify", payload);
			setAlert({ kind: "success", text: "Passkey added." });
			setNewNick("");
			load();
		} catch (e) {
			const det = (e as any)?.detail;
			setAlert({ kind: "error", text: typeof det === "string" && det ? `Registration failed: ${det}` : "Registration failed." });
		} finally { setBusy(false); }
	};

	return (
		<div className="space-y-3">
			<h2 className="text-lg font-semibold">Passkeys (WebAuthn)</h2>
			<p className="text-slate-300">Register a passkey for phishing-resistant 2FA. Works with platform authenticators (Windows Hello, Touch ID) and security keys.</p>

			{alert && <div className={{ info: "text-blue-400", success: "text-green-400", error: "text-red-400", warning: "text-yellow-400" }[alert.kind]}>{alert.text}</div>}

			{creds.length === 0 ? (
				<div className="text-slate-300">No passkeys registered yet.</div>
			) : (
				<div className="space-y-2">
					{creds.map((row) => (
						<div key={row.credential_id} className="grid grid-cols-12 items-center gap-2">
							<input className="col-span-6 rounded border border-slate-600 bg-transparent px-3 py-2" value={nickById[row.credential_id] ?? ""} onChange={(e) => setNickById((s) => ({ ...s, [row.credential_id]: e.target.value }))} />
							<div className="col-span-4 text-slate-300 text-sm">{String(row.created_at || "")}</div>
							<button onClick={() => onSave(row.credential_id)} disabled={busy} className="col-span-1 rounded bg-slate-700 px-2 py-2">Save</button>
							<button onClick={() => onDelete(row.credential_id)} disabled={busy} className="col-span-1 rounded bg-slate-700 px-2 py-2">Delete</button>
						</div>
					))}
				</div>
			)}

		<hr className="border-slate-700 my-3" />
		<div className="space-y-2">
			<h3 className="font-medium">Register a new passkey</h3>
			<label className="block">Nickname (optional)</label>
			<input className="w-full rounded border border-slate-600 bg-transparent px-3 py-2" value={newNick} onChange={(e) => setNewNick(e.target.value)} />
			<button disabled={busy} onClick={onCreate} className="mt-2 rounded bg-blue-600 px-3 py-2 disabled:opacity-50">Create passkey</button>
		</div>
		</div>
	);
}

