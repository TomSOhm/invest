"""
Invest Solo -- Backtest performance metrics (M12).

Pure-function metric library operating on pandas Series.

All inputs are assumed to be aligned (same DatetimeIndex). Functions return
``float('nan')`` when input is too short / degenerate rather than raising.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

# Trading-day annualisation constant. We assume daily-resolution returns
# throughout the backtest -- for monthly/quarterly series the caller must
# pre-resample.
_TRADING_DAYS_PER_YEAR = 252


def _to_returns(equity_curve: pd.Series) -> pd.Series:
    """Convert an equity curve into period-over-period simple returns."""
    if equity_curve is None or len(equity_curve) < 2:
        return pd.Series(dtype=float)
    return equity_curve.pct_change().dropna()


def total_return(equity_curve: pd.Series) -> float:
    """Compute total return as ``(final / initial) - 1``.

    Returns ``nan`` for series shorter than two points.
    """
    if equity_curve is None or len(equity_curve) < 2:
        return float("nan")
    initial = float(equity_curve.iloc[0])
    final = float(equity_curve.iloc[-1])
    if initial <= 0:
        return float("nan")
    return final / initial - 1.0


def cagr(equity_curve: pd.Series) -> float:
    """Compound Annual Growth Rate, derived from the equity curve.

    Uses calendar-day spacing between the first and last index timestamps.
    Returns ``nan`` for degenerate inputs (≤1 sample, ≤0 elapsed days).
    """
    if equity_curve is None or len(equity_curve) < 2:
        return float("nan")
    initial = float(equity_curve.iloc[0])
    final = float(equity_curve.iloc[-1])
    if initial <= 0 or final <= 0:
        return float("nan")
    start = pd.Timestamp(equity_curve.index[0])
    end = pd.Timestamp(equity_curve.index[-1])
    days = max((end - start).days, 1)
    years = days / 365.25
    if years <= 0:
        return float("nan")
    return (final / initial) ** (1.0 / years) - 1.0


def sharpe_ratio(returns: pd.Series, rf: float = 0.03) -> float:
    """Annualised Sharpe ratio of a daily-return series.

    Parameters
    ----------
    returns : pd.Series
        Periodic (daily) returns.
    rf : float, default 0.03
        Annualised risk-free rate. Converted to per-period via ``rf / 252``.
    """
    if returns is None or len(returns) < 2:
        return float("nan")
    # Use the std of the *raw* returns (rf is a constant shift and doesn't
    # change variance). Treat near-zero variance (flat equity) as undefined
    # to avoid divide-by-near-zero blow-ups in the report.
    raw_std = float(returns.std(ddof=1))
    if raw_std <= 1e-12 or not np.isfinite(raw_std):
        return float("nan")
    excess = returns - (rf / _TRADING_DAYS_PER_YEAR)
    return float(excess.mean() / raw_std) * np.sqrt(_TRADING_DAYS_PER_YEAR)


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum peak-to-trough drawdown of the equity curve.

    Returns a non-positive float (e.g. ``-0.23`` for a 23% drawdown). Returns
    ``nan`` for empty inputs and ``0.0`` for monotonically increasing curves.
    """
    if equity_curve is None or len(equity_curve) < 2:
        return float("nan")
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    return float(drawdown.min())


def information_ratio(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    """Information ratio = mean(active) / std(active), annualised.

    Active return = strategy − benchmark. Indices are aligned via inner join.
    """
    if strategy_returns is None or benchmark_returns is None:
        return float("nan")
    aligned = pd.concat(
        [strategy_returns, benchmark_returns], axis=1, join="inner"
    ).dropna()
    if len(aligned) < 2:
        return float("nan")
    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    std = float(active.std(ddof=1))
    if std <= 1e-20 or not np.isfinite(std):
        return float("nan")
    return float(active.mean() / std) * np.sqrt(_TRADING_DAYS_PER_YEAR)


def hit_rate(returns: pd.Series) -> float:
    """Fraction of periods with strictly positive return.

    Returns ``nan`` for empty inputs.
    """
    if returns is None or len(returns) == 0:
        return float("nan")
    valid = returns.dropna()
    if len(valid) == 0:
        return float("nan")
    return float((valid > 0).mean())


def alpha_beta(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    rf: float = 0.03,
) -> Tuple[float, float]:
    """Annualised Jensen alpha and beta from CAPM regression.

    OLS on excess returns (over the per-period rf):

        (R_s - rf_d) = alpha_d + beta * (R_b - rf_d) + eps

    Returns
    -------
    (alpha_annualised, beta) : tuple[float, float]
        ``alpha_annualised`` = ``alpha_d * 252``. ``beta`` is dimensionless.
        Both are ``nan`` when the series is too short or degenerate.
    """
    if strategy_returns is None or benchmark_returns is None:
        return float("nan"), float("nan")
    aligned = pd.concat(
        [strategy_returns, benchmark_returns], axis=1, join="inner"
    ).dropna()
    if len(aligned) < 5:
        return float("nan"), float("nan")
    rf_d = rf / _TRADING_DAYS_PER_YEAR
    rs = aligned.iloc[:, 0] - rf_d
    rb = aligned.iloc[:, 1] - rf_d
    var_b = float(rb.var(ddof=1))
    if var_b <= 1e-20 or not np.isfinite(var_b):
        return float("nan"), float("nan")
    # Flat strategy (variance ≈ 0): the regression is meaningless. Returning
    # nan rather than a spurious -rf alpha keeps the report honest.
    if float(aligned.iloc[:, 0].var(ddof=1)) <= 1e-20:
        return float("nan"), float("nan")
    cov_sb = float(np.cov(rs, rb, ddof=1)[0, 1])
    beta = cov_sb / var_b
    alpha_d = float(rs.mean() - beta * rb.mean())
    alpha_annualised = alpha_d * _TRADING_DAYS_PER_YEAR
    return alpha_annualised, beta
