"use client";

import { useState } from "react";
import api from "@/lib/api";

type UserTrialInfo = {
  user_id: number;
  email: string;
  trial_enabled: boolean;
  trial_credits: number;
  real_credits: number;
  total_balance: number;
  calculated_balance: number;
};

export default function UserTrialManager() {
  const [query, setQuery] = useState("");
  const [users, setUsers] = useState<UserTrialInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingUser, setEditingUser] = useState<UserTrialInfo | null>(null);
  const [editForm, setEditForm] = useState({
    trial_enabled: false,
    trial_credits: 0,
    real_credits: 0,
    reconcile: false,
  });
  const [status, setStatus] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const search = async () => {
    if (!query) return;
    setLoading(true);
    setStatus(null);
    try {
      const res = await api.get<UserTrialInfo[]>(`/admin/users/search?q=${encodeURIComponent(query)}`);
      setUsers(res);
      if (res.length === 0) {
        setStatus({ type: "error", text: "No users found" });
      }
    } catch (e) {
      console.error(e);
      setStatus({ type: "error", text: "Search failed" });
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (u: UserTrialInfo) => {
    setEditingUser(u);
    setSaveError(null);
    setEditForm({
      trial_enabled: u.trial_enabled,
      trial_credits: u.trial_credits / 100,
      real_credits: u.real_credits / 100,
      reconcile: false,
    });
  };

  const save = async () => {
    if (!editingUser) return;
    setSaveError(null);
    try {
      await api.post(`/admin/users/${editingUser.user_id}/trial-state`, {
        ...editForm,
        trial_credits: Math.round(editForm.trial_credits * 100),
        real_credits: Math.round(editForm.real_credits * 100),
      });
      setStatus({ type: "success", text: "User updated successfully" });
      setEditingUser(null);
      search(); // Refresh
    } catch (e) {
      console.error(e);
      setSaveError("Save failed. Please check the logs.");
    }
  };

  const formatUSD = (cents: number) => {
    return (cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
  };

  return (
    <div className="rounded border border-slate-700 p-3 mt-4">
      <h2 className="text-xl font-semibold mb-4 text-white">User Trial Manager</h2>
      
      {status && (
        <div className={`mb-4 p-2 rounded ${status.type === 'success' ? 'bg-green-900/50 text-green-200 border border-green-800' : 'bg-red-900/50 text-red-200 border border-red-800'}`}>
          {status.text}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Email or User ID"
          className="w-full rounded border border-slate-700 bg-transparent p-2 text-white"
          onKeyDown={(e) => e.key === 'Enter' && search()}
        />
        <button onClick={search} disabled={loading} className="rounded bg-blue-600 px-4 py-2 text-white">
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      <div className="space-y-2">
        {users.map((u) => (
          <div key={u.user_id} className="border border-slate-700 p-2 rounded flex justify-between items-center text-white">
            <div>
              <div className="font-bold">{u.email} (ID: {u.user_id})</div>
              <div className="text-sm text-slate-400">
                Trial: {u.trial_enabled ? "Enabled" : "Disabled"} | 
                Trial Credits: {formatUSD(u.trial_credits)} | 
                Real Credits: {formatUSD(u.real_credits)} | 
                Total: {formatUSD(u.total_balance)}
                {u.calculated_balance !== u.total_balance && (
                  <span className="text-red-400 ml-2 font-bold">
                    (Calc: {formatUSD(u.calculated_balance)})
                  </span>
                )}
              </div>
            </div>
            <button onClick={() => startEdit(u)} className="bg-slate-700 px-3 py-1 rounded text-white hover:bg-slate-600">
              Edit
            </button>
          </div>
        ))}
      </div>

      {editingUser && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-slate-800 p-6 rounded shadow-lg w-96 text-white border border-slate-700">
            <h3 className="text-lg font-bold mb-4">Edit User {editingUser.email}</h3>
            
            {editingUser.calculated_balance !== editingUser.total_balance && (
               <div className="mb-4 p-2 bg-yellow-900/30 border border-yellow-700 rounded text-sm text-yellow-200">
                 Warning: Stored balance ({formatUSD(editingUser.total_balance)}) differs from calculated history ({formatUSD(editingUser.calculated_balance)}).
                 <button 
                   onClick={() => setEditForm({
                     ...editForm, 
                     real_credits: (editingUser.calculated_balance - (editForm.trial_enabled ? editForm.trial_credits * 100 : 0)) / 100,
                     reconcile: true
                   })}
                   className="ml-2 underline hover:text-yellow-100"
                 >
                   Fix Real Credits
                 </button>
               </div>
            )}

            <div className="mb-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editForm.trial_enabled}
                  onChange={(e) => setEditForm({ ...editForm, trial_enabled: e.target.checked })}
                  className="rounded border-slate-600 bg-slate-700"
                />
                Trial Enabled
              </label>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-bold mb-1 text-slate-300">Trial Credits (USD)</label>
              <input
                type="number"
                step="0.01"
                value={editForm.trial_credits}
                onChange={(e) => setEditForm({ ...editForm, trial_credits: parseFloat(e.target.value) || 0 })}
                className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white"
              />
            </div>

            <div className="mb-4">
              <label className="block text-sm font-bold mb-1 text-slate-300">Real Credits (USD)</label>
              <input
                type="number"
                step="0.01"
                value={editForm.real_credits}
                onChange={(e) => setEditForm({ ...editForm, real_credits: parseFloat(e.target.value) || 0 })}
                className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white"
              />
            </div>

            {saveError && (
              <div className="mb-4 p-2 rounded bg-red-900/50 text-red-200 border border-red-800 text-sm">
                {saveError}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button onClick={() => setEditingUser(null)} className="bg-slate-600 px-4 py-2 rounded hover:bg-slate-500">
                Cancel
              </button>
              <button onClick={save} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-500">
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
