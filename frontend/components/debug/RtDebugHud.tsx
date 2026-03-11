"use client";
import { useEffect, useState } from 'react';
import { hudEnabled, RtDebugEvent } from '@/lib/rtDebug';

export default function RtDebugHud() {
  const [events, setEvents] = useState<RtDebugEvent[]>([]);
  const [visible, setVisible] = useState<boolean>(false);
  useEffect(() => {
    if (!hudEnabled()) return;
    const w: any = window as any;
    try { setEvents([...(w.__rtDebugEvents || [])]); } catch {}
    const onEvt = (e: Event) => {
      try { const ev = (e as CustomEvent).detail as RtDebugEvent; setEvents(prev => [...prev.slice(-49), ev]); } catch {}
    };
    const onKey = (e: KeyboardEvent) => {
      // Accept both key and code checks for reliability across layouts
      const isBacktick = e.key === '`' || e.code === 'Backquote';
      // Allow Ctrl+` or Shift+` (or both). Keep Meta for Mac.
      const hasMod = e.ctrlKey || e.metaKey || e.shiftKey;
      if (isBacktick && hasMod) {
        e.preventDefault();
        setVisible(v => !v);
      }
    };
    window.addEventListener('rt-debug', onEvt as EventListener);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('rt-debug', onEvt as EventListener); window.removeEventListener('keydown', onKey); };
  }, []);
  if (!hudEnabled() || !visible) return null;
  return (
    <div style={{ position: 'fixed', top: 8, right: 8, zIndex: 99999, width: 420, minWidth: 320, height: 260, minHeight: 160, overflow: 'auto', resize: 'both', fontFamily: 'monospace', fontSize: 11, background: 'rgba(15,23,42,0.92)', color: '#a3e635', border: '1px solid #334155', borderRadius: 6, padding: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <strong>RT Debug (toggle Ctrl/Shift + `)</strong>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => {
              try {
                const w: any = window as any;
                if (w.__rtDebugEvents) w.__rtDebugEvents.length = 0;
              } catch {}
              setEvents([]);
            }}
            title="Clear events"
            style={{ background: 'transparent', color: '#94a3b8' }}
          >clear</button>
          <button onClick={() => setVisible(false)} style={{ background: 'transparent', color: '#94a3b8' }}>hide</button>
        </div>
      </div>
      {events.slice(-200).map((e, i) => (
        <div key={i} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          <span style={{ color: '#38bdf8' }}>{e.ts.toFixed(1)}</span> <span style={{ color: '#fbbf24' }}>{e.name}</span> {e.data ? JSON.stringify(e.data) : ''}
        </div>
      ))}
    </div>
  );
}
