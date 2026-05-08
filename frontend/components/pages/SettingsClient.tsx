"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import api, { ApiError } from "@/lib/api";

type Alert = { kind: "info" | "success" | "warning" | "error"; text: string } | null;
type ProviderKeyMeta = { provider: string; configured: boolean; key_tail?: string | null; storage_mode?: string | null; updated_at?: string | null };
type UserSettingsPayload = { public_profile?: boolean; dont_save_future_data?: boolean; byok_sync_modes?: Record<string, boolean> | null };
const BYOK_PROVIDERS = [
	{ id: "anthropic", label: "Anthropic", placeholder: "sk-ant-api..." },
	{ id: "gemini", label: "Google", placeholder: "AIza... or AQ..." },
	{ id: "openai", label: "OpenAI", placeholder: "sk-proj-..." },
	{ id: "xai", label: "xAI", placeholder: "xai-..." },
];

const defaultSyncModes = () => Object.fromEntries(BYOK_PROVIDERS.map((p) => [p.id, false])) as Record<string, boolean>;
const maskKeyPreview = (value: string) => {
	const key = String(value || "").trim();
	if (!key) return "";
	if (key.length <= 6) return `${key.slice(0, 1)}...${key.slice(-1)}`;
	return `${key.slice(0, 2)}...${key.slice(-2)}`;
};
const localKeyPreview = (provider: string) => {
	if (typeof window === "undefined") return "";
	try {
		const stored = JSON.parse(localStorage.getItem(`rt_byok_local_${provider}`) || "{}");
		return String(stored.preview || (stored.tail ? `...${stored.tail}` : ""));
	} catch {
		return "";
	}
};
async function readLocalKey(provider: string): Promise<string | null> {
	if (typeof window === "undefined") return null;
	const raw = localStorage.getItem(`rt_byok_local_${provider}`);
	if (!raw) return null;
	const payload = JSON.parse(raw);
	const cryptoKey = await new Promise<CryptoKey | null>((resolve) => {
		const open = indexedDB.open("restailor-byok", 1);
		open.onerror = () => resolve(null);
		open.onsuccess = () => {
			try {
				const tx = open.result.transaction("keys", "readonly");
				const req = tx.objectStore("keys").get(provider);
				req.onsuccess = () => resolve((req.result as CryptoKey) || null);
				req.onerror = () => resolve(null);
			} catch {
				resolve(null);
			}
		};
	});
	if (!cryptoKey) return null;
	const plain = await crypto.subtle.decrypt(
		{ name: "AES-GCM", iv: new Uint8Array(payload.iv || []) },
		cryptoKey,
		new Uint8Array(payload.cipher || []),
	);
	return new TextDecoder().decode(plain);
}

interface SettingsClientProps {
	initialSettings?: any | null;
}

