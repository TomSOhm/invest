"use client";

import clsx from "clsx";
import type { DataSource } from "@/lib/types";

interface SourceSelectorProps {
  value: DataSource;
  onChange: (s: DataSource) => void;
  className?: string;
  disabled?: boolean;
}

const OPTIONS: {
  value: DataSource;
  label: string;
  shortLabel: string;
  hint: string;
}[] = [
  {
    value: "hybrid",
    label: "Hybrid",
    shortLabel: "H",
    hint: "FMP first, yfinance fallback per field (default, best coverage)",
  },
  {
    value: "yfinance",
    label: "Yahoo",
    shortLabel: "YF",
    hint: "yfinance only — works for all global tickers, no quota",
  },
  {
    value: "fmp",
    label: "FMP",
    shortLabel: "FMP",
    hint: "Financial Modeling Prep only — richer US data, 250 calls/day cap",
  },
];

/**
 * Segmented control for switching the data backend that feeds live fetches.
 * Usage:
 *   <SourceSelector value={source} onChange={setSource} />
 */
export default function SourceSelector({
  value,
  onChange,
  className,
  disabled = false,
}: SourceSelectorProps) {
  return (
    <div
      role="tablist"
      aria-label="Data source"
      className={clsx(
        "inline-flex rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 p-0.5 gap-0.5",
        disabled && "opacity-50 pointer-events-none",
        className
      )}
    >
      {OPTIONS.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={active}
            title={opt.hint}
            onClick={() => onChange(opt.value)}
            className={clsx(
              "px-3 py-1.5 text-sm font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500",
              active
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
            )}
          >
            <span className="hidden sm:inline">{opt.label}</span>
            <span className="sm:hidden">{opt.shortLabel}</span>
          </button>
        );
      })}
    </div>
  );
}
