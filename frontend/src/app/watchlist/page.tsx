"use client";

import { useState, useRef } from "react";
import { Plus, RefreshCw, Trash2, PlusCircle } from "lucide-react";
import { useWatchlist } from "@/hooks/useWatchlist";
import type {
  AddPositionRequest,
  Horizon,
  WatchlistItem,
} from "@/lib/types";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatDate,
} from "@/lib/formatters";
import SignalBadge from "@/components/ui/SignalBadge";
import PeaBadge from "@/components/ui/PeaBadge";
import Modal from "@/components/ui/Modal";
import Spinner from "@/components/ui/Spinner";
import { ScoreBar } from "@/components/ui/ScoreGauge";
import HorizonSelector from "@/components/ui/HorizonSelector";
import SourceSelector from "@/components/ui/SourceSelector";
import { useDataSource } from "@/hooks/useDataSource";
import CTOWarningBanner from "@/components/ui/CTOWarningBanner";
import MetricInfo from "@/components/ui/MetricInfo";
import { api } from "@/lib/api";
import type { PortfolioPosition } from "@/lib/types";
import clsx from "clsx";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getScoreForHorizon(item: WatchlistItem, horizon: Horizon): number | null {
  if (horizon === "long_term") return item.score_lt ?? null;
  if (horizon === "medium_term") return item.score_mt ?? null;
  return item.score_st ?? null;
}

function getSignalForHorizon(item: WatchlistItem, horizon: Horizon): string | null {
  if (horizon === "long_term") return item.signal_lt ?? null;
  if (horizon === "medium_term") return item.signal_mt ?? null;
  return item.signal_st ?? null;
}

function passesGatesForHorizon(item: WatchlistItem, horizon: Horizon): boolean | null {
  // WatchlistItem does not expose passes_gates; use score as proxy (null if unavailable)
  const score = getScoreForHorizon(item, horizon);
  return score != null ? score >= 50 : null;
}

// ---------------------------------------------------------------------------
// Add-to-portfolio modal
// ---------------------------------------------------------------------------

