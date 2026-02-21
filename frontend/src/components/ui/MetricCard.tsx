import clsx from "clsx";
import { formatCurrency, formatPercent, formatNumber, formatRatio } from "@/lib/formatters";

type FormatType = "percent" | "currency" | "number" | "ratio" | "large";

interface MetricCardProps {
  label: string;
  value: number | string | null | undefined;
  format?: FormatType;
  isGood?: boolean | null;
  suffix?: string;
  decimals?: number;
}

function formatValue(
  value: number | string | null | undefined,
  format?: FormatType,
  decimals?: number
): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  switch (format) {
    case "percent":
      return formatPercent(value, decimals ?? 1);
    case "currency":
      return formatCurrency(value);
    case "ratio":
      return formatRatio(value, decimals ?? 2);
    case "number":
      return formatNumber(value, decimals ?? 2);
    default:
      return formatNumber(value, decimals ?? 2);
  }
}

export default function MetricCard({
  label,
  value,
  format,
  isGood,
  suffix,
  decimals,
}: MetricCardProps) {
  const displayValue = formatValue(value, format, decimals);
  const hasValue = value != null && value !== "";

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-500 dark:text-slate-400 truncate">{label}</span>
      <span
        className={clsx(
          "text-sm font-semibold tabular-nums font-mono",
          hasValue && isGood === true && "text-emerald-600 dark:text-emerald-400",
          hasValue && isGood === false && "text-red-500 dark:text-red-400",
          (isGood === null || isGood === undefined) && "text-slate-900 dark:text-slate-100",
          !hasValue && "text-slate-400"
        )}
      >
        {displayValue}
        {suffix && hasValue && <span className="text-xs font-normal ml-0.5">{suffix}</span>}
      </span>
    </div>
  );
}
