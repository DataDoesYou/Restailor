import { useCallback, useEffect, useMemo, useState } from "react";

/**
 * Pure React state management for resume and JD text inputs.
 * 
 * No auto-save, no localStorage, no database fetch.
 * Data persists only via snapshots when jobs are run.
 * SSR loads initial values from snapshot via current_snapshot_key.
 */
export function useSharedInputs(opts?: { 
  skipInitialFetch?: boolean; 
  initialResume?: string; 
  initialJd?: string; 
  skipLocalStorage?: boolean;
}) {
  const [resumeText, setResumeText] = useState<string>(() => opts?.initialResume || "");
  const [jdText, setJdText] = useState<string>(() => opts?.initialJd || "");

  // On logout: clear state
  useEffect(() => {
    const onAuth = (e: Event) => {
      const det: any = (e as CustomEvent).detail || {};
      if (String(det?.state || "").toLowerCase() === "logged-out") {
        setResumeText("");
        setJdText("");
      }
    };
    window.addEventListener("rt-auth", onAuth as EventListener);
    return () => window.removeEventListener("rt-auth", onAuth as EventListener);
  }, []);

  return useMemo(() => ({ 
    resumeText, 
    setResumeText, 
    jdText, 
    setJdText 
  }), [resumeText, jdText]);
}

export default useSharedInputs;
