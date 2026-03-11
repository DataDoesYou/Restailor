"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import api, { ApiError } from "@/lib/api";

type Alert = { kind: "info" | "success" | "warning" | "error"; text: string } | null;

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

	// Load current settings on mount (abortable) - skip if we have SSR data
	useEffect(() => {
		if (hadSsrSettings) return; // Skip client fetch if we have SSR data
		
		const controller = new AbortController();
		(async () => {
			try {
				const d = await api.get<{ public_profile?: boolean; dont_save_future_data?: boolean }>("/users/me/settings", { signal: controller.signal });
				setPublicProfile(Boolean(d?.public_profile));
				setDontSaveFutureData(Boolean(d?.dont_save_future_data));
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
			await api.put("/users/me/settings", {
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
	}, [dontSaveFutureData, loading, savingPublicProfile]);

	// Auto-save handler for don't save future data checkbox
	const handleDontSaveToggle = useCallback(async (checked: boolean) => {
		if (loading || savingDontSave) return;
		
		// Optimistic update
		setDontSaveFutureData(checked);
		setSavingDontSave(true);
		setDontSaveSaved(false);
		setAlert(null);
		
		try {
			await api.put("/users/me/settings", {
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
	}, [publicProfile, loading, savingDontSave]);

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
		<div className="mx-auto max-w-xl space-y-4 px-4 md:px-0" role="main">
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

