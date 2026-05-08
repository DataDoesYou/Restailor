"use client";

import React, { useEffect, useState } from "react";
import api, { ApiError } from "@/lib/api";
import { UserDrilldownModal } from "@/components/analytics/UserDrilldownModal";
import { isRtDebug } from "@/lib/rtDebug";
import { findModelByModelId } from "@/components/resume/models";

// Map model_ids and historical model names to friendly display names
function getModelDisplayName(modelId: string): string {
  // Try model_id lookup first
  const opt = findModelByModelId(modelId);
  if (opt) return opt.alias;
  
  // Historical model mappings (preserve all legacy names)
  const historicalMap: Record<string, string> = {
    // Current models
    'claude-sonnet-4-6': 'Claude Sonnet 4.6',
    'claude-opus-4-7': 'Claude Opus 4.7',
    'claude-opus-4-6': 'Claude Opus 4.6',
    'gemini-3-flash-preview': 'Gemini 3 Flash',
    'gemini-3.1-pro-preview': 'Gemini 3.1 Pro',
    'gpt-5.5': 'GPT-5.5',
    'gpt-5.4-mini': 'GPT-5.4 Mini',
    'gpt-5.4': 'GPT-5.4',
    'gpt-5.3-chat-latest': 'GPT-5.3 Chat',
    'grok-4.3': 'Grok 4.3',
    'grok-4-1-fast-reasoning': 'Grok 4.1 Fast Reasoning',
    'grok-4-fast': 'Grok 4 Fast',
    'grok-4': 'Grok 4',
    
    // Legacy models (plain model IDs)
    'gemini-2.5-flash': 'Gemini 2.5 Flash',
    'gemini-2.5-pro': 'Gemini 2.5 Pro',
    'gpt-5.1-instant': 'GPT-5.1 Instant',
    'gpt-5.1-thinking': 'GPT-5.1 Thinking',
    'gpt-4.1': 'GPT-4.1',
    'gpt-5': 'GPT-5',
    'claude-4.0-opus': 'Claude Opus 4.0',
    'claude-3.7-sonnet': 'Claude Sonnet 3.7',
    'gemini-2.0-flash': 'Gemini 2.0 Flash',
    'gemini-2.0-pro': 'Gemini 2.0 Pro',
    'grok-3': 'Grok 3',
  };
  
  return historicalMap[modelId] || modelId;
}

// Response types matching backend
interface UserStats {
  total_users: number;
  signup_users: number;
  trial_users: number;
  paid_users: number;
  admin_users: number;
  verified_users: number;
  active_7d: number;
  active_30d: number;
}

interface RevenueMetrics {
  total_deposits_cents: number;
  total_deposits_usd: string;
  total_spend_cents: number;
  total_spend_usd: string;
  average_deposits_per_user_cents: number;
  average_deposits_per_user_usd: string;
}

interface SystemHealth {
  total_requests_24h: number;
  total_spend_24h_usd: string;
  avg_latency_ms: number | null;
  error_rate: number;
}

interface OverviewData {
  user_stats: UserStats;
  revenue_metrics: RevenueMetrics;
  system_health: SystemHealth;
}

interface SignupTrend {
  bucket: string;
  count: number;
}

interface RequestVolume {
  request_type: string;
  count: number;
  total_spend_usd: string;
}

interface ModelUsage {
  model: string;
  request_count: number;
  total_spend_usd: string;
  avg_price_usd: string;
}

