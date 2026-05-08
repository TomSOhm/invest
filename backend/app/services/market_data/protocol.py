"""
Invest Solo -- MarketDataSource Protocol
Defines the contract that every data backend (FMP, yfinance, mock) must satisfy.

Design notes:
- Uses typing.Protocol (structural subtyping) -- no ABC inheritance required.
- Methods that a concrete source cannot supply MUST raise NotImplementedError so
  the HybridDataFetcher can detect "unsupported" vs a genuine NaN value.
- FetchedField carries both the value and its provenance so callers can build
  the per-field coverage matrix required by M2 and M5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import pandas as pd


@dataclass
class FetchedField:
    """A single value together with the source that produced it.

    Attributes
    ----------
    value:
        The actual data value. May be ``float('nan')`` when the source knows
        the field exists but has no data for this ticker.
    source:
        One of ``"fmp"``, ``"yfinance"``, or ``"missing"`` (both sources
        returned nothing useful).
    """

    value: Any = float("nan")
    source: str = "missing"  # "fmp" | "yfinance" | "missing"


@runtime_checkable
class MarketDataSource(Protocol):
    """Structural protocol for all market data backends.

    Every implementing class must expose a ``name`` attribute and the eight
    fetch methods listed below. Methods that a source fundamentally cannot
    provide must raise ``NotImplementedError`` (not return NaN) so the hybrid
    composer can distinguish "unsupported" from "no data for this ticker".

    Concrete implementations: ``FMPDataFetcher``, ``YFinanceDataFetcher``.
    """

    name: str  # "fmp" | "yfinance" | "mock"

    # ------------------------------------------------------------------
    # Quote / price data
    # ------------------------------------------------------------------

    def fetch_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch current market snapshot for *ticker*.

        Returns a flat dict containing at minimum:
            ``Price``, ``MarketCap``, ``EV``, ``Shares``, ``Beta``,
            ``AvgVolume``, ``FiftyTwoWeekHigh``, ``FiftyTwoWeekLow``.

        All missing numeric values should be ``float('nan')``.
        """
        ...

    def fetch_fundamentals_annual(self, ticker: str) -> pd.DataFrame:
        """Fetch annual fundamental statements merged into a single DataFrame.

        Returns
        -------
        pd.DataFrame
            Rows = financial line items (e.g. ``"Revenue"``, ``"EBIT"``).
            Columns = fiscal year end dates (most-recent first, as strings
            ``"YYYY-MM-DD"``).
            Empty DataFrame on 404 / no data.
        """
        ...

    def fetch_fundamentals_quarterly(self, ticker: str) -> pd.DataFrame:
        """Same layout as :meth:`fetch_fundamentals_annual` but quarterly."""
        ...

    def fetch_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        """Fetch OHLCV price history.

        Returns
        -------
        pd.DataFrame
            Columns: ``Date``, ``Open``, ``High``, ``Low``, ``Close``,
            ``Volume``.  ``Date`` is a ``datetime64[ns]`` column (not index).
            Empty DataFrame on failure.
        """
        ...

    def fetch_eps_estimates(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch analyst EPS estimates.

        Returns a DataFrame or ``None`` if not available. Sources that do not
        support this method must raise ``NotImplementedError``.
        """
        ...

    def fetch_eps_revisions(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch EPS revision history (upgrade/downgrade data).

        Returns a DataFrame or ``None``. Sources lacking this signal must
        raise ``NotImplementedError``.
        """
        ...

    def fetch_analyst_targets(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch consensus analyst price targets.

        Returns a dict with keys ``target_low``, ``target_mean``,
        ``target_high``, ``target_median``, ``num_analysts``, or ``None``.
        Sources that cannot provide this must raise ``NotImplementedError``.
        """
        ...

    def fetch_news(
        self, ticker: str, limit: int = 20
    ) -> Optional[List[Dict[str, Any]]]:
        """Fetch recent news headlines.

        Returns a list of dicts with keys ``title``, ``publishedAt``,
        ``source``, ``url``, or ``None``. Sources lacking news must raise
        ``NotImplementedError``.
        """
        ...

    def fetch_profile(self, ticker: str) -> Dict[str, Any]:
        """Fetch company profile / identification data.

        Returns a dict containing at minimum:
            ``Name``, ``Sector``, ``Industry``, ``Country``, ``Exchange``,
            ``FirstTradeDate`` (ISO string or ``None``).
        """
        ...
