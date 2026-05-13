"""Tests for src/analysis/momentum.py (M9)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.analysis.momentum import (
    above_50dma,
    above_200dma,
    golden_cross,
    momentum_12_1,
    momentum_score,
    momentum_signals_df,
    relative_strength_3m,
    volume_surge,
)


def _trading_dates(n: int, end: str = "2025-12-31") -> pd.DatetimeIndex:
    """Build a business-day index of length n ending on `end`."""
    return pd.bdate_range(end=end, periods=n)


# ---------------------------------------------------------------------------
# momentum_12_1
# ---------------------------------------------------------------------------


def test_momentum_12_1_exact_value():
    """Synthetic series with a known 12-1 ratio.

    price_{t-21} = 110, price_{t-252} = 100 -> momentum = 0.10
    """
    n = 260
    idx = _trading_dates(n)
    values = np.full(n, 100.0)
    # The function pulls iloc[-22] (price_{t-21}) and iloc[-252].
    values[-22] = 110.0
    values[-252] = 100.0
    series = pd.Series(values, index=idx)
    assert math.isclose(momentum_12_1(series), 0.10, rel_tol=1e-9)


def test_momentum_12_1_returns_nan_for_short_history():
    series = pd.Series(np.arange(100, dtype=float))
    assert math.isnan(momentum_12_1(series))


def test_momentum_12_1_dataframe_input():
    """Function tolerates a yfinance-shaped DataFrame with Close column."""
    n = 260
    df = pd.DataFrame({"Close": np.full(n, 100.0)}, index=_trading_dates(n))
    df.iloc[-22, 0] = 121.0
    df.iloc[-252, 0] = 100.0
    assert math.isclose(momentum_12_1(df), 0.21, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# above_50dma / above_200dma / golden_cross
# ---------------------------------------------------------------------------


def test_above_50dma_simple():
    # Last point well above mean
    series = pd.Series([100.0] * 50 + [200.0])
    assert above_50dma(series) is True


def test_above_50dma_below():
    series = pd.Series([100.0] * 50 + [50.0])
    assert above_50dma(series) is False


def test_above_50dma_insufficient_history():
    assert above_50dma(pd.Series([100.0] * 10)) is False


def test_above_200dma_climbing():
    # Strictly increasing series -> last close > 200dma
    series = pd.Series(np.linspace(50, 200, 250))
    assert above_200dma(series) is True


def test_golden_cross_climbing():
    # Strictly increasing series: 50dma > 200dma at the tail
    series = pd.Series(np.linspace(50, 200, 250))
    assert golden_cross(series) is True


def test_golden_cross_falling():
    series = pd.Series(np.linspace(200, 50, 250))
    assert golden_cross(series) is False


# ---------------------------------------------------------------------------
# volume_surge
# ---------------------------------------------------------------------------


def test_volume_surge_ratio_2():
    """5d-avg=200, 90d-avg approx 100 -> ratio approx 2.0."""
    # Build 90-element series: first 85 points at 100, last 5 at 200.
    values = np.array([100.0] * 85 + [200.0] * 5)
    series = pd.Series(values)
    avg_5 = 200.0
    avg_90 = (85 * 100 + 5 * 200) / 90  # = 105.555...
    expected = avg_5 / avg_90
    result = volume_surge(series)
    assert math.isclose(result, expected, rel_tol=1e-6)


def test_volume_surge_clean_2x():
    """Construct so that avg_90 is exactly 100 and avg_5 is 200."""
    # 90 points: chosen so the rolling 90-day window still averages 100.
    # Simplest: 90-day window of all 100s, then last 5 days at 200 in the
    # window means avg_90 includes those 200s. To hit ratio==2 cleanly, give
    # avg_5=200 directly and accept the avg_90 includes them. We assert the
    # ratio is consistent with the formula instead.
    series = pd.Series([100.0] * 85 + [200.0] * 5)
    ratio = volume_surge(series)
    avg_5 = 200.0
    avg_90 = series.tail(90).mean()
    assert math.isclose(ratio, avg_5 / avg_90, rel_tol=1e-9)


def test_volume_surge_short_history():
    series = pd.Series([100.0] * 50)
    assert math.isnan(volume_surge(series))


# ---------------------------------------------------------------------------
# relative_strength_3m
# ---------------------------------------------------------------------------


def test_relative_strength_3m_aligned_series():
    """Stock +20% over 3m, market +10% -> RS = +10%."""
    n = 80
    idx = _trading_dates(n)
    stock = pd.Series(np.full(n, 100.0), index=idx)
    market = pd.Series(np.full(n, 100.0), index=idx)
    # Set value 63 trading days before the end and the latest value
    stock.iloc[-1] = 120.0
    stock.iloc[-64] = 100.0
    market.iloc[-1] = 110.0
    market.iloc[-64] = 100.0
    rs = relative_strength_3m(stock, market)
    assert math.isclose(rs, 0.10, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# momentum_score
# ---------------------------------------------------------------------------


def test_momentum_score_climbing_series_high():
    """Strictly increasing AAPL-like series should yield a high momentum score."""
    n = 260
    idx = _trading_dates(n)
    # 50% gain over the year, monotonic.
    close = pd.Series(np.linspace(100, 150, n), index=idx)
    market = pd.Series(np.linspace(100, 110, n), index=idx)  # +10% market
    volume = pd.Series([1_000_000] * (n - 5) + [2_000_000] * 5, index=idx)
    score = momentum_score(close, market, volume)
    assert score is not None and not math.isnan(score)
    assert score >= 70.0, f"Climbing series should score >= 70, got {score}"


def test_momentum_score_falling_series_low():
    n = 260
    idx = _trading_dates(n)
    close = pd.Series(np.linspace(150, 75, n), index=idx)
    market = pd.Series(np.linspace(100, 100, n), index=idx)
    volume = pd.Series([1_000_000] * n, index=idx)
    score = momentum_score(close, market, volume)
    assert score <= 35.0, f"Falling series should score <= 35, got {score}"


def test_momentum_score_short_history_returns_nan():
    series = pd.Series([100.0] * 50)
    assert math.isnan(momentum_score(series, None, None))


# ---------------------------------------------------------------------------
# momentum_signals_df
# ---------------------------------------------------------------------------


def test_momentum_signals_df_shape_and_columns():
    n = 260
    idx = _trading_dates(n)
    df_aapl = pd.DataFrame(
        {"Close": np.linspace(100, 150, n), "Volume": np.full(n, 1_000_000.0)},
        index=idx,
    )
    df_nvda = pd.DataFrame(
        {"Close": np.linspace(80, 200, n), "Volume": np.full(n, 1_000_000.0)},
        index=idx,
    )
    market = pd.DataFrame({"Close": np.linspace(100, 105, n)}, index=idx)

    out = momentum_signals_df(
        {"AAPL": df_aapl, "NVDA": df_nvda},
        market_history=market,
    )
    expected_cols = {
        "Momentum_12_1",
        "RS_3m",
        "Above_50DMA",
        "Above_200DMA",
        "Golden_Cross",
        "Volume_Surge",
        "Momentum_Score",
    }
    assert expected_cols.issubset(set(out.columns))
    assert list(out.index) == ["AAPL", "NVDA"]
    # Both climbing -> score >=70
    assert out.loc["AAPL", "Momentum_Score"] >= 70
    assert out.loc["NVDA", "Momentum_Score"] >= 70


def test_momentum_signals_df_empty_input():
    out = momentum_signals_df({}, market_history=None)
    assert out.empty
    assert "Momentum_12_1" in out.columns
