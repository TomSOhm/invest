"""
Invest Solo — Composite Scoring Engine
Implements the 0-100 scoring system from METHODOLOGY.md
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple

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


def _percentile_score(value: float, low_bad: float, high_good: float, inverse: bool = False) -> float:
    """Map a value to 0-100 score. If inverse=True, lower is better."""
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
    """Compute simplified Piotroski F-Score (0-9)."""
    score = 0
    # 1. ROA > 0
    if row.get("ROA", 0) > 0: score += 1
    # 2. Operating cashflow > 0
    if row.get("OperatingCashflow", 0) > 0: score += 1
    # 3. Delta ROA > 0 (use proxy: ROA > 5%)
    if row.get("ROA", 0) > 0.05: score += 1
    # 4. CFO > Net Income (accruals quality)
    if row.get("OperatingCashflow", 0) > row.get("NetIncome", float('inf')): score += 1
    # 5. Long-term debt decreased (proxy: D/E < 1.0)
    if row.get("DebtEquity", 2) < 1.0: score += 1
    # 6. Current ratio > 1.0
    cr = row.get("CurrentRatio", 0)
    if cr > 1.0: score += 1
    # 7. No dilution (proxy: shares stable) — award by default
    score += 1
    # 8. Gross margin positive
    if row.get("GrossMargin", 0) > 0.2: score += 1
    # 9. Asset turnover (Revenue/Assets)
    ta = row.get("TotalAssets", 0)
    rev = row.get("Revenue", 0)
    if ta > 0 and rev / ta > 0.3: score += 1
    return score


def altman_z_score(row: pd.Series) -> float:
    """Compute Altman Z-Score for bankruptcy risk assessment."""
    ta = row.get("TotalAssets", 0)
    if ta == 0:
        return np.nan
    eq = row.get("TotalEquity", 0)
    rev = row.get("Revenue", 0)
    ebit = row.get("EBIT", 0)
    mktcap = row.get("MarketCap", 0)
    total_liab = ta - eq
    # Working capital proxy
    wc = row.get("Cash", 0) - row.get("TotalDebt", 0) * 0.3
    x1 = wc / ta
    x2 = (eq * 0.4) / ta  # Retained earnings proxy
    x3 = ebit / ta
    x4 = mktcap / max(total_liab, 1)
    x5 = rev / ta
    return 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5


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


def score_universe(df: pd.DataFrame) -> pd.DataFrame:
    """Score entire universe and add all analytical columns."""
    results = []
    for ticker, row in df.iterrows():
        scores = compute_composite_score(row)
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
            "Altman_Z": round(altman_z_score(row), 2) if pd.notna(altman_z_score(row)) else np.nan,
            "Graham_Number": round(graham_number(row), 2) if pd.notna(graham_number(row)) else np.nan,
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
