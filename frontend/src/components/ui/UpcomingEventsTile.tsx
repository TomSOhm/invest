"use client";

import { Calendar, DollarSign } from "lucide-react";
import type { CompanyCalendar } from "@/lib/types";
import { formatCurrency, formatDate, formatPercent } from "@/lib/formatters";

interface Props {
  calendar: CompanyCalendar | null;
}

/**
 * Compact "Upcoming Events" tile for the company page header strip.
 *
 * Renders next earnings date + EPS estimate and next ex-dividend date +
 * amount + yield. Returns ``null`` when both event dates are null so that
 * non-US tickers with no calendar coverage don't show an empty card.
 *
 * Usage:
 *   <UpcomingEventsTile calendar={data} />
 */
export default function UpcomingEventsTile({ calendar }: Props) {
  if (!calendar) return null;
  const hasEarnings = calendar.next_earnings_date != null;
  const hasDiv = calendar.ex_dividend_date != null;
  if (!hasEarnings && !hasDiv) return null;

  return (
    <div
      role="region"
      aria-label="Upcoming events"
      className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 space-y-2 w-full sm:w-auto sm:min-w-[220px] order-last sm:order-none"
    >
      <div className="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
        Upcoming Events
      </div>

      {hasEarnings && (
        <div className="flex items-center gap-2 text-xs">
          <Calendar
            size={12}
            className="text-emerald-500 flex-shrink-0"
            aria-hidden
          />
          <span className="text-slate-500 dark:text-slate-400">Earnings</span>
          <span className="font-mono ml-auto text-slate-800 dark:text-slate-200">
            {formatDate(calendar.next_earnings_date)}
          </span>
          {calendar.next_earnings_eps_estimate != null && (
            <span
              className="font-mono text-emerald-600 dark:text-emerald-400"
              title="Consensus EPS estimate"
            >
              Est. {formatCurrency(calendar.next_earnings_eps_estimate, "USD")}
            </span>
          )}
        </div>
      )}

      {hasDiv && (
        <div className="flex items-center gap-2 text-xs">
          <DollarSign
            size={12}
            className="text-amber-500 flex-shrink-0"
            aria-hidden
          />
          <span className="text-slate-500 dark:text-slate-400">Ex-Div</span>
          <span className="font-mono ml-auto text-slate-800 dark:text-slate-200">
            {formatDate(calendar.ex_dividend_date)}
          </span>
          {calendar.dividend_amount != null && (
            <span className="font-mono text-slate-600 dark:text-slate-400">
              {formatCurrency(calendar.dividend_amount, "USD")}
            </span>
          )}
          {calendar.dividend_yield != null && (
            <span
              className="text-slate-500 dark:text-slate-500"
              title="Dividend yield"
            >
              {formatPercent(calendar.dividend_yield * 100)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
