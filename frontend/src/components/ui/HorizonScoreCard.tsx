"use client";

import { useState } from "react";
import { CheckCircle, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import type { Horizon, HorizonScoring } from "@/lib/types";
import { scoreToColor } from "@/lib/constants";
import SignalBadge from "./SignalBadge";
import MetricInfo from "./MetricInfo";

const HORIZON_LABELS: Record<Horizon, string> = {
  long_term: "Long Term",
  medium_term: "Medium Term",
  short_term: "Short Term",
};

const HORIZON_SCORE_ID: Record<Horizon, string> = {
  long_term: "score_lt",
  medium_term: "score_mt",
  short_term: "score_st",
};

interface HorizonScoreCardProps {
  horizon: Horizon;
  scoring: HorizonScoring;
}

/**
 * Displays score, signal, passes_gates indicator, and blockers for a horizon.
 * Usage:
 *   <HorizonScoreCard horizon="long_term" scoring={data.horizons.long_term} />
 */
export default function HorizonScoreCard({
  horizon,
  scoring,
}: HorizonScoreCardProps) {
  const [blockersExpanded, setBlockersExpanded] = useState(false);
  const color = scoreToColor(scoring.score);
  const showCTOPill =
    horizon === "short_term" && scoring.recommended_account === "CTO";

  const visibleBlockers =
    !blockersExpanded && scoring.blockers.length > 3
      ? scoring.blockers.slice(0, 3)
      : scoring.blockers;

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide inline-flex items-center gap-1">
          {HORIZON_LABELS[horizon]}
          <MetricInfo metricId={HORIZON_SCORE_ID[horizon]} size={12} />
        </span>
        <div className="flex items-center gap-2">
          {showCTOPill && (
            <span className="px-2 py-0.5 text-xs font-semibold rounded bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 inline-flex items-center gap-1">
              CTO
              <MetricInfo metricId="recommended_account" size={11} />
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <SignalBadge signal={scoring.signal} />
            <MetricInfo metricId="signal" size={12} />
          </span>
        </div>
      </div>

      {/* Score + gate row */}
      <div className="flex items-center gap-4">
        {/* Big score number */}
        <div
          className="text-4xl font-bold font-mono tabular-nums"
          style={{ color }}
          aria-label={`Score ${Math.round(scoring.score)}`}
        >
          {Math.round(scoring.score)}
        </div>

        {/* Score bar */}
        <div className="flex-1 space-y-1">
          <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${scoring.score}%`, backgroundColor: color }}
            />
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            {scoring.passes_gates ? (
              <>
                <CheckCircle
                  size={13}
                  className="text-emerald-500 shrink-0"
                  aria-hidden
                />
                <span className="text-emerald-600 dark:text-emerald-400 font-medium inline-flex items-center gap-1">
                  All gates passed
                  <MetricInfo metricId="passes_gates" size={11} />
                </span>
              </>
            ) : (
              <>
                <XCircle
                  size={13}
                  className="text-red-500 shrink-0"
                  aria-hidden
                />
                <span className="text-red-500 dark:text-red-400 font-medium inline-flex items-center gap-1">
                  {scoring.blockers.length} gate
                  {scoring.blockers.length !== 1 ? "s" : ""} failing
                  <MetricInfo metricId="passes_gates" size={11} />
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Blockers list */}
      {scoring.blockers.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-500 dark:text-slate-400 inline-flex items-center gap-1">
            Blockers
            <MetricInfo metricId="blockers" size={11} />
          </div>
          <ul className="space-y-0.5">
            {visibleBlockers.map((b) => (
              <li
                key={b}
                className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5"
              >
                <XCircle size={10} className="shrink-0" aria-hidden />
                {b}
              </li>
            ))}
          </ul>
          {scoring.blockers.length > 3 && (
            <button
              onClick={() => setBlockersExpanded((x) => !x)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              aria-expanded={blockersExpanded}
            >
              {blockersExpanded ? (
                <>
                  <ChevronUp size={12} /> Show less
                </>
              ) : (
                <>
                  <ChevronDown size={12} /> +
                  {scoring.blockers.length - 3} more
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
