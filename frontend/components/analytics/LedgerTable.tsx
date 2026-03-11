"use client";

import React from "react";

export interface LedgerRow { id?: string; created_at: string; delta_cents: number; type?: string; note?: string; provider_ref?: string }

export function LedgerTable({ rows, onViewAll }: { rows: LedgerRow[]; onViewAll?: () => void }) {
  const fmtUsd = (n: number) => `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  // Filter to deposits only
  const deposits = (rows || []).filter(r => (r.delta_cents || 0) > 0);
  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto rounded-md border border-outline-var">
        <table className="min-w-full text-sm text-foreground">
          <thead className="bg-[var(--accent)] text-legend">
            <tr>
              <th className="text-left px-3 py-2">Date</th>
              <th className="text-left px-3 py-2">Deposit ($)</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Note</th>
              <th className="text-left px-3 py-2">Ref</th>
            </tr>
          </thead>
          <tbody>
            {deposits.map((r, i) => (
              <tr key={(r.id || String(i))} className={i % 2 ? "bg-[var(--accent)]" : "bg-transparent"}>
                <td className="px-3 py-2 whitespace-nowrap">{new Date(r.created_at).toLocaleString()}</td>
                <td className="px-3 py-2">{fmtUsd((r.delta_cents || 0) / 100.0)}</td>
                <td className="px-3 py-2">{r.type || ""}</td>
                <td className="px-3 py-2">{r.note || ""}</td>
                <td className="px-3 py-2">{r.provider_ref || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="p-3 flex justify-end">
          <button onClick={onViewAll} className="text-sm px-3 py-1 rounded border border-outline-var bg-[var(--accent)] hover:bg-[var(--muted)]">
            View all
          </button>
        </div>
      </div>
      {/* Mobile card layout */}
      <div className="md:hidden space-y-3">
        {deposits.map((r, i) => (
          <div key={(r.id || String(i))} className="rounded-md border border-outline-var bg-[var(--accent)] p-4">
            <div className="flex justify-between items-start mb-2">
              <div className="text-xs text-legend">{new Date(r.created_at).toLocaleString()}</div>
              <div className="text-lg font-semibold text-foreground">{fmtUsd((r.delta_cents || 0) / 100.0)}</div>
            </div>
            {(r.type || r.note || r.provider_ref) && (
              <div className="space-y-1 text-sm text-foreground/80">
                {r.type && <div><span className="text-legend">Type:</span> {r.type}</div>}
                {r.note && <div><span className="text-legend">Note:</span> {r.note}</div>}
                {r.provider_ref && <div><span className="text-legend">Ref:</span> {r.provider_ref}</div>}
              </div>
            )}
          </div>
        ))}
        <div className="flex justify-end">
          <button onClick={onViewAll} className="text-base px-4 py-2 rounded border border-outline-var bg-[var(--accent)] active:bg-[var(--muted)]">
            View all
          </button>
        </div>
      </div>
    </>
  );
}
