"use client";

import clsx from "clsx";
import { CHART_PERIODS, type ChartPeriod } from "@/lib/types";

interface Props {
  value: ChartPeriod;
  onChange: (p: ChartPeriod) => void;
  className?: string;
}

export default function PeriodSelector({ value, onChange, className }: Props) {
  function handleKey(e: React.KeyboardEvent<HTMLButtonElement>) {
    const idx = CHART_PERIODS.indexOf(value);
    if (e.key === "ArrowRight") {
      e.preventDefault();
      onChange(CHART_PERIODS[(idx + 1) % CHART_PERIODS.length]);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      onChange(CHART_PERIODS[(idx - 1 + CHART_PERIODS.length) % CHART_PERIODS.length]);
    } else if (e.key === "Home") {
      e.preventDefault();
      onChange(CHART_PERIODS[0]);
    } else if (e.key === "End") {
      e.preventDefault();
      onChange(CHART_PERIODS[CHART_PERIODS.length - 1]);
    }
  }

  return (
    <div
      role="tablist"
      aria-label="Chart period"
      className={clsx(
        "inline-flex rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 p-0.5 gap-0.5",
        className,
      )}
    >
      {CHART_PERIODS.map((p) => {
        const active = value === p;
        return (
          <button
            key={p}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(p)}
            onKeyDown={handleKey}
            className={clsx(
              "px-2.5 py-1 text-xs font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500",
              active
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200",
            )}
          >
            {p}
          </button>
        );
      })}
    </div>
  );
}
