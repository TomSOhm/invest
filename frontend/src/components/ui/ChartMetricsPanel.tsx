"use client";

import clsx from "clsx";
import type { ChartMetrics } from "@/lib/types";
import { formatPercent, formatNumber } from "@/lib/formatters";

interface Props {
  metrics: ChartMetrics;
  benchmarkLabel: string | null;
}

interface Tile {
  label: string;
  value: string;
  positive: boolean | null;
}

function pct(v: number | null): string {
  return v == null ? "—" : formatPercent(v * 100);
}

function sign(v: number | null): boolean | null {
  if (v == null) return null;
  if (v > 0) return true;
  if (v < 0) return false;
  return null;
}

export default function ChartMetricsPanel({ metrics, benchmarkLabel }: Props) {
  const tiles: Tile[] = [
    {
      label: "Total Return",
      value: pct(metrics.total_return),
      positive: sign(metrics.total_return),
    },
    { label: "CAGR", value: pct(metrics.cagr), positive: sign(metrics.cagr) },
    { label: "Ann. Vol", value: pct(metrics.annualized_vol), positive: null },
    {
      label: "Max DD",
      value: pct(metrics.max_drawdown),
      positive: sign(metrics.max_drawdown),
    },
    {
      label: benchmarkLabel ? `Beta vs ${benchmarkLabel}` : "Beta",
      value: metrics.beta == null ? "—" : formatNumber(metrics.beta, 2),
      positive: null,
    },
    {
      label: "Sharpe",
      value: metrics.sharpe == null ? "—" : formatNumber(metrics.sharpe, 2),
      positive: sign(metrics.sharpe),
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {tiles.map((t) => (
        <div
          key={t.label}
          className="rounded-md border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 px-3 py-2.5 flex flex-col gap-0.5"
        >
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            {t.label}
          </div>
          <div
            className={clsx(
              "text-sm font-mono font-semibold tabular-nums",
              t.positive === true && "text-emerald-600 dark:text-emerald-400",
              t.positive === false && "text-red-500 dark:text-red-400",
              t.positive == null && "text-slate-900 dark:text-slate-100",
            )}
          >
            {t.value}
          </div>
        </div>
      ))}
    </div>
  );
}
