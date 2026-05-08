"""
Invest Solo — Composite Scoring Engine
Implements the 0-100 scoring system from METHODOLOGY.md
"""
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional, Set, Tuple

# M5 additions: Earnings Quality, Quality/Moat, real Risk metric aggregators.
# These are exported as top-level names so callers can do:
#     from src.analysis.scoring_engine import earnings_quality_score, moat_score, risk_score_real
# The composite score / weights remain UNCHANGED in M5 (M7 owns reshuffling).
from src.analysis.earnings_quality import earnings_quality_score  # noqa: E402,F401
from src.analysis.quality_moat import moat_score  # noqa: E402,F401
from src.analysis.risk_metrics import risk_score_real  # noqa: E402,F401

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


def score_universe(
    df: pd.DataFrame,
    price_history_map: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Score entire universe and add all analytical columns.

    M5 addition: also computes ``EarningsQuality_Score``, ``Moat_Score`` and
    ``Risk_Score_v2`` columns. The legacy ``Risk_Score`` is preserved
    (unchanged) so the public schema is stable; ``Risk_Score_v2`` is the new
    informational column. The composite calculation is NOT touched -- M7 owns
    the reshuffling of weights to incorporate the new categories.

    Parameters
    ----------
    df:
        Input universe DataFrame.
    price_history_map:
        Optional ``{ticker: pd.DataFrame}`` map plumbed through to
        ``risk_score_real`` for vol / drawdown / beta. When absent, the
        risk-v2 score falls back to row-only signals.
    """
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

    # ------------------------------------------------------------------
    # M5: Informational scores (do NOT participate in Composite_Score yet)
    # ------------------------------------------------------------------
    try:
        merged["EarningsQuality_Score"] = earnings_quality_score(merged)
    except Exception:
        merged["EarningsQuality_Score"] = 50.0
    try:
        merged["Moat_Score"] = moat_score(merged)
    except Exception:
        merged["Moat_Score"] = 50.0
    try:
        merged["Risk_Score_v2"] = risk_score_real(merged, price_history_map=price_history_map)
    except Exception:
        merged["Risk_Score_v2"] = 50.0

    return merged.sort_values("Composite_Score", ascending=False)
