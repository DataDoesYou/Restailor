"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, useCallback } from "react";
import api from "@/lib/api";
import { clearAccessToken, clearEphemeralAccessToken } from "@/lib/auth";
import LoginClient from "@/components/pages/LoginClient";
import { deriveAliasAndTooltip } from "@/components/resume/models";
import SidebarModels from "@/components/chrome/SidebarModels";
import { supportMailto } from "@/lib/site";
import dynamic from "next/dynamic";
const AuthDebug = process.env.NEXT_PUBLIC_RT_DEBUG === "1"
  ? dynamic(() => import("@/components/debug/AuthDebug"), { ssr: false })
  : null as unknown as (() => React.JSX.Element);

interface Props {
  initialMe?: any | null;
  initialBalance?: any | null;
}

export default function SidebarClient({ initialMe = null, initialBalance = null }: Props) {
  const [me, setMe] = useState<any | null>(initialMe);
  const [balance, setBalance] = useState<any | null>(initialBalance);
  const hadSsrAuth = typeof initialMe !== "undefined" && initialMe !== null;
  const [loaded, setLoaded] = useState<boolean>(hadSsrAuth);
  const [trialModels, setTrialModels] = useState<string[] | null | undefined>(undefined);

  // Initialize __rt_was_logged_in flag for SSR auth to prevent AuthFetchGuard blocking
  useEffect(() => {
    if (hadSsrAuth && typeof window !== "undefined") {
      (window as any).__rt_was_logged_in = true;
    }
  }, [hadSsrAuth]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      console.log('[SidebarClient] useEffect load starting...');
      try { 
        const u = await api.get("/users/me"); 
        console.log('[SidebarClient] Client fetch success:', { hasUser: !!u });
        if (mounted) setMe(u); 
      } catch (e: any) { 
        console.log('[SidebarClient] Client fetch error:', { status: e?.status, willClear: e?.status === 401 || e?.status === 403 });
        // Only clear user on explicit 401/403 - preserve SSR data on network errors
        if (mounted && (e?.status === 401 || e?.status === 403)) {
          setMe(null);
        }
      }
      try { const b = await api.get("/users/me/balance"); if (mounted) setBalance(b); } catch {}
      // Fetch trial eligibility to get trial_models restriction
      try {
        const trial = await api.get<any>("/credits/trial-eligibility");
        if (mounted) {
          setTrialModels(trial?.trial_models || null);
        }
      } catch {
        if (mounted) setTrialModels(null);
      }
      if (mounted) setLoaded(true);
    };
    // FIXED: Don't refetch user if we already have SSR data - just refresh balance
    // The SSR data is fresh and avoids race conditions with cookie hydration
    if (hadSsrAuth) {
      // We have SSR user data, just refresh balance/trial without re-validating user
      const refreshData = async () => {
        try { const b = await api.get("/users/me/balance"); if (mounted) setBalance(b); } catch {}
        try {
          const trial = await api.get<any>("/credits/trial-eligibility");
          if (mounted) {
            setTrialModels(trial?.trial_models || null);
          }
        } catch {
          if (mounted) setTrialModels(null);
        }
        if (mounted) setLoaded(true);
      };
      refreshData();
    } else {
      // No SSR data, need to fetch user client-side (e.g., after login event)
      // For logged-out users, set trialModels to null (no restrictions) so models can load
      if (mounted) setTrialModels(null);
      setLoaded(true);
    }
    const onAuth = () => load();
    window.addEventListener("rt-auth", onAuth as EventListener);
    return () => { mounted = false; window.removeEventListener("rt-auth", onAuth as EventListener); };
  }, [hadSsrAuth]);

  // Live balance updates: listen for global balance events and refresh or set from payload
  useEffect(() => {
    let disposed = false;
    const onBalance = async (e: Event) => {
      if (disposed) return;
      const d = (e as CustomEvent).detail || {};
      // If a new balance is provided, apply it directly; otherwise refetch
      if (typeof d.balance_usd !== "undefined" || typeof d.balance_cents !== "undefined") {
        setBalance((prev: any) => ({ ...(prev || {}), ...d, currency: d.currency || ((prev && (prev as any).currency) || "USD") }));
      } else {
        try { const b = await api.get("/users/me/balance"); if (!disposed) setBalance(b); } catch {}
      }
      // Refetch trial eligibility to update trial_models restrictions (e.g., after claiming trial)
      try {
        const trial = await api.get<any>("/credits/trial-eligibility");
        if (!disposed) {
          setTrialModels(trial?.trial_models || null);
        }
      } catch {
        if (!disposed) setTrialModels(null);
      }
    };
    window.addEventListener("rt-balance", onBalance as EventListener);
    return () => { disposed = true; window.removeEventListener("rt-balance", onBalance as EventListener); };
  }, []);

  // Model selection state - managed by SidebarModels
  const [fitModelLabel, setFitModelLabel] = useState<string>("GPT-5");
  const [tailorModelLabel, setTailorModelLabel] = useState<string>("Grok 4.3");
  const [judgeLabel, setJudgeLabel] = useState<string>("Grok 4.3");

  // Simple handlers - SidebarModels handles DB persistence
  const handleFitChange = (label: string) => {
    if (running) return;
    setFitModelLabel(label);
  };

  const handleTailorChange = (label: string) => {
    if (running) return;
    setTailorModelLabel(label);
  };

  const handleJudgeChange = (label: string) => {
    if (running) return;
    setJudgeLabel(label);
  };

  // NOTE: rt-sidebar event is now dispatched by SidebarModels component
  // (removed duplicate dispatch from here to avoid alias/label format confusion)

  // Compute route and roles (hooks must be unconditional)
  const pathname = usePathname() || "";
  const uname = String(me?.email || me?.username || "").trim();
  const isAdmin = String(me?.role || "").toLowerCase() === "admin";
  const isActive = (href: string, exactMatch = false) => exactMatch ? pathname === href : (pathname === href || pathname.startsWith(href + "/"));
  const navLinkClass = (href: string, exactMatch = false) => [
    "block rounded px-3 py-2 transition-colors",
    "underline",
    "hover:bg-slate-700 active:bg-slate-500",
    isActive(href, exactMatch) ? "bg-slate-700/70 text-white no-underline font-semibold" : ""
  ].filter(Boolean).join(" ");
  const featureAnalytics = (process.env.NEXT_PUBLIC_FEATURE_ANALYTICS ?? "1") === "1";

  // Judge visibility (keep simple boolean state for now - can be moved to DB later)
  const [showJudge, setShowJudge] = useState<boolean>(true);

  // Listen for page run-state to disable controls while a job is active
  const [running, setRunning] = useState<boolean>(false);
  useEffect(() => {
    const onRun = (e: Event) => {
      const d = (e as CustomEvent).detail || {};
      if (typeof d.running === "boolean") {
        setRunning(d.running);
        // On run stop, refresh balance immediately
        if (d.running === false) {
          (async () => {
            try { const b = await api.get("/users/me/balance"); setBalance(b); } catch {}
          })();
        }
      }
    };
    window.addEventListener("rt-run", onRun as EventListener);
    return () => window.removeEventListener("rt-run", onRun as EventListener);
  }, []);

  // Listen for main-page state changes for showJudge
  useEffect(() => {
    const onSidebarEvt = (e: Event) => {
      const d = (e as CustomEvent).detail || {};
      if (typeof d.showJudge === "boolean") setShowJudge(d.showJudge);
    };
    window.addEventListener("rt-sidebar", onSidebarEvt as EventListener);
    return () => window.removeEventListener("rt-sidebar", onSidebarEvt as EventListener);
  }, []);

  // Listen for model selection updates from SidebarModels
  // NOTE: These aliases come in alias format (e.g. "GPT-5.5 Instant"), not full label format
  // They're only used for the legacy UI state, not for dispatching events
  useEffect(() => {
    const onMultiModels = (e: Event) => {
      const d = (e as CustomEvent).detail || {};
      // Don't update - SidebarModels handles all event dispatching now
      // These local states are just for display (if needed)
    };
    window.addEventListener("rt-multi-models", onMultiModels as EventListener);
    return () => window.removeEventListener("rt-multi-models", onMultiModels as EventListener);
  }, []);

  return (
    <aside className="sticky top-0 h-screen text-slate-200 text-base w-[240px] min-w-[240px] max-w-[240px] shrink-0 box-border relative overflow-x-hidden">
      <div className="space-y-2 px-5 pt-6 h-full overflow-y-auto overflow-x-hidden hover-thin-scrollbar pb-6">
        {!me ? (
          <>
            <LoginClient stackedButtons />
            {AuthDebug ? <AuthDebug /> : null}
          </>
        ) : (
          <>
            {/* Navigation links appear above Account for all logged-in users */}
            <div className="mb-2 space-y-2">
              <nav className="flex flex-col gap-1">
                <Link href="/resume" className={navLinkClass("/resume")} aria-current={isActive("/resume") ? "page" : undefined}>Resume Tailor</Link>
                <Link href="/history" className={navLinkClass("/history")} aria-current={isActive("/history") ? "page" : undefined}>History</Link>
                {featureAnalytics && (
                  <Link href="/dashboard/analytics" className={navLinkClass("/dashboard/analytics")} aria-current={isActive("/dashboard/analytics") ? "page" : undefined}>Analytics</Link>
                )}
                <Link href="/budget" className={navLinkClass("/budget")} aria-current={isActive("/budget") ? "page" : undefined}>Budget</Link>
                <Link href="/security" className={navLinkClass("/security")} aria-current={isActive("/security") ? "page" : undefined}>Security</Link>
                <Link href="/settings" className={navLinkClass("/settings")} aria-current={isActive("/settings") ? "page" : undefined}>Settings</Link>
                <Link href="/help" className={navLinkClass("/help")} aria-current={isActive("/help") ? "page" : undefined}>Help</Link>
                {isAdmin && (
                  <>
                    <Link href="/admin" className={navLinkClass("/admin", true)} aria-current={pathname === "/admin" ? "page" : undefined}>Admin</Link>
                    <Link href="/admin/analytics" className={navLinkClass("/admin/analytics")} aria-current={isActive("/admin/analytics") ? "page" : undefined}>Admin Analytics</Link>
                  </>
                )}
              </nav>
            </div>
            <div
              role="separator"
              aria-hidden
              className="-mx-12 w-full h-px bg-slate-700/70"
              style={{ marginTop: 24, marginBottom: 24 }}
            />
            <div className="mb-4">Welcome, {uname}</div>
            {balance && (typeof balance.balance_usd === "string" || typeof balance.balance_usd === "number") && (
              <div className="text-slate-400 text-base">Balance: ${String(balance.balance_usd)}</div>
            )}
            <div className="mt-4">
              <button
                className="w-full text-left underline btn-plain"
                onClick={() => {
                  (async () => {
                    try {
                      await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/logout`, { method: 'POST', credentials: 'include' });
                    } catch {}
                    try { clearAccessToken(); clearEphemeralAccessToken(); } catch {}
                    try {
                      // Clear local input store and broadcast to live pages
                      localStorage.setItem("__rt_resume_text", "");
                      localStorage.setItem("__rt_jd_text", "");
                      localStorage.setItem("__rt_resume_ts", JSON.stringify(0));
                      localStorage.setItem("__rt_jd_ts", JSON.stringify(0));
                      window.dispatchEvent(new CustomEvent("rt-inputs", { detail: { resumeText: "", jdText: "", rTs: 0, jTs: 0 } }));
                    } catch {}
                    try { window.dispatchEvent(new CustomEvent("rt-auth", { detail: { state: "logged-out", reason: 'manual' } })); } catch {}
                    window.location.href = "/";
                  })();
                }}
              >Logout</button>
            </div>
          </>
        )}
        
        {/* Single SidebarModels instance - handles both logged-in and logged-out states */}
        {(isActive("/resume") || pathname === "/") && (
          <>
            {/* Separator before model settings */}
            {me && (
              <div
                role="separator"
                aria-hidden
                className="-mx-12 w-full h-px bg-slate-700/70"
                style={{ marginTop: 24, marginBottom: 24 }}
              />
            )}
            <div className={!me ? "mt-4" : "mt-3"}>
              <SidebarModels
                running={running}
                showJudge={me ? showJudge : true}
                trialModels={trialModels}
                isAuthenticated={!!me}
              />
            </div>
          </>
        )}
        
        {/* Contact links - appears at bottom for all users */}
        <div
          role="separator"
          aria-hidden
          className="-mx-12 w-full h-px bg-slate-700/70"
          style={{ marginTop: 24, marginBottom: 24 }}
        />
        <div className="space-y-1 text-xs">
          <a 
            href="/help"
            suppressHydrationWarning
            className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-700/50 transition-colors text-slate-400 hover:text-slate-200"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Help & Documentation</span>
          </a>
          <a 
            href="/team"
            suppressHydrationWarning
            className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-700/50 transition-colors text-slate-400 hover:text-slate-200"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            <span>Team</span>
          </a>
          <a 
            href={supportMailto}
            suppressHydrationWarning
            className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-700/50 transition-colors text-slate-400 hover:text-slate-200"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <span>Contact Support</span>
          </a>
        </div>
        
        {/* Copyright notice */}
        <div className="mt-4 pt-3 text-[10px] text-slate-500 leading-relaxed">
          © {new Date().getFullYear()} DataDoesYou LLC.<br />All rights reserved.
        </div>
      </div>
      {/* visual separator that doesn't affect inner measurements */}
      <div aria-hidden className="absolute top-0 right-0 h-full w-px bg-slate-800" />
    </aside>
  );
}
