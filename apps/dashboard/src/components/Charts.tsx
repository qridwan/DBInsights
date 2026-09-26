"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface TrendPoint {
  label: string;
  high: number;
  medium: number;
  low: number;
}

export function TrendChart({ data }: { data: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" fontSize={12} />
        <YAxis allowDecimals={false} fontSize={12} />
        <Tooltip />
        <Legend />
        <Bar dataKey="high" stackId="s" fill="#dc2626" name="High" />
        <Bar dataKey="medium" stackId="s" fill="#f97316" name="Medium" />
        <Bar dataKey="low" stackId="s" fill="#94a3b8" name="Low" />
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface BarDatum {
  name: string;
  value: number;
  detail?: string;
}

export function HorizontalBars({
  data,
  color,
  unit,
}: {
  data: BarDatum[];
  color: string;
  unit: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 30 + 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" fontSize={12} />
        <YAxis type="category" dataKey="name" width={190} fontSize={11} />
        <Tooltip
          formatter={(value) => [`${value} ${unit}`, ""]}
          labelFormatter={(_, payload) => String(payload?.[0]?.payload?.detail ?? "")}
        />
        <Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
