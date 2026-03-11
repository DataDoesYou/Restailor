"use client";

import React, { useEffect, useMemo, useState, useLayoutEffect } from "react";
import { useSearchParams } from "next/navigation";
import api, { ApiError } from "@/lib/api";
import { ModelSettings } from "@/lib/apiClient";
import { getAnalyticsSummary, Bucket } from "@/lib/api.analytics";
import { getJobsAnalytics, JobsAnalyticsResponse } from "@/lib/api.analytics.jobs";
import { PeriodControls } from "@/components/analytics/PeriodControls";
import { LocalNav } from "@/components/analytics/LocalNav";
import { KpiCards } from "@/components/analytics/KpiCards";
import { LedgerTable } from "@/components/analytics/LedgerTable";
import {
  RequestsSpendChart,
  ByTypeBar,
  ByModelBar,
  BalanceDeltaChart,
  RequestsStackedArea,
  SpendBars,
  SpendByTypeDonut,
  TopModelsBar,
  TokenMixByModelBars,
  LatencyLine,
  BalanceLine,
} from "@/components/analytics/Charts";
import { FunnelBar, CohortRings, ClosuresLine, SnapshotsAppliedArea, AppliedBar } from "@/components/analytics/JobsCharts";

interface SummaryData {
  series: { bucket: string; count: number; spend_usd: string }[];
  requests_by_type?: { bucket: string; request_type: string; count: number }[];
  by_type: Record<string, { count: number; spend_usd: string }>;
  by_model: Record<string, { count: number; spend_usd: string }>;
  multi_model: Record<string, number>;
  token_mix: Record<string, number>;
  latency: { avg_ms?: number; series?: { bucket: string; avg_ms: number }[] };
  balance_timeline: { bucket: string; delta_cents: number; running_cents: number }[];
  tokens_by_model?: { model: string; avg_prompt: number; avg_completion: number }[];
  recent_ledger?: { id?: string; created_at: string; delta_cents: number; type?: string; note?: string; provider_ref?: string }[];
  current_balance_cents?: number;
  balance_usd?: string;
  avg_price_recent_usd?: string;
  totals?: { requests: number; spend_usd: string };
}

