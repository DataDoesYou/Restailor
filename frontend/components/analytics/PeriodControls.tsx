"use client";

import React from "react";

type Bucket = "day" | "week" | "month";

export function PeriodControls(props: {
  period: string;
  setPeriod: (p: string) => void;
  from?: string | null;
  to?: string | null;
  setFrom?: (v: string | null) => void;
  setTo?: (v: string | null) => void;
  bucket: Bucket;
  setBucket: (b: Bucket) => void;
  loading?: boolean;
}) {
  const { period, setPeriod, from, to, setFrom, setTo, bucket, setBucket } = props;
  return (
    <>
      {/* Desktop layout - horizontal */}
      <div className="hidden md:flex items-center gap-3" aria-label="Analytics period controls">
        <div
          className="inline-flex rounded-md border border-outline-var p-1 bg-[var(--accent)] sticky-controls"
          role="group"
          aria-label="Select date period"
        >
          {[
            {key: "7d", label: "7d"},
            {key: "30d", label: "30d"},
            {key: "90d", label: "90d"},
            {key: "ytd", label: "YTD"},
            {key: "all", label: "All"},
          ].map(p => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPeriod(p.key)}
              aria-pressed={period === p.key}
              aria-label={`Set period to ${p.label}`}
              className={
                "px-3 py-1 text-sm rounded-md text-foreground " +
                (period === p.key
                  ? "bg-[var(--chart-1)] text-black font-bold"
                  : "bg-[var(--accent)] hover:bg-[var(--muted)]")
              }
            >{p.label}</button>
          ))}
        </div>

        <select
          className="border border-outline-var rounded-md px-2 py-1 text-sm bg-[var(--accent)] text-foreground"
          value={bucket}
          onChange={e => setBucket(e.target.value as Bucket)}
          id="bucket-select"
          aria-label="Select bucket size"
        >
          <option value="day">Daily</option>
          <option value="week">Weekly</option>
          <option value="month">Monthly</option>
        </select>
      </div>
      {/* Mobile layout - vertical stack */}
      <div className="md:hidden space-y-3 w-full" aria-label="Analytics period controls">
        <div
          className="grid grid-cols-5 gap-2 w-full"
          role="group"
          aria-label="Select date period"
        >
          {[
            {key: "7d", label: "7d"},
            {key: "30d", label: "30d"},
            {key: "90d", label: "90d"},
            {key: "ytd", label: "YTD"},
            {key: "all", label: "All"},
          ].map(p => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPeriod(p.key)}
              aria-pressed={period === p.key}
              aria-label={`Set period to ${p.label}`}
              className={
                "px-2 py-2 text-base rounded-md text-foreground border " +
                (period === p.key
                  ? "bg-[var(--chart-1)] text-black font-bold border-[var(--chart-1)]"
                  : "bg-[var(--accent)] border-outline-var active:bg-[var(--muted)]")
              }
            >{p.label}</button>
          ))}
        </div>

        <select
          className="border border-outline-var rounded-md px-3 py-2 text-base bg-[var(--accent)] text-foreground w-full"
          value={bucket}
          onChange={e => setBucket(e.target.value as Bucket)}
          id="bucket-select-mobile"
          aria-label="Select bucket size"
        >
          <option value="day">Daily</option>
          <option value="week">Weekly</option>
          <option value="month">Monthly</option>
        </select>
      </div>
    </>
  );
}
