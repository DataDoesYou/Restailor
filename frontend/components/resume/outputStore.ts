import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type ResultType = "fit" | "tailor" | "judge" | "";

function now(): number { return Date.now(); }

// All output persistence is now handled via database snapshots and current_snapshot_key.
// SSR loads snapshots on page load. No localStorage needed - it only caused conflicts.
export function useSharedOutputs(initial?: { resultType?: ResultType; fitOutput?: string; tailoredOutput?: string; judgeOutput?: string }) {
  const [resultType, setResultType] = useState<ResultType>(() => {
    // Use SSR-provided initial or deterministic default
    if (initial?.resultType && ["fit","tailor","judge",""].includes(initial.resultType)) return initial.resultType as ResultType;
    return "fit";
  });
  const [fitOutput, setFitOutput] = useState<string>(initial?.fitOutput || "");
  const [tailoredOutput, setTailoredOutput] = useState<string>(initial?.tailoredOutput || "");
  const [judgeOutput, setJudgeOutput] = useState<string>(initial?.judgeOutput || "");

  const fitTs = useRef<number>(0);
  const tailorTs = useRef<number>(0);
  const judgeTs = useRef<number>(0);
  const rtypeTs = useRef<number>(0);

  // Cross-page sync listener (for multi-tab coordination)
  useEffect(() => {
    const onOutputs = (e: Event) => {
      try {
        const d: any = (e as CustomEvent).detail || {};
        if (typeof d.fitTs === "number" && typeof d.fitOutput === "string") {
          if (d.fitTs > (fitTs.current || 0)) { fitTs.current = d.fitTs; setFitOutput(d.fitOutput); }
        }
        if (typeof d.tailorTs === "number" && typeof d.tailoredOutput === "string") {
          if (d.tailorTs > (tailorTs.current || 0)) { tailorTs.current = d.tailorTs; setTailoredOutput(d.tailoredOutput); }
        }
        if (typeof d.judgeTs === "number" && typeof d.judgeOutput === "string") {
          if (d.judgeTs > (judgeTs.current || 0)) { judgeTs.current = d.judgeTs; setJudgeOutput(d.judgeOutput); }
        }
        if (typeof d.rtypeTs === "number" && typeof d.resultType === "string") {
          if (d.rtypeTs > (rtypeTs.current || 0)) { rtypeTs.current = d.rtypeTs; setResultType(d.resultType); }
        }
      } catch {}
    };
    window.addEventListener("rt-outputs", onOutputs as EventListener);
    return () => window.removeEventListener("rt-outputs", onOutputs as EventListener);
  }, []);

  const broadcast = useCallback((payload: any) => {
    try { window.dispatchEvent(new CustomEvent("rt-outputs", { detail: payload })); } catch {}
  }, []);

  const updateFit = useCallback((val: string) => {
    setFitOutput(val);
    const ts = now(); fitTs.current = ts;
    broadcast({ fitOutput: val, fitTs: ts });
  }, [broadcast]);

  const updateTailored = useCallback((val: string) => {
    setTailoredOutput(val);
    const ts = now(); tailorTs.current = ts;
    broadcast({ tailoredOutput: val, tailorTs: ts });
  }, [broadcast]);

  const updateJudge = useCallback((val: string) => {
    setJudgeOutput(val);
    const ts = now(); judgeTs.current = ts;
    broadcast({ judgeOutput: val, judgeTs: ts });
  }, [broadcast]);

  const updateResultType = useCallback((val: ResultType) => {
    setResultType(val);
    const ts = now(); rtypeTs.current = ts;
    broadcast({ resultType: val, rtypeTs: ts });
  }, [broadcast]);

  const clearOutputs = useCallback((opts?: { preserveResultType?: boolean }) => {
    const keepRT = opts?.preserveResultType === true;
    setFitOutput(""); setTailoredOutput(""); setJudgeOutput("");
    if (!keepRT) {
      // Keep a valid tab selected instead of clearing to empty (prevents radio unselection on navigation)
      setResultType(r => (r && ["fit","tailor","judge"].includes(r)) ? r as ResultType : "fit");
    }
    fitTs.current = 0; tailorTs.current = 0; judgeTs.current = 0; if (!keepRT) rtypeTs.current = now();
    broadcast({ fitOutput: "", tailoredOutput: "", judgeOutput: "", resultType: (keepRT ? resultType : (resultType || "fit")), fitTs: 0, tailorTs: 0, judgeTs: 0, rtypeTs: rtypeTs.current });
  }, [broadcast, resultType]);

  // Narrow clear used when starting a Fit run: only clear Fit content and timestamp
  const clearFitOnly = useCallback(() => {
    setFitOutput("");
    fitTs.current = 0;
    broadcast({ fitOutput: "", fitTs: 0 });
  }, [broadcast]);

  // Mirror resultType to cookie for SSR / fast back navigation before hydration
  useEffect(() => {
    try {
      if (!resultType) return;
      const secure = (typeof location !== 'undefined' && location.protocol === 'https:') ? '; Secure' : '';
      document.cookie = `rt_result_type=${encodeURIComponent(resultType)}; Path=/; SameSite=Lax${secure}; Max-Age=900`;
    } catch {}
  }, [resultType]);

  // Clear on logout to mirror previous behavior
  useEffect(() => {
    const onAuth = (e: Event) => {
      const d: any = (e as CustomEvent).detail || {};
      if (String(d?.state || "").toLowerCase() === "logged-out") {
        const reason = String(d?.reason || '').toLowerCase();
        // For auto / 401 (session expiry or forced) perform full privacy clear (including resultType)
        if (reason === '401' || reason === 'auto') {
          clearOutputs({ preserveResultType: false });
        } else {
          // Manual logout: clear content but keep the user's selected tab preference
          clearOutputs({ preserveResultType: true });
        }
      }
    };
    window.addEventListener("rt-auth", onAuth as EventListener);
    return () => window.removeEventListener("rt-auth", onAuth as EventListener);
  }, [clearOutputs]);

  return useMemo(() => ({
    resultType, setResultType: updateResultType,
    fitOutput, setFitOutput: updateFit,
    tailoredOutput, setTailoredOutput: updateTailored,
    judgeOutput, setJudgeOutput: updateJudge,
    clearOutputs,
    clearFitOnly,
  }), [resultType, updateResultType, fitOutput, updateFit, tailoredOutput, updateTailored, judgeOutput, updateJudge, clearOutputs]);
}

export default useSharedOutputs;