export default function AnalyticsClient({ initialActive = "overview" }: { initialActive?: string }) {
  const sp = useSearchParams();
  const STORAGE_KEY = "analytics.activeSection";
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [jobsA, setJobsA] = useState<JobsAnalyticsResponse | null>(null);
  
  // Initialize with URL params or defaults (will be overridden by user prefs if available)
  const initialRange = useMemo(() => {
    const range = sp?.get("range") || "90d";
    const fromQ = sp?.get("from") || null;
    const toQ = sp?.get("to") || null;
    const bucketRaw = sp?.get("bucket") || "day";
    const bucketQ = (bucketRaw === "week" || bucketRaw === "month" ? bucketRaw : "day") as "day" | "week" | "month";
    return { range, fromQ, toQ, bucketQ };
  }, [sp]);
  
  const [period, setPeriod] = useState<string>(initialRange.range);
  const [bucket, setBucket] = useState<Bucket>(initialRange.bucketQ as Bucket);
  const [from, setFrom] = useState<string | null>(initialRange.fromQ);
  const [to, setTo] = useState<string | null>(initialRange.toQ);
  const [preferencesLoaded, setPreferencesLoaded] = useState<boolean>(false);
  const [fullSettings, setFullSettings] = useState<ModelSettings | null>(null);
  // Seed with SSR-provided initialActive to avoid hydration mismatch
  const [active, setActive] = useState<string>(initialActive);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lowerReady, setLowerReady] = useState<boolean>(false);
  
  // Load user's preferred analytics period on mount
  useEffect(() => {
    async function loadPreferences() {
      try {
        const response = await api.get<{ settings: ModelSettings }>("/users/me/model-settings");
        setFullSettings(response.settings);
        const savedPeriod = response.settings?.analytics_period;
        if (savedPeriod && !sp?.get("range")) {
          // Only apply saved preference if there's no URL param
          setPeriod(savedPeriod);
        }
      } catch (e: any) {
        // Silently fail - user might not be logged in, or prefs don't exist
      } finally {
        setPreferencesLoaded(true);
      }
    }
    loadPreferences();
  }, [sp]);
  
  // Save period preference when it changes (instant)
  useEffect(() => {
    if (!preferencesLoaded) return; // Don't save on initial load
    if (!fullSettings) return; // Don't save if we don't have base settings
    
    // Avoid saving if the period hasn't actually changed from what's in settings
    if (fullSettings.analytics_period === period) return;
    
    async function savePreference() {
      try {
        const newSettings = { ...fullSettings!, analytics_period: period };
        // Optimistically update local state to prevent double-save
        setFullSettings(newSettings);
        
        await api.put("/users/me/model-settings", {
          settings: newSettings,
        });
      } catch (e: any) {
        // Silently fail - user might not be logged in
      }
    }
    
    savePreference();
  }, [period, preferencesLoaded, fullSettings]);

  function computeRangeISO(): { from: string; to: string } {
    const now = new Date();
    if (period === "custom" && from && to) {
      return { from: new Date(from).toISOString(), to: new Date(to).toISOString() };
    }
    if (period === "ytd") {
      const jan1 = new Date(Date.UTC(now.getUTCFullYear(), 0, 1, 0, 0, 0));
      return { from: jan1.toISOString(), to: now.toISOString() };
    }
    if (period === "all") {
      // All-time: from beginning of time (year 2000) to now
      const beginning = new Date(Date.UTC(2000, 0, 1, 0, 0, 0));
      return { from: beginning.toISOString(), to: now.toISOString() };
    }
    const days = period === "7d" ? 7 : period === "90d" ? 90 : 30;
    const start = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
    return { from: start.toISOString(), to: now.toISOString() };
  }

  async function load(limit?: number, signal?: AbortSignal) {
    setLoading(true);
    setError(null);
    try {
      const r = computeRangeISO();
      const [summaryData, jobsData] = await Promise.all([
        getAnalyticsSummary({ from: r.from, to: r.to, bucket, recentLimit: limit, tz: "UTC" }, { signal }),
        getJobsAnalytics({ signal, query: { from: r.from, to: r.to, bucket, tz: "UTC" } }),
      ]);
      setSummary(summaryData);
      setJobsA(jobsData);
    } catch (e: any) {
      // During hot reloads, in-flight requests can be aborted; don't latch an error on AbortError
      const msgText = String(e?.message || e || "");
      const isAbort = e?.name === "AbortError" || /aborted/i.test(msgText) || /The operation was aborted/i.test(msgText);
      if (!isAbort) {
        const msg = e instanceof ApiError ? `${e.status}: ${String(e.detail)}` : msgText;
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  // Debounce refetch on date changes by 300ms
  useEffect(() => {
    const ac = new AbortController();
    const timer = setTimeout(() => {
      load(undefined, ac.signal);
    }, 300);
    return () => {
      ac.abort();
      clearTimeout(timer);
    };
  }, [period, bucket, from, to]);

  // Keep URL search params in sync
  useEffect(() => {
    try {
      const u = new URL(window.location.href);
      u.searchParams.set("range", period);
      if (period === "custom") {
        if (from) u.searchParams.set("from", from);
        else u.searchParams.delete("from");
        if (to) u.searchParams.set("to", to);
        else u.searchParams.delete("to");
      } else {
        u.searchParams.delete("from");
        u.searchParams.delete("to");
      }
      u.searchParams.set("bucket", bucket);
      if (u.toString() !== window.location.href) window.history.replaceState({}, "", u.toString());
    } catch {}
  }, [period, bucket, from, to]);

  // Tabs available (keep in sync with LocalNav items)
  const tabs = useMemo(() => [
    "overview", "usage", "spend", "models", "ledger", "jobs"
  ] as const, []);

  // Track when initial active tab has been resolved to avoid flicker
  const [activeReady, setActiveReady] = useState(false);

  // Determine initial tab before first paint to prevent flicker
  useLayoutEffect(() => {
    try {
      const fromHash = window.location.hash ? window.location.hash.slice(1) : "";
      if (fromHash && tabs.includes(fromHash as any)) {
        if (fromHash !== active) setActive(fromHash);
        try { localStorage.setItem(STORAGE_KEY, fromHash); } catch {}
        try { document.cookie = `analytics_active=${fromHash}; Max-Age=2592000; Path=/`; } catch {}
        setActiveReady(true);
        return;
      }
      const saved = (() => { try { return localStorage.getItem(STORAGE_KEY) || ""; } catch { return ""; } })();
      if (saved && tabs.includes(saved as any)) {
        if (saved !== active) setActive(saved);
        try { if (!fromHash) window.location.hash = saved; } catch {}
        try { document.cookie = `analytics_active=${saved}; Max-Age=2592000; Path=/`; } catch {}
        setActiveReady(true);
        return;
      }
    } catch {}
    if (active !== "overview") setActive("overview");
    setActiveReady(true);
  }, [tabs]);

  // Listen for hash changes after mount
  useEffect(() => {
    const onHashChange = () => {
      try {
        const h = window.location.hash ? window.location.hash.slice(1) : "";
        if (h && tabs.includes(h as any)) {
          if (h !== active) setActive(h);
          try { localStorage.setItem(STORAGE_KEY, h); } catch {}
          try { document.cookie = `analytics_active=${h}; Max-Age=2592000; Path=/`; } catch {}
        }
      } catch {}
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [tabs, active]);

  // Mark lower sections eligible as soon as we have data (supports deep links like #usage on refresh)
  useEffect(() => {
    if (summary) setLowerReady(true);
  }, [summary]);

  const totals = useMemo(() => {
    const totalReq = summary?.totals?.requests ?? (summary?.series?.reduce((s, p) => s + (p.count || 0), 0) || 0);
    const totalSpend = summary?.totals?.spend_usd
      ? parseFloat(summary.totals.spend_usd)
      : summary?.series?.reduce((s, p) => s + (parseFloat(p.spend_usd || "0") || 0), 0) || 0;
    const r = computeRangeISO();
    const days = Math.max(1, Math.ceil((new Date(r.to).getTime() - new Date(r.from).getTime()) / (24 * 60 * 60 * 1000)));
    const avgPerDay = totalReq / days;
    const balanceCents = summary?.current_balance_cents || 0;
    const balanceUsd = summary?.balance_usd ?? (balanceCents / 100).toFixed(2);
    // Use server-provided rolling avg (last 100) when available; fallback to series avg
    const avgPriceRecent = summary?.avg_price_recent_usd ? parseFloat(summary.avg_price_recent_usd) : totalReq > 0 ? totalSpend / totalReq : 0;
    const requestsLeft = avgPriceRecent > 0 ? Math.floor((parseFloat(balanceUsd) || 0) / avgPriceRecent) : 0;
    return { totalReq, totalSpend, avgPerDay, balanceUsd, requestsLeft, avgPriceRecent };
  }, [summary, period, from, to, bucket]);

  const empty = useMemo(() => {
    if (!summary) return false;
    const noSeries = !summary.series || summary.series.length === 0;
    const noByType = !summary.by_type || Object.keys(summary.by_type).length === 0;
    const noByModel = !summary.by_model || Object.keys(summary.by_model).length === 0;
    const noLedger = !summary.balance_timeline || summary.balance_timeline.length === 0;
    return noSeries && noByType && noByModel && noLedger;
  }, [summary]);

  return (
    <div className="p-0">
      {/* Sticky header */}
      <div className="sticky top-0 z-20 bg-[#0b0e14] border-b border-outline-var">
        {/* Desktop header - horizontal layout */}
        <div className="hidden md:block">
          <div className="px-6 py-3 flex items-center justify-between gap-4">
            <h1 className="text-xl font-semibold">Analytics</h1>
            <PeriodControls
              period={period}
              setPeriod={setPeriod}
              from={from}
              to={to}
              setFrom={setFrom}
              setTo={setTo}
              bucket={bucket}
              setBucket={setBucket}
              loading={loading}
            />
          </div>
          <div className="px-6">
            <LocalNav
              active={active}
              showActive={true}
              setActive={(k) => {
                setActive(k);
                if (typeof window !== "undefined") {
                  try { window.location.hash = k; } catch {}
                  try { localStorage.setItem(STORAGE_KEY, k); } catch {}
                  try { document.cookie = `analytics_active=${k}; Max-Age=2592000; Path=/`; } catch {}
                }
              }}
              items={[
                { key: "overview", label: "Overview" },
                { key: "usage", label: "Usage" },
                { key: "spend", label: "Spend" },
                { key: "models", label: "Models" },
                { key: "ledger", label: "Deposits" },
                { key: "jobs", label: "Jobs" },
              ]}
            />
          </div>
        </div>
        {/* Mobile header - vertical layout */}
        <div className="md:hidden">
          <div className="px-4 py-3">
            <h1 className="text-xl font-semibold mb-3">Analytics</h1>
            <PeriodControls
              period={period}
              setPeriod={setPeriod}
              from={from}
              to={to}
              setFrom={setFrom}
              setTo={setTo}
              bucket={bucket}
              setBucket={setBucket}
              loading={loading}
            />
          </div>
          <div className="px-4">
            <LocalNav
              active={active}
              showActive={true}
              setActive={(k) => {
                setActive(k);
                if (typeof window !== "undefined") {
                  try { window.location.hash = k; } catch {}
                  try { localStorage.setItem(STORAGE_KEY, k); } catch {}
                  try { document.cookie = `analytics_active=${k}; Max-Age=2592000; Path=/`; } catch {}
                }
              }}
              items={[
                { key: "overview", label: "Overview" },
                { key: "usage", label: "Usage" },
                { key: "spend", label: "Spend" },
                { key: "models", label: "Models" },
                { key: "ledger", label: "Deposits" },
                { key: "jobs", label: "Jobs" },
              ]}
            />
          </div>
        </div>
      </div>

      <div className="px-4 md:px-6 py-6 space-y-6" style={{ visibility: activeReady ? "visible" : "hidden" }}>
        {error && <div className="text-sm text-red-600">{error}</div>}

        {/* Overview */}
        {active === "overview" && (
          <div className="space-y-6" role="tabpanel" id="panel-overview" aria-labelledby="tab-overview">
            {summary && (
              <KpiCards
                items={[
                  { label: "Total requests", value: totals.totalReq },
                  { label: "Avg/day", value: totals.avgPerDay.toFixed(1) },
                  { label: "Total spend", value: `$${totals.totalSpend.toFixed(2)}` },
                  { label: "Current balance", value: `$${totals.balanceUsd}` },
                  { label: "Requests left est.", value: totals.requestsLeft, hint: "Uses rolling avg of your last 100 requests" },
                ]}
              />
            )}
            {loading && <div>Loading…</div>}
            {summary && !empty && (
              <div className="space-y-6">
                <RequestsSpendChart data={summary.series} />
                {summary.requests_by_type && <RequestsStackedArea data={summary.requests_by_type} />}
                <LatencyLine data={summary.latency?.series || []} />
              </div>
            )}
            {summary && empty && (
              <div className="p-4 rounded-md bg-[var(--accent)] border border-outline-var text-sm text-foreground/80" role="status" aria-live="polite">
                <div className="font-medium">No activity in this period</div>
                <ul className="list-disc list-inside mt-1">
                  <li>Try expanding the date range (e.g., 30d → 90d or YTD)</li>
                  <li>Switch the bucket to a larger interval (Weekly/Monthly)</li>
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Usage (lazy after Overview) */}
        {active === "usage" && summary && lowerReady && (
          <div className="space-y-6" role="tabpanel" id="panel-usage" aria-labelledby="tab-usage">
            {!empty ? (
              <>
                <ByTypeBar data={summary.by_type} />
                {summary.requests_by_type && <RequestsStackedArea data={summary.requests_by_type} />}
                {summary.tokens_by_model && <TokenMixByModelBars data={summary.tokens_by_model} />}
              </>
            ) : (
              <div className="p-4 rounded-md bg-[var(--accent)] border border-outline-var text-sm text-foreground/80" role="status" aria-live="polite">
                <div className="font-medium">No activity in this period</div>
                <div>Adjust the date range or try a larger bucket.</div>
              </div>
            )}
          </div>
        )}

        {/* Spend (lazy after Overview) */}
        {active === "spend" && summary && lowerReady && (
          <div className="space-y-6" role="tabpanel" id="panel-spend" aria-labelledby="tab-spend">
            {!empty ? (
              <>
                <RequestsSpendChart data={summary.series} />
                <SpendBars data={summary.by_type} />
                <SpendByTypeDonut data={summary.by_type} />
              </>
            ) : (
              <div className="p-4 rounded-md bg-[var(--accent)] border border-outline-var text-sm text-foreground/80" role="status" aria-live="polite">
                <div className="font-medium">No activity in this period</div>
                <div>Try expanding the date range and revisit this tab.</div>
              </div>
            )}
          </div>
        )}

        {/* Models (lazy after Overview) */}
        {active === "models" && summary && lowerReady && (
          <div className="space-y-6" role="tabpanel" id="panel-models" aria-labelledby="tab-models">
            {!empty ? (
              <>
                <ByModelBar data={summary.by_model} />
                <TopModelsBar data={summary.by_model} />
                {summary.tokens_by_model && <TokenMixByModelBars data={summary.tokens_by_model} />}
              </>
            ) : (
              <div className="p-4 rounded-md bg-[var(--accent)] border border-outline-var text-sm text-foreground/80" role="status" aria-live="polite">
                <div className="font-medium">No activity in this period</div>
                <div>Adjust the date range to see model usage.</div>
              </div>
            )}
          </div>
        )}

        {/* Deposits (lazy after Overview) */}
        {active === "ledger" && summary && lowerReady && (
          <div className="space-y-6" role="tabpanel" id="panel-ledger" aria-labelledby="tab-ledger">
            {!empty ? (
              <>
                <BalanceDeltaChart data={summary.balance_timeline} />
                <BalanceLine data={summary.balance_timeline} />
                {summary.recent_ledger && (
                  <LedgerTable
                    rows={summary.recent_ledger}
                    onViewAll={() => {
                      const ac = new AbortController();
                      load(200, ac.signal);
                    }}
                  />
                )}
              </>
            ) : (
              <div className="p-4 rounded-md bg-[var(--accent)] border border-outline-var text-sm text-foreground/80" role="status" aria-live="polite">
                <div className="font-medium">No activity in this period</div>
                <div>Expand the date range to view deposits.</div>
              </div>
            )}
          </div>
        )}

        {/* Jobs */}
            {active === "jobs" && jobsA && (
          <div className="space-y-6" role="tabpanel" id="panel-jobs" aria-labelledby="tab-jobs">
            {(() => {
              const cohort = jobsA.cohort_over_time || [];
              const snap = jobsA.snapshots_over_time || [];
              const stages = jobsA.stages_over_time || [];
              if (cohort.length === 0 && snap.length === 0 && stages.length === 0) {
                return <FunnelBar stages={jobsA.funnel_active} counts={jobsA.counts_by_stage_active} />;
              }
              if (cohort.length > 0) {
                const rows = [...cohort].sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)));
                return <SnapshotsAppliedArea rows={rows} />;
              }
              // Fallback: merge snapshots and stage transitions (legacy)
              const map = new Map<string, any>();
              for (const r of snap) {
                map.set(r.bucket, { bucket: r.bucket, snapshots: r.snapshots || 0, applied: r.applied || 0, interviewing: 0, offer: 0, hired: 0 });
              }
              for (const s of stages) {
                const prev = map.get(s.bucket) || { bucket: s.bucket, snapshots: 0, applied: 0, interviewing: 0, offer: 0, hired: 0 };
                prev.interviewing = s.interviewing || 0;
                prev.offer = s.offer || 0;
                prev.hired = s.hired || 0;
                map.set(s.bucket, prev);
              }
              const rows = Array.from(map.values()).sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)));
              return <SnapshotsAppliedArea rows={rows} />;
            })()}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {(() => {
                // Sum totals over the selected period
                const cohort = (jobsA.cohort_over_time || []).slice();
                const rows = cohort.length > 0 ? cohort : (() => {
                  // Fallback: merge snapshots + stages
                  const map = new Map<string, any>();
                  const snap = jobsA.snapshots_over_time || [];
                  const stages = jobsA.stages_over_time || [];
                  for (const r of snap) {
                    map.set(r.bucket, { bucket: r.bucket, snapshots: r.snapshots || 0, applied: r.applied || 0, interviewing: 0, offer: 0, hired: 0 });
                  }
                  for (const s of stages) {
                    const prev = map.get(s.bucket) || { bucket: s.bucket, snapshots: 0, applied: 0, interviewing: 0, offer: 0, hired: 0 };
                    prev.interviewing = s.interviewing || 0;
                    prev.offer = s.offer || 0;
                    prev.hired = s.hired || 0;
                    map.set(s.bucket, prev);
                  }
                  return Array.from(map.values());
                })();
                const totals = rows.reduce((acc: any, r: any) => {
                  acc.snapshots += r.snapshots || 0;
                  acc.applied += r.applied || 0;
                  acc.interviewing += r.interviewing || 0;
                  acc.offer += r.offer || 0;
                  acc.hired += r.hired || 0;
                  return acc;
                }, { snapshots: 0, applied: 0, interviewing: 0, offer: 0, hired: 0 });
                return <CohortRings totals={totals} />;
              })()}
              {(() => {
                const cohort = jobsA.cohort_over_time || [];
                const rows = (cohort.length > 0 ? cohort : (() => {
                  const map = new Map<string, any>();
                  const snap = jobsA.snapshots_over_time || [];
                  const stages = jobsA.stages_over_time || [];
                  for (const r of snap) {
                    map.set(r.bucket, { bucket: r.bucket, snapshots: r.snapshots || 0, applied: r.applied || 0, interviewing: 0, offer: 0, hired: 0 });
                  }
                  for (const s of stages) {
                    const prev = map.get(s.bucket) || { bucket: s.bucket, snapshots: 0, applied: 0, interviewing: 0, offer: 0, hired: 0 };
                    prev.interviewing = s.interviewing || 0;
                    prev.offer = s.offer || 0;
                    prev.hired = s.hired || 0;
                    map.set(s.bucket, prev);
                  }
                  return Array.from(map.values());
                })()).map(r => ({ bucket: r.bucket, applied: r.applied || 0 }));
                return <AppliedBar rows={rows} bucketLabel={bucket} />;
              })()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
