"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Play, List, RefreshCw } from "lucide-react";
import { useScreener } from "@/hooks/useScreener";
import type { Horizon, ScreenerResultItem, PresetMeta } from "@/lib/types";
import { formatNumber, formatPercent, formatLargeNumber } from "@/lib/formatters";
import SignalBadge from "@/components/ui/SignalBadge";
import PeaBadge from "@/components/ui/PeaBadge";
import Spinner from "@/components/ui/Spinner";
import { ScoreBar } from "@/components/ui/ScoreGauge";
import HorizonSelector from "@/components/ui/HorizonSelector";
import CTOWarningBanner from "@/components/ui/CTOWarningBanner";
import MetricInfo from "@/components/ui/MetricInfo";
import { fetchScreenerPresets } from "@/lib/api";
import clsx from "clsx";

// Fallback preset list shown before API resolves
const FALLBACK_PRESETS: PresetMeta[] = [
  { name: "pea_value", horizon: "long_term", description: "PEA Value", recommended_account: "PEA" },
  { name: "pea_quality", horizon: "long_term", description: "PEA Quality", recommended_account: "PEA" },
  { name: "dividend", horizon: "long_term", description: "Dividend", recommended_account: "PEA" },
  { name: "global", horizon: "long_term", description: "Global Best" },
];

function getScoreForHorizon(item: ScreenerResultItem, horizon: Horizon): number {
  if (horizon === "long_term") return item.score_lt;
  if (horizon === "medium_term") return item.score_mt;
  return item.score_st;
}

function getSignalForHorizon(item: ScreenerResultItem, horizon: Horizon): string {
  if (horizon === "long_term") return item.signal_lt;
  if (horizon === "medium_term") return item.signal_mt;
  return item.signal_st;
}

function getKeyMetricForHorizon(
  item: ScreenerResultItem,
  horizon: Horizon
): { label: string; value: string } {
  if (horizon === "long_term") {
    return { label: "P/E", value: formatNumber(item.pe, 1) };
  }
  if (horizon === "medium_term") {
    return {
      label: "DCF MoS",
      value: item.dcf_mos_mid != null ? formatPercent(item.dcf_mos_mid * 100) : "—",
    };
  }
  // short_term
  return {
    label: "Score ST",
    value: formatNumber(item.score_st, 1),
  };
}

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
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" || e.key === " " ? onChange(!checked) : undefined}
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

interface CustomFilters {
  max_pe?: number;
  min_roe?: number;
  min_market_cap?: number;
  max_debt_equity?: number;
  min_operating_margin?: number;
  min_div_yield?: number;
  min_revenue_growth?: number;
}

const DEFAULT_FILTERS: CustomFilters = {};

