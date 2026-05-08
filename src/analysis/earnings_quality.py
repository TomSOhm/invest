"""
Earnings Quality Module (M5)
============================
Pure-function library detecting accounting manipulation and earnings quality
weaknesses. No I/O, no network, no caching -- callers supply the inputs.

Implemented metrics:
    - Beneish M-Score (Beneish, 1999): 8-variable manipulation flag.
      M > -1.78 → likely manipulator.
    - Sloan Accruals (Sloan, 1996): NI vs CFO divergence as % of avg assets.
      > 0.10 = aggressive; > 0.20 = very aggressive (red flag).
    - Cash Conversion Ratio 5y avg: mean(FCF/NI). < 0.7 = quality concern.
    - earnings_quality_score: sector-relative composite 0..100. Higher = better.

Each per-row function is NaN-safe: missing inputs return NaN (the aggregator
skips NaNs when normalising). The aggregator falls back to z-score normalisation
when the M3 sector-relative percentile module is unavailable.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_finite(val: Any) -> bool:
    """True iff val is a finite numeric (rejects None, NaN, Inf, non-numeric)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


def _as_float(val: Any) -> float:
    """Cast to float, returning NaN on any failure."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return float("nan")
    return f if np.isfinite(f) else float("nan")


def _safe_div(num: Any, den: Any) -> float:
    """Numeric division returning NaN when either operand is NaN/0/non-numeric."""
    n, d = _as_float(num), _as_float(den)
    if not (np.isfinite(n) and np.isfinite(d)) or d == 0:
        return float("nan")
    return n / d


def _zscore_norm(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Map a Series to 0..100 via z-score winsorised at ±3 sigma.

    NaN values stay NaN; the caller decides how to fill them (typically 50.0).
    A constant series returns 50.0 for every finite value.
    """
    s = series.astype(float)
    if s.notna().sum() < 2:
        return pd.Series([50.0 if pd.notna(v) else np.nan for v in s], index=s.index)
    mu = s.mean(skipna=True)
    sigma = s.std(skipna=True, ddof=0)
    if not np.isfinite(sigma) or sigma == 0:
        return pd.Series([50.0 if pd.notna(v) else np.nan for v in s], index=s.index)
    z = (s - mu) / sigma
    z = z.clip(-3.0, 3.0)
    if not higher_is_better:
        z = -z
    # Map z ∈ [-3, 3] → [0, 100]
    return ((z + 3.0) / 6.0 * 100.0).clip(0.0, 100.0)


# ---------------------------------------------------------------------------
# Beneish M-Score (1999)
# ---------------------------------------------------------------------------

