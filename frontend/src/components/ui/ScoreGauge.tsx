"use client";

import { scoreToColor } from "@/lib/constants";

interface ScoreGaugeProps {
  score: number | null | undefined;
  size?: number;
}

export default function ScoreGauge({ score, size = 80 }: ScoreGaugeProps) {
  if (score == null) {
    return (
      <div
        style={{ width: size, height: size }}
        className="flex items-center justify-center rounded-full border-4 border-slate-200 dark:border-slate-700 text-slate-400 text-sm font-bold"
      >
        —
      </div>
    );
  }

  const clampedScore = Math.max(0, Math.min(100, score));
  const color = scoreToColor(clampedScore);
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  // Semi-circle: 180 degrees of the arc represents 0-100
  const semiCircumference = circumference / 2;
  const offset = semiCircumference - (clampedScore / 100) * semiCircumference;

  const cx = size / 2;

  return (
    <div className="relative flex flex-col items-center" style={{ width: size }}>
      <svg
        width={size}
        height={size * 0.6}
        viewBox={`0 0 ${size} ${size * 0.6}`}
        aria-label={`Score: ${clampedScore}`}
      >
        {/* Background arc */}
        <path
          d={`M ${5} ${size * 0.55} A ${radius} ${radius} 0 0 1 ${size - 5} ${size * 0.55}`}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="8"
          strokeLinecap="round"
          className="dark:stroke-slate-700"
        />
        {/* Foreground arc */}
        <path
          d={`M ${5} ${size * 0.55} A ${radius} ${radius} 0 0 1 ${size - 5} ${size * 0.55}`}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${semiCircumference}`}
          strokeDashoffset={`${offset}`}
          style={{ transition: "stroke-dashoffset 0.5s ease" }}
        />
        {/* Score text */}
        <text
          x={cx}
          y={size * 0.52}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={size * 0.22}
          fontWeight="700"
          fill={color}
        >
          {Math.round(clampedScore)}
        </text>
      </svg>
    </div>
  );
}

// Smaller inline version for tables
export function ScoreBar({ score, className }: { score: number | null | undefined; className?: string }) {
  if (score == null) return <span className="text-slate-400">—</span>;
  const color = scoreToColor(score);
  return (
    <div className={`flex items-center gap-1.5 ${className ?? ""}`}>
      <div className="w-12 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
      <span
        className="text-xs font-mono font-semibold tabular-nums"
        style={{ color }}
      >
        {Math.round(score)}
      </span>
    </div>
  );
}
