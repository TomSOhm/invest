"""
Invest Solo -- Market Data Package
Provides FMP-first hybrid data fetching with per-field yfinance fallback.
"""

from backend.app.services.market_data.fmp_fetcher import FMPDataFetcher, FMPQuotaExceeded
from backend.app.services.market_data.hybrid_fetcher import HybridDataFetcher
from backend.app.services.market_data.protocol import FetchedField, MarketDataSource
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher

__all__ = [
    "MarketDataSource",
    "FetchedField",
    "FMPDataFetcher",
    "FMPQuotaExceeded",
    "YFinanceDataFetcher",
    "HybridDataFetcher",
]
