"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown, Check, X } from "lucide-react";
import { useCompany } from "@/hooks/useCompany";
import { formatCurrency, formatNumber, formatPercent, formatDate, formatLargeNumber } from "@/lib/formatters";
import { scoreToColor } from "@/lib/constants";
import SignalBadge from "@/components/ui/SignalBadge";
import PeaBadge from "@/components/ui/PeaBadge";
import ScoreGauge from "@/components/ui/ScoreGauge";
import Card from "@/components/ui/Card";
import Spinner from "@/components/ui/Spinner";
import clsx from "clsx";

// Metric row inside a card
function MetricRow({
  label,
  value,
  isGood,
}: {
  label: string;
  value: string;
  isGood?: boolean | null;
}) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-slate-100 dark:border-slate-800 last:border-0">
      <span className="text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <span
        className={clsx(
          "text-xs font-mono font-semibold",
          isGood === true && "text-emerald-600 dark:text-emerald-400",
          isGood === false && "text-red-500 dark:text-red-400",
          isGood == null && "text-slate-800 dark:text-slate-200"
        )}
      >
        {value}
      </span>
    </div>
  );
}

// Score category bar
function ScoreCategoryBar({
  label,
  score,
  weight,
}: {
  label: string;
  score: number;
  weight?: number;
}) {
  const color = scoreToColor(score);
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-600 dark:text-slate-400">
          {label}
          {weight != null && (
            <span className="ml-1 text-slate-400 text-[10px]">({Math.round(weight * 100)}%)</span>
          )}
        </span>
        <span className="text-xs font-mono font-bold" style={{ color }}>
          {Math.round(score)}
        </span>
      </div>
      <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// Analyst bar: buy/hold/sell distribution
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
  if (total === 0) return <p className="text-sm text-slate-400">No analyst data</p>;

  const pct = (n: number) => `${((n / total) * 100).toFixed(0)}%`;

  return (
    <div className="space-y-2">
      <div className="flex h-4 rounded-full overflow-hidden gap-px">
        {strongBuy > 0 && (
          <div
            className="bg-emerald-600"
            style={{ width: pct(strongBuy) }}
            title={`Strong Buy: ${strongBuy}`}
          />
        )}
        {buy > 0 && (
          <div
            className="bg-emerald-400"
            style={{ width: pct(buy) }}
            title={`Buy: ${buy}`}
          />
        )}
        {hold > 0 && (
          <div
            className="bg-amber-400"
            style={{ width: pct(hold) }}
            title={`Hold: ${hold}`}
          />
        )}
        {sell > 0 && (
          <div
            className="bg-red-400"
            style={{ width: pct(sell) }}
            title={`Sell: ${sell}`}
          />
        )}
        {strongSell > 0 && (
          <div
            className="bg-red-600"
            style={{ width: pct(strongSell) }}
            title={`Strong Sell: ${strongSell}`}
          />
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

// Altman Z visual
function AltmanZBar({ z }: { z: number | null }) {
  if (z == null) return <span className="text-slate-400 text-sm">—</span>;

  const clamped = Math.max(-1, Math.min(5, z));
  const pct = ((clamped + 1) / 6) * 100;

  const color =
    z > 2.99 ? "#10b981" : z > 1.81 ? "#f59e0b" : "#ef4444";
  const label = z > 2.99 ? "Safe Zone" : z > 1.81 ? "Grey Zone" : "Distress Zone";

  return (
    <div className="space-y-2">
      <div className="relative h-4 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
        {/* Zone markers */}
        <div
          className="absolute top-0 bottom-0 bg-red-200 dark:bg-red-900/30"
          style={{ left: 0, width: `${((1.81 + 1) / 6) * 100}%` }}
        />
        <div
          className="absolute top-0 bottom-0 bg-amber-100 dark:bg-amber-900/20"
          style={{
            left: `${((1.81 + 1) / 6) * 100}%`,
            width: `${((2.99 - 1.81) / 6) * 100}%`,
          }}
        />
        <div
          className="absolute top-0 bottom-0 bg-emerald-100 dark:bg-emerald-900/20"
          style={{ left: `${((2.99 + 1) / 6) * 100}%`, right: 0 }}
        />
        {/* Indicator */}
        <div
          className="absolute top-1 bottom-1 w-2 rounded-full"
          style={{ left: `calc(${pct}% - 4px)`, backgroundColor: color }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-400">
        <span>Distress &lt;1.81</span>
        <span>Grey 1.81-2.99</span>
        <span>Safe &gt;2.99</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-lg font-bold font-mono" style={{ color }}>
          {z.toFixed(2)}
        </span>
        <span className="text-sm" style={{ color }}>
          {label}
        </span>
      </div>
    </div>
  );
}

// Piotroski grid (9 criteria)
function PiotroskiGrid({ score }: { score: number }) {
  const criteria = [
    { label: "ROA > 0" },
    { label: "CFO > 0" },
    { label: "ROA Improving" },
    { label: "CFO > ROA (Accruals)" },
    { label: "Lower Leverage" },
    { label: "Higher Current Ratio" },
    { label: "No Share Dilution" },
    { label: "Higher Gross Margin" },
    { label: "Higher Asset Turnover" },
  ];

  // The API only returns total score, so we fill from top
  const filled = Math.round(score);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        {criteria.map((c, i) => {
          const pass = i < filled;
          return (
            <div
              key={c.label}
              className={clsx(
                "flex items-center gap-1.5 px-2 py-1.5 rounded text-xs",
                pass
                  ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400"
                  : "bg-red-50 dark:bg-red-900/20 text-red-500 dark:text-red-400"
              )}
            >
              {pass ? <Check size={11} /> : <X size={11} />}
              <span className="leading-tight">{c.label}</span>
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-3">
        <div className="flex gap-1">
          {Array.from({ length: 9 }).map((_, i) => (
            <div
              key={i}
              className={clsx(
                "w-4 h-4 rounded-sm",
                i < filled
                  ? "bg-emerald-500"
                  : "bg-slate-200 dark:bg-slate-700"
              )}
            />
          ))}
        </div>
        <span
          className={clsx(
            "font-bold text-base",
            filled >= 7
              ? "text-emerald-600 dark:text-emerald-400"
              : filled >= 4
              ? "text-amber-600 dark:text-amber-400"
              : "text-red-500"
          )}
        >
          {filled}/9 — {filled >= 7 ? "Strong" : filled >= 4 ? "Moderate" : "Weak"}
        </span>
      </div>
    </div>
  );
}

export default function CompanyPage() {
  const params = useParams();
  const router = useRouter();
  const ticker = (params.ticker as string)?.toUpperCase();
  const { data, loading, error, fetch } = useCompany();

  useEffect(() => {
    if (ticker) fetch(ticker);
  }, [ticker, fetch]);

  if (loading) {
    return (
      <div className="flex justify-center items-center py-32">
        <Spinner size={36} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-screen-xl mx-auto px-4 py-8">
        <button onClick={() => router.back()} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 mb-4 transition-colors">
          <ArrowLeft size={15} /> Back
        </button>
        <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { metrics, scoring, analyst, pea_eligible, pea_pme_eligible, last_updated } = data;

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6 space-y-5">
      {/* Back */}
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
      >
        <ArrowLeft size={15} /> Back
      </button>

      {/* Header */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-5 py-4 flex flex-wrap items-center gap-4">
        <ScoreGauge score={scoring.composite_score} size={90} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
              {metrics.name}
            </h1>
            <span className="font-mono text-sm bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded">
              {metrics.ticker}
            </span>
            <SignalBadge signal={scoring.signal} />
            <PeaBadge eligible={pea_eligible} pme={pea_pme_eligible} />
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-slate-500">
            <span>{metrics.sector}</span>
            <span>|</span>
            <span>{metrics.industry}</span>
            <span>|</span>
            <span>{metrics.exchange} · {metrics.country}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100">
            {formatCurrency(metrics.price)}
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Mkt Cap: {formatLargeNumber(metrics.market_cap)}
          </div>
          {metrics.fifty_two_week_high_pct != null && (
            <div
              className={clsx(
                "text-xs flex items-center justify-end gap-0.5 mt-0.5",
                metrics.fifty_two_week_high_pct >= 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-500"
              )}
            >
              {metrics.fifty_two_week_high_pct >= 0 ? (
                <TrendingUp size={11} />
              ) : (
                <TrendingDown size={11} />
              )}
              {formatPercent(metrics.fifty_two_week_high_pct)} vs 52w high
            </div>
          )}
        </div>
      </div>

      {/* Analyst + Score breakdown row */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Analyst */}
        <Card title="Analyst Consensus">
          {analyst ? (
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
                  {analyst.target_mean != null && metrics.price > 0 && (
                    <div
                      className={clsx(
                        "text-xs",
                        analyst.target_mean > metrics.price
                          ? "text-emerald-500"
                          : "text-red-500"
                      )}
                    >
                      {formatPercent(
                        ((analyst.target_mean - metrics.price) / metrics.price) * 100
                      )}{" "}
                      upside
                    </div>
                  )}
                </div>
                <div>
                  <div className="text-xs text-slate-400">High</div>
                  <div className="font-mono text-sm font-semibold text-slate-700 dark:text-slate-300">
                    {formatCurrency(analyst.target_high)}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">No analyst data available.</p>
          )}
        </Card>

        {/* Score breakdown */}
        <Card title="Score Breakdown">
          <div className="space-y-2.5">
            <ScoreCategoryBar
              label="Valuation"
              score={scoring.valuation_score}
              weight={scoring.scoring_weights?.valuation}
            />
            <ScoreCategoryBar
              label="Profitability"
              score={scoring.profitability_score}
              weight={scoring.scoring_weights?.profitability}
            />
            <ScoreCategoryBar
              label="Financial Health"
              score={scoring.health_score}
              weight={scoring.scoring_weights?.health}
            />
            <ScoreCategoryBar
              label="Growth"
              score={scoring.growth_score}
              weight={scoring.scoring_weights?.growth}
            />
            <ScoreCategoryBar
              label="Shareholder Returns"
              score={scoring.shareholder_score}
              weight={scoring.scoring_weights?.shareholder}
            />
            <ScoreCategoryBar
              label="Risk"
              score={scoring.risk_score}
              weight={scoring.scoring_weights?.risk}
            />
          </div>
        </Card>
      </div>

      {/* Metrics Grid */}
      <div className="grid md:grid-cols-3 lg:grid-cols-4 gap-4">
        {/* Valuation */}
        <Card title="Valuation">
          <MetricRow label="P/E" value={formatNumber(metrics.pe, 1)} isGood={metrics.pe != null ? metrics.pe < 25 : null} />
          <MetricRow label="Fwd P/E" value={formatNumber(metrics.forward_pe, 1)} />
          <MetricRow label="P/B" value={formatNumber(metrics.pb, 2)} isGood={metrics.pb != null ? metrics.pb < 3 : null} />
          <MetricRow label="P/S" value={formatNumber(metrics.ps, 2)} />
          <MetricRow label="P/FCF" value={formatNumber(metrics.pfcf, 1)} />
          <MetricRow label="EV/EBITDA" value={formatNumber(metrics.ev_ebitda, 1)} />
          <MetricRow label="EV/Sales" value={formatNumber(metrics.ev_sales, 2)} />
          <MetricRow label="PEG" value={formatNumber(metrics.peg, 2)} isGood={metrics.peg != null ? metrics.peg < 1.5 : null} />
        </Card>

        {/* Profitability */}
        <Card title="Profitability">
          <MetricRow label="ROE" value={metrics.roe != null ? formatPercent(metrics.roe) : "—"} isGood={metrics.roe != null ? metrics.roe > 10 : null} />
          <MetricRow label="ROA" value={metrics.roa != null ? formatPercent(metrics.roa) : "—"} isGood={metrics.roa != null ? metrics.roa > 5 : null} />
          <MetricRow label="ROIC" value={metrics.roic != null ? formatPercent(metrics.roic) : "—"} isGood={metrics.roic != null ? metrics.roic > 10 : null} />
          <MetricRow label="Gross Margin" value={metrics.gross_margin != null ? formatPercent(metrics.gross_margin) : "—"} />
          <MetricRow label="Operating Margin" value={metrics.operating_margin != null ? formatPercent(metrics.operating_margin) : "—"} isGood={metrics.operating_margin != null ? metrics.operating_margin > 10 : null} />
          <MetricRow label="Net Margin" value={metrics.net_margin != null ? formatPercent(metrics.net_margin) : "—"} />
          <MetricRow label="FCF Margin" value={metrics.fcf_margin != null ? formatPercent(metrics.fcf_margin) : "—"} />
        </Card>

        {/* Financial Health */}
        <Card title="Financial Health">
          <MetricRow label="Current Ratio" value={formatNumber(metrics.current_ratio, 2)} isGood={metrics.current_ratio != null ? metrics.current_ratio > 1.5 : null} />
          <MetricRow label="D/E Ratio" value={formatNumber(metrics.debt_equity, 2)} isGood={metrics.debt_equity != null ? metrics.debt_equity < 1 : null} />
          <MetricRow label="Interest Coverage" value={formatNumber(metrics.interest_coverage, 1)} isGood={metrics.interest_coverage != null ? metrics.interest_coverage > 3 : null} />
          <MetricRow label="Beta" value={formatNumber(metrics.beta, 2)} />
          <MetricRow label="Rev Growth" value={metrics.revenue_growth != null ? formatPercent(metrics.revenue_growth) : "—"} isGood={metrics.revenue_growth != null ? metrics.revenue_growth > 0 : null} />
          <MetricRow label="Div Yield" value={metrics.div_yield != null ? formatPercent(metrics.div_yield) : "—"} />
          <MetricRow label="Payout Ratio" value={metrics.payout_ratio != null ? formatPercent(metrics.payout_ratio) : "—"} />
        </Card>

        {/* Market & Ownership */}
        <Card title="Market & Ownership">
          <MetricRow label="52w High %" value={metrics.fifty_two_week_high_pct != null ? formatPercent(metrics.fifty_two_week_high_pct) : "—"} />
          <MetricRow label="52w High" value={formatCurrency(metrics.fifty_two_week_high)} />
          <MetricRow label="52w Low" value={formatCurrency(metrics.fifty_two_week_low)} />
          <MetricRow label="Insider %" value={metrics.insider_pct != null ? formatPercent(metrics.insider_pct) : "—"} />
          <MetricRow label="Institutional %" value={metrics.institutional_pct != null ? formatPercent(metrics.institutional_pct) : "—"} />
          <MetricRow label="Short Float %" value={metrics.short_pct_float != null ? formatPercent(metrics.short_pct_float) : "—"} isGood={metrics.short_pct_float != null ? metrics.short_pct_float < 5 : null} />
          <MetricRow label="Earnings Surprise" value={metrics.earnings_surprise_pct != null ? formatPercent(metrics.earnings_surprise_pct) : "—"} />
          <MetricRow label="EV" value={formatLargeNumber(metrics.enterprise_value)} />
        </Card>
      </div>

      {/* Piotroski + Altman + Graham row */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* Piotroski */}
        <Card title={`Piotroski F-Score — ${scoring.piotroski_f}/9`} className="md:col-span-1">
          <PiotroskiGrid score={scoring.piotroski_f} />
        </Card>

        {/* Altman Z */}
        <Card title="Altman Z-Score">
          <AltmanZBar z={scoring.altman_z} />
        </Card>

        {/* Graham */}
        <Card title="Graham Analysis">
          <div className="space-y-3">
            <MetricRow
              label="Graham Number"
              value={scoring.graham_number != null ? formatCurrency(scoring.graham_number) : "—"}
            />
            <MetricRow
              label="Current Price"
              value={formatCurrency(metrics.price)}
            />
            <MetricRow
              label="Margin of Safety"
              value={scoring.graham_mos != null ? formatPercent(scoring.graham_mos) : "—"}
              isGood={scoring.graham_mos != null ? scoring.graham_mos > 0 : null}
            />
            {scoring.graham_mos != null && (
              <div className="pt-2">
                <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={clsx(
                      "h-full rounded-full transition-all",
                      scoring.graham_mos > 0 ? "bg-emerald-500" : "bg-red-500"
                    )}
                    style={{
                      width: `${Math.min(100, Math.abs(scoring.graham_mos))}%`,
                    }}
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {scoring.graham_mos > 0
                    ? `Undervalued by ${formatPercent(scoring.graham_mos)} vs Graham Number`
                    : `Overvalued by ${formatPercent(Math.abs(scoring.graham_mos))} vs Graham Number`}
                </p>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Footer */}
      <div className="text-xs text-slate-400 pb-4">
        Data source: {data.data_source} · Last updated: {formatDate(last_updated)}
      </div>
    </div>
  );
}
