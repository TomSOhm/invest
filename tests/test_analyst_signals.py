"""Tests for src/analysis/analyst_signals.py — SUE + EPS-revision math.

Formulas follow the Phase 0 financial review:
- SUE excludes the current quarter from the stdev denominator (Bernard-Thomas 1989).
- SUE uses dollar surprises (eps_actual - eps_estimate), not surprisePercent.
- Sample stdev (ddof=1).
- Min 6 quarters required for a valid SUE.
- EPS revision % = (current - past) / abs(past).
"""
from __future__ import annotations

import math

import pytest

from src.analysis.analyst_signals import (
    compute_eps_revision_pct_from_trend,
    compute_sue_from_history,
    earnings_surprise_latest,
    parse_recommendations_summary,
)


# ---------------------------------------------------------------------------
# compute_sue_from_history
# ---------------------------------------------------------------------------


def test_compute_sue_basic_8_quarters() -> None:
    """SUE = surprises[0] / stdev(surprises[1:], ddof=1)."""
    history = [
        {"eps_actual": 2.10, "eps_estimate": 2.00},  # current quarter
        {"eps_actual": 1.95, "eps_estimate": 1.90},
        {"eps_actual": 1.80, "eps_estimate": 1.85},
        {"eps_actual": 1.70, "eps_estimate": 1.65},
        {"eps_actual": 1.60, "eps_estimate": 1.55},
        {"eps_actual": 1.50, "eps_estimate": 1.55},
        {"eps_actual": 1.40, "eps_estimate": 1.35},
        {"eps_actual": 1.30, "eps_estimate": 1.30},
    ]
    sue = compute_sue_from_history(history)
    assert sue is not None
    # Surprises[1:] = [0.05, -0.05, 0.05, 0.05, -0.05, 0.05, 0]
    # stdev(ddof=1) ≈ 0.041; SUE = 0.10 / 0.041 ≈ 2.43
    assert 1.5 < sue < 3.5


def test_compute_sue_returns_none_when_under_six_quarters() -> None:
    """Phase 0 review: require minimum 6 quarters."""
    assert compute_sue_from_history([]) is None
    history = [
        {"eps_actual": 2.10, "eps_estimate": 2.00},
        {"eps_actual": 1.95, "eps_estimate": 1.90},
        {"eps_actual": 1.80, "eps_estimate": 1.85},
        {"eps_actual": 1.70, "eps_estimate": 1.65},
        {"eps_actual": 1.60, "eps_estimate": 1.55},  # only 5 rows
    ]
    assert compute_sue_from_history(history) is None


def test_compute_sue_returns_none_when_all_surprises_equal() -> None:
    """sigma == 0 → undefined SUE; return None."""
    history = [{"eps_actual": 2.0, "eps_estimate": 1.5} for _ in range(8)]
    assert compute_sue_from_history(history) is None


def test_compute_sue_excludes_current_quarter_from_sigma() -> None:
    """Bernard-Thomas: current quarter must NOT be in the σ denominator."""
    # If we include current in σ, a single huge current surprise inflates σ.
    # By excluding it, σ stays low and SUE is large.
    history = [
        {"eps_actual": 5.00, "eps_estimate": 1.00},  # huge surprise in current
        {"eps_actual": 1.01, "eps_estimate": 1.00},
        {"eps_actual": 1.00, "eps_estimate": 1.01},
        {"eps_actual": 1.02, "eps_estimate": 1.00},
        {"eps_actual": 0.99, "eps_estimate": 1.00},
        {"eps_actual": 1.01, "eps_estimate": 1.00},
    ]
    sue = compute_sue_from_history(history)
    assert sue is not None
    # σ on the 5 small surprises is tiny; numerator is 4.0; SUE should be very large
    assert sue > 100


# ---------------------------------------------------------------------------
# compute_eps_revision_pct_from_trend
# ---------------------------------------------------------------------------


