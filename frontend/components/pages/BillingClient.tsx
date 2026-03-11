"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api, { ApiError } from "@/lib/api";
import Link from "next/link";
import { MODEL_OPTIONS } from "@/components/resume/models";

type Balance = { 
	balance_usd?: string | number; 
	balance_cents?: number;
	purchased_balance_cents?: number;
	trial_balance_cents?: number;
} | null;
type Trial = { 
	eligible?: boolean; 
	reason?: string; 
	trial_models?: string[]; 
	trial_duration_days?: number; 
	trial_end_date?: string; 
	[k: string]: unknown 
} | null;
type Summary = {
	averages_by_model?: Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }>;
	price_map?: Record<string, { input?: string | number; output?: string | number }>;
	multiplier?: string | number | null;
} | null;

type Props = {
	initialBalance?: Balance;
	initialTrial?: Trial;
	initialSummary?: Summary;
	initialIsAdmin?: boolean;
	initialUseMyAvgs?: boolean;
	initialUserAvgs?: Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }>;
};

export default function BillingClient({ initialBalance = null, initialTrial = null, initialSummary = null, initialIsAdmin = false, initialUseMyAvgs = false, initialUserAvgs }: Props) {
	const [balance, setBalance] = useState<Balance>(initialBalance);
	const [trial, setTrial] = useState<Trial>(initialTrial);
	const [summary, setSummary] = useState<Summary>(initialSummary);
	const [userAvgs, setUserAvgs] = useState<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }>>(Array.isArray(initialUserAvgs) ? initialUserAvgs : []);
	const [userAvgsLoading, setUserAvgsLoading] = useState<boolean>(false);
	const [userAvgsFetched, setUserAvgsFetched] = useState<boolean>(false); // becomes true after first response
	const userAvgsCache = useRef<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> | null>(null);
	const [useMyAvgs, setUseMyAvgs] = useState<boolean>(() => {
		// Prefer SSR-provided initial value to avoid hydration mismatch, fallback to localStorage client-side
		if (typeof window === "undefined") return Boolean(initialUseMyAvgs);
		try { return (localStorage.getItem("use_my_avgs") === "1"); } catch { return Boolean(initialUseMyAvgs); }
	});
	const [isAdmin, setIsAdmin] = useState<boolean>(Boolean(initialIsAdmin));
	const [alert, setAlert] = useState<{ kind: "info" | "success" | "warning" | "error"; text: string } | null>(null);
	const [authPending, setAuthPending] = useState<boolean>(true);
	const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(null);

	// Load/refresh base data (seeded by SSR props to avoid flicker)
	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const [bal, tr, sum, me] = await Promise.all([
					api.get<Balance>("/users/me/balance").catch(() => null),
					api.get<Trial>("/credits/trial-eligibility").catch(() => null),
					api.get<Summary>("/billing/summary").catch(() => null),
					api.get<{ role?: string }>("/users/me").catch(() => null),
				]);
				if (cancelled) return;
				if (bal) setBalance(bal);
				if (tr) setTrial(tr);
				if (sum) setSummary(sum);
				if (me) {
					setIsAdmin(Boolean(me?.role === "admin"));
					setIsLoggedIn(true);
				} else {
					setIsLoggedIn(false);
				}
				setAuthPending(false);
			} catch {
				if (cancelled) return;
				setIsLoggedIn(false);
				setAuthPending(false);
			}
		})();
		return () => { cancelled = true; };
	}, []);

	// Client-side redirect for /billing route (protected workspace)
	useEffect(() => {
		if (authPending) return; // Wait for auth check to complete
		if (isLoggedIn === false && typeof window !== 'undefined' && window.location.pathname === '/billing') {
			// Redirect logged-out users to homepage
			window.location.href = '/';
		}
	}, [authPending, isLoggedIn]);

	// Persist toggle and broadcast to other tabs/pages
	useEffect(() => {
		try {
			localStorage.setItem("use_my_avgs", useMyAvgs ? "1" : "0");
			const secure = (typeof location !== "undefined" && location.protocol === "https:") ? "; Secure" : "";
			document.cookie = `rt_use_my_avgs=${useMyAvgs ? "1" : "0"}; Path=/; SameSite=Lax${secure}; Max-Age=${365*24*60*60}`;
			window.dispatchEvent(new CustomEvent("rt-settings", { detail: { useMyAvgs } }));
		} catch {}
	}, [useMyAvgs]);

	// Personal averages
	useEffect(() => {
		let cancelled = false;
	// When disabled, just hide the section but keep any cached result (even empty) to avoid flicker on re-enable
	if (!useMyAvgs) { setUserAvgs([]); setUserAvgsLoading(false); setUserAvgsFetched(false); return; }

	// If we already have a cached value (including an empty array), show it immediately and refetch in background without toggling loading
	if (userAvgsCache.current !== null) {
		setUserAvgs(userAvgsCache.current);
		setUserAvgsFetched(true);
		setUserAvgsLoading(false);
		(async () => {
			try {
				const rows = await api.get<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }>>("/pricing/averages", { query: { scope: "user" } });
				if (!cancelled && Array.isArray(rows)) { setUserAvgs(rows); userAvgsCache.current = rows; }
			} catch {
				// keep existing cached view on failure
			}
		})();
		return () => { cancelled = true; };
	}

	// First enable with no cache: show skeleton while fetching
	setUserAvgsFetched(false);
	setUserAvgsLoading(true);
	(async () => {
		try {
			const rows = await api.get<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }>>("/pricing/averages", { query: { scope: "user" } });
			if (!cancelled && Array.isArray(rows)) { setUserAvgs(rows); userAvgsCache.current = rows; }
		} catch {
			if (!cancelled) { setUserAvgs([]); userAvgsCache.current = []; }
		} finally {
			if (!cancelled) { setUserAvgsLoading(false); setUserAvgsFetched(true); }
		}
	})();
	return () => { cancelled = true; };
	}, [useMyAvgs]);

	const onClaimTrial = useCallback(async () => {
		try {
			await api.post("/credits/claim-trial", {});
			setAlert({ kind: "success", text: "Trial claimed. Your balance has been updated." });
			// Refresh balance
			try {
				const b = await api.get<Balance>("/users/me/balance");
				setBalance(b);
				// Dispatch event to update sidebar
				try {
					window.dispatchEvent(new CustomEvent("rt-balance", { detail: b }));
				} catch {}
			} catch {}
		} catch (e) {
			const err = e as ApiError;
			let detail: string | undefined;
			try { detail = typeof err.detail === "string" ? err.detail : (err.detail as any)?.detail; } catch {}
			setAlert({ kind: "error", text: detail ? `Cannot claim: ${detail}` : "Could not claim free trial." });
		}
	}, []);

	const amounts = [5, 10, 25, 50, 100];
	const onPurchase = useCallback(async (usd: number) => {
		try {
			const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/billing/purchase-intent`, {
				method: "POST",
				credentials: "include",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ amount_usd: usd }),
			});
			if (r.status === 501) {
				setAlert({ kind: "info", text: "Stripe coming soon" });
			} else if (r.ok) {
				const data = await r.json();
				if (data.checkout_url) {
					// Redirect to Stripe Checkout
					window.location.href = data.checkout_url;
				} else {
					setAlert({ kind: "error", text: "No checkout URL returned" });
				}
			} else {
				// Parse error details from API response
				let errorMessage = "Purchase failed";
				try {
					const errorData = await r.json();
					if (errorData.detail) {
						const detail = typeof errorData.detail === "string" 
							? errorData.detail 
							: JSON.stringify(errorData.detail);
						errorMessage = `Purchase failed: ${detail}`;
					} else {
						errorMessage = `Purchase failed (${r.status} ${r.statusText})`;
					}
				} catch {
					errorMessage = `Purchase failed (${r.status} ${r.statusText})`;
				}
				setAlert({ kind: "error", text: errorMessage });
			}
		} catch (err) {
			const errorMsg = err instanceof Error ? err.message : "Unknown error";
			setAlert({ kind: "error", text: `Network error: ${errorMsg}` });
		}
	}, []);

	// Build global averages pivot: rows=request_type, cols=model, cells="$price (n)"
	const avgTable = useMemo(() => {
		const rows = (summary?.averages_by_model || []).slice();
		if (!rows.length) return null as null | { reqs: string[]; models: string[]; grid: string[][] };
		
		// Get active model IDs from MODEL_OPTIONS
		const activeModelIds = new Set(MODEL_OPTIONS.map(m => m.model_id));
		
		// Filter to only active models and map to friendly names
		const modelIdToAlias: Record<string, string> = {};
		const aliasToModelId: Record<string, string> = {};
		MODEL_OPTIONS.forEach(m => {
			modelIdToAlias[m.model_id] = m.alias;
			aliasToModelId[m.alias] = m.model_id;
		});
		
		// Filter rows to only include active models
		const activeRows = rows.filter(r => {
			const modelId = String(r.model || "");
			return activeModelIds.has(modelId);
		});
		
		if (!activeRows.length) return null as null | { reqs: string[]; models: string[]; grid: string[][] };
		
		const reqs = Array.from(new Set(activeRows.map((r) => String(r.request_type || "")))).sort();
		// Use friendly aliases for display, sorted alphabetically
		const modelAliases = Array.from(new Set(activeRows.map((r) => {
			const modelId = String(r.model || "");
			return modelIdToAlias[modelId] || modelId;
		}))).sort();
		
		const idxReq: Record<string, number> = Object.fromEntries(reqs.map((r, i) => [r, i]));
		const grid: string[][] = Array.from({ length: reqs.length }, () => Array(modelAliases.length).fill("—"));
		
		for (const r of activeRows) {
			const rt = String(r.request_type || "");
			const modelId = String(r.model || "");
			const alias = modelIdToAlias[modelId] || modelId;
			const price = r.avg_price_usd;
			const n = r.n;
			if (rt in idxReq && modelAliases.includes(alias)) {
				const ri = idxReq[rt]; const ci = modelAliases.indexOf(alias);
				grid[ri][ci] = `$${price} (${n})`;
			}
		}
		return { reqs, models: modelAliases, grid };
	}, [summary]);

	// Build user averages pivot (same format as global), using userAvgs rows
	const myAvgTable = useMemo(() => {
		const rows = (userAvgs || []).slice();
		if (!rows.length) return null as null | { reqs: string[]; models: string[]; grid: string[][] };
		
		// Get active model IDs from MODEL_OPTIONS
		const activeModelIds = new Set(MODEL_OPTIONS.map(m => m.model_id));
		
		// Filter to only active models and map to friendly names
		const modelIdToAlias: Record<string, string> = {};
		MODEL_OPTIONS.forEach(m => {
			modelIdToAlias[m.model_id] = m.alias;
		});
		
		// Filter rows to only include active models
		const activeRows = rows.filter(r => {
			const modelId = String(r.model || "");
			return activeModelIds.has(modelId);
		});
		
		if (!activeRows.length) return null as null | { reqs: string[]; models: string[]; grid: string[][] };
		
		const reqs = Array.from(new Set(activeRows.map((r) => String(r.request_type || "")))).sort();
		// Use friendly aliases for display, sorted alphabetically
		const modelAliases = Array.from(new Set(activeRows.map((r) => {
			const modelId = String(r.model || "");
			return modelIdToAlias[modelId] || modelId;
		}))).sort();
		
		const idxReq: Record<string, number> = Object.fromEntries(reqs.map((r, i) => [r, i]));
		const grid: string[][] = Array.from({ length: reqs.length }, () => Array(modelAliases.length).fill("—"));
		
		for (const r of activeRows) {
			const rt = String(r.request_type || "");
			const modelId = String(r.model || "");
			const alias = modelIdToAlias[modelId] || modelId;
			const price = r.avg_price_usd;
			const n = r.n;
			if (rt in idxReq && modelAliases.includes(alias)) {
				const ri = idxReq[rt]; const ci = modelAliases.indexOf(alias);
				grid[ri][ci] = `$${price} (${n})`;
			}
		}
		return { reqs, models: modelAliases, grid };
	}, [userAvgs]);

	// Helper to map trial model provider names to display names
	const formatTrialModels = (models: string[] | undefined) => {
		if (!models || models.length === 0) return null;
		
		// Map to aliases
		const aliases = models.map(modelId => {
			const option = MODEL_OPTIONS.find(opt => 
				opt.model_id === modelId || 
				(opt.legacy_model_ids && opt.legacy_model_ids.includes(modelId))
			);
			return option ? option.alias : modelId;
		});

		// Deduplicate
		const uniqueAliases = Array.from(new Set(aliases));

		// Sort by sidebar order (MODEL_OPTIONS)
		uniqueAliases.sort((a, b) => {
			const idxA = MODEL_OPTIONS.findIndex(m => m.alias === a);
			const idxB = MODEL_OPTIONS.findIndex(m => m.alias === b);
			// Put unknown models at the end
			const orderA = idxA === -1 ? 999 : idxA;
			const orderB = idxB === -1 ? 999 : idxB;
			return orderA - orderB;
		});

		return uniqueAliases.join(", ");
	};

	return (
		<div className="space-y-4 px-4 md:px-0">
			<h1 className="text-2xl font-semibold">Billing</h1>

			{alert && (
				<div className={{ info: "text-blue-400", success: "text-green-400", warning: "text-yellow-400", error: "text-red-400" }[alert.kind]}>{alert.text}</div>
			)}

			{/* Trial nudges */}
			{trial && (
				<div>
					{trial.reason === "needs_2fa" ? (
						<div>
							<h2 className="text-xl font-semibold">Free trial</h2>
							<p>Enable 2FA with an authenticator app or add a passkey to claim your free trial.</p>
							{formatTrialModels(trial.trial_models) && (
								<p className="text-sm text-slate-400 mt-2">
									Trial includes: {formatTrialModels(trial.trial_models)}
									{trial.trial_duration_days && ` (${trial.trial_duration_days} days)`}
								</p>
							)}
						<div className="flex gap-2 mt-3">
							<Link href="/security" className="rounded bg-slate-700 px-3 py-2 text-center">Go to Security</Link>
						</div>
							<hr className="my-4 border-slate-700" />
						</div>
		    ) : trial.eligible ? (
						<div>
							<h2 className="text-xl font-semibold">Free trial</h2>
							{formatTrialModels(trial.trial_models) && (
								<p className="text-sm text-slate-400 mt-2">
									Trial includes: {formatTrialModels(trial.trial_models)}
									{trial.trial_duration_days && ` (${trial.trial_duration_days} days)`}
								</p>
							)}
			    <button className="rounded bg-slate-700 px-3 py-2 mt-2" onClick={onClaimTrial}>Claim free trial</button>
							<hr className="my-4 border-slate-700" />
						</div>
					) : null}
				</div>
			)}

			{/* Active trial info - show when user has trial balance but no purchased balance */}
			{balance && (balance.trial_balance_cents ?? 0) > 0 && (balance.purchased_balance_cents ?? 0) === 0 && trial?.trial_models && trial.trial_models.length > 0 && (
				<div className="bg-slate-800/50 border border-slate-700 rounded p-4">
					<h2 className="text-lg font-semibold mb-2">Using Free Trial</h2>
					<p className="text-sm text-slate-300">
						You're currently using trial credits. Available models: {formatTrialModels(trial.trial_models)}
					</p>
					{trial.trial_duration_days && (
						<p className="text-xs text-slate-400 mt-1">
							Trial credits expire after {trial.trial_duration_days} days
						</p>
					)}
					<p className="text-sm text-slate-400 mt-2">
						Purchase credits to unlock all models.
					</p>
				</div>
			)}

			{/* Current balance - responsive grid */}
			<div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
				<div>
					<div className="text-sm uppercase text-slate-400 mb-2">Current Balance</div>
					<div className="text-3xl font-semibold">${balance && balance.balance_usd !== undefined ? String(balance.balance_usd) : "0.00"}</div>
				</div>

				{/* Purchase credits */}
				<div className="md:col-span-2">
					<h2 className="text-xl font-semibold">Purchase credits</h2>
					<div className="grid grid-cols-3 md:grid-cols-5 gap-2 mt-3">
						{amounts.map((amt) => (
							<button key={amt} className="rounded bg-slate-700 px-3 py-2 hover:bg-slate-600 active:bg-slate-500" onClick={() => onPurchase(amt)}>${amt}</button>
						))}
					</div>
				</div>
			</div>

			<hr className="border-slate-700" />

			{/* Personal averages toggle/preview */}
			<div>
				<label className="inline-flex items-center gap-2">
					<input
						type="checkbox"
						checked={useMyAvgs}
						onChange={(e) => {
							const checked = e.target.checked;
							// Prefer cached snapshot (even empty) to avoid skeleton flicker; effect will refetch in background
							if (checked) {
								if (userAvgsCache.current !== null) {
									setUserAvgs(userAvgsCache.current);
									setUserAvgsFetched(true);
									setUserAvgsLoading(false);
								} else {
									setUserAvgsFetched(false);
									setUserAvgsLoading(true);
								}
							} else {
								setUserAvgsLoading(false);
								setUserAvgs([]);
								// keep cache so re-enabling can render instantly
							}
							// Persist + broadcast immediately so other pages (e.g., Resume) update tooltips without a fetch
							try {
								localStorage.setItem("use_my_avgs", checked ? "1" : "0");
								const secure = (typeof location !== "undefined" && location.protocol === "https:") ? "; Secure" : "";
								document.cookie = `rt_use_my_avgs=${checked ? "1" : "0"}; Path=/; SameSite=Lax${secure}; Max-Age=${365*24*60*60}`;
								window.dispatchEvent(new CustomEvent("rt-settings", { detail: { useMyAvgs: checked } }));
							} catch {}
							setUseMyAvgs(checked);
						}}
					/>
					<span>Use my averages for tooltips</span>
					{useMyAvgs && !userAvgsFetched && (
						<span className="text-slate-400 text-sm ml-2">Loading…</span>
					)}
				</label>
				{useMyAvgs && userAvgsFetched && (
					<div className="mt-2">
						{userAvgs.length && myAvgTable ? (
							<>
								<div className="text-slate-400 text-sm">Your averages (last 100 per model)</div>
								<div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
									<table className="min-w-full text-sm">
										<thead>
											<tr>
												<th className="text-left pr-4">request_type</th>
												{myAvgTable.models.map((m) => (
													<th key={m} className="text-left pr-4 whitespace-nowrap">{m}</th>
												))}
											</tr>
										</thead>
										<tbody>
											{myAvgTable.reqs.map((rt, i) => (
												<tr key={rt}>
													<td className="pr-4">{rt}</td>
													{myAvgTable.models.map((m, j) => (
														<td key={`${i}-${j}`} className="pr-4 whitespace-nowrap">{myAvgTable.grid[i][j]}</td>
													))}
												</tr>
											))}
										</tbody>
									</table>
								</div>
							</>
						) : (
							<div className="text-slate-400 text-sm">No personal averages yet.</div>
						)}
					</div>
				)}
			</div>

			{/* Global averages */}
			{avgTable && (
				<div>
					<h2 className="text-xl font-semibold">Averages (global, last 100 per model)</h2>
					<div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
						<table className="min-w-full text-sm">
							<thead>
								<tr>
									<th className="text-left pr-4">request_type</th>
									{avgTable.models.map((m) => (
										<th key={m} className="text-left pr-4 whitespace-nowrap">{m}</th>
									))}
								</tr>
							</thead>
							<tbody>
								{avgTable.reqs.map((rt, i) => (
									<tr key={rt}>
										<td className="pr-4">{rt}</td>
										{avgTable.models.map((m, j) => (
											<td key={`${i}-${j}`} className="pr-4 whitespace-nowrap">{avgTable.grid[i][j]}</td>
										))}
									</tr>
								))}
							</tbody>
						</table>
					</div>
					{((summary?.price_map && Object.keys(summary.price_map).length) || summary?.multiplier != null) ? (
						<hr className="my-4 border-slate-700" />
					) : null}
				</div>
			)}

			{/* Price map */}
			<div>
					<h2 className="text-xl font-semibold">Current price map</h2>
					{summary?.multiplier != null && (
						<div className="text-slate-400 text-sm">Multiplier: x{String(summary.multiplier)}</div>
					)}
					{summary?.price_map && Object.keys(summary.price_map).length > 0 ? (
						<div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 mt-2">
							<table className="min-w-full text-sm">
								<thead>
									<tr>
										<th className="text-left pr-4">model</th>
										<th className="text-left pr-4 whitespace-nowrap">input (per 1M tokens)</th>
										<th className="text-left pr-4 whitespace-nowrap">output (per 1M tokens)</th>
									</tr>
								</thead>
								<tbody>
									{(() => {
										// Get active model IDs and create alias mapping, preserving MODEL_OPTIONS order
										const modelIdToAlias: Record<string, string> = {};
										const modelIdToOrder: Record<string, number> = {};
										MODEL_OPTIONS.forEach((m, idx) => {
											modelIdToAlias[m.model_id] = m.alias;
											modelIdToOrder[m.model_id] = idx;
										});
										const activeModelIds = new Set(MODEL_OPTIONS.map(m => m.model_id));
										
										// Filter and sort by MODEL_OPTIONS order (sidebar order)
										return Object.entries(summary.price_map)
											.filter(([modelId]) => activeModelIds.has(modelId))
											.sort(([a], [b]) => {
												const orderA = modelIdToOrder[a] ?? 999;
												const orderB = modelIdToOrder[b] ?? 999;
												return orderA - orderB;
											})
											.map(([modelId, rates]) => (
												<tr key={modelId}>
													<td className="pr-4">{modelIdToAlias[modelId] || modelId}</td>
													<td className="pr-4 whitespace-nowrap">{String(rates.input ?? "")}</td>
													<td className="pr-4 whitespace-nowrap">{String(rates.output ?? "")}</td>
												</tr>
											));
									})()}
								</tbody>
							</table>
						</div>
					) : null}
					<div className="mt-2" />
				</div>
		</div>
	);
}

