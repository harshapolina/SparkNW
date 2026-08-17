"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = {
  date: string;
  followers?: number;
};

export function PerformanceChart({ data }: { data: Point[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%" debounce={40}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="sparkViewsLive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff4d00" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#ff4d00" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
        <Tooltip
          contentStyle={{ background: "#121212", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
        />
        <Area
          type="monotone"
          dataKey="followers"
          stroke="#ff4d00"
          fill="url(#sparkViewsLive)"
          strokeWidth={2.5}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
