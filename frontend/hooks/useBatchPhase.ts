/**
 * Parallel fan-out for multi-model phases. Single-model flows stay unchanged.
 */
import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { getApiBaseUrl } from "../lib/api"; // existing helper for consistent base URL
// Canonical model ordering (sidebar listing order). We normalize batch execution to this order
// so timers / aggregated results are deterministic, while the sidebar itself still reflects
// user click sequence for selection UX.
import { DISPLAY_OPTIONS } from "@/components/resume/models";

export type BatchJob = {
  alias: string;
  jobId: string; // assigned after submit
  es: EventSource | null;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  resultText?: string;
  failCode?: string | null;
  startedAt: number; // ms epoch
  endedAt?: number; // ms epoch
};

export type BatchState = {
  phase: "fit" | "tailor" | "judge";
  jobs: BatchJob[];
  cancelled: boolean;
};

export interface UseBatchPhaseApi {
  startBatch: (
    phase: "fit" | "tailor" | "judge",
    aliases: string[],
    submitFn: (alias: string) => Promise<{ jobId: string }>
  ) => Promise<void>;
  cancelBatch: () => Promise<void>;
  active: boolean; // any queued|running jobs
  jobs: BatchJob[];
  batchMarkdown: string;
  totals: { perJobSeconds: Record<string, number>; totalSeconds: number };
}

// Helper to build markdown line for a job (including partial streaming results)
function jobMarkdown(j: BatchJob): string {
  if (j.status === "succeeded") return `### ${j.alias}\n${j.resultText || ""}\n`;
  if (j.status === "failed") return `### ${j.alias}\n*Failed: ${j.failCode || "ERROR"}*\n`;
  if (j.status === "cancelled") return `### ${j.alias}\n*Cancelled*\n`;
  // Running jobs with partial text: show incremental streaming results
  if (j.status === "running" && j.resultText) return `### ${j.alias}\n${j.resultText}\n`;
  // Non-terminal without partial text: keep header so ordering is stable but leave blank body
  return `### ${j.alias}\n`;
}

