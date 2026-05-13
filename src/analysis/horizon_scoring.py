"""
Invest Solo — Three-Horizon Composite Scoring (M7)

METHODOLOGY_v2 splits the legacy single ``Composite_Score`` into three
horizon-specific composites with distinct weight schemes plus a set of
binary "investability" gates per horizon. This module is pure orchestration:
it expects the M3/M5/M9 sub-score columns to already exist on the
DataFrame and produces, for each horizon X in {lt, mt, st}:

    score_X        : weighted composite, 0..100, NaN-aware
    signal_X       : Strong Buy / Buy / Hold / Sell / Strong Sell
                     (delegated to scoring_engine.generate_signal, with
                     DCF mid-MoS feeding the M6 two-criterion path)
    passes_gates_X : bool — every gate satisfied
    blockers_X     : list[str] — names of failing gates (empty when passes)

The horizon definitions live in ``settings.yaml`` under the ``horizons:``
key; this module reads them as plain dicts so it stays decoupled from the
backend AppConfig.

Sub-score column mapping (the canonical names emitted by ``score_dataframe``
after M3/M5/M9 wiring):

    valuation         -> Valuation_Score
    profitability     -> Profitability_Score
    health            -> Health_Score
    growth            -> Growth_Score
    capital_allocation-> Shareholder_Score   (legacy column kept; rename in M10)
    risk              -> Risk_Score_v2       (M5's real risk score, NOT legacy "Risk_Score")
    earnings_quality  -> EarningsQuality_Score (M5)
    momentum          -> Momentum_Score      (M9; NaN if no price_history_map)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.analysis.scoring_engine import generate_signal

__all__ = [
    "DEFAULT_SUB_SCORE_COLUMNS",
    "score_long_term",
    "score_medium_term",
    "score_short_term",
    "score_three_horizons",
]

# Canonical category -> column-name mapping. Used as the default when
# callers don't supply one explicitly.
DEFAULT_SUB_SCORE_COLUMNS: dict[str, str] = {
    "valuation": "Valuation_Score",
    "profitability": "Profitability_Score",
    "health": "Health_Score",
    "growth": "Growth_Score",
    "capital_allocation": "Shareholder_Score",
    "risk": "Risk_Score_v2",
    "earnings_quality": "EarningsQuality_Score",
    "momentum": "Momentum_Score",
}


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _is_finite(val: Any) -> bool:
    """True iff val is a finite numeric (rejects None, NaN, Inf, non-numeric)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


_COVERAGE_FLOOR = 0.5  # below this, composite gets damped toward neutral 50
_COVERAGE_DAMP_TO = 50.0  # the score a fully-missing row collapses toward


def _renormalised_weighted_mean(
    row: pd.Series,
    weights: dict[str, float],
    sub_score_columns: dict[str, str],
) -> float:
    """Coverage-aware weighted mean across scoring categories.

    Each category contributes (score * weight) only when its column exists
    AND the row's value is finite. Pure renormalisation over the present
    set inflated composites for sparse rows (1 strong category out of 6
    => composite ≈ that one category). We now dampen toward neutral when
    coverage drops below ``_COVERAGE_FLOOR``:

        weighted = sum(score * weight) / sum(weight)         # present-only mean
        coverage = sum(present weight) / sum(total weight)
        if coverage >= floor:
            composite = weighted                              # no penalty
        else:
            t = coverage / floor                              # 0..1
            composite = t * weighted + (1 - t) * 50           # blend to neutral

    Effect: a row with 80% coverage scores at the present-only mean; a row
    with 0% coverage collapses to NaN; in between, the composite is pulled
    toward 50, so a "Buy"-grade signal cannot ride a single sub-score.
    Returns NaN only when *every* category is missing.
    """
    present_score = 0.0
    present_weight = 0.0
    total_weight = 0.0
    for cat, w in weights.items():
        total_weight += float(w)
        col = sub_score_columns.get(cat)
        if col is None:
            continue
        val = row.get(col, np.nan)
        if not _is_finite(val):
            continue
        present_score += float(val) * float(w)
        present_weight += float(w)
    if present_weight <= 0 or total_weight <= 0:
        return float("nan")
    weighted = present_score / present_weight
    coverage = present_weight / total_weight
    if coverage >= _COVERAGE_FLOOR:
        return weighted
    t = coverage / _COVERAGE_FLOOR
    return t * weighted + (1.0 - t) * _COVERAGE_DAMP_TO


