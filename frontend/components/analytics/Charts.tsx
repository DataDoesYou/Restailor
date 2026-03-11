"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell } from "recharts";
import { MODEL_OPTIONS, findModelByModelId } from "@/components/resume/models";

// Format any bucket/date-like value to a date-only string (YYYY-MM-DD) without time
function dateOnlyLabel(v: unknown): string {
  const s = String(v || "");
  // Try to match leading YYYY-MM-DD from ISO or space-separated strings
  const m = s.match(/^\d{4}-\d{2}-\d{2}/);
  if (m) return m[0];
  // Fallback: attempt Date parse and reformat; guard invalid Date
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  return s;
}

const tooltipStyle = {
  backgroundColor: 'var(--chart-tooltip-bg)',
  color: 'var(--chart-tooltip-fg)',
  borderColor: 'var(--chart-tooltip-border)'
} as const;

// Number formatting helpers (thousands separators everywhere)
const fmtInt = (v: any) => Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
const fmtUsd = (v: any) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// Map model IDs to friendly aliases
const MODEL_ID_TO_ALIAS: Record<string, string> = (() => {
  const m: Record<string, string> = {};
  try {
    // Add plain model_id mappings
    MODEL_OPTIONS.forEach(o => { 
      m[o.model_id] = o.alias;
    });
    
    // Historical model mappings (preserve all legacy names)
    const historical: Record<string, string> = {
      // Legacy plain model IDs
      'gpt-4.1': 'GPT-4.1',
      'gpt-5': 'GPT-5 Thinking',
      'gpt-5.1': 'GPT-5.1 (legacy)',  // Old records before instant/thinking split
      'gpt-5.1-instant': 'GPT-5.1 Instant',
      'gpt-5.1-thinking': 'GPT-5.1 Thinking',
      'claude-4.0-opus': 'Claude Opus 4.0',
      'claude-3.7-sonnet': 'Claude Sonnet 3.7',
      'claude-sonnet-4-20250514': 'Sonnet 4',
      'gemini-2.0-flash': 'Gemini 2.0 Flash',
      'gemini-2.0-pro': 'Gemini 2.0 Pro',
      'grok-3': 'Grok 3',
      'grok-3-latest': 'Grok 3',
    };
    Object.assign(m, historical);
  } catch {}
  return m;
})();

const toAlias = (idOrAlias: string): string => {
  // Try direct lookup first
  if (MODEL_ID_TO_ALIAS[idOrAlias]) {
    return MODEL_ID_TO_ALIAS[idOrAlias];
  }
  
  // Try model_id lookup
  const opt = findModelByModelId(idOrAlias);
  if (opt) return opt.alias;
  
  // Fallback to original value
  return idOrAlias;
};

// Sidebar order (aliases as displayed there)
const ALIAS_ORDER: string[] = (() => {
  try { return MODEL_OPTIONS.map(o => o.alias); } catch { return []; }
})();
const ORDER_INDEX = new Map(ALIAS_ORDER.map((a, i) => [a, i] as const));
const aliasIndex = (alias: string) => ORDER_INDEX.get(alias) ?? Number.MAX_SAFE_INTEGER;

// ----- Nice tick helpers to produce rounded axis ticks like 0, 10, 20, ... -----
function niceStep(max: number, approxCount = 5): number {
  if (!isFinite(max) || max <= 0) return 1;
  const raw = max / Math.max(2, approxCount - 1); // aim for ~N ticks including 0 and max
  const power = Math.floor(Math.log10(raw));
  const base = Math.pow(10, power);
  const scaled = raw / base;
  let stepScaled = 1;
  if (scaled <= 1) stepScaled = 1;
  else if (scaled <= 2) stepScaled = 2;
  else if (scaled <= 5) stepScaled = 5;
  else stepScaled = 10;
  return stepScaled * base;
}

function niceTicksMax(max: number, approxCount = 5): number[] {
  if (!isFinite(max) || max <= 0) return [0, 1];
  const step = niceStep(max, approxCount);
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Number(v.toFixed(12)));
  return ticks;
}

