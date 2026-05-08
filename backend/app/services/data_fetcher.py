"""
Invest Solo -- Data Fetcher Service (M2 compatibility shim)
===========================================================
As of M2, the actual fetching logic lives in:
  backend/app/services/market_data/
    protocol.py       -- MarketDataSource Protocol
    fmp_fetcher.py    -- FMPDataFetcher (FMP REST API)
    yfinance_fetcher.py -- YFinanceDataFetcher
    hybrid_fetcher.py -- HybridDataFetcher (FMP-first, yfinance fallback)

This file is kept as a *thin shim* so that:
  - backend/app/dependencies.py can keep returning DataFetcher unchanged
  - scripts/capture_golden_snapshots.py keeps working
  - SCORING_COLUMNS / EXTRA_FIELDS remain importable from this module

M10 will rename this and replace dependencies.py injection.
"""
import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from loguru import logger

from backend.app.config import settings
from backend.app.services.cache_service import CacheService

# Load .env so FMP_TOKEN is available before instantiation
load_dotenv()


# ---------------------------------------------------------------------------
# Column contracts (unchanged from M1 -- do NOT modify)
# ---------------------------------------------------------------------------

SCORING_COLUMNS = [
    "PE", "PB", "PS", "PFCF", "EV_EBITDA", "EV_Sales",
    "ROE", "ROA", "ROIC", "OperatingMargin", "NetMargin", "FCFMargin", "GrossMargin",
    "RevenueGrowth", "CurrentRatio", "DebtEquity", "InterestCoverage",
    "DivYield", "PayoutRatio", "Beta",
    "Price", "MarketCap", "EV", "Shares",
    "Revenue", "EBITDA", "EBIT", "NetIncome", "FCF", "OperatingCashflow", "CapEx",
    "TotalAssets", "TotalEquity", "TotalDebt", "Cash",
    # M1 additions (real Altman Z'' inputs, real Piotroski dilution check, screener wiring)
    "CurrentAssets", "CurrentLiabilities", "RetainedEarnings",
    "AvgVolume", "YearsListed", "Shares_PriorYear",
    # M4 additions (Year-over-Year deltas for Piotroski 2000)
    "ROA_PriorYear", "OperatingCashflow_PriorYear",
    "LongTermDebt", "LongTermDebt_PriorYear",
    "CurrentRatio_PriorYear", "GrossMargin_PriorYear",
    "Revenue_PriorYear", "TotalAssets_PriorYear",
    "Name", "Sector", "Industry", "Country", "Exchange",
    "PEA", "PEA_PME",
]

# Extra fields we fetch beyond what the scoring engine needs
EXTRA_FIELDS = [
    "ForwardPE", "PEG", "InsiderPct", "InstitutionalPct",
    "ShortPctFloat", "FiftyTwoWeekHigh", "FiftyTwoWeekLow",
]


# ---------------------------------------------------------------------------
# DataFetcher shim
# ---------------------------------------------------------------------------

class DataFetcher:
    """Backwards-compatible shim over HybridDataFetcher.

    Instantiates FMPDataFetcher + YFinanceDataFetcher + HybridDataFetcher and
    delegates every public method call to the hybrid.

    The constructor signature (``cache`` kwarg) is unchanged so that
    ``dependencies.py`` continues to work without modification.
    """

    def __init__(self, cache: Optional[CacheService] = None) -> None:
        _cache = cache or CacheService()
        # Import here to avoid circular imports at module load
        from backend.app.services.market_data.fmp_fetcher import FMPDataFetcher
        from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher
        from backend.app.services.market_data.hybrid_fetcher import HybridDataFetcher

        fmp_token = os.getenv("FMP_TOKEN", "")
        fmp_enabled = getattr(settings, "fmp_enabled", True)

        fmp_fetcher = FMPDataFetcher(
            token=fmp_token,
            cache=_cache,
            enabled=fmp_enabled,
        )
        yf_fetcher = YFinanceDataFetcher(cache=_cache)

        self._hybrid = HybridDataFetcher(
            fmp=fmp_fetcher,
            yf=yf_fetcher,
            cache=_cache,
        )

        # Kept for any code that reads DataFetcher._pea_countries directly
        self._pea_countries = settings.pea_eligible_countries
        self._delay = settings.request_delay_seconds
        self._cache = _cache

    # ------------------------------------------------------------------
    # Delegate to hybrid
    # ------------------------------------------------------------------

    def fetch_single(self, ticker_symbol: str) -> Dict[str, Any]:
        """Delegate to HybridDataFetcher.fetch_single()."""
        return self._hybrid.fetch_single(ticker_symbol)

    def fetch_batch(self, tickers: List[str]) -> pd.DataFrame:
        """Delegate to HybridDataFetcher.fetch_batch()."""
        return self._hybrid.fetch_batch(tickers)

    def fetch_analyst_ratings(self, ticker_symbol: str) -> Optional[Dict[str, Any]]:
        """Delegate to HybridDataFetcher.fetch_analyst_ratings()."""
        return self._hybrid.fetch_analyst_ratings(ticker_symbol)

    # ------------------------------------------------------------------
    # Legacy static method kept for callers that used DataFetcher._country_to_code
    # ------------------------------------------------------------------

    @staticmethod
    def _country_to_code(country_name: str) -> str:
        """Map a country name to its ISO 2-letter code (legacy compatibility)."""
        from backend.app.services.market_data.yfinance_fetcher import _country_to_code
        return _country_to_code(country_name)

    # ------------------------------------------------------------------
    # Legacy method: _determine_pea_eligible (kept for compatibility)
    # ------------------------------------------------------------------

    def _determine_pea_eligible(self, country: str) -> bool:
        """Check PEA eligibility from country code (legacy compatibility)."""
        if not country:
            return False
        return country.upper() in self._pea_countries
