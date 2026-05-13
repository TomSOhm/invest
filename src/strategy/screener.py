"""
Invest Solo — Multi-Criteria Stock Screener
Filters universe based on quantitative criteria + PEA eligibility.

M1 adds: min_avg_volume and min_years_listed filter wiring (bug #8).

M8 extends apply_filters to handle every filter key used by the 9 horizon
presets in horizon_presets.py.  Newly handled keys are documented below in
the apply_filters docstring.  The design principle for missing data is:

    "Silently skip" semantics — if the required column is absent from
    the DataFrame the filter is skipped (not applied), so adding a new
    data column incrementally never breaks existing runs.  NaN values
    within a present column always pass (conservative; we don't exclude
    names just because a metric couldn't be fetched).

Legacy presets (DEFAULT_FILTERS, PEA_STRICT_FILTERS, VALUE_FILTERS,
QUALITY_GROWTH_FILTERS, DIVIDEND_INCOME_FILTERS) and their helper
functions (screen_pea_value, screen_global_best, etc.) are preserved
unchanged so existing callers keep working.
"""

import numpy as np
import pandas as pd

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


def _col_present(df: pd.DataFrame, col: str) -> bool:
    """True when *col* exists as a column in *df*."""
    return col in df.columns


def _nan_safe_ge(series: pd.Series, threshold: float) -> pd.Series:
    """``series >= threshold`` where NaN rows pass (conservative semantics)."""
    return (series >= threshold) | series.isna()


def _nan_safe_le(series: pd.Series, threshold: float) -> pd.Series:
    """``series <= threshold`` where NaN rows pass (conservative semantics)."""
    return (series <= threshold) | series.isna()


