"use client";

import { useEffect, useState } from "react";
import api, { ApiError } from "@/lib/api";

interface CheckboxState {
  is_checked: boolean;
  updated_at: string | null;
}

export default function DBTestPage() {
  const [isChecked, setIsChecked] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  // Load checkbox state on mount
  useEffect(() => {
    const loadCheckboxState = async () => {
      try {
        const resp = await api.get<CheckboxState>("/test-checkbox");
        setIsChecked(resp.is_checked);
        setLastUpdated(resp.updated_at);
        setError(null);
      } catch (e) {
        const err = e as ApiError;
        if (err.status === 401) {
          setError("Please log in to use this feature");
        } else {
          setError("Failed to load checkbox state");
        }
      } finally {
        setLoading(false);
      }
    };

    loadCheckboxState();
  }, []);

  // Handle checkbox toggle
  const handleToggle = async (newValue: boolean) => {
    // Optimistically update UI
    setIsChecked(newValue);
    setSaving(true);
    setError(null);

    try {
      const resp = await api.put<CheckboxState>("/test-checkbox", {
        is_checked: newValue,
      });
      setIsChecked(resp.is_checked);
      setLastUpdated(resp.updated_at);
    } catch (e) {
      const err = e as ApiError;
      // Revert on error
      setIsChecked(!newValue);
      if (err.status === 401) {
        setError("Please log in to save changes");
      } else {
        setError("Failed to save checkbox state");
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-300">
        <div className="rounded-lg bg-slate-800 p-8 shadow-lg">
          <p className="text-lg">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-300">
      <div className="w-full max-w-md rounded-lg bg-slate-800 p-8 shadow-lg">
        <h1 className="mb-6 text-2xl font-semibold text-white">DB Test Page</h1>
        
        <div className="space-y-4">
          <p className="text-sm text-slate-400">
            This page demonstrates a checkbox that persists its state to the database,
            similar to the Steam wishlist checkbox functionality.
          </p>

          <div className="rounded-lg bg-slate-700 p-6">
            <label className="flex cursor-pointer items-center space-x-3">
              <input
                type="checkbox"
                checked={isChecked}
                onChange={(e) => handleToggle(e.target.checked)}
                disabled={saving}
                className="h-5 w-5 rounded border-slate-600 bg-slate-600 text-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <span className="text-lg font-medium">
                Test Checkbox {saving && "(saving...)"}
              </span>
            </label>

            {lastUpdated && (
              <p className="mt-3 text-xs text-slate-400">
                Last updated: {new Date(lastUpdated).toLocaleString()}
              </p>
            )}
          </div>

          {error && (
            <div className="rounded-lg bg-red-900/30 p-4 text-red-400">
              <p className="text-sm">{error}</p>
            </div>
          )}

          <div className="rounded-lg bg-slate-700 p-4">
            <h3 className="mb-2 font-semibold text-white">Current State:</h3>
            <p className="font-mono text-sm">
              is_checked: <span className="text-blue-400">{isChecked ? "true" : "false"}</span>
            </p>
          </div>

          <div className="text-sm text-slate-400">
            <p className="font-semibold">How it works:</p>
            <ul className="mt-2 list-inside list-disc space-y-1">
              <li>Checkbox state loads from the database on page load</li>
              <li>Toggling the checkbox immediately saves to the database</li>
              <li>State persists across page refreshes and sessions</li>
              <li>Each user has their own independent checkbox state</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