function niceIntegerTicksMax(max: number, approxCount = 5): number[] {
  if (!isFinite(max) || max <= 0) return [0, 1];
  let step = niceStep(max, approxCount);
  step = Math.max(1, Math.round(step));
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  return ticks;
}

function niceSymmetricTicks(minVal: number, maxVal: number, approxCount = 5): number[] {
  if (!isFinite(minVal) || !isFinite(maxVal) || minVal === maxVal) return [0, 1];
  const extent = Math.max(Math.abs(minVal), Math.abs(maxVal));
  const step = niceStep(extent, approxCount);
  const top = Math.ceil(extent / step) * step;
  const ticks: number[] = [];
  for (let v = -top; v <= top + 1e-9; v += step) ticks.push(Number(v.toFixed(12)));
  return ticks;
}

export function RequestsSpendChart({ data }: { data: { bucket: string; count: number; spend_usd: string }[] }) {
  const series = (data || []).map(d => ({ ...d, spend: parseFloat(d.spend_usd) }));
  const maxCount = Math.max(0, ...series.map(d => d.count || 0));
  const maxSpend = Math.max(0, ...series.map(d => d.spend || 0));
  const countTicks = niceIntegerTicksMax(maxCount, 5);
  const spendTicks = niceTicksMax(maxSpend, 5);
  return (
  <div className="w-full h-64" role="img" aria-label="Requests and spend over time" tabIndex={0}>
      <ResponsiveContainer>
        <LineChart data={series} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
      <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
  <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
  <YAxis yAxisId="left" stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={countTicks} domain={[countTicks[0], countTicks[countTicks.length - 1]]} />
  <YAxis yAxisId="right" orientation="right" stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtUsd} ticks={spendTicks} domain={[spendTicks[0], spendTicks[spendTicks.length - 1]]} />
  <Tooltip cursor={{ stroke: 'var(--chart-cursor-line)' }} contentStyle={tooltipStyle} itemStyle={{ color: 'var(--chart-tooltip-fg)' }} labelStyle={{ color: 'var(--chart-tooltip-fg)' }} separator=": " formatter={(v: any, n: any) => [n?.toString()?.toLowerCase()?.includes('spend') ? fmtUsd(v) : fmtInt(v), n]} labelFormatter={(l: any) => dateOnlyLabel(l)} />
      <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
      <Line yAxisId="left" type="monotone" dataKey="count" stroke={'var(--chart-1)'} dot={false} name="Requests" />
  <Line yAxisId="right" type="monotone" dataKey="spend" stroke={'var(--chart-2)'} dot={false} name="Spend" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ByTypeBar({ data }: { data: Record<string, { count: number; spend_usd: string }> }) {
  const items = Object.entries(data || {}).map(([k, v]) => ({ name: k, count: v.count, spend: parseFloat(v.spend_usd) }));
  const maxCount = Math.max(0, ...items.map(d => d.count || 0));
  const maxSpend = Math.max(0, ...items.map(d => d.spend || 0));
  const countTicks = niceIntegerTicksMax(maxCount, 5);
  const spendTicks = niceTicksMax(maxSpend, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Requests and spend by request type" tabIndex={0}>
      <ResponsiveContainer>
        <BarChart data={items} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="name" tick={{ fill: 'var(--chart-axis)' }} />
          {/* Left axis for Requests */}
          <YAxis yAxisId="left" stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={countTicks} domain={[countTicks[0], countTicks[countTicks.length - 1]]} />
          {/* Right axis for Spend */}
          <YAxis
            yAxisId="right"
            orientation="right"
            stroke={'var(--chart-axis)'}
            tick={{ fill: 'var(--chart-axis)' }}
            tickFormatter={fmtUsd}
            ticks={spendTicks}
            domain={[spendTicks[0], spendTicks[spendTicks.length - 1]]}
          />
          {/* Use dataKey from the tooltip payload to disambiguate series reliably */}
          <Tooltip
            cursor={{ fill: 'var(--chart-cursor)' }}
            contentStyle={tooltipStyle}
            itemStyle={{ color: 'var(--chart-tooltip-fg)' }}
            labelStyle={{ color: 'var(--chart-tooltip-fg)' }}
            separator=": "
            formatter={(value: any, _name: any, item: any) =>
              item && item.dataKey === 'spend'
                ? [fmtUsd(value), 'Spend']
                : [fmtInt(value), 'Requests']
            }
          />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Bar yAxisId="left" dataKey="count" fill={'var(--chart-1)'} name="Requests" />
          <Bar yAxisId="right" dataKey="spend" fill={'var(--chart-2)'} name="Spend" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ByModelBar({ data }: { data: Record<string, { count: number; spend_usd: string }> }) {
  const items = Object.entries(data || {})
    .map(([k, v]) => ({ name: toAlias(k), count: v.count, spend: parseFloat(v.spend_usd) }))
    .sort((a, b) => aliasIndex(a.name) - aliasIndex(b.name));
  const maxCount = Math.max(0, ...items.map(d => d.count || 0));
  const maxSpend = Math.max(0, ...items.map(d => d.spend || 0));
  const countTicks = niceIntegerTicksMax(maxCount, 5);
  const spendTicks = niceTicksMax(maxSpend, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Requests and spend by model" tabIndex={0}>
      <ResponsiveContainer>
        <BarChart data={items} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="name" interval={0} angle={-20} height={60} textAnchor="end" tick={{ fill: 'var(--chart-axis)' }} />
          {/* Left axis: Requests */}
          <YAxis yAxisId="left" stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={countTicks} domain={[countTicks[0], countTicks[countTicks.length - 1]]} />
          {/* Right axis: Spend ($) */}
          <YAxis yAxisId="right" orientation="right" stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtUsd} ticks={spendTicks} domain={[spendTicks[0], spendTicks[spendTicks.length - 1]]} />
          {/* Use dataKey to avoid relying on display name in tooltip */}
          <Tooltip
            cursor={{ fill: 'var(--chart-cursor)' }}
            contentStyle={tooltipStyle}
            itemStyle={{ color: 'var(--chart-tooltip-fg)' }}
            labelStyle={{ color: 'var(--chart-tooltip-fg)' }}
            separator=": "
            formatter={(value: any, _name: any, item: any) =>
              item && item.dataKey === 'spend'
                ? [fmtUsd(value), 'Spend']
                : [fmtInt(value), 'Requests']
            }
          />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Bar yAxisId="left" dataKey="count" fill={'var(--chart-1)'} name="Requests" />
          <Bar yAxisId="right" dataKey="spend" fill={'var(--chart-2)'} name="Spend" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BalanceDeltaChart({ data }: { data: { bucket: string; delta_cents?: number; deposits_cents?: number }[] }) {
  // Show true deposits; fallback to positive part of delta if deposits_cents not provided
  const rows = (data || []).map(d => {
    const depCents = (d.deposits_cents ?? Math.max(0, d.delta_cents || 0)) || 0;
    return { bucket: d.bucket, deposits: Math.max(0, depCents / 100.0) };
  });
  const maxVal = Math.max(0, ...rows.map(r => r.deposits));
  const ticks = niceTicksMax(maxVal, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Deposits over time" tabIndex={0}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtUsd} ticks={ticks} domain={[ticks[0], ticks[ticks.length - 1]]} />
          <Tooltip cursor={{ fill: 'var(--chart-cursor)' }} contentStyle={tooltipStyle} itemStyle={{ color: 'var(--chart-tooltip-fg)' }} labelStyle={{ color: 'var(--chart-tooltip-fg)' }} separator=": " formatter={(v: any) => [fmtUsd(v), 'Deposits']} labelFormatter={(l: any) => dateOnlyLabel(l)} />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Bar dataKey="deposits" fill={'var(--chart-1)'} name="Deposits ($)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// New charts per Prompt 6

// 1) RequestsStackedArea — expects summary.requests_by_type with [{ bucket, request_type, count }]
export function RequestsStackedArea({ data }: { data: { bucket: string; request_type: string; count: number }[] }) {
  // pivot to one row per bucket with keys per type
  const buckets = new Map<string, any>();
  (data || []).forEach(r => {
    const key = r.bucket;
  if (!buckets.has(key)) buckets.set(key, { bucket: key, fit: 0, tailor: 0, judge: 0 });
    const row = buckets.get(key);
    const t = (r.request_type || "other").toLowerCase();
  // Only count known types; ignore any others
  if (t in row) row[t] += r.count || 0;
  });
  const series = Array.from(buckets.values()).sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)));
  const maxTotal = Math.max(0, ...series.map(r => (r.fit || 0) + (r.tailor || 0) + (r.judge || 0)));
  const ticks = niceIntegerTicksMax(maxTotal, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Requests by type over time" tabIndex={0}>
      <ResponsiveContainer>
        <AreaChart data={series} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={ticks} domain={[ticks[0], ticks[ticks.length - 1]]} />
          <Tooltip cursor={{ stroke: 'var(--chart-cursor-line)' }} contentStyle={tooltipStyle} itemStyle={{ color: 'var(--chart-tooltip-fg)' }} labelStyle={{ color: 'var(--chart-tooltip-fg)' }} separator=": " formatter={(value: any, name: any) => [fmtInt(value), `${String(name)} requests`]} labelFormatter={(l: any) => dateOnlyLabel(l)} />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Area type="monotone" dataKey="fit" stackId="1" stroke={'var(--chart-1)'} fill={'var(--chart-1)'} name="fit" />
          <Area type="monotone" dataKey="tailor" stackId="1" stroke={'var(--chart-2)'} fill={'var(--chart-2)'} name="tailor" />
          <Area type="monotone" dataKey="judge" stackId="1" stroke={'var(--chart-3)'} fill={'var(--chart-3)'} name="judge" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// 2) SpendBars — If server exposes per-bucket spend, we can derive from series.spend_usd per bucket by request_type, but
// since we have only by_type totals, we omit time spend if not available. We'll implement simple bar using by_type totals.
export function SpendBars({ data }: { data: Record<string, { spend_usd: string }> }) {
  const items = Object.entries(data || {}).map(([k, v]) => ({ name: k, spend: parseFloat(v.spend_usd || '0') }));
  const maxSpend = Math.max(0, ...items.map(i => i.spend));
  const ticks = niceTicksMax(maxSpend, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Spend by request type" tabIndex={0}>
      <ResponsiveContainer>
        <BarChart data={items} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="name" tick={{ fill: 'var(--chart-axis)' }} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtUsd} ticks={ticks} domain={[ticks[0], ticks[ticks.length - 1]]} />
          <Tooltip cursor={{ fill: 'var(--chart-cursor)' }} contentStyle={tooltipStyle} itemStyle={{ color: 'var(--chart-tooltip-fg)' }} labelStyle={{ color: 'var(--chart-tooltip-fg)' }} separator=": " formatter={(value: any) => [fmtUsd(value), 'Spend']} />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Bar dataKey="spend" fill={'var(--chart-2)'} name="Spend" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// 3) SpendByTypeDonut
const DONUT_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)'
]; 
export function SpendByTypeDonut({ data }: { data: Record<string, { spend_usd: string }> }) {
  const items = Object.entries(data || {}).map(([k, v]) => ({ name: k, value: parseFloat(v.spend_usd || '0') }));
  return (
    <div className="w-full h-64" role="img" aria-label="Spend distribution by request type" tabIndex={0}>
      <ResponsiveContainer>
        <PieChart>
          <Pie data={items} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={2}>
            {items.map((_, i) => <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: 'var(--chart-tooltip-fg)' }} labelStyle={{ color: 'var(--chart-tooltip-fg)' }} separator=": " formatter={(value: any, name: any) => [fmtUsd(value), String(name)]} />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

// 4) TopModelsBar — use by_model totals
export function TopModelsBar({ data }: { data: Record<string, { count: number; spend_usd: string }> }) {
  const items = Object.entries(data || {})
  .map(([k, v]) => ({ name: toAlias(k), count: v.count, spend: parseFloat(v.spend_usd || '0') }))
  .sort((a, b) => aliasIndex(a.name) - aliasIndex(b.name))
    .slice(0, 15);
  const maxCount = Math.max(0, ...items.map(i => i.count || 0));
  const maxSpend = Math.max(0, ...items.map(i => i.spend || 0));
  const countTicks = niceIntegerTicksMax(maxCount, 5);
  const spendTicks = niceTicksMax(maxSpend, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Top models by requests and spend" tabIndex={0}>
      <ResponsiveContainer>
        <BarChart data={items} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="name" interval={0} angle={-20} height={70} textAnchor="end" tick={{ fill: 'var(--chart-axis)' }} />
          {/* Left axis: Requests */}
          <YAxis yAxisId="left" stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={countTicks} domain={[countTicks[0], countTicks[countTicks.length - 1]]} />
          {/* Right axis: Spend ($) */}
          <YAxis yAxisId="right" orientation="right" stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtUsd} ticks={spendTicks} domain={[spendTicks[0], spendTicks[spendTicks.length - 1]]} />
          {/* Format spend as currency and label correctly using dataKey */}
          <Tooltip
            cursor={{ fill: 'var(--chart-cursor)' }}
            contentStyle={tooltipStyle}
            itemStyle={{ color: 'var(--chart-tooltip-fg)' }}
            labelStyle={{ color: 'var(--chart-tooltip-fg)' }}
            separator=": "
            formatter={(value: any, _name: any, item: any) =>
              item && item.dataKey === 'spend'
                ? [fmtUsd(value), 'Spend']
                : [fmtInt(value), 'Requests']
            }
          />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Bar yAxisId="left" dataKey="count" fill={'var(--chart-1)'} name="Requests" />
          <Bar yAxisId="right" dataKey="spend" fill={'var(--chart-2)'} name="Spend" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// 5) TokenMixByModelBars — expects tokens_by_model: [{ model, avg_prompt, avg_completion }]
export function TokenMixByModelBars({ data }: { data: { model: string; avg_prompt: number; avg_completion: number }[] }) {
  const items = (data || [])
    .map(d => ({ ...d, model: toAlias(d.model) }))
    .sort((a, b) => aliasIndex(a.model) - aliasIndex(b.model))
    .slice(0, 20);
  const maxTokens = Math.max(0, ...items.map(i => Math.max(i.avg_prompt || 0, i.avg_completion || 0)));
  const ticks = niceIntegerTicksMax(maxTokens, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Average tokens per model" tabIndex={0}>
      <ResponsiveContainer>
        <BarChart data={items} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="model" interval={0} angle={-20} height={70} textAnchor="end" tick={{ fill: 'var(--chart-axis)' }} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtInt} ticks={ticks} domain={[ticks[0], ticks[ticks.length - 1]]} />
            <Tooltip
              cursor={{ fill: 'var(--chart-cursor)' }}
              contentStyle={tooltipStyle}
              itemStyle={{ color: 'var(--chart-tooltip-fg)' }}
              labelStyle={{ color: 'var(--chart-tooltip-fg)' }}
              separator=": "
              formatter={(v: any, n: any) => [fmtInt(v), n === 'avg_prompt' ? 'Avg prompt tokens' : 'Avg completion tokens']}
            />
          <Legend formatter={(v: any) => v === 'avg_prompt' ? 'Avg prompt' : 'Avg completion'} />
          <Bar dataKey="avg_prompt" fill={'var(--chart-1)'} />
          <Bar dataKey="avg_completion" fill={'var(--chart-2)'} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// 6) LatencyLine — from latency.series
export function LatencyLine({ data }: { data: { bucket: string; avg_ms: number }[] }) {
  const maxMs = Math.max(0, ...((data || []).map(d => d.avg_ms || 0)));
  const secTicks = niceTicksMax(maxMs / 1000, 5); // ticks in seconds
  const msTicks = secTicks.map(s => s * 1000);
  return (
    <div className="w-full h-64" role="img" aria-label="Average latency over time" tabIndex={0}>
      <ResponsiveContainer>
        <LineChart data={data || []} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={(v: any) => `${(Number(v) / 1000).toFixed(1)}s`} ticks={msTicks} domain={[msTicks[0], msTicks[msTicks.length - 1]]} />
          <Tooltip
            cursor={{ stroke: 'var(--chart-cursor-line)' }}
            contentStyle={tooltipStyle}
            itemStyle={{ color: 'var(--chart-tooltip-fg)' }}
            labelStyle={{ color: 'var(--chart-tooltip-fg)' }}
            separator=": "
            formatter={(v: any) => [`${(Number(v) / 1000).toFixed(1)}s`, 'Avg latency (s)']}
            labelFormatter={(l: any) => dateOnlyLabel(l)}
          />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Line type="monotone" dataKey="avg_ms" stroke={'var(--chart-5)'} dot={false} name="Avg latency (s)" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// 7) BalanceLine — plot running_cents/100 over time
export function BalanceLine({ data }: { data: { bucket: string; running_cents: number }[] }) {
  const baseRows = (data || []).map(d => ({ bucket: String(d.bucket), balance: (d.running_cents || 0) / 100.0 }));
  // If no data, render empty
  const rows = (() => {
    if (!baseRows.length) return baseRows;
    // Build map by YYYY-MM-DD and find first/last dates
    const keyOf = (s: string) => {
      const k = dateOnlyLabel(s); // YYYY-MM-DD
      return k;
    };
    const byKey = new Map<string, number>();
    const keys: string[] = [];
    for (const r of baseRows) {
      const k = keyOf(r.bucket);
      if (!byKey.has(k)) keys.push(k);
      byKey.set(k, r.balance);
    }
    // Sort keys asc
    keys.sort();
    const start = keys[0];
    const end = keys[keys.length - 1];
    // Iterate day-by-day from start..end (inclusive), carrying forward last known balance
    const toDate = (k: string) => new Date(k + 'T00:00:00.000Z');
    const toKey = (d: Date) => d.toISOString().slice(0, 10);
    let cursor = toDate(start);
    const endDate = toDate(end);
    const filled: { bucket: string; balance: number }[] = [];
    let last = byKey.get(start)!;
    while (cursor <= endDate) {
      const ck = toKey(cursor);
      if (byKey.has(ck)) last = byKey.get(ck)!;
      filled.push({ bucket: ck, balance: last });
      cursor = new Date(cursor.getTime() + 24 * 60 * 60 * 1000);
    }
    return filled;
  })();
  const maxBal = Math.max(0, ...rows.map(r => r.balance));
  const ticks = niceTicksMax(maxBal, 5);
  return (
    <div className="w-full h-64" role="img" aria-label="Account balance over time" tabIndex={0}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={'var(--chart-grid)'} />
          <XAxis dataKey="bucket" minTickGap={24} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={dateOnlyLabel} />
          <YAxis stroke={'var(--chart-axis)'} tick={{ fill: 'var(--chart-axis)' }} tickFormatter={fmtUsd} ticks={ticks} domain={[0, ticks[ticks.length - 1]]} />
          <Tooltip cursor={{ stroke: 'var(--chart-cursor-line)' }} contentStyle={tooltipStyle} itemStyle={{ color: 'var(--chart-tooltip-fg)' }} labelStyle={{ color: 'var(--chart-tooltip-fg)' }} separator=": " formatter={(v: any) => [fmtUsd(v), 'Balance']} labelFormatter={(l: any) => dateOnlyLabel(l)} />
          <Legend wrapperStyle={{ color: 'var(--chart-legend)' }} />
          <Line type="monotone" dataKey="balance" stroke={'var(--chart-4)'} dot={false} name="Balance ($)" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
