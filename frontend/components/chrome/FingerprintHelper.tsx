"use client";
import { useEffect } from "react";

export default function FingerprintHelper() {
  useEffect(() => {
    const enabled = (process.env.NEXT_PUBLIC_RT_ENABLE_FINGERPRINT || "").trim() === "1";
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      try {
        // Load open-source FingerprintJS from CDN, same approach as Streamlit helper
        // eslint-disable-next-line no-eval
        const mod: any = await (eval("import")('https://openfpcdn.io/fingerprintjs/v4'));
        const fp = await mod.load();
        const result = await fp.get();
        const vid = result?.visitorId || null;
        if (!cancelled && vid) {
          // Best-effort: attach to window for parity; backend may read it from signup payloads
          (window as any).visitorId = vid;
        }
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, []);
  return null;
}