def _check_gates(
    row: pd.Series,
    gates: dict[str, Any],
    require_momentum: bool = False,
) -> list[str]:
    """Evaluate every gate; return the list of *failing* gate keys.

    The list is empty when all gates pass. Gates whose required input is
    NaN/missing are reported as failing with a "missing_<key>" suffix
    rather than silently passing — gating must be conservative.

    Recognised gate keys (any subset can appear):

        min_data_completeness   : data_completeness >= value
        max_distress            : Altman_Z >= value
        min_market_cap          : MarketCap >= value
        min_years_listed        : YearsListed >= value
        min_avg_volume          : AvgVolume >= value
        max_realized_vol_1y     : Realized_Vol_1y <= value (NaN -> missing)

    The ``pea_warning`` and ``recommended_account`` keys are not gates;
    they're carried through as metadata and ignored here.

    Parameters
    ----------
    require_momentum : bool
        When True (typically only the short-term horizon), a missing
        ``Momentum_Score`` adds ``"missing_momentum"`` to the blockers list.
        ST scores collapse to mostly-noise when momentum is absent, so we
        block rather than score it.
    """
    blockers: list[str] = []

    # data_completeness gate
    if "min_data_completeness" in gates:
        thr = float(gates["min_data_completeness"])
        val = row.get("data_completeness", np.nan)
        if not _is_finite(val):
            blockers.append("missing_data_completeness")
        elif float(val) < thr:
            blockers.append("min_data_completeness")

    # distress gate (Altman Z'' floor)
    if "max_distress" in gates:
        thr = float(gates["max_distress"])
        val = row.get("Altman_Z", np.nan)
        if not _is_finite(val):
            blockers.append("missing_altman_z")
        elif float(val) < thr:
            blockers.append("max_distress")

    # market cap gate
    if "min_market_cap" in gates:
        thr = float(gates["min_market_cap"])
        val = row.get("MarketCap", np.nan)
        if not _is_finite(val):
            blockers.append("missing_market_cap")
        elif float(val) < thr:
            blockers.append("min_market_cap")

    # listing-age gate
    if "min_years_listed" in gates:
        thr = float(gates["min_years_listed"])
        val = row.get("YearsListed", np.nan)
        if not _is_finite(val):
            blockers.append("missing_years_listed")
        elif float(val) < thr:
            blockers.append("min_years_listed")

    # liquidity gate
    if "min_avg_volume" in gates:
        thr = float(gates["min_avg_volume"])
        val = row.get("AvgVolume", np.nan)
        if not _is_finite(val):
            blockers.append("missing_avg_volume")
        elif float(val) < thr:
            blockers.append("min_avg_volume")

    # realised-vol ceiling
    if "max_realized_vol_1y" in gates:
        thr = float(gates["max_realized_vol_1y"])
        val = row.get("Realized_Vol_1y", np.nan)
        if not _is_finite(val):
            blockers.append("missing_realized_vol_1y")
        elif float(val) > thr:
            blockers.append("max_realized_vol_1y")

    # momentum sanity gate (ST horizon only)
    if require_momentum:
        val = row.get("Momentum_Score", np.nan)
        if not _is_finite(val):
            blockers.append("missing_momentum")

    return blockers


# Blockers whose presence means "we don't have enough data to score honestly".
# When any of these fire, force the signal to "Insufficient Data" regardless of
# composite — the composite is built on the few categories that happen to be
# present, so a high score is meaningless.
#
# NOT included on purpose:
#   missing_years_listed   – metadata only. yfinance often doesn't expose
#                            firstTradeDateEpochUtc for non-US tickers, but a
#                            missing listing date isn't a scoring-quality issue.
#                            Surfaces in blockers[] for transparency; caps signal
#                            at Hold via the catch-all below, never escalates to
#                            "Insufficient Data".
#   missing_avg_volume     – same: liquidity metric, not a scoring input.
_DATA_QUALITY_BLOCKERS = frozenset(
    {
        "min_data_completeness",
        "missing_data_completeness",
        "missing_altman_z",
        "missing_market_cap",
        "missing_realized_vol_1y",
        "missing_momentum",
    }
)


