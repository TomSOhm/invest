"""Unit tests for src.analysis.risk_metrics.

Coverage:
    - realized_volatility_1y on synthetic GBM-like series with known sigma.
    - max_drawdown_3y on synthetic series with engineered -50% drawdown.
    - beta_5y_monthly on perfectly correlated synthetic series → ~1.0.
    - net_debt_to_ebitda + interest_coverage_real basic checks.
    - risk_score_real falls back to row-only signals when no price map given.
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

from src.analysis.risk_metrics import (  # noqa: E402
    beta_5y_monthly,
    interest_coverage_real,
    max_drawdown_3y,
    net_debt_to_ebitda,
    realized_volatility_1y,
    risk_score_real,
)

# ---------------------------------------------------------------------------
# Realized volatility
# ---------------------------------------------------------------------------


def test_realized_vol_recovers_known_sigma() -> None:
    """Generate 252 daily log-returns with sigma=0.01 → annualised ≈ 0.1587."""
    rng = np.random.default_rng(42)
    daily_log_ret = rng.normal(loc=0.0, scale=0.01, size=252)
    prices = np.exp(np.cumsum(daily_log_ret)) * 100.0
    dates = pd.date_range("2024-01-01", periods=252, freq="B")
    df = pd.DataFrame({"Date": dates, "Close": prices})

    val = realized_volatility_1y(df)
    # Expected: 0.01 * sqrt(252) ≈ 0.1587. Allow 30% relative tolerance for sample noise.
    expected = 0.01 * math.sqrt(252)
    assert math.isclose(val, expected, rel_tol=0.30), f"vol={val:.4f}, expected~{expected:.4f}"


def test_realized_vol_nan_on_short_series() -> None:
    df = pd.DataFrame(
        {"Date": pd.date_range("2024-01-01", periods=5, freq="D"), "Close": [100.0, 101.0, 102.0, 99.0, 101.0]}
    )
    assert math.isnan(realized_volatility_1y(df))


# ---------------------------------------------------------------------------
# Max drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown_recovers_minus_50() -> None:
    """Engineered series: peaks at 100, troughs at 50 → drawdown -50%."""
    closes = [
        80.0,
        90.0,
        100.0,  # ascend to 100
        90.0,
        80.0,
        70.0,
        60.0,
        50.0,  # crash to 50  → DD = -0.5
        55.0,
        60.0,
        70.0,  # partial recovery
    ]
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"Date": dates, "Close": closes})
    val = max_drawdown_3y(df)
    assert math.isclose(val, -0.5, abs_tol=1e-3), f"expected -0.5, got {val}"


def test_max_drawdown_zero_for_monotonic_series() -> None:
    closes = list(range(100, 200))
    dates = pd.date_range("2022-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"Date": dates, "Close": closes})
    val = max_drawdown_3y(df)
    assert math.isclose(val, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Beta
# ---------------------------------------------------------------------------


def test_beta_perfect_correlation_is_one() -> None:
    """Stock prices == market prices for 5y → beta = 1.0."""
    dates = pd.date_range("2020-01-01", periods=60 * 21, freq="B")  # ~5y of business days
    rng = np.random.default_rng(7)
    daily_log_ret = rng.normal(loc=0.0, scale=0.005, size=len(dates))
    prices = np.exp(np.cumsum(daily_log_ret)) * 100.0
    stock_df = pd.DataFrame({"Date": dates, "Close": prices})
    market_df = pd.DataFrame({"Date": dates, "Close": prices.copy()})

    beta = beta_5y_monthly(stock_df, market_df)
    assert math.isclose(beta, 1.0, abs_tol=1e-3), f"beta={beta}"


def test_beta_double_market_movement_is_two() -> None:
    """Stock returns = 2 × market returns → beta = 2.0."""
    dates = pd.date_range("2020-01-01", periods=60 * 21, freq="B")
    rng = np.random.default_rng(13)
    market_log_ret = rng.normal(loc=0.0, scale=0.005, size=len(dates))
    market_prices = np.exp(np.cumsum(market_log_ret)) * 100.0
    stock_log_ret = 2.0 * market_log_ret
    stock_prices = np.exp(np.cumsum(stock_log_ret)) * 100.0

    stock_df = pd.DataFrame({"Date": dates, "Close": stock_prices})
    market_df = pd.DataFrame({"Date": dates, "Close": market_prices})
    beta = beta_5y_monthly(stock_df, market_df)
    # Some leakage from log-vs-arithmetic returns; tolerate ±0.2
    assert 1.7 < beta < 2.3, f"beta={beta}"


def test_beta_nan_on_empty_series() -> None:
    empty = pd.DataFrame()
    other = pd.DataFrame({"Date": [pd.Timestamp("2024-01-01")], "Close": [100.0]})
    assert math.isnan(beta_5y_monthly(empty, other))


# ---------------------------------------------------------------------------
# Row-derived signals
# ---------------------------------------------------------------------------


def test_net_debt_to_ebitda_basic() -> None:
    row = pd.Series({"TotalDebt": 200.0, "Cash": 50.0, "EBITDA": 100.0})
    assert math.isclose(net_debt_to_ebitda(row), 1.5, rel_tol=1e-9)


def test_net_debt_to_ebitda_nan_with_zero_ebitda() -> None:
    row = pd.Series({"TotalDebt": 200.0, "Cash": 50.0, "EBITDA": 0.0})
    assert math.isnan(net_debt_to_ebitda(row))


def test_interest_coverage_uses_existing_column() -> None:
    row = pd.Series({"InterestCoverage": 8.5})
    assert math.isclose(interest_coverage_real(row), 8.5, rel_tol=1e-9)


def test_interest_coverage_falls_back_to_ebit_and_interest_expense() -> None:
    row = pd.Series({"EBIT": 150.0, "InterestExpense": 30.0})
    assert math.isclose(interest_coverage_real(row), 5.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def test_risk_score_real_works_without_price_history() -> None:
    """When price_history_map is None, the aggregator must still return scores."""
    df = pd.DataFrame(
        [
            {
                "TotalDebt": 100.0,
                "Cash": 50.0,
                "EBITDA": 200.0,
                "InterestCoverage": 12.0,
                "Altman_Z": 4.5,
                "Sector": "",
            },
            {"TotalDebt": 800.0, "Cash": 50.0, "EBITDA": 100.0, "InterestCoverage": 1.5, "Altman_Z": 0.8, "Sector": ""},
        ],
        index=["SAFE", "DISTRESS"],
    )
    score = risk_score_real(df, price_history_map=None)
    assert score.between(0.0, 100.0).all()
    assert score.loc["SAFE"] > score.loc["DISTRESS"]


def test_risk_score_real_with_price_history_map() -> None:
    """Smoke test: providing a price map shouldn't break and should still produce 0..100."""
    dates = pd.date_range("2022-01-01", periods=400, freq="B")
    rng = np.random.default_rng(0)
    safe_prices = np.exp(np.cumsum(rng.normal(0.0001, 0.005, size=len(dates)))) * 100.0
    risky_prices = np.exp(np.cumsum(rng.normal(0.0001, 0.025, size=len(dates)))) * 100.0
    market_prices = np.exp(np.cumsum(rng.normal(0.0001, 0.008, size=len(dates)))) * 100.0

    price_map = {
        "SAFE": pd.DataFrame({"Date": dates, "Close": safe_prices}),
        "DISTRESS": pd.DataFrame({"Date": dates, "Close": risky_prices}),
        "_market": pd.DataFrame({"Date": dates, "Close": market_prices}),
    }
    df = pd.DataFrame(
        [
            {
                "TotalDebt": 100.0,
                "Cash": 50.0,
                "EBITDA": 200.0,
                "InterestCoverage": 12.0,
                "Altman_Z": 4.5,
                "Sector": "",
            },
            {"TotalDebt": 800.0, "Cash": 50.0, "EBITDA": 100.0, "InterestCoverage": 1.5, "Altman_Z": 0.8, "Sector": ""},
        ],
        index=["SAFE", "DISTRESS"],
    )
    score = risk_score_real(df, price_history_map=price_map)
    assert score.between(0.0, 100.0).all()