export default function AdminAnalyticsClient() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [signups, setSignups] = useState<SignupTrend[]>([]);
  const [requests, setRequests] = useState<RequestVolume[]>([]);
  const [models, setModels] = useState<ModelUsage[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "users" | "spend" | "revenue">("overview");
  const [period, setPeriod] = useState<string>("90d");
  const [customFrom, setCustomFrom] = useState<string>("");
  const [customTo, setCustomTo] = useState<string>("");
  const [authReady, setAuthReady] = useState<boolean>(false);
  const [preferencesLoaded, setPreferencesLoaded] = useState<boolean>(false);
  const [initialLoadDone, setInitialLoadDone] = useState<boolean>(false);

  // Drilldown modal state
  const [drilldownOpen, setDrilldownOpen] = useState(false);
  const [drilldownMetric, setDrilldownMetric] = useState<"requests" | "spend" | "active" | "deposits" | "balance" | "users">("requests");
  const [drilldownLabel, setDrilldownLabel] = useState("");
  const [drilldownDays, setDrilldownDays] = useState<number | null>(null);
  const [drilldownRequestType, setDrilldownRequestType] = useState<string | null>(null);
  const [drilldownModel, setDrilldownModel] = useState<string | null>(null);
  const [drilldownAccountType, setDrilldownAccountType] = useState<string | null>(null);
  const [drilldownSignupDate, setDrilldownSignupDate] = useState<string | null>(null);

  function openDrilldown(
    metric: "requests" | "spend" | "active" | "deposits" | "balance" | "users", 
    label: string, 
    days?: number | null,
    requestType?: string | null,
    model?: string | null,
    accountType?: string | null,
    signupDate?: string | null
  ) {
    setDrilldownMetric(metric);
    setDrilldownLabel(label);
    setDrilldownRequestType(requestType ?? null);
    setDrilldownModel(model ?? null);
    setDrilldownAccountType(accountType ?? null);
    setDrilldownSignupDate(signupDate ?? null);
    // Use the minimum of the specified days and the global period
    const globalDays = computeDays();
    if (days !== undefined) {
      // If a specific timeframe is provided (e.g., 7d, 1 for 24h), use the minimum
      if (globalDays === null || days === null) {
        setDrilldownDays(days ?? globalDays);
      } else {
        setDrilldownDays(Math.min(days, globalDays));
      }
    } else {
      setDrilldownDays(globalDays);
    }
    setDrilldownOpen(true);
  }

  // Load admin preferences from database on mount (before anything else)
  useEffect(() => {
    let mounted = true;
    
    async function loadPreferencesAndAuth() {
      try {
        // First verify auth is established
        await api.get("/users/me");
        if (!mounted) return;
        
        // Then load preferences
        const response = await api.get<{ settings: { admin_analytics_period?: string; admin_analytics_tab?: string } }>("/users/me/model-settings");
        if (!mounted) return;
        
        const savedPeriod = response?.settings?.admin_analytics_period;
        const savedTab = response?.settings?.admin_analytics_tab;
        
        if (savedPeriod) {
          setPeriod(savedPeriod);
        }
        if (savedTab && ["overview", "users", "spend", "revenue"].includes(savedTab)) {
          setActiveTab(savedTab as "overview" | "users" | "spend" | "revenue");
        }
        
        setPreferencesLoaded(true);
        setAuthReady(true);
        setInitialLoadDone(true);
      } catch (e: any) {
        if (isRtDebug()) console.log("Could not load admin analytics preferences:", e);
        if (mounted) {
          // Still mark as ready so we show the error or default view
          setPreferencesLoaded(true);
          setAuthReady(false);
          setInitialLoadDone(true);
          setError("Authentication required");
          setLoading(false);
        }
      }
    }
    
    // Add a small delay to ensure auth is established
    const timer = setTimeout(() => {
      loadPreferencesAndAuth();
    }, 100);
    
    return () => { 
      mounted = false;
      clearTimeout(timer);
    };
  }, []);

  // Save both period and tab preferences together to avoid overwriting
  useEffect(() => {
    if (!initialLoadDone) return; // Don't save during initial load
    
    async function savePreferences() {
      try {
        // Fetch current settings first
        const currentResponse = await api.get<{ settings: any }>("/users/me/model-settings");
        const currentSettings = currentResponse?.settings || {};
        
        // Merge in the admin analytics preferences
        const updatedSettings = {
          ...currentSettings,
          admin_analytics_period: period,
          admin_analytics_tab: activeTab
        };
        
        const payload = { settings: updatedSettings };
        await api.put<{ settings: any; message: string }>("/users/me/model-settings", payload);
      } catch (e: any) {
        if (isRtDebug()) console.log("Could not save admin analytics preferences:", e);
      }
    }
    
    savePreferences();
  }, [period, activeTab, initialLoadDone]);

  // Load data when preferences are ready and period/dates change
  useEffect(() => {
    if (!authReady || !preferencesLoaded) return;
    loadData();
  }, [period, customFrom, customTo, authReady, preferencesLoaded]);

  function computeDays(): number | null {
    if (period === "all") return null; // All-time
    if (period === "ytd") {
      const now = new Date();
      const jan1 = new Date(Date.UTC(now.getUTCFullYear(), 0, 1));
      return Math.ceil((now.getTime() - jan1.getTime()) / (24 * 60 * 60 * 1000));
    }
    if (period === "custom" && customFrom && customTo) {
      const from = new Date(customFrom);
      const to = new Date(customTo);
      return Math.ceil((to.getTime() - from.getTime()) / (24 * 60 * 60 * 1000));
    }
    if (period === "7d") return 7;
    if (period === "90d") return 90;
    return 30; // default 30d
  }

  async function loadData() {
    setLoading(true);
    setError(null);
    
    try {
      const days = computeDays();
      const daysParam = days !== null ? `days=${days}` : "";
      const signupsParams = daysParam ? `?${daysParam}` : "";
      const requestsParams = daysParam ? `?${daysParam}` : "";
      const modelsParams = daysParam ? `?${daysParam}&limit=10` : "?limit=10";
      
      const [overviewData, signupsData, requestsData, modelsData] = await Promise.all([
        api.get<OverviewData>("/admin/analytics/overview"),
        api.get<SignupTrend[]>(`/admin/analytics/signups${signupsParams}`),
        api.get<RequestVolume[]>(`/admin/analytics/requests${requestsParams}`),
        api.get<ModelUsage[]>(`/admin/analytics/models${modelsParams}`),
      ]);

      setOverview(overviewData);
      setSignups(signupsData);
      setRequests(requestsData);
      setModels(modelsData);
    } catch (e: any) {
      const msg = e instanceof ApiError ? `${e.status}: ${String(e.detail)}` : String(e.message || e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  if (loading && !overview) {
    return (
      <div className="mx-auto max-w-7xl px-4 md:px-6 py-6">
        <div className="text-slate-400">Loading admin analytics...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 md:px-6 py-6">
        <div className="text-red-400">Error loading analytics: {error}</div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="mx-auto max-w-7xl px-4 md:px-6 py-6">
        <div className="text-slate-400">No data available</div>
      </div>
    );
  }

  const formatNumber = (n: number) => n.toLocaleString();

  return (
    <div className="mx-auto max-w-7xl px-4 md:px-6 py-6">
      <h1 className="text-3xl font-bold mb-6">Admin Analytics</h1>

      {/* Time Range Selector */}
      <div className="mb-6">
        <div className="flex gap-2 flex-wrap">
          {["7d", "30d", "90d", "ytd", "all"].map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 md:px-4 py-2 rounded text-sm md:text-base ${
                period === p
                  ? "bg-blue-600 text-white"
                  : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              }`}
            >
              {p === "7d" ? "7d" : p === "30d" ? "30d" : p === "90d" ? "90d" : p === "ytd" ? "YTD" : "All"}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-slate-700 mb-6 overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
        <nav className="flex gap-4 min-w-max md:min-w-0">
          {[
            { key: "overview", label: "Overview" },
            { key: "users", label: "Users" },
            { key: "spend", label: "Spend" },
            { key: "revenue", label: "Revenue" },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`px-4 py-2 border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.key
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Overview Tab */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard 
              title="Total Users" 
              value={formatNumber(overview.user_stats.total_users)} 
              onClick={() => openDrilldown("users", "Total Users", null)}
            />
            <KpiCard 
              title="Active (7d)" 
              value={formatNumber(overview.user_stats.active_7d)} 
              onClick={() => openDrilldown("active", "Active Users (7d)", 7)}
            />
            <KpiCard 
              title="Requests (24h)" 
              value={formatNumber(overview.system_health.total_requests_24h)} 
              onClick={() => openDrilldown("requests", "Requests (24h)", 1)}
            />
            <KpiCard 
              title="Deposits" 
              value={`$${overview.revenue_metrics.total_deposits_usd}`} 
              onClick={() => openDrilldown("deposits", "Total Deposits", null)}
            />
          </div>

          {/* System Health */}
          <div className="bg-slate-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">System Health (24h)</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <MetricRow 
                label="Requests" 
                value={formatNumber(overview.system_health.total_requests_24h)} 
                onClick={() => openDrilldown("requests", "System Requests (24h)", 1)}
              />
              <MetricRow 
                label="Spend" 
                value={`$${overview.system_health.total_spend_24h_usd}`} 
                onClick={() => openDrilldown("spend", "System Spend (24h)", 1)}
              />
              <MetricRow 
                label="Error Rate" 
                value={`${overview.system_health.error_rate.toFixed(2)}%`}
                valueClass={overview.system_health.error_rate > 5 ? "text-red-400" : "text-green-400"}
              />
              {overview.system_health.avg_latency_ms !== null && (
                <MetricRow label="Avg Latency" value={`${overview.system_health.avg_latency_ms.toFixed(0)}ms`} />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Users Tab */}
      {activeTab === "users" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <KpiCard 
              title="Total Users" 
              value={formatNumber(overview.user_stats.total_users)} 
              onClick={() => openDrilldown("users", "Total Users", null, null, null, null)}
            />
            <KpiCard 
              title="Signup Users" 
              value={formatNumber(overview.user_stats.signup_users)} 
              onClick={() => openDrilldown("users", "Signup Users", null, null, null, "signup")}
              subtitle="Registered only"
            />
            <KpiCard 
              title="Trial Users" 
              value={formatNumber(overview.user_stats.trial_users)} 
              onClick={() => openDrilldown("users", "Trial Users", null, null, null, "trial")}
              subtitle="Claimed trial"
            />
            <KpiCard 
              title="Paid Users" 
              value={formatNumber(overview.user_stats.paid_users)} 
              onClick={() => openDrilldown("users", "Paid Users", null, null, null, "paid")}
            />
            <KpiCard 
              title="Verified Users" 
              value={formatNumber(overview.user_stats.verified_users)} 
              onClick={() => openDrilldown("users", "Verified Users", null, null, null, "verified")}
            />
            <KpiCard 
              title="Active (7d)" 
              value={formatNumber(overview.user_stats.active_7d)} 
              onClick={() => openDrilldown("active", "Active Users (7d)", 7, null, null, null)}
            />
            <KpiCard 
              title="Active (30d)" 
              value={formatNumber(overview.user_stats.active_30d)} 
              onClick={() => openDrilldown("active", "Active Users (30d)", 30, null, null, null)}
            />
          </div>

          {/* Signup Trends */}
          <div className="bg-slate-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Signup Trends</h2>
            <div className="space-y-2">
              {signups.slice(0, 10).map((s) => (
                <div key={s.bucket} className="flex justify-between items-center py-2 border-b border-slate-700">
                  <span className="text-slate-300">{new Date(s.bucket).toLocaleDateString()}</span>
                  <button 
                    onClick={() => openDrilldown("users", `Signups on ${new Date(s.bucket).toLocaleDateString()}`, null, null, null, null, s.bucket.split('T')[0])}
                    className="text-blue-400 hover:text-blue-300 hover:underline font-semibold"
                  >
                    {s.count}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Spend Tab */}
      {activeTab === "spend" && (
        <div className="space-y-6">
          {/* Request Volume by Type */}
          <div className="bg-slate-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Request Volume by Type</h2>
            <div className="space-y-3">
              {requests.map((r) => (
                <div 
                  key={r.request_type} 
                  className="flex justify-between items-center py-3 border-b border-slate-700"
                >
                  <span className="text-slate-300 capitalize">{r.request_type}</span>
                  <div className="text-right">
                    <button 
                      onClick={() => openDrilldown("requests", `${r.request_type} Requests`, null, r.request_type, null)}
                      className="text-blue-400 hover:text-blue-300 hover:underline font-semibold"
                    >
                      {formatNumber(r.count)} requests →
                    </button>
                    <div className="text-slate-400 text-sm">${r.total_spend_usd}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Models */}
          <div className="bg-slate-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Top Models</h2>
            <div className="space-y-3">
              {models.map((m) => (
                <div key={m.model} className="flex justify-between items-center py-3 border-b border-slate-700">
                  <span className="text-slate-300 font-mono text-sm">{getModelDisplayName(m.model)}</span>
                  <div className="text-right">
                    <button 
                      onClick={() => openDrilldown("requests", `${getModelDisplayName(m.model)} Requests`, null, null, m.model)}
                      className="text-blue-400 hover:text-blue-300 hover:underline font-semibold"
                    >
                      {formatNumber(m.request_count)} requests
                    </button>
                    <div className="text-slate-400 text-sm">${m.total_spend_usd} (avg: ${m.avg_price_usd})</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Revenue Tab */}
      {activeTab === "revenue" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <KpiCard 
              title="Total Deposits" 
              value={`$${overview.revenue_metrics.total_deposits_usd}`} 
              onClick={() => openDrilldown("deposits", "Total Deposits by User", null)}
            />
            <KpiCard 
              title="Total Spend" 
              value={`$${overview.revenue_metrics.total_spend_usd}`} 
              onClick={() => openDrilldown("spend", "Total Spend by User", null)}
            />
            <KpiCard 
              title="ADPU" 
              value={`$${overview.revenue_metrics.average_deposits_per_user_usd}`} 
              subtitle="Average Deposits Per User" 
              onClick={() => openDrilldown("deposits", "Deposits Per User", null)}
            />
            <KpiCard 
              title="Net Balance" 
              value={`$${(parseFloat(overview.revenue_metrics.total_deposits_usd) - parseFloat(overview.revenue_metrics.total_spend_usd)).toFixed(2)}`}
              onClick={() => openDrilldown("balance", "Net Balance by User", null)}
            />
          </div>

          <div className="bg-slate-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Revenue Breakdown</h2>
            <div className="space-y-4">
              <MetricRow 
                label="Total Deposits" 
                value={`$${overview.revenue_metrics.total_deposits_usd}`}
                onClick={() => openDrilldown("deposits", "Total Deposits by User", null)}
              />
              <MetricRow 
                label="Total Spend" 
                value={`$${overview.revenue_metrics.total_spend_usd}`}
                onClick={() => openDrilldown("spend", "Total Spend by User", null)}
              />
              <MetricRow 
                label="Average per User" 
                value={`$${overview.revenue_metrics.average_deposits_per_user_usd}`}
                onClick={() => openDrilldown("deposits", "Deposits Per User", null)}
              />
            </div>
          </div>
        </div>
      )}

      {/* Drilldown Modal */}
      <UserDrilldownModal
        isOpen={drilldownOpen}
        onClose={() => setDrilldownOpen(false)}
        metric={drilldownMetric}
        metricLabel={drilldownLabel}
        days={drilldownDays}
        requestType={drilldownRequestType}
        model={drilldownModel}
        accountType={drilldownAccountType}
        signupDate={drilldownSignupDate}
      />
    </div>
  );
}

// Helper Components
function KpiCard({ 
  title, 
  value, 
  subtitle, 
  onClick 
}: { 
  title: string; 
  value: string; 
  subtitle?: string; 
  onClick?: () => void;
}) {
  return (
    <div className="bg-slate-800 rounded-lg p-6">
      <div className="text-slate-400 text-sm mb-1">{title}</div>
      <div className="text-2xl font-bold text-white">
        {onClick ? (
          <button 
            onClick={onClick} 
            className="text-blue-400 hover:text-blue-300 hover:underline transition-colors text-left"
          >
            {value}
          </button>
        ) : (
          value
        )}
      </div>
      {subtitle && <div className="text-slate-500 text-xs mt-1">{subtitle}</div>}
    </div>
  );
}

function MetricRow({ 
  label, 
  value, 
  subtitle, 
  valueClass, 
  onClick 
}: { 
  label: string; 
  value: string; 
  subtitle?: string; 
  valueClass?: string; 
  onClick?: () => void;
}) {
  return (
    <div className="flex justify-between items-center py-2">
      <span className="text-slate-300">{label}</span>
      <div className="text-right">
        <div className={`font-semibold ${valueClass || "text-blue-400"}`}>
          {onClick ? (
            <button 
              onClick={onClick} 
              className="hover:underline transition-colors"
            >
              {value}
            </button>
          ) : (
            value
          )}
        </div>
        {subtitle && <div className="text-slate-500 text-xs">{subtitle}</div>}
      </div>
    </div>
  );
}
