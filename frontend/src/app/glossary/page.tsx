"use client";

import { useState, useMemo } from "react";
import Card from "@/components/ui/Card";
import { METRIC_DEFINITIONS } from "@/lib/metric-definitions";

// ---------------------------------------------------------------------------
// Category definitions — ordered as per plan T2.2
// ---------------------------------------------------------------------------
const CATEGORIES: {
  id: string;
  label: string;
  keys: string[];
}[] = [
  {
    id: "composite",
    label: "Composite & Signals",
    keys: [
      "score_lt",
      "score_mt",
      "score_st",
      "signal",
      "passes_gates",
      "blockers",
      "recommended_account",
    ],
  },
  {
    id: "dcf",
    label: "DCF & Valuation",
    keys: [
      "dcf_fair_value",
      "dcf_mos",
      "wacc_used",
      "graham_number",
      "graham_mos",
      "pe",
      "forward_pe",
      "pb",
      "ps",
      "pfcf",
      "ev_ebitda",
      "ev_sales",
      "peg",
    ],
  },
  {
    id: "earnings_quality",
    label: "Earnings Quality",
    keys: [
      "piotroski_f",
      "altman_z",
      "altman_zone",
      "m_score",
      "sloan_accruals",
      "cash_conversion_ratio_5y",
      "earnings_quality_score",
    ],
  },
  {
    id: "profitability",
    label: "Profitability & Margins",
    keys: [
      "roe",
      "roa",
      "roic",
      "gross_margin",
      "operating_margin",
      "net_margin",
      "fcf_margin",
      "moat_score",
    ],
  },
  {
    id: "health",
    label: "Financial Health",
    keys: [
      "current_ratio",
      "debt_equity",
      "net_debt_ebitda",
      "interest_coverage",
      "revenue_growth",
    ],
  },
  {
    id: "risk",
    label: "Risk",
    keys: ["risk_score", "realized_vol_1y", "max_drawdown_3y", "beta"],
  },
  {
    id: "momentum",
    label: "Momentum",
    keys: [
      "momentum_12_1",
      "rs_3m",
      "above_50dma",
      "above_200dma",
      "golden_cross",
      "volume_surge",
      "eps_revision_30d",
      "eps_revision_90d",
      "sue_z_score",
      "sentiment_30d",
      "sentiment_trend",
    ],
  },
  {
    id: "dividend",
    label: "Dividend",
    keys: ["div_yield", "payout_ratio"],
  },
  {
    id: "subscores",
    label: "Sub-Scores",
    keys: [
      "sub_valuation",
      "sub_profitability",
      "sub_health",
      "sub_growth",
      "sub_shareholder",
      "sub_risk_legacy",
    ],
  },
  {
    id: "portfolio_summary",
    label: "Portfolio Summary",
    keys: [
      "total_value",
      "total_gain_loss",
      "avg_score_lt",
      "weight_pct",
      "position_count",
    ],
  },
  {
    id: "screener_summary",
    label: "Screener Summary",
    keys: ["total_passed", "signal_distribution"],
  },
  {
    id: "position",
    label: "Position Details",
    keys: [
      "market_value",
      "cost_basis",
      "gain_loss_pct",
      "fifty_two_week_high_pct",
      "pea_eligible",
    ],
  },
  {
    id: "analyst",
    label: "Analyst",
    keys: ["analyst_rating", "analyst_target_price"],
  },
];

