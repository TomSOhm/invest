"""
Risk Metrics Module (M5)
========================
Pure-function library replacing the anemic legacy ``risk_score`` (Beta +
InterestCoverage only) with a real risk composite.

Implemented metrics (all NaN-safe):
    - realized_volatility_1y(price_history): annualised stddev of daily log-returns.
    - max_drawdown_3y(price_history): worst peak-to-trough decline in last 3y.
    - net_debt_to_ebitda(row): leverage proxy.
    - beta_5y_monthly(price_history, market_history): regression beta.
    - interest_coverage_real(row): EBIT / |InterestExpense| using M1's real value.
    - risk_score_real(df, price_history_map): 0..100 composite, higher = safer.

The aggregator accepts ``price_history_map`` as optional. When None, it
gracefully falls back to row-only signals (ND/EBITDA, IC, Z'') and skips the
price-derived ones.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_finite(val: Any) -> bool:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


def _as_float(val: Any) -> float:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return float("nan")
    return f if np.isfinite(f) else float("nan")


def _close_series(price_history: Any) -> pd.Series:
    """Extract a sorted ``Close`` series from a yfinance/FMP price-history frame.

    Accepts:
        - pd.Series of close prices
        - pd.DataFrame with a ``Close`` column (and optional ``Date``)
        - None / empty → returns an empty Series.
    """
    if price_history is None:
        return pd.Series(dtype=float)
    if isinstance(price_history, pd.Series):
        s = price_history.dropna().astype(float)
        return s
    if isinstance(price_history, pd.DataFrame):
        if price_history.empty:
            return pd.Series(dtype=float)
        if "Close" in price_history.columns:
            s = price_history["Close"].astype(float)
            if "Date" in price_history.columns:
                idx = pd.to_datetime(price_history["Date"], errors="coerce")
                s = s.copy()
                s.index = idx
            return s.dropna().sort_index()
        # Sometimes the DataFrame is keyed by date already
        try:
            return price_history.iloc[:, 0].astype(float).dropna().sort_index()
        except Exception:
            return pd.Series(dtype=float)
    return pd.Series(dtype=float)


def _zscore_norm(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = series.astype(float)
    if s.notna().sum() < 2:
        return pd.Series([50.0 if pd.notna(v) else np.nan for v in s], index=s.index)
    mu = s.mean(skipna=True)
    sigma = s.std(skipna=True, ddof=0)
    if not np.isfinite(sigma) or sigma == 0:
        return pd.Series([50.0 if pd.notna(v) else np.nan for v in s], index=s.index)
    z = ((s - mu) / sigma).clip(-3.0, 3.0)
    if not higher_is_better:
        z = -z
    return ((z + 3.0) / 6.0 * 100.0).clip(0.0, 100.0)


# ---------------------------------------------------------------------------
# Price-history derived signals
# ---------------------------------------------------------------------------


def realized_volatility_1y(price_history: Any) -> float:
    """Annualised stddev of daily log-returns over the most recent ~252 trading days.

    Returns 0..2 typical range. NaN if fewer than 30 valid daily prices.
    """
    s = _close_series(price_history)
    if s.empty or len(s) < 30:
        return float("nan")

    # Use the most recent ~252 trading days
    s = s.tail(260)
    log_ret = np.log(s / s.shift(1)).dropna()
    if len(log_ret) < 20:
        return float("nan")
    sigma = float(log_ret.std(ddof=0))
    if not np.isfinite(sigma):
        return float("nan")
    return sigma * float(np.sqrt(252.0))


def max_drawdown_3y(price_history: Any) -> float:
    """Max peak-to-trough decline over the past ~3 years (756 trading days).

    Returns a non-positive number, e.g. -0.4 = -40%. NaN if fewer than 5 valid
    prices (drawdown is undefined for trivially short series).
    """
    s = _close_series(price_history)
    if s.empty or len(s) < 5:
        return float("nan")
    s = s.tail(756)
    running_max = s.cummax()
    dd = (s - running_max) / running_max
    if dd.empty:
        return float("nan")
    mn = float(dd.min())
    return mn if np.isfinite(mn) else float("nan")


def beta_5y_monthly(price_history: Any, market_history: Any) -> float:
    """Beta from 60 monthly returns (5y) regressed against the market.

    Resamples both series to month-end closing prices, computes simple monthly
    returns, then ``beta = cov(stock, market) / var(market)``.

    Returns NaN if fewer than 12 paired monthly returns.
    """
    s = _close_series(price_history)
    m = _close_series(market_history)
    if s.empty or m.empty:
        return float("nan")

    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index, errors="coerce")
    if not isinstance(m.index, pd.DatetimeIndex):
        m.index = pd.to_datetime(m.index, errors="coerce")
    s = s.dropna()
    m = m.dropna()
    if s.empty or m.empty:
        return float("nan")

    s_m = s.resample("ME").last().dropna()
    m_m = m.resample("ME").last().dropna()
    s_r = s_m.pct_change().dropna()
    m_r = m_m.pct_change().dropna()

    aligned = pd.concat([s_r, m_r], axis=1, join="inner").dropna()
    if len(aligned) < 12:
        return float("nan")
    stock_r = aligned.iloc[:, 0]
    mkt_r = aligned.iloc[:, 1]
    var_m = float(np.var(mkt_r, ddof=0))
    if not np.isfinite(var_m) or var_m == 0:
        return float("nan")
    cov = float(np.cov(stock_r, mkt_r, ddof=0)[0, 1])
    return cov / var_m


# ---------------------------------------------------------------------------
# Row-derived signals
# ---------------------------------------------------------------------------


def net_debt_to_ebitda(row: pd.Series) -> float:
    """(TotalDebt - Cash) / EBITDA. NaN if EBITDA <= 0 or any input missing."""
    debt = _as_float(row.get("TotalDebt"))
    cash = _as_float(row.get("Cash"))
    ebitda = _as_float(row.get("EBITDA"))
    if not (np.isfinite(debt) and np.isfinite(cash) and np.isfinite(ebitda)):
        return float("nan")
    if ebitda <= 0:
        return float("nan")
    return float((debt - cash) / ebitda)


def interest_coverage_real(row: pd.Series) -> float:
    """EBIT / |InterestExpense|. Uses M1's real interest expense -- never fabricates.

    Reads ``InterestCoverage`` directly from the row when present (the data
    fetcher already computes it from the real numbers). Falls back to
    EBIT / InterestExpense if the InterestCoverage column is missing.
    """
    ic = _as_float(row.get("InterestCoverage"))
    if np.isfinite(ic):
        return ic
    ebit = _as_float(row.get("EBIT"))
    ie = _as_float(row.get("InterestExpense"))
    if not (np.isfinite(ebit) and np.isfinite(ie)) or ie == 0:
        return float("nan")
    return float(ebit / abs(ie))


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def risk_score_real(
    df: pd.DataFrame,
    price_history_map: dict[str, Any] | None = None,
) -> pd.Series:
    """Sector-relative composite of risk signals. Higher = SAFER (0..100).

    Signals (all normalised so higher = safer):
        - Realised vol 1y           (lower vol = safer)
        - Max drawdown 3y           (smaller |DD| = safer; closer to 0)
        - Net Debt / EBITDA         (lower leverage = safer)
        - Interest Coverage         (higher = safer)
        - Altman Z'' (if column     (higher = safer)
          ``Altman_Z`` present)
        - Beta 5y monthly           (lower beta = safer)

    If ``price_history_map`` is None, the price-derived signals (vol, DD,
    Beta) are skipped and the score is computed from row-only signals
    (ND/EBITDA, Interest Coverage, Altman_Z). This keeps the function usable
    in unit tests and in cached-only flows where price history isn't loaded.

    Parameters
    ----------
    df:
        DataFrame indexed by ticker (or with a ``Ticker`` column). Each row
        must expose ``EBITDA``, ``TotalDebt``, ``Cash`` and ideally
        ``InterestCoverage`` or (``EBIT``, ``InterestExpense``). ``Altman_Z``
        is optional but recommended.
    price_history_map:
        Optional ``{ticker: pd.DataFrame}`` mapping. The per-ticker DataFrame
        is expected to have a ``Close`` column (yfinance / FMP convention).
        A special key ``"_market"`` may carry the market-index history used
        for beta. When absent, beta is skipped.

    Returns
    -------
    pd.Series
        Risk-score per row, indexed identically to ``df``.
    """
    # ------------------------------------------------------------------
    # 1. Row-only signals (always computable)
    # ------------------------------------------------------------------
    nd_ebitda = df.apply(net_debt_to_ebitda, axis=1)
    ic = df.apply(interest_coverage_real, axis=1)
    if "Altman_Z" in df.columns:
        zscore = df["Altman_Z"].astype(float)
    else:
        zscore = pd.Series([np.nan] * len(df), index=df.index)

    # ------------------------------------------------------------------
    # 2. Price-derived signals (only if price_history_map supplied)
    # ------------------------------------------------------------------
    have_prices = price_history_map is not None and bool(price_history_map)
    market_hist = (price_history_map or {}).get("_market") if have_prices else None

    if have_prices:
        vols: dict[Any, float] = {}
        mdds: dict[Any, float] = {}
        betas: dict[Any, float] = {}
        for idx in df.index:
            ticker = str(idx)
            ph = price_history_map.get(ticker)
            vols[idx] = realized_volatility_1y(ph)
            mdds[idx] = max_drawdown_3y(ph)
            if market_hist is not None:
                betas[idx] = beta_5y_monthly(ph, market_hist)
            else:
                betas[idx] = float("nan")
        vol_series = pd.Series(vols)
        mdd_series = pd.Series(mdds)
        beta_series = pd.Series(betas)
    else:
        vol_series = pd.Series([np.nan] * len(df), index=df.index)
        mdd_series = pd.Series([np.nan] * len(df), index=df.index)
        beta_series = pd.Series([np.nan] * len(df), index=df.index)

    # ------------------------------------------------------------------
    # 3. Normalise (sector-relative via M3, else z-score fallback)
    # ------------------------------------------------------------------
    sectors = df.get("Sector", pd.Series(["" for _ in range(len(df))], index=df.index))
    tmp = pd.DataFrame(
        {
            "nd_ebitda": nd_ebitda,
            "ic": ic,
            "altman": zscore,
            "vol": vol_series,
            "mdd": mdd_series,
            "beta": beta_series,
            "Sector": sectors,
        },
        index=df.index,
    )
    try:
        from src.analysis.sector_percentile import score_sector_relative  # type: ignore

        def _norm(metric: str, higher_is_better: bool) -> pd.Series:
            return score_sector_relative(tmp, metric, inverse=not higher_is_better)
    except (ImportError, AttributeError, TypeError):

        def _norm(metric: str, higher_is_better: bool) -> pd.Series:
            return _zscore_norm(tmp[metric], higher_is_better=higher_is_better)

    parts: dict[str, pd.Series] = {
        "nd_ebitda": _norm("nd_ebitda", False),  # lower is safer
        "ic": _norm("ic", True),
        "altman": _norm("altman", True),
    }
    if have_prices:
        parts["vol"] = _norm("vol", False)  # lower vol = safer
        parts["mdd"] = _norm("mdd", True)  # closer to 0 (less negative) = safer
        parts["beta"] = _norm("beta", False)  # lower beta = safer

    combined = pd.concat(parts, axis=1)
    score = combined.mean(axis=1, skipna=True).fillna(50.0).clip(0.0, 100.0)
    return score.round(1)
