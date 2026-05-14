"""Tests for the computed-fallback layer."""

from __future__ import annotations

import math

from backend.app.services.market_data.computed_fallback import apply_computed_fallback


def test_interest_coverage_recomputed_when_nan() -> None:
    row = {"EBIT": 100.0, "InterestExpense": 25.0, "InterestCoverage": float("nan")}
    sources = {"InterestCoverage": "missing"}
    apply_computed_fallback(row, sources)
    assert row["InterestCoverage"] == 4.0
    assert sources["InterestCoverage"] == "computed"


def test_interest_coverage_left_alone_when_finite() -> None:
    row = {"EBIT": 100.0, "InterestExpense": 25.0, "InterestCoverage": 3.5}
    sources = {"InterestCoverage": "fmp"}
    apply_computed_fallback(row, sources)
    assert row["InterestCoverage"] == 3.5
    assert sources["InterestCoverage"] == "fmp"


def test_does_not_overwrite_existing_source() -> None:
    """Even if value is NaN, sources='fmp' must not be downgraded to 'computed'."""
    row = {"EBIT": 100.0, "InterestExpense": 25.0, "InterestCoverage": float("nan")}
    sources = {"InterestCoverage": "fmp"}  # source says fmp but value is NaN
    apply_computed_fallback(row, sources)
    # Value stays NaN, source stays "fmp" — do NOT overwrite legitimate provenance
    assert math.isnan(row["InterestCoverage"])
    assert sources["InterestCoverage"] == "fmp"


def test_fcf_recomputed_from_ocf_minus_capex() -> None:
    row = {"OperatingCashflow": 200.0, "CapEx": 60.0, "FCF": float("nan")}
    sources = {"FCF": "missing"}
    apply_computed_fallback(row, sources)
    assert row["FCF"] == 140.0


def test_revenue_growth_recomputed_from_prior_year() -> None:
    row = {"Revenue": 1100.0, "Revenue_PriorYear": 1000.0, "RevenueGrowth": float("nan")}
    sources = {"RevenueGrowth": "missing"}
    apply_computed_fallback(row, sources)
    assert math.isclose(row["RevenueGrowth"], 0.1, abs_tol=1e-9)


def test_roic_recomputed_from_ebit_equity_debt_cash() -> None:
    row = {
        "EBIT": 100.0,
        "TotalEquity": 400.0,
        "TotalDebt": 100.0,
        "Cash": 50.0,
        "ROIC": float("nan"),
    }
    sources = {"ROIC": "missing"}
    apply_computed_fallback(row, sources)
    # ROIC = EBIT*(1-0.25) / (Equity + Debt - Cash) = 75 / 450
    assert math.isclose(row["ROIC"], 75 / 450, abs_tol=1e-9)


def test_fcf_margin_after_fcf_recompute() -> None:
    """FCFMargin should compute when FCF is recomputed in the same pass."""
    row = {
        "OperatingCashflow": 200.0,
        "CapEx": 60.0,
        "FCF": float("nan"),
        "Revenue": 1000.0,
        "FCFMargin": float("nan"),
    }
    sources = {"FCF": "missing", "FCFMargin": "missing"}
    apply_computed_fallback(row, sources)
    assert row["FCF"] == 140.0
    assert math.isclose(row["FCFMargin"], 0.14, abs_tol=1e-9)
    assert sources["FCF"] == "computed"
    assert sources["FCFMargin"] == "computed"


def test_current_ratio_recomputed() -> None:
    row = {"CurrentAssets": 150.0, "CurrentLiabilities": 100.0, "CurrentRatio": float("nan")}
    sources = {"CurrentRatio": "missing"}
    apply_computed_fallback(row, sources)
    assert math.isclose(row["CurrentRatio"], 1.5)


def test_debt_equity_recomputed() -> None:
    row = {"TotalDebt": 200.0, "TotalEquity": 500.0, "DebtEquity": float("nan")}
    sources = {"DebtEquity": "missing"}
    apply_computed_fallback(row, sources)
    assert math.isclose(row["DebtEquity"], 0.4)


def test_nothing_set_when_inputs_missing() -> None:
    row = {"EBIT": float("nan"), "InterestExpense": 10.0, "InterestCoverage": float("nan")}
    sources = {"InterestCoverage": "missing"}
    apply_computed_fallback(row, sources)
    assert math.isnan(row["InterestCoverage"])
    assert sources["InterestCoverage"] == "missing"


def test_idempotent_when_rerun() -> None:
    row = {"EBIT": 100.0, "InterestExpense": 25.0, "InterestCoverage": float("nan")}
    sources = {"InterestCoverage": "missing"}
    apply_computed_fallback(row, sources)
    apply_computed_fallback(row, sources)  # second call must be a no-op
    assert row["InterestCoverage"] == 4.0
    assert sources["InterestCoverage"] == "computed"