export function useBatchPhase(): UseBatchPhaseApi {
  const [phase, setPhase] = useState<"fit" | "tailor" | "judge">("fit");
  const [jobs, setJobs] = useState<BatchJob[]>([]);
  const cancelledRef = useRef(false);
  const submittingRef = useRef(false);
  // Preserve initial alias order for deterministic markdown output
  const orderRef = useRef<string[]>([]);

  // Track for cleanup on unmount/reset
  const esRefs = useRef<Record<string, EventSource | null>>({});

  const reset = useCallback(() => {
    try {
      Object.values(esRefs.current).forEach(es => { try { es?.close(); } catch {} });
    } catch {}
    esRefs.current = {};
    cancelledRef.current = false;
    setJobs([]);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      try { Object.values(esRefs.current).forEach(es => { try { es?.close(); } catch {} }); } catch {}
    };
  }, []);

  const finalizeJob = useCallback((alias: string, data: Partial<Pick<BatchJob, "status" | "resultText" | "failCode" | "endedAt">>) => {
    setJobs(prev => prev.map(j => j.alias === alias ? { ...j, ...data } : j));
  }, []);

  const startBatch = useCallback<UseBatchPhaseApi["startBatch"]>(async (ph, aliases, submitFn) => {
    if (!Array.isArray(aliases) || aliases.length === 0) return;
    // Reset any previous batch completely
    reset();
    setPhase(ph);
    // Normalize to canonical sidebar order (DISPLAY_OPTIONS order) for execution & display.
    // This makes output order independent of the order in which checkboxes were clicked.
    const canonical = DISPLAY_OPTIONS.map(o => o.alias);
    const canonIndex = (a: string) => {
      const i = canonical.indexOf(a);
      return i === -1 ? 9999 : i;
    };
    const ordered = [...aliases].sort((a,b) => canonIndex(a) - canonIndex(b));
    orderRef.current = ordered.slice();
    submittingRef.current = true;
    const seeded: BatchJob[] = ordered.map(a => ({
      alias: a,
      jobId: "", // unknown yet
      es: null,
      status: "queued",
      startedAt: 0,
    }));
    setJobs(seeded);

    const base = getApiBaseUrl();

    // Submit in order but run all in parallel (fan-out)
  const submitPromises = ordered.map(async (alias) => {
      let jobId = "";
      try {
        const { jobId: jid } = await submitFn(alias);
        jobId = jid;
      } catch (e) {
        // Mark failed immediately (submission failure)
        finalizeJob(alias, { status: "failed", failCode: "SUBMIT_ERROR", endedAt: Date.now() });
        return;
      }

      // Mark running & record start
      setJobs(prev => prev.map(j => j.alias === alias ? { ...j, jobId, status: "running", startedAt: Date.now() } : j));

      const streamUrl = `${base}/jobs/${jobId}/stream`;
      let accumulated = "";
      let terminal = false;
      const es = new EventSource(streamUrl, { withCredentials: true });
      esRefs.current[alias] = es;

      const closeEs = () => { try { es.close(); } catch {}; esRefs.current[alias] = null; };

      const safeFinalize = (status: BatchJob["status"], extra: Partial<BatchJob>) => {
        if (terminal) return; terminal = true; closeEs();
        finalizeJob(alias, { status, endedAt: Date.now(), ...extra });
      };

      es.onmessage = (ev) => {
        if (!ev?.data) return;
        let data: any = null;
        try { data = JSON.parse(ev.data); } catch { return; }
        const st = data?.status;
        if (st === "completed" || st === "succeeded") {
          if (typeof data?.text === "string") accumulated = data.text; // final full text
          safeFinalize("succeeded", { resultText: accumulated || data?.text || "" });
          return;
        }
        if (st === "cancelled" || st === "canceled") {
          safeFinalize("cancelled", { failCode: "CANCELLED" });
          return;
        }
        if (st === "failed" || st === "error") {
          safeFinalize("failed", { failCode: data?.fail_code || data?.code || "ERROR" });
          return;
        }
        // Handle partial/incremental streaming updates (processing status with partial field)
        if (st === "processing" && typeof data?.partial === "string") {
          accumulated = data.partial;
          // Update job with partial text without finalizing
          setJobs(prev => prev.map(j => j.alias === alias ? { ...j, resultText: accumulated } : j));
          return;
        }
        // Streaming chunk variants: prefer append delta or text fragment
        if (typeof data?.delta === "string") accumulated += data.delta;
        else if (typeof data?.text === "string" && !data?.append_full) accumulated = data.text; // fallback overwrite pattern
      };

      es.onerror = () => {
        if (terminal) return; // already done
        // One-shot fallback: fetch result endpoint
        (async () => {
          try {
            const r = await fetch(`${base}/jobs/${jobId}/result`, { credentials: "include" });
            if (r.ok) {
              const jr: any = await r.json().catch(() => ({}));
              const text = jr?.text || jr?.result_text || jr?.result || "";
              if (text) {
                accumulated = text;
                safeFinalize("succeeded", { resultText: accumulated });
                return;
              }
            }
            safeFinalize("failed", { failCode: "NO_RESULT" });
          } catch {
            safeFinalize("failed", { failCode: "NO_RESULT" });
          }
        })();
      };
    });

    await Promise.all(submitPromises);
    submittingRef.current = false;
  }, [reset, finalizeJob]);

  const cancelBatch = useCallback<UseBatchPhaseApi["cancelBatch"]>(async () => {
    cancelledRef.current = true;
    const base = getApiBaseUrl();
    const now = Date.now();
    const targets = jobs.filter(j => j.status === "queued" || j.status === "running");
    await Promise.all(targets.map(async (j) => {
      try {
        if (j.jobId) {
          await fetch(`${base}/jobs/${j.jobId}/cancel`, { method: "POST", credentials: "include" }).catch(() => {});
        }
      } catch {}
      try { j.es?.close(); } catch {}
    }));
  // Close and null any lingering EventSources (including ones that already terminaled during cancellation loop)
  try { Object.entries(esRefs.current).forEach(([k, es]) => { try { es?.close(); } catch {}; esRefs.current[k] = null; }); } catch {}
  setJobs(prev => prev.map(j => (j.status === "queued" || j.status === "running") ? { ...j, status: "cancelled", endedAt: now, es: null } : j));
  // Fully clear ref map to avoid leaks
  esRefs.current = {};
  }, [jobs]);

  const active = useMemo(() => jobs.some(j => j.status === "queued" || j.status === "running"), [jobs]);

  const batchMarkdown = useMemo(() => {
    if (!jobs.length) return "";
    // Don't show structure until at least one job has started streaming (has resultText or is terminal)
    const hasAnyContent = jobs.some(j => 
      j.resultText || 
      j.status === "succeeded" || 
      j.status === "failed" || 
      j.status === "cancelled"
    );
    if (!hasAnyContent) return ""; // Show nothing until first stream arrives
    // Sort by original order captured at batch start
    const orderIdx = (a: string) => {
      const i = orderRef.current.indexOf(a);
      return i === -1 ? 9999 : i;
    };
    const sorted = [...jobs].sort((a,b) => orderIdx(a.alias) - orderIdx(b.alias));
    return sorted.map(j => jobMarkdown(j)).join("\n");
  }, [jobs]);

  const totals = useMemo(() => {
    const perJobSeconds: Record<string, number> = {};
    let totalSeconds = 0;
    const now = Date.now();
    for (const j of jobs) {
      if (j.status === "succeeded" || j.status === "failed" || j.status === "cancelled") {
        if (j.startedAt) {
          const end = j.endedAt ?? now;
            const sec = (end - j.startedAt) / 1000;
          perJobSeconds[j.alias] = sec;
          totalSeconds += sec;
        }
      }
    }
    return { perJobSeconds, totalSeconds };
  }, [jobs]);

  return { startBatch, cancelBatch, active, jobs, batchMarkdown, totals };
}

export default useBatchPhase;