function AddToPortfolioModal({
  open,
  onClose,
  item,
}: {
  open: boolean;
  onClose: () => void;
  item: WatchlistItem | null;
}) {
  const [form, setForm] = useState({
    quantity: 1,
    buy_price: item?.current_price ?? 0,
    buy_date: "",
    account_type: "pea" as "pea" | "pea_pme" | "cto",
    notes: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function update<K extends keyof typeof form>(
    key: K,
    val: (typeof form)[K]
  ) {
    setForm((f) => ({ ...f, [key]: val }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!item) return;
    setErr(null);
    setSubmitting(true);
    try {
      const req: AddPositionRequest = {
        ticker: item.ticker,
        quantity: form.quantity,
        buy_price: form.buy_price,
        buy_date: form.buy_date || undefined,
        account_type: form.account_type,
        notes: form.notes || undefined,
      };
      await api.post<PortfolioPosition>("/api/portfolio/positions", req);
      setSuccess(true);
      setTimeout(onClose, 1200);
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
    <Modal
      open={open}
      onClose={onClose}
      title={`Add ${item?.ticker ?? ""} to Portfolio`}
    >
      {success ? (
        <div className="py-6 text-center text-emerald-600 dark:text-emerald-400 text-sm font-medium">
          Position added successfully!
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
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
                onChange={(e) =>
                  update("buy_price", parseFloat(e.target.value))
                }
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
                    e.target.value as typeof form.account_type
                  )
                }
              >
                <option value="pea">PEA</option>
                <option value="pea_pme">PEA-PME</option>
                <option value="cto">CTO</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Buy Date</label>
              <input
                className={inputCls}
                type="date"
                value={form.buy_date}
                onChange={(e) => update("buy_date", e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className={labelCls}>Notes</label>
            <input
              className={inputCls}
              value={form.notes}
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
              Add to Portfolio
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function WatchlistPage() {
  const { source, setSource } = useDataSource();
  const { data, loading, error, addItem, removeItem, refresh } = useWatchlist(source);
  const [horizon, setHorizon] = useState<Horizon>("long_term");
  const [tickerInput, setTickerInput] = useState("");
  const [notesInput, setNotesInput] = useState("");
  const [adding, setAdding] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);
  const [portfolioItem, setPortfolioItem] = useState<WatchlistItem | null>(
    null
  );
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleAdd() {
    const t = tickerInput.trim().toUpperCase();
    if (!t) return;
    setAdding(true);
    setAddErr(null);
    const result = await addItem({ ticker: t, notes: notesInput || undefined });
    setAdding(false);
    if (result) {
      setTickerInput("");
      setNotesInput("");
    } else {
      setAddErr("Failed to add ticker");
    }
  }

  const thCls =
    "px-3 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap";
  const tdCls = "px-3 py-2 text-sm whitespace-nowrap";

  return (
    <div className="max-w-screen-xl mx-auto px-4 py-6 space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
          Watchlist
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <SourceSelector value={source} onChange={setSource} />
          <HorizonSelector value={horizon} onChange={setHorizon} />
          <button
            onClick={() => refresh()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* CTO warning for short-term */}
      {horizon === "short_term" && <CTOWarningBanner />}

      {/* Add ticker form */}
      <div className="flex gap-2 flex-wrap">
        <input
          ref={inputRef}
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="Ticker (e.g. ASML.AS)"
          className="px-3 py-2 text-sm rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 w-44"
        />
        <input
          value={notesInput}
          onChange={(e) => setNotesInput(e.target.value)}
          placeholder="Notes (optional)"
          className="px-3 py-2 text-sm rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 flex-1 min-w-40"
        />
        <button
          onClick={handleAdd}
          disabled={adding || !tickerInput.trim()}
          className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60 transition-colors"
        >
          {adding ? <Spinner size={14} /> : <Plus size={14} />}
          Add
        </button>
        {addErr && (
          <span className="text-sm text-red-500 self-center">{addErr}</span>
        )}
      </div>

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
                  <th className={thCls}>Ticker</th>
                  <th className={thCls}>Name</th>
                  <th className={`${thCls} text-right`}>Price</th>
                  <th className={thCls}>
                    <span className="inline-flex items-center gap-1">
                      Score
                      <MetricInfo metricId="score_lt" size={11} />
                    </span>
                  </th>
                  <th className={thCls}>
                    <span className="inline-flex items-center gap-1">
                      Signal
                      <MetricInfo metricId="signal" size={11} />
                    </span>
                  </th>
                  <th className={`${thCls} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      P/E
                      <MetricInfo metricId="pe" size={11} />
                    </span>
                  </th>
                  <th className={`${thCls} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      ROE
                      <MetricInfo metricId="roe" size={11} />
                    </span>
                  </th>
                  <th className={`${thCls} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      Graham MoS
                      <MetricInfo metricId="graham_mos" size={11} />
                    </span>
                  </th>
                  <th className={`${thCls} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      DCF MoS
                      <MetricInfo metricId="dcf_mos" size={11} />
                    </span>
                  </th>
                  <th className={thCls}>Analyst</th>
                  <th className={thCls}>PEA</th>
                  {horizon === "short_term" && <th className={thCls}>Account</th>}
                  <th className={thCls}>Added</th>
                  <th className={thCls}></th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td
                      colSpan={13}
                      className="text-center py-12 text-sm text-slate-400"
                    >
                      No items in watchlist. Add a ticker above.
                    </td>
                  </tr>
                )}
                {data.items.map((item) => {
                  const horizonScore = getScoreForHorizon(item, horizon);
                  const horizonSignal = getSignalForHorizon(item, horizon);
                  // ST view shows CTO chip when passes_gates_st proxy is true
                  const showCTOChip =
                    horizon === "short_term" &&
                    passesGatesForHorizon(item, "short_term");

                  return (
                    <tr
                      key={item.id}
                      className="border-t border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors"
                    >
                      <td className={tdCls}>
                        <a
                          href={`/company/${item.ticker}`}
                          className="font-mono font-semibold text-emerald-600 dark:text-emerald-400 hover:underline"
                        >
                          {item.ticker}
                        </a>
                      </td>
                      <td className={`${tdCls} max-w-[160px]`}>
                        <span className="truncate block text-slate-700 dark:text-slate-300">
                          {item.name}
                        </span>
                      </td>
                      <td className={`${tdCls} text-right font-mono`}>
                        {formatCurrency(item.current_price)}
                      </td>
                      <td className={tdCls}>
                        <ScoreBar score={horizonScore} />
                      </td>
                      <td className={tdCls}>
                        <SignalBadge signal={horizonSignal} />
                      </td>
                      <td className={`${tdCls} text-right font-mono text-slate-600 dark:text-slate-400`}>
                        {formatNumber(item.pe, 1)}
                      </td>
                      <td
                        className={clsx(
                          `${tdCls} text-right font-mono`,
                          item.roe != null && item.roe > 10
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-slate-600 dark:text-slate-400"
                        )}
                      >
                        {item.roe != null ? formatPercent(item.roe) : "—"}
                      </td>
                      <td
                        className={clsx(
                          `${tdCls} text-right font-mono`,
                          item.graham_mos != null && item.graham_mos > 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-red-500 dark:text-red-400"
                        )}
                      >
                        {item.graham_mos != null
                          ? formatPercent(item.graham_mos)
                          : "—"}
                      </td>
                      <td
                        className={clsx(
                          `${tdCls} text-right font-mono`,
                          item.dcf_mos_mid != null && item.dcf_mos_mid > 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-red-500 dark:text-red-400"
                        )}
                      >
                        {item.dcf_mos_mid != null
                          ? formatPercent(item.dcf_mos_mid * 100)
                          : "—"}
                      </td>
                      <td className={`${tdCls} text-slate-500`}>
                        {item.analyst_rating ?? "—"}
                        {item.analyst_target_price != null && (
                          <span className="ml-1 text-xs">
                            {formatCurrency(item.analyst_target_price)}
                          </span>
                        )}
                      </td>
                      <td className={tdCls}>
                        <PeaBadge
                          eligible={item.pea_eligible ?? false}
                          pme={item.pea_pme_eligible ?? false}
                        />
                      </td>
                      {horizon === "short_term" && (
                        <td className={tdCls}>
                          {showCTOChip ? (
                            <span className="px-1.5 py-0.5 text-xs font-semibold rounded bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300">
                              CTO
                            </span>
                          ) : null}
                        </td>
                      )}
                      <td className={`${tdCls} text-slate-400 text-xs`}>
                        {formatDate(item.added_date)}
                      </td>
                      <td className={tdCls}>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => setPortfolioItem(item)}
                            title="Add to Portfolio"
                            className="p-1 rounded text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors"
                            aria-label="Add to portfolio"
                          >
                            <PlusCircle size={14} />
                          </button>
                          <button
                            onClick={() => removeItem(item.id)}
                            title="Remove from watchlist"
                            className="p-1 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            aria-label="Remove from watchlist"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
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

      <AddToPortfolioModal
        open={portfolioItem !== null}
        onClose={() => setPortfolioItem(null)}
        item={portfolioItem}
      />
    </div>
  );
}
