"""Price-history + chart-derived metrics service."""
from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher

ChartPeriod = Literal["1M", "3M", "6M", "1Y", "5Y", "MAX"]

_PERIOD_DAYS: dict[str, int | None] = {
    "1M": 22,
    "3M": 66,
    "6M": 132,
    "1Y": 252,
    "5Y": 252 * 5,
    "MAX": None,
}


class ChartService:
    """Builds the company price-history response with computed metrics."""

    # Risk-free rate (annual). Phase 0 review: 0 systematically overstates
    # Sharpe by 0.2-0.4 in a 4-5% rate regime. Hardcode 4% default.
    RF_ANNUAL = 0.04

    def __init__(self, yf_fetcher: YFinanceDataFetcher) -> None:
        self._yf = yf_fetcher

    def get_price_history(
        self,
        ticker: str,
        period: str = "1Y",
        benchmark: str | None = None,
    ) -> dict[str, Any]:
        tickers = [ticker] + ([benchmark] if benchmark and benchmark != ticker else [])
        frames = self._yf.fetch_multi_price_history(tickers, period="max")

        stock_df = frames.get(ticker, pd.DataFrame())
        bench_df = frames.get(benchmark, pd.DataFrame()) if benchmark else pd.DataFrame()

        stock_df = self._slice_period(stock_df, period)
        bench_df = self._slice_period(bench_df, period)

        metrics = self._compute_metrics(stock_df, bench_df)
        mas = self._moving_averages(stock_df)

        return {
            "ticker": ticker,
            "period": period,
            "benchmark": benchmark,
            "candles": self._candles(stock_df),
            "benchmark_candles": self._candles(bench_df),
            "metrics": metrics,
            "moving_averages": mas,
        }

    @staticmethod
    def _slice_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
        if df.empty:
            return df
        n = _PERIOD_DAYS.get(period)
        if n is None:
            return df
        return df.tail(n).copy()

    @staticmethod
    def _candles(df: pd.DataFrame) -> list[dict[str, Any]]:
        """Emit JSON-serialisable candles. NaN fields become None (Pydantic
        serializes None to JSON null), satisfying the optional schema."""
        if df.empty:
            return []

        def _f(v: Any) -> float | None:
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            return None if np.isnan(f) or np.isinf(f) else f

        out: list[dict[str, Any]] = []
        for ts, row in df.iterrows():
            out.append(
                {
                    "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                    "open": _f(row.get("Open")),
                    "high": _f(row.get("High")),
                    "low": _f(row.get("Low")),
                    "close": _f(row.get("Close")),
                    "volume": _f(row.get("Volume")),
                }
            )
        return out

    @staticmethod
    def _moving_averages(df: pd.DataFrame) -> dict[str, list[float | None]]:
        if df.empty:
            return {"ma_50": [], "ma_200": []}
        close = df["Close"].astype(float)
        ma50 = close.rolling(50, min_periods=50).mean()
        ma200 = close.rolling(200, min_periods=200).mean()

        def _ser(s: pd.Series) -> list[float | None]:
            return [None if pd.isna(v) else float(v) for v in s]

        return {"ma_50": _ser(ma50), "ma_200": _ser(ma200)}

    @staticmethod
    def _compute_metrics(stock: pd.DataFrame, bench: pd.DataFrame) -> dict[str, Any]:
        """Phase 0 financial review baked in:
        - vol + sharpe use LOG returns (time-additive, no 0.5*sigma^2 bias).
        - CAGR uses calendar days / 365.25.
        - sharpe uses rf=4% annual.
        - beta computes pct_change FIRST then inner-joins on date.
        """
        out: dict[str, Any] = {
            "total_return": None,
            "cagr": None,
            "annualized_vol": None,
            "max_drawdown": None,
            "beta": None,
            "sharpe": None,
        }
        if stock.empty:
            return out

        closes = stock["Close"].astype(float).dropna()
        if len(closes) < 2:
            return out

        first, last = closes.iloc[0], closes.iloc[-1]
        out["total_return"] = float(last / first - 1)

        # CAGR: calendar days, not trading days
        try:
            cal_days = (closes.index[-1] - closes.index[0]).days
            years = cal_days / 365.25
        except (AttributeError, TypeError):
            years = len(closes) / 252.0
        if years >= 1.0:
            out["cagr"] = float((last / first) ** (1 / years) - 1)

        log_rets = np.log(closes / closes.shift(1)).dropna()
        if not log_rets.empty:
            vol_daily = float(log_rets.std())
            out["annualized_vol"] = vol_daily * float(np.sqrt(252))
            if vol_daily > 0:
                rf_daily = (1 + ChartService.RF_ANNUAL) ** (1 / 252) - 1
                excess_mean = float(log_rets.mean()) - rf_daily
                out["sharpe"] = (excess_mean / vol_daily) * float(np.sqrt(252))

        cummax = closes.cummax()
        out["max_drawdown"] = float((closes / cummax - 1).min())

        if not bench.empty:
            bench_close = bench["Close"].astype(float).dropna()
            ra = closes.pct_change().dropna()
            rb = bench_close.pct_change().dropna()
            aligned = pd.concat([ra, rb], axis=1, join="inner").dropna()
            if len(aligned) >= 60:
                var_b = float(aligned.iloc[:, 1].var())
                if var_b > 0:
                    cov_mat = aligned.cov()
                    out["beta"] = float(cov_mat.iloc[0, 1] / var_b)

        return out
