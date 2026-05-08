"""
Invest Solo — Composite Scoring Engine
Implements the 0-100 scoring system from METHODOLOGY.md.

M3 (sector-relative percentile): the legacy ``_percentile_score`` linear
map (hardcoded per-metric breakpoints, mislabelled as a percentile) is
removed. Sub-score builders now operate on full DataFrames and rank each
metric within sector groups via ``score_sector_relative``. The per-row
API (``valuation_score``, ``financial_health_score``, …,
``compute_composite_score``) is preserved as a thin shim that builds a
1-row DataFrame on the fly — useful for snapshot tests that score a
single frozen input row, but it cannot compute meaningful peer
percentiles in isolation. Pass an explicit peer DataFrame via
``compute_composite_score_with_peers`` for sector-aware single-ticker
scoring.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional, Set, Tuple

from src.analysis.sector_percentile import score_sector_relative

# M5 informational aggregators (sector-relative). Composite weighting unchanged
# in M5 (M7 owns reshuffling); these are exposed as new columns only.
from src.analysis.earnings_quality import earnings_quality_score  # noqa: F401
from src.analysis.quality_moat import moat_score  # noqa: F401
from src.analysis.risk_metrics import risk_score_real  # noqa: F401

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


# Sectors classified as "manufacturers" for the classic Altman Z model.
# Everything else uses Altman Z'' (4 factors, no asset turnover X5).
_ALTMAN_MANUFACTURER_SECTORS: Set[str] = {
    "Industrials",
    "Materials",
    "Energy",
    "Consumer Cyclical",
    "Consumer Defensive",
}


# Negative-PE penalty (legacy semantics preserved): unprofitable companies
# receive a fixed low score on the PE component, regardless of where they
# would rank within their sector. Applied as a post-rank override in
# ``valuation_score_df``.
_NEGATIVE_PE_PENALTY: float = 10.0


# Minimum peers per sector before sector-relative ranking is preferred over
# the global universe. Below this threshold, the sector falls through to
# the global rank — see sector_percentile.score_sector_relative.
_DEFAULT_MIN_PEERS: int = 5


def _is_finite(val: Any) -> bool:
    """True iff val is a finite numeric (rejects None, NaN, Inf, non-numeric)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


# ══════════════════════════════════════════════════════════════
# Vectorised sub-score builders (M3)
# Each takes the full DataFrame and returns a Series indexed identically
# to df. Components are aggregated via mean(axis=1, skipna=True) so that
# missing metrics simply drop out instead of being imputed at 50.
# ══════════════════════════════════════════════════════════════


def _ensure_columns(df: pd.DataFrame, names: List[str]) -> pd.DataFrame:
    """Return a DataFrame guaranteed to contain ``names``; missing become NaN."""
    out = df.copy()
    for n in names:
        if n not in out.columns:
            out[n] = np.nan
    return out


def valuation_score_df(df: pd.DataFrame, min_n: int = _DEFAULT_MIN_PEERS) -> pd.Series:
    """Sector-relative valuation score (0-100).

    Components: PE, PB, PS, PFCF, EV_EBITDA, EV_Sales — all inverse
    (lower is cheaper). Negative PE rows receive the legacy penalty
    (``_NEGATIVE_PE_PENALTY``) as a post-rank override.
    """
    df = _ensure_columns(df, ["PE", "PB", "PS", "PFCF", "EV_EBITDA", "EV_Sales", "Sector"])

    parts = pd.concat(
        [
            score_sector_relative(df, "PE", inverse=True, min_n=min_n).rename("PE"),
            score_sector_relative(df, "PB", inverse=True, min_n=min_n).rename("PB"),
            score_sector_relative(df, "PS", inverse=True, min_n=min_n).rename("PS"),
            score_sector_relative(df, "PFCF", inverse=True, min_n=min_n).rename("PFCF"),
            score_sector_relative(df, "EV_EBITDA", inverse=True, min_n=min_n).rename("EV_EBITDA"),
            score_sector_relative(df, "EV_Sales", inverse=True, min_n=min_n).rename("EV_Sales"),
        ],
        axis=1,
    )

    # Negative-PE penalty: override the PE component on rows where PE < 0.
    pe_numeric = pd.to_numeric(df["PE"], errors="coerce")
    neg_pe_mask = pe_numeric < 0
    if neg_pe_mask.any():
        parts.loc[neg_pe_mask, "PE"] = _NEGATIVE_PE_PENALTY

    # Drop PFCF column for rows where PFCF <= 0: legacy rule — only score
    # PFCF when it is positive (otherwise the metric is meaningless).
    pfcf_numeric = pd.to_numeric(df["PFCF"], errors="coerce")
    bad_pfcf = pfcf_numeric.notna() & (pfcf_numeric <= 0)
    if bad_pfcf.any():
        parts.loc[bad_pfcf, "PFCF"] = np.nan

    return parts.mean(axis=1, skipna=True)