export default function ScreenerPage() {
  const router = useRouter();
  const { results, loading, error, runScreen, runPreset, scoreTickers } = useScreener();
  const [horizon, setHorizon] = useState<Horizon>("long_term");
  const [filters, setFilters] = useState<CustomFilters>(DEFAULT_FILTERS);
  const [peaOnly, setPeaOnly] = useState(false);
  const [customTickers, setCustomTickers] = useState("");
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [presets, setPresets] = useState<PresetMeta[]>(FALLBACK_PRESETS);

  useEffect(() => {
    fetchScreenerPresets()
      .then(setPresets)
      .catch(() => {
        // fallback already set
      });
  }, []);

  function updateFilter<K extends keyof CustomFilters>(key: K, val: CustomFilters[K]) {
    setFilters((f) => ({ ...f, [key]: val }));
    setActivePreset(null);
  }

  function handleRunScreen() {
    setActivePreset(null);
    const customFiltersPayload: Record<string, unknown> = {};
    if (filters.max_pe != null) customFiltersPayload.max_pe = filters.max_pe;
    if (filters.min_roe != null) customFiltersPayload.min_roe = filters.min_roe / 100;
    if (filters.min_market_cap != null) customFiltersPayload.min_market_cap = filters.min_market_cap * 1e6;
    if (filters.max_debt_equity != null) customFiltersPayload.max_debt_equity = filters.max_debt_equity;
    if (filters.min_operating_margin != null) customFiltersPayload.min_operating_margin = filters.min_operating_margin / 100;
    if (filters.min_div_yield != null) customFiltersPayload.min_div_yield = filters.min_div_yield / 100;
    if (filters.min_revenue_growth != null) customFiltersPayload.min_revenue_growth = filters.min_revenue_growth / 100;

    runScreen({
      horizon,
      custom_filters: Object.keys(customFiltersPayload).length > 0 ? customFiltersPayload : null,
      pea_only: peaOnly,
      sort_by: "score",
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
    scoreTickers(tickers, horizon);
  }

  const selectedPresetMeta = presets.find((p) => p.name === activePreset);
  const showCTOBanner =
    horizon === "short_term" ||
    selectedPresetMeta?.horizon === "short_term";

  const thCls =
    "px-3 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap";
  const tdCls = "px-3 py-2 text-sm whitespace-nowrap";

  const summarySignals = results?.summary?.signal_distribution ?? {};

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">Screener</h1>
        <HorizonSelector value={horizon} onChange={setHorizon} />
      </div>

      {/* CTO Warning for short-term */}
      {showCTOBanner && (
        <div className="mb-4">
          <CTOWarningBanner />
        </div>
      )}

      <div className="flex gap-5">
        {/* Left: Filter Panel */}
        <aside className="w-72 shrink-0 space-y-5">
          {/* Presets */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Presets</div>
            <div className="flex flex-col gap-2">
              {presets.map((p) => (
                <button
                  key={p.name}
                  onClick={() => handlePreset(p.name)}
                  className={clsx(
                    "w-full p-3 text-left rounded-md transition-colors border relative",
                    activePreset === p.name
                      ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30"
                      : "border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  )}
                >
                  <div className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                    {p.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </div>
                  {p.description && (
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 leading-snug line-clamp-3 mt-0.5">
                      {p.description}
                    </div>
                  )}
                  {p.horizon === "short_term" && (
                    <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-orange-400" title="Short-term preset" />
                  )}
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
              onChange={(v) => updateFilter("min_market_cap", v)}
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
                <span className="font-semibold text-slate-700 dark:text-slate-300 inline-flex items-center gap-1">
                  {results.summary.total_passed} stocks passed
                  <MetricInfo metricId="total_passed" size={12} />
                </span>
                <span className="text-slate-400">|</span>
                <span className="text-slate-600 dark:text-slate-400 inline-flex items-center gap-1">
                  Avg Score:{" "}
                  <strong>{formatNumber(results.summary.avg_score, 1)}</strong>
                  <MetricInfo metricId="avg_score_lt" size={12} />
                </span>
                <span className="text-slate-400">|</span>
                {Object.entries(summarySignals).map(([signal, count]) => (
                  <span key={signal} className="text-xs text-slate-500">
                    {count} {signal}
                  </span>
                ))}
                <MetricInfo metricId="signal_distribution" size={12} />
                <span className="ml-auto text-xs text-slate-400 capitalize">
                  {results.summary.horizon.replace("_", " ")}
                </span>
              </div>

              {/* Results Table */}
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800">
                      <tr>
                        <th className={thCls}>Ticker</th>
                        <th className={thCls}>Name</th>
                        {/* Score columns — active horizon highlighted */}
                        <th
                          className={clsx(
                            thCls,
                            horizon === "long_term" && "bg-emerald-50/50 dark:bg-emerald-900/10"
                          )}
                        >
                          <span className="inline-flex items-center gap-1">
                            Score LT
                            <MetricInfo metricId="score_lt" size={11} />
                          </span>
                        </th>
                        <th
                          className={clsx(
                            thCls,
                            horizon === "medium_term" && "bg-emerald-50/50 dark:bg-emerald-900/10"
                          )}
                        >
                          <span className="inline-flex items-center gap-1">
                            Score MT
                            <MetricInfo metricId="score_mt" size={11} />
                          </span>
                        </th>
                        <th
                          className={clsx(
                            thCls,
                            horizon === "short_term" && "bg-emerald-50/50 dark:bg-emerald-900/10"
                          )}
                        >
                          <span className="inline-flex items-center gap-1">
                            Score ST
                            <MetricInfo metricId="score_st" size={11} />
                          </span>
                        </th>
                        <th className={thCls}>
                          <span className="inline-flex items-center gap-1">
                            Signal
                            <MetricInfo metricId="signal" size={11} />
                          </span>
                        </th>
                        <th className={thCls}>Sector</th>
                        <th className={`${thCls} text-right`}>Mkt Cap</th>
                        <th className={`${thCls} text-right`}>
                          <span className="inline-flex items-center gap-1">
                            {horizon === "long_term"
                              ? "P/E"
                              : horizon === "medium_term"
                              ? "DCF MoS"
                              : "ROE%"}
                            <MetricInfo
                              metricId={
                                horizon === "long_term"
                                  ? "pe"
                                  : horizon === "medium_term"
                                  ? "dcf_mos"
                                  : "roe"
                              }
                              size={11}
                            />
                          </span>
                        </th>
                        <th className={`${thCls} text-right`}>
                          <span className="inline-flex items-center gap-1">
                            F-Score
                            <MetricInfo metricId="piotroski_f" size={11} />
                          </span>
                        </th>
                        <th className={thCls}>PEA</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.results.length === 0 && (
                        <tr>
                          <td
                            colSpan={11}
                            className="text-center py-10 text-sm text-slate-400"
                          >
                            No results match your filters.
                          </td>
                        </tr>
                      )}
                      {results.results.map((item) => {
                        const activeScore = getScoreForHorizon(item, horizon);
                        const activeSignal = getSignalForHorizon(item, horizon);
                        const keyMetric = getKeyMetricForHorizon(item, horizon);

                        return (
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
                            <td className={`${tdCls} max-w-[140px]`}>
                              <span className="truncate block text-slate-700 dark:text-slate-300">
                                {item.name ?? "—"}
                              </span>
                            </td>
                            <td
                              className={clsx(
                                tdCls,
                                horizon === "long_term" && "bg-emerald-50/30 dark:bg-emerald-900/5"
                              )}
                            >
                              <ScoreBar score={item.score_lt} />
                            </td>
                            <td
                              className={clsx(
                                tdCls,
                                horizon === "medium_term" && "bg-emerald-50/30 dark:bg-emerald-900/5"
                              )}
                            >
                              <ScoreBar score={item.score_mt} />
                            </td>
                            <td
                              className={clsx(
                                tdCls,
                                horizon === "short_term" && "bg-emerald-50/30 dark:bg-emerald-900/5"
                              )}
                            >
                              <ScoreBar score={item.score_st} />
                            </td>
                            <td className={tdCls}>
                              <SignalBadge signal={activeSignal} />
                            </td>
                            <td className={`${tdCls} text-slate-500 text-xs max-w-[100px]`}>
                              <span className="truncate block">{item.sector ?? "—"}</span>
                            </td>
                            <td className={`${tdCls} text-right font-mono text-slate-500`}>
                              {formatLargeNumber(item.market_cap)}
                            </td>
                            <td className={`${tdCls} text-right font-mono text-slate-600 dark:text-slate-400`}>
                              <span title={keyMetric.label}>{keyMetric.value}</span>
                            </td>
                            <td className={`${tdCls} text-right font-mono`}>
                              {item.piotroski_f != null ? (
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
                              ) : (
                                <span className="text-slate-400">—</span>
                              )}
                            </td>
                            <td className={tdCls}>
                              <PeaBadge eligible={item.pea_eligible} />
                            </td>
                          </tr>
                        );
                      })}
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
