import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";

type Inputs = { resumeText: string; jdText: string };

async function fetchServerInputs(): Promise<Inputs | null> {
  try {
    const d = await api.get<{ resume_text?: string; jd_text?: string }>("/users/me/inputs");
    return { resumeText: String(d?.resume_text || ""), jdText: String(d?.jd_text || "") };
  } catch {
    return null;
  }
}

async function saveServerInputs(resumeText: string, jdText: string): Promise<void> {
  try {
    await api.put("/users/me/inputs", { resume_text: resumeText, jd_text: jdText });
  } catch {}
}

export function useSharedInputs(opts?: { skipInitialFetch?: boolean; initialResume?: string; initialJd?: string; skipLocalStorage?: boolean }) {
  const [resumeText, setResumeText] = useState<string>(() => opts?.initialResume || "");
  const [jdText, setJdText] = useState<string>(() => opts?.initialJd || "");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initialize from server (database is single source of truth)
  useEffect(() => {
    if (opts?.skipInitialFetch) return; // SSR already loaded snapshot
    let active = true;
    
    (async () => {
      const serverData = await fetchServerInputs();
      if (!active) return;
      
      if (serverData && (serverData.resumeText || serverData.jdText)) {
        if (serverData.resumeText) setResumeText(serverData.resumeText);
        if (serverData.jdText) setJdText(serverData.jdText);
      } else {
        setResumeText("");
        setJdText("");
      }
    })();
    
    return () => { active = false; };
  }, []);

  // Debounced server save
  const scheduleSave = useCallback((r: string, j: string) => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { saveServerInputs(r, j); }, 2000);
  }, []);

  const updateResume = useCallback((val: string) => {
    setResumeText(val);
    scheduleSave(val, jdText);
  }, [jdText, scheduleSave]);

  const updateJd = useCallback((val: string) => {
    setJdText(val);
    scheduleSave(resumeText, val);
  }, [resumeText, scheduleSave]);

  // On logout: clear state
  useEffect(() => {
    const onAuth = (e: Event) => {
      const det: any = (e as CustomEvent).detail || {};
      if (String(det?.state || "").toLowerCase() === "logged-out") {
        setResumeText("");
        setJdText("");
        return;
      }
      // On login: fetch from server
      fetchServerInputs().then((d) => {
        if (!d) return;
        if (d.resumeText.trim()) setResumeText(d.resumeText);
        if (d.jdText.trim()) setJdText(d.jdText);
      });
    };
    window.addEventListener("rt-auth", onAuth as EventListener);
    return () => window.removeEventListener("rt-auth", onAuth as EventListener);
  }, []);

  return useMemo(() => ({ 
    resumeText, 
    setResumeText: updateResume, 
    jdText, 
    setJdText: updateJd 
  }), [resumeText, updateResume, jdText, updateJd]);
}

export default useSharedInputs;
