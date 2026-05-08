"""
Quality / Moat Module (M5)
==========================
Pure-function library scoring the durability of a company's economic moat.
Inputs come from the data fetcher; no I/O happens here.

Implemented metrics:
    - Gross profitability (Novy-Marx 2013): GP / TotalAssets.
    - ROIC 5y average and stability (inverse-stddev): consistent compounders.
    - Operating margin stability: pricing power proxy.
    - ROIC - WACC spread: positive sustained spread = real economic moat.
    - Reinvestment efficiency: ΔEBIT / ΔInvestedCapital over a 3y window.
    - moat_score(df): 0..100 sector-relative composite.

WACC handling: ``roic_wacc_spread`` reads ``WACC`` from the row when
available; otherwise falls back to a default cost-of-equity of 9% (settings
override possible via the ``moat_default_wacc`` setting). M6 will populate
real WACC; for M5 the placeholder column is set to NaN by the data fetcher.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

import numpy as np
import pandas as pd


_DEFAULT_WACC = 0.09  # 9% cost of equity, used when WACC column missing


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_finite(val: Any) -> bool:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


def _as_float(val: Any) -> float:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return float("nan")
    return f if np.isfinite(f) else float("nan")


def _to_list(seq: Any) -> List[Any]:
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
    if isinstance(seq, str):
        try:
            import json
            data = json.loads(seq)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _finite_floats(seq: Any) -> List[float]:
    """Return only the finite-numeric entries of seq."""
    out: List[float] = []
    for v in _to_list(seq):
        f = _as_float(v)
        if np.isfinite(f):
            out.append(f)
    return out


def _zscore_norm(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = series.astype(float)
    if s.notna().sum() < 2:
        return pd.Series([50.0 if pd.notna(v) else np.nan for v in s], index=s.index)
    mu = s.mean(skipna=True)
    sigma = s.std(skipna=True, ddof=0)
    if not np.isfinite(sigma) or sigma == 0:
        return pd.Series([50.0 if pd.notna(v) else np.nan for v in s], index=s.index)
    z = ((s - mu) / sigma).clip(-3.0, 3.0)
    if not higher_is_better:
        z = -z
    return ((z + 3.0) / 6.0 * 100.0).clip(0.0, 100.0)


# ---------------------------------------------------------------------------
# Per-row functions
# ---------------------------------------------------------------------------

def gross_profitability(row: pd.Series) -> float:
    """Novy-Marx 2013: GP / TA = (Revenue - COGS) / TotalAssets.

    Stronger predictor of future returns than book-to-market in their study.
    Heuristic interpretation: > 0.30 = strong moat. Returns NaN on missing.
    """
    rev = _as_float(row.get("Revenue"))
    ta = _as_float(row.get("TotalAssets"))
    cogs = _as_float(row.get("COGS"))
    if not (np.isfinite(rev) and np.isfinite(ta) and np.isfinite(cogs)) or ta <= 0:
        # Fall back to GrossMargin × Revenue / TotalAssets when COGS is missing
        gm = _as_float(row.get("GrossMargin"))
        if np.isfinite(rev) and np.isfinite(ta) and np.isfinite(gm) and ta > 0:
            return float(gm * rev / ta)
        return float("nan")
    gp = rev - cogs
    return float(gp / ta)


def roic_5y_avg(
    row: pd.Series,
    roic_history: Optional[Sequence[float]] = None,
) -> float:
    """5y average ROIC. Reads ``ROIC_History_5y`` from the row when no override given.

    Returns NaN if fewer than 3 valid years.
    """
    seq = roic_history if roic_history is not None else row.get("ROIC_History_5y")
    vals = _finite_floats(seq)
    if len(vals) < 3:
        return float("nan")
    return float(np.mean(vals))


def roic_stability(
    row: pd.Series,
    roic_history: Optional[Sequence[float]] = None,
) -> float:
    """Inverse stddev of ROIC: higher = more stable. NaN if < 3 years.

    Computed as ``1 / (1 + stddev)`` so that stddev=0 → 1.0 (max stability)
    and stddev=∞ → 0 (no stability). The 0..1 range is convenient for the
    sector-relative aggregator without a winsorisation step.
    """
    seq = roic_history if roic_history is not None else row.get("ROIC_History_5y")
    vals = _finite_floats(seq)
    if len(vals) < 3:
        return float("nan")
    sigma = float(np.std(vals, ddof=0))
    return float(1.0 / (1.0 + sigma))


def operating_margin_stability(
    row: pd.Series,
    op_margin_history: Optional[Sequence[float]] = None,
) -> float:
    """Inverse-stddev of operating margins. Same shape as ``roic_stability``."""
    seq = (
        op_margin_history
        if op_margin_history is not None
        else row.get("OperatingMargin_History_5y")
    )
    vals = _finite_floats(seq)
    if len(vals) < 3:
        return float("nan")
    sigma = float(np.std(vals, ddof=0))
    return float(1.0 / (1.0 + sigma))


def roic_wacc_spread(row: pd.Series) -> float:
    """ROIC - WACC. Positive sustained spread is the textbook moat signal.

    For M5, ``WACC`` is read from the row when present; otherwise we fall back
    to a default cost-of-equity of 9%. M6 will populate the real WACC column.
    """
    roic = _as_float(row.get("ROIC"))
    wacc = _as_float(row.get("WACC"))
    if not np.isfinite(wacc):
        wacc = _DEFAULT_WACC
    if not np.isfinite(roic):
        return float("nan")
    return float(roic - wacc)


def reinvestment_efficiency(row: pd.Series) -> float:
    """ΔEBIT / ΔInvestedCapital over a 3y window.

    Reads ``EBIT_History_3y`` and ``InvestedCapital_History_3y`` (lists ordered
    most-recent first). Returns NaN if either has fewer than 2 valid entries
    or if the change in invested capital is non-positive (we cannot infer
    compounding from a divestment / contraction event).

    > 1.0 means each new euro invested grew operating profit by more than one
    euro -- the textbook "high return on incremental capital" compounding
    machine.
    """
    ebit_seq = _finite_floats(row.get("EBIT_History_3y"))
    ic_seq = _finite_floats(row.get("InvestedCapital_History_3y"))
    if len(ebit_seq) < 2 or len(ic_seq) < 2:
        return float("nan")

    # Most-recent first; compute deltas earliest -> latest
    d_ebit = ebit_seq[0] - ebit_seq[-1]
    d_ic = ic_seq[0] - ic_seq[-1]
    if d_ic <= 0:
        return float("nan")
    return float(d_ebit / d_ic)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def moat_score(df: pd.DataFrame) -> pd.Series:
    """Sector-relative composite of GP/TA, ROIC 5y avg, ROIC stability,
    OpMargin stability, ROIC-WACC spread, and reinvestment efficiency.

    All six signals are normalised to 0..100 (higher = better) and averaged
    with equal weights. Missing inputs are skipped per row; rows where all
    six are NaN get 50.0.
    """
    gp = df.apply(gross_profitability, axis=1)
    roic_avg = df.apply(lambda r: roic_5y_avg(r, r.get("ROIC_History_5y")), axis=1)
    roic_stab = df.apply(lambda r: roic_stability(r, r.get("ROIC_History_5y")), axis=1)
    op_stab = df.apply(
        lambda r: operating_margin_stability(r, r.get("OperatingMargin_History_5y")),
        axis=1,
    )
    spread = df.apply(roic_wacc_spread, axis=1)
    reinvest = df.apply(reinvestment_efficiency, axis=1)

    # Build a temp DataFrame so we can call M3's score_sector_relative
    # (which expects df + metric column name + inverse=...).
    sectors = df.get("Sector", pd.Series(["" for _ in range(len(df))], index=df.index))
    tmp = pd.DataFrame(
        {
            "gp": gp,
            "roic_avg": roic_avg,
            "roic_stab": roic_stab,
            "op_stab": op_stab,
            "spread": spread,
            "reinvest": reinvest,
            "Sector": sectors,
        },
        index=df.index,
    )
    try:
        from src.analysis.sector_percentile import score_sector_relative  # type: ignore

        def _norm(metric: str, higher_is_better: bool) -> pd.Series:
            return score_sector_relative(tmp, metric, inverse=not higher_is_better)
    except (ImportError, AttributeError, TypeError):
        def _norm(metric: str, higher_is_better: bool) -> pd.Series:
            return _zscore_norm(tmp[metric], higher_is_better=higher_is_better)

    parts = pd.concat(
        {
            "gp": _norm("gp", True),
            "roic_avg": _norm("roic_avg", True),
            "roic_stab": _norm("roic_stab", True),
            "op_stab": _norm("op_stab", True),
            "spread": _norm("spread", True),
            "reinvest": _norm("reinvest", True),
        },
        axis=1,
    )
    score = parts.mean(axis=1, skipna=True).fillna(50.0).clip(0.0, 100.0)
    return score.round(1)
