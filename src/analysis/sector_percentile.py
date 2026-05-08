"""Sector-relative percentile scoring (M3).

Pure-function module. No I/O, no yfinance, no FMP. Inputs are pandas
DataFrames already populated by the data layer. Replaces the legacy
``_percentile_score`` linear map in ``scoring_engine.py`` with a true
percentile rank computed against sector peers (or the global universe
when a sector has too few peers to be statistically meaningful).

Why this matters
----------------
The legacy linear map used hardcoded breakpoints (e.g. ``low_bad=5,
high_good=30`` for P/E). A SaaS company at P/E 35 was clamped to 0,
even though P/E 35 is BELOW the software-sector median. A utility at
P/E 14 scored ~80, even though P/E 14 is RICHER than the utility-sector
median. Both are wrong relative to peers. This module fixes that by
ranking each metric within its sector group.

Public API
----------
``score_sector_relative(df, metric, inverse=False, min_n=5)`` -> Series
    Rank each row of ``df`` against same-sector peers on ``metric``.
    Falls back to global rank when a sector has fewer than ``min_n``
    peers. ``inverse=True`` flips the rank so lower raw values produce
    higher scores (e.g. P/E, P/B where lower-is-better).
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


__all__ = ["score_sector_relative"]


def _percentile_rank(s: pd.Series, inverse: bool) -> pd.Series:
    """Convert a Series of numeric values to 0-100 percentile ranks.

    Uses ``method="average"`` so ties receive equal rank, ``pct=True``
    so the result is in (0, 1], multiplied by 100. NaN inputs preserve
    NaN in the output (no imputation).
    """
    if s.dropna().empty:
        # Pandas .rank on all-NaN returns all-NaN already, but be explicit.
        return pd.Series(np.nan, index=s.index, dtype="float64")
    ranked = s.rank(method="average", pct=True, na_option="keep") * 100.0
    if inverse:
        # Lower raw value -> higher score. Flip around 100.
        ranked = 100.0 - ranked
        # Preserve NaN: subtraction propagates NaN, but be explicit so
        # callers can rely on it without surprise from future pandas.
        ranked = ranked.where(s.notna(), np.nan)
    return ranked


def score_sector_relative(
    df: pd.DataFrame,
    metric: str,
    inverse: bool = False,
    sector_col: str = "Sector",
    fallback_universe: Literal["global"] = "global",
    min_n: int = 5,
) -> pd.Series:
    """Score each row 0-100 by sector-relative percentile rank of ``metric``.

    For each sector with ``>= min_n`` non-NaN peers in the input
    DataFrame, rank within the sector. For smaller sectors (or rows
    with a missing sector label), fall back to ranking against the
    global universe (every non-NaN row in ``df``). Higher rank = higher
    score, except when ``inverse=True`` (e.g. P/E where lower is better).

    NaN values in ``metric`` produce NaN in the output. We do NOT
    impute and do NOT fabricate scores.

    Parameters
    ----------
    df : pd.DataFrame
        Universe to rank. Index is preserved.
    metric : str
        Column name to rank.
    inverse : bool, default False
        If True, lower raw values produce higher scores (cheaper-is-
        better metrics like P/E, EV/EBITDA, DebtEquity).
    sector_col : str, default "Sector"
        Column name carrying the sector label.
    fallback_universe : {"global"}, default "global"
        Where to rank rows whose sector has < ``min_n`` peers. Only
        "global" supported in M3; reserved for future "regional"
        fallbacks.
    min_n : int, default 5
        Minimum peers (non-NaN ``metric`` values) per sector to keep the
        sector grouping. Below this threshold the sector falls through
        to the global universe.

    Returns
    -------
    pd.Series
        Float series in [0, 100] (or NaN), indexed identically to ``df``.
    """
    if metric not in df.columns:
        # Caller asked for a metric we don't have. Return NaN series.
        return pd.Series(np.nan, index=df.index, dtype="float64")
    if fallback_universe != "global":
        raise ValueError(
            f"fallback_universe={fallback_universe!r} not supported; only 'global' in M3"
        )

    metric_series = pd.to_numeric(df[metric], errors="coerce")
    sectors = df.get(sector_col)

    # Step 1: compute the global rank (used for fallback rows).
    global_score = _percentile_rank(metric_series, inverse=inverse)

    # Step 2: if no sector column, every row is a global-rank fallback.
    if sectors is None:
        return global_score

    # Step 3: identify which sectors have enough peers.
    sectors_clean = sectors.fillna("").astype(str)
    # Count non-NaN metric values per sector (only rows that contribute).
    counts = (
        metric_series.notna()
        .groupby(sectors_clean)
        .sum()
    )
    big_enough = set(counts[counts >= min_n].index)
    # Empty sector ("") never qualifies — no peers to compare to.
    big_enough.discard("")

    out = global_score.copy()

    # Step 4: for each qualifying sector, overwrite global with within-sector rank.
    for sector in big_enough:
        mask = sectors_clean == sector
        sector_metric = metric_series[mask]
        sector_rank = _percentile_rank(sector_metric, inverse=inverse)
        # Reindex back into the full Series at the masked positions.
        out.loc[mask] = sector_rank

    return out