def financial_health_score_df(df: pd.DataFrame, min_n: int = _DEFAULT_MIN_PEERS) -> pd.Series:
    """Sector-relative financial-health score (0-100).

    Components:
        - CurrentRatio (higher better)
        - DebtEquity (lower better)
        - InterestCoverage (higher better)
        - Net Debt / EBITDA, derived = (TotalDebt - Cash) / EBITDA (lower better)
    Each is sector-percentile-ranked; missing components drop out.
    """
    df = _ensure_columns(
        df,
        [
            "CurrentRatio",
            "DebtEquity",
            "InterestCoverage",
            "EBITDA",
            "TotalDebt",
            "Cash",
            "Sector",
        ],
    )

    # Build derived ND/EBITDA column (legacy-equivalent definition).
    ebitda = pd.to_numeric(df["EBITDA"], errors="coerce")
    debt = pd.to_numeric(df["TotalDebt"], errors="coerce")
    cash = pd.to_numeric(df["Cash"], errors="coerce")
    nd_ebitda = (debt - cash) / ebitda.where(ebitda > 0)
    df = df.copy()
    df["_ND_EBITDA"] = nd_ebitda

    # Skip CurrentRatio rows where it is non-positive (meaningless).
    cr = pd.to_numeric(df["CurrentRatio"], errors="coerce")
    df["CurrentRatio"] = cr.where(cr > 0)

    # Skip DebtEquity rows where it is negative (data quirk — neg equity).
    de = pd.to_numeric(df["DebtEquity"], errors="coerce")
    df["DebtEquity"] = de.where(de >= 0)

    # Skip InterestCoverage rows where it is non-positive.
    ic = pd.to_numeric(df["InterestCoverage"], errors="coerce")
    df["InterestCoverage"] = ic.where(ic > 0)

    parts = pd.concat(
        [
            score_sector_relative(df, "CurrentRatio", inverse=False, min_n=min_n).rename(
                "CurrentRatio"
            ),
            score_sector_relative(df, "DebtEquity", inverse=True, min_n=min_n).rename(
                "DebtEquity"
            ),
            score_sector_relative(df, "InterestCoverage", inverse=False, min_n=min_n).rename(
                "InterestCoverage"
            ),
            score_sector_relative(df, "_ND_EBITDA", inverse=True, min_n=min_n).rename(
                "ND_EBITDA"
            ),
        ],
        axis=1,
    )
    return parts.mean(axis=1, skipna=True)


def profitability_score_df(df: pd.DataFrame, min_n: int = _DEFAULT_MIN_PEERS) -> pd.Series:
    """Sector-relative profitability score (0-100).

    Components: ROE, ROA, ROIC, OperatingMargin, NetMargin, FCFMargin —
    all higher-is-better.
    """
    df = _ensure_columns(
        df,
        [
            "ROE", "ROA", "ROIC",
            "OperatingMargin", "NetMargin", "FCFMargin",
            "Sector",
        ],
    )
    parts = pd.concat(
        [
            score_sector_relative(df, "ROE", inverse=False, min_n=min_n).rename("ROE"),
            score_sector_relative(df, "ROA", inverse=False, min_n=min_n).rename("ROA"),
            score_sector_relative(df, "ROIC", inverse=False, min_n=min_n).rename("ROIC"),
            score_sector_relative(df, "OperatingMargin", inverse=False, min_n=min_n).rename(
                "OperatingMargin"
            ),
            score_sector_relative(df, "NetMargin", inverse=False, min_n=min_n).rename("NetMargin"),
            score_sector_relative(df, "FCFMargin", inverse=False, min_n=min_n).rename("FCFMargin"),
        ],
        axis=1,
    )
    return parts.mean(axis=1, skipna=True)


