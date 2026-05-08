"use client";

import clsx from "clsx";
import { TrendingUp, TrendingDown, CheckCircle, XCircle, Minus } from "lucide-react";
import type { MomentumSignals } from "@/lib/types";
import { formatPercent, formatNumber } from "@/lib/formatters";
import MetricInfo from "./MetricInfo";

interface MomentumPanelProps {
  momentum: MomentumSignals;
}

/**
 * Card showing momentum metrics: 12-1 momentum, RS_3m, MA flags,
 * volume surge, EPS revisions, SUE z-score.
 *
 * Usage:
 *   <MomentumPanel momentum={data.momentum} />
 */
export default function MomentumPanel({ momentum }: MomentumPanelProps) {
  const {
    momentum_12_1,
    rs_3m,
    above_50dma,
    above_200dma,
    golden_cross,
    volume_surge,
    eps_revision_30d,
    eps_revision_90d,
    sue_z_score,
    sentiment_30d,
    sentiment_trend,
  } = momentum;

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-4">
      <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
        Momentum
      </span>

      {/* Row 1: Price momentum metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricTile
          label="12-1 Momentum"
          value={
            momentum_12_1 != null
              ? formatPercent(momentum_12_1 * 100)
              : "—"
          }
          positive={momentum_12_1 != null ? momentum_12_1 > 0 : null}
          metricId="momentum_12_1"
        />
        <MetricTile
          label="RS 3-Month"
          value={rs_3m != null ? formatPercent(rs_3m * 100) : "—"}
          positive={rs_3m != null ? rs_3m > 0 : null}
          metricId="rs_3m"
        />
        <MetricTile
          label="Volume Surge"
          value={volume_surge != null ? `${volume_surge.toFixed(2)}x` : "—"}
          positive={volume_surge != null ? volume_surge > 1.5 : null}
          metricId="volume_surge"
        />
        <MetricTile
          label="SUE Z-Score"
          value={sue_z_score != null ? sue_z_score.toFixed(2) : "—"}
          positive={sue_z_score != null ? sue_z_score >= 1.5 : null}
          highlight={
            sue_z_score != null && sue_z_score >= 1.5
              ? "Strong beat"
              : undefined
          }
          metricId="sue_z_score"
        />
      </div>

      {/* Row 2: Boolean MA chips */}
      <div className="flex flex-wrap gap-2">
        <BoolChip label="Above 50 DMA" value={above_50dma} metricId="above_50dma" />
        <BoolChip label="Above 200 DMA" value={above_200dma} metricId="above_200dma" />
        <BoolChip label="Golden Cross" value={golden_cross} metricId="golden_cross" />
      </div>

      {/* Row 3: EPS revisions */}
      <div className="space-y-1.5">
        <div className="text-xs text-slate-500">EPS Revisions</div>
        <div className="grid grid-cols-2 gap-2">
          <EPSRevisionBar
            label="30 days"
            value={eps_revision_30d ?? null}
            metricId="eps_revision_30d"
          />
          <EPSRevisionBar
            label="90 days"
            value={eps_revision_90d ?? null}
            metricId="eps_revision_90d"
          />
        </div>
      </div>

      {/* Row 4: Sentiment */}
      {(sentiment_30d != null || sentiment_trend != null) && (
        <div className="grid grid-cols-2 gap-3">
          {sentiment_30d != null && (
            <MetricTile
              label="Sentiment 30d"
              value={sentiment_30d.toFixed(2)}
              positive={sentiment_30d > 0}
              metricId="sentiment_30d"
            />
          )}
          {sentiment_trend != null && (
            <MetricTile
              label="Sentiment Trend"
              value={sentiment_trend > 0 ? "Improving" : "Declining"}
              positive={sentiment_trend > 0}
              metricId="sentiment_trend"
            />
          )}
        </div>
      )}
    </div>
  );
}

function MetricTile({
  label,
  value,
  positive,
  highlight,
  metricId,
}: {
  label: string;
  value: string;
  positive?: boolean | null;
  highlight?: string;
  metricId?: string;
}) {
  return (
    <div className="rounded-md bg-slate-50 dark:bg-slate-800/60 p-2.5 space-y-0.5">
      <div className="text-xs text-slate-400 inline-flex items-center gap-1">
        {label}
        {metricId && <MetricInfo metricId={metricId} size={11} />}
      </div>
      <div
        className={clsx(
          "text-sm font-mono font-bold",
          positive === true &&
            "text-emerald-600 dark:text-emerald-400",
          positive === false && "text-red-500 dark:text-red-400",
          positive == null && "text-slate-700 dark:text-slate-300"
        )}
      >
        {value}
      </div>
      {highlight && (
        <div className="text-xs text-emerald-500 font-medium">{highlight}</div>
      )}
    </div>
  );
}

function BoolChip({
  label,
  value,
  metricId,
}: {
  label: string;
  value?: boolean | null;
  metricId?: string;
}) {
  const known = value != null;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium",
        !known && "bg-slate-100 text-slate-400 dark:bg-slate-800",
        known &&
          value &&
          "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
        known &&
          !value &&
          "bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400"
      )}
    >
      {!known ? (
        <Minus size={10} aria-hidden />
      ) : value ? (
        <CheckCircle size={10} aria-hidden />
      ) : (
        <XCircle size={10} aria-hidden />
      )}
      {label}
      {metricId && <MetricInfo metricId={metricId} size={11} />}
    </span>
  );
}

function EPSRevisionBar({
  label,
  value,
  metricId,
}: {
  label: string;
  value: number | null;
  metricId?: string;
}) {
  const pct = value != null ? value * 100 : null;
  const barWidth = pct != null ? Math.min(100, Math.abs(pct) * 2) : 0;
  const positive = pct != null && pct >= 0;

  return (
    <div className="space-y-0.5">
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400 inline-flex items-center gap-1">
          {label}
          {metricId && <MetricInfo metricId={metricId} size={11} />}
        </span>
        {pct != null ? (
          <span
            className={clsx(
              "text-xs font-mono font-semibold",
              positive
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-500 dark:text-red-400"
            )}
          >
            {positive ? "+" : ""}
            {pct.toFixed(1)}%
          </span>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )}
      </div>
      <div className="h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
        <div
          className={clsx(
            "h-full rounded-full transition-all",
            positive ? "bg-emerald-500" : "bg-red-500"
          )}
          style={{ width: `${barWidth}%` }}
        />
      </div>
    </div>
  );
}
