import { headers, cookies as nextCookies } from "next/headers";
import "server-only";

import ResumeTailorClient from "@/components/pages/ResumeTailorClient";

function getApiBase(): string {
	const base = process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "";
	if (!base) throw new Error("API base not set");
	return base.replace(/\/$/, "");
}

export default async function ResumePage({ searchParams }: { searchParams?: Promise<Record<string,string|string[]|undefined>> }) {
	// Client-side auth guard (more reliable cross-platform than SSR session check)
	const sp = searchParams ? await searchParams : undefined;
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

	// Load snapshot: first try ?appliedKey=, then fall back to current_snapshot_key from database
	try {
		const ak = sp && (Array.isArray(sp.appliedKey) ? sp.appliedKey[0] : sp.appliedKey);
		const forceAppliedParam = sp && (Array.isArray(sp.forceApplied) ? sp.forceApplied[0] : sp.forceApplied);
		
		let snapshotKeyToLoad: string | undefined = ak;
		
		// If no appliedKey in URL, check if user has a current_snapshot_key in database
		if (!snapshotKeyToLoad && hasAuth) {
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
		}
	} catch {}
	// STEAM: No fallback cookie reads - database only (removed rt_open_force_applied, rt_open_applied_key, rt_applied_overrides logic)
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
		// While the client bundle loads, render a lightweight skeleton that roughly
		// preserves layout space. This avoids a large CLS shift and makes the page
		// feel responsive while deferring all dynamic logic to the client only.
		return (
			<div className="min-h-[600px] text-slate-300">
				<ResumeTailorClient
					key={sp && (Array.isArray(sp.appliedKey) ? sp.appliedKey[0] : sp.appliedKey) || 'default'}
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
			</div>
		);
}