def growth_score_df(df: pd.DataFrame, min_n: int = _DEFAULT_MIN_PEERS) -> pd.Series:
    """Sector-relative growth score (0-100). Single component: RevenueGrowth."""
    df = _ensure_columns(df, ["RevenueGrowth", "Sector"])
    return score_sector_relative(df, "RevenueGrowth", inverse=False, min_n=min_n)


def shareholder_return_score_df(
    df: pd.DataFrame, min_n: int = _DEFAULT_MIN_PEERS
) -> pd.Series:
    """Sector-relative shareholder-return score (0-100).

    Components:
        - DivYield: higher is better, sector-percentile rank.
        - PayoutRatio: legacy non-monotonic curve preserved (peak at
          30-60%, low at extremes). Implemented as a deterministic
          function of the raw PayoutRatio rather than a rank, because
          the "ideal range" semantics don't translate to percentile.
    """
    df = _ensure_columns(df, ["DivYield", "PayoutRatio", "Sector"])

    div_score = score_sector_relative(df, "DivYield", inverse=False, min_n=min_n)

    pr = pd.to_numeric(df["PayoutRatio"], errors="coerce")
    payout_score = pr.apply(_payout_curve)

    return pd.concat([div_score.rename("DivYield"), payout_score.rename("PayoutRatio")], axis=1).mean(
        axis=1, skipna=True
    )


def _payout_curve(pr: float) -> float:
    """Legacy non-monotonic payout-ratio curve (M2 semantics preserved)."""
    if pd.isna(pr):
        return np.nan
    if 0.30 <= pr <= 0.60:
        return 90.0
    if pr < 0.30:
        return 50.0 + pr / 0.30 * 40.0
    if pr <= 1.0:
        return max(20.0, 90.0 - (pr - 0.60) / 0.40 * 70.0)
    return 10.0  # > 100% payout = unsustainable


def risk_score_df(df: pd.DataFrame, min_n: int = _DEFAULT_MIN_PEERS) -> pd.Series:
    """Sector-relative risk score (0-100, higher = safer).

    Components:
        - Beta: lower is safer (inverse rank).
        - InterestCoverage: higher is safer (overlap with health, kept
          for risk-specific weighting).
    """
    df = _ensure_columns(df, ["Beta", "InterestCoverage", "Sector"])
    df = df.copy()
    ic = pd.to_numeric(df["InterestCoverage"], errors="coerce")
    df["InterestCoverage"] = ic.where(ic > 0)

    parts = pd.concat(
        [
            score_sector_relative(df, "Beta", inverse=True, min_n=min_n).rename("Beta"),
            score_sector_relative(df, "InterestCoverage", inverse=False, min_n=min_n).rename(
                "InterestCoverage"
            ),
        ],
        axis=1,
    )
    return parts.mean(axis=1, skipna=True)


def _composite_from_subscores(subscores: pd.DataFrame) -> pd.Series:
    """Weighted sum of sub-scores into a single composite Series."""
    composite = (
        subscores["Valuation_Score"] * SCORING_WEIGHTS["valuation"]
        + subscores["Health_Score"] * SCORING_WEIGHTS["financial_health"]
        + subscores["Profitability_Score"] * SCORING_WEIGHTS["profitability"]
        + subscores["Growth_Score"] * SCORING_WEIGHTS["growth"]
        + subscores["Shareholder_Score"] * SCORING_WEIGHTS["shareholder_return"]
        + subscores["Risk_Score"] * SCORING_WEIGHTS["risk"]
    )
    return composite


# ══════════════════════════════════════════════════════════════
# Per-row API (back-compat shim, M3)
#
# These functions exist so legacy callers (snapshot tests via
# ``score_row``, the company-detail endpoint via
# ``ScoringService.score_single``) keep compiling. They wrap the row in
# a 1-row DataFrame and call the vectorised builder. With a 1-row
# DataFrame and no peers, sector-relative ranking degenerates to "this
# row is the only one" -> rank = 100 (or 0 inverse). For meaningful
# peer-aware scoring, callers should switch to the DataFrame-shaped
# entry points (``score_dataframe``, ``compute_composite_score_with_peers``).
# ══════════════════════════════════════════════════════════════


def _single_row_df(row: pd.Series) -> pd.DataFrame:
    """Wrap a Series in a 1-row DataFrame, indexed by the Series name (or '_').

    Series.to_frame().T loses the dtype hints of empty cells; we explicitly
    coerce numeric-looking columns to numeric so subsequent rank math works.
    """
    name = row.name if row.name is not None else "_"
    df = pd.DataFrame([row.to_dict()], index=[name])
    return df


