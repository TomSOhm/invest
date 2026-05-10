"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown } from "lucide-react";
import { useCompany } from "@/hooks/useCompany";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatDate,
  formatLargeNumber,
} from "@/lib/formatters";
import { scoreToColor } from "@/lib/constants";
import SignalBadge from "@/components/ui/SignalBadge";
import PeaBadge from "@/components/ui/PeaBadge";
import Card from "@/components/ui/Card";
import Spinner from "@/components/ui/Spinner";
import HorizonScoreCard from "@/components/ui/HorizonScoreCard";
import DCFFairValueRange from "@/components/ui/DCFFairValueRange";
import EarningsQualityPanel from "@/components/ui/EarningsQualityPanel";
import MomentumPanel from "@/components/ui/MomentumPanel";
import { ScoreBar } from "@/components/ui/ScoreGauge";
import MetricInfo from "@/components/ui/MetricInfo";
import type { AnalystRatings, RiskSignals, SubScores } from "@/lib/types";
import clsx from "clsx";

// Metric row inside a card
function MetricRow({
  label,
  value,
  isGood,
  metricId,
}: {
  label: string;
  value: string;
  isGood?: boolean | null;
  metricId?: string;
}) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-slate-100 dark:border-slate-800 last:border-0">
      <span className="text-xs text-slate-500 dark:text-slate-400 inline-flex items-center gap-1">
        {label}
        {metricId && <MetricInfo metricId={metricId} size={11} />}
      </span>
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
          <div className="bg-emerald-600" style={{ width: pct(strongBuy) }} title={`Strong Buy: ${strongBuy}`} />
        )}
        {buy > 0 && (
          <div className="bg-emerald-400" style={{ width: pct(buy) }} title={`Buy: ${buy}`} />
        )}
        {hold > 0 && (
          <div className="bg-amber-400" style={{ width: pct(hold) }} title={`Hold: ${hold}`} />
        )}
        {sell > 0 && (
          <div className="bg-red-400" style={{ width: pct(sell) }} title={`Sell: ${sell}`} />
        )}
        {strongSell > 0 && (
          <div className="bg-red-600" style={{ width: pct(strongSell) }} title={`Strong Sell: ${strongSell}`} />
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

// Risk panel (lightweight)
function RiskPanel({ risk }: { risk: RiskSignals }) {
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
      <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
        Risk
      </span>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {risk.risk_score != null && (
          <div>
            <div className="text-xs text-slate-400 mb-0.5 inline-flex items-center gap-1">
              Risk Score
              <MetricInfo metricId="risk_score" size={11} />
            </div>
            <ScoreBar score={risk.risk_score} />
          </div>
        )}
        {risk.realized_vol_1y != null && (
          <MetricRow
            label="Vol 1Y"
            value={formatPercent(risk.realized_vol_1y * 100)}
            isGood={risk.realized_vol_1y < 0.25}
            metricId="realized_vol_1y"
          />
        )}
        {risk.max_drawdown_3y != null && (
          <MetricRow
            label="Max DD 3Y"
            value={formatPercent(risk.max_drawdown_3y * 100)}
            isGood={risk.max_drawdown_3y > -0.3}
            metricId="max_drawdown_3y"
          />
        )}
        {risk.net_debt_ebitda != null && (
          <MetricRow
            label="ND/EBITDA"
            value={formatNumber(risk.net_debt_ebitda, 1) + "x"}
            isGood={risk.net_debt_ebitda < 3}
            metricId="net_debt_ebitda"
          />
        )}
        {risk.interest_coverage != null && (
          <MetricRow
            label="Interest Cov."
            value={formatNumber(risk.interest_coverage, 1) + "x"}
            isGood={risk.interest_coverage > 3}
            metricId="interest_coverage"
          />
        )}
        {risk.beta != null && (
          <MetricRow
            label="Beta"
            value={formatNumber(risk.beta, 2)}
            metricId="beta"
          />
        )}
      </div>
    </div>
  );
}

// Sub-scores panel (collapsible)
function SubScoresPanel({ subScores }: { subScores: SubScores }) {
  const items = [
    { label: "Valuation", score: subScores.valuation, metricId: "sub_valuation" },
    { label: "Profitability", score: subScores.profitability, metricId: "sub_profitability" },
    { label: "Financial Health", score: subScores.health, metricId: "sub_health" },
    { label: "Growth", score: subScores.growth, metricId: "sub_growth" },
    { label: "Shareholder Returns", score: subScores.shareholder, metricId: "sub_shareholder" },
    { label: "Risk (Legacy)", score: subScores.risk_legacy, metricId: "sub_risk_legacy" },
  ];

  return (
    <details className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
      <summary className="px-4 py-3 cursor-pointer text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
        Sub-Scores (Legacy M3)
      </summary>
      <div className="px-4 pb-4 pt-2 space-y-2.5">
        {items.map((item) => {
          const color = scoreToColor(item.score);
          return (
            <div key={item.label} className="space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-xs text-slate-600 dark:text-slate-400 inline-flex items-center gap-1">
                  {item.label}
                  <MetricInfo metricId={item.metricId} size={11} />
                </span>
                <span className="text-xs font-mono font-bold" style={{ color }}>
                  {Math.round(item.score)}
                </span>
              </div>
              <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${item.score}%`, backgroundColor: color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
}

// Analyst targets panel
function AnalystTargetsPanel({ analyst }: { analyst: AnalystRatings; currentPrice: number }) {
  return (
    <Card title="Analyst Consensus">
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
          </div>
          <div>
            <div className="text-xs text-slate-400">High</div>
            <div className="font-mono text-sm font-semibold text-slate-700 dark:text-slate-300">
              {formatCurrency(analyst.target_high)}
            </div>
          </div>
        </div>
      </div>
    </Card>
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
        <button
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 mb-4 transition-colors"
        >
          <ArrowLeft size={15} /> Back
        </button>
        <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const {
    metrics,
    horizons,
    sub_scores,
    valuation,
    quality,
    risk,
    momentum,
    analyst_ratings,
    pea_eligible,
    pea_pme_eligible,
    last_updated,
  } = data;

  const currentPrice = metrics.price ?? data.price ?? 0;

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6 space-y-5">
      {/* Back */}
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
      >
        <ArrowLeft size={15} /> Back
      </button>

      {/* Score-source warning when this ticker isn't in the screener universe */}
      {data.score_source === "single_row_fallback" && (
        <div className="rounded-md border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          <strong>Approximate scores.</strong> {ticker} is not in the screened
          universe, so sector-relative percentiles fall back to a global rank
          against this ticker alone. Scores may differ from the screener. Add
          this ticker to <code className="font-mono text-xs bg-amber-100 dark:bg-amber-900/50 px-1 rounded">data/universes/universe_pea_static.csv</code> and click <em>Refresh</em> on the screener to get peer-relative scoring.
        </div>
      )}

      {/* Header */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-5 py-4 flex flex-wrap items-center gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
              {metrics.name || data.name}
            </h1>
            <span className="font-mono text-sm bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded">
              {metrics.ticker || ticker}
            </span>
            <PeaBadge eligible={pea_eligible} pme={pea_pme_eligible} />
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-slate-500">
            {metrics.sector && <span>{metrics.sector}</span>}
            {metrics.industry && (
              <>
                <span>|</span>
                <span>{metrics.industry}</span>
              </>
            )}
            {metrics.exchange && metrics.country && (
              <>
                <span>|</span>
                <span>
                  {metrics.exchange} · {metrics.country}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100">
            {formatCurrency(currentPrice)}
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
          {data.data_completeness != null && (
            <div className="text-xs text-slate-400 mt-0.5">
              Data: {Math.round(data.data_completeness * 100)}% complete
            </div>
          )}
        </div>
      </div>

      {/* Three Horizon Score Cards */}
      <div className="grid md:grid-cols-3 gap-4">
        <HorizonScoreCard horizon="long_term" scoring={horizons.long_term} />
        <HorizonScoreCard horizon="medium_term" scoring={horizons.medium_term} />
        <HorizonScoreCard horizon="short_term" scoring={horizons.short_term} />
      </div>

      {/* DCF Fair Value Range */}
      <DCFFairValueRange valuation={valuation} currentPrice={currentPrice} />

      {/* Earnings Quality + Momentum */}
      <div className="grid md:grid-cols-2 gap-4">
        <EarningsQualityPanel quality={quality} />
        <MomentumPanel momentum={momentum} />
      </div>

      {/* Risk + Analyst */}
      <div className="grid md:grid-cols-2 gap-4">
        <RiskPanel risk={risk} />
        {analyst_ratings ? (
          <AnalystTargetsPanel
            analyst={analyst_ratings}
            currentPrice={currentPrice}
          />
        ) : (
          <Card title="Analyst Consensus">
            <p className="text-sm text-slate-400">No analyst data available.</p>
          </Card>
        )}
      </div>

      {/* Raw Metrics Grid */}
      <div className="grid md:grid-cols-3 lg:grid-cols-4 gap-4">
        {/* Valuation */}
        <Card title="Valuation">
          <MetricRow label="P/E" value={formatNumber(metrics.pe, 1)} isGood={metrics.pe != null ? metrics.pe < 25 : null} metricId="pe" />
          <MetricRow label="Fwd P/E" value={formatNumber(metrics.forward_pe, 1)} metricId="forward_pe" />
          <MetricRow label="P/B" value={formatNumber(metrics.pb, 2)} isGood={metrics.pb != null ? metrics.pb < 3 : null} metricId="pb" />
          <MetricRow label="P/S" value={formatNumber(metrics.ps, 2)} metricId="ps" />
          <MetricRow label="P/FCF" value={formatNumber(metrics.pfcf, 1)} metricId="pfcf" />
          <MetricRow label="EV/EBITDA" value={formatNumber(metrics.ev_ebitda, 1)} metricId="ev_ebitda" />
          <MetricRow label="EV/Sales" value={formatNumber(metrics.ev_sales, 2)} metricId="ev_sales" />
          <MetricRow label="PEG" value={formatNumber(metrics.peg, 2)} isGood={metrics.peg != null ? metrics.peg < 1.5 : null} metricId="peg" />
        </Card>

        {/* Profitability */}
        <Card title="Profitability">
          <MetricRow label="ROE" value={metrics.roe != null ? formatPercent(metrics.roe) : "—"} isGood={metrics.roe != null ? metrics.roe > 10 : null} metricId="roe" />
          <MetricRow label="ROA" value={metrics.roa != null ? formatPercent(metrics.roa) : "—"} isGood={metrics.roa != null ? metrics.roa > 5 : null} metricId="roa" />
          <MetricRow label="ROIC" value={metrics.roic != null ? formatPercent(metrics.roic) : "—"} isGood={metrics.roic != null ? metrics.roic > 10 : null} metricId="roic" />
          <MetricRow label="Gross Margin" value={metrics.gross_margin != null ? formatPercent(metrics.gross_margin) : "—"} metricId="gross_margin" />
          <MetricRow label="Operating Margin" value={metrics.operating_margin != null ? formatPercent(metrics.operating_margin) : "—"} isGood={metrics.operating_margin != null ? metrics.operating_margin > 10 : null} metricId="operating_margin" />
          <MetricRow label="Net Margin" value={metrics.net_margin != null ? formatPercent(metrics.net_margin) : "—"} metricId="net_margin" />
          <MetricRow label="FCF Margin" value={metrics.fcf_margin != null ? formatPercent(metrics.fcf_margin) : "—"} metricId="fcf_margin" />
        </Card>

        {/* Financial Health */}
        <Card title="Financial Health">
          <MetricRow label="Current Ratio" value={formatNumber(metrics.current_ratio, 2)} isGood={metrics.current_ratio != null ? metrics.current_ratio > 1.5 : null} metricId="current_ratio" />
          <MetricRow label="D/E Ratio" value={formatNumber(metrics.debt_equity, 2)} isGood={metrics.debt_equity != null ? metrics.debt_equity < 1 : null} metricId="debt_equity" />
          <MetricRow label="Interest Coverage" value={formatNumber(metrics.interest_coverage, 1)} isGood={metrics.interest_coverage != null ? metrics.interest_coverage > 3 : null} metricId="interest_coverage" />
          <MetricRow label="Beta" value={formatNumber(metrics.beta, 2)} metricId="beta" />
          <MetricRow label="Rev Growth" value={metrics.revenue_growth != null ? formatPercent(metrics.revenue_growth) : "—"} isGood={metrics.revenue_growth != null ? metrics.revenue_growth > 0 : null} metricId="revenue_growth" />
          <MetricRow label="Div Yield" value={metrics.div_yield != null ? formatPercent(metrics.div_yield) : "—"} metricId="div_yield" />
          <MetricRow label="Payout Ratio" value={metrics.payout_ratio != null ? formatPercent(metrics.payout_ratio) : "—"} metricId="payout_ratio" />
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

      {/* Sub-scores (collapsible) */}
      <SubScoresPanel subScores={sub_scores} />

      {/* Footer */}
      <div className="text-xs text-slate-400 pb-4">
        Data source: {data.data_source} · Last updated: {formatDate(last_updated)}
      </div>
    </div>
  );
}
