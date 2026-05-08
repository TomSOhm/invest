"use client";

import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";
import MetricInfo from "./MetricInfo";

/**
 * Banner shown when the Short-Term horizon is selected.
 * Warns French investors about PFU tax implications in PEA for ST trading.
 *
 * Usage:
 *   <CTOWarningBanner />
 */
export default function CTOWarningBanner() {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <div
      role="alert"
      className="flex items-start gap-3 px-4 py-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 text-orange-800 dark:text-orange-300"
    >
      <AlertTriangle
        size={16}
        className="shrink-0 mt-0.5 text-orange-500"
        aria-hidden
      />
      <p className="text-xs flex-1">
        <strong className="inline-flex items-center gap-1">
          Short-term trading in a PEA is sub-optimal.
          <MetricInfo metricId="recommended_account" size={11} />
        </strong>{" "}
        Use a{" "}
        <strong>CTO (compte-titres ordinaire)</strong> for short-term positions.
        Early withdrawals from a PEA within 5 years trigger a{" "}
        <strong>30% flat tax (PFU)</strong> on capital gains, versus only 17.2%
        social charges after 5 years. Short-term strategies are better suited to
        a CTO where you can manage tax timing.{" "}
        <a
          href="https://www.service-public.fr/particuliers/vosdroits/F2385"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-orange-900 dark:hover:text-orange-200"
        >
          Learn more about PEA taxation.
        </a>
      </p>
      <button
        onClick={() => setDismissed(true)}
        aria-label="Dismiss CTO warning"
        className="shrink-0 p-0.5 rounded hover:bg-orange-200 dark:hover:bg-orange-800 transition-colors"
      >
        <X size={14} />
      </button>
    </div>
  );
}