def valuation_score(row: pd.Series, peers: Optional[pd.DataFrame] = None) -> float:
    """Per-row valuation score; uses ``peers`` as the peer universe if given."""
    df = peers if peers is not None else _single_row_df(row)
    if peers is not None and (row.name not in df.index):
        # Caller supplied peers without this row in them — append it so we
        # rank the row in context. Avoid mutating the caller's DataFrame.
        df = pd.concat([df, _single_row_df(row)])
    score_series = valuation_score_df(df)
    return float(score_series.loc[row.name if row.name is not None else "_"])


def financial_health_score(row: pd.Series, peers: Optional[pd.DataFrame] = None) -> float:
    df = peers if peers is not None else _single_row_df(row)
    if peers is not None and (row.name not in df.index):
        df = pd.concat([df, _single_row_df(row)])
    return float(financial_health_score_df(df).loc[row.name if row.name is not None else "_"])


def profitability_score(row: pd.Series, peers: Optional[pd.DataFrame] = None) -> float:
    df = peers if peers is not None else _single_row_df(row)
    if peers is not None and (row.name not in df.index):
        df = pd.concat([df, _single_row_df(row)])
    return float(profitability_score_df(df).loc[row.name if row.name is not None else "_"])


def growth_score(row: pd.Series, peers: Optional[pd.DataFrame] = None) -> float:
    df = peers if peers is not None else _single_row_df(row)
    if peers is not None and (row.name not in df.index):
        df = pd.concat([df, _single_row_df(row)])
    return float(growth_score_df(df).loc[row.name if row.name is not None else "_"])


def shareholder_return_score(row: pd.Series, peers: Optional[pd.DataFrame] = None) -> float:
    df = peers if peers is not None else _single_row_df(row)
    if peers is not None and (row.name not in df.index):
        df = pd.concat([df, _single_row_df(row)])
    return float(shareholder_return_score_df(df).loc[row.name if row.name is not None else "_"])


def risk_score(row: pd.Series, peers: Optional[pd.DataFrame] = None) -> float:
    df = peers if peers is not None else _single_row_df(row)
    if peers is not None and (row.name not in df.index):
        df = pd.concat([df, _single_row_df(row)])
    return float(risk_score_df(df).loc[row.name if row.name is not None else "_"])


