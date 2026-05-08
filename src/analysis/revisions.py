"""
Invest Solo -- EPS Revisions & Earnings Surprise Signals (M9)

Pure-pandas/numpy implementations of the consensus-revision factors and the
SUE (Standardised Unexpected Earnings) z-score.  These power the
post-earnings-announcement-drift (PEAD) and analyst-revision tilts in the ST
horizon (METHODOLOGY_v2.md).

The bulk variant ``revisions_signals_df`` is the column block joined back
onto the scoring universe in ``score_universe``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Candidate column names FMP uses for the consensus-EPS field across endpoints.
_EPS_AVG_COLUMNS = (
    "estimatedEpsAvg",
    "estimatedEPSAvg",
    "epsAvg",
    "averageEstimate",
)

_DATE_COLUMNS = ("date", "Date", "reportDate", "calendarYear")


def _find_first_column(df: pd.DataFrame, candidates) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize_estimates(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with a parsed datetime ``date`` column and a
    numeric consensus-EPS column. Empty/None input returns an empty frame."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date", "epsAvg"])

    out = df.copy()
    date_col = _find_first_column(out, _DATE_COLUMNS)
    eps_col = _find_first_column(out, _EPS_AVG_COLUMNS)
    if date_col is None or eps_col is None:
        return pd.DataFrame(columns=["date", "epsAvg"])

    out["date"] = pd.to_datetime(out[date_col], errors="coerce")
    out["epsAvg"] = pd.to_numeric(out[eps_col], errors="coerce")
    out = out.dropna(subset=["date", "epsAvg"]).sort_values("date")
    return out[["date", "epsAvg"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# eps_revision_change
# ---------------------------------------------------------------------------


def eps_revision_change(estimates_history: pd.DataFrame, days: int) -> float:
    """% change in median consensus EPS estimate over ``days`` calendar days.

    Strategy
    --------
    1. Pick the most recent estimate row (``epsAvg_now``).
    2. Find the row with date closest to ``now - days`` calendar days.
    3. Return ``(epsAvg_now / epsAvg_then - 1)``.

    Returns NaN if the input is empty, the lookback row falls outside the
    history, the prior estimate is non-positive, or either value is non-finite.
    """
    df = _normalize_estimates(estimates_history)
    if df.empty or len(df) < 2:
        return float("nan")

    latest_date = df["date"].iloc[-1]
    latest_eps = df["epsAvg"].iloc[-1]
    if not np.isfinite(latest_eps):
        return float("nan")

    target_date = latest_date - pd.Timedelta(days=days)
    prior_rows = df[df["date"] <= target_date]
    if prior_rows.empty:
        # Not enough history covering the lookback window
        return float("nan")
    prior_eps = prior_rows["epsAvg"].iloc[-1]

    if not np.isfinite(prior_eps) or prior_eps == 0:
        return float("nan")

    return float(latest_eps / prior_eps - 1.0)


# ---------------------------------------------------------------------------
# sue_z_score
# ---------------------------------------------------------------------------


def sue_z_score(reported_eps: float, expected_eps: float, prior_surprises_std: float) -> float:
    """Standardised Unexpected Earnings.

    Formula
    -------
        SUE = (reported_eps - expected_eps) / stddev(prior 4 quarter surprises)

    Returns NaN if any input is non-finite or ``prior_surprises_std`` <= 0.
    Convention: SUE > 1.5 = strong beat (PEAD candidate);
    SUE < -1.5 = strong miss.
    """
    if not all(
        isinstance(x, (int, float, np.floating)) and np.isfinite(x)
        for x in (reported_eps, expected_eps, prior_surprises_std)
    ):
        return float("nan")
    if prior_surprises_std <= 0:
        return float("nan")
    return float((reported_eps - expected_eps) / prior_surprises_std)


# ---------------------------------------------------------------------------
# revisions_score (composite 0-100)
# ---------------------------------------------------------------------------


def revisions_score(
    eps_estimates: pd.DataFrame,
    latest_surprise: Optional[Dict[str, Any]] = None,
) -> float:
    """0-100 composite of revision-momentum signals.

    Components (sum to 100):
        - EPS revision 30d positive   :  20 pts (linear from -5% to +5%)
        - EPS revision 90d positive   :  25 pts (linear from -10% to +10%)
        - EPS revision 180d positive  :  25 pts (linear from -15% to +15%)
        - SUE positive                :  30 pts (linear from -2 to +2)

    ``latest_surprise`` dict expects keys:
        ``reported_eps``, ``expected_eps``, ``prior_surprises_std``.

    Returns NaN if the estimates frame is empty AND there's no usable surprise.
    """
    rev_30 = eps_revision_change(eps_estimates, 30)
    rev_90 = eps_revision_change(eps_estimates, 90)
    rev_180 = eps_revision_change(eps_estimates, 180)

    sue = float("nan")
    if latest_surprise:
        sue = sue_z_score(
            latest_surprise.get("reported_eps", float("nan")),
            latest_surprise.get("expected_eps", float("nan")),
            latest_surprise.get("prior_surprises_std", float("nan")),
        )

    if not any(np.isfinite(x) for x in (rev_30, rev_90, rev_180, sue)):
        return float("nan")

    def _bin(value: float, low: float, high: float) -> float:
        if not np.isfinite(value):
            return 50.0
        if value <= low:
            return 0.0
        if value >= high:
            return 100.0
        return 100.0 * (value - low) / (high - low)

    score = 0.0
    score += 0.20 * _bin(rev_30, -0.05, 0.05)
    score += 0.25 * _bin(rev_90, -0.10, 0.10)
    score += 0.25 * _bin(rev_180, -0.15, 0.15)
    score += 0.30 * _bin(sue, -2.0, 2.0)
    return float(round(score, 2))


# ---------------------------------------------------------------------------
# Bulk variant
# ---------------------------------------------------------------------------


def revisions_signals_df(
    estimates_map: Dict[str, pd.DataFrame],
    surprises_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> pd.DataFrame:
    """Compute the revisions signal block for a universe.

    Parameters
    ----------
    estimates_map:
        ``{ticker: analyst_estimates_df}``. Each DataFrame should be the FMP
        ``/v3/analyst-estimates`` response (rows = report dates, columns
        include ``estimatedEpsAvg``).
    surprises_map:
        ``{ticker: {reported_eps, expected_eps, prior_surprises_std}}``.
        Optional -- when missing for a ticker SUE is NaN.

    Returns
    -------
    DataFrame indexed by ticker with columns:
        EPS_Rev_30d, EPS_Rev_90d, EPS_Rev_180d, SUE, Revisions_Score
    """
    surprises_map = surprises_map or {}
    rows: List[Dict[str, Any]] = []
    for ticker, df in estimates_map.items():
        surprise = surprises_map.get(ticker)
        sue = float("nan")
        if surprise:
            sue = sue_z_score(
                surprise.get("reported_eps", float("nan")),
                surprise.get("expected_eps", float("nan")),
                surprise.get("prior_surprises_std", float("nan")),
            )
        rows.append({
            "Ticker": ticker,
            "EPS_Rev_30d": eps_revision_change(df, 30),
            "EPS_Rev_90d": eps_revision_change(df, 90),
            "EPS_Rev_180d": eps_revision_change(df, 180),
            "SUE": sue,
            "Revisions_Score": revisions_score(df, surprise),
        })
    if not rows:
        return pd.DataFrame(
            columns=["EPS_Rev_30d", "EPS_Rev_90d", "EPS_Rev_180d", "SUE", "Revisions_Score"]
        )
    return pd.DataFrame(rows).set_index("Ticker")
