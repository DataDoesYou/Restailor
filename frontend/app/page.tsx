import ResumeTailorClient from "@/components/pages/ResumeTailorClient";
import HomepageDebugOverlay from "@/components/debug/HomepageDebugOverlay";
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import "server-only";

function getApiBase(): string {
	const base = process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "";
	if (!base) throw new Error("API base not set");
	return base.replace(/\/$/, "");
}

export default async function Page({ searchParams }: { searchParams: Promise<{ [k: string]: string | string[] | undefined }> }) {
	// If we arrive from the email link (?reset=1&token=...), route to the reset page.
	const sp = await searchParams || {};
	const reset = (Array.isArray(sp.reset) ? sp.reset[0] : sp.reset) ?? undefined;
	const token = (Array.isArray(sp.token) ? sp.token[0] : sp.token) ?? undefined;
	const debugParam = String((Array.isArray(sp.debug) ? sp.debug[0] : sp.debug) || "").toLowerCase();
	const debugRequested = debugParam === "true" || debugParam === "1";
	if ((reset === "1" || String(reset || "").toLowerCase() === "true") && token) {
			redirect(`/reset-password?token=${encodeURIComponent(token)}`);
	}

	const h = await headers();
	const cookie = h.get("cookie") || "";
	const hasAuth = /(?:^|; )rt_session=/.test(cookie) || /(?:^|; )rt_access=/.test(cookie) || /(?:^|; )rt_access_ephem=/.test(cookie);
	
	// STEAM: Only read UI preference cookies, not state cookies
	const showJudgeCookie = (() => { const m = /(?:^|; )rt_show_judge=([^;]+)/.exec(cookie); return m ? decodeURIComponent(m[1]) === "1" : undefined; })();
	const judgeLabelCookie = (() => { const m = /(?:^|; )rt_judge_label=([^;]+)/.exec(cookie); return m ? decodeURIComponent(m[1]) : undefined; })();
	const resultTypeCookie = (() => { const m = /(?:^|; )rt_result_type=([^;]+)/.exec(cookie); return m ? decodeURIComponent(m[1]) : undefined; })();
	const resultTypeInitial = ["fit","tailor","judge"].includes(resultTypeCookie || "") ? resultTypeCookie : "fit";
	const statsMdCookie = (() => { const m = /(?:^|; )rt_stats_md=([^;]+)/.exec(cookie); return m ? decodeURIComponent(m[1]) : undefined; })();

	// STEAM: No cookie-based applied state - database only
	let initialApplied = false;
	let initialFitOutput: string | undefined = undefined;
	let initialTailoredOutput: string | undefined = undefined;
	let initialJudgeOutput: string | undefined = undefined;
	let initialStatsMdServer: string | undefined = statsMdCookie;
	let initialSnapshotLoaded = false;
	let initialResumeText: string | undefined = undefined;
	let initialJdText: string | undefined = undefined;
	let initialAppliedBanner: string | undefined = undefined;
	// Trial/banner numbers for SSR to avoid $1.00 flicker on hydration
	let initialTrialUsd: string | undefined = undefined;
	let initialFreeReqHint: number | undefined = undefined;
	let currentSnapshotLookupAttempted = false;
	let showHomepageDebug = false;
	let homepageDebugLoggedOut = false;

	// Load snapshot: first try ?appliedKey=, then fall back to current_snapshot_key from database
	try {
		const ak = (Array.isArray(sp.appliedKey) ? sp.appliedKey[0] : sp.appliedKey);
		const forceAppliedParam = (Array.isArray(sp.forceApplied) ? sp.forceApplied[0] : sp.forceApplied);
		
		let snapshotKeyToLoad: string | undefined = ak;
		
		// If no appliedKey in URL, check if user has a current_snapshot_key in database
		if (!snapshotKeyToLoad && hasAuth) {
			currentSnapshotLookupAttempted = true;
			const currentSnapshotRes = await fetch(`${getApiBase()}/users/me/current-snapshot`, {
				headers: cookie ? { Cookie: cookie } : undefined,
				credentials: "include",
				cache: "no-store",
			});
			if (currentSnapshotRes.ok) {
				const currentSnapshotData: any = await currentSnapshotRes.json().catch(() => null);
				if (currentSnapshotData?.current_snapshot_key) {
					snapshotKeyToLoad = currentSnapshotData.current_snapshot_key;
				}
			}
		}
		
		// Load snapshot by key (either from URL or from user's current_snapshot_key)
		if (snapshotKeyToLoad) {
			const res = await fetch(`${getApiBase()}/applications/by-key?appliedKey=${encodeURIComponent(snapshotKeyToLoad)}`, {
				headers: cookie ? { Cookie: cookie } : undefined,
				credentials: "include",
				cache: "no-store",
			});
			if (res.ok) {
				const js: any = await res.json().catch(() => null);
				if (js?.found && js?.row) {
					initialApplied = !!js.row.isApplied || String(forceAppliedParam || '') === '1';
					const snap = js.row.snapshot || {};
					if (snap && typeof snap === 'object') {
						if (typeof snap.fitOutput === 'string') initialFitOutput = snap.fitOutput;
						if (typeof snap.tailoredOutput === 'string') initialTailoredOutput = snap.tailoredOutput;
						if (typeof snap.judgeOutput === 'string') initialJudgeOutput = snap.judgeOutput;
						if (!initialStatsMdServer && typeof snap.statsMd === 'string') initialStatsMdServer = snap.statsMd;
						if (typeof snap.resumeInput === 'string') initialResumeText = snap.resumeInput;
						if (typeof snap.jdInput === 'string') initialJdText = snap.jdInput;
						if (initialApplied) {
							initialAppliedBanner = "Applied snapshot opened – editing either box will create a new draft";
						} else {
							initialAppliedBanner = "Previously seen JD – loaded latest results (re-run to refresh)";
						}
						if (initialFitOutput || initialTailoredOutput || initialJudgeOutput || initialResumeText || initialJdText) {
							initialSnapshotLoaded = true;
						}
					}
				}
			}
		} else if (!hasAuth) {
			// Demo: Load random snapshot for logged out users
			try {
				const res = await fetch(`${getApiBase()}/applications/demo/random`, {
					headers: cookie ? { Cookie: cookie } : undefined,
					credentials: "include",
					cache: "no-store",
				});
				if (res.ok) {
					const js: any = await res.json().catch(() => null);
					if (js?.found && js?.row) {
						// Don't set initialApplied=true to avoid "Applied" green badges unless desired.
						// Use banner to indicate demo status.
						const snap = js.row.snapshot || {};
						if (snap && typeof snap === 'object') {
							if (typeof snap.fitOutput === 'string') initialFitOutput = snap.fitOutput;
							if (typeof snap.tailoredOutput === 'string') initialTailoredOutput = snap.tailoredOutput;
							if (typeof snap.judgeOutput === 'string') initialJudgeOutput = snap.judgeOutput;
							if (!initialStatsMdServer && typeof snap.statsMd === 'string') initialStatsMdServer = snap.statsMd;
							if (typeof snap.resumeInput === 'string') initialResumeText = snap.resumeInput;
							if (typeof snap.jdInput === 'string') initialJdText = snap.jdInput;
							initialAppliedBanner = "Viewing Example Application (Demo)";
							initialSnapshotLoaded = true;
						}
					}
				}
			} catch {}
		}
	} catch {}

	// Fetch pricing/trial info server-side so first paint uses correct values (no client-only fallback)
	try {
		const res = await fetch(`${getApiBase()}/pricing/average`, {
			headers: cookie ? { Cookie: cookie } : undefined,
			credentials: "include",
			cache: "no-store",
		});
		if (res.ok) {
			const js: any = await res.json().catch(() => null);
			if (js && typeof js === 'object') {
				if (typeof js.trial_usd === 'string' && js.trial_usd) initialTrialUsd = js.trial_usd;
				if (typeof js.free_hint === 'number' && isFinite(js.free_hint)) initialFreeReqHint = js.free_hint;
			}
		}
	} catch {}

	if (debugRequested) {
		try {
			const res = await fetch(`${getApiBase()}/config/frontend`, {
				headers: cookie ? { Cookie: cookie } : undefined,
				credentials: "include",
				cache: "no-store",
			});
			if (res.ok) {
				const js: any = await res.json().catch(() => null);
				homepageDebugLoggedOut = js?.homepage_debug_logged_out === true;
			}
		} catch {}
	}

	if (debugRequested && hasAuth) {
		try {
			const res = await fetch(`${getApiBase()}/users/me`, {
				headers: cookie ? { Cookie: cookie } : undefined,
				credentials: "include",
				cache: "no-store",
			});
			if (res.ok) {
				const me: any = await res.json().catch(() => null);
				showHomepageDebug = String(me?.role || "").toLowerCase() === "admin";
			}
		} catch {}
	}
	if (debugRequested && homepageDebugLoggedOut) {
		showHomepageDebug = true;
	}

	return (
		<div className="min-h-[600px] text-slate-300">
			<ResumeTailorClient
				key={(Array.isArray(sp.appliedKey) ? sp.appliedKey[0] : sp.appliedKey) || "__no_ak__"}
				initialLoggedIn={hasAuth}
				initialAuthVerified={false}
				initialApplied={initialApplied}
				initialJudgeLabel={judgeLabelCookie}
				initialResultType={resultTypeInitial}
				initialStatsMd={initialStatsMdServer}
				initialFitOutput={initialFitOutput}
				initialTailoredOutput={initialTailoredOutput}
				initialJudgeOutput={initialJudgeOutput}
				initialSnapshotLoaded={initialSnapshotLoaded}
				initialResumeText={initialResumeText}
				initialJdText={initialJdText}
				initialAppliedBanner={initialAppliedBanner}
				initialTrialUsd={initialTrialUsd}
				initialFreeReqHint={initialFreeReqHint}
			/>
			{showHomepageDebug ? (
				<HomepageDebugOverlay
					seed={{
						hasAuth,
						initialApplied,
						initialSnapshotLoaded,
						hasInitialResume: typeof initialResumeText === "string" && initialResumeText.length > 0,
						hasInitialJd: typeof initialJdText === "string" && initialJdText.length > 0,
						hasFitOutput: typeof initialFitOutput === "string" && initialFitOutput.length > 0,
						hasTailoredOutput: typeof initialTailoredOutput === "string" && initialTailoredOutput.length > 0,
						hasJudgeOutput: typeof initialJudgeOutput === "string" && initialJudgeOutput.length > 0,
						resultTypeInitial: String(resultTypeInitial || "fit"),
						hasAppliedKey: Boolean(Array.isArray(sp.appliedKey) ? sp.appliedKey[0] : sp.appliedKey),
						hasCurrentSnapshotLookup: currentSnapshotLookupAttempted,
						debugLoggedOutEnabled: homepageDebugLoggedOut,
						initialTrialUsd,
						initialFreeReqHint,
					}}
				/>
			) : null}
		</div>
	);
}
