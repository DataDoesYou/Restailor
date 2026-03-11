"use client";

import React from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell, LineChart, Line, Sankey, AreaChart, Area } from "recharts";

// Shared helpers
const BASE_FONT_SIZE = 16; // px – standardized tooltip/legend font size
const tooltipStyle = {
  backgroundColor: 'var(--chart-tooltip-bg)',
  color: 'var(--chart-tooltip-fg)',
  borderColor: 'var(--chart-tooltip-border)',
  fontSize: BASE_FONT_SIZE,
} as const;
const tooltipItemStyle = { color: 'var(--chart-tooltip-fg)', fontSize: BASE_FONT_SIZE } as const;
const tooltipLabelStyle = { color: 'var(--chart-tooltip-fg)', fontSize: BASE_FONT_SIZE } as const;
const legendStyle = { color: 'var(--chart-legend)', fontSize: BASE_FONT_SIZE } as const;
const fmtInt = (v: any) => Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 });

const DONUT_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)'
];

function dateOnlyLabel(v: unknown): string {
  const s = String(v || "");
  const m = s.match(/^\d{4}-\d{2}-\d{2}/);
  if (m) return m[0];
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  return s;
}

export function FunnelBar({ stages, counts }: { stages: string[]; counts: Record<string, number> }) {
  // Build a sequential left-to-right Sankey: applied -> interviewing -> offer -> hired
  // Without transition counts, we approximate each link's value conservatively as min(current, next).
  const canonical = ["applied", "interviewing", "offer", "hired"] as const;
  // Show all canonical stages in order, even if some are missing from `stages` input
  const nodeNames = [...canonical];
  // Normalize count keys to lowercase for robustness
  const lcCounts: Record<string, number> = Object.fromEntries(
    Object.entries(counts || {}).map(([k, v]) => [String(k).toLowerCase(), Math.max(0, Number(v) || 0)])
  );
  const [normalized, setNormalized] = React.useState(false);
  const nodes = nodeNames.map((name) => ({ name }));
  type LinkShape = { source: number; target: number; value: number; valueAbs: number; valuePct: number };
  const links: Array<LinkShape> = [];
  const EPS = 0.0001; // tiny value to keep columns visible when upstream is 0
  let anyCount = 0;
  let prev = lcCounts[nodeNames[0]] || 0; // start from 'applied'
  anyCount += prev;
  const appliedBase = prev; // use Applied as the normalization base
  for (let i = 0; i < nodeNames.length - 1; i++) {
    const nextCount = lcCounts[nodeNames[i + 1]] || 0;
    anyCount += nextCount;
    // cascade forward: flow cannot exceed previous link value
    const flow = Math.min(prev, nextCount);
    const vAbs = flow > 0 ? flow : (prev > 0 || nextCount > 0 ? EPS : 0);
    const vPct = appliedBase > 0 ? (vAbs / appliedBase) * 100 : 0;
    if (vAbs > 0) links.push({ source: i, target: i + 1, value: normalized ? vPct : vAbs, valueAbs: vAbs, valuePct: vPct });
    prev = flow; // next step cannot exceed current flow
  }
  // If toggle changes after initial link build, map value to match selection
  const data = {
    nodes,
    links: links.map(l => ({ ...l, value: normalized ? l.valuePct : l.valueAbs }))
  } as const;

  const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
  const SankeyTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;
    const p = payload[0]?.payload || {};
    const src = p?.source?.name ? title(p.source.name) : '';
    const tgt = p?.target?.name ? title(p.target.name) : '';
    const valAbs = typeof p?.valueAbs === 'number' ? p.valueAbs : (p?.value ?? 0);
    const valPct = typeof p?.valuePct === 'number' ? p.valuePct : 0;
    return (
      <div style={tooltipStyle as React.CSSProperties} className="px-2 py-1 rounded border">
        <div className="text-base" style={{ color: 'var(--chart-tooltip-fg)' }}>
          {src && tgt ? `${src} → ${tgt}` : 'Flow'}: {fmtInt(valAbs)}{normalized ? ` (${valPct.toFixed(1)}%)` : ''}
        </div>
      </div>
    );
  };
  const NodeRenderer = (props: any) => {
    const { x, y, width, height, payload } = props;
    const name: string = payload?.name || "";
    const count = lcCounts[name.toLowerCase()] || 0;
    const idx = ["applied","interviewing","offer","hired"].indexOf(name.toLowerCase());
    const nodeColors = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)'];
    const fillColor = nodeColors[Math.max(0, idx)] || 'var(--chart-1)';
    return (
      <g>
        <rect x={x} y={y} width={width} height={height} fill={fillColor} stroke={'var(--chart-grid)'} />
        <text x={x + width + 8} y={y + height / 2} fill={'var(--chart-axis)'} fontSize={12} dominantBaseline="middle">
          {title(name)} ({fmtInt(count)})
        </text>
      </g>
    );
  };

  return (
    <div className="w-full h-80" role="img" aria-label="Active funnel (Sankey: Applied → Interviewing → Offer → Hired)" tabIndex={0}>
      <div className="flex justify-end text-xs text-foreground/70 px-1 pb-1 select-none gap-2">
        <label className="inline-flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            className="accent-current"
            checked={normalized}
            onChange={(e) => setNormalized(e.target.checked)}
            disabled={appliedBase <= 0}
            aria-label="Normalize link widths by percent of Applied"
          />
          <span>Normalize %</span>
        </label>
      </div>
      <div className="flex justify-between text-xs text-foreground/70 px-1 pb-1 select-none">
        <span>Applied</span>
        <span>Interviewing</span>
        <span>Offer</span>
        <span>Hired</span>
      </div>
      {anyCount > 0 ? (
        <ResponsiveContainer width="100%" height="100%">
          <Sankey
            data={data}
            nodePadding={28}
            nodeWidth={28}
            nodeAlign="justify"
            margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
            node={<NodeRenderer />}
            link={{ stroke: 'var(--chart-2)', strokeOpacity: 0.6, fill: 'var(--chart-2)', fillOpacity: 0.35 }}
          >
            <Tooltip content={<SankeyTooltip />} />
            <Legend wrapperStyle={legendStyle as React.CSSProperties} iconSize={10} />
          </Sankey>
        </ResponsiveContainer>
      ) : (
        <div className="h-full flex items-center justify-center text-sm text-foreground">
          No active funnel data for this period
        </div>
      )}
    </div>
  );
}

