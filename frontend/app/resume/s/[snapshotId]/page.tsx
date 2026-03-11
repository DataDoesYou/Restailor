import ResumeTailorClient from "@/components/pages/ResumeTailorClient";
import { headers, cookies as nextCookies } from "next/headers";

function getApiBase(): string {
  const base = process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "";
  if (!base) throw new Error("API base not set");
  return base.replace(/\/$/, "");
}

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function ResumeBySnapshotPage({ params, searchParams }: { params: Promise<{ snapshotId: string }>, searchParams?: Promise<Record<string,string|string[]|undefined>> }) {
  const { snapshotId } = await params;
  const sp = searchParams ? await searchParams : undefined;
  const h = await headers();
  const cookie = h.get("cookie") || "";
  // STEAM: No state cookies - database only

  let initialApplied = false;
  let initialFitOutput: string | undefined = undefined;
  let initialTailoredOutput: string | undefined = undefined;
  let initialJudgeOutput: string | undefined = undefined;
  let initialStatsMd: string | undefined = undefined;
  let initialResumeText: string | undefined = undefined;
  let initialJdText: string | undefined = undefined;
  let initialSnapshotLoaded = false;
  let initialAppliedBanner: string | undefined = undefined;

  try {
    const res = await fetch(`${getApiBase()}/applications/by-id?snapshotId=${encodeURIComponent(snapshotId)}`, {
      headers: cookie ? { Cookie: cookie } : undefined,
      credentials: "include",
      cache: "no-store",
    });
    if (res.ok) {
      const js: any = await res.json().catch(() => null);
      if (js?.found && js?.row) {
  // Only set initialApplied from database - client hydration will handle forceApplied from URL
  initialApplied = !!js.row.isApplied;
        // STEAM: No cookie writes - database only
        const snap = js.row.snapshot || {};
        if (snap && typeof snap === 'object') {
          if (typeof snap.fitOutput === 'string') initialFitOutput = snap.fitOutput;
          if (typeof snap.tailoredOutput === 'string') initialTailoredOutput = snap.tailoredOutput;
          if (typeof snap.judgeOutput === 'string') initialJudgeOutput = snap.judgeOutput;
          if (typeof snap.statsMd === 'string') initialStatsMd = snap.statsMd;
          if (typeof snap.resumeInput === 'string') initialResumeText = snap.resumeInput;
          if (typeof snap.jdInput === 'string') initialJdText = snap.jdInput;
          if (initialFitOutput || initialTailoredOutput || initialJudgeOutput) initialSnapshotLoaded = true;
          if (initialApplied) initialAppliedBanner = "Applied snapshot opened – editing either box will create a new draft";
        }
      }
    }
  } catch {}

  // STEAM: No cookie fallback - database only (removed rt_open_force_applied, rt_open_applied_key, rt_applied_overrides)

  return (
    <div className="min-h-[600px] text-slate-300">
      <ResumeTailorClient
        key={snapshotId}
        initialLoggedIn={/(?:^|; )rt_session=|(?:^|; )rt_access=|(?:^|; )rt_access_ephem=/.test(cookie)}
        initialAuthVerified={true}
        initialApplied={initialApplied}
        initialAppliedBanner={initialAppliedBanner}
        initialFitOutput={initialFitOutput}
        initialTailoredOutput={initialTailoredOutput}
        initialJudgeOutput={initialJudgeOutput}
        initialStatsMd={initialStatsMd}
        initialSnapshotLoaded={initialSnapshotLoaded}
        initialResumeText={initialResumeText}
        initialJdText={initialJdText}
        __seedDebug={{ cookies: cookie, used: { forceAppliedParam: (sp && (Array.isArray(sp.forceApplied) ? sp.forceApplied[0] : sp.forceApplied)) === '1' } }}
      />
    </div>
  );
}
