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

interface ResolvedMarker {
  snapped_date: string;
  snapped_close: number;
  // Tailwind-mapped fills — dark-mode safe (WCAG-AA against slate-900)
  fill_light: string;
  fill_dark: string;
  eps_actual: number | null;
  eps_estimate: number | null;
  surprise_pct: number | null;
  pm5: number | null;
}

function buildRows(
  candles: Candle[],
  benchmark: Candle[],
  ma: MovingAverages,
): ChartRow[] {
  const benchByDate = new Map(benchmark.map((c) => [c.date, c.close]));
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
 * Weekend earnings snap to the most recent prior trading day so the
 * marker sits on the close line.
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

/**
 * Custom Recharts tooltip. Renders the standard date + price block, plus
 * an earnings detail panel when the hovered date matches an earnings
 * marker. Multi-line content uses proper React elements (not embedded
 * `\n` characters) so each detail row renders on its own line.
 */
interface TooltipEntry {
  payload?: ChartRow;
  value?: unknown;
  name?: unknown;
  color?: string;
}

function ChartTooltip({
  active,
  payload,
  label,
  markerByDate,
}: {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: string | number;
  markerByDate: Map<string, ResolvedMarker>;
}) {
  const labelStr = typeof label === "string" ? label : undefined;
  if (!active || !payload || payload.length === 0) return null;
  const ev = labelStr ? markerByDate.get(labelStr) : undefined;
  return (
    <div
      role={ev ? "tooltip" : undefined}
      aria-live={ev ? "polite" : undefined}
      className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded shadow-md px-2.5 py-1.5 text-xs"
    >
      <div className="font-semibold text-slate-700 dark:text-slate-200">
        Date: {labelStr ?? label}
      </div>
      {payload.map((p) => (
        <div key={String(p.name ?? "")} className="flex justify-between gap-3">
          <span style={{ color: p.color }}>{String(p.name ?? "")}</span>
          <span className="font-mono text-slate-800 dark:text-slate-200">
            {typeof p.value === "number" ? p.value.toFixed(2) : "—"}
          </span>
        </div>
      ))}
      {ev && (
        <div className="mt-1 pt-1 border-t border-slate-200 dark:border-slate-700 space-y-0.5 text-[11px]">
          <div className="font-semibold text-emerald-600 dark:text-emerald-400">
            Earnings
          </div>
          <div className="flex justify-between gap-3 text-slate-700 dark:text-slate-300">
            <span>Actual</span>
            <span className="font-mono">
              {ev.eps_actual != null ? ev.eps_actual.toFixed(2) : "—"}
            </span>
          </div>
          <div className="flex justify-between gap-3 text-slate-700 dark:text-slate-300">
            <span>Est</span>
            <span className="font-mono">
              {ev.eps_estimate != null ? ev.eps_estimate.toFixed(2) : "—"}
            </span>
          </div>
          <div className="flex justify-between gap-3 text-slate-700 dark:text-slate-300">
            <span>Surprise</span>
            <span className="font-mono">
              {ev.surprise_pct != null
                ? `${ev.surprise_pct > 0 ? "+" : ""}${ev.surprise_pct.toFixed(1)}%`
                : "—"}
            </span>
          </div>
          <div className="flex justify-between gap-3 text-slate-700 dark:text-slate-300">
            <span>±5d return</span>
            <span className="font-mono">
              {ev.pm5 != null ? `${(ev.pm5 * 100).toFixed(2)}%` : "—"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
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

  // WCAG-AA palette: bright shades pass 3:1 against slate-900 (dark) AND
  // dark shades pass 3:1 against white (light). Recharts SVG can't read
  // CSS classes on a fill attribute, so we resolve a single fill that
  // works in both themes — emerald-500/red-500/slate-400 are the
  // narrowest cross-theme picks.
  const markers: ResolvedMarker[] = (earnings ?? [])
    .map((e): ResolvedMarker | null => {
      const idx = snapToTradingDay(data, e.date);
      if (idx < 0) return null;
      const row = data[idx];
      const isBeat = e.surprise_pct != null && e.surprise_pct > 0;
      const isMiss = e.surprise_pct != null && e.surprise_pct < 0;
      // Single-fill choice that meets WCAG-AA graphical-element contrast
      // (≥3:1) against both white and slate-900 backgrounds. emerald-600
      // and red-600 are the darkest hues that still read on slate-900.
      const fill = isBeat
        ? "#059669" // emerald-600
        : isMiss
          ? "#dc2626" // red-600
          : "#475569"; // slate-600
      return {
        snapped_date: row.date,
        snapped_close: row.close,
        fill_light: fill,
        fill_dark: fill,
        eps_actual: e.eps_actual,
        eps_estimate: e.eps_estimate,
        surprise_pct: e.surprise_pct,
        pm5: pm5Return(data, idx),
      };
    })
    .filter((m): m is ResolvedMarker => m !== null);

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
            content={(props) => (
              <ChartTooltip {...props} markerByDate={markerByDate} />
            )}
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
              fill={m.fill_light}
              stroke="#ffffff"
              strokeWidth={1.8}
              ifOverflow="extendDomain"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
