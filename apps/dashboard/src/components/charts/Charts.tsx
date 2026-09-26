"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const AXIS = { fontSize: 12, fill: "var(--muted)" } as const;
const GRID = "var(--line)";

function TooltipBox({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">{children}</div>;
}

export interface TrendPoint { label: string; high: number; medium: number; low: number }

export function SeverityTrend({ data }: { data: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={230}>
      <AreaChart data={data} margin={{ left: -18, right: 8, top: 8 }}>
        <defs>
          {[["high", "#ef4444"], ["medium", "#f59e0b"], ["low", "#94a3b8"]].map(([k, c]) => (
            <linearGradient key={k} id={`g-${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={c} stopOpacity={0.35} />
              <stop offset="100%" stopColor={c} stopOpacity={0.04} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip
          cursor={{ stroke: "var(--line-strong)" }}
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <TooltipBox>
                <div className="mb-1 font-medium text-ink">{label}</div>
                {[...payload].reverse().map((p) => (
                  <div key={String(p.dataKey)} className="flex items-center gap-2 text-muted">
                    <span className="h-2 w-2 rounded-full" style={{ background: p.stroke as string }} />
                    {String(p.name)}: <b className="text-ink tabular-nums">{String(p.value)}</b>
                  </div>
                ))}
              </TooltipBox>
            ) : null
          }
        />
        <Area type="monotone" dataKey="low" stackId="s" name="Low" stroke="#94a3b8" strokeWidth={1.5} fill="url(#g-low)" />
        <Area type="monotone" dataKey="medium" stackId="s" name="Medium" stroke="#f59e0b" strokeWidth={1.5} fill="url(#g-medium)" />
        <Area type="monotone" dataKey="high" stackId="s" name="High" stroke="#ef4444" strokeWidth={1.5} fill="url(#g-high)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SeverityDonut({ high, medium, low }: { high: number; medium: number; low: number }) {
  const total = high + medium + low;
  const data = [
    { name: "High", value: high, color: "#ef4444" },
    { name: "Medium", value: medium, color: "#f59e0b" },
    { name: "Low", value: low, color: "#94a3b8" },
  ].filter((d) => d.value > 0);
  return (
    <div className="flex items-center gap-6">
      <div className="relative h-36 w-36 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data.length ? data : [{ name: "none", value: 1, color: "var(--line)" }]} dataKey="value" innerRadius={46} outerRadius={64} paddingAngle={data.length > 1 ? 3 : 0} stroke="none" startAngle={90} endAngle={-270}>
              {(data.length ? data : [{ color: "var(--line)" }]).map((d, i) => <Cell key={i} fill={d.color} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold tabular-nums text-ink">{total}</span>
          <span className="text-[11px] text-muted">findings</span>
        </div>
      </div>
      <ul className="space-y-2 text-sm">
        {[["High", high, "#ef4444"], ["Medium", medium, "#f59e0b"], ["Low", low, "#94a3b8"]].map(([n, v, c]) => (
          <li key={String(n)} className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: String(c) }} />
            <span className="w-14 text-muted">{n}</span>
            <b className="tabular-nums text-ink">{String(v)}</b>
            <span className="text-xs text-faint">{total ? `${Math.round((Number(v) / total) * 100)}%` : ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface BarDatum { name: string; value: number; detail?: string; color?: string }

export function HorizontalBars({ data, color = "var(--brand)", unit, nameWidth = 180 }: { data: BarDatum[]; color?: string; unit: string; nameWidth?: number }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(110, data.length * 32 + 24)}>
      <BarChart data={data} layout="vertical" margin={{ left: 4, right: 28, top: 4, bottom: 4 }} barCategoryGap={8}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" width={nameWidth} tick={{ ...AXIS, fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip
          cursor={{ fill: "var(--sunken)" }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TooltipBox>
                <div className="max-w-xs break-words font-mono text-[11px] text-muted">{String(payload[0].payload.detail ?? payload[0].payload.name)}</div>
                <div className="mt-1 text-ink"><b className="tabular-nums">{String(payload[0].value)}</b> {unit}</div>
              </TooltipBox>
            ) : null
          }
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={20}>
          {data.map((d, i) => <Cell key={i} fill={d.color ?? color} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
