"use client";

import { useState, useMemo } from "react";
import {
  Plus,
  RefreshCw,
  ChevronUp,
  ChevronDown,
  ChevronRight,
  Trash2,
  Pencil,
} from "lucide-react";
import { usePortfolio } from "@/hooks/usePortfolio";
import type {
  AddPositionRequest,
  Horizon,
  PortfolioPosition,
  UpdatePositionRequest,
} from "@/lib/types";
import {
  formatCurrency,
  formatPercent,
  formatNumber,
  formatDate,
} from "@/lib/formatters";
import { ACCOUNT_TYPE_LABELS } from "@/lib/constants";
import SignalBadge from "@/components/ui/SignalBadge";
import PeaBadge from "@/components/ui/PeaBadge";
import Modal from "@/components/ui/Modal";
import Spinner from "@/components/ui/Spinner";
import Card from "@/components/ui/Card";
import { ScoreBar } from "@/components/ui/ScoreGauge";
import HorizonSelector from "@/components/ui/HorizonSelector";
import MetricInfo from "@/components/ui/MetricInfo";
import clsx from "clsx";

// ---------------------------------------------------------------------------
// Helpers to get horizon-specific score/signal from a position
// ---------------------------------------------------------------------------

function getScoreForHorizon(pos: PortfolioPosition, horizon: Horizon): number | null {
  if (horizon === "long_term") return pos.score_lt ?? null;
  if (horizon === "medium_term") return pos.score_mt ?? null;
  return pos.score_st ?? null;
}

function getSignalForHorizon(pos: PortfolioPosition, horizon: Horizon): string | null {
  if (horizon === "long_term") return pos.signal_lt ?? null;
  if (horizon === "medium_term") return pos.signal_mt ?? null;
  return pos.signal_st ?? null;
}

// ---------------------------------------------------------------------------
// Summary card
// ---------------------------------------------------------------------------

