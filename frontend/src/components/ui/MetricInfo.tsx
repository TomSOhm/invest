"use client";

import { useEffect, useId, useRef, useState } from "react";
import { HelpCircle, X } from "lucide-react";
import clsx from "clsx";
import { METRIC_DEFINITIONS, type MetricDef } from "@/lib/metric-definitions";

interface MetricInfoProps {
  metricId: string;
  className?: string;
  // Override the icon size in pixels. Default 14 to sit next to text labels.
  size?: number;
  // Optional aria label for screen readers when the visible label is not nearby.
  ariaLabel?: string;
}

export default function MetricInfo({
  metricId,
  className,
  size = 14,
  ariaLabel,
}: MetricInfoProps) {
  const def: MetricDef | undefined = METRIC_DEFINITIONS[metricId];
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    // Defer focus to next tick so the dialog has mounted.
    const t = setTimeout(() => closeBtnRef.current?.focus(), 0);
    return () => {
      document.removeEventListener("keydown", onKey);
      clearTimeout(t);
    };
  }, [open]);

  if (!def) return null;

  return (
    <span className={clsx("relative inline-block", className)}>
      <button
        type="button"
        ref={triggerRef}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-label={ariaLabel ?? `Definition: ${def.label}`}
        aria-expanded={open}
        className="inline-flex items-center justify-center align-middle text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 transition-colors cursor-help focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-full"
      >
        <HelpCircle size={size} />
      </button>

      {open && (
        <>
          {/* Backdrop captures clicks outside the popover to close it. */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />

          {/* Popover panel — absolute positioned under the icon. */}
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="absolute left-0 top-full mt-2 w-80 max-w-[calc(100vw-2rem)] z-50 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl text-left"
          >
            <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-slate-200 dark:border-slate-800">
              <h3
                id={titleId}
                className="text-sm font-semibold text-slate-900 dark:text-slate-100 leading-tight"
              >
                {def.label}
              </h3>
              <button
                type="button"
                ref={closeBtnRef}
                onClick={() => setOpen(false)}
                aria-label="Close definition"
                className="p-0.5 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors flex-shrink-0"
              >
                <X size={14} />
              </button>
            </div>

            <div className="px-4 py-3 space-y-3 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              <Section heading="What it is" body={def.what} />
              <Section heading="Why it matters" body={def.why} />
              <Section heading="Good vs bad" body={def.goodVsBad} />
              <Section heading="Example" body={def.example} />
              {def.caveats && <Section heading="Caveats" body={def.caveats} />}
              {def.reference && (
                <p className="pt-1 text-[11px] text-slate-500 dark:text-slate-500 italic">
                  Reference: {def.reference}
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </span>
  );
}

function Section({ heading, body }: { heading: string; body: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-500">
        {heading}
      </p>
      <p className="mt-0.5 text-slate-700 dark:text-slate-300">{body}</p>
    </div>
  );
}
