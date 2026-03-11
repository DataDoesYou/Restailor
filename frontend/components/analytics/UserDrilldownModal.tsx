"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface UserDrilldownData {
  user_email: string;
  user_id: number;
  request_count: number;
  total_amount_usd: string;
  last_activity: string | null;
  account_type: string;
}

interface UserDrilldownModalProps {
  isOpen: boolean;
  onClose: () => void;
  metric: "requests" | "spend" | "active" | "deposits" | "balance" | "users";
  metricLabel: string;
  days: number | null;
  requestType?: string | null;
  model?: string | null;
  accountType?: string | null;
  signupDate?: string | null;
}

export function UserDrilldownModal({
  isOpen,
  onClose,
  metric,
  metricLabel,
  days,
  requestType,
  model,
  accountType,
  signupDate,
}: UserDrilldownModalProps) {
  const [data, setData] = useState<UserDrilldownData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<keyof UserDrilldownData>("request_count");
  const [sortDesc, setSortDesc] = useState(true);

  useEffect(() => {
    if (!isOpen) return;

    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.append("metric", metric);
        if (days !== null) params.append("days", days.toString());
        if (requestType) params.append("request_type", requestType);
        if (model) params.append("model", model);
        if (accountType) params.append("account_type", accountType);
        if (signupDate) params.append("signup_date", signupDate);
        
        const url = `/admin/analytics/drilldown/users?${params.toString()}`;
        
        console.log('[UserDrilldownModal] Fetching:', url);
        const result = await api.get<UserDrilldownData[]>(url);
        console.log('[UserDrilldownModal] Result:', result);
        setData(result);
      } catch (e: any) {
        console.error('[UserDrilldownModal] Error:', e);
        const errorMsg = e?.message || e?.detail || "Failed to load drilldown data";
        setError(errorMsg);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [isOpen, metric, days, requestType, model, accountType, signupDate]);

  if (!isOpen) return null;

  const handleSort = (field: keyof UserDrilldownData) => {
    if (sortField === field) {
      setSortDesc(!sortDesc);
    } else {
      setSortField(field);
      setSortDesc(true);
    }
  };

  const sortedData = [...data].sort((a, b) => {
    const aVal = a[sortField];
    const bVal = b[sortField];
    
    // Special handling for last_activity to put nulls at the end
    if (sortField === "last_activity") {
      if (aVal === null && bVal === null) return 0;
      if (aVal === null) return 1; // null always goes to the end
      if (bVal === null) return -1; // null always goes to the end
    }
    
    let comparison = 0;
    if (typeof aVal === "number" && typeof bVal === "number") {
      comparison = aVal - bVal;
    } else if (typeof aVal === "string" && typeof bVal === "string") {
      comparison = aVal.localeCompare(bVal);
    }
    
    return sortDesc ? -comparison : comparison;
  });

  const formatDate = (isoString: string | null) => {
    if (!isoString) return "N/A";
    return new Date(isoString).toLocaleString();
  };

  const getAccountBadgeColor = (type: string) => {
    switch (type) {
      case "admin": return "bg-purple-600 text-white";
      case "paid": return "bg-green-600 text-white";
      case "trial": return "bg-amber-600 text-white";
      case "signup": return "bg-cyan-600 text-white";
      default: return "bg-slate-600 text-slate-300";
    }
  };

  const SortIcon = ({ field }: { field: keyof UserDrilldownData }) => {
    if (sortField !== field) return <span className="text-slate-600">⇅</span>;
    return <span>{sortDesc ? "↓" : "↑"}</span>;
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg max-w-6xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex justify-between items-start">
          <h2 className="text-2xl font-bold">
            {metricLabel} - User Breakdown
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-2xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {loading && (
            <div className="text-slate-400">Loading drilldown data...</div>
          )}

          {error && (
            <div className="text-red-400">Error: {error}</div>
          )}

          {!loading && !error && data.length === 0 && (
            <div className="text-slate-400">No data available</div>
          )}

          {!loading && !error && data.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th
                      className="text-left p-3 cursor-pointer hover:bg-slate-700"
                      onClick={() => handleSort("user_email")}
                    >
                      Email <SortIcon field="user_email" />
                    </th>
                    <th
                      className="text-left p-3 cursor-pointer hover:bg-slate-700"
                      onClick={() => handleSort("account_type")}
                    >
                      Type <SortIcon field="account_type" />
                    </th>
                    <th
                      className="text-right p-3 cursor-pointer hover:bg-slate-700"
                      onClick={() => handleSort("request_count")}
                    >
                      Requests <SortIcon field="request_count" />
                    </th>
                    <th
                      className="text-right p-3 cursor-pointer hover:bg-slate-700"
                      onClick={() => handleSort("total_amount_usd")}
                    >
                      {metric === "deposits" ? "Deposits" : metric === "balance" ? "Balance" : "Spend"} <SortIcon field="total_amount_usd" />
                    </th>
                    <th
                      className="text-left p-3 cursor-pointer hover:bg-slate-700"
                      onClick={() => handleSort("last_activity")}
                    >
                      Last Activity <SortIcon field="last_activity" />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedData.map((row) => (
                    <tr
                      key={row.user_id}
                      className="border-b border-slate-700 hover:bg-slate-750"
                    >
                      <td className="p-3 font-mono text-sm">{row.user_email}</td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs ${getAccountBadgeColor(row.account_type)}`}>
                          {row.account_type}
                        </span>
                      </td>
                      <td className="p-3 text-right">{row.request_count.toLocaleString()}</td>
                      <td className="p-3 text-right">${row.total_amount_usd}</td>
                      <td className="p-3 text-sm text-slate-400">{formatDate(row.last_activity)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-700">
          <div className="text-slate-400 text-sm">
            Showing {sortedData.length} users
          </div>
        </div>
      </div>
    </div>
  );
}