// ---------------------------------------------------------------------------
// Sub-heading component for section labels inside cards
// ---------------------------------------------------------------------------
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-xs uppercase tracking-wide font-semibold text-slate-500 dark:text-slate-400 select-none">
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Single metric card
// ---------------------------------------------------------------------------
function MetricCard({
  id,
  def,
}: {
  id: string;
  def: (typeof METRIC_DEFINITIONS)[string];
}) {
  return (
    <div id={id} className="scroll-mt-20">
    <Card>
      {/* Header */}
      <div className="mb-3">
        <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
          {def.label}
        </h3>
        <code className="text-xs font-mono text-slate-400 dark:text-slate-500">
          {id}
        </code>
      </div>

      <div className="space-y-3 text-sm text-slate-700 dark:text-slate-300">
        {/* Definition */}
        <div>
          <SectionLabel>Definition</SectionLabel>
          <p className="mt-1">{def.what}</p>
        </div>

        {/* Formula — only rendered when present */}
        {def.formula && (
          <div>
            <SectionLabel>Formula</SectionLabel>
            <code className="block mt-1 font-mono text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-3 py-2 whitespace-pre-wrap leading-relaxed text-slate-800 dark:text-slate-200">
              {def.formula}
            </code>
          </div>
        )}

        {/* Why it matters */}
        <div>
          <SectionLabel>Why it matters</SectionLabel>
          <p className="mt-1">{def.why}</p>
        </div>

        {/* Good vs Bad */}
        <div>
          <SectionLabel>Good vs Bad</SectionLabel>
          <p className="mt-1">{def.goodVsBad}</p>
        </div>

        {/* Example */}
        <div>
          <SectionLabel>Example</SectionLabel>
          <p className="mt-1">{def.example}</p>
        </div>

        {/* Caveats — optional */}
        {def.caveats && (
          <div>
            <SectionLabel>Limits / Caveats</SectionLabel>
            <p className="mt-1">{def.caveats}</p>
          </div>
        )}
      </div>
    </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function GlossaryPage() {
  const [query, setQuery] = useState("");

  // Filtered view: search across label and what
  const filteredCategories = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return CATEGORIES;

    return CATEGORIES.map((cat) => ({
      ...cat,
      keys: cat.keys.filter((key) => {
        const def = METRIC_DEFINITIONS[key];
        if (!def) return false;
        return (
          def.label.toLowerCase().includes(q) ||
          def.what.toLowerCase().includes(q) ||
          key.toLowerCase().includes(q)
        );
      }),
    })).filter((cat) => cat.keys.length > 0);
  }, [query]);

  // Total count for display
  const totalShown = filteredCategories.reduce(
    (acc, cat) => acc + cat.keys.length,
    0
  );

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          Glossary
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Full metric catalog — definitions, formulas, thresholds, examples and
          caveats for every metric used in the scoring engine.
        </p>
      </div>

      {/* Search */}
      <div className="mb-6">
        <input
          type="search"
          placeholder="Search metrics..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full max-w-sm rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
        {query && (
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {totalShown} metric{totalShown !== 1 ? "s" : ""} match
            {totalShown === 1 ? "es" : ""} &ldquo;{query}&rdquo;
          </p>
        )}
      </div>

      {/* Sticky category nav */}
      {!query && (
        <nav
          aria-label="Glossary categories"
          className="sticky top-14 z-40 -mx-4 px-4 py-2 mb-6 bg-white/90 dark:bg-slate-950/90 backdrop-blur border-b border-slate-200 dark:border-slate-800"
        >
          <ol className="flex flex-wrap gap-x-3 gap-y-1">
            {CATEGORIES.map((cat, idx) => (
              <li key={cat.id}>
                <a
                  href={`#cat-${cat.id}`}
                  className="text-xs text-slate-500 dark:text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors"
                >
                  <span className="text-slate-300 dark:text-slate-600 mr-1">
                    {idx + 1}.
                  </span>
                  {cat.label}
                </a>
              </li>
            ))}
          </ol>
        </nav>
      )}

      {/* Category sections */}
      {filteredCategories.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No metrics found for &ldquo;{query}&rdquo;.
        </p>
      ) : (
        <div className="space-y-10">
          {filteredCategories.map((cat) => (
            <section key={cat.id} id={`cat-${cat.id}`} className="scroll-mt-28">
              {/* Section heading */}
              <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-4 pb-2 border-b border-slate-200 dark:border-slate-700">
                {cat.label}
              </h2>

              {/* Metric cards in a responsive grid */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {cat.keys.map((key) => {
                  const def = METRIC_DEFINITIONS[key];
                  if (!def) return null;
                  return <MetricCard key={key} id={key} def={def} />;
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