function SummaryCard({
  label,
  value,
  sub,
  positive,
  metricId,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean | null;
  metricId?: string;
}) {
  return (
    <Card className="flex flex-col gap-1 min-w-0">
      <span className="text-xs text-slate-500 dark:text-slate-400 inline-flex items-center gap-1">
        {label}
        {metricId && <MetricInfo metricId={metricId} size={11} />}
      </span>
      <span
        className={clsx(
          "text-xl font-bold tabular-nums",
          positive === true && "text-emerald-600 dark:text-emerald-400",
          positive === false && "text-red-500 dark:text-red-400",
          positive == null && "text-slate-900 dark:text-slate-100"
        )}
      >
        {value}
      </span>
      {sub && <span className="text-xs text-slate-400">{sub}</span>}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Add Position Modal
// ---------------------------------------------------------------------------

function AddPositionModal({
  open,
  onClose,
  onSubmit,
  initialTicker = "",
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (req: AddPositionRequest) => Promise<unknown>;
  initialTicker?: string;
}) {
  const [form, setForm] = useState<AddPositionRequest>({
    ticker: initialTicker,
    quantity: 1,
    buy_price: 0,
    buy_date: "",
    account_type: "pea",
    notes: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function update<K extends keyof AddPositionRequest>(
    key: K,
    val: AddPositionRequest[K]
  ) {
    setForm((f) => ({ ...f, [key]: val }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.ticker) {
      setErr("Ticker is required");
      return;
    }
    if (form.quantity <= 0) {
      setErr("Quantity must be > 0");
      return;
    }
    if (form.buy_price <= 0) {
      setErr("Buy price must be > 0");
      return;
    }
    setErr(null);
    setSubmitting(true);
    try {
      const req: AddPositionRequest = {
        ...form,
        ticker: form.ticker.toUpperCase().trim(),
        buy_date: form.buy_date || undefined,
        notes: form.notes || undefined,
      };
      await onSubmit(req);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  const inputCls =
    "w-full px-3 py-2 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500";
  const labelCls =
    "block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1";

  return (
    <Modal open={open} onClose={onClose} title="Add Position">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Ticker *</label>
            <input
              className={inputCls}
              value={form.ticker}
              onChange={(e) => update("ticker", e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
              required
            />
          </div>
          <div>
            <label className={labelCls}>Account Type *</label>
            <select
              className={inputCls}
              value={form.account_type}
              onChange={(e) =>
                update(
                  "account_type",
                  e.target.value as AddPositionRequest["account_type"]
                )
              }
            >
              <option value="pea">PEA</option>
              <option value="pea_pme">PEA-PME</option>
              <option value="cto">CTO</option>
            </select>
          </div>
          <div>
            <label className={labelCls}>Quantity *</label>
            <input
              className={inputCls}
              type="number"
              min={0.001}
              step="any"
              value={form.quantity}
              onChange={(e) => update("quantity", parseFloat(e.target.value))}
              required
            />
          </div>
          <div>
            <label className={labelCls}>Buy Price (EUR) *</label>
            <input
              className={inputCls}
              type="number"
              min={0.001}
              step="any"
              value={form.buy_price}
              onChange={(e) => update("buy_price", parseFloat(e.target.value))}
              required
            />
          </div>
          <div>
            <label className={labelCls}>Buy Date</label>
            <input
              className={inputCls}
              type="date"
              value={form.buy_date ?? ""}
              onChange={(e) => update("buy_date", e.target.value)}
            />
          </div>
        </div>
        <div>
          <label className={labelCls}>Notes</label>
          <textarea
            className={inputCls}
            rows={2}
            value={form.notes ?? ""}
            onChange={(e) => update("notes", e.target.value)}
            placeholder="Optional notes..."
          />
        </div>
        {err && <p className="text-sm text-red-500">{err}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-md border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-sm rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60 transition-colors flex items-center gap-2"
          >
            {submitting && <Spinner size={14} />}
            Add Position
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Edit Position Modal
// ---------------------------------------------------------------------------

function EditPositionModal({
  open,
  onClose,
  position,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  position: PortfolioPosition | null;
  onSubmit: (id: string, req: UpdatePositionRequest) => Promise<void>;
}) {
  const [quantity, setQuantity] = useState<number>(position?.quantity ?? 0);
  const [buyPrice, setBuyPrice] = useState<number>(position?.buy_price ?? 0);
  const [buyDate, setBuyDate] = useState<string>(position?.buy_date ?? "");
  const [notes, setNotes] = useState<string>(position?.notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!position) return null;

  const pos = position; // captured for use inside async closures

  const inputCls =
    "w-full px-3 py-2 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500";
  const labelCls =
    "block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (quantity <= 0) {
      setErr("Quantity must be > 0");
      return;
    }
    if (buyPrice <= 0) {
      setErr("Buy price must be > 0");
      return;
    }
    setErr(null);
    setSubmitting(true);
    try {
      await onSubmit(pos.id, {
        quantity,
        buy_price: buyPrice,
        buy_date: buyDate || undefined,
        notes: notes || undefined,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Edit Position — ${pos.ticker}`}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Quantity *</label>
            <input
              className={inputCls}
              type="number"
              min={0.001}
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(parseFloat(e.target.value))}
              required
            />
          </div>
          <div>
            <label className={labelCls}>Buy Price (EUR) *</label>
            <input
              className={inputCls}
              type="number"
              min={0.001}
              step="any"
              value={buyPrice}
              onChange={(e) => setBuyPrice(parseFloat(e.target.value))}
              required
            />
          </div>
          <div>
            <label className={labelCls}>Buy Date</label>
            <input
              className={inputCls}
              type="date"
              value={buyDate}
              onChange={(e) => setBuyDate(e.target.value)}
            />
          </div>
        </div>
        <div>
          <label className={labelCls}>Notes</label>
          <textarea
            className={inputCls}
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional notes..."
          />
        </div>
        {err && <p className="text-sm text-red-500">{err}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-md border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-sm rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60 transition-colors flex items-center gap-2"
          >
            {submitting && <Spinner size={14} />}
            Save Changes
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Expanded row
// ---------------------------------------------------------------------------

function ExpandedRow({
  pos,
  horizon,
}: {
  pos: PortfolioPosition;
  horizon: Horizon;
}) {
  const metricGroup = (
    label: string,
    items: { label: string; value: string; good?: boolean | null }[]
  ) => (
    <div>
      <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2 uppercase tracking-wide">
        {label}
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
        {items.map((item) => (
          <div key={item.label} className="flex justify-between items-center">
            <span className="text-xs text-slate-500">{item.label}</span>
            <span
              className={clsx(
                "text-xs font-mono font-semibold",
                item.good === true && "text-emerald-600 dark:text-emerald-400",
                item.good === false && "text-red-500 dark:text-red-400",
                item.good == null && "text-slate-700 dark:text-slate-300"
              )}
            >
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="bg-slate-50 dark:bg-slate-800/50 border-t border-slate-200 dark:border-slate-800 px-6 py-4 grid grid-cols-2 md:grid-cols-4 gap-6">
      {metricGroup("Valuation", [
        { label: "P/E", value: formatNumber(pos.pe, 1) },
        { label: "Fwd P/E", value: formatNumber(pos.forward_pe, 1) },
        { label: "P/B", value: formatNumber(pos.pb, 2) },
        { label: "P/S", value: formatNumber(pos.ps, 2) },
        { label: "PEG", value: formatNumber(pos.peg, 2) },
        { label: "Graham #", value: formatNumber(pos.graham_number, 2) },
        {
          label: "Graham MoS",
          value: pos.graham_mos != null ? formatPercent(pos.graham_mos) : "—",
        },
        {
          label: "DCF MoS",
          value:
            pos.dcf_mos_mid != null
              ? formatPercent(pos.dcf_mos_mid * 100)
              : "—",
        },
      ])}
      {metricGroup("Profitability", [
        {
          label: "ROE",
          value: pos.roe != null ? formatPercent(pos.roe) : "—",
          good: pos.roe != null ? pos.roe > 10 : null,
        },
        {
          label: "ROA",
          value: pos.roa != null ? formatPercent(pos.roa) : "—",
          good: pos.roa != null ? pos.roa > 5 : null,
        },
        {
          label: "ROIC",
          value: pos.roic != null ? formatPercent(pos.roic) : "—",
          good: pos.roic != null ? pos.roic > 10 : null,
        },
        {
          label: "Op Margin",
          value: pos.operating_margin != null ? formatPercent(pos.operating_margin) : "—",
        },
        {
          label: "Net Margin",
          value: pos.net_margin != null ? formatPercent(pos.net_margin) : "—",
        },
        {
          label: "Rev Growth",
          value: pos.revenue_growth != null ? formatPercent(pos.revenue_growth) : "—",
        },
      ])}
      {metricGroup("Quality Scores", [
        {
          label: "Piotroski F",
          value: pos.piotroski_f != null ? `${pos.piotroski_f}/9` : "—",
          good: pos.piotroski_f != null ? pos.piotroski_f >= 7 : null,
        },
        {
          label: "Altman Z",
          value: formatNumber(pos.altman_z, 2),
          good: pos.altman_z != null ? pos.altman_z > 2.99 : null,
        },
        {
          label: "Div Yield",
          value: pos.div_yield != null ? formatPercent(pos.div_yield) : "—",
        },
        {
          label: "52w High%",
          value: pos.fifty_two_week_high_pct != null ? formatPercent(pos.fifty_two_week_high_pct) : "—",
        },
      ])}
      {metricGroup("Analyst & Meta", [
        { label: "Rating", value: pos.analyst_rating ?? "—" },
        {
          label: "Target",
          value:
            pos.analyst_target_price != null
              ? formatCurrency(pos.analyst_target_price)
              : "—",
        },
        {
          label: "Account",
          value: ACCOUNT_TYPE_LABELS[pos.account_type] ?? pos.account_type,
        },
        { label: "Buy Date", value: formatDate(pos.buy_date) },
        { label: "Notes", value: pos.notes ?? "—" },
      ])}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sort header icon (hoisted out of PortfolioPage so React does not treat it as
// a new component on every render and reset its children's state).
// ---------------------------------------------------------------------------

function SortIcon({
  col,
  sortKey,
  sortDesc,
}: {
  col: string;
  sortKey: string;
  sortDesc: boolean;
}) {
  if (sortKey !== col) return <ChevronDown size={12} className="opacity-30" />;
  return sortDesc ? <ChevronDown size={12} /> : <ChevronUp size={12} />;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PortfolioPage() {
  const {
    data,
    loading,
    error,
    horizon,
    changeHorizon,
    addPosition,
    removePosition,
    updatePosition,
    refresh,
  } = usePortfolio("long_term");

  const [showAdd, setShowAdd] = useState(false);
  const [editingPosition, setEditingPosition] =
    useState<PortfolioPosition | null>(null);
  const [sortKey, setSortKey] = useState<string>("weight_pct");
  const [sortDesc, setSortDesc] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const sorted = useMemo(() => {
    if (!data?.positions) return [];
    return [...data.positions].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey] as
        | number
        | string
        | null
        | undefined;
      const bv = (b as unknown as Record<string, unknown>)[sortKey] as
        | number
        | string
        | null
        | undefined;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDesc ? bv - av : av - bv;
      }
      return sortDesc
        ? String(bv).localeCompare(String(av))
        : String(av).localeCompare(String(bv));
    });
  }, [data, sortKey, sortDesc]);

  function handleSort(key: string) {
    if (sortKey === key) setSortDesc((d) => !d);
    else {
      setSortKey(key);
      setSortDesc(true);
    }
  }

  // Derived score column key
  const scoreKey =
    horizon === "long_term"
      ? "score_lt"
      : horizon === "medium_term"
      ? "score_mt"
      : "score_st";

  const summary = data?.summary;

  const thCls =
    "px-3 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap select-none cursor-pointer hover:text-slate-700 dark:hover:text-slate-200";
  const tdCls = "px-3 py-2 text-sm whitespace-nowrap";

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6 space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
          Portfolio
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <HorizonSelector value={horizon} onChange={changeHorizon} />
          <button
            onClick={() => refresh()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
          >
            <Plus size={14} />
            Add Position
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryCard
            label="Total Value"
            value={formatCurrency(summary.total_value)}
            sub={`PEA: ${formatCurrency(summary.pea_value)}`}
            metricId="total_value"
          />
          <SummaryCard
            label="Total P&L"
            value={formatCurrency(summary.total_gain_loss)}
            sub={formatPercent(summary.total_gain_loss_pct)}
            positive={summary.total_gain_loss >= 0}
            metricId="total_gain_loss"
          />
          <SummaryCard
            label="Avg Score (LT)"
            value={formatNumber(summary.avg_score_lt, 1)}
            sub="Long-term (0-100)"
            metricId="avg_score_lt"
          />
          <SummaryCard
            label="Positions"
            value={String(summary.position_count)}
            sub={`Signals: ${Object.entries(summary.signal_distribution)
              .map(([k, v]) => `${v} ${k}`)
              .join(", ")}`}
            metricId="position_count"
          />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && !data && (
        <div className="flex justify-center items-center py-20">
          <Spinner size={32} />
        </div>
      )}

      {/* Table */}
      {data && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className={thCls} onClick={() => handleSort("ticker")}>
                    <span className="flex items-center gap-1">
                      Ticker <SortIcon col="ticker" sortKey={sortKey} sortDesc={sortDesc} />
                    </span>
                  </th>
                  <th className={thCls} onClick={() => handleSort("name")}>
                    <span className="flex items-center gap-1">
                      Name <SortIcon col="name" sortKey={sortKey} sortDesc={sortDesc} />
                    </span>
                  </th>
                  <th
                    className={`${thCls} text-right`}
                    onClick={() => handleSort("current_price")}
                  >
                    <span className="flex items-center justify-end gap-1">
                      Price <SortIcon col="current_price" sortKey={sortKey} sortDesc={sortDesc} />
                    </span>
                  </th>
                  <th
                    className={`${thCls} text-right`}
                    onClick={() => handleSort("quantity")}
                  >
                    <span className="flex items-center justify-end gap-1">
                      Qty <SortIcon col="quantity" sortKey={sortKey} sortDesc={sortDesc} />
                    </span>
                  </th>
                  <th
                    className={`${thCls} text-right`}
                    onClick={() => handleSort("cost_basis")}
                  >
                    <span className="flex items-center justify-end gap-1">
                      Cost <SortIcon col="cost_basis" sortKey={sortKey} sortDesc={sortDesc} />
                    </span>
                  </th>
                  <th
                    className={`${thCls} text-right`}
                    onClick={() => handleSort("market_value")}
                  >
                    <span className="flex items-center justify-end gap-1">
                      Value <SortIcon col="market_value" sortKey={sortKey} sortDesc={sortDesc} />
                    </span>
                  </th>
                  <th
                    className={`${thCls} text-right`}
                    onClick={() => handleSort("gain_loss_pct")}
                  >
                    <span className="flex items-center justify-end gap-1">
                      P&L% <SortIcon col="gain_loss_pct" sortKey={sortKey} sortDesc={sortDesc} />
                      <MetricInfo metricId="gain_loss_pct" size={11} />
                    </span>
                  </th>
                  <th
                    className={`${thCls} text-right`}
                    onClick={() => handleSort("weight_pct")}
                  >
                    <span className="flex items-center justify-end gap-1">
                      Weight <SortIcon col="weight_pct" sortKey={sortKey} sortDesc={sortDesc} />
                      <MetricInfo metricId="weight_pct" size={11} />
                    </span>
                  </th>
                  <th
                    className={thCls}
                    onClick={() => handleSort(scoreKey)}
                  >
                    <span className="flex items-center gap-1">
                      Score ({horizon === "long_term" ? "LT" : horizon === "medium_term" ? "MT" : "ST"})
                      <SortIcon col={scoreKey} sortKey={sortKey} sortDesc={sortDesc} />
                      <MetricInfo
                        metricId={
                          horizon === "long_term"
                            ? "score_lt"
                            : horizon === "medium_term"
                            ? "score_mt"
                            : "score_st"
                        }
                        size={11}
                      />
                    </span>
                  </th>
                  <th className={thCls}>
                    <span className="inline-flex items-center gap-1">
                      Signal
                      <MetricInfo metricId="signal" size={11} />
                    </span>
                  </th>
                  <th className={thCls}>
                    <span className="inline-flex items-center gap-1">
                      PEA
                      <MetricInfo metricId="pea_eligible" size={11} />
                    </span>
                  </th>
                  <th className={thCls}></th>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 && (
                  <tr>
                    <td
                      colSpan={12}
                      className="text-center py-12 text-sm text-slate-400"
                    >
                      No positions yet. Add your first position.
                    </td>
                  </tr>
                )}
                {sorted.map((pos) => {
                  const isExpanded = expandedId === pos.id;
                  const pnlPct = pos.gain_loss_pct ?? 0;
                  const pnlColor =
                    pnlPct > 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : pnlPct < 0
                      ? "text-red-500 dark:text-red-400"
                      : "text-slate-500";

                  const horizonScore = getScoreForHorizon(pos, horizon);
                  const horizonSignal = getSignalForHorizon(pos, horizon);

                  return [
                    <tr
                      key={pos.id}
                      className={clsx(
                        "border-t border-slate-100 dark:border-slate-800 cursor-pointer transition-colors",
                        isExpanded
                          ? "bg-slate-50 dark:bg-slate-800/40"
                          : "hover:bg-slate-50 dark:hover:bg-slate-800/30"
                      )}
                      onClick={() =>
                        setExpandedId(isExpanded ? null : pos.id)
                      }
                    >
                      <td className={tdCls}>
                        <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">
                          {pos.ticker}
                        </span>
                      </td>
                      <td className={`${tdCls} max-w-[140px]`}>
                        <span className="truncate block text-slate-700 dark:text-slate-300">
                          {pos.name}
                        </span>
                      </td>
                      <td className={`${tdCls} text-right font-mono`}>
                        {formatCurrency(pos.current_price)}
                      </td>
                      <td className={`${tdCls} text-right font-mono text-slate-600 dark:text-slate-400`}>
                        {formatNumber(pos.quantity, 2)}
                      </td>
                      <td className={`${tdCls} text-right font-mono text-slate-600 dark:text-slate-400`}>
                        {formatCurrency(pos.cost_basis)}
                      </td>
                      <td className={`${tdCls} text-right font-mono font-medium`}>
                        {formatCurrency(pos.market_value)}
                      </td>
                      <td className={`${tdCls} text-right font-mono ${pnlColor}`}>
                        {formatPercent(pnlPct)}
                      </td>
                      <td className={`${tdCls} text-right font-mono text-slate-500`}>
                        {formatPercent(pos.weight_pct ?? null, 1)}
                      </td>
                      <td className={tdCls}>
                        <ScoreBar score={horizonScore} />
                      </td>
                      <td className={tdCls}>
                        <SignalBadge signal={horizonSignal} />
                      </td>
                      <td className={tdCls}>
                        <PeaBadge
                          eligible={pos.pea_eligible ?? false}
                          pme={pos.pea_pme_eligible ?? false}
                        />
                      </td>
                      <td className={tdCls}>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingPosition(pos);
                            }}
                            className="p-1 rounded text-slate-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                            aria-label="Edit position"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              removePosition(pos.id);
                            }}
                            className="p-1 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            aria-label="Remove position"
                          >
                            <Trash2 size={13} />
                          </button>
                          <ChevronRight
                            size={14}
                            className={clsx(
                              "text-slate-400 transition-transform",
                              isExpanded && "rotate-90"
                            )}
                          />
                        </div>
                      </td>
                    </tr>,
                    isExpanded && (
                      <tr key={`${pos.id}-expand`}>
                        <td colSpan={12} className="p-0">
                          <ExpandedRow pos={pos} horizon={horizon} />
                        </td>
                      </tr>
                    ),
                  ];
                })}
              </tbody>
            </table>
          </div>
          {data.last_refreshed && (
            <div className="px-4 py-2 text-xs text-slate-400 border-t border-slate-100 dark:border-slate-800">
              Last refreshed: {formatDate(data.last_refreshed)}
            </div>
          )}
        </div>
      )}

      <AddPositionModal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        onSubmit={addPosition}
      />
      <EditPositionModal
        key={editingPosition?.id ?? "none"}
        open={editingPosition !== null}
        onClose={() => setEditingPosition(null)}
        position={editingPosition}
        onSubmit={async (id, req) => {
          await updatePosition(id, req);
          setEditingPosition(null);
        }}
      />
    </div>
  );
}
