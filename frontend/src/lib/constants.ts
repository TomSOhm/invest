export const SIGNAL_COLORS: Record<string, string> = {
  "Strong Buy": "#10b981",  // emerald-500
  "Buy": "#34d399",          // emerald-400
  "Hold": "#f59e0b",         // amber-500
  "Sell": "#f87171",         // red-400
  "Strong Sell": "#ef4444",  // red-500
  "Insufficient Data": "#94a3b8",  // slate-400 — neutral, not a recommendation
};

export const SIGNAL_TEXT_COLORS: Record<string, string> = {
  "Strong Buy": "text-emerald-600 dark:text-emerald-400",
  "Buy": "text-emerald-500 dark:text-emerald-300",
  "Hold": "text-amber-600 dark:text-amber-400",
  "Sell": "text-red-500 dark:text-red-400",
  "Strong Sell": "text-red-600 dark:text-red-500",
  "Insufficient Data": "text-slate-500 dark:text-slate-400",
};

export function scoreToColor(score: number): string {
  if (score >= 75) return "#10b981"; // emerald
  if (score >= 60) return "#34d399"; // emerald-400
  if (score >= 45) return "#f59e0b"; // amber
  if (score >= 30) return "#f87171"; // red-400
  return "#ef4444";                  // red-500
}

export function signalToBgColor(signal: string): string {
  const map: Record<string, string> = {
    "Strong Buy": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    "Buy": "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400",
    "Hold": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    "Sell": "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    "Strong Sell": "bg-red-200 text-red-800 dark:bg-red-900/50 dark:text-red-300",
    "Insufficient Data": "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  };
  return map[signal] ?? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";
}

export const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  pea: "PEA",
  pea_pme: "PEA-PME",
  cto: "CTO",
};

export const PIOTROSKI_CRITERIA = [
  { key: "roa_positive", label: "ROA > 0", category: "Profitability" },
  { key: "cfo_positive", label: "CFO > 0", category: "Profitability" },
  { key: "roa_increasing", label: "ROA Improving", category: "Profitability" },
  { key: "accruals", label: "CFO > ROA", category: "Profitability" },
  { key: "leverage_decreasing", label: "Lower Leverage", category: "Leverage" },
  { key: "current_ratio_increasing", label: "Higher Current Ratio", category: "Leverage" },
  { key: "no_dilution", label: "No Share Dilution", category: "Leverage" },
  { key: "gross_margin_increasing", label: "Higher Gross Margin", category: "Efficiency" },
  { key: "asset_turnover_increasing", label: "Higher Asset Turnover", category: "Efficiency" },
];
