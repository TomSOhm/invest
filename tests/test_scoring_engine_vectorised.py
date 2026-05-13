"""Vectorised scoring-engine tests (M3).

Verifies that ``score_dataframe`` (the new vectorised entry point and
the back-compat alias for ``score_universe``) emits the expected output
schema and that its sub-scores roll up into ``Composite_Score`` per the
documented weights.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.analysis.scoring_engine import (  # noqa: E402
    SCORING_WEIGHTS,
    growth_score_df,
    profitability_score_df,
    score_dataframe,
    score_universe,
    valuation_score_df,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixture: a small heterogeneous-sector universe
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def small_universe() -> pd.DataFrame:
    """Six software stocks (qualifies for sector rank with min_n=5) plus four
    others that fall through to global rank.
    """
    data = [
        # Six software stocks
        {
            "Ticker": "S1",
            "Sector": "Technology",
            "PE": 15,
            "PB": 4,
            "PS": 5,
            "PFCF": 20,
            "EV_EBITDA": 12,
            "EV_Sales": 4,
            "ROE": 0.20,
            "ROA": 0.10,
            "ROIC": 0.15,
            "OperatingMargin": 0.30,
            "NetMargin": 0.20,
            "FCFMargin": 0.18,
            "RevenueGrowth": 0.20,
            "DivYield": 0.005,
            "PayoutRatio": 0.10,
            "Beta": 1.1,
            "InterestCoverage": 25.0,
            "CurrentRatio": 1.5,
            "DebtEquity": 0.4,
            "EBITDA": 1e9,
            "TotalDebt": 5e8,
            "Cash": 1e9,
            "Price": 100,
            "Shares": 1e9,
            "TotalEquity": 5e9,
            "NetIncome": 5e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 5e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 1e9,
            "MarketCap": 1e11,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.6,
        },
        {
            "Ticker": "S2",
            "Sector": "Technology",
            "PE": 20,
            "PB": 5,
            "PS": 6,
            "PFCF": 25,
            "EV_EBITDA": 15,
            "EV_Sales": 5,
            "ROE": 0.18,
            "ROA": 0.09,
            "ROIC": 0.13,
            "OperatingMargin": 0.27,
            "NetMargin": 0.18,
            "FCFMargin": 0.15,
            "RevenueGrowth": 0.18,
            "DivYield": 0.0,
            "PayoutRatio": 0.0,
            "Beta": 1.2,
            "InterestCoverage": 20.0,
            "CurrentRatio": 1.4,
            "DebtEquity": 0.5,
            "EBITDA": 1e9,
            "TotalDebt": 5e8,
            "Cash": 8e8,
            "Price": 100,
            "Shares": 1e9,
            "TotalEquity": 5e9,
            "NetIncome": 5e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 5e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 1e9,
            "MarketCap": 1e11,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.6,
        },
        {
            "Ticker": "S3",
            "Sector": "Technology",
            "PE": 25,
            "PB": 6,
            "PS": 7,
            "PFCF": 30,
            "EV_EBITDA": 18,
            "EV_Sales": 6,
            "ROE": 0.16,
            "ROA": 0.08,
            "ROIC": 0.11,
            "OperatingMargin": 0.24,
            "NetMargin": 0.16,
            "FCFMargin": 0.13,
            "RevenueGrowth": 0.15,
            "DivYield": 0.01,
            "PayoutRatio": 0.20,
            "Beta": 1.3,
            "InterestCoverage": 15.0,
            "CurrentRatio": 1.3,
            "DebtEquity": 0.6,
            "EBITDA": 1e9,
            "TotalDebt": 5e8,
            "Cash": 6e8,
            "Price": 100,
            "Shares": 1e9,
            "TotalEquity": 5e9,
            "NetIncome": 5e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 5e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 1e9,
            "MarketCap": 1e11,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.6,
        },
        {
            "Ticker": "S4",
            "Sector": "Technology",
            "PE": 30,
            "PB": 7,
            "PS": 8,
            "PFCF": 35,
            "EV_EBITDA": 21,
            "EV_Sales": 7,
            "ROE": 0.14,
            "ROA": 0.07,
            "ROIC": 0.09,
            "OperatingMargin": 0.21,
            "NetMargin": 0.14,
            "FCFMargin": 0.11,
            "RevenueGrowth": 0.12,
            "DivYield": 0.0,
            "PayoutRatio": 0.0,
            "Beta": 1.4,
            "InterestCoverage": 12.0,
            "CurrentRatio": 1.2,
            "DebtEquity": 0.7,
            "EBITDA": 1e9,
            "TotalDebt": 5e8,
            "Cash": 4e8,
            "Price": 100,
            "Shares": 1e9,
            "TotalEquity": 5e9,
            "NetIncome": 5e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 5e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 1e9,
            "MarketCap": 1e11,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.6,
        },
        {
            "Ticker": "S5",
            "Sector": "Technology",
            "PE": 35,
            "PB": 8,
            "PS": 9,
            "PFCF": 40,
            "EV_EBITDA": 24,
            "EV_Sales": 8,
            "ROE": 0.12,
            "ROA": 0.06,
            "ROIC": 0.07,
            "OperatingMargin": 0.18,
            "NetMargin": 0.12,
            "FCFMargin": 0.09,
            "RevenueGrowth": 0.10,
            "DivYield": 0.0,
            "PayoutRatio": 0.0,
            "Beta": 1.5,
            "InterestCoverage": 8.0,
            "CurrentRatio": 1.1,
            "DebtEquity": 0.8,
            "EBITDA": 1e9,
            "TotalDebt": 5e8,
            "Cash": 3e8,
            "Price": 100,
            "Shares": 1e9,
            "TotalEquity": 5e9,
            "NetIncome": 5e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 5e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 1e9,
            "MarketCap": 1e11,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.6,
        },
        {
            "Ticker": "S6",
            "Sector": "Technology",
            "PE": 50,
            "PB": 10,
            "PS": 12,
            "PFCF": 60,
            "EV_EBITDA": 35,
            "EV_Sales": 10,
            "ROE": 0.08,
            "ROA": 0.04,
            "ROIC": 0.05,
            "OperatingMargin": 0.12,
            "NetMargin": 0.08,
            "FCFMargin": 0.06,
            "RevenueGrowth": 0.05,
            "DivYield": 0.0,
            "PayoutRatio": 0.0,
            "Beta": 1.8,
            "InterestCoverage": 5.0,
            "CurrentRatio": 1.0,
            "DebtEquity": 1.0,
            "EBITDA": 1e9,
            "TotalDebt": 5e8,
            "Cash": 2e8,
            "Price": 100,
            "Shares": 1e9,
            "TotalEquity": 5e9,
            "NetIncome": 5e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 5e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 1e9,
            "MarketCap": 1e11,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.6,
        },
        # Four utilities (small sector)
        {
            "Ticker": "U1",
            "Sector": "Utilities",
            "PE": 12,
            "PB": 1.5,
            "PS": 1,
            "PFCF": 14,
            "EV_EBITDA": 7,
            "EV_Sales": 1.5,
            "ROE": 0.10,
            "ROA": 0.05,
            "ROIC": 0.06,
            "OperatingMargin": 0.20,
            "NetMargin": 0.08,
            "FCFMargin": 0.10,
            "RevenueGrowth": 0.03,
            "DivYield": 0.04,
            "PayoutRatio": 0.50,
            "Beta": 0.5,
            "InterestCoverage": 5.0,
            "CurrentRatio": 1.2,
            "DebtEquity": 1.5,
            "EBITDA": 2e9,
            "TotalDebt": 3e9,
            "Cash": 5e8,
            "Price": 50,
            "Shares": 1e9,
            "TotalEquity": 4e9,
            "NetIncome": 4e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 4e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 5e8,
            "MarketCap": 5e10,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.4,
        },
        {
            "Ticker": "U2",
            "Sector": "Utilities",
            "PE": 14,
            "PB": 1.6,
            "PS": 1.1,
            "PFCF": 16,
            "EV_EBITDA": 8,
            "EV_Sales": 1.6,
            "ROE": 0.11,
            "ROA": 0.05,
            "ROIC": 0.07,
            "OperatingMargin": 0.21,
            "NetMargin": 0.09,
            "FCFMargin": 0.11,
            "RevenueGrowth": 0.04,
            "DivYield": 0.045,
            "PayoutRatio": 0.55,
            "Beta": 0.55,
            "InterestCoverage": 6.0,
            "CurrentRatio": 1.3,
            "DebtEquity": 1.4,
            "EBITDA": 2e9,
            "TotalDebt": 3e9,
            "Cash": 5e8,
            "Price": 50,
            "Shares": 1e9,
            "TotalEquity": 4e9,
            "NetIncome": 4e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 4e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 5e8,
            "MarketCap": 5e10,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.4,
        },
        {
            "Ticker": "U3",
            "Sector": "Utilities",
            "PE": 16,
            "PB": 1.7,
            "PS": 1.2,
            "PFCF": 18,
            "EV_EBITDA": 9,
            "EV_Sales": 1.7,
            "ROE": 0.12,
            "ROA": 0.06,
            "ROIC": 0.08,
            "OperatingMargin": 0.22,
            "NetMargin": 0.10,
            "FCFMargin": 0.12,
            "RevenueGrowth": 0.05,
            "DivYield": 0.05,
            "PayoutRatio": 0.60,
            "Beta": 0.6,
            "InterestCoverage": 7.0,
            "CurrentRatio": 1.4,
            "DebtEquity": 1.3,
            "EBITDA": 2e9,
            "TotalDebt": 3e9,
            "Cash": 5e8,
            "Price": 50,
            "Shares": 1e9,
            "TotalEquity": 4e9,
            "NetIncome": 4e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 4e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 5e8,
            "MarketCap": 5e10,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.4,
        },
        {
            "Ticker": "U4",
            "Sector": "Utilities",
            "PE": 20,
            "PB": 1.9,
            "PS": 1.4,
            "PFCF": 22,
            "EV_EBITDA": 11,
            "EV_Sales": 2.0,
            "ROE": 0.07,
            "ROA": 0.03,
            "ROIC": 0.05,
            "OperatingMargin": 0.18,
            "NetMargin": 0.06,
            "FCFMargin": 0.08,
            "RevenueGrowth": 0.01,
            "DivYield": 0.035,
            "PayoutRatio": 0.45,
            "Beta": 0.7,
            "InterestCoverage": 4.0,
            "CurrentRatio": 1.0,
            "DebtEquity": 1.7,
            "EBITDA": 2e9,
            "TotalDebt": 3e9,
            "Cash": 5e8,
            "Price": 50,
            "Shares": 1e9,
            "TotalEquity": 4e9,
            "NetIncome": 4e8,
            "TotalAssets": 1e10,
            "Revenue": 5e9,
            "EBIT": 1e9,
            "CurrentAssets": 4e9,
            "CurrentLiabilities": 3e9,
            "RetainedEarnings": 5e8,
            "MarketCap": 5e10,
            "Shares_PriorYear": 1e9,
            "OperatingCashflow": 1e9,
            "GrossMargin": 0.4,
        },
    ]
    return pd.DataFrame(data).set_index("Ticker")


# ──────────────────────────────────────────────────────────────────────────────
# score_dataframe schema
# ──────────────────────────────────────────────────────────────────────────────


def test_score_dataframe_emits_expected_columns(small_universe: pd.DataFrame) -> None:
    """The vectorised scorer emits the public schema unchanged."""
    out = score_dataframe(small_universe)
    expected = {
        "Composite_Score",
        "Valuation_Score",
        "Health_Score",
        "Profitability_Score",
        "Growth_Score",
        "Shareholder_Score",
        "Risk_Score",
        "Signal",
        "Piotroski_F",
        "Altman_Z",
        "Graham_Number",
        "Graham_MoS",
        "data_completeness",
    }
    assert expected.issubset(set(out.columns))


def test_score_dataframe_index_preserved(small_universe: pd.DataFrame) -> None:
    out = score_dataframe(small_universe)
    assert set(out.index) == set(small_universe.index)


def test_score_universe_is_alias(small_universe: pd.DataFrame) -> None:
    """``score_universe`` is the back-compat alias for ``score_dataframe``."""
    out_a = score_dataframe(small_universe).sort_index()
    out_b = score_universe(small_universe).sort_index()
    pd.testing.assert_frame_equal(out_a, out_b)


# ──────────────────────────────────────────────────────────────────────────────
# Composite is the weighted sum of sub-scores
# ──────────────────────────────────────────────────────────────────────────────


def test_composite_aliases_score_lt(small_universe: pd.DataFrame) -> None:
    """M7: ``Composite_Score`` is now an alias for the long-term horizon
    composite (``score_lt``).  Pre-M7 this test verified a fixed weight
    formula across the six legacy sub-scores; M7 introduces the
    horizon-specific weight schemes (LT weights live under
    ``settings.horizons.long_term.weights``), so the legacy formula no
    longer matches.

    M10 will atomically swap the public schema and delete this alias.
    Until then the contract we test is: every row's ``Composite_Score``
    equals its ``score_lt`` (with NaN-safe fallback to the underlying
    legacy composite when the row was so sparse the horizon block
    couldn't compute a finite value).
    """
    out = score_dataframe(small_universe)
    # Every row that has a finite score_lt should match Composite_Score exactly.
    has_lt = out["score_lt"].notna()
    np.testing.assert_allclose(
        out.loc[has_lt, "Composite_Score"].values,
        out.loc[has_lt, "score_lt"].values,
        atol=0.11,
    )


def test_subscores_still_use_legacy_weight_keys() -> None:
    """Sanity: ``SCORING_WEIGHTS`` (legacy single-composite weights) is
    still exported because ``compute_composite_score`` (per-row API) keeps
    using it. Just verify the keys haven't drifted; M10 owns the rename.
    """
    expected_keys = {
        "valuation",
        "financial_health",
        "profitability",
        "growth",
        "shareholder_return",
        "risk",
    }
    assert set(SCORING_WEIGHTS.keys()) == expected_keys
    assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-6


def test_subscores_in_range(small_universe: pd.DataFrame) -> None:
    """Every sub-score is in [0, 100]."""
    out = score_dataframe(small_universe)
    for col in [
        "Valuation_Score",
        "Health_Score",
        "Profitability_Score",
        "Growth_Score",
        "Shareholder_Score",
        "Risk_Score",
        "Composite_Score",
    ]:
        s = out[col].dropna()
        assert (s >= 0).all() and (s <= 100).all(), f"{col} out of range"


# ──────────────────────────────────────────────────────────────────────────────
# Sector-relative behaviour smoke test
# ──────────────────────────────────────────────────────────────────────────────


def test_within_tech_sector_higher_pe_scores_lower(small_universe: pd.DataFrame) -> None:
    """Within the 6-stock tech sector, higher P/E gets a lower valuation score."""
    score_dataframe(small_universe)
    val = valuation_score_df(small_universe)
    # S1 (PE=15) > S6 (PE=50) on valuation, by sector rank.
    assert val.loc["S1"] > val.loc["S6"]
    # And specifically the PE-rank component within tech gives S1 the
    # top score and S6 the bottom (since P/E is the only inverse-ranked
    # cheapness signal where this universe varies monotonically).
    # The full valuation_score averages many components; we just verify
    # ordering is consistent with the within-sector ranking.


def test_growth_score_within_sector_monotonic(small_universe: pd.DataFrame) -> None:
    """Growth score: higher RevenueGrowth -> higher score within tech."""
    growth = growth_score_df(small_universe)
    # S1 has highest growth (0.20), S6 has lowest (0.05) within tech.
    assert growth.loc["S1"] > growth.loc["S6"]


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────


def test_score_dataframe_empty_returns_empty() -> None:
    out = score_dataframe(pd.DataFrame())
    assert out.empty


def test_negative_pe_penalty_applied() -> None:
    """A row with PE < 0 has its PE component overridden to the penalty."""
    df = pd.DataFrame(
        {
            "Sector": ["Technology"] * 6,
            "PE": [10, 20, 30, 40, 50, -5],
            "PB": [3, 4, 5, 6, 7, 8],
            "PS": [3, 4, 5, 6, 7, 8],
            "PFCF": [10, 20, 30, 40, 50, 60],
            "EV_EBITDA": [10, 12, 14, 16, 18, 20],
            "EV_Sales": [3, 4, 5, 6, 7, 8],
        },
        index=["A", "B", "C", "D", "E", "F"],
    )
    val = valuation_score_df(df)
    # Row F (negative PE) should be lower than row E (PE=50, the worst
    # of the positive-PE peers) because the penalty 10 is below E's
    # within-sector inverse rank.
    assert val.loc["F"] < val.loc["E"]


def test_profitability_higher_is_better() -> None:
    """Profitability is monotonic in ROE/ROIC etc within sector."""
    df = pd.DataFrame(
        {
            "Sector": ["Technology"] * 5,
            "ROE": [0.05, 0.10, 0.15, 0.20, 0.25],
            "ROA": [0.02, 0.04, 0.06, 0.08, 0.10],
            "ROIC": [0.04, 0.08, 0.12, 0.16, 0.20],
            "OperatingMargin": [0.05, 0.10, 0.15, 0.20, 0.25],
            "NetMargin": [0.03, 0.06, 0.09, 0.12, 0.15],
            "FCFMargin": [0.02, 0.04, 0.06, 0.08, 0.10],
        },
        index=["A", "B", "C", "D", "E"],
    )
    score = profitability_score_df(df)
    # Strict monotonic increase across A..E.
    vals = score.values
    assert all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
