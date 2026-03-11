"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { logger } from "@/lib/logger";

type Props = {
  siteKey: string;
  className?: string;
  onState?: (state: "idle" | "success" | "error") => void;
};

declare global {
  interface Window {
    turnstile?: {
      render: (container: string | HTMLElement, options: any) => string;
      reset: (widgetId: string) => void;
      remove: (widgetId: string) => void;
    };
    __rt_ts_cb?: () => void;
  }
}

// Track global script state
let scriptStatus: 'idle' | 'loading' | 'loaded' | 'error' = 'idle';
const scriptListeners: (() => void)[] = [];

function loadTurnstileScript() {
  if (scriptStatus === 'loaded' || scriptStatus === 'loading') return;

  // Check if already loaded by external means
  if (typeof window !== 'undefined' && window.turnstile) {
    scriptStatus = 'loaded';
    return;
  }

  scriptStatus = 'loading';
  
  window.__rt_ts_cb = () => {
    scriptStatus = 'loaded';
    scriptListeners.forEach(l => l());
    scriptListeners.length = 0;
  };

  const script = document.createElement("script");
  // Use explicit render mode to prevent auto-rendering race conditions
  script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=__rt_ts_cb&render=explicit";
  script.async = true;
  script.defer = true;
  script.onerror = () => {
    scriptStatus = 'error';
    logger.error("[TurnstileWidget] Failed to load script");
  };
  document.body.appendChild(script);
}

// Client-only Cloudflare Turnstile widget. It injects the script and posts the token to the backend.
export default function TurnstileWidget({ siteKey, className = "", onState }: Props) {
  const xClient = useMemo(() => {
    try {
      // Lazy import to avoid bundling cycles
      const mod = require("@/lib/client");
      return typeof mod.getClientId === "function" ? mod.getClientId() : "";
    } catch {
      return "";
    }
  }, []);

  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [isScriptLoaded, setIsScriptLoaded] = useState(scriptStatus === 'loaded');

  useEffect(() => {
    if (scriptStatus === 'idle') {
      loadTurnstileScript();
    }
    
    if (scriptStatus === 'loaded') {
      setIsScriptLoaded(true);
    } else if (scriptStatus === 'loading') {
      const listener = () => setIsScriptLoaded(true);
      scriptListeners.push(listener);
      return () => {
        const idx = scriptListeners.indexOf(listener);
        if (idx !== -1) scriptListeners.splice(idx, 1);
      };
    }
  }, []);

  useEffect(() => {
    if (!isScriptLoaded || !containerRef.current || !siteKey) return;
    if (widgetIdRef.current) return; // Already rendered

    // Inform parent that we're starting up
    try { onState?.("idle"); } catch {}

    const renderWidget = () => {
        if (!window.turnstile) return;
        
        try {
            const id = window.turnstile.render(containerRef.current!, {
                sitekey: siteKey,
                theme: 'dark',
                size: 'compact',
                appearance: 'always',
                callback: async (token: string) => {
                    logger.debug("[TurnstileWidget] Token received, posting to backend");
                    try {
                        await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/__captcha/turnstile`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json", "X-Client-Id": xClient },
                            credentials: "include",
                            body: JSON.stringify({ token }),
                        });
                        logger.debug("[TurnstileWidget] Setting state to success");
                        onState?.("success");
                    } catch (err) {
                        logger.error("[TurnstileWidget] Error posting token:", err);
                        onState?.("error");
                    }
                },
                'error-callback': () => {
                    logger.error("[TurnstileWidget] Error callback");
                    onState?.("error");
                },
                'expired-callback': () => {
                    logger.warn("[TurnstileWidget] Expired");
                    onState?.("idle");
                }
            });
            widgetIdRef.current = id;
        } catch (e) {
            logger.error("[TurnstileWidget] Render error", e);
            onState?.("error");
        }
    };

    renderWidget();

    // If the script is blocked (adblock) mark an error after a short delay to hint the user.
    const failTimer = window.setTimeout(() => {
      if (!widgetIdRef.current && !window.turnstile) onState?.("error");
    }, 5000);

    return () => {
      clearTimeout(failTimer);
      if (widgetIdRef.current && window.turnstile) {
        try {
            window.turnstile.remove(widgetIdRef.current);
        } catch (e) {
            // ignore
        }
        widgetIdRef.current = null;
      }
    };
  }, [isScriptLoaded, siteKey, xClient, onState]);

  return (
    <div className={className}>
      <div
        ref={containerRef}
        className="cf-turnstile min-h-[38px]"
        style={{ maxWidth: '100%', width: 'fit-content' }}
      />
    </div>
  );
}
