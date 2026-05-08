"""
Invest Solo — Composite Scoring Engine
Implements the 0-100 scoring system from METHODOLOGY.md

The Piotroski / Altman / Graham primitives live in
``src/analysis/quality_signals.py`` (M4); this module re-exports them so
existing callers keep working unchanged.
"""
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional, Set, Tuple

from src.analysis.quality_signals import (
    altman_z_classic,        # re-exported for callers that want classic Z directly
    altman_z_double_prime,   # re-exported for callers that want Z'' directly
    altman_z_select,         # re-exported (returns score + variant tuple)
    altman_z_score as _altman_z_score_impl,
    graham_number as _graham_number_impl,
    piotroski_f_score as _piotroski_f_score_impl,
)

__all__ = [
    "SCORING_WEIGHTS",
    "SIGNAL_THRESHOLDS",
    "valuation_score",
    "financial_health_score",
    "profitability_score",
    "growth_score",
    "shareholder_return_score",
    "risk_score",
    "compute_composite_score",
    "generate_signal",
    "piotroski_f_score",
    "altman_z_score",
    "altman_z_classic",
    "altman_z_double_prime",
    "altman_z_select",
    "graham_number",
    "data_completeness",
    "score_universe",
]

# ══════════════════════════════════════════════════════════════
# SCORING THRESHOLDS (from settings.yaml)
# ══════════════════════════════════════════════════════════════

SCORING_WEIGHTS = {
    "valuation": 0.25,
    "financial_health": 0.20,
    "profitability": 0.20,
    "growth": 0.15,
    "shareholder_return": 0.10,
    "risk": 0.10,
}

SIGNAL_THRESHOLDS = {
    "strong_buy":  {"min_score": 80, "max_price_ratio": 0.70},
    "buy":         {"min_score": 65, "max_price_ratio": 0.85},
    "hold":        {"min_score": 40, "max_score": 65},
    "sell":        {"max_score": 40, "min_price_ratio": 1.30},
    "strong_sell": {"max_score": 25, "min_price_ratio": 1.50},
}


