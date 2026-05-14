"use client";

import clsx from "clsx";
import { BENCHMARK_OPTIONS } from "@/lib/benchmarks";

interface Props {
  value: string | null;
  onChange: (ticker: string | null) => void;
  className?: string;
}

export default function BenchmarkSelector({ value, onChange, className }: Props) {
  const selectedKey =
    BENCHMARK_OPTIONS.find((o) => o.ticker === value)?.key ?? "none";

  return (
    <select
      aria-label="Benchmark index"
      value={selectedKey}
      onChange={(e) => {
        const opt = BENCHMARK_OPTIONS.find((o) => o.key === e.target.value);
        onChange(opt?.ticker ?? null);
      }}
      className={clsx(
        "px-2.5 py-1.5 text-xs font-medium rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 cursor-pointer",
        className,
      )}
    >
      {BENCHMARK_OPTIONS.map((o) => (
        <option key={o.key} value={o.key}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
