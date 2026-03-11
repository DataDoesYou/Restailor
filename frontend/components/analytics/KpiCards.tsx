"use client";

import React from "react";

export function KpiCards(props: { items: { label: string; value: string | number; hint?: string }[] }) {
  const items = props.items || [];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {items.map((it, idx) => (
  <div key={idx} className="rounded-lg border border-outline-var bg-[var(--accent)] p-4 shadow-sm">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{it.label}</div>
          <div className="mt-1 text-2xl font-semibold text-foreground">{it.value}</div>
          {it.hint && <div className="text-xs text-muted-foreground mt-1">{it.hint}</div>}
        </div>
      ))}
    </div>
  );
}
