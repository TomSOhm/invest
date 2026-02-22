"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Play, List, RefreshCw } from "lucide-react";
import { useScreener } from "@/hooks/useScreener";
import type { ScreenerFilters } from "@/lib/types";
import { formatNumber, formatPercent, formatLargeNumber } from "@/lib/formatters";
import SignalBadge from "@/components/ui/SignalBadge";
import PeaBadge from "@/components/ui/PeaBadge";
import Spinner from "@/components/ui/Spinner";
import { ScoreBar } from "@/components/ui/ScoreGauge";
import clsx from "clsx";

const PRESETS = [
  { name: "pea_value", label: "PEA Value" },
  { name: "pea_quality", label: "PEA Quality" },
  { name: "dividend", label: "Dividend" },
  { name: "global", label: "Global Best" },
];

const DEFAULT_FILTERS: ScreenerFilters = {
  max_pe: undefined,
  min_roe: undefined,
  min_market_cap: undefined,
  max_debt_equity: undefined,
  min_operating_margin: undefined,
  min_div_yield: undefined,
  min_composite_score: undefined,
  min_revenue_growth: undefined,
};

function FilterInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: number | undefined;
  onChange: (v: number | undefined) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
        {label}
      </label>
      <input
        type="number"
        step="any"
        value={value ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === "" ? undefined : parseFloat(v));
        }}
        placeholder={placeholder ?? "Any"}
        className="w-full px-2.5 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
      />
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <div
        className={clsx(
          "w-9 h-5 rounded-full transition-colors relative",
          checked ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"
        )}
        onClick={() => onChange(!checked)}
      >
        <div
          className={clsx(
            "w-4 h-4 rounded-full bg-white shadow-sm absolute top-0.5 transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5"
          )}
        />
      </div>
      <span className="text-sm text-slate-700 dark:text-slate-300">{label}</span>
    </label>
  );
}