def _is_finite(val: Any) -> bool:
    """True iff val is a finite numeric (rejects None, NaN, Inf, non-numeric)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


# DEPRECATED: replaced by sector_relative_percentile in M3.
def _percentile_score(value: float, low_bad: float, high_good: float, inverse: bool = False) -> float:
    """Map a value to 0-100 score. If inverse=True, lower is better.

    Hardcoded linear mapping; kept verbatim through M2 to preserve the public
    schema, then replaced by `sector_relative_percentile` in M3.
    """
    if pd.isna(value) or np.isinf(value):
        return 50.0  # neutral for missing data
    if inverse:
        if value <= low_bad:
            return 100.0
        elif value >= high_good:
            return 0.0
        else:
            return 100.0 * (high_good - value) / (high_good - low_bad)
    else:
        if value >= high_good:
            return 100.0
        elif value <= low_bad:
            return 0.0
        else:
            return 100.0 * (value - low_bad) / (high_good - low_bad)


def valuation_score(row: pd.Series) -> float:
    """Score 0-100: how undervalued is this stock?"""
    scores = []
    # P/E: lower is cheaper (inverse), but negative P/E = unprofitable = bad
    pe = row.get("PE", np.nan)
    if pd.notna(pe) and pe > 0:
        scores.append(_percentile_score(pe, 5.0, 30.0, inverse=True))
    elif pd.notna(pe) and pe < 0:
        scores.append(10.0)  # Unprofitable penalty
    # P/B: lower is cheaper
    scores.append(_percentile_score(row.get("PB", np.nan), 0.3, 5.0, inverse=True))
    # P/S: lower is cheaper
    scores.append(_percentile_score(row.get("PS", np.nan), 0.2, 8.0, inverse=True))
    # P/FCF: lower is cheaper
    pfcf = row.get("PFCF", np.nan)
    if pd.notna(pfcf) and pfcf > 0:
        scores.append(_percentile_score(pfcf, 5.0, 35.0, inverse=True))
    # EV/EBITDA: lower is cheaper
    scores.append(_percentile_score(row.get("EV_EBITDA", np.nan), 3.0, 20.0, inverse=True))
    # EV/Sales: lower is cheaper
    scores.append(_percentile_score(row.get("EV_Sales", np.nan), 0.3, 8.0, inverse=True))
    return np.mean(scores) if scores else 50.0


def financial_health_score(row: pd.Series) -> float:
    """Score 0-100: how financially solid is this company?"""
    scores = []
    # Current ratio: higher is better (but >3 is excess)
    cr = row.get("CurrentRatio", np.nan)
    if pd.notna(cr) and cr > 0:
        scores.append(_percentile_score(cr, 0.5, 2.5))
    # Debt/Equity: lower is better
    de = row.get("DebtEquity", np.nan)
    if pd.notna(de) and de >= 0:
        scores.append(_percentile_score(de, 0.0, 3.0, inverse=True))
    # Interest Coverage: higher is better
    ic = row.get("InterestCoverage", np.nan)
    if pd.notna(ic) and ic > 0:
        scores.append(_percentile_score(ic, 1.5, 15.0))
    # Net Debt / EBITDA: lower is better
    ebitda = row.get("EBITDA", 0)
    debt = row.get("TotalDebt", 0)
    cash = row.get("Cash", 0)
    if ebitda and ebitda > 0:
        nd_ebitda = (debt - cash) / ebitda
        scores.append(_percentile_score(nd_ebitda, -1.0, 5.0, inverse=True))
    return np.mean(scores) if scores else 50.0


def profitability_score(row: pd.Series) -> float:
    """Score 0-100: how profitable is this company?"""
    scores = []
    # ROE
    roe = row.get("ROE", np.nan)
    if pd.notna(roe):
        scores.append(_percentile_score(roe, 0.0, 0.25))
    # ROA
    scores.append(_percentile_score(row.get("ROA", np.nan), 0.0, 0.12))
    # ROIC
    roic = row.get("ROIC", np.nan)
    if pd.notna(roic):
        scores.append(_percentile_score(roic, 0.0, 0.20))
    # Operating Margin
    scores.append(_percentile_score(row.get("OperatingMargin", np.nan), 0.0, 0.25))
    # Net Margin
    scores.append(_percentile_score(row.get("NetMargin", np.nan), 0.0, 0.20))
    # FCF Margin
    scores.append(_percentile_score(row.get("FCFMargin", np.nan), 0.0, 0.15))
    return np.mean(scores) if scores else 50.0


def growth_score(row: pd.Series) -> float:
    """Score 0-100: how fast is this company growing?"""
    scores = []
    rg = row.get("RevenueGrowth", np.nan)
    if pd.notna(rg):
        scores.append(_percentile_score(rg, -0.10, 0.25))
    return np.mean(scores) if scores else 50.0


def shareholder_return_score(row: pd.Series) -> float:
    """Score 0-100: how well does this company reward shareholders?"""
    scores = []
    # Dividend yield
    dy = row.get("DivYield", np.nan)
    if pd.notna(dy):
        scores.append(_percentile_score(dy, 0.0, 0.06))
    # Payout ratio: moderate is best (30-60% ideal)
    pr = row.get("PayoutRatio", np.nan)
    if pd.notna(pr):
        if 0.30 <= pr <= 0.60:
            scores.append(90.0)
        elif pr < 0.30:
            scores.append(50.0 + pr / 0.30 * 40)
        elif pr <= 1.0:
            scores.append(max(20, 90 - (pr - 0.60) / 0.40 * 70))
        else:
            scores.append(10.0)  # >100% payout = unsustainable
    return np.mean(scores) if scores else 50.0


def risk_score(row: pd.Series) -> float:
    """Score 0-100: how safe is this stock? (higher = safer)"""
    scores = []
    # Beta: closer to 1 is moderate, low beta = safer
    beta = row.get("Beta", np.nan)
    if pd.notna(beta):
        scores.append(_percentile_score(beta, 0.3, 2.0, inverse=True))
    # Interest coverage (overlap with health but risk-specific)
    ic = row.get("InterestCoverage", np.nan)
    if pd.notna(ic) and ic > 0:
        scores.append(_percentile_score(ic, 2.0, 12.0))
    return np.mean(scores) if scores else 50.0


def compute_composite_score(row: pd.Series) -> Dict[str, float]:
    """Calculate full composite score with category breakdown."""
    categories = {
        "valuation": valuation_score(row),
        "financial_health": financial_health_score(row),
        "profitability": profitability_score(row),
        "growth": growth_score(row),
        "shareholder_return": shareholder_return_score(row),
        "risk": risk_score(row),
    }
    composite = sum(categories[k] * SCORING_WEIGHTS[k] for k in categories)
    categories["composite"] = round(composite, 1)
    return categories


def generate_signal(composite_score: float) -> str:
    """Convert composite score to investment signal."""
    if composite_score >= 80:
        return "Strong Buy"
    elif composite_score >= 65:
        return "Buy"
    elif composite_score >= 40:
        return "Hold"
    elif composite_score >= 25:
        return "Sell"
    else:
        return "Strong Sell"


def piotroski_f_score(row: pd.Series) -> int:
    """Compute the Piotroski F-Score (0-9) using YoY deltas (M4 implementation).

    Delegates to :func:`src.analysis.quality_signals.piotroski_f_score`, which
    treats each of the 9 signals individually and skips any whose
    current-year or prior-year inputs are NaN.  The aggregate is therefore
    the SUM of present-and-satisfied signals (0..9).
    """
    return _piotroski_f_score_impl(row)


def altman_z_score(row: pd.Series) -> float:
    """Compute Altman Z (manufacturers) or Z'' (everything else).

    Sector-aware dispatch lives in
    :func:`src.analysis.quality_signals.altman_z_select`.  This wrapper
    returns only the numeric score so existing callers (``score_universe``,
    capture_golden_snapshots) keep their float-only return contract.  M10
    will surface the variant via the public API.

    Zones (manufacturers, classic Z): Safe > 2.99 / Grey 1.81-2.99 / Distress < 1.81
    Zones (non-manufacturers, Z''):    Safe > 2.6  / Grey 1.1-2.6   / Distress < 1.1

    Returns NaN if required inputs are missing -- never fabricates.
    """
    return _altman_z_score_impl(row)


def graham_number(row: pd.Series) -> float:
    """Calculate Graham Number intrinsic value (sqrt(22.5 * EPS * BVPS))."""
    return _graham_number_impl(row)


# ──────────────────────────────────────────────────────────────────────────────
# Data completeness (M1 addition, internal-only field)
# ──────────────────────────────────────────────────────────────────────────────
# Union of every input field touched by sub-score builders + Piotroski + Altman
# + Graham. ~25 entries. Used to compute `data_completeness ∈ [0, 1]` per row,
# which is exposed in `score_universe` output for the audit trail. Not added to
# the public API schema yet -- M10 promotes it.
_SCORING_INPUT_FIELDS: Tuple[str, ...] = (
    # Valuation
    "PE", "PB", "PS", "PFCF", "EV_EBITDA", "EV_Sales",
    # Health
    "CurrentRatio", "DebtEquity", "InterestCoverage",
    "EBITDA", "TotalDebt", "Cash",
    # Profitability
    "ROE", "ROA", "ROIC",
    "OperatingMargin", "NetMargin", "FCFMargin",
    # Growth
    "RevenueGrowth",
    # Shareholder
    "DivYield", "PayoutRatio",
    # Risk
    "Beta",
    # Piotroski / Altman / Graham (extra fields not already listed)
    "OperatingCashflow", "NetIncome", "GrossMargin",
    "TotalAssets", "TotalEquity", "Revenue",
    "Shares", "Shares_PriorYear",
    "EBIT", "MarketCap",
    "CurrentAssets", "CurrentLiabilities", "RetainedEarnings",
    # M4 -- YoY inputs for Piotroski 2000 deltas
    "ROA_PriorYear", "OperatingCashflow_PriorYear",
    "LongTermDebt", "LongTermDebt_PriorYear",
    "CurrentRatio_PriorYear", "GrossMargin_PriorYear",
    "Revenue_PriorYear", "TotalAssets_PriorYear",
)


def data_completeness(row: pd.Series) -> float:
    """Fraction of scoring input fields that are present (finite) in this row.

    Returns a float in [0, 1] rounded to 2 decimals. A value of 1.0 means every
    field the scoring engine examines is populated; 0.0 means none of them are.
    """
    if len(_SCORING_INPUT_FIELDS) == 0:
        return 0.0
    present = sum(1 for f in _SCORING_INPUT_FIELDS if _is_finite(row.get(f, np.nan)))
    return round(present / len(_SCORING_INPUT_FIELDS), 2)


def score_universe(df: pd.DataFrame) -> pd.DataFrame:
    """Score entire universe and add all analytical columns."""
    results = []
    for ticker, row in df.iterrows():
        scores = compute_composite_score(row)
        az = altman_z_score(row)
        gn = graham_number(row)
        results.append({
            "Ticker": ticker,
            "Composite_Score": scores["composite"],
            "Valuation_Score": round(scores["valuation"], 1),
            "Health_Score": round(scores["financial_health"], 1),
            "Profitability_Score": round(scores["profitability"], 1),
            "Growth_Score": round(scores["growth"], 1),
            "Shareholder_Score": round(scores["shareholder_return"], 1),
            "Risk_Score": round(scores["risk"], 1),
            "Signal": generate_signal(scores["composite"]),
            "Piotroski_F": piotroski_f_score(row),
            "Altman_Z": round(az, 2) if pd.notna(az) else np.nan,
            "Graham_Number": round(gn, 2) if pd.notna(gn) else np.nan,
            # M1 audit-trail field; not in public API schema yet (see M10).
            "data_completeness": data_completeness(row),
        })
    scores_df = pd.DataFrame(results).set_index("Ticker")
    # Merge back with original
    merged = df.join(scores_df)
    # Graham margin of safety
    merged["Graham_MoS"] = np.where(
        merged["Graham_Number"].notna() & (merged["Price"] > 0),
        (merged["Graham_Number"] / merged["Price"] - 1) * 100,
        np.nan
    )
    merged["Graham_MoS"] = merged["Graham_MoS"].round(1)
    return merged.sort_values("Composite_Score", ascending=False)
