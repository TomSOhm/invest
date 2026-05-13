"""
Invest Solo -- Price Momentum Signals (M9)

Pure-pandas/numpy implementations of the momentum factors referenced in
METHODOLOGY_v2.md (ST/MT horizons). All inputs are daily price/volume series
indexed by date; all outputs are floats / bools / NaN.

The bulk variant ``momentum_signals_df`` produces the column block joined
back onto the scoring universe in ``score_universe`` (M9 hook -- see
src/analysis/scoring_engine.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADING_DAYS_YEAR = 252
TRADING_DAYS_MONTH = 21
TRADING_DAYS_3M = 63

# ---------------------------------------------------------------------------
# Single-series helpers
# ---------------------------------------------------------------------------


def _coerce_close_series(prices) -> pd.Series:
    """Accept Series or DataFrame and return a 1-D close-price Series.

    Tolerates the shape returned by ``yfinance.Ticker.history()`` (DataFrame
    with a ``Close`` column). Drops NaN rows so iloc-based indexing is safe.
    """
    if isinstance(prices, pd.DataFrame):
        for col in ("Close", "close", "Adj Close", "AdjClose"):
            if col in prices.columns:
                series = prices[col]
                break
        else:
            # Single-column DataFrame fallback
            series = prices.iloc[:, 0]
    else:
        series = prices
    series = pd.Series(series).dropna()
    return series


def momentum_12_1(prices) -> float:
    """Academic 12-1 momentum: 12-month return excluding the last month.

    Formula
    -------
        momentum = price_{t-21} / price_{t-252} - 1

    Returns NaN when fewer than ``TRADING_DAYS_YEAR`` observations are
    available or either endpoint is non-finite / non-positive.
    """
    series = _coerce_close_series(prices)
    if len(series) < TRADING_DAYS_YEAR:
        return float("nan")

    p_recent = series.iloc[-TRADING_DAYS_MONTH - 1]  # ~21 trading days ago
    p_old = series.iloc[-TRADING_DAYS_YEAR]  # ~252 trading days ago

    if not (np.isfinite(p_recent) and np.isfinite(p_old) and p_old > 0):
        return float("nan")
    return float(p_recent / p_old - 1.0)


def relative_strength_3m(prices, market) -> float:
    """3-month return of the stock minus the same window for the market index.

    Both series are date-aligned (intersect indexes) before the return is
    computed; if fewer than 63 aligned observations remain the result is NaN.
    """
    s_stock = _coerce_close_series(prices)
    s_mkt = _coerce_close_series(market)

    # Align by index (intersection)
    aligned = pd.concat([s_stock, s_mkt], axis=1, join="inner").dropna()
    if len(aligned) < TRADING_DAYS_3M + 1:
        return float("nan")

    stock = aligned.iloc[:, 0]
    mkt = aligned.iloc[:, 1]

    s_now = stock.iloc[-1]
    s_then = stock.iloc[-TRADING_DAYS_3M - 1]
    m_now = mkt.iloc[-1]
    m_then = mkt.iloc[-TRADING_DAYS_3M - 1]

    if not all(np.isfinite(x) for x in (s_now, s_then, m_now, m_then)):
        return float("nan")
    if s_then <= 0 or m_then <= 0:
        return float("nan")

    stock_ret = s_now / s_then - 1.0
    mkt_ret = m_now / m_then - 1.0
    return float(stock_ret - mkt_ret)


def above_50dma(prices) -> bool:
    """Latest close strictly greater than the 50-day rolling mean.

    NaN rolling mean (insufficient history) returns False rather than NaN so
    the caller doesn't have to mix bools and NaNs in the screener row.
    """
    series = _coerce_close_series(prices)
    if len(series) < 50:
        return False
    ma = series.rolling(window=50).mean().iloc[-1]
    last = series.iloc[-1]
    if not (np.isfinite(ma) and np.isfinite(last)):
        return False
    return bool(last > ma)


def above_200dma(prices) -> bool:
    """Latest close strictly greater than the 200-day rolling mean."""
    series = _coerce_close_series(prices)
    if len(series) < 200:
        return False
    ma = series.rolling(window=200).mean().iloc[-1]
    last = series.iloc[-1]
    if not (np.isfinite(ma) and np.isfinite(last)):
        return False
    return bool(last > ma)


def golden_cross(prices) -> bool:
    """50dma > 200dma -- bullish trend signal.

    Requires at least 200 valid observations.
    """
    series = _coerce_close_series(prices)
    if len(series) < 200:
        return False
    ma50 = series.rolling(window=50).mean().iloc[-1]
    ma200 = series.rolling(window=200).mean().iloc[-1]
    if not (np.isfinite(ma50) and np.isfinite(ma200)):
        return False
    return bool(ma50 > ma200)


def volume_surge(volume) -> float:
    """Ratio of 5-day to 90-day average volume.

    Returns NaN when fewer than 90 valid observations are available or the
    90-day average is zero. Values >1.3 are commonly read as a "surge".
    """
    if isinstance(volume, pd.DataFrame):
        if "Volume" in volume.columns:
            v = volume["Volume"]
        else:
            v = volume.iloc[:, 0]
    else:
        v = volume
    v = pd.Series(v).dropna()
    if len(v) < 90:
        return float("nan")

    avg_5 = v.iloc[-5:].mean()
    avg_90 = v.iloc[-90:].mean()
    if not (np.isfinite(avg_5) and np.isfinite(avg_90)) or avg_90 == 0:
        return float("nan")
    return float(avg_5 / avg_90)


def momentum_score(prices, market, volume) -> float:
    """0-100 composite momentum score.

    Sub-signal weighting (sums to 100):
        - momentum_12_1 mapped to 0-100 with linear bins:        30 pts
            < -0.10 -> 0, -0.10..0.10 linear, > 0.30 -> 100
        - relative_strength_3m -> 0-100:                          20 pts
            < -0.10 -> 0, -0.10..0.10 linear, > 0.20 -> 100
        - above_50dma:                                            15 pts
        - above_200dma:                                           15 pts
        - golden_cross:                                           10 pts
        - volume_surge clipped to [0, 2] mapped to 0-100:         10 pts

    Returns NaN when momentum_12_1 is NaN (insufficient history is the
    dominant failure mode -- without 12-month history nothing else gives
    a defensible composite).
    """
    m12 = momentum_12_1(prices)
    if not np.isfinite(m12):
        return float("nan")

    rs = relative_strength_3m(prices, market) if market is not None else float("nan")
    a50 = above_50dma(prices)
    a200 = above_200dma(prices)
    gx = golden_cross(prices)
    vs = volume_surge(volume) if volume is not None else float("nan")

    def _bin(value: float, low: float, high: float) -> float:
        if not np.isfinite(value):
            return 50.0
        if value <= low:
            return 0.0
        if value >= high:
            return 100.0
        return 100.0 * (value - low) / (high - low)

    score = 0.0
    score += 0.30 * _bin(m12, -0.10, 0.30)
    score += 0.20 * _bin(rs, -0.10, 0.20)
    score += 15.0 if a50 else 0.0
    score += 15.0 if a200 else 0.0
    score += 10.0 if gx else 0.0
    if np.isfinite(vs):
        # vs in [0, 2] -> 0..100
        clipped = max(0.0, min(2.0, vs))
        score += 0.10 * (clipped / 2.0) * 100.0
    else:
        score += 5.0  # neutral fill if no volume

    return float(round(score, 2))


# ---------------------------------------------------------------------------
# Bulk DataFrame variant for screener integration
# ---------------------------------------------------------------------------


def _extract_close_volume(df: pd.DataFrame) -> tuple:
    """Return (close, volume) Series from a price-history DataFrame.

    Handles both a date-indexed DataFrame and one with a ``Date`` column.
    Missing volume yields a NaN series of the same length.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    if "Date" in df.columns:
        df = df.set_index(pd.to_datetime(df["Date"], errors="coerce")).drop(columns=["Date"])
    close_col = next((c for c in ("Close", "close", "Adj Close", "AdjClose") if c in df.columns), None)
    if close_col is None:
        close_col = df.columns[0]
    close = df[close_col]

    vol_col = next((c for c in ("Volume", "volume") if c in df.columns), None)
    if vol_col:
        volume = df[vol_col]
    else:
        volume = pd.Series([np.nan] * len(df), index=df.index)
    return close, volume


