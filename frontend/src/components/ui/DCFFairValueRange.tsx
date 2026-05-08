"use client";

import clsx from "clsx";
import type { DCFValuation } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import MoSBar from "./MoSBar";
import { AlertTriangle } from "lucide-react";

interface DCFFairValueRangeProps {
  valuation: DCFValuation;
  currentPrice: number;
}

/**
 * Horizontal bar showing DCF low → mid → high intrinsic value range
 * with the current price marker. MoS_Mid prominently displayed.
 *
 * Usage:
 *   <DCFFairValueRange valuation={data.valuation} currentPrice={data.metrics.price ?? 0} />
 */
export default function DCFFairValueRange({
  valuation,
  currentPrice,
}: DCFFairValueRangeProps) {
  const { fair_value_low, fair_value_mid, fair_value_high, mos_mid, warnings } =
    valuation;

  const hasDCF =
    fair_value_low != null || fair_value_mid != null || fair_value_high != null;

  if (!hasDCF) {
    return (
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2">
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
          DCF Fair Value
        </span>
        <p className="text-sm text-slate-400">No DCF data available.</p>
        {warnings.length > 0 && <WarningsList warnings={warnings} />}
      </div>
    );
  }

  // Build range for the SVG bar
  const low = fair_value_low ?? 0;
  const mid = fair_value_mid ?? low;
  const high = fair_value_high ?? mid;

  // Pad the display range so the current price marker is always visible
  const rangeMin = Math.min(low, currentPrice) * 0.85;
  const rangeMax = Math.max(high, currentPrice) * 1.1;
  const rangeSpan = rangeMax - rangeMin;

  function toPct(v: number) {
    return ((v - rangeMin) / rangeSpan) * 100;
  }

  const lowPct = toPct(low);
  const midPct = toPct(mid);
  const highPct = toPct(high);
  const pricePct = toPct(currentPrice);

  const priceBelowMid = currentPrice < (fair_value_mid ?? Infinity);

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
          DCF Fair Value Range
        </span>
        {mos_mid != null && (
          <span
            className={clsx(
              "text-sm font-bold font-mono",
              mos_mid >= 0
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-500 dark:text-red-400"
            )}
          >
            MoS {mos_mid >= 0 ? "+" : ""}
            {(mos_mid * 100).toFixed(1)}%
          </span>
        )}
      </div>

      {/* SVG bar */}
      <div className="relative" aria-label="DCF fair value range bar">
        <svg
          viewBox="0 0 400 56"
          className="w-full"
          aria-hidden="true"
        >
          {/* Track */}
          <rect x="0" y="22" width="400" height="12" rx="6" fill="#e2e8f0" className="dark:fill-slate-700" />

          {/* Low → High band */}
          <rect
            x={`${lowPct * 4}` /* 400 / 100 */}
            y="22"
            width={`${(highPct - lowPct) * 4}`}
            height="12"
            rx="4"
            fill={priceBelowMid ? "#6ee7b7" : "#fca5a5"}
            opacity="0.7"
          />

          {/* Mid marker */}
          <rect
            x={`${midPct * 4 - 1.5}`}
            y="18"
            width="3"
            height="20"
            rx="1.5"
            fill={priceBelowMid ? "#10b981" : "#ef4444"}
          />

          {/* Current price marker (diamond) */}
          <polygon
            points={`${pricePct * 4},14 ${pricePct * 4 + 6},22 ${pricePct * 4},30 ${pricePct * 4 - 6},22`}
            fill="#6366f1"
            stroke="white"
            strokeWidth="1.5"
          />

          {/* Labels */}
          {fair_value_low != null && (
            <text
              x={`${lowPct * 4}`}
              y="48"
              textAnchor="middle"
              fontSize="9"
              fill="#94a3b8"
            >
              Low
            </text>
          )}
          {fair_value_mid != null && (
            <text
              x={`${midPct * 4}`}
              y="48"
              textAnchor="middle"
              fontSize="9"
              fill="#94a3b8"
            >
              Mid
            </text>
          )}
          {fair_value_high != null && (
            <text
              x={`${highPct * 4}`}
              y="48"
              textAnchor="middle"
              fontSize="9"
              fill="#94a3b8"
            >
              High
            </text>
          )}
          <text
            x={`${pricePct * 4}`}
            y="10"
            textAnchor="middle"
            fontSize="9"
            fill="#6366f1"
            fontWeight="600"
          >
            Price
          </text>
        </svg>
      </div>

      {/* Value labels */}
      <div className="grid grid-cols-4 gap-2 text-center text-xs">
        <div>
          <div className="text-slate-400">Pessimistic</div>
          <div className="font-mono font-semibold text-slate-700 dark:text-slate-300">
            {formatCurrency(fair_value_low)}
          </div>
        </div>
        <div>
          <div className="text-slate-400">Base</div>
          <div
            className={clsx(
              "font-mono font-bold",
              priceBelowMid
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-500 dark:text-red-400"
            )}
          >
            {formatCurrency(fair_value_mid)}
          </div>
        </div>
        <div>
          <div className="text-slate-400">Optimistic</div>
          <div className="font-mono font-semibold text-slate-700 dark:text-slate-300">
            {formatCurrency(fair_value_high)}
          </div>
        </div>
        <div>
          <div className="text-indigo-500">Current</div>
          <div className="font-mono font-semibold text-indigo-600 dark:text-indigo-400">
            {formatCurrency(currentPrice)}
          </div>
        </div>
      </div>

      {/* MoS bar */}
      {mos_mid != null && (
        <MoSBar mos={mos_mid} label="Mid-case MoS" />
      )}

      {/* Warnings */}
      {warnings.length > 0 && <WarningsList warnings={warnings} />}
    </div>
  );
}

function WarningsList({ warnings }: { warnings: string[] }) {
  return (
    <ul className="space-y-1">
      {warnings.map((w, i) => (
        <li
          key={i}
          className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400"
        >
          <AlertTriangle size={12} className="shrink-0 mt-0.5" aria-hidden />
          {w}
        </li>
      ))}
    </ul>
  );
}