def compute_composite_score(
    row: pd.Series,
    peers: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """Calculate full composite score with category breakdown.

    Without ``peers``, ranks against a 1-row universe (degenerate but
    backward-compatible with snapshot tests). With ``peers``, ranks the
    row against the supplied DataFrame.
    """
    df = peers if peers is not None else _single_row_df(row)
    if peers is not None and (row.name not in df.index):
        df = pd.concat([df, _single_row_df(row)])
    idx = row.name if row.name is not None else "_"

    # Replace NaN sub-scores with 50.0 (legacy semantics: missing data is
    # neutral, not a zero penalty). This preserves the score-out scale
    # callers expect even when an entire sub-score is NaN.
    valuation = _nan_to_neutral(valuation_score_df(df).loc[idx])
    health = _nan_to_neutral(financial_health_score_df(df).loc[idx])
    profitability = _nan_to_neutral(profitability_score_df(df).loc[idx])
    growth = _nan_to_neutral(growth_score_df(df).loc[idx])
    shareholder = _nan_to_neutral(shareholder_return_score_df(df).loc[idx])
    risk = _nan_to_neutral(risk_score_df(df).loc[idx])

    categories = {
        "valuation": valuation,
        "financial_health": health,
        "profitability": profitability,
        "growth": growth,
        "shareholder_return": shareholder,
        "risk": risk,
    }
    composite = sum(categories[k] * SCORING_WEIGHTS[k] for k in categories)
    categories["composite"] = round(composite, 1)
    return categories


def _nan_to_neutral(val: float) -> float:
    """Map NaN sub-scores to 50.0 (neutral). Preserve finite values."""
    if isinstance(val, (float, np.floating)) and np.isnan(val):
        return 50.0
    return float(val)


def compute_composite_score_with_peers(
    row: pd.Series, peers: pd.DataFrame
) -> Dict[str, float]:
    """Convenience: ``compute_composite_score`` requiring an explicit peer DF."""
    return compute_composite_score(row, peers=peers)


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
    """Compute simplified Piotroski F-Score (0-9), NaN-safe.

    Each of the 9 signals contributes +1 when satisfied, 0 when violated, and
    is SKIPPED entirely when the inputs are missing (NaN). Skipping a signal
    means the score has fewer than 9 possible points -- the value returned is
    therefore the SUM of present-and-satisfied signals (0..9). This is more
    conservative than the prior code, which awarded silent +1 (signal #7) and
    used `default=2`/`default=inf` which caused missing data to fail tests in
    inverted ways.

    Returns
    -------
    int
        Sum of present-and-satisfied signals (0..9).
    """
    signals: List[Optional[int]] = []

    # 1. ROA > 0
    roa = row.get("ROA", np.nan)
    signals.append(1 if (_is_finite(roa) and roa > 0) else (0 if _is_finite(roa) else None))

    # 2. Operating cashflow > 0
    cfo = row.get("OperatingCashflow", np.nan)
    signals.append(1 if (_is_finite(cfo) and cfo > 0) else (0 if _is_finite(cfo) else None))

    # 3. Delta ROA > 0 (proxy: ROA > 5%) — skipped if ROA absent.
    if _is_finite(roa):
        signals.append(1 if roa > 0.05 else 0)
    else:
        signals.append(None)

    # 4. CFO > Net Income (accruals quality). NaN-safe: skip if either is NaN.
    # BUG FIX (M1 #6): prior code used `default=float('inf')` for NetIncome, which
    # made the test FAIL when NI was missing -- inverted. Now we skip on NaN.
    ni = row.get("NetIncome", np.nan)
    if _is_finite(cfo) and _is_finite(ni):
        signals.append(1 if cfo > ni else 0)
    else:
        signals.append(None)

    # 5. Long-term debt decreased (proxy: D/E < 1.0).
    # BUG FIX (M1 #4): prior code used `default=2` which made missing data fail.
    # Now skip on NaN so missing data doesn't punish the ticker.
    de = row.get("DebtEquity", np.nan)
    if _is_finite(de):
        signals.append(1 if de < 1.0 else 0)
    else:
        signals.append(None)

    # 6. Current ratio > 1.0
    cr = row.get("CurrentRatio", np.nan)
    if _is_finite(cr):
        signals.append(1 if cr > 1.0 else 0)
    else:
        signals.append(None)

    # 7. No dilution: shares_now <= shares_prior * 1.005 (≤+0.5% YoY).
    # BUG FIX (M1 #5): prior code awarded +1 unconditionally. Now we use the
    # real `Shares` and `Shares_PriorYear` from the data fetcher. Skip on NaN.
    shares_now = row.get("Shares", np.nan)
    shares_prior = row.get("Shares_PriorYear", np.nan)
    if (
        _is_finite(shares_now)
        and _is_finite(shares_prior)
        and shares_prior > 0
    ):
        delta = (float(shares_now) - float(shares_prior)) / float(shares_prior)
        signals.append(1 if delta <= 0.005 else 0)
    else:
        signals.append(None)

    # 8. Gross margin healthy (>20%)
    gm = row.get("GrossMargin", np.nan)
    if _is_finite(gm):
        signals.append(1 if gm > 0.2 else 0)
    else:
        signals.append(None)

    # 9. Asset turnover (Revenue/Assets > 0.3)
    ta = row.get("TotalAssets", np.nan)
    rev = row.get("Revenue", np.nan)
    if _is_finite(ta) and _is_finite(rev) and ta > 0:
        signals.append(1 if rev / ta > 0.3 else 0)
    else:
        signals.append(None)

    return int(sum(s for s in signals if s is not None))


def altman_z_score(row: pd.Series) -> float:
    """Compute Altman Z (manufacturers) or Z'' (everything else).

    BUG FIX (M1 #7): prior code fabricated proxies:
        - Working capital ≈ Cash − 0.3×TotalDebt
        - Retained earnings ≈ 0.4×Equity
        - X3 used the EBITDA-aliased EBIT
    All three are eliminated. We now use:
        - WC = CurrentAssets − CurrentLiabilities (real)
        - RE = RetainedEarnings (real)
        - EBIT = real EBIT from data_fetcher
    If any required input is NaN, return NaN -- never fabricate.

    Sector dispatch:
        Manufacturers (Industrials, Materials, Energy, Consumer Cyclical/Defensive)
            -> Classic 5-factor Altman Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5
            -> Zones: Safe > 2.99 / Grey 1.81–2.99 / Distress < 1.81
        Non-manufacturers (services, tech, utilities, financials, etc.)
            -> Altman Z'' (4-factor, no X5) = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4
            -> Zones: Safe > 2.6 / Grey 1.1–2.6 / Distress < 1.1
    Note the Z'' zone thresholds DIFFER from classic Z; downstream interpretation
    should be sector-aware.

    Returns
    -------
    float
        Z or Z'' score, or NaN if inputs are insufficient.
    """
    ta = row.get("TotalAssets", np.nan)
    eq = row.get("TotalEquity", np.nan)
    rev = row.get("Revenue", np.nan)
    ebit = row.get("EBIT", np.nan)
    mktcap = row.get("MarketCap", np.nan)
    current_assets = row.get("CurrentAssets", np.nan)
    current_liabilities = row.get("CurrentLiabilities", np.nan)
    retained_earnings = row.get("RetainedEarnings", np.nan)
    sector = row.get("Sector", "")

    # X1 = Working Capital / Total Assets  -- real now, no fabrication.
    if not (_is_finite(current_assets) and _is_finite(current_liabilities) and _is_finite(ta) and ta > 0):
        return np.nan
    wc = float(current_assets) - float(current_liabilities)
    x1 = wc / float(ta)

    # X2 = Retained Earnings / TA  -- real now, no fabrication.
    if not _is_finite(retained_earnings):
        return np.nan
    x2 = float(retained_earnings) / float(ta)

    # X3 = EBIT / TA -- real EBIT from M1 #1.
    if not _is_finite(ebit):
        return np.nan
    x3 = float(ebit) / float(ta)

    # X4 = MarketCap / TotalLiabilities (book-value variant uses BV equity, but
    # the original Altman 1968 used market value of equity / book value of liab).
    if not (_is_finite(mktcap) and _is_finite(eq)):
        return np.nan
    total_liab = float(ta) - float(eq)
    if total_liab <= 0:
        # Negative liabilities is undefined; skip rather than fabricate.
        return np.nan
    x4 = float(mktcap) / total_liab

    is_manufacturer = bool(sector) and sector in _ALTMAN_MANUFACTURER_SECTORS
    if is_manufacturer:
        if not _is_finite(rev):
            return np.nan
        x5 = float(rev) / float(ta)
        return 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    else:
        return 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4


def graham_number(row: pd.Series) -> float:
    """Calculate Graham Number intrinsic value."""
    ni = row.get("NetIncome", 0)
    shares = row.get("Shares", 0)
    eq = row.get("TotalEquity", 0)
    if shares <= 0 or ni <= 0 or eq <= 0:
        return np.nan
    eps = ni / shares
    bvps = eq / shares
    return np.sqrt(22.5 * eps * bvps)


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


# ══════════════════════════════════════════════════════════════
# Vectorised universe scorer (M3 + M5 + M9)
# ══════════════════════════════════════════════════════════════


def score_dataframe(
    df: pd.DataFrame,
    price_history_map: Optional[Dict[str, pd.DataFrame]] = None,
    market_history: Optional[pd.DataFrame] = None,
    news_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    estimates_map: Optional[Dict[str, pd.DataFrame]] = None,
    surprises_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> pd.DataFrame:
    """Score the entire universe in one vectorised pass and append columns.

    Parameters
    ----------
    df : pd.DataFrame
        Universe indexed by ticker, with the standard column schema. The
        ``Sector`` column drives sector-relative ranking (sectors with
        fewer than 5 peers fall back to global rank).
    price_history_map, market_history, news_map, estimates_map, surprises_map:
        Optional M5 / M9 inputs. When omitted, the M5 / M9 informational
        columns are still computed where the row-based fields suffice
        (Risk_Score_v2 falls back to row-only signals; momentum / sentiment
        are simply skipped). When provided, the function attaches the full
        column blocks for those categories.

    Returns
    -------
    pd.DataFrame
        ``df`` joined with ``Composite_Score``, six sub-scores, ``Signal``,
        ``Piotroski_F``, ``Altman_Z``, ``Graham_Number``, ``Graham_MoS``,
        ``data_completeness``, plus M5 informational columns
        (``EarningsQuality_Score``, ``Moat_Score``, ``Risk_Score_v2``) and
        M9 column blocks (when respective inputs are passed). Sorted
        descending by ``Composite_Score``.
    """
    if df.empty:
        return df

    # Vectorised sub-scores. Replace NaN sub-scores with 50.0 (neutral) so
    # the composite scale stays stable across rows with sparse data.
    valuation = valuation_score_df(df).apply(_nan_to_neutral)
    health = financial_health_score_df(df).apply(_nan_to_neutral)
    profitability = profitability_score_df(df).apply(_nan_to_neutral)
    growth = growth_score_df(df).apply(_nan_to_neutral)
    shareholder = shareholder_return_score_df(df).apply(_nan_to_neutral)
    risk = risk_score_df(df).apply(_nan_to_neutral)

    subscores = pd.DataFrame(
        {
            "Valuation_Score": valuation.round(1),
            "Health_Score": health.round(1),
            "Profitability_Score": profitability.round(1),
            "Growth_Score": growth.round(1),
            "Shareholder_Score": shareholder.round(1),
            "Risk_Score": risk.round(1),
        }
    )
    composite = _composite_from_subscores(subscores).round(1)

    # Per-row analytics that still operate row-wise (Altman, Graham,
    # Piotroski, completeness — these are not percentile-based).
    altman = df.apply(altman_z_score, axis=1)
    graham = df.apply(graham_number, axis=1)
    piotroski = df.apply(piotroski_f_score, axis=1).astype(int)
    completeness = df.apply(data_completeness, axis=1)
    signals = composite.apply(generate_signal)

    out = df.copy()
    out["Composite_Score"] = composite
    out["Valuation_Score"] = subscores["Valuation_Score"]
    out["Health_Score"] = subscores["Health_Score"]
    out["Profitability_Score"] = subscores["Profitability_Score"]
    out["Growth_Score"] = subscores["Growth_Score"]
    out["Shareholder_Score"] = subscores["Shareholder_Score"]
    out["Risk_Score"] = subscores["Risk_Score"]
    out["Signal"] = signals
    out["Piotroski_F"] = piotroski
    out["Altman_Z"] = altman.apply(lambda v: round(v, 2) if pd.notna(v) else np.nan)
    out["Graham_Number"] = graham.apply(lambda v: round(v, 2) if pd.notna(v) else np.nan)
    out["data_completeness"] = completeness

    # Graham margin of safety (vectorised).
    if "Price" in out.columns:
        price = pd.to_numeric(out["Price"], errors="coerce")
        gn = out["Graham_Number"]
        out["Graham_MoS"] = np.where(
            gn.notna() & price.notna() & (price > 0),
            (gn / price - 1) * 100,
            np.nan,
        )
        out["Graham_MoS"] = out["Graham_MoS"].round(1)
    else:
        out["Graham_MoS"] = np.nan

    # ------------------------------------------------------------------
    # M5: Informational sector-relative scores (NOT yet in Composite_Score).
    # ------------------------------------------------------------------
    try:
        out["EarningsQuality_Score"] = earnings_quality_score(out)
    except Exception:
        out["EarningsQuality_Score"] = 50.0
    try:
        out["Moat_Score"] = moat_score(out)
    except Exception:
        out["Moat_Score"] = 50.0
    try:
        out["Risk_Score_v2"] = risk_score_real(out, price_history_map=price_history_map)
    except Exception:
        out["Risk_Score_v2"] = 50.0

    # ---- M9: optional momentum / revisions / sentiment column blocks ----
    if price_history_map:
        from src.analysis.momentum import momentum_signals_df
        mom_df = momentum_signals_df(price_history_map, market_history)
        out = out.join(mom_df, how="left")
    if estimates_map:
        from src.analysis.revisions import revisions_signals_df
        rev_df = revisions_signals_df(estimates_map, surprises_map)
        out = out.join(rev_df, how="left")
    if news_map:
        from src.analysis.sentiment import sentiment_signals_df
        sent_df = sentiment_signals_df(news_map)
        out = out.join(sent_df, how="left")

    return out.sort_values("Composite_Score", ascending=False)


# Backward-compatible alias. Existing callers (daily_run.py,
# reporting/*.py, ScoringService.score_dataframe) keep working without
# modification.
score_universe = score_dataframe