def momentum_signals_df(
    price_history_map: dict[str, pd.DataFrame],
    market_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute the momentum signal block for a universe.

    Parameters
    ----------
    price_history_map:
        ``{ticker: price_history_df}``. The DataFrames must contain a Close
        column; Volume optional.
    market_history:
        Benchmark price history (e.g. ``^FCHI`` for PEA, ``^GSPC`` for global).
        When None, ``RS_3m`` and the relative-strength contribution to
        ``Momentum_Score`` fall back to NaN/neutral.

    Returns
    -------
    DataFrame indexed by ticker with columns:
        Momentum_12_1, RS_3m, Above_50DMA, Above_200DMA, Golden_Cross,
        Volume_Surge, Momentum_Score
    """
    market_close: pd.Series | None
    if market_history is not None and not market_history.empty:
        market_close, _ = _extract_close_volume(market_history)
    else:
        market_close = None

    rows = []
    for ticker, df in price_history_map.items():
        close, volume = _extract_close_volume(df)
        rows.append(
            {
                "Ticker": ticker,
                "Momentum_12_1": momentum_12_1(close),
                "RS_3m": relative_strength_3m(close, market_close) if market_close is not None else float("nan"),
                "Above_50DMA": above_50dma(close),
                "Above_200DMA": above_200dma(close),
                "Golden_Cross": golden_cross(close),
                "Volume_Surge": volume_surge(volume),
                "Momentum_Score": momentum_score(close, market_close, volume),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "Momentum_12_1",
                "RS_3m",
                "Above_50DMA",
                "Above_200DMA",
                "Golden_Cross",
                "Volume_Surge",
                "Momentum_Score",
            ]
        )
    return pd.DataFrame(rows).set_index("Ticker")
