// EXAMPLE: How to use BroadcastChannel instead of localStorage for cross-tab sync
// This is a simplified example showing the concept

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";

type Inputs = { resumeText: string; jdText: string };

function now(): number { return Date.now(); }

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

export function useSharedInputsBroadcast(opts?: { 
  skipInitialFetch?: boolean; 
  initialResume?: string; 
  initialJd?: string; 
}) {
  const [resumeText, setResumeText] = useState<string>(() => opts?.initialResume || "");
  const [jdText, setJdText] = useState<string>(() => opts?.initialJd || "");
  const rTs = useRef<number>(0);
  const jTs = useRef<number>(0);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  // Create BroadcastChannel once on mount
  const channelRef = useRef<BroadcastChannel | null>(null);

  // Initialize from server first (privacy-first: database is source of truth)
  useEffect(() => {
    if (opts?.skipInitialFetch) return;
    let active = true;
    
    (async () => {
      const serverData = await fetchServerInputs();
      if (!active) return;
      
      if (serverData && (serverData.resumeText || serverData.jdText)) {
        const ts = now();
        if (serverData.resumeText) {
          setResumeText(serverData.resumeText);
          rTs.current = ts;
        }
        if (serverData.jdText) {
          setJdText(serverData.jdText);
          jTs.current = ts;
        }
      } else {
        setResumeText("");
        setJdText("");
        rTs.current = 0;
        jTs.current = 0;
      }
    })();
    
    return () => { active = false; };
  }, []);

  // Setup BroadcastChannel for cross-tab sync
  useEffect(() => {
    // BroadcastChannel is like a "radio frequency" - all tabs tuned to 'rt-inputs' can communicate
    const channel = new BroadcastChannel('rt-inputs');
    channelRef.current = channel;

    // Listen for messages from other tabs
    channel.onmessage = (event) => {
      try {
        const d = event.data || {};
        
        // Resume text update from another tab
        if (typeof d.rTs === "number" && typeof d.resumeText === "string") {
          // Special case: rTs=0 means force clear (logout)
          // Otherwise only accept newer timestamps to avoid race conditions
          if (d.rTs === 0 || d.rTs > (rTs.current || 0)) {
            rTs.current = d.rTs;
            setResumeText(d.resumeText);
          }
        }
        
        // JD text update from another tab
        if (typeof d.jTs === "number" && typeof d.jdText === "string") {
          if (d.jTs === 0 || d.jTs > (jTs.current || 0)) {
            jTs.current = d.jTs;
            setJdText(d.jdText);
          }
        }
      } catch (err) {
        console.error('[BroadcastChannel] Error handling message:', err);
      }
    };

    // Cleanup: close the channel when component unmounts
    return () => {
      channel.close();
      channelRef.current = null;
    };
  }, []);

  // Debounced server save (same as before)
  const scheduleSave = useCallback((r: string, j: string) => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { 
      saveServerInputs(r, j); 
    }, 2000);
  }, []);

  const updateResume = useCallback((val: string) => {
    setResumeText(val);
    const ts = now(); 
    rTs.current = ts;
    
    // Broadcast to other tabs (replaces window.dispatchEvent + localStorage)
    if (channelRef.current) {
      try {
        channelRef.current.postMessage({ resumeText: val, rTs: ts });
      } catch (err) {
        console.error('[BroadcastChannel] Error posting message:', err);
      }
    }
    
    scheduleSave(val, jdText);
  }, [jdText, scheduleSave]);

  const updateJd = useCallback((val: string) => {
    setJdText(val);
    const ts = now(); 
    jTs.current = ts;
    
    // Broadcast to other tabs
    if (channelRef.current) {
      try {
        channelRef.current.postMessage({ jdText: val, jTs: ts });
      } catch (err) {
        console.error('[BroadcastChannel] Error posting message:', err);
      }
    }
    
    scheduleSave(resumeText, val);
  }, [resumeText, scheduleSave]);

  // Handle login/logout events
  useEffect(() => {
    const onAuth = (e: Event) => {
      const det: any = (e as CustomEvent).detail || {};
      
      if (String(det?.state || "").toLowerCase() === "logged-out") {
        // Clear local state and broadcast to other tabs
        setResumeText(""); 
        setJdText("");
        rTs.current = 0; 
        jTs.current = 0;
        
        if (channelRef.current) {
          try {
            channelRef.current.postMessage({ 
              resumeText: "", 
              jdText: "", 
              rTs: 0, 
              jTs: 0 
            });
          } catch {}
        }
        return;
      }
      
      // On login: hydrate from server if local is empty
      if (!resumeText.trim() || !jdText.trim()) {
        fetchServerInputs().then((d) => {
          if (!d) return;
          const ts = now();
          if (!resumeText.trim() && d.resumeText.trim()) {
            setResumeText(d.resumeText);
            rTs.current = ts;
          }
          if (!jdText.trim() && d.jdText.trim()) {
            setJdText(d.jdText);
            jTs.current = ts;
          }
        });
      }
    };
    
    window.addEventListener("rt-auth", onAuth as EventListener);
    return () => window.removeEventListener("rt-auth", onAuth as EventListener);
  }, [resumeText, jdText]);

  return useMemo(() => ({ 
    resumeText, 
    setResumeText: updateResume, 
    jdText, 
    setJdText: updateJd 
  }), [resumeText, updateResume, jdText, updateJd]);
}

export default useSharedInputsBroadcast;

/*
KEY DIFFERENCES FROM localStorage APPROACH:

1. NO DISK PERSISTENCE
   - BroadcastChannel messages live only in memory
   - When all tabs close, data is gone
   - More private: no forensic traces on disk

2. SIMPLER API
   - channel.postMessage(data)  // send to other tabs
   - channel.onmessage = handler // receive from other tabs
   - No need for localStorage.setItem/getItem

3. MORE EFFICIENT
   - Direct tab-to-tab communication
   - No disk I/O
   - No storage events

4. SAME BROWSER ONLY
   - Only works between tabs in same browser profile
   - localStorage has same limitation

5. AUTOMATIC CLEANUP
   - channel.close() automatically unsubscribes
   - No orphaned localStorage keys

BROWSER SUPPORT:
- Chrome 54+
- Firefox 38+
- Safari 15.4+
- Edge 79+
(Good support in 2025, but can add fallback for older browsers)

HOW IT WORKS:
1. Tab A creates: new BroadcastChannel('rt-inputs')
2. Tab B creates: new BroadcastChannel('rt-inputs')  // same name = same channel
3. Tab A: channel.postMessage({ resumeText: "Hello" })
4. Tab B: receives via channel.onmessage
5. Tab B updates its UI instantly
6. No localStorage, no cookies, no server polling needed!

ANALOGY:
- localStorage = bulletin board (everyone writes notes, everyone reads)
- BroadcastChannel = walkie-talkie (direct voice communication on shared frequency)
*/