def apply_filters(df: pd.DataFrame, filters: dict, pea_only: bool = False) -> pd.DataFrame:
    """Apply screening filters to scored DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Universe indexed by ticker.  Must contain a ``Composite_Score``
        column for the sort step; all other columns are optional — any
        filter whose target column is absent is silently skipped.
    filters : dict
        Key/value filter spec.  Any combination of the keys listed below
        may be present; unknown keys are silently ignored.
    pea_only : bool, default False
        When True, restrict to rows where ``df["PEA"] == True``.  The
        ``pea_only`` *key* inside the filters dict is also accepted and
        has the same effect (avoids having to thread the parameter
        separately from the preset dict).

    Filter keys
    -----------
    Legacy / existing (M0–M1):
        min_market_cap          : df["MarketCap"]
        min_pe / max_pe         : df["PE"]
        min_roe                 : df["ROE"]
        min_current_ratio       : df["CurrentRatio"] (banks: 0 accepted)
        max_debt_equity         : df["DebtEquity"]  (negative equity: pass)
        min_interest_coverage   : df["InterestCoverage"]
        min_operating_margin    : df["OperatingMargin"]
        min_fcf                 : df["FCF"]
        min_composite_score     : df["Composite_Score"]
        min_div_yield           : df["DivYield"]
        max_payout_ratio        : df["PayoutRatio"]
        min_revenue_growth      : df["RevenueGrowth"]

    Universal pre-filters (M1 partial, M8 complete):
        min_avg_volume          : df["AvgVolume"]  — M1 fix #8 (NaN = pass)
        min_avg_daily_volume_eur: same column (alias, added by M8 presets)
        min_years_listed        : df["YearsListed"]  — M1 fix #8
        exclude_sectors         : list[str] — drop rows in df["Sector"]
        not_in_distress         : bool — drop rows where Altman_Z < 1.1
        min_data_completeness   : df["data_completeness"]

    Sector-relative percentile scores (M3):
        min_valuation_score     : df["Valuation_Score"]
        max_valuation_score     : df["Valuation_Score"]  (for deep-value presets)
        min_health_score        : df["Health_Score"]
        min_profitability_score : df["Profitability_Score"]
        min_growth_score        : df["Growth_Score"]
        min_shareholder_score   : df["Shareholder_Score"]
        min_risk_score_v2       : df["Risk_Score_v2"]
        min_earnings_quality_score : df["EarningsQuality_Score"]
        min_moat_score          : df["Moat_Score"]
        min_momentum_score      : df["Momentum_Score"]

    Quality / financial floors (M4/M5):
        min_f_score             : df["Piotroski_F"]
        min_altman_z            : df["Altman_Z"]  (custom threshold)
        max_nd_ebitda           : df["Net_Debt_EBITDA"] or inline TotalDebt/Cash/EBITDA
        min_interest_coverage   : df["InterestCoverage"]
        min_ccr_3y_avg          : df["CashConversionRatio_3y"]
        min_ccr_5y_avg          : df["CashConversionRatio_5y"]
        min_gross_profitability : df["Gross_Profitability"]
        min_roic_5y_avg         : df["ROIC_5y_Avg"]
        min_roic                : df["ROIC"]
        min_fcf_margin          : df["FCFMargin"]
        max_beta                : df["Beta"]
        max_realized_vol_1y     : df["Realized_Vol_1y"]

    Valuation:
        max_ev_ebit             : df["EV_EBIT"] or inline EV/EBIT
        max_p_fcf               : df["PFCF"]
        max_pb                  : df["PB"]
        min_dcf_mos             : df["DCF_MoS_Mid"]  (M6)

    Growth (multi-period):
        min_revenue_cagr_5y     : df["RevenueCAGR_5y"]
        max_revenue_cagr_5y     : df["RevenueCAGR_5y"]
        min_eps_cagr_5y         : df["EPS_CAGR_5y"]
        min_pos_revenue_years_5y: df["PosRevenueYears_5y"]
        min_revenue_growth_yoy  : df["RevenueGrowth"] (alias)

    Dividend:
        min_div_yield           : df["DivYield"]
        max_payout_ratio        : df["PayoutRatio"]
        min_dividend_growth_5y_cagr : df["DivGrowth_5y_CAGR"]
        min_fcf_dividend_coverage   : df["FCF_DivCoverage"]
        min_consecutive_dividend_years : df["ConsecutiveDivYears"]
        min_total_shareholder_yield : df["TotalShareholderYield"]

    Momentum / revisions / sentiment (M9):
        min_eps_revision_3m     : df["EPS_Rev_90d"]  (90-day window ~ 3m)
        min_eps_revision_6m     : df["EPS_Rev_180d"]
        min_relative_strength_3m_vs_index : df["RS_3m"]
        price_above_50dma       : df["Above_50DMA"]  (bool)
        price_above_200dma      : df["Above_200DMA"] (bool)
        ma_50_above_ma_200      : df["Golden_Cross"]  (bool)
        min_volume_surge_5d_vs_90d : df["Volume_Surge"]
        min_sue_z_score         : df["SUE"]
        min_news_sentiment_30d  : df["Sentiment_Score"]  (NaN = pass)

    Composite horizon scores (M7):
        min_composite_score_lt  : df["score_lt"]
        min_composite_score_mt  : df["score_mt"]
        min_composite_score_st  : df["score_st"]

    Turnaround / event flags (requires plumbing):
        min_op_margin_improvement_yoy : df["OpMarginImprovement_YoY"]
        positive_fcf_latest_year      : df["FCF"] > 0 (direct column)
        positive_cash_balance         : df["Cash"] > 0

    Notes on NaN handling:
        NaN values in a present column always PASS the filter (conservative).
        This means sparse data causes false positives, not false negatives.
        Apply ``min_data_completeness`` to cull genuinely sparse rows first.
    """
    mask = pd.Series(True, index=df.index)

    # pea_only can come from the parameter or from inside the filters dict
    effective_pea_only = pea_only or bool(filters.get("pea_only", False))
    if effective_pea_only:
        if _col_present(df, "PEA"):
            mask &= df["PEA"]
        # If PEA column absent, skip (don't crash); caller should ensure column.

    f = filters

    # ── Legacy / core filters ─────────────────────────────────────────────────
    if "min_market_cap" in f and _col_present(df, "MarketCap"):
        mask &= _nan_safe_ge(df["MarketCap"], f["min_market_cap"])
    if "min_pe" in f and _col_present(df, "PE"):
        mask &= _nan_safe_ge(df["PE"], f["min_pe"])
    if "max_pe" in f and _col_present(df, "PE"):
        mask &= _nan_safe_le(df["PE"], f["max_pe"])
    if "min_roe" in f and _col_present(df, "ROE"):
        mask &= _nan_safe_ge(df["ROE"], f["min_roe"])
    if "min_current_ratio" in f and _col_present(df, "CurrentRatio"):
        cr = df["CurrentRatio"]
        mask &= (cr >= f["min_current_ratio"]) | (cr == 0) | cr.isna()  # Banks: 0 accepted
    if "max_debt_equity" in f and _col_present(df, "DebtEquity"):
        de = df["DebtEquity"]
        mask &= (de <= f["max_debt_equity"]) | (de < 0) | de.isna()  # Negative equity edge case
    if "min_interest_coverage" in f and _col_present(df, "InterestCoverage"):
        mask &= _nan_safe_ge(df["InterestCoverage"], f["min_interest_coverage"])
    if "min_operating_margin" in f and _col_present(df, "OperatingMargin"):
        mask &= _nan_safe_ge(df["OperatingMargin"], f["min_operating_margin"])
    if "min_fcf" in f and _col_present(df, "FCF"):
        mask &= _nan_safe_ge(df["FCF"], f["min_fcf"])
    if "min_composite_score" in f and _col_present(df, "Composite_Score"):
        mask &= _nan_safe_ge(df["Composite_Score"], f["min_composite_score"])
    if "min_div_yield" in f and _col_present(df, "DivYield"):
        mask &= _nan_safe_ge(df["DivYield"], f["min_div_yield"])
    if "max_payout_ratio" in f and _col_present(df, "PayoutRatio"):
        mask &= _nan_safe_le(df["PayoutRatio"], f["max_payout_ratio"])
    if "min_revenue_growth" in f and _col_present(df, "RevenueGrowth"):
        mask &= _nan_safe_ge(df["RevenueGrowth"], f["min_revenue_growth"])

    # ── M1 fix #8: min_avg_volume / min_years_listed ──────────────────────────
    # NaN rows pass so old cached fetches without these columns are not silently
    # discarded.  Both the original key and the M8 alias are accepted.
    _avg_vol_threshold = f.get("min_avg_volume") or f.get("min_avg_daily_volume_eur")
    if _avg_vol_threshold is not None and _col_present(df, "AvgVolume"):
        av = df["AvgVolume"]
        mask &= (av >= _avg_vol_threshold) | av.isna()
    if "min_years_listed" in f and _col_present(df, "YearsListed"):
        yl = df["YearsListed"]
        mask &= (yl >= f["min_years_listed"]) | yl.isna()

    # ── M8: Universal pre-filters ─────────────────────────────────────────────

    # exclude_sectors: drop rows whose Sector is in the exclusion list
    if "exclude_sectors" in f and _col_present(df, "Sector"):
        excluded: list[str] = list(f["exclude_sectors"])
        if excluded:
            mask &= ~df["Sector"].isin(excluded)

    # not_in_distress: Altman Z'' / Z must be > 1.1 (universal distress floor)
    if f.get("not_in_distress", False) and _col_present(df, "Altman_Z"):
        az = pd.to_numeric(df["Altman_Z"], errors="coerce")
        mask &= _nan_safe_ge(az, 1.1)

    # min_data_completeness: fraction of scoring fields that are finite
    if "min_data_completeness" in f and _col_present(df, "data_completeness"):
        mask &= _nan_safe_ge(df["data_completeness"], f["min_data_completeness"])

    # ── M8: Sector-relative percentile scores (M3) ────────────────────────────

    if "min_valuation_score" in f and _col_present(df, "Valuation_Score"):
        mask &= _nan_safe_ge(df["Valuation_Score"], f["min_valuation_score"])
    # max_valuation_score: used by LT_DEEP_VALUE to stay in the cheapest tier
    if "max_valuation_score" in f and _col_present(df, "Valuation_Score"):
        mask &= _nan_safe_le(df["Valuation_Score"], f["max_valuation_score"])
    if "min_health_score" in f and _col_present(df, "Health_Score"):
        mask &= _nan_safe_ge(df["Health_Score"], f["min_health_score"])
    if "min_profitability_score" in f and _col_present(df, "Profitability_Score"):
        mask &= _nan_safe_ge(df["Profitability_Score"], f["min_profitability_score"])
    if "min_growth_score" in f and _col_present(df, "Growth_Score"):
        mask &= _nan_safe_ge(df["Growth_Score"], f["min_growth_score"])
    if "min_shareholder_score" in f and _col_present(df, "Shareholder_Score"):
        mask &= _nan_safe_ge(df["Shareholder_Score"], f["min_shareholder_score"])
    if "min_risk_score_v2" in f and _col_present(df, "Risk_Score_v2"):
        mask &= _nan_safe_ge(df["Risk_Score_v2"], f["min_risk_score_v2"])
    if "min_earnings_quality_score" in f and _col_present(df, "EarningsQuality_Score"):
        mask &= _nan_safe_ge(df["EarningsQuality_Score"], f["min_earnings_quality_score"])
    if "min_moat_score" in f and _col_present(df, "Moat_Score"):
        mask &= _nan_safe_ge(df["Moat_Score"], f["min_moat_score"])
    if "min_momentum_score" in f and _col_present(df, "Momentum_Score"):
        mask &= _nan_safe_ge(df["Momentum_Score"], f["min_momentum_score"])

    # ── M8: Quality / financial floors (M4/M5) ───────────────────────────────

    # Piotroski F-Score floor
    if "min_f_score" in f and _col_present(df, "Piotroski_F"):
        mask &= _nan_safe_ge(df["Piotroski_F"], f["min_f_score"])

    # Custom Altman Z floor (not_in_distress uses 1.1; this allows higher floor)
    if "min_altman_z" in f and _col_present(df, "Altman_Z"):
        az = pd.to_numeric(df["Altman_Z"], errors="coerce")
        mask &= _nan_safe_ge(az, f["min_altman_z"])

    # Net Debt / EBITDA: prefer a pre-computed column; compute inline if absent
    if "max_nd_ebitda" in f:
        if _col_present(df, "Net_Debt_EBITDA"):
            mask &= _nan_safe_le(df["Net_Debt_EBITDA"], f["max_nd_ebitda"])
        elif all(_col_present(df, c) for c in ("TotalDebt", "Cash", "EBITDA")):
            ebitda = pd.to_numeric(df["EBITDA"], errors="coerce")
            net_debt = pd.to_numeric(df["TotalDebt"], errors="coerce") - pd.to_numeric(df["Cash"], errors="coerce")
            nd_ebitda = net_debt / ebitda.where(ebitda.abs() > 0, other=np.nan)
            mask &= _nan_safe_le(nd_ebitda, f["max_nd_ebitda"])
        # If neither option is available, skip (NaN = pass semantics)

    # Cash Conversion Ratio 3y / 5y average (M5 EarningsQuality)
    if "min_ccr_3y_avg" in f and _col_present(df, "CashConversionRatio_3y"):
        mask &= _nan_safe_ge(df["CashConversionRatio_3y"], f["min_ccr_3y_avg"])
    if "min_ccr_5y_avg" in f and _col_present(df, "CashConversionRatio_5y"):
        mask &= _nan_safe_ge(df["CashConversionRatio_5y"], f["min_ccr_5y_avg"])

    # Gross profitability (Novy-Marx): GP / Total Assets
    if "min_gross_profitability" in f and _col_present(df, "Gross_Profitability"):
        mask &= _nan_safe_ge(df["Gross_Profitability"], f["min_gross_profitability"])

    # ROIC (trailing and 5y average)
    if "min_roic" in f and _col_present(df, "ROIC"):
        mask &= _nan_safe_ge(df["ROIC"], f["min_roic"])
    if "min_roic_5y_avg" in f and _col_present(df, "ROIC_5y_Avg"):
        mask &= _nan_safe_ge(df["ROIC_5y_Avg"], f["min_roic_5y_avg"])

    # FCF margin
    if "min_fcf_margin" in f and _col_present(df, "FCFMargin"):
        mask &= _nan_safe_ge(df["FCFMargin"], f["min_fcf_margin"])

    # Beta cap (volatility risk gate)
    if "max_beta" in f and _col_present(df, "Beta"):
        mask &= _nan_safe_le(df["Beta"], f["max_beta"])

    # Realised volatility 1y ceiling
    if "max_realized_vol_1y" in f and _col_present(df, "Realized_Vol_1y"):
        mask &= _nan_safe_le(df["Realized_Vol_1y"], f["max_realized_vol_1y"])

    # Gross margin stability (low stddev = stable pricing power)
    if "max_gross_margin_stddev_5y" in f and _col_present(df, "GrossMargin_Stddev_5y"):
        mask &= _nan_safe_le(df["GrossMargin_Stddev_5y"], f["max_gross_margin_stddev_5y"])

    # ── M8: Valuation filters ─────────────────────────────────────────────────

    # EV / EBIT: prefer pre-computed column; derive inline when absent
    if "max_ev_ebit" in f:
        if _col_present(df, "EV_EBIT"):
            mask &= _nan_safe_le(df["EV_EBIT"], f["max_ev_ebit"])
        elif all(_col_present(df, c) for c in ("EV_EBITDA", "EBITDA", "EBIT")):
            # Fallback: scale EV from EV_EBITDA using EBITDA/EBIT ratio
            ebitda = pd.to_numeric(df["EBITDA"], errors="coerce")
            ebit = pd.to_numeric(df["EBIT"], errors="coerce")
            ev_ebitda = pd.to_numeric(df["EV_EBITDA"], errors="coerce")
            # EV_EBIT = EV_EBITDA × (EBITDA / EBIT) where EBIT > 0
            ratio = ebitda / ebit.where(ebit > 0, other=np.nan)
            ev_ebit_derived = ev_ebitda * ratio
            mask &= _nan_safe_le(ev_ebit_derived, f["max_ev_ebit"])
        # If unable to compute: skip

    if "max_p_fcf" in f and _col_present(df, "PFCF"):
        mask &= _nan_safe_le(df["PFCF"], f["max_p_fcf"])
    if "max_pb" in f and _col_present(df, "PB"):
        mask &= _nan_safe_le(df["PB"], f["max_pb"])

    # DCF margin of safety (M6: DCF_MoS_Mid = (IV - Price) / Price)
    if "min_dcf_mos" in f and _col_present(df, "DCF_MoS_Mid"):
        mask &= _nan_safe_ge(df["DCF_MoS_Mid"], f["min_dcf_mos"])

    # ── M8: Multi-period growth filters ──────────────────────────────────────

    if "min_revenue_cagr_5y" in f and _col_present(df, "RevenueCAGR_5y"):
        mask &= _nan_safe_ge(df["RevenueCAGR_5y"], f["min_revenue_cagr_5y"])
    if "max_revenue_cagr_5y" in f and _col_present(df, "RevenueCAGR_5y"):
        mask &= _nan_safe_le(df["RevenueCAGR_5y"], f["max_revenue_cagr_5y"])
    if "min_eps_cagr_5y" in f and _col_present(df, "EPS_CAGR_5y"):
        mask &= _nan_safe_ge(df["EPS_CAGR_5y"], f["min_eps_cagr_5y"])
    if "min_pos_revenue_years_5y" in f and _col_present(df, "PosRevenueYears_5y"):
        mask &= _nan_safe_ge(df["PosRevenueYears_5y"], f["min_pos_revenue_years_5y"])
    # min_revenue_growth_yoy: alias of min_revenue_growth (uses RevenueGrowth column)
    if "min_revenue_growth_yoy" in f and _col_present(df, "RevenueGrowth"):
        mask &= _nan_safe_ge(df["RevenueGrowth"], f["min_revenue_growth_yoy"])
    # Operating margin trend (slope over 2 years; requires dedicated column)
    if "min_operating_margin_trend_2y" in f and _col_present(df, "OpMarginTrend_2y"):
        mask &= _nan_safe_ge(df["OpMarginTrend_2y"], f["min_operating_margin_trend_2y"])

    # ── M8: Dividend / income filters ────────────────────────────────────────

    if "min_dividend_growth_5y_cagr" in f and _col_present(df, "DivGrowth_5y_CAGR"):
        mask &= _nan_safe_ge(df["DivGrowth_5y_CAGR"], f["min_dividend_growth_5y_cagr"])
    if "min_fcf_dividend_coverage" in f and _col_present(df, "FCF_DivCoverage"):
        mask &= _nan_safe_ge(df["FCF_DivCoverage"], f["min_fcf_dividend_coverage"])
    if "min_consecutive_dividend_years" in f and _col_present(df, "ConsecutiveDivYears"):
        mask &= _nan_safe_ge(df["ConsecutiveDivYears"], f["min_consecutive_dividend_years"])
    if "min_total_shareholder_yield" in f and _col_present(df, "TotalShareholderYield"):
        mask &= _nan_safe_ge(df["TotalShareholderYield"], f["min_total_shareholder_yield"])

    # ── M8: Momentum / revisions / sentiment (M9 columns) ────────────────────

    # EPS revision over 3 months (~90 calendar days, EPS_Rev_90d column)
    if "min_eps_revision_3m" in f and _col_present(df, "EPS_Rev_90d"):
        mask &= _nan_safe_ge(df["EPS_Rev_90d"], f["min_eps_revision_3m"])
    # EPS revision over 6 months (~180 calendar days)
    if "min_eps_revision_6m" in f and _col_present(df, "EPS_Rev_180d"):
        mask &= _nan_safe_ge(df["EPS_Rev_180d"], f["min_eps_revision_6m"])
    # 3-month relative strength vs benchmark index
    if "min_relative_strength_3m_vs_index" in f and _col_present(df, "RS_3m"):
        mask &= _nan_safe_ge(df["RS_3m"], f["min_relative_strength_3m_vs_index"])
    # Price above 50dma flag (bool column)
    if f.get("price_above_50dma") and _col_present(df, "Above_50DMA"):
        mask &= df["Above_50DMA"].fillna(False).astype(bool)
    # Price above 200dma flag (bool column)
    if f.get("price_above_200dma") and _col_present(df, "Above_200DMA"):
        mask &= df["Above_200DMA"].fillna(False).astype(bool)
    # Golden cross: MA50 > MA200 (bool column)
    if f.get("ma_50_above_ma_200") and _col_present(df, "Golden_Cross"):
        mask &= df["Golden_Cross"].fillna(False).astype(bool)
    # Volume surge: 5-day vs 90-day average
    if "min_volume_surge_5d_vs_90d" in f and _col_present(df, "Volume_Surge"):
        mask &= _nan_safe_ge(df["Volume_Surge"], f["min_volume_surge_5d_vs_90d"])
    # SUE z-score (Standardised Unexpected Earnings)
    if "min_sue_z_score" in f and _col_present(df, "SUE"):
        mask &= _nan_safe_ge(df["SUE"], f["min_sue_z_score"])
    # News sentiment (FinBERT-based; NaN passes when model unavailable)
    if "min_news_sentiment_30d" in f and _col_present(df, "Sentiment_Score"):
        mask &= _nan_safe_ge(df["Sentiment_Score"], f["min_news_sentiment_30d"])

    # ── M8: Horizon composite score gates (M7 columns) ───────────────────────

    if "min_composite_score_lt" in f and _col_present(df, "score_lt"):
        mask &= _nan_safe_ge(df["score_lt"], f["min_composite_score_lt"])
    if "min_composite_score_mt" in f and _col_present(df, "score_mt"):
        mask &= _nan_safe_ge(df["score_mt"], f["min_composite_score_mt"])
    if "min_composite_score_st" in f and _col_present(df, "score_st"):
        mask &= _nan_safe_ge(df["score_st"], f["min_composite_score_st"])

    # ── M8: Turnaround / event boolean flags ─────────────────────────────────

    # min_op_margin_improvement_yoy (MT_TURNAROUND)
    if "min_op_margin_improvement_yoy" in f and _col_present(df, "OpMarginImprovement_YoY"):
        mask &= _nan_safe_ge(df["OpMarginImprovement_YoY"], f["min_op_margin_improvement_yoy"])
    # positive_fcf_latest_year: FCF > 0
    if f.get("positive_fcf_latest_year") and _col_present(df, "FCF"):
        fcf = pd.to_numeric(df["FCF"], errors="coerce")
        mask &= (fcf > 0) | fcf.isna()
    # positive_cash_balance: Cash > 0
    if f.get("positive_cash_balance") and _col_present(df, "Cash"):
        cash = pd.to_numeric(df["Cash"], errors="coerce")
        mask &= (cash > 0) | cash.isna()

    # ── Determine sort column ─────────────────────────────────────────────────
    # Prefer horizon-specific score when a horizon composite gate was applied;
    # fall back to Composite_Score for generic/legacy filters.
    sort_col = "Composite_Score"
    for horizon_key, col in [
        ("min_composite_score_lt", "score_lt"),
        ("min_composite_score_mt", "score_mt"),
        ("min_composite_score_st", "score_st"),
    ]:
        if horizon_key in f and _col_present(df, col):
            sort_col = col
            break

    result = df[mask]
    if _col_present(result, sort_col):
        return result.sort_values(sort_col, ascending=False)
    return result


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


def generate_screening_summary(df: pd.DataFrame) -> dict:
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