def test_eps_revision_pct_30d() -> None:
    trend = [
        {"period": "0q", "current": 5.20, "n_minus_30d": 5.00, "n_minus_90d": 4.80}
    ]
    rev_30 = compute_eps_revision_pct_from_trend(trend, days=30)
    assert rev_30 is not None
    assert math.isclose(rev_30, 0.04, abs_tol=1e-6)


def test_eps_revision_pct_90d() -> None:
    trend = [
        {"period": "0q", "current": 5.20, "n_minus_30d": 5.00, "n_minus_90d": 4.80}
    ]
    rev_90 = compute_eps_revision_pct_from_trend(trend, days=90)
    assert rev_90 is not None
    assert math.isclose(rev_90, (5.20 - 4.80) / 4.80, abs_tol=1e-6)


def test_eps_revision_pct_negative_estimate_uses_abs() -> None:
    """Sign must be correct when prior estimate is negative (loss)."""
    trend = [
        {"period": "0q", "current": -0.30, "n_minus_30d": -0.50, "n_minus_90d": -0.40}
    ]
    rev_30 = compute_eps_revision_pct_from_trend(trend, days=30)
    # Estimate raised from -0.50 to -0.30 → bullish → positive %
    assert rev_30 is not None
    assert rev_30 > 0


def test_eps_revision_pct_none_when_no_data() -> None:
    assert compute_eps_revision_pct_from_trend([], days=30) is None
    assert (
        compute_eps_revision_pct_from_trend(
            [{"period": "0q", "current": 5.0, "n_minus_30d": 0}], days=30
        )
        is None
    )


# ---------------------------------------------------------------------------
# parse_recommendations_summary
# ---------------------------------------------------------------------------


def test_parse_recommendations_summary() -> None:
    rec = {"strong_buy": 12, "buy": 20, "hold": 8, "sell": 2, "strong_sell": 0}
    parsed = parse_recommendations_summary(rec)
    assert parsed == rec


def test_parse_recommendations_summary_empty() -> None:
    assert parse_recommendations_summary(None) == {
        "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0,
    }


# ---------------------------------------------------------------------------
# earnings_surprise_latest
# ---------------------------------------------------------------------------


def test_earnings_surprise_latest() -> None:
    history = [
        {"date": "2024-12-31", "surprise_pct": 5.0},
        {"date": "2024-09-30", "surprise_pct": 2.6},
    ]
    assert earnings_surprise_latest(history) == 5.0


def test_earnings_surprise_latest_empty() -> None:
    assert earnings_surprise_latest([]) is None


def test_compute_sue_skips_invalid_eps_rows() -> None:
    """Rows with non-numeric eps_actual/estimate are skipped, not crashed on."""
    history = [
        {"eps_actual": "N/A", "eps_estimate": 2.00},
        {"eps_actual": float("nan"), "eps_estimate": 1.90},
        {"eps_actual": 1.80, "eps_estimate": 1.85},
        {"eps_actual": 1.70, "eps_estimate": 1.65},
        {"eps_actual": 1.60, "eps_estimate": 1.55},
        {"eps_actual": 1.50, "eps_estimate": 1.55},
        {"eps_actual": 1.40, "eps_estimate": 1.35},
        {"eps_actual": 1.30, "eps_estimate": 1.30},
    ]
    sue = compute_sue_from_history(history)
    # 6 valid rows remain → SUE computed
    assert sue is not None


def test_parse_recommendations_summary_skips_non_numeric_values() -> None:
    """String / NaN values must not crash; corresponding keys stay at default 0."""
    rec = {"buy": "5", "hold": float("nan"), "strong_buy": 10}
    parsed = parse_recommendations_summary(rec)
    assert parsed["buy"] == 0  # string skipped
    assert parsed["hold"] == 0  # NaN skipped
    assert parsed["strong_buy"] == 10
    assert parsed["sell"] == 0
    assert parsed["strong_sell"] == 0
