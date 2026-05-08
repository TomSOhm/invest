"use client";

import clsx from "clsx";
import type { Horizon } from "@/lib/types";

interface HorizonSelectorProps {
  value: Horizon;
  onChange: (h: Horizon) => void;
  className?: string;
}

const OPTIONS: { value: Horizon; label: string; shortLabel: string }[] = [
  { value: "long_term", label: "Long Term", shortLabel: "LT" },
  { value: "medium_term", label: "Medium Term", shortLabel: "MT" },
  { value: "short_term", label: "Short Term", shortLabel: "ST" },
];

/**
 * Segmented control for switching scoring horizon.
 * Usage:
 *   <HorizonSelector value={horizon} onChange={setHorizon} />
 */
export default function HorizonSelector({
  value,
  onChange,
  className,
}: HorizonSelectorProps) {
  return (
    <div
      role="tablist"
      aria-label="Scoring horizon"
      className={clsx(
        "inline-flex rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 p-0.5 gap-0.5",
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
