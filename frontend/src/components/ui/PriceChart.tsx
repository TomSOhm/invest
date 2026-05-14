"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Candle, MovingAverages } from "@/lib/types";

export interface EarningsMarker {
  date: string; // "YYYY-MM-DD"
  eps_actual: number | null;
  eps_estimate: number | null;
  surprise_pct: number | null;
}

interface Props {
  candles: Candle[];
  benchmarkCandles: Candle[];
  movingAverages: MovingAverages;
  benchmarkLabel: string | null;
  earnings?: EarningsMarker[] | null;
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

/**
 * Snap an earnings date to the nearest trading day actually present in
 * `data`. Returns the index of the snapped row, or -1 when the earnings
 * date is before the first trading day in the window.
 *
 * Weekend earnings (Yahoo reports the announcement date, not the trading
 * day) snap to the most recent prior trading day so the marker sits on
 * the close line.
 */
function snapToTradingDay(data: ChartRow[], date: string): number {
  const exact = data.findIndex((row) => row.date === date);
  if (exact >= 0) return exact;
  for (let i = data.length - 1; i >= 0; i--) {
    if (data[i].date <= date) return i;
  }
  return -1;
}

function pm5Return(data: ChartRow[], idx: number): number | null {
  if (idx < 5 || idx + 5 >= data.length) return null;
  const before = data[idx - 5].close;
  const after = data[idx + 5].close;
  if (!before || !after) return null;
  return (after - before) / before;
}

export default function PriceChart({
  candles,
  benchmarkCandles,
  movingAverages,
  benchmarkLabel,
  earnings,
  height = 320,
}: Props) {
  const data = buildRows(candles, benchmarkCandles, movingAverages);

  type Marker = {
    snapped_date: string;
    snapped_close: number;
    fill: string;
    eps_actual: number | null;
    eps_estimate: number | null;
    surprise_pct: number | null;
    pm5: number | null;
  };
  const markers: Marker[] = (earnings ?? [])
    .map((e): Marker | null => {
      const idx = snapToTradingDay(data, e.date);
      if (idx < 0) return null;
      const row = data[idx];
      const fill =
        e.surprise_pct == null
          ? "#94a3b8"
          : e.surprise_pct > 0
            ? "#10b981"
            : e.surprise_pct < 0
              ? "#ef4444"
              : "#64748b";
      return {
        snapped_date: row.date,
        snapped_close: row.close,
        fill,
        eps_actual: e.eps_actual,
        eps_estimate: e.eps_estimate,
        surprise_pct: e.surprise_pct,
        pm5: pm5Return(data, idx),
      };
    })
    .filter((m): m is Marker => m !== null);

  const markerByDate = new Map(markers.map((m) => [m.snapped_date, m]));

  return (
    <div
      role="img"
      aria-label={`Price chart, ${data.length} data points${benchmarkLabel ? `, with ${benchmarkLabel} overlay` : ""}${markers.length > 0 ? `, ${markers.length} earnings markers` : ""}`}
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
            formatter={(value, name, _item, _index, payload) => {
              const v = typeof value === "number" ? value : null;
              const base: [string, string] =
                v == null ? ["—", String(name)] : [v.toFixed(2), String(name)];
              if (name !== "Price") return base;
              const date =
                payload && typeof payload === "object" && "date" in payload
                  ? (payload as { date: string }).date
                  : undefined;
              const ev = date ? markerByDate.get(date) : undefined;
              if (!ev) return base;
              const surprise =
                ev.surprise_pct != null
                  ? `${ev.surprise_pct > 0 ? "+" : ""}${ev.surprise_pct.toFixed(1)}%`
                  : "—";
              const pm5 =
                ev.pm5 != null
                  ? `${(ev.pm5 * 100).toFixed(2)}%`
                  : "—";
              const actual = ev.eps_actual != null ? ev.eps_actual.toFixed(2) : "—";
              const est = ev.eps_estimate != null ? ev.eps_estimate.toFixed(2) : "—";
              return [
                `${base[0]}\nEarnings · Actual ${actual} · Est ${est} · Surprise ${surprise} · ±5d ${pm5}`,
                base[1],
              ];
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
          {markers.map((m) => (
            <ReferenceDot
              key={m.snapped_date}
              x={m.snapped_date}
              y={m.snapped_close}
              r={5}
              fill={m.fill}
              stroke="#fff"
              strokeWidth={1.5}
              ifOverflow="extendDomain"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