export default function ScreenerPage() {
  const router = useRouter();
  const { results, loading, error, runScreen, runPreset, scoreTickers } = useScreener();
  const [filters, setFilters] = useState<ScreenerFilters>(DEFAULT_FILTERS);
  const [peaOnly, setPeaOnly] = useState(false);
  const [customTickers, setCustomTickers] = useState("");
  const [activePreset, setActivePreset] = useState<string | null>(null);

  function updateFilter<K extends keyof ScreenerFilters>(key: K, val: ScreenerFilters[K]) {
    setFilters((f) => ({ ...f, [key]: val }));
    setActivePreset(null);
  }

  function handleRunScreen() {
    setActivePreset(null);
    // Percentage-based filters are entered by the user as whole numbers (e.g. 10 for 10%)
    // but the backend stores data in decimal form (0.10). Divide by 100 before sending.
    const convertedFilters: ScreenerFilters = {
      ...filters,
      min_roe: filters.min_roe != null ? filters.min_roe / 100 : undefined,
      min_operating_margin: filters.min_operating_margin != null ? filters.min_operating_margin / 100 : undefined,
      min_div_yield: filters.min_div_yield != null ? filters.min_div_yield / 100 : undefined,
      min_revenue_growth: filters.min_revenue_growth != null ? filters.min_revenue_growth / 100 : undefined,
    };
    runScreen({
      filters: convertedFilters,
      pea_only: peaOnly,
      sort_by: "composite_score",
      sort_desc: true,
      limit: 100,
    });
  }

  function handlePreset(name: string) {
    setActivePreset(name);
    runPreset(name, peaOnly, 50);
  }

  function handleScoreTickers() {
    const tickers = customTickers
      .split(/[\n,\s]+/)
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
    if (tickers.length === 0) return;
    scoreTickers(tickers);
  }

  const thCls =
    "px-3 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap";
  const tdCls = "px-3 py-2 text-sm whitespace-nowrap";

  const summarySignals = results?.summary?.signal_distribution ?? {};

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6">
      <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-5">Screener</h1>

      <div className="flex gap-5">
        {/* Left: Filter Panel */}
        <aside className="w-60 shrink-0 space-y-5">
          {/* Presets */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Presets</div>
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  onClick={() => handlePreset(p.name)}
                  className={clsx(
                    "px-2 py-1.5 text-xs rounded-md font-medium transition-colors border",
                    activePreset === p.name
                      ? "bg-emerald-600 border-emerald-600 text-white"
                      : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-emerald-400 hover:text-emerald-600 dark:hover:text-emerald-400"
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* PEA Toggle */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
            <Toggle checked={peaOnly} onChange={setPeaOnly} label="PEA Only" />
          </div>

          {/* Filters */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Filters</div>
            <FilterInput
              label="Max P/E"
              value={filters.max_pe}
              onChange={(v) => updateFilter("max_pe", v)}
            />
            <FilterInput
              label="Min ROE (%)"
              value={filters.min_roe}
              onChange={(v) => updateFilter("min_roe", v)}
              placeholder="e.g. 10"
            />
            <FilterInput
              label="Min Market Cap (M)"
              value={filters.min_market_cap}
              onChange={(v) => updateFilter("min_market_cap", v ? v * 1e6 : undefined)}
              placeholder="e.g. 1000"
            />
            <FilterInput
              label="Max D/E"
              value={filters.max_debt_equity}
              onChange={(v) => updateFilter("max_debt_equity", v)}
              placeholder="e.g. 1.5"
            />
            <FilterInput
              label="Min Op Margin (%)"
              value={filters.min_operating_margin}
              onChange={(v) => updateFilter("min_operating_margin", v)}
              placeholder="e.g. 10"
            />
            <FilterInput
              label="Min Div Yield (%)"
              value={filters.min_div_yield}
              onChange={(v) => updateFilter("min_div_yield", v)}
            />
            <FilterInput
              label="Min Score (0-100)"
              value={filters.min_composite_score}
              onChange={(v) => updateFilter("min_composite_score", v)}
              placeholder="e.g. 60"
            />
            <FilterInput
              label="Min Rev Growth (%)"
              value={filters.min_revenue_growth}
              onChange={(v) => updateFilter("min_revenue_growth", v)}
            />

            <button
              onClick={handleRunScreen}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60 transition-colors mt-2"
            >
              {loading ? <Spinner size={14} /> : <Play size={13} />}
              Run Screen
            </button>
          </div>

          {/* Custom Tickers */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Custom Tickers</div>
            <textarea
              value={customTickers}
              onChange={(e) => setCustomTickers(e.target.value)}
              placeholder={"AAPL, MSFT\nASML.AS\nMC.PA"}
              rows={4}
              className="w-full px-2.5 py-2 text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none font-mono"
            />
            <button
              onClick={handleScoreTickers}
              disabled={loading || !customTickers.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm rounded-md border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-60 transition-colors"
            >
              {loading ? <Spinner size={14} /> : <List size={13} />}
              Score Tickers
            </button>
          </div>
        </aside>

        {/* Right: Results */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Error */}
          {error && (
            <div className="p-3 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex justify-center items-center py-20">
              <Spinner size={32} />
            </div>
          )}

          {/* Summary Bar */}
          {results && !loading && (
            <>
              <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 rounded-lg bg-slate-100 dark:bg-slate-800/60 text-sm">
                <span className="font-semibold text-slate-700 dark:text-slate-300">
                  {results.summary.total_passed} stocks passed
                </span>
                <span className="text-slate-400">|</span>
                <span className="text-slate-600 dark:text-slate-400">
                  Avg Score: <strong>{formatNumber(results.summary.avg_score, 1)}</strong>
                </span>
                <span className="text-slate-400">|</span>
                {Object.entries(summarySignals).map(([signal, count]) => (
                  <span key={signal} className="text-xs text-slate-500">
                    {count} {signal}
                  </span>
                ))}
                <span className="ml-auto text-xs text-slate-400">
                  Screened: {results.summary.total_screened}
                </span>
              </div>

              {/* Results Table */}
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
                <div className="overflow-x-auto">
                  <table>
                    <thead className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800">
                      <tr>
                        <th className={thCls}>Ticker</th>
                        <th className={thCls}>Name</th>
                        <th className={thCls}>Score</th>
                        <th className={thCls}>Signal</th>
                        <th className={`${thCls} text-right`}>P/E</th>
                        <th className={`${thCls} text-right`}>ROE%</th>
                        <th className={`${thCls} text-right`}>Div%</th>
                        <th className={`${thCls} text-right`}>Growth%</th>
                        <th className={`${thCls} text-right`}>F-Score</th>
                        <th className={`${thCls} text-right`}>Mkt Cap</th>
                        <th className={thCls}>PEA</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.results.length === 0 && (
                        <tr>
                          <td colSpan={11} className="text-center py-10 text-sm text-slate-400">
                            No results match your filters.
                          </td>
                        </tr>
                      )}
                      {results.results.map((item) => (
                        <tr
                          key={item.ticker}
                          onClick={() => router.push(`/company/${item.ticker}`)}
                          className="border-t border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/30 cursor-pointer transition-colors"
                        >
                          <td className={tdCls}>
                            <span className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                              {item.ticker}
                            </span>
                          </td>
                          <td className={`${tdCls} max-w-[160px]`}>
                            <span className="truncate block text-slate-700 dark:text-slate-300">
                              {item.name}
                            </span>
                          </td>
                          <td className={tdCls}>
                            <ScoreBar score={item.composite_score} />
                          </td>
                          <td className={tdCls}>
                            <SignalBadge signal={item.signal} />
                          </td>
                          <td className={`${tdCls} text-right font-mono text-slate-600 dark:text-slate-400`}>
                            {formatNumber(item.pe, 1)}
                          </td>
                          <td
                            className={clsx(
                              `${tdCls} text-right font-mono`,
                              item.roe != null && item.roe > 0.10
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-slate-500"
                            )}
                          >
                            {item.roe != null ? formatPercent(item.roe * 100) : "—"}
                          </td>
                          <td className={`${tdCls} text-right font-mono text-slate-500`}>
                            {item.div_yield != null ? formatPercent(item.div_yield * 100) : "—"}
                          </td>
                          <td
                            className={clsx(
                              `${tdCls} text-right font-mono`,
                              item.revenue_growth != null && item.revenue_growth > 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-red-500 dark:text-red-400"
                            )}
                          >
                            {item.revenue_growth != null ? formatPercent(item.revenue_growth * 100) : "—"}
                          </td>
                          <td className={`${tdCls} text-right font-mono`}>
                            <span
                              className={clsx(
                                "font-semibold",
                                item.piotroski_f >= 7
                                  ? "text-emerald-600 dark:text-emerald-400"
                                  : item.piotroski_f >= 4
                                  ? "text-amber-600 dark:text-amber-400"
                                  : "text-red-500 dark:text-red-400"
                              )}
                            >
                              {item.piotroski_f}/9
                            </span>
                          </td>
                          <td className={`${tdCls} text-right font-mono text-slate-500`}>
                            {formatLargeNumber(item.market_cap)}
                          </td>
                          <td className={tdCls}>
                            <PeaBadge eligible={item.pea_eligible} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {/* Empty state */}
          {!results && !loading && !error && (
            <div className="flex flex-col items-center justify-center py-24 text-slate-400 gap-3">
              <RefreshCw size={32} className="opacity-30" />
              <p className="text-sm">Select a preset or configure filters to start screening.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
