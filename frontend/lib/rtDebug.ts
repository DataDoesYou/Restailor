// Lightweight runtime-gated debug logger for Resume Tailor flows
// Gating: URL ?rtDebug=1 or ?debug=true.

export function isRtDebug(): boolean {
  try {
    if (typeof window === 'undefined') return false;
    const sp = new URLSearchParams(window.location.search);
    if (sp.get('rtDebug') === '1') return true;
    if (sp.get('debug') === 'true' || sp.get('debug') === '1') return true;
    // Disabled: localStorage check (too persistent, prefer explicit URL flag)
    // try { if (localStorage.getItem('rtDebug') === '1') return true; } catch {}
    // @ts-ignore
    // Disabled: window.__rtDebug check (prefer explicit URL flag)
    // if ((window as any).__rtDebug) return true;
    // Server-provided config flag (injected in layout when enabled)
    // Disabled: prefer explicit URL flag only in production
    // try { if ((window as any).__rtConfig?.rt_debug_ui) return true; } catch {}
  } catch {}
  // Disabled: Build-time env toggle (too persistent, prefer explicit URL flag)
  // try { if (String(process.env.NEXT_PUBLIC_RT_DEBUG_UI || '').trim() === '1') return true; } catch {}
  return false;
}

export type RtDebugEvent = { name: string; ts: number; data?: any };

export function log(name: string, data?: any) {
  if (!isRtDebug()) return;
  try {
    const evt: RtDebugEvent = { name, ts: performance.now?.() || Date.now(), data };
    // store in a ring buffer on window for HUD access
    const w: any = window as any;
    if (!w.__rtDebugEvents) w.__rtDebugEvents = [] as RtDebugEvent[];
    const arr: RtDebugEvent[] = w.__rtDebugEvents;
    arr.push(evt);
    if (arr.length > 200) arr.splice(0, arr.length - 200);
    // console output for quick capture
    // eslint-disable-next-line no-console
    console.debug('[rt-debug]', evt.name, evt.data || {});
    // notify HUD listeners
    try { window.dispatchEvent(new CustomEvent('rt-debug', { detail: evt })); } catch {}
  } catch {}
}

export function setNavId(navId: string) {
  try { if (typeof window !== 'undefined') sessionStorage.setItem('rt_nav_id', navId); } catch {}
}
export function getNavId(): string | null {
  try { if (typeof window !== 'undefined') return sessionStorage.getItem('rt_nav_id'); } catch {}
  return null;
}

export function genNavId(): string {
  try { return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`; } catch { return String(Date.now()); }
}

export function hudEnabled(): boolean { return isRtDebug(); }
