import React, { useEffect, useMemo, useState } from "react";

export interface BatchStatusBannerProps {
  phase: "fit" | "tailor" | "judge";
  jobs: { alias: string; status: "queued" | "running" | "succeeded" | "failed" | "cancelled"; startedAt?: number; endedAt?: number; failCode?: string | null }[];
  active: boolean;
  onCancel?: () => void;
  totals?: { totalSeconds: number };
}

// Format milliseconds duration to mm:ss
function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "00:00";
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60).toString().padStart(2, "0");
  const s = (totalSec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

const statusLabel: Record<BatchStatusBannerProps["jobs"][number]["status"], string> = {
  queued: "queued▶",
  running: "running⏳",
  succeeded: "succeeded✅",
  failed: "failed❌",
  cancelled: "cancelled⨯",
};

const PhaseMap: Record<BatchStatusBannerProps["phase"], string> = {
  fit: "Fit",
  tailor: "Tailor",
  judge: "Judge",
};

const BatchStatusBanner: React.FC<BatchStatusBannerProps> = ({ phase, jobs, active, onCancel, totals }) => {
  // Trigger re-render every second while any job running
  const anyRunning = useMemo(() => jobs.some(j => j.status === "running"), [jobs]);
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    // Always register a cleanup so an existing interval is cleared when anyRunning flips false.
    let id: ReturnType<typeof setInterval> | undefined;
    if (anyRunning) {
      id = setInterval(() => { setNow(Date.now()); }, 1000);
    } else {
      // Capture a final timestamp when jobs just transitioned to all terminal states
      setNow(Date.now());
    }
    return () => { if (id) clearInterval(id); };
  }, [anyRunning]);

  const show = active || jobs.some(j => j.status !== "succeeded");
  if (!show) return null;

  const header = jobs.some(j => j.status === "queued" || j.status === "running") ? `${PhaseMap[phase]} in progress` : `${PhaseMap[phase]} results`;

  return (
    <div className="rounded-2xl shadow bg-white/70 dark:bg-neutral-800/70 backdrop-blur border border-neutral-200 dark:border-neutral-700 p-4 flex flex-col gap-2 text-sm">
      <div className="font-medium text-neutral-800 dark:text-neutral-100">{header}</div>
      <div className="flex flex-col gap-1">
        {jobs.map(j => {
          const st = j.status;
          const started = j.startedAt || 0;
          const end = (st === "running") ? now : (j.endedAt || now);
          const dur = started ? formatDuration(end - started) : "--:--";
          return (
            <div key={j.alias} className="flex items-center justify-between">
              <div className="flex-1 truncate">
                <span className="text-neutral-700 dark:text-neutral-200">• {j.alias}</span>
                <span className="ml-2 text-neutral-500 dark:text-neutral-400">— {statusLabel[st]}{st === "failed" && j.failCode ? `(${j.failCode})` : ""}</span>
              </div>
              <div className="font-mono tabular-nums text-neutral-600 dark:text-neutral-300 ml-2">{dur}</div>
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between pt-1">
        {jobs.some(j => j.status === "queued" || j.status === "running") ? (
          <button
            type="button"
            onClick={() => { try { onCancel?.(); } catch {} }}
            className="text-xs px-3 py-1 rounded border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition"
          >
            Cancel all
          </button>
        ) : <div />}
        {totals && Number.isFinite(totals.totalSeconds) && (
          <div className="text-xs text-neutral-500 dark:text-neutral-400">Total: {totals.totalSeconds.toFixed(0)}s</div>
        )}
      </div>
    </div>
  );
};

export default BatchStatusBanner;