def beneish_m_score(row: pd.Series) -> float:
    """Beneish M-Score -- 8-variable manipulation flag.

    Inputs (current and prior year, all required):
        Receivables, Sales, GrossMargin, TotalAssets, CurrentAssets, PPE,
        DepreciationAmortization, SGA, NetIncome, CFO, LongTermDebt,
        CurrentLiabilities

    The row is expected to expose paired columns (current ``X`` and prior
    ``X_PriorYear``). Any missing input → return NaN.

    Formula::

        M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
            + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    Where:
        DSRI = (Receivables / Sales)_t / (Receivables / Sales)_t-1
        GMI  = GrossMargin_t-1 / GrossMargin_t
        AQI  = (NonCurrentAssets / TotalAssets)_t /  same prior year
        SGI  = Sales_t / Sales_t-1
        DEPI = (D&A / (D&A + PPE))_t-1 / same_t   -- depreciation slowdown
        SGAI = (SGA / Sales)_t / (SGA / Sales)_t-1
        TATA = (NetIncome - CFO) / TotalAssets    -- accruals to total assets
        LVGI = ((LTDebt + CurrLiab) / TotalAssets)_t / same prior year

    Returns
    -------
    float
        M-Score. M > -1.78 indicates likely earnings manipulation.
        NaN if any required input is missing.
    """
    # Pull the 12 inputs (current and prior). NaN-safe: any missing → NaN result.
    recv_t = _as_float(row.get("Receivables"))
    recv_p = _as_float(row.get("Receivables_PriorYear"))
    sales_t = _as_float(row.get("Revenue"))
    sales_p = _as_float(row.get("Revenue_PriorYear"))
    gm_t = _as_float(row.get("GrossMargin"))
    gm_p = _as_float(row.get("GrossMargin_PriorYear"))
    ta_t = _as_float(row.get("TotalAssets"))
    ta_p = _as_float(row.get("TotalAssets_PriorYear"))
    ca_t = _as_float(row.get("CurrentAssets"))
    ca_p = _as_float(row.get("CurrentAssets_PriorYear"))
    ppe_t = _as_float(row.get("PPE"))
    ppe_p = _as_float(row.get("PPE_PriorYear"))
    da_t = _as_float(row.get("DepreciationAmortization"))
    da_p = _as_float(row.get("DepreciationAmortization_PriorYear"))
    sga_t = _as_float(row.get("SGA"))
    sga_p = _as_float(row.get("SGA_PriorYear"))
    ni_t = _as_float(row.get("NetIncome"))
    cfo_t = _as_float(row.get("OperatingCashflow"))
    ltd_t = _as_float(row.get("LongTermDebt"))
    ltd_p = _as_float(row.get("LongTermDebt_PriorYear"))
    cl_t = _as_float(row.get("CurrentLiabilities"))
    cl_p = _as_float(row.get("CurrentLiabilities_PriorYear"))

    inputs = [
        recv_t, recv_p, sales_t, sales_p, gm_t, gm_p,
        ta_t, ta_p, ca_t, ca_p, ppe_t, ppe_p,
        da_t, da_p, sga_t, sga_p,
        ni_t, cfo_t,
        ltd_t, ltd_p, cl_t, cl_p,
    ]
    if not all(np.isfinite(x) for x in inputs):
        return float("nan")

    if sales_t <= 0 or sales_p <= 0 or ta_t <= 0 or ta_p <= 0:
        return float("nan")
    if gm_t <= 0 or gm_p <= 0:
        # Gross margins must be positive (negative GM is a red flag of its own,
        # but DSRI/GMI ratios become meaningless).
        return float("nan")

    # 1. DSRI -- receivables-to-sales acceleration
    dsri = _safe_div(recv_t / sales_t, recv_p / sales_p)

    # 2. GMI -- gross margin deterioration (prior/current)
    gmi = _safe_div(gm_p, gm_t)

    # 3. AQI -- asset quality (non-current/total)
    nca_t = ta_t - ca_t
    nca_p = ta_p - ca_p
    aqi_t = _safe_div(nca_t, ta_t)
    aqi_p = _safe_div(nca_p, ta_p)
    aqi = _safe_div(aqi_t, aqi_p)

    # 4. SGI -- sales growth
    sgi = _safe_div(sales_t, sales_p)

    # 5. DEPI -- depreciation slowdown. Note: numerator uses prior, denom current.
    depi_num = _safe_div(da_p, da_p + ppe_p)
    depi_den = _safe_div(da_t, da_t + ppe_t)
    depi = _safe_div(depi_num, depi_den)

    # 6. SGAI -- SG&A intensity change
    sgai = _safe_div(sga_t / sales_t, sga_p / sales_p)

    # 7. TATA -- total accruals to total assets (current period only)
    tata = _safe_div(ni_t - cfo_t, ta_t)

    # 8. LVGI -- leverage growth
    lvgi_t = _safe_div(ltd_t + cl_t, ta_t)
    lvgi_p = _safe_div(ltd_p + cl_p, ta_p)
    lvgi = _safe_div(lvgi_t, lvgi_p)

    eight = [dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi]
    if not all(np.isfinite(x) for x in eight):
        return float("nan")

    m = (
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )
    return float(m)


# ---------------------------------------------------------------------------
# Sloan Accruals (1996)
# ---------------------------------------------------------------------------

def sloan_accruals(row: pd.Series) -> float:
    """Sloan accruals = (NetIncome - CFO) / Average(TotalAssets_t, TotalAssets_t-1).

    Threshold flags (interpretive, not enforced here):
        > 0.10 → aggressive accruals
        > 0.20 → very aggressive (red flag)

    Returns NaN if any required input is missing.
    """
    ni = _as_float(row.get("NetIncome"))
    cfo = _as_float(row.get("OperatingCashflow"))
    ta_t = _as_float(row.get("TotalAssets"))
    ta_p = _as_float(row.get("TotalAssets_PriorYear"))

    if not all(np.isfinite(x) for x in (ni, cfo, ta_t, ta_p)):
        return float("nan")
    avg_ta = (ta_t + ta_p) / 2.0
    if avg_ta <= 0:
        return float("nan")
    return float((ni - cfo) / avg_ta)


# ---------------------------------------------------------------------------
# Cash Conversion Ratio (5y average)
# ---------------------------------------------------------------------------