export function HiredClosedDonut({ hired, closed }: { hired: number; closed: number }) {
  const data = [
    { name: 'Hired', value: hired || 0 },
    { name: 'Archived', value: closed || 0 },
  ];
  return (
    <div className="w-full h-64" role="img" aria-label="Hired vs Archived" tabIndex={0}>
      <ResponsiveContainer>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={2}>
            {data.map((_, i) => <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} separator=": " formatter={(v: any, n: any) => [fmtInt(v), String(n)]} />
          <Legend wrapperStyle={legendStyle as React.CSSProperties} iconSize={10} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CohortRings({ totals }: { totals: { snapshots: number; applied: number; interviewing: number; offer: number; hired: number } }) {
  // Single source of truth: flags are cumulative (hired implies offer/interviewing)
  // Don't clamp to previous values - each flag can have its own count
  let s = Math.max(0, totals.snapshots || 0);
  let a = Math.min(Math.max(0, totals.applied || 0), s);  // Still clamp to total snapshots
  let i = Math.min(Math.max(0, totals.interviewing || 0), s);  // Clamp to snapshots, not applied
  let o = Math.min(Math.max(0, totals.offer || 0), s);  // Clamp to snapshots, not interviewing
  let h = Math.min(Math.max(0, totals.hired || 0), s);  // Clamp to snapshots, not offer
  const remainderColor = 'var(--chart-grid)';

  const ringDefs = [
    { key: 'snapshots', label: 'Snapshots', value: s, color: 'var(--chart-2)' },
    { key: 'applied', label: 'Applied', value: a, color: 'var(--chart-1)' },
    { key: 'interviewing', label: 'Interviewing', value: i, color: 'var(--chart-3)' },
    { key: 'offer', label: 'Offer', value: o, color: 'var(--chart-4)' },
    { key: 'hired', label: 'Hired', value: h, color: 'var(--chart-5)' },
  ] as const;

  if (s <= 0) {
    return (
      <div className="w-full h-64 flex items-center justify-center text-sm text-foreground/70 border border-outline-var rounded" role="status" aria-live="polite">
        No snapshots in this period
      </div>
    );
  }

  // Concentric rings: outermost = Snapshots (100%), innermost = Hired
  const baseOuter = 100; // px radius baseline used by Recharts
  const ringWidth = 10;
  const gap = 2;

  // Helper to build ring data (embed ring label for tooltip clarity)
  const ringData = (ringLabel: string, ringKey: string, filled: number) => ([
    { name: ringLabel, value: Math.max(0, filled), ringLabel, ringKey, total: s, isFilled: true },
    { name: 'Remaining', value: Math.max(0, s - filled), ringLabel, ringKey, total: s, isFilled: false },
  ]);

  const LegendList = () => (
    <div className="flex flex-col gap-2" style={{ fontSize: BASE_FONT_SIZE }} aria-hidden="true">
      {ringDefs.map((r) => {
        const pct = s > 0 ? (r.value / s) * 100 : 0;
        return (
          <div key={r.key} className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: r.color as any }} />
            <span className="text-foreground/80">{r.label}</span>
            <span className="ml-auto tabular-nums text-foreground/70">{fmtInt(r.value)}{s > 0 ? ` (${pct.toFixed(0)}%)` : ''}</span>
          </div>
        );
      })}
    </div>
  );

  // Custom tooltip that hides "Remaining" slices and shows values only for filled segments
  const RingsTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;
    const p = payload[0]?.payload || {};
    if (!p.isFilled) return null; // suppress gray remainder tooltips
    const total = Number(p.total || s || 0);
    const val = Number(payload[0]?.value || 0);
    const label = String(p.ringLabel || payload[0]?.name || '');
    const pct = total > 0 ? (val / total) * 100 : 0;
    return (
      <div style={tooltipStyle as React.CSSProperties} className="px-2 py-1 rounded border">
        <div style={{ color: 'var(--chart-tooltip-fg)', fontSize: BASE_FONT_SIZE }}>
          {label}: {fmtInt(val)} ({pct.toFixed(0)}%)
        </div>
      </div>
    );
  };

  return (
    <div className="w-full md:flex md:flex-row md:items-center md:gap-6" role="img" aria-label="Snapshots ⊇ Applied ⊇ Interviewing ⊇ Offer ⊇ Hired (concentric rings)">
      <div className="flex-1 min-w-0 h-64">
        <ResponsiveContainer>
          <PieChart>
          {ringDefs.map((r, idx) => {
            const outer = baseOuter - idx * (ringWidth + gap);
            const inner = outer - ringWidth;
            const data = ringData(r.label, r.key, r.value);
            return (
              <Pie
                key={r.key}
                data={data}
                dataKey="value"
                nameKey="name"
                startAngle={90}
                endAngle={-270}
                innerRadius={inner}
                outerRadius={outer}
                stroke={"var(--chart-bg)"}
                strokeWidth={1}
                isAnimationActive={false}
              >
                <Cell fill={r.color} />
                <Cell fill={remainderColor} />
              </Pie>
            );
          })}
          <Tooltip content={<RingsTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 md:mt-0 md:w-auto">
        <LegendList />
      </div>
    </div>
  );
}

export function ClosuresLine({ rows }: { rows: { bucket: string; count: number }[] }) {
  const maxVal = Math.max(0, ...rows.map(r => r.count || 0));
  const ticks = (() => {
    if (maxVal <= 0) return [0, 1];
    const step = Math.max(1, Math.round(maxVal / 4));
    const arr: number[] = [];
    for (let v = 0; v <= Math.ceil(maxVal / step) * step; v += step) arr.push(v);
    return arr;
  })();
  return (
    <div className="w-full h-64" role="img" aria-label="Archived per week" tabIndex={0}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={ticks} domain={[ticks[0], ticks[ticks.length-1]]} />
          <Tooltip cursor={{ stroke: 'var(--chart-cursor-line)' }} contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} separator=": " formatter={(v: any) => [fmtInt(v), 'Archived']} labelFormatter={(l: any) => dateOnlyLabel(l)} />
          <Legend wrapperStyle={legendStyle as React.CSSProperties} iconSize={10} />
          <Line type="monotone" dataKey="count" stroke={'var(--chart-2)'} dot={false} name="Archived" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AppliedBar({ rows, bucketLabel }: { rows: { bucket: string; applied: number }[]; bucketLabel?: 'day' | 'week' | 'month' }) {
  const maxVal = Math.max(0, ...rows.map(r => (r.applied || 0)));
  const ticks = (() => {
    if (maxVal <= 0) return [0, 1];
    const step = Math.max(1, Math.round(maxVal / 4));
    const arr: number[] = [];
    for (let v = 0; v <= Math.ceil(maxVal / step) * step; v += step) arr.push(v);
    return arr;
  })();
  const name = 'Applied';
  const bucketText = bucketLabel === 'week' ? 'week' : bucketLabel === 'month' ? 'month' : 'day';
  return (
    <div className="w-full h-64" role="img" aria-label={`Applied per ${bucketText}`} tabIndex={0}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={ticks} domain={[ticks[0], ticks[ticks.length-1]]} />
          <Tooltip cursor={{ fill: 'var(--chart-cursor-fill)' }} contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} separator=": " formatter={(v: any) => [fmtInt(v), name]} labelFormatter={(l: any) => dateOnlyLabel(l)} />
          <Legend wrapperStyle={legendStyle as React.CSSProperties} iconSize={10} />
          <Bar dataKey="applied" name={name} fill={'var(--chart-1)'} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SnapshotsAppliedArea({ rows }: { rows: { bucket: string; snapshots: number; applied: number; interviewing?: number; offer?: number; hired?: number }[] }) {
  const maxVal = Math.max(0, ...rows.map(r => Math.max(r.snapshots || 0, r.applied || 0, r.interviewing || 0, r.offer || 0, r.hired || 0)));
  const ticks = (() => {
    if (maxVal <= 0) return [0, 1];
    const step = Math.max(1, Math.round(maxVal / 4));
    const arr: number[] = [];
    for (let v = 0; v <= Math.ceil(maxVal / step) * step; v += step) arr.push(v);
    return arr;
  })();
  return (
    <div className="w-full h-72" role="img" aria-label="Daily snapshots vs applied" tabIndex={0}>
      <ResponsiveContainer>
        <AreaChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={ticks} domain={[ticks[0], ticks[ticks.length-1]]} />
          <Tooltip
            cursor={{ stroke: 'var(--chart-cursor-line)' }}
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            separator=": "
            formatter={(v: any, n: any, item: any) => {
              const key = item?.dataKey as string;
              const name = key === 'snapshots' ? 'Snapshots'
                : key === 'applied' ? 'Applied'
                : key === 'interviewing' ? 'Interviewing'
                : key === 'offer' ? 'Offer'
                : key === 'hired' ? 'Hired'
                : n;
              return [fmtInt(v), name];
            }}
            labelFormatter={(l: any) => dateOnlyLabel(l)}
          />
          <Legend wrapperStyle={legendStyle as React.CSSProperties} iconSize={10} />
          <Area type="monotone" dataKey="snapshots" name="Snapshots" stroke={'var(--chart-2)'} fill={'var(--chart-2)'} fillOpacity={0.2} />
          <Area type="monotone" dataKey="applied" name="Applied" stroke={'var(--chart-1)'} fill={'var(--chart-1)'} fillOpacity={0.3} />
          <Area type="monotone" dataKey="interviewing" name="Interviewing" stroke={'var(--chart-3)'} fill={'var(--chart-3)'} fillOpacity={0.25} />
          <Area type="monotone" dataKey="offer" name="Offer" stroke={'var(--chart-4)'} fill={'var(--chart-4)'} fillOpacity={0.25} />
          <Area type="monotone" dataKey="hired" name="Hired" stroke={'var(--chart-5)'} fill={'var(--chart-5)'} fillOpacity={0.25} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
