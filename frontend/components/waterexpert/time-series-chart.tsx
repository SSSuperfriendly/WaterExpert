"use client";

import * as React from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { formatMaybeDate, formatNumber } from "@/lib/format";

export interface SeriesDef {
  key: string;
  label: string;
  color: string;
  dashed?: boolean;
}

const PALETTE = [
  "#0ea5e9", // sky-500
  "#f59e0b", // amber-500
  "#10b981", // emerald-500
  "#ef4444", // red-500
  "#8b5cf6", // violet-500
  "#ec4899", // pink-500
];

export function TimeSeriesChart({
  data,
  series,
  height = 320,
  xKey = "date",
}: {
  data: Record<string, unknown>[];
  series: SeriesDef[];
  height?: number;
  xKey?: string;
}) {
  const normalized = React.useMemo(
    () =>
      data.map((row) => {
        const out: Record<string, unknown> = { [xKey]: row[xKey] };
        for (const s of series) {
          const v = row[s.key];
          out[s.key] = typeof v === "number" ? v : Number(v);
        }
        return out;
      }),
    [data, series, xKey]
  );

  const resolvedSeries = React.useMemo(
    () =>
      series.map((s, i) => ({
        ...s,
        color: s.color || PALETTE[i % PALETTE.length],
      })),
    [series]
  );

  return (
    <div style={{ width: "100%", height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={normalized} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border/60" />
          <XAxis
            dataKey={xKey}
            tickFormatter={(v) => formatMaybeDate(v).slice(5)}
            tick={{ fontSize: 11 }}
            tickMargin={6}
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 11 }}
            width={44}
            tickFormatter={(v) => formatNumber(v, 1)}
          />
          <Tooltip
            formatter={(value: number, name: string) => [formatNumber(value, 2), name]}
            labelFormatter={(label) => formatMaybeDate(label)}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {resolvedSeries.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={s.dashed ? 1.5 : 2}
              strokeDasharray={s.dashed ? "5 5" : undefined}
              dot={false}
              activeDot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