export default function SettingsClient({ initialSettings = null }: SettingsClientProps) {
	const hadSsrSettings = typeof initialSettings !== "undefined" && initialSettings !== null;
	const [loading, setLoading] = useState(!hadSsrSettings);
	const [savingPublicProfile, setSavingPublicProfile] = useState(false);
	const [savingDontSave, setSavingDontSave] = useState(false);
	const [alert, setAlert] = useState<Alert>(null);
	const [authPending, setAuthPending] = useState<boolean>(!hadSsrSettings);
	const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(hadSsrSettings ? true : null);
	
	// Success messages shown inline next to checkboxes
	const [publicProfileSaved, setPublicProfileSaved] = useState(false);
	const [dontSaveSaved, setDontSaveSaved] = useState(false);

	// Settings state - initialize from SSR if available
	const [publicProfile, setPublicProfile] = useState(hadSsrSettings ? Boolean(initialSettings?.public_profile) : false);
	const [dontSaveFutureData, setDontSaveFutureData] = useState(hadSsrSettings ? Boolean(initialSettings?.dont_save_future_data) : false);
	const [providerKeys, setProviderKeys] = useState<Record<string, ProviderKeyMeta>>({});
	const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
	const [localPreviews, setLocalPreviews] = useState<Record<string, string>>({});
	const [syncModes, setSyncModes] = useState<Record<string, boolean>>(() => ({
		...defaultSyncModes(),
		...(initialSettings?.byok_sync_modes || {}),
	}));
	const [savingProvider, setSavingProvider] = useState<string | null>(null);

	// Delete data state
	const [deleteDataPwd, setDeleteDataPwd] = useState("");
	const [deletingData, setDeletingData] = useState(false);
	
	// Delete account state
	const [deleteAccountPwd, setDeleteAccountPwd] = useState("");
	const [deletingAccount, setDeletingAccount] = useState(false);

	// Initialize __rt_was_logged_in flag for SSR auth to prevent AuthFetchGuard blocking
	useEffect(() => {
		if (hadSsrSettings && typeof window !== "undefined") {
			(window as any).__rt_was_logged_in = true;
		}
	}, [hadSsrSettings]);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const data = await api.get<{ providers?: ProviderKeyMeta[] }>("/users/me/provider-keys");
				if (cancelled) return;
				const next: Record<string, ProviderKeyMeta> = {};
				for (const row of data.providers || []) {
					next[row.provider] = row;
				}
				setProviderKeys(next);
			} catch {}
		})();
		return () => { cancelled = true; };
	}, []);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			const next: Record<string, string> = {};
			for (const p of BYOK_PROVIDERS) {
				const existing = localKeyPreview(p.id);
				if (existing && !existing.startsWith("...")) {
					next[p.id] = existing;
					continue;
				}
				try {
					const raw = await readLocalKey(p.id);
					if (!raw) {
						if (existing) next[p.id] = existing;
						continue;
					}
					const preview = maskKeyPreview(raw);
					next[p.id] = preview;
					const stored = JSON.parse(localStorage.getItem(`rt_byok_local_${p.id}`) || "{}");
					localStorage.setItem(`rt_byok_local_${p.id}`, JSON.stringify({ ...stored, preview }));
				} catch {
					if (existing) next[p.id] = existing;
				}
			}
			if (!cancelled) setLocalPreviews(next);
		})();
		return () => { cancelled = true; };
	}, []);

	const persistSettings = useCallback(async (overrides: Partial<UserSettingsPayload>) => {
		const body: UserSettingsPayload = {
			public_profile: publicProfile,
			dont_save_future_data: dontSaveFutureData,
			byok_sync_modes: syncModes,
			...overrides,
		};
		await api.put("/users/me/settings", body);
	}, [dontSaveFutureData, publicProfile, syncModes]);

	const saveLocalKey = useCallback(async (provider: string, rawKey: string) => {
		const enc = new TextEncoder();
		const material = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
		const iv = crypto.getRandomValues(new Uint8Array(12));
		const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, material, enc.encode(rawKey));
		await new Promise<void>((resolve, reject) => {
			const open = indexedDB.open("restailor-byok", 1);
			open.onupgradeneeded = () => open.result.createObjectStore("keys");
			open.onerror = () => reject(open.error);
			open.onsuccess = () => {
				const tx = open.result.transaction("keys", "readwrite");
				tx.objectStore("keys").put(material, provider);
				tx.oncomplete = () => resolve();
				tx.onerror = () => reject(tx.error);
			};
		});
		localStorage.setItem(`rt_byok_local_${provider}`, JSON.stringify({
			iv: Array.from(iv),
			cipher: Array.from(new Uint8Array(cipher)),
			tail: rawKey.slice(-4),
			preview: maskKeyPreview(rawKey),
		}));
	}, []);

	const handleSaveProviderKey = useCallback(async (provider: string) => {
		const raw = String(keyInputs[provider] || "").trim();
		if (!raw) {
			setAlert({ kind: "warning", text: "Enter a provider key before saving." });
			return;
		}
		setSavingProvider(provider);
		setAlert(null);
		try {
			if (syncModes[provider] === false) {
				await saveLocalKey(provider, raw);
				try { await api.delete(`/users/me/provider-keys/${provider}`); } catch {}
				setProviderKeys((prev) => ({ ...prev, [provider]: { provider, configured: true, key_tail: maskKeyPreview(raw), storage_mode: "local" } }));
				setLocalPreviews((prev) => ({ ...prev, [provider]: maskKeyPreview(raw) }));
			} else {
				const meta = await api.put<ProviderKeyMeta>(`/users/me/provider-keys/${provider}`, { api_key: raw, storage_mode: "server" });
				localStorage.removeItem(`rt_byok_local_${provider}`);
				setProviderKeys((prev) => ({ ...prev, [provider]: meta }));
			}
			setKeyInputs((prev) => ({ ...prev, [provider]: "" }));
			setAlert({ kind: "success", text: "Provider key saved." });
		} catch {
			setAlert({ kind: "error", text: "Could not save provider key." });
		} finally {
			setSavingProvider(null);
		}
	}, [keyInputs, saveLocalKey, syncModes]);

	const handleRemoveProviderKey = useCallback(async (provider: string) => {
		setSavingProvider(provider);
		try {
			try {
				await api.delete(`/users/me/provider-keys/${provider}`);
			} catch (err) {
				if ((err as ApiError)?.status !== 404) throw err;
			}
			localStorage.removeItem(`rt_byok_local_${provider}`);
			setProviderKeys((prev) => ({ ...prev, [provider]: { provider, configured: false } }));
			setLocalPreviews((prev) => {
				const next = { ...prev };
				delete next[provider];
				return next;
			});
			setAlert({ kind: "success", text: "Provider key removed." });
		} catch {
			setAlert({ kind: "error", text: "Could not remove provider key." });
		} finally {
			setSavingProvider(null);
		}
	}, []);

	// Load current settings on mount (abortable) - skip if we have SSR data
	useEffect(() => {
		if (hadSsrSettings) return; // Skip client fetch if we have SSR data
		
		const controller = new AbortController();
		(async () => {
			try {
				const d = await api.get<UserSettingsPayload>("/users/me/settings", { signal: controller.signal });
				setPublicProfile(Boolean(d?.public_profile));
				setDontSaveFutureData(Boolean(d?.dont_save_future_data));
				setSyncModes({ ...defaultSyncModes(), ...(d?.byok_sync_modes || {}) });
				setIsLoggedIn(true);
			} catch (e) {
				if (controller.signal.aborted) return;
				const err = e as ApiError;
				if (err?.status === 401 || err?.status === 403) {
					setIsLoggedIn(false);
					setAlert({ kind: "info", text: "Please log in to view your settings." });
				} else {
					setAlert({ kind: "warning", text: "Could not load settings. Try again shortly." });
				}
			} finally {
				if (!controller.signal.aborted) {
					setLoading(false);
					setAuthPending(false);
				}
			}
		})();
		return () => controller.abort();
	}, [hadSsrSettings]);

	// Client-side redirect for /settings route (protected workspace)
	const redirectedRef = useRef(false);
	useEffect(() => {
		if (authPending) return; // Wait for auth check to complete
		if (redirectedRef.current) return; // Prevent multiple redirects
		if (isLoggedIn === false && typeof window !== 'undefined' && window.location.pathname === '/settings') {
			// Redirect logged-out users to homepage
			redirectedRef.current = true;
			window.location.href = '/';
		}
	}, [authPending, isLoggedIn]);

	// Auto-save handler for public profile checkbox
	const handlePublicProfileToggle = useCallback(async (checked: boolean) => {
		if (loading || savingPublicProfile) return;
		
		// Optimistic update
		setPublicProfile(checked);
		setSavingPublicProfile(true);
		setPublicProfileSaved(false);
		setAlert(null);
		
		try {
			await persistSettings({
				public_profile: checked,
				dont_save_future_data: dontSaveFutureData,
			});
			setPublicProfileSaved(true);
			// Auto-hide after 3 seconds
			setTimeout(() => setPublicProfileSaved(false), 3000);
		} catch (e) {
			// Revert on error
			setPublicProfile(!checked);
			const err = e as ApiError;
			if (err?.status === 401 || err?.status === 403) {
				setAlert({ kind: "info", text: "Your session expired. Please log in again." });
			} else if (err instanceof ApiError) {
				setAlert({ kind: "error", text: "Could not save setting. Please try again." });
			} else {
				setAlert({ kind: "error", text: "Network error while saving. Please try again." });
			}
		} finally {
			setSavingPublicProfile(false);
		}
	}, [dontSaveFutureData, loading, persistSettings, savingPublicProfile]);

	// Auto-save handler for don't save future data checkbox
	const handleDontSaveToggle = useCallback(async (checked: boolean) => {
		if (loading || savingDontSave) return;
		
		// Optimistic update
		setDontSaveFutureData(checked);
		setSavingDontSave(true);
		setDontSaveSaved(false);
		setAlert(null);
		
		try {
			await persistSettings({
				public_profile: publicProfile,
				dont_save_future_data: checked,
			});
			setDontSaveSaved(true);
			// Auto-hide after 3 seconds
			setTimeout(() => setDontSaveSaved(false), 3000);
		} catch (e) {
			// Revert on error
			setDontSaveFutureData(!checked);
			const err = e as ApiError;
			if (err?.status === 401 || err?.status === 403) {
				setAlert({ kind: "info", text: "Your session expired. Please log in again." });
			} else if (err instanceof ApiError) {
				setAlert({ kind: "error", text: "Could not save setting. Please try again." });
			} else {
				setAlert({ kind: "error", text: "Network error while saving. Please try again." });
			}
		} finally {
			setSavingDontSave(false);
		}
	}, [publicProfile, loading, persistSettings, savingDontSave]);

	const handleSyncModeToggle = useCallback(async (provider: string, checked: boolean) => {
		const previous = syncModes;
		const next = { ...defaultSyncModes(), ...syncModes, [provider]: checked };
		setSyncModes(next);
		setAlert(null);
		try {
			await persistSettings({ byok_sync_modes: next });
		} catch {
			setSyncModes(previous);
			setAlert({ kind: "error", text: "Could not save sync preference." });
		}
	}, [persistSettings, syncModes]);

	const onDeleteAllData = useCallback(async () => {
		if (deletingData) return; // guard repeated clicks
		const val = String(deleteDataPwd || "").trim();
		if (!val) {
			setAlert({ kind: "warning", text: "Please enter your password." });
			return;
		}
		setDeletingData(true);
		try {
			// Note: Backend currently doesn't validate password for delete-data, but we collect it for consistency
			const r = await api.post<Response>("/users/me/delete-data", { confirm: true });
			setAlert({ kind: "success", text: "Deletion job enqueued." });
			setDeleteDataPwd("");
		} catch (e) {
			const err = e as ApiError;
			if (err?.status === 401 || err?.status === 403) {
				setAlert({ kind: "info", text: "Please log in to continue." });
			} else if (err instanceof ApiError) {
				setAlert({ kind: "error", text: "Could not enqueue deletion. Please try again." });
			} else {
				setAlert({ kind: "error", text: "Network error while requesting deletion. Please try again." });
			}
		} finally {
			setDeletingData(false);
		}
	}, [deleteDataPwd, deletingData]);

	const onDeleteAccount = useCallback(async () => {
		if (deletingAccount) return; // guard repeated clicks
		const val = String(deleteAccountPwd || "").trim();
		if (!val) {
			setAlert({ kind: "warning", text: "Please enter your password." });
			return;
		}
		setDeletingAccount(true);
		try {
			await api.post("/users/me/delete-account", { password: val });
			setAlert({ kind: "success", text: "Account deletion job enqueued." });
			// Do not auto-logout here to keep parity on messages; backend processes async
		} catch (e) {
			const err = e as ApiError;
			if (err?.status === 401 || err?.status === 403) {
				setAlert({ kind: "info", text: "Please log in to continue." });
			} else if (err instanceof ApiError) {
				setAlert({ kind: "error", text: "Could not enqueue account deletion. Please try again." });
			} else {
				setAlert({ kind: "error", text: "Network error while requesting account deletion. Please try again." });
			}
		} finally {
			setDeletingAccount(false);
		}
	}, [deleteAccountPwd, deletingAccount]);

	return (
		<div className="mx-auto max-w-4xl space-y-4 px-4 md:px-0" role="main">
			<h1 className="text-2xl font-semibold">Settings</h1>

			{/* Error/warning alerts only (success shown inline) */}
			{alert && alert.kind !== "success" && (
				<div 
					role="alert" 
					aria-live="polite"
					className={`fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-3 rounded-lg shadow-lg border transition-all duration-300 ${
						{
							info: "bg-blue-900/90 border-blue-500 text-blue-100",
							success: "bg-green-900/90 border-green-500 text-green-100",
							warning: "bg-yellow-900/90 border-yellow-500 text-yellow-100",
							error: "bg-red-900/90 border-red-500 text-red-100"
						}[alert.kind]
					}`}
				>
					{alert.text}
				</div>
			)}

			{/* Settings form */}
			{loading ? (
				<div className="rounded border border-slate-700 p-4">
					<div className="text-slate-400">Loading settings...</div>
				</div>
			) : (
				<div className="rounded border border-slate-700 p-4 space-y-4">
					{/* Public Profile Setting */}
					<div className="space-y-2">
						<div className="flex items-center gap-3">
							<div className="relative">
								<input 
									id="pp" 
									type="checkbox" 
									className="accent-amber-500"
									checked={publicProfile} 
									onChange={(e) => handlePublicProfileToggle(e.target.checked)}
									disabled={savingPublicProfile}
									aria-busy={savingPublicProfile}
								/>
								{savingPublicProfile && (
									<div className="absolute -right-6 top-0 h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" title="Saving..." />
								)}
							</div>
							<label htmlFor="pp" className="font-medium">Make my profile public</label>
							{savingPublicProfile && <span className="text-xs text-slate-400">Saving...</span>}
							{publicProfileSaved && <span className="text-xs text-green-400">Saved</span>}
						</div>
						<div className="text-sm text-slate-300 ml-6">Recruiters can discover your public profile in the future. Private by default.</div>
					</div>

					{/* Don't Save Future Data Setting */}
					<div className="space-y-2">
						<div className="flex items-center gap-3">
							<div className="relative">
								<input 
									id="nosave" 
									type="checkbox" 
									className="accent-amber-500"
									checked={dontSaveFutureData} 
									onChange={(e) => handleDontSaveToggle(e.target.checked)}
									disabled={savingDontSave}
									aria-busy={savingDontSave}
								/>
								{savingDontSave && (
									<div className="absolute -right-6 top-0 h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" title="Saving..." />
								)}
							</div>
							<label htmlFor="nosave" className="font-medium">Don't save future data</label>
							{savingDontSave && <span className="text-xs text-slate-400">Saving...</span>}
							{dontSaveSaved && <span className="text-xs text-green-400">Saved</span>}
						</div>
						<div className="text-sm text-slate-300 ml-6">We'll process your data in memory and won't store your resume, job description, or generated results.</div>
					</div>
				</div>
			)}

			<div className="rounded border border-slate-700 p-4 space-y-4">
				<div>
					<h2 className="text-lg font-semibold">BYOK Provider Keys</h2>
					<p className="text-sm text-slate-400 mt-1">Model runs require your own provider API key.</p>
				</div>
				<div className="space-y-3">
					{BYOK_PROVIDERS.map((p) => {
						const meta = providerKeys[p.id];
						const localPreview = localPreviews[p.id] || localKeyPreview(p.id);
						const local = meta?.storage_mode === "local" || Boolean(localPreview);
						const keyPreview = meta?.key_tail || localPreview;
						const displayValue = keyInputs[p.id] ?? (meta?.configured || local ? keyPreview : "");
						return (
							<div key={p.id} className="rounded border border-slate-700 p-3">
								<div className="flex flex-col gap-3 md:flex-row md:items-center">
									<div className="md:w-32">
										<div className="font-medium">{p.label}</div>
										<div className="text-xs text-slate-400">{meta?.configured || local ? "Saved" : "Missing"}</div>
									</div>
									<div className="min-w-0 flex-1">
										<input
											type={keyInputs[p.id] !== undefined ? "password" : "text"}
											value={displayValue}
											onChange={(e) => setKeyInputs((prev) => ({ ...prev, [p.id]: e.target.value }))}
											placeholder={p.placeholder}
											className="w-full rounded border border-slate-700 bg-transparent px-3 py-2 text-sm"
										/>
									</div>
									<label className="inline-flex items-center gap-2 text-sm text-slate-300">
										<input
											type="checkbox"
											className="accent-amber-500"
											checked={Boolean(syncModes[p.id])}
											onChange={(e) => handleSyncModeToggle(p.id, e.target.checked)}
										/>
										Sync to server
									</label>
									<div className="flex gap-2">
										<button className="rounded bg-slate-700 px-3 py-2 text-sm hover:bg-slate-600 disabled:opacity-50" disabled={savingProvider === p.id} onClick={() => handleSaveProviderKey(p.id)}>Save</button>
										<button className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-50" disabled={savingProvider === p.id} onClick={() => handleRemoveProviderKey(p.id)}>Remove</button>
									</div>
								</div>
							</div>
						);
					})}
				</div>
			</div>
			
			<hr className="border-slate-700" />
			<h2 className="text-xl font-semibold">Delete your data</h2>

			{/* Delete all my data section */}
			<div className="space-y-4">
				<div>
					<h3 className="font-medium mb-2">Delete all my data</h3>
					<div className="text-sm text-slate-300 space-y-1 mb-3">
						<p>This removes all your stored content but keeps your account active:</p>
						<ul className="list-disc list-inside ml-2 space-y-1">
							<li>All job submissions (resumes, job descriptions)</li>
							<li>All AI-generated content (tailored resumes, fit analyses)</li>
							<li>2FA settings and trusted devices</li>
							<li>Cached inputs</li>
						</ul>
						<p className="mt-2 text-slate-400">
							<strong>Keeps:</strong> Your account, username, credits, application tracking, and settings.
						</p>
					</div>
					
					<form
						onSubmit={(e) => { e.preventDefault(); onDeleteAllData(); }}
						noValidate
						method="post"
						className="space-y-2"
						aria-busy={deletingData}
					>
						{/* Visually hidden username field for password manager context & a11y */}
						<input
							type="text"
							name="username"
							autoComplete="username"
							tabIndex={-1}
							aria-hidden="true"
							className="sr-only opacity-0 pointer-events-none"
							readOnly
							value=""
						/>
						
						<label className="block text-sm" htmlFor="delete-data-pwd">
							Enter your password to confirm:
						</label>
						<input
							id="delete-data-pwd"
							name="current-password"
							className="w-full md:max-w-md rounded border border-slate-700 bg-transparent p-2"
							type="password"
							autoComplete="current-password"
							placeholder="Your password"
							value={deleteDataPwd}
							onChange={(e) => setDeleteDataPwd(e.target.value)}
						/>
						
						<button 
							type="submit"
							className="w-full md:max-w-md rounded bg-slate-700 px-3 py-2 hover:bg-slate-600 transition-colors disabled:opacity-50" 
							disabled={!deleteDataPwd.trim() || deletingData}
						>
							{deletingData ? "Deleting data…" : "Delete all my data"}
						</button>
					</form>
				</div>

				<hr className="border-slate-700" />

				{/* Delete my account section */}
				<div>
					<h3 className="font-medium mb-2">Delete my account</h3>
					<div className="text-sm text-slate-300 space-y-1 mb-3">
						<p>Permanently delete your account and all associated data:</p>
						<ul className="list-disc list-inside ml-2 space-y-1">
							<li>Everything from "Delete all my data" above</li>
							<li>Your account (username, email, password)</li>
							<li>All credits (forfeited, no refunds)</li>
							<li>Application tracking and analytics</li>
							<li>All settings and preferences</li>
						</ul>
						<p className="mt-2 text-red-400">
							<strong>Warning:</strong> This action cannot be undone.
						</p>
					</div>

					<form
						onSubmit={(e) => { e.preventDefault(); onDeleteAccount(); }}
						noValidate
						method="post"
						className="space-y-2"
						aria-busy={deletingAccount}
					>
						{/* Visually hidden username field for password manager context & a11y */}
						<input
							type="text"
							name="username"
							autoComplete="username"
							tabIndex={-1}
							aria-hidden="true"
							className="sr-only opacity-0 pointer-events-none"
							readOnly
							value=""
						/>
						<label className="block text-sm" htmlFor="delete-pwd">
							Enter your password to confirm account deletion:
						</label>
						<input
							id="delete-pwd"
							name="current-password"
							className="w-full md:max-w-md rounded border border-slate-700 bg-transparent p-2"
							type="password"
							autoComplete="current-password"
							placeholder="Your password"
							value={deleteAccountPwd}
							onChange={(e) => setDeleteAccountPwd(e.target.value)}
						/>
						<button
							type="submit"
							className="w-full md:max-w-md rounded bg-red-600 px-3 py-2 disabled:opacity-50 hover:bg-red-700 transition-colors"
							disabled={!deleteAccountPwd.trim() || deletingAccount}
						>
							{deletingAccount ? "Deleting account…" : "Delete my account permanently"}
						</button>
					</form>
				</div>
			</div>
		</div>
	);
}
