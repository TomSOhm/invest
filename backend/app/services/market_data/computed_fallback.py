"""Computed-fallback layer: derive scoring fields from raw inputs when the
primary backends (FMP, yfinance) left them NaN.

This module performs no I/O. It operates on a fully-populated row dict and
only touches fields whose current value is NaN AND whose ``field_sources``
entry is currently ``"missing"``. Each recomputed field's provenance is
updated to ``"computed"`` so the coverage matrix can tell the tiers apart
(fmp / yfinance / computed / missing).
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _is_finite(val: Any) -> bool:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


def _safe_div(a: Any, b: Any) -> float:
    if not (_is_finite(a) and _is_finite(b)):
        return float("nan")
    bf = float(b)
    if bf == 0:
        return float("nan")
    return float(a) / bf


def _maybe_set(
    row: dict[str, Any],
    sources: dict[str, str],
    field: str,
    value: float,
) -> None:
    """Set the field + mark source 'computed' only when:
    - the candidate value is finite,
    - the current row[field] is NaN,
    - the current sources[field] is 'missing'.

    Never overwrites a legitimate 'fmp' or 'yfinance' provenance.
    """
    if not _is_finite(value):
        return
    if _is_finite(row.get(field)):
        return
    if sources.get(field, "missing") != "missing":
        return
    row[field] = float(value)
    sources[field] = "computed"


def recompute_interest_coverage(row: dict[str, Any], sources: dict[str, str]) -> None:
    ebit = row.get("EBIT")
    ie = row.get("InterestExpense")
    if _is_finite(ebit) and _is_finite(ie):
        ie_abs = abs(float(ie))
        if ie_abs > 0:
            _maybe_set(row, sources, "InterestCoverage", float(ebit) / ie_abs)


def recompute_fcf(row: dict[str, Any], sources: dict[str, str]) -> None:
    ocf = row.get("OperatingCashflow")
    capex = row.get("CapEx")
    if _is_finite(ocf) and _is_finite(capex):
        _maybe_set(row, sources, "FCF", float(ocf) - abs(float(capex)))


def recompute_fcf_margin(row: dict[str, Any], sources: dict[str, str]) -> None:
    fcf = row.get("FCF")
    rev = row.get("Revenue")
    if _is_finite(fcf) and _is_finite(rev) and float(rev) > 0:
        _maybe_set(row, sources, "FCFMargin", float(fcf) / float(rev))


def recompute_revenue_growth(row: dict[str, Any], sources: dict[str, str]) -> None:
    rev = row.get("Revenue")
    rev_prior = row.get("Revenue_PriorYear")
    if _is_finite(rev) and _is_finite(rev_prior) and float(rev_prior) > 0:
        _maybe_set(row, sources, "RevenueGrowth", float(rev) / float(rev_prior) - 1)


def recompute_roic(row: dict[str, Any], sources: dict[str, str]) -> None:
    ebit = row.get("EBIT")
    equity = row.get("TotalEquity")
    debt = row.get("TotalDebt")
    cash = row.get("Cash")
    if all(_is_finite(v) for v in (ebit, equity, debt, cash)):
        invested = float(equity) + float(debt) - float(cash)
        if invested > 0:
            _maybe_set(row, sources, "ROIC", (float(ebit) * 0.75) / invested)


def recompute_current_ratio(row: dict[str, Any], sources: dict[str, str]) -> None:
    ca = row.get("CurrentAssets")
    cl = row.get("CurrentLiabilities")
    if _is_finite(ca) and _is_finite(cl):
        _maybe_set(row, sources, "CurrentRatio", _safe_div(ca, cl))


def recompute_debt_equity(row: dict[str, Any], sources: dict[str, str]) -> None:
    debt = row.get("TotalDebt")
    equity = row.get("TotalEquity")
    if _is_finite(debt) and _is_finite(equity):
        _maybe_set(row, sources, "DebtEquity", _safe_div(debt, equity))


_RECOMPUTERS = (
    recompute_fcf,
    recompute_interest_coverage,
    recompute_revenue_growth,
    recompute_roic,
    recompute_current_ratio,
    recompute_debt_equity,
    recompute_fcf_margin,  # depends on recompute_fcf running first
)


def apply_computed_fallback(
    row: dict[str, Any],
    sources: dict[str, str],
) -> None:
    """Run every recomputer in dependency order. Idempotent."""
    for fn in _RECOMPUTERS:
        fn(row, sources)
