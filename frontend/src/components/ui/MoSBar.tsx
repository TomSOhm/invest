"use client";

import clsx from "clsx";

interface MoSBarProps {
  mos: number;
  label?: string;
  className?: string;
}

/**
 * Compact horizontal bar centred on 0. Scale: -50% to +50%.
 * Green when positive (undervalued), red when negative (overvalued).
 *
 * Usage:
 *   <MoSBar mos={0.23} label="DCF Mid MoS" />
 */
export default function MoSBar({ mos, label, className }: MoSBarProps) {
  // Clamp to -50..+50 range for visual
  const clamped = Math.max(-0.5, Math.min(0.5, mos));
  const pct = Math.abs(clamped) / 0.5; // 0..1 fraction of half-bar
  const positive = mos >= 0;

  return (
    <div className={clsx("space-y-1", className)}>
      {label && (
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {label}
          </span>
          <span
            className={clsx(
              "text-xs font-mono font-bold",
              positive
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-500 dark:text-red-400"
            )}
          >
            {positive ? "+" : ""}
            {(mos * 100).toFixed(1)}%
          </span>
        </div>
      )}
      <div
        className="relative h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden"
        role="meter"
        aria-valuenow={Math.round(mos * 100)}
        aria-valuemin={-50}
        aria-valuemax={50}
        aria-label={label ?? "Margin of Safety"}
      >
        {/* Center tick */}
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-300 dark:bg-slate-600" />
        {/* Bar */}
        <div
          className={clsx(
            "absolute top-0 bottom-0 rounded-full transition-all duration-500",
            positive ? "bg-emerald-500" : "bg-red-500"
          )}
          style={{
            left: positive ? "50%" : `calc(50% - ${pct * 50}%)`,
            width: `${pct * 50}%`,
          }}
        />
      </div>
      {!label && (
        <div className="flex justify-between text-[10px] text-slate-400">
          <span>-50%</span>
          <span
            className={clsx(
              "font-mono font-bold text-xs",
              positive
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-500 dark:text-red-400"
            )}
          >
            {positive ? "+" : ""}
            {(mos * 100).toFixed(1)}%
          </span>
          <span>+50%</span>
        </div>
      )}
    </div>
  );
}
