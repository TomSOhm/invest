"""
Backtest-test fixtures.

The backtest tests run against a deterministic synthetic price-history
fetcher so they don't depend on live FMP / yfinance availability and stay
fast (<30s each).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pytest


def _generate_synthetic_price_history(
    seed: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    annual_drift: float = 0.08,
    annual_vol: float = 0.20,
) -> pd.DataFrame:
    """Geometric Brownian motion price path.

    Returns a DataFrame with a Date column and OHLCV columns. Daily volume
    is held constant at 1e6 to avoid liquidity-filter spurious effects.
    """
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start=start, end=end)
    n = len(days)
    if n == 0:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    dt = 1 / 252
    drift_d = annual_drift * dt
    vol_d = annual_vol * np.sqrt(dt)
    rets = rng.normal(loc=drift_d, scale=vol_d, size=n)
    prices = 100.0 * np.exp(np.cumsum(rets))
    df = pd.DataFrame(
        {
            "Date": days,
            "Open": prices,
            "High": prices * 1.005,
            "Low": prices * 0.995,
            "Close": prices,
            "Volume": np.full(n, 1_000_000, dtype=int),
        }
    )
    return df


class SyntheticFetcher:
    """Mock MarketDataSource that emits synthetic GBM price histories.

    The fundamentals API returns empty DataFrames -- the test injects
    fundamentals via ``universe_df``.
    """

    name = "synthetic"

    def __init__(
        self,
        start: pd.Timestamp = pd.Timestamp("2018-01-01"),
        end: pd.Timestamp = pd.Timestamp("2024-12-31"),
        ticker_drifts: Optional[Dict[str, float]] = None,
        benchmark_drift: float = 0.06,
    ) -> None:
        self._start = start
        self._end = end
        self._ticker_drifts = ticker_drifts or {}
        self._benchmark_drift = benchmark_drift

    def fetch_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        # Deterministic seed derived from ticker hash so tests are reproducible.
        seed = abs(hash(ticker)) % (2**32)
        # Benchmarks (^FCHI / ^GSPC) get the benchmark drift, others ticker drift.
        if ticker in ("^FCHI", "^GSPC", "^STOXX50E"):
            drift = self._benchmark_drift
        else:
            drift = self._ticker_drifts.get(ticker, 0.10)
        return _generate_synthetic_price_history(
            seed=seed,
            start=self._start,
            end=self._end,
            annual_drift=drift,
            annual_vol=0.20,
        )

    def fetch_quote(self, ticker: str) -> Dict[str, Any]:
        return {}

    def fetch_fundamentals_annual(self, ticker: str) -> pd.DataFrame:
        return pd.DataFrame()

    def fetch_fundamentals_quarterly(self, ticker: str) -> pd.DataFrame:
        return pd.DataFrame()

    def fetch_eps_estimates(self, ticker: str):
        return None

    def fetch_eps_revisions(self, ticker: str):
        return None

    def fetch_analyst_targets(self, ticker: str):
        return None

    def fetch_news(self, ticker: str, limit: int = 20):
        return None

    def fetch_profile(self, ticker: str) -> Dict[str, Any]:
        return {}


@pytest.fixture
def synthetic_fetcher() -> SyntheticFetcher:
    """Default synthetic fetcher: generic 10% drift for stocks, 6% for benchmarks."""
    return SyntheticFetcher()


@pytest.fixture
def alpha_fetcher() -> SyntheticFetcher:
    """Synthetic fetcher where all stocks beat the benchmark by 4%/y.

    Used to verify the backtest plumbing: when stocks structurally outperform
    by a wide margin, alpha must come back positive.
    """
    return SyntheticFetcher(
        ticker_drifts={},  # default 10%
        benchmark_drift=0.06,
    )


@pytest.fixture
def pea_universe_df() -> pd.DataFrame:
    """Use the bundled PEA sample universe DataFrame as fundamentals input."""
    from src.data.sample_universe import get_universe_dataframe
    return get_universe_dataframe()


@pytest.fixture
def pea_tickers(pea_universe_df) -> List[str]:
    return list(pea_universe_df.index)


@pytest.fixture
def sp500_tickers() -> List[str]:
    """Curated S&P 500 sample (top ~50 by market cap)."""
    from backend.app.services.backtest.cli import SP500_SAMPLE_50
    return list(SP500_SAMPLE_50)


@pytest.fixture
def sp500_universe_df(sp500_tickers) -> pd.DataFrame:
    """Synthesise a minimum fundamentals frame for S&P names.

    Most preset filters operate on columns that the bundled sample universe
    does NOT cover for US tickers (e.g. ROIC_5y_Avg, F-Score). We inject
    'pass-through' values so the preset doesn't reject everything.
    """
    rows = []
    for i, t in enumerate(sp500_tickers):
        rows.append(
            {
                "Ticker": t,
                "Name": t,
                "Sector": "Technology" if i % 2 == 0 else "Healthcare",
                "Industry": "Software",
                "Country": "US",
                "Exchange": "NASDAQ",
                "Price": 100.0,
                "MarketCap": 200e9,
                "EV": 200e9,
                "Shares": 2e9,
                "Revenue": 50e9,
                "RevenueGrowth": 0.10,
                "EBITDA": 20e9,
                "EBIT": 18e9,
                "NetIncome": 12e9,
                "FCF": 10e9,
                "OperatingCashflow": 14e9,
                "CapEx": 4e9,
                "TotalAssets": 200e9,
                "TotalEquity": 100e9,
                "TotalDebt": 30e9,
                "Cash": 20e9,
                "CurrentAssets": 60e9,
                "CurrentLiabilities": 30e9,
                "RetainedEarnings": 50e9,
                "GrossMargin": 0.55,
                "OperatingMargin": 0.30,
                "NetMargin": 0.24,
                "FCFMargin": 0.20,
                "ROE": 0.18,
                "ROA": 0.10,
                "ROIC": 0.20,
                "PE": 22.0,
                "PB": 5.0,
                "PS": 4.0,
                "PFCF": 20.0,
                "EV_EBITDA": 12.0,
                "EV_Sales": 4.0,
                "DivYield": 0.015,
                "PayoutRatio": 0.30,
                "Beta": 1.1,
                "CurrentRatio": 1.5,
                "DebtEquity": 0.30,
                "InterestCoverage": 15.0,
                "AvgVolume": 5_000_000,
                "PEA": False,
                "PEA_PME": False,
            }
        )
    df = pd.DataFrame(rows)
    df.set_index("Ticker", inplace=True)
    return df
