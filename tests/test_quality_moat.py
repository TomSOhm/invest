"""Unit tests for src.analysis.quality_moat.

Coverage:
    - GP/TA on Costco-like fixture (high revenue, low TA) → high.
    - GP/TA on capital-heavy utility (low revenue, high TA) → low.
    - ROIC stability: stddev=0 → max; stddev=high → low.
    - reinvestment_efficiency happy path & NaN guards.
    - moat_score returns 0..100 with finite outputs.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    sys.path.insert(0, str(p))

from src.analysis.quality_moat import (  # noqa: E402
    gross_profitability,
    moat_score,
    operating_margin_stability,
    reinvestment_efficiency,
    roic_5y_avg,
    roic_stability,
    roic_wacc_spread,
)


# ---------------------------------------------------------------------------
# Gross Profitability (Novy-Marx)
# ---------------------------------------------------------------------------


def test_gross_profitability_high_for_costco_like() -> None:
    """High-turnover retailer: Revenue 200, COGS 170, TA 50 → GP/TA = 0.6."""
    row = pd.Series({"Revenue": 200.0, "COGS": 170.0, "TotalAssets": 50.0})
    val = gross_profitability(row)
    assert math.isclose(val, 0.6, rel_tol=1e-6)
    assert val > 0.30, "Costco-like fixture should clear the moat heuristic"


def test_gross_profitability_low_for_capital_heavy_utility() -> None:
    """Capital-intensive utility: Revenue 50, COGS 40, TA 500 → GP/TA = 0.02."""
    row = pd.Series({"Revenue": 50.0, "COGS": 40.0, "TotalAssets": 500.0})
    val = gross_profitability(row)
    assert math.isclose(val, 0.02, rel_tol=1e-6)
    assert val < 0.10, "Capital-heavy utility should fail the moat heuristic"


def test_gross_profitability_falls_back_to_gross_margin() -> None:
    """When COGS missing, fall back to GrossMargin × Revenue / TotalAssets."""
    row = pd.Series({"Revenue": 100.0, "TotalAssets": 50.0, "GrossMargin": 0.4})
    val = gross_profitability(row)
    assert math.isclose(val, 0.8, rel_tol=1e-6)


def test_gross_profitability_nan_when_no_inputs() -> None:
    row = pd.Series({})
    assert math.isnan(gross_profitability(row))


# ---------------------------------------------------------------------------
# ROIC stability / 5y avg
# ---------------------------------------------------------------------------


def test_roic_5y_avg_basic() -> None:
    history = [0.10, 0.12, 0.15, 0.13, 0.11]
    val = roic_5y_avg(pd.Series({}), roic_history=history)
    assert math.isclose(val, 0.122, rel_tol=1e-6)


def test_roic_5y_avg_requires_three_years() -> None:
    val = roic_5y_avg(pd.Series({}), roic_history=[0.10, 0.12])
    assert math.isnan(val)


def test_roic_stability_max_when_constant() -> None:
    """Constant ROIC → stddev=0 → 1/(1+0) = 1.0 (maximum stability)."""
    val = roic_stability(pd.Series({}), roic_history=[0.10, 0.10, 0.10, 0.10, 0.10])
    assert math.isclose(val, 1.0, rel_tol=1e-9)


def test_roic_stability_lower_when_volatile() -> None:
    val_stable = roic_stability(pd.Series({}), roic_history=[0.10, 0.10, 0.10, 0.10, 0.10])
    val_volatile = roic_stability(
        pd.Series({}), roic_history=[0.05, 0.30, -0.10, 0.40, 0.02]
    )
    assert val_volatile < val_stable, "Volatile ROIC must score lower than constant ROIC"
    assert 0.0 < val_volatile < 1.0


def test_roic_stability_nan_with_short_history() -> None:
    assert math.isnan(roic_stability(pd.Series({}), roic_history=[0.10]))


# ---------------------------------------------------------------------------
# Operating margin stability
# ---------------------------------------------------------------------------


def test_op_margin_stability_max_when_constant() -> None:
    val = operating_margin_stability(
        pd.Series({}), op_margin_history=[0.20, 0.20, 0.20, 0.20, 0.20]
    )
    assert math.isclose(val, 1.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# ROIC - WACC spread
# ---------------------------------------------------------------------------


def test_roic_wacc_spread_uses_default_when_wacc_missing() -> None:
    """ROIC=0.15, no WACC → uses default 0.09 → spread = 0.06."""
    row = pd.Series({"ROIC": 0.15})
    val = roic_wacc_spread(row)
    assert math.isclose(val, 0.06, rel_tol=1e-6)


def test_roic_wacc_spread_uses_real_wacc_when_present() -> None:
    row = pd.Series({"ROIC": 0.15, "WACC": 0.08})
    val = roic_wacc_spread(row)
    assert math.isclose(val, 0.07, rel_tol=1e-6)


def test_roic_wacc_spread_nan_without_roic() -> None:
    assert math.isnan(roic_wacc_spread(pd.Series({})))


# ---------------------------------------------------------------------------
# Reinvestment efficiency
# ---------------------------------------------------------------------------


def test_reinvestment_efficiency_happy_path() -> None:
    """ΔEBIT=200, ΔIC=100 → ratio 2.0."""
    row = pd.Series(
        {
            "EBIT_History_3y": [300.0, 200.0, 100.0],          # most recent first
            "InvestedCapital_History_3y": [600.0, 550.0, 500.0],
        }
    )
    val = reinvestment_efficiency(row)
    assert math.isclose(val, 2.0, rel_tol=1e-6)


def test_reinvestment_efficiency_nan_on_contraction() -> None:
    """Negative ΔIC → NaN (cannot infer compounding from a divestment)."""
    row = pd.Series(
        {
            "EBIT_History_3y": [200.0, 220.0, 240.0],
            "InvestedCapital_History_3y": [300.0, 400.0, 500.0],  # IC fell
        }
    )
    assert math.isnan(reinvestment_efficiency(row))


def test_reinvestment_efficiency_nan_with_short_history() -> None:
    row = pd.Series(
        {
            "EBIT_History_3y": [200.0],
            "InvestedCapital_History_3y": [500.0],
        }
    )
    assert math.isnan(reinvestment_efficiency(row))


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def test_moat_score_returns_finite_0_100() -> None:
    df = pd.DataFrame(
        [
            {
                "Revenue": 200.0,
                "COGS": 170.0,
                "TotalAssets": 50.0,
                "ROIC": 0.20,
                "GrossMargin": 0.30,
                "ROIC_History_5y": [0.20, 0.22, 0.21, 0.20, 0.19],
                "OperatingMargin_History_5y": [0.15, 0.16, 0.15, 0.14, 0.15],
                "EBIT_History_3y": [50.0, 45.0, 40.0],
                "InvestedCapital_History_3y": [100.0, 90.0, 80.0],
                "Sector": "",
            },
            {
                "Revenue": 50.0,
                "COGS": 45.0,
                "TotalAssets": 500.0,
                "ROIC": 0.04,
                "GrossMargin": 0.10,
                "ROIC_History_5y": [0.05, -0.02, 0.10, 0.04, -0.01],
                "OperatingMargin_History_5y": [0.05, 0.02, 0.10, -0.01, 0.04],
                "EBIT_History_3y": [10.0, 5.0, 8.0],
                "InvestedCapital_History_3y": [200.0, 250.0, 280.0],  # IC rising though EBIT noisy
                "Sector": "",
            },
        ],
        index=["COSTCO_LIKE", "UTILITY_LIKE"],
    )
    score = moat_score(df)
    assert score.between(0.0, 100.0).all()
    assert score.loc["COSTCO_LIKE"] > score.loc["UTILITY_LIKE"]