def _downgrade_signal_for_blockers(sig: str, blockers: list[str]) -> str:
    """Drop a Buy/Strong Buy signal when blockers indicate the call is unsafe.

    - Any data-quality blocker -> "Insufficient Data"
    - Any other blocker -> cap at "Hold" (don't promote, don't sell)
    - No blockers -> signal unchanged
    """
    if not blockers:
        return sig
    if any(b in _DATA_QUALITY_BLOCKERS for b in blockers):
        return "Insufficient Data"
    if sig in ("Strong Buy", "Buy"):
        return "Hold"
    return sig


# ──────────────────────────────────────────────────────────────────────────────
# Per-horizon scorers
# ──────────────────────────────────────────────────────────────────────────────


def _score_one_horizon(
    df: pd.DataFrame,
    weights: dict[str, float],
    gates: dict[str, Any],
    sub_score_columns: dict[str, str],
    horizon_suffix: str,
    require_momentum: bool = False,
) -> pd.DataFrame:
    """Internal: compute composite + signal + gates for ONE horizon.

    Returns a DataFrame with four columns (suffixed by ``horizon_suffix``)
    indexed identically to ``df``. Pure: never mutates ``df``.

    Composite is computed via :func:`_renormalised_weighted_mean` so
    missing sub-scores degrade gracefully. Signal delegates to
    :func:`scoring_engine.generate_signal`, feeding ``DCF_MoS_Mid`` as the
    margin-of-safety input when present (NaN-safe fallback when absent).
    """
    if df.empty:
        return pd.DataFrame(
            index=df.index,
            columns=[
                f"score_{horizon_suffix}",
                f"signal_{horizon_suffix}",
                f"passes_gates_{horizon_suffix}",
                f"blockers_{horizon_suffix}",
            ],
        )

    scores: list[float] = []
    signals: list[str] = []
    passes: list[bool] = []
    blockers_per_row: list[list[str]] = []

    has_dcf_mid = "DCF_MoS_Mid" in df.columns

    for _, row in df.iterrows():
        composite = _renormalised_weighted_mean(row, weights, sub_score_columns)
        # Signal needs a numeric composite — fall back to neutral 50 when
        # the row was so sparse every category dropped out. Snapshots that
        # used to score 50 for "all NaN sub-scores" stay equivalent.
        signal_input = composite if _is_finite(composite) else 50.0
        mos = float(row["DCF_MoS_Mid"]) if has_dcf_mid and _is_finite(row.get("DCF_MoS_Mid")) else float("nan")
        sig = generate_signal(signal_input, mos)

        bls = _check_gates(row, gates, require_momentum=require_momentum)
        # Gates that flag data-quality holes force "Insufficient Data";
        # other failed gates cap at "Hold". A clean row passes through.
        sig = _downgrade_signal_for_blockers(sig, bls)

        scores.append(round(composite, 1) if _is_finite(composite) else float("nan"))
        signals.append(sig)
        passes.append(len(bls) == 0)
        blockers_per_row.append(bls)

    out = pd.DataFrame(
        {
            f"score_{horizon_suffix}": scores,
            f"signal_{horizon_suffix}": signals,
            f"passes_gates_{horizon_suffix}": passes,
            f"blockers_{horizon_suffix}": blockers_per_row,
        },
        index=df.index,
    )
    return out