def cash_conversion_ratio_5y(
    row: pd.Series,
    fcf_history: Optional[Sequence[float]] = None,
    ni_history: Optional[Sequence[float]] = None,
) -> float:
    """Mean of FCF_t / NetIncome_t over the supplied 5-year history.

    Interpretation: < 0.7 means net income is not converting to cash, a quality
    concern. Returns NaN if either history has < 3 valid years (NaNs and
    NI <= 0 are treated as missing for that year because FCF/NI flips sign in
    loss years, contaminating the mean).

    Parameters
    ----------
    row:
        The row series. If ``fcf_history`` / ``ni_history`` are not supplied,
        the method reads ``FCF_History_5y`` / ``NetIncome_History_5y`` columns.
    fcf_history, ni_history:
        Optional explicit overrides.

    Returns
    -------
    float
        Mean FCF/NI ratio, or NaN if insufficient valid year-pairs.
    """
    fcf_seq = fcf_history if fcf_history is not None else row.get("FCF_History_5y")
    ni_seq = ni_history if ni_history is not None else row.get("NetIncome_History_5y")

    fcf_list = _to_list(fcf_seq)
    ni_list = _to_list(ni_seq)
    if not fcf_list or not ni_list:
        return float("nan")

    n = min(len(fcf_list), len(ni_list))
    ratios: List[float] = []
    for i in range(n):
        fcf_i = _as_float(fcf_list[i])
        ni_i = _as_float(ni_list[i])
        if not (np.isfinite(fcf_i) and np.isfinite(ni_i)):
            continue
        if ni_i <= 0:
            # Loss years invalidate the ratio; skip (Sloan paper convention).
            continue
        ratios.append(fcf_i / ni_i)

    if len(ratios) < 3:
        return float("nan")
    return float(np.mean(ratios))


def _to_list(seq: Any) -> List[Any]:
    """Best-effort coerce a column value to a list of scalars (None on failure)."""
    if seq is None:
        return []
    if isinstance(seq, (list, tuple)):
        return list(seq)
    if isinstance(seq, np.ndarray):
        return seq.tolist()
    if isinstance(seq, pd.Series):
        return seq.tolist()
    if isinstance(seq, float) and np.isnan(seq):
        return []
    # Allow JSON-string fallback used by the snapshot loader
    if isinstance(seq, str):
        try:
            import json
            data = json.loads(seq)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


# ---------------------------------------------------------------------------
# Aggregator -- earnings_quality_score (0..100, sector-relative)
# ---------------------------------------------------------------------------

def earnings_quality_score(df: pd.DataFrame) -> pd.Series:
    """Sector-relative composite of M-Score (low=good), Sloan accruals (low=good),
    and CCR (high=good). Returns a Series of 0..100 floats indexed by row.

    Workflow:
        1. Compute the three raw signals per row.
        2. Normalise via M3's ``sector_relative_percentile`` if available;
           otherwise fall back to z-score normalisation.
        3. Equal-weight average. Rows where all three signals are NaN get 50.0.
    """
    # Compute per-row raw signals
    m_scores = df.apply(beneish_m_score, axis=1)
    sloan_vals = df.apply(sloan_accruals, axis=1)
    ccr_vals = df.apply(
        lambda r: cash_conversion_ratio_5y(
            r,
            fcf_history=r.get("FCF_History_5y"),
            ni_history=r.get("NetIncome_History_5y"),
        ),
        axis=1,
    )

    # M3 sector-relative percentile (canonical API: score_sector_relative(df,
    # metric, inverse=...)). Fall back to z-score normalisation if missing.
    try:
        from src.analysis.sector_percentile import score_sector_relative  # type: ignore
        sectors = df.get("Sector", pd.Series(["" for _ in range(len(df))], index=df.index))
        tmp = pd.DataFrame({"m": m_scores, "sloan": sloan_vals, "ccr": ccr_vals, "Sector": sectors}, index=df.index)
        m_norm = score_sector_relative(tmp, "m", inverse=True)
        sloan_norm = score_sector_relative(tmp, "sloan", inverse=True)
        ccr_norm = score_sector_relative(tmp, "ccr", inverse=False)
    except (ImportError, AttributeError, TypeError):
        m_norm = _zscore_norm(m_scores, higher_is_better=False)
        sloan_norm = _zscore_norm(sloan_vals, higher_is_better=False)
        ccr_norm = _zscore_norm(ccr_vals, higher_is_better=True)

    # Equal-weight average, NaN-safe (skipna=True with mean across columns)
    parts = pd.concat({"m": m_norm, "sloan": sloan_norm, "ccr": ccr_norm}, axis=1)
    score = parts.mean(axis=1, skipna=True)
    score = score.fillna(50.0).clip(0.0, 100.0)
    return score.round(1)
