"""Unit tests for the backtest metrics library."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.app.services.backtest.metrics import (
    alpha_beta,
    cagr,
    hit_rate,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    total_return,
)


def _equity_from_returns(rets: np.ndarray, start: pd.Timestamp, initial: float = 100.0) -> pd.Series:
    days = pd.bdate_range(start=start, periods=len(rets) + 1)
    eq = initial * np.cumprod(1 + np.insert(rets, 0, 0.0))
    return pd.Series(eq, index=days)


# ──────────────────────────────────────────────────────────────────────────────
# total_return
# ──────────────────────────────────────────────────────────────────────────────


def test_total_return_basic():
    eq = pd.Series([100, 110, 120, 121])
    assert math.isclose(total_return(eq), 0.21, rel_tol=1e-9)


def test_total_return_short_input():
    assert math.isnan(total_return(pd.Series([100])))
    assert math.isnan(total_return(pd.Series(dtype=float)))


def test_total_return_zero_initial():
    assert math.isnan(total_return(pd.Series([0, 100])))


# ──────────────────────────────────────────────────────────────────────────────
# cagr
# ──────────────────────────────────────────────────────────────────────────────


def test_cagr_one_year_doubling():
    """100 -> 200 over 365 calendar days -> 100% CAGR."""
    eq = pd.Series(
        [100, 200],
        index=[pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31")],
    )
    assert cagr(eq) == pytest.approx(1.0, rel=0.02)


def test_cagr_two_years_doubling():
    """100 -> 200 over 2 years -> sqrt(2) - 1 ≈ 41.4%."""
    eq = pd.Series(
        [100, 200],
        index=[pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")],
    )
    assert cagr(eq) == pytest.approx(math.sqrt(2) - 1, abs=0.01)


def test_cagr_short_input():
    assert math.isnan(cagr(pd.Series(dtype=float)))


# ──────────────────────────────────────────────────────────────────────────────
# sharpe_ratio
# ──────────────────────────────────────────────────────────────────────────────


def test_sharpe_short_returns_nan():
    """Series shorter than 2 samples -> nan."""
    assert math.isnan(sharpe_ratio(pd.Series(dtype=float)))
    assert math.isnan(sharpe_ratio(pd.Series([0.01])))


def test_sharpe_positive_for_positive_excess_returns():
    rng = np.random.default_rng(42)
    rets = pd.Series(rng.normal(0.0008, 0.01, 252))
    sr = sharpe_ratio(rets, rf=0.03)
    assert sr > 0


# ──────────────────────────────────────────────────────────────────────────────
# max_drawdown
# ──────────────────────────────────────────────────────────────────────────────


def test_max_drawdown_simple():
    eq = pd.Series([100, 110, 90, 105])
    # Running max = [100, 110, 110, 110], dd = [0, 0, -0.18, -0.045]
    assert max_drawdown(eq) == pytest.approx(-0.1818, abs=1e-3)


def test_max_drawdown_monotone_increasing():
    eq = pd.Series([100, 110, 120, 130])
    assert max_drawdown(eq) == pytest.approx(0.0, abs=1e-9)


def test_max_drawdown_short_input():
    assert math.isnan(max_drawdown(pd.Series(dtype=float)))


# ──────────────────────────────────────────────────────────────────────────────
# information_ratio
# ──────────────────────────────────────────────────────────────────────────────


def test_information_ratio_zero_when_equal():
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.001, 0.01, 252))
    # IR(rets, rets) -> 0 (active = 0).
    ir = information_ratio(rets, rets)
    assert math.isnan(ir) or abs(ir) < 1e-6


def test_information_ratio_positive_for_outperformer():
    rng = np.random.default_rng(7)
    bench = pd.Series(rng.normal(0.0003, 0.01, 252))
    strat = bench + 0.0005  # +5 bp/day excess
    ir = information_ratio(strat, bench)
    assert ir > 1.0  # very high IR for synthetic constant alpha


# ──────────────────────────────────────────────────────────────────────────────
# hit_rate
# ──────────────────────────────────────────────────────────────────────────────


def test_hit_rate_half():
    rets = pd.Series([0.01, -0.01, 0.02, -0.02])
    assert hit_rate(rets) == 0.5


def test_hit_rate_all_positive():
    rets = pd.Series([0.01, 0.02, 0.03])
    assert hit_rate(rets) == 1.0


def test_hit_rate_empty():
    assert math.isnan(hit_rate(pd.Series(dtype=float)))


# ──────────────────────────────────────────────────────────────────────────────
# alpha_beta
# ──────────────────────────────────────────────────────────────────────────────


def test_alpha_beta_recovers_known_relationship():
    """Construct strat = 0.5 * bench + alpha and verify recovery."""
    rng = np.random.default_rng(123)
    bench = pd.Series(rng.normal(0.0004, 0.012, 1000))
    true_alpha_d = 0.0002  # 5% annualised
    true_beta = 0.5
    strat = true_beta * bench + true_alpha_d
    alpha, beta = alpha_beta(strat, bench, rf=0.0)
    assert beta == pytest.approx(true_beta, abs=0.05)
    assert alpha == pytest.approx(true_alpha_d * 252, abs=0.02)


def test_alpha_beta_short_input_returns_nan():
    a, b = alpha_beta(pd.Series([0.01]), pd.Series([0.01]))
    assert math.isnan(a) and math.isnan(b)