def score_long_term(
    df: pd.DataFrame,
    weights: dict[str, float],
    gates: dict[str, Any],
    sub_score_columns: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Long-term composite + signal + investability gates.

    Output columns (per row):
        score_lt, signal_lt, passes_gates_lt, blockers_lt

    Composite:
        Renormalised weighted mean across the categories present in
        ``weights``. Missing sub-scores drop out (their weight is removed).

    Signal:
        ``generate_signal(composite_lt, mos=DCF_MoS_Mid)`` — the M6
        two-criterion path activates when MoS is finite, otherwise the
        legacy composite-only thresholds apply.

    Gates (LT default set in settings.yaml):
        min_data_completeness, max_distress (Altman Z'' floor),
        min_market_cap, min_years_listed.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain the sub-score columns named in ``sub_score_columns``,
        plus ``data_completeness``, ``Altman_Z``, ``MarketCap``,
        ``YearsListed``, and (optionally) ``DCF_MoS_Mid``.
    weights, gates : dict
        Pulled from ``settings.horizons_long_term``.
    sub_score_columns : dict, optional
        Defaults to ``DEFAULT_SUB_SCORE_COLUMNS``.
    """
    sub = sub_score_columns or DEFAULT_SUB_SCORE_COLUMNS
    return _score_one_horizon(df, weights, gates, sub, horizon_suffix="lt", require_momentum=False)


def score_medium_term(
    df: pd.DataFrame,
    weights: dict[str, float],
    gates: dict[str, Any],
    sub_score_columns: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Medium-term composite + signal + gates.

    Output columns: score_mt, signal_mt, passes_gates_mt, blockers_mt.

    MT differs from LT primarily by adding momentum to the weight mix and
    relaxing the data-completeness threshold (0.60 vs 0.70). Same gate
    keys; ``min_years_listed`` is dropped by the default settings.
    """
    sub = sub_score_columns or DEFAULT_SUB_SCORE_COLUMNS
    return _score_one_horizon(df, weights, gates, sub, horizon_suffix="mt", require_momentum=False)


def score_short_term(
    df: pd.DataFrame,
    weights: dict[str, float],
    gates: dict[str, Any],
    sub_score_columns: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Short-term composite + signal + gates.

    Output columns: score_st, signal_st, passes_gates_st, blockers_st.

    ST is momentum-led (default 55% weight on Momentum_Score) so the gate
    set is stricter on liquidity (``min_avg_volume``) and volatility
    (``max_realized_vol_1y``) and relaxes Altman to allow trading
    distressed names (``max_distress: 1.5`` vs 1.1 for LT/MT).

    A missing ``Momentum_Score`` adds ``"missing_momentum"`` to blockers
    rather than letting an unmoored composite slip through.
    """
    sub = sub_score_columns or DEFAULT_SUB_SCORE_COLUMNS
    return _score_one_horizon(df, weights, gates, sub, horizon_suffix="st", require_momentum=True)


# ──────────────────────────────────────────────────────────────────────────────
# Convenience wrapper
# ──────────────────────────────────────────────────────────────────────────────


def score_three_horizons(
    df: pd.DataFrame,
    settings_block: dict[str, Any],
    sub_score_columns: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Compute LT/MT/ST horizon scores in one pass and join them onto ``df``.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame already enriched with M3/M5/M9 sub-scores plus the gate
        inputs (``data_completeness``, ``Altman_Z``, ``MarketCap``,
        ``YearsListed``, ``AvgVolume``, ``Realized_Vol_1y``, ``DCF_MoS_Mid``).
    settings_block : dict
        The ``horizons:`` block from settings.yaml. Expected to contain
        ``long_term``, ``medium_term``, and ``short_term`` sub-blocks with
        ``weights`` and ``gates`` keys. Each horizon is processed only when
        its sub-block is present — missing horizons are silently skipped.
    sub_score_columns : dict, optional
        Override the default sub-score column mapping.

    Returns
    -------
    pd.DataFrame
        ``df`` with the horizon columns appended; original column ordering
        is preserved. Adds ``recommended_account`` when the short-term
        sub-block declares it (typically ``"CTO"``); applied only on rows
        where ``passes_gates_st`` is True.
    """
    if df.empty or not settings_block:
        return df

    sub = sub_score_columns or DEFAULT_SUB_SCORE_COLUMNS
    out = df.copy()

    if "long_term" in settings_block:
        lt = settings_block["long_term"] or {}
        out = out.join(
            score_long_term(out, lt.get("weights", {}), lt.get("gates", {}), sub),
            how="left",
        )

    if "medium_term" in settings_block:
        mt = settings_block["medium_term"] or {}
        out = out.join(
            score_medium_term(out, mt.get("weights", {}), mt.get("gates", {}), sub),
            how="left",
        )

    if "short_term" in settings_block:
        st = settings_block["short_term"] or {}
        out = out.join(
            score_short_term(out, st.get("weights", {}), st.get("gates", {}), sub),
            how="left",
        )

        # Stamp recommended_account on rows that pass ST gates. Settings
        # block typically sets this to "CTO" because short-term momentum
        # trading triggers PEA's frequent-trading rules and forfeits the
        # tax wrapper — surfacing the recommendation in the output keeps
        # downstream consumers (frontend, screener) honest about it.
        rec = st.get("gates", {}).get("recommended_account")
        if rec is not None and "passes_gates_st" in out.columns:
            out["recommended_account"] = np.where(
                out["passes_gates_st"].fillna(False).astype(bool),
                str(rec),
                "",
            )

    return out
