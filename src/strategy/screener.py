"""
Invest Solo — Multi-Criteria Stock Screener
Filters universe based on quantitative criteria + PEA eligibility.
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, List


DEFAULT_FILTERS = {
    "min_market_cap": 100e6,
    "min_pe": 0,
    "max_pe": 25,
    "min_roe": 0.05,
    "min_current_ratio": 0.7,
    "max_debt_equity": 3.0,
    "min_interest_coverage": 2.0,
    "min_operating_margin": 0.0,
    "min_fcf": 0,
    "min_composite_score": 0,
}

PEA_STRICT_FILTERS = {
    "min_market_cap": 200e6,
    "min_pe": 0,
    "max_pe": 20,
    "min_roe": 0.08,
    "min_current_ratio": 0.8,
    "max_debt_equity": 2.0,
    "min_interest_coverage": 3.0,
    "min_operating_margin": 0.05,
    "min_fcf": 0,
    "min_composite_score": 55,
}

VALUE_FILTERS = {
    "min_market_cap": 50e6,
    "min_pe": 0,
    "max_pe": 15,
    "min_roe": 0.06,
    "max_debt_equity": 2.5,
    "min_interest_coverage": 2.0,
    "min_operating_margin": 0.0,
    "min_composite_score": 50,
}

QUALITY_GROWTH_FILTERS = {
    "min_market_cap": 500e6,
    "min_roe": 0.12,
    "min_operating_margin": 0.10,
    "min_revenue_growth": 0.05,
    "min_composite_score": 60,
}

DIVIDEND_INCOME_FILTERS = {
    "min_market_cap": 1e9,
    "min_div_yield": 0.03,
    "max_payout_ratio": 0.85,
    "min_interest_coverage": 3.0,
    "min_composite_score": 45,
}


def apply_filters(df: pd.DataFrame, filters: Dict, pea_only: bool = False) -> pd.DataFrame:
    """Apply screening filters to scored DataFrame."""
    mask = pd.Series(True, index=df.index)

    if pea_only:
        mask &= df["PEA"] == True

    f = filters
    if "min_market_cap" in f:
        mask &= df["MarketCap"] >= f["min_market_cap"]
    if "min_pe" in f:
        mask &= df["PE"] >= f["min_pe"]
    if "max_pe" in f:
        mask &= df["PE"] <= f["max_pe"]
    if "min_roe" in f:
        mask &= df["ROE"] >= f["min_roe"]
    if "min_current_ratio" in f:
        cr = df["CurrentRatio"]
        mask &= (cr >= f["min_current_ratio"]) | (cr == 0)  # Banks have 0
    if "max_debt_equity" in f:
        de = df["DebtEquity"]
        mask &= (de <= f["max_debt_equity"]) | (de < 0)  # Negative equity edge case
    if "min_interest_coverage" in f:
        mask &= df["InterestCoverage"] >= f["min_interest_coverage"]
    if "min_operating_margin" in f:
        mask &= df["OperatingMargin"] >= f["min_operating_margin"]
    if "min_fcf" in f:
        mask &= df["FCF"] >= f["min_fcf"]
    if "min_composite_score" in f and "Composite_Score" in df.columns:
        mask &= df["Composite_Score"] >= f["min_composite_score"]
    if "min_div_yield" in f:
        mask &= df["DivYield"] >= f["min_div_yield"]
    if "max_payout_ratio" in f:
        mask &= df["PayoutRatio"] <= f["max_payout_ratio"]
    if "min_revenue_growth" in f:
        mask &= df["RevenueGrowth"] >= f["min_revenue_growth"]

    # M1 bug fix #8: wire `min_avg_volume` and `min_years_listed` filters that
    # were loaded from settings.yaml but never applied. NaN-tolerant: rows
    # missing the column (e.g. older cached fetches) are KEPT, so we don't
    # silently drop everything when AvgVolume/YearsListed haven't been
    # populated yet by the data fetcher.
    if "min_avg_volume" in f and "AvgVolume" in df.columns:
        av = df["AvgVolume"]
        mask &= (av >= f["min_avg_volume"]) | av.isna()
    if "min_years_listed" in f and "YearsListed" in df.columns:
        yl = df["YearsListed"]
        mask &= (yl >= f["min_years_listed"]) | yl.isna()

    return df[mask].sort_values("Composite_Score", ascending=False)


def screen_pea_value(df: pd.DataFrame) -> pd.DataFrame:
    """Screen for PEA-eligible value stocks."""
    return apply_filters(df, VALUE_FILTERS, pea_only=True)


def screen_pea_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Screen for PEA-eligible quality growth stocks."""
    return apply_filters(df, QUALITY_GROWTH_FILTERS, pea_only=True)


def screen_dividend_income(df: pd.DataFrame) -> pd.DataFrame:
    """Screen for high-dividend income stocks."""
    return apply_filters(df, DIVIDEND_INCOME_FILTERS, pea_only=True)


def screen_global_best(df: pd.DataFrame) -> pd.DataFrame:
    """Screen top global picks regardless of PEA eligibility."""
    return apply_filters(df, DEFAULT_FILTERS, pea_only=False)


def get_top_picks(df: pd.DataFrame, n: int = 10, strategy: str = "pea_value") -> pd.DataFrame:
    """Get top N picks for a given strategy."""
    screeners = {
        "pea_value": screen_pea_value,
        "pea_quality": screen_pea_quality,
        "dividend": screen_dividend_income,
        "global": screen_global_best,
    }
    screener = screeners.get(strategy, screen_global_best)
    result = screener(df)
    return result.head(n)


def generate_screening_summary(df: pd.DataFrame) -> Dict:
    """Generate summary statistics of the screened universe."""
    if df.empty:
        return {"count": 0}
    return {
        "count": len(df),
        "avg_composite": round(df["Composite_Score"].mean(), 1),
        "avg_pe": round(df["PE"].mean(), 1),
        "avg_roe": round(df["ROE"].mean() * 100, 1),
        "avg_div_yield": round(df["DivYield"].mean() * 100, 2),
        "signals": df["Signal"].value_counts().to_dict(),
        "sectors": df["Sector"].value_counts().to_dict(),
        "countries": df["Country"].value_counts().to_dict(),
        "best_score": round(df["Composite_Score"].max(), 1),
        "worst_score": round(df["Composite_Score"].min(), 1),
    }
