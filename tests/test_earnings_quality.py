"""Unit tests for src.analysis.earnings_quality.

Coverage:
    - Beneish M-Score on Enron-like fixture (manipulator) → M > -1.78
    - Beneish M-Score on Berkshire-like fixture (clean)   → M < -2.5
    - Sloan accruals on aggressive-accrual fixture        → > 0.10
    - Cash Conversion Ratio:
        * FCF == NI for 5y → ratio ≈ 1.0
        * FCF == 0.5*NI    → ratio ≈ 0.5
        * Only 2 valid years → NaN (≥ 3 required)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    sys.path.insert(0, str(p))

from src.analysis.earnings_quality import (  # noqa: E402
    beneish_m_score,
    cash_conversion_ratio_5y,
    earnings_quality_score,
    sloan_accruals,
)

# ---------------------------------------------------------------------------
# Beneish M-Score fixtures
# ---------------------------------------------------------------------------


def _enron_like_row() -> pd.Series:
    """Synthetic Enron-style profile: aggressive accruals, deteriorating GM,
    explosive sales growth, asset mix shifting to non-current, leverage rising.

    The 8 Beneish indices should each push M well above -1.78.
    """
    return pd.Series(
        {
            # Receivables ballooning relative to sales (DSRI > 1)
            "Receivables": 200.0,
            "Receivables_PriorYear": 100.0,
            "Revenue": 600.0,
            "Revenue_PriorYear": 400.0,  # SGI = 1.5 (high growth)
            # Gross margin dropping (GMI > 1)
            "GrossMargin": 0.18,
            "GrossMargin_PriorYear": 0.30,
            # Asset mix shifting to non-current (AQI > 1)
            "TotalAssets": 1000.0,
            "TotalAssets_PriorYear": 800.0,
            "CurrentAssets": 300.0,
            "CurrentAssets_PriorYear": 320.0,  # NCA share rising
            # Depreciation slowing (DEPI > 1)
            "PPE": 600.0,
            "PPE_PriorYear": 480.0,
            "DepreciationAmortization": 30.0,
            "DepreciationAmortization_PriorYear": 50.0,
            # SGA holds steady relative to sales (SGAI ~ 1)
            "SGA": 60.0,
            "SGA_PriorYear": 40.0,
            # Earnings detached from cash (TATA huge positive)
            "NetIncome": 80.0,
            "OperatingCashflow": -40.0,
            # Leverage rising (LVGI > 1)
            "LongTermDebt": 400.0,
            "LongTermDebt_PriorYear": 200.0,
            "CurrentLiabilities": 200.0,
            "CurrentLiabilities_PriorYear": 160.0,
        }
    )


def _berkshire_like_row() -> pd.Series:
    """Synthetic clean-ops profile: stable margins, modest growth, cash > NI,
    falling leverage. M should be safely below -2.5.
    """
    return pd.Series(
        {
            "Receivables": 100.0,
            "Receivables_PriorYear": 100.0,
            "Revenue": 1050.0,  # 5% growth -- very modest
            "Revenue_PriorYear": 1000.0,
            "GrossMargin": 0.30,
            "GrossMargin_PriorYear": 0.30,
            "TotalAssets": 2000.0,
            "TotalAssets_PriorYear": 2000.0,
            "CurrentAssets": 800.0,
            "CurrentAssets_PriorYear": 800.0,
            "PPE": 1000.0,
            "PPE_PriorYear": 1000.0,
            # Depreciation accelerating slightly (DEPI < 1 -> negative pressure on M)
            "DepreciationAmortization": 110.0,
            "DepreciationAmortization_PriorYear": 100.0,
            "SGA": 100.0,
            "SGA_PriorYear": 100.0,
            # Earnings backed by cash (TATA strongly negative)
            "NetIncome": 200.0,
            "OperatingCashflow": 260.0,
            # Falling leverage (LVGI < 1)
            "LongTermDebt": 300.0,
            "LongTermDebt_PriorYear": 350.0,
            "CurrentLiabilities": 200.0,
            "CurrentLiabilities_PriorYear": 220.0,
        }
    )


def test_beneish_flags_enron_like_manipulator() -> None:
    m = beneish_m_score(_enron_like_row())
    assert math.isfinite(m), "Beneish should return a number on full inputs"
    assert m > -1.78, f"Enron-like fixture must trip the manipulator threshold; got M={m:.3f}"


def test_beneish_clears_clean_fixture() -> None:
    m = beneish_m_score(_berkshire_like_row())
    assert math.isfinite(m)
    assert m < -2.5, f"Clean fixture must produce M well below the manipulator threshold; got M={m:.3f}"


def test_beneish_returns_nan_on_missing_input() -> None:
    row = _berkshire_like_row()
    row["Revenue"] = np.nan
    assert math.isnan(beneish_m_score(row))


# ---------------------------------------------------------------------------
# Sloan accruals
# ---------------------------------------------------------------------------


def test_sloan_flags_aggressive_accruals() -> None:
    """NI - CFO = +50, avg TA = 250 → ratio 0.20 (very aggressive)."""
    row = pd.Series(
        {
            "NetIncome": 100.0,
            "OperatingCashflow": 50.0,
            "TotalAssets": 300.0,
            "TotalAssets_PriorYear": 200.0,
        }
    )
    val = sloan_accruals(row)
    assert val > 0.10, f"Expected aggressive-accrual flag, got {val}"
    assert math.isclose(val, 0.20, rel_tol=1e-6), f"Expected 0.20 exactly, got {val}"


def test_sloan_clean_when_cfo_exceeds_ni() -> None:
    row = pd.Series(
        {
            "NetIncome": 100.0,
            "OperatingCashflow": 130.0,
            "TotalAssets": 300.0,
            "TotalAssets_PriorYear": 200.0,
        }
    )
    val = sloan_accruals(row)
    assert val < 0.0, f"CFO > NI should yield negative accruals; got {val}"


def test_sloan_nan_on_missing_input() -> None:
    row = pd.Series({"NetIncome": 100.0, "OperatingCashflow": 80.0})
    assert math.isnan(sloan_accruals(row))


# ---------------------------------------------------------------------------
# Cash Conversion Ratio
# ---------------------------------------------------------------------------


def test_ccr_equal_fcf_and_ni_yields_one() -> None:
    fcf = [100.0, 110.0, 120.0, 130.0, 140.0]
    ni = [100.0, 110.0, 120.0, 130.0, 140.0]
    val = cash_conversion_ratio_5y(pd.Series({}), fcf_history=fcf, ni_history=ni)
    assert math.isclose(val, 1.0, rel_tol=1e-9)


def test_ccr_half_fcf_yields_half() -> None:
    fcf = [50.0, 55.0, 60.0, 65.0, 70.0]
    ni = [100.0, 110.0, 120.0, 130.0, 140.0]
    val = cash_conversion_ratio_5y(pd.Series({}), fcf_history=fcf, ni_history=ni)
    assert math.isclose(val, 0.5, rel_tol=1e-9)


def test_ccr_requires_three_valid_years() -> None:
    # Only 2 years of data → NaN
    fcf = [100.0, 110.0]
    ni = [100.0, 110.0]
    val = cash_conversion_ratio_5y(pd.Series({}), fcf_history=fcf, ni_history=ni)
    assert math.isnan(val)


def test_ccr_skips_loss_years() -> None:
    # NI <= 0 in two years → only 3 valid pairs, edge of validity
    fcf = [100.0, 110.0, 120.0, 130.0, 140.0]
    ni = [-50.0, -10.0, 100.0, 110.0, 120.0]  # 3 valid pairs (idx 2,3,4)
    val = cash_conversion_ratio_5y(pd.Series({}), fcf_history=fcf, ni_history=ni)
    assert math.isfinite(val), "3 valid pairs should be sufficient"
    # mean(120/100, 130/110, 140/120) ≈ 1.146
    assert 1.10 < val < 1.20, f"Mean of 3 valid ratios should be ~1.15, got {val}"


def test_ccr_reads_from_row_columns() -> None:
    row = pd.Series(
        {
            "FCF_History_5y": [100.0, 110.0, 120.0, 130.0, 140.0],
            "NetIncome_History_5y": [100.0, 110.0, 120.0, 130.0, 140.0],
        }
    )
    val = cash_conversion_ratio_5y(row)
    assert math.isclose(val, 1.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Aggregator -- earnings_quality_score
# ---------------------------------------------------------------------------


def test_earnings_quality_score_returns_0_100() -> None:
    rows = [_enron_like_row(), _berkshire_like_row()]
    df = pd.DataFrame(rows, index=["ENRON", "BRK"])
    df["FCF_History_5y"] = [
        [10.0, 20.0, 30.0, 40.0, 50.0],
        [200.0, 220.0, 240.0, 260.0, 280.0],
    ]
    df["NetIncome_History_5y"] = [
        [100.0, 110.0, 120.0, 130.0, 140.0],
        [200.0, 210.0, 220.0, 230.0, 240.0],
    ]
    df["Sector"] = ["", ""]  # bypass sector-relative
    score = earnings_quality_score(df)
    assert score.between(0.0, 100.0).all(), f"Scores must be in [0, 100]: {score.tolist()}"
    # Berkshire-like should clearly outscore Enron-like
    assert score.loc["BRK"] > score.loc["ENRON"], f"BRK should beat ENRON: {score.tolist()}"
