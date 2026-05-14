"use client";

import clsx from "clsx";
import Card from "@/components/ui/Card";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import type { AnalystChange, AnalystRatings } from "@/lib/types";

function AnalystBar({
  strongBuy,
  buy,
  hold,
  sell,
  strongSell,
}: {
  strongBuy: number;
  buy: number;
  hold: number;
  sell: number;
  strongSell: number;
}) {
  const total = strongBuy + buy + hold + sell + strongSell;
  if (total === 0)
    return <p className="text-sm text-slate-400">No analyst rating data</p>;

  const pct = (n: number) => `${((n / total) * 100).toFixed(0)}%`;

  return (
    <div className="space-y-2">
      <div className="flex h-4 rounded-full overflow-hidden gap-px">
        {strongBuy > 0 && (
          <div className="bg-emerald-600" style={{ width: pct(strongBuy) }} title={`Strong Buy: ${strongBuy}`} />
        )}
        {buy > 0 && (
          <div className="bg-emerald-400" style={{ width: pct(buy) }} title={`Buy: ${buy}`} />
        )}
        {hold > 0 && (
          <div className="bg-amber-400" style={{ width: pct(hold) }} title={`Hold: ${hold}`} />
        )}
        {sell > 0 && (
          <div className="bg-red-400" style={{ width: pct(sell) }} title={`Sell: ${sell}`} />
        )}
        {strongSell > 0 && (
          <div className="bg-red-600" style={{ width: pct(strongSell) }} title={`Strong Sell: ${strongSell}`} />
        )}
      </div>
      <div className="flex gap-4 text-xs text-slate-500">
        {strongBuy > 0 && <span className="text-emerald-600 dark:text-emerald-400">SB: {strongBuy}</span>}
        {buy > 0 && <span className="text-emerald-500">B: {buy}</span>}
        {hold > 0 && <span className="text-amber-500">H: {hold}</span>}
        {sell > 0 && <span className="text-red-400">S: {sell}</span>}
        {strongSell > 0 && <span className="text-red-600">SS: {strongSell}</span>}
        <span className="ml-auto">Total: {total}</span>
      </div>
    </div>
  );
}

function RecentChangesList({ changes }: { changes: AnalystChange[] }) {
  if (changes.length === 0) return null;
  return (
    <div
      role="region"
      aria-label="Recent analyst rating changes"
      className="space-y-1.5 pt-2 border-t border-slate-100 dark:border-slate-800"
    >
      <div className="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
        Recent Changes
      </div>
      <ul className="space-y-0.5">
        {changes.slice(0, 3).map((c, i) => (
          <li
            key={`${c.date}-${c.firm}-${i}`}
            className="text-xs flex items-center gap-2 text-slate-600 dark:text-slate-400"
          >
            <span className="font-mono text-slate-400">{c.date}</span>
            <span className="font-semibold">{c.firm}</span>
            <span className="text-slate-400">
              {c.from_grade} →{" "}
              <span
                className={clsx(
                  c.action === "up" && "text-emerald-600 dark:text-emerald-400",
                  c.action === "down" && "text-red-500 dark:text-red-400",
                )}
              >
                {c.to_grade}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GrowthEstimateTile({ value }: { value: number | null | undefined }) {
  if (value == null) return null;
  const positive = value > 0;
  return (
    <div className="flex justify-between items-center pt-2 border-t border-slate-100 dark:border-slate-800">
      <span className="text-xs text-slate-500 dark:text-slate-400">FY Growth Est.</span>
      <span
        className={clsx(
          "text-sm font-mono font-semibold tabular-nums",
          positive ? "text-emerald-600 dark:text-emerald-400" : "text-red-500 dark:text-red-400",
        )}
      >
        {formatPercent(value * 100)}
      </span>
    </div>
  );
}

interface Props {
  analyst: AnalystRatings;
  currentPrice?: number;
}

export default function AnalystTargetsPanel({ analyst }: Props) {
  return (
    <Card title="Analyst Consensus">
      <div className="space-y-3">
        <AnalystBar
          strongBuy={analyst.strong_buy}
          buy={analyst.buy}
          hold={analyst.hold}
          sell={analyst.sell}
          strongSell={analyst.strong_sell}
        />
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-xs text-slate-400">Low</div>
            <div className="font-mono text-sm font-semibold text-slate-700 dark:text-slate-300">
              {formatCurrency(analyst.target_low)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Mean</div>
            <div className="font-mono text-sm font-bold text-slate-900 dark:text-slate-100">
              {formatCurrency(analyst.target_mean)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">High</div>
            <div className="font-mono text-sm font-semibold text-slate-700 dark:text-slate-300">
              {formatCurrency(analyst.target_high)}
            </div>
          </div>
        </div>
        <GrowthEstimateTile value={analyst.growth_estimate_fy} />
        {analyst.recent_changes && (
          <RecentChangesList changes={analyst.recent_changes} />
        )}
      </div>
    </Card>
  );
}
