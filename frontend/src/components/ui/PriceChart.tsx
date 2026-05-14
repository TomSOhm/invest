"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Candle, MovingAverages } from "@/lib/types";

interface Props {
  candles: Candle[];
  benchmarkCandles: Candle[];
  movingAverages: MovingAverages;
  benchmarkLabel: string | null;
  height?: number;
}

interface ChartRow {
  date: string;
  close: number;
  benchmark?: number | null;
  ma_50?: number | null;
  ma_200?: number | null;
}

function buildRows(
  candles: Candle[],
  benchmark: Candle[],
  ma: MovingAverages,
): ChartRow[] {
  const benchByDate = new Map(benchmark.map((c) => [c.date, c.close]));
  // Rebase benchmark to the stock's first close so both series share a Y origin.
  const stockFirst = candles[0]?.close ?? 1;
  const benchFirst = benchmark[0]?.close ?? 1;
  const rebase = (v: number | undefined) =>
    v == null ? null : (v / benchFirst) * stockFirst;

  return candles.map((c, i) => ({
    date: c.date,
    close: c.close,
    benchmark: rebase(benchByDate.get(c.date)),
    ma_50: ma.ma_50[i] ?? null,
    ma_200: ma.ma_200[i] ?? null,
  }));
}

export default function PriceChart({
  candles,
  benchmarkCandles,
  movingAverages,
  benchmarkLabel,
  height = 320,
}: Props) {
  const data = buildRows(candles, benchmarkCandles, movingAverages);

  return (
    <div
      role="img"
      aria-label={`Price chart, ${data.length} data points${benchmarkLabel ? `, with ${benchmarkLabel} overlay` : ""}`}
    >
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          data={data}
          margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
          accessibilityLayer
        >
          <CartesianGrid
            strokeDasharray="3 3"
            className="stroke-slate-200 dark:stroke-slate-700"
          />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={48} />
          <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            labelFormatter={(l) => `Date: ${l}`}
            formatter={(value, name) => {
              const v = typeof value === "number" ? value : null;
              return v == null ? ["—", String(name)] : [v.toFixed(2), String(name)];
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line
            type="monotone"
            dataKey="close"
            name="Price"
            stroke="#059669"
            strokeWidth={1.6}
            dot={false}
          />
          {benchmarkLabel && (
            <Line
              type="monotone"
              dataKey="benchmark"
              name={benchmarkLabel}
              stroke="#64748b"
              strokeWidth={1.2}
              strokeDasharray="4 3"
              dot={false}
            />
          )}
          <Line
            type="monotone"
            dataKey="ma_50"
            name="50d MA"
            stroke="#f59e0b"
            strokeWidth={1}
            dot={false}
            strokeOpacity={0.7}
          />
          <Line
            type="monotone"
            dataKey="ma_200"
            name="200d MA"
            stroke="#ef4444"
            strokeWidth={1}
            dot={false}
            strokeOpacity={0.7}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
