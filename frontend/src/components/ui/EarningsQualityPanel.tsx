"use client";

import clsx from "clsx";
import { Check, X, AlertTriangle } from "lucide-react";
import type { QualitySignals } from "@/lib/types";
import { formatNumber, formatPercent, formatCurrency } from "@/lib/formatters";

interface EarningsQualityPanelProps {
  quality: QualitySignals;
}

/**
 * Grid of 6 quality metrics: F-Score, Altman Z, Beneish M, Sloan, CCR, Graham MoS.
 *
 * Usage:
 *   <EarningsQualityPanel quality={data.quality} />
 */
export default function EarningsQualityPanel({
  quality,
}: EarningsQualityPanelProps) {
  const f = quality.piotroski_f;
  const z = quality.altman_z;
  const m = quality.m_score;
  const sloan = quality.sloan_accruals;
  const ccr = quality.cash_conversion_ratio_5y;
  const grahamMos = quality.graham_mos;

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-4">
      <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
        Earnings Quality
      </span>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {/* Piotroski F-Score */}
        <div className="space-y-1.5">
          <div className="text-xs text-slate-500">Piotroski F-Score</div>
          {f != null ? (
            <>
              <div className="flex gap-0.5">
                {Array.from({ length: 9 }).map((_, i) => (
                  <div
                    key={i}
                    className={clsx(
                      "h-3 flex-1 rounded-sm transition-colors",
                      i < f
                        ? "bg-emerald-500"
                        : "bg-slate-200 dark:bg-slate-700"
                    )}
                    aria-hidden="true"
                  />
                ))}
              </div>
              <div
                className={clsx(
                  "text-sm font-bold",
                  f >= 7
                    ? "text-emerald-600 dark:text-emerald-400"
                    : f >= 4
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-red-500"
                )}
              >
                {f}/9{" "}
                <span className="font-normal text-xs">
                  {f >= 7 ? "Strong" : f >= 4 ? "Moderate" : "Weak"}
                </span>
              </div>
            </>
          ) : (
            <span className="text-slate-400 text-sm">—</span>
          )}
        </div>

        {/* Altman Z */}
        <div className="space-y-1.5">
          <div className="text-xs text-slate-500">Altman Z-Score</div>
          {z != null ? (
            <>
              <div
                className={clsx(
                  "text-lg font-bold font-mono",
                  quality.altman_zone === "Safe"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : quality.altman_zone === "Grey"
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-red-500"
                )}
              >
                {z.toFixed(2)}
              </div>
              <ZoneBadge zone={quality.altman_zone} />
            </>
          ) : (
            <span className="text-slate-400 text-sm">—</span>
          )}
        </div>

        {/* Beneish M-Score */}
        <div className="space-y-1.5">
          <div className="text-xs text-slate-500">Beneish M-Score</div>
          {m != null ? (
            <>
              <div
                className={clsx(
                  "text-lg font-bold font-mono",
                  m > -1.78 ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
                )}
              >
                {m.toFixed(2)}
              </div>
              {m > -1.78 ? (
                <div className="flex items-center gap-1 text-xs text-red-500">
                  <AlertTriangle size={11} aria-hidden />
                  Possible manipulation
                </div>
              ) : (
                <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <Check size={11} aria-hidden />
                  Low risk
                </div>
              )}
            </>
          ) : (
            <span className="text-slate-400 text-sm">—</span>
          )}
        </div>

        {/* Sloan Accruals */}
        <div className="space-y-1.5">
          <div className="text-xs text-slate-500">Sloan Accruals</div>
          {sloan != null ? (
            <>
              <div
                className={clsx(
                  "text-lg font-bold font-mono",
                  sloan > 0.1 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"
                )}
              >
                {(sloan * 100).toFixed(1)}%
              </div>
              {sloan > 0.1 ? (
                <div className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                  <AlertTriangle size={11} aria-hidden />
                  Concern (&gt;10%)
                </div>
              ) : (
                <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <Check size={11} aria-hidden />
                  Acceptable
                </div>
              )}
            </>
          ) : (
            <span className="text-slate-400 text-sm">—</span>
          )}
        </div>

        {/* Cash Conversion Ratio */}
        <div className="space-y-1.5">
          <div className="text-xs text-slate-500">CCR 5yr</div>
          {ccr != null ? (
            <>
              <div
                className={clsx(
                  "text-lg font-bold font-mono",
                  ccr < 0.7 ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
                )}
              >
                {ccr.toFixed(2)}x
              </div>
              {ccr < 0.7 ? (
                <div className="flex items-center gap-1 text-xs text-red-500">
                  <X size={11} aria-hidden />
                  Concern (&lt;0.7)
                </div>
              ) : (
                <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <Check size={11} aria-hidden />
                  Good
                </div>
              )}
            </>
          ) : (
            <span className="text-slate-400 text-sm">—</span>
          )}
        </div>

        {/* Graham MoS */}
        <div className="space-y-1.5">
          <div className="text-xs text-slate-500">Graham MoS</div>
          {grahamMos != null ? (
            <>
              <div
                className={clsx(
                  "text-lg font-bold font-mono",
                  grahamMos > 0
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-red-500"
                )}
              >
                {grahamMos > 0 ? "+" : ""}
                {grahamMos.toFixed(1)}%
              </div>
              <div className="h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={clsx(
                    "h-full rounded-full transition-all",
                    grahamMos > 0 ? "bg-emerald-500" : "bg-red-500"
                  )}
                  style={{
                    width: `${Math.min(100, Math.abs(grahamMos))}%`,
                  }}
                />
              </div>
              <div className="text-xs text-slate-400">
                {grahamMos > 0 ? "Undervalued vs Graham" : "Overvalued vs Graham"}
              </div>
            </>
          ) : (
            <span className="text-slate-400 text-sm">—</span>
          )}
        </div>
      </div>
    </div>
  );
}

function ZoneBadge({
  zone,
}: {
  zone?: "Safe" | "Grey" | "Distress" | null;
}) {
  if (!zone) return null;
  const cfg = {
    Safe: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
    Grey: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    Distress: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold",
        cfg[zone]
      )}
    >
      {zone} Zone
    </span>
  );
}
