"""
Invest Solo -- FastAPI Dependency Injection
Creates service singletons and provides them via Depends() callables.
"""

from functools import lru_cache

from backend.app.services.cache_service import CacheService
from backend.app.services.company_service import CompanyService
from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.portfolio_service import PortfolioService
from backend.app.services.scoring_service import ScoringService
from backend.app.services.screener_service import ScreenerService
from backend.app.services.watchlist_service import WatchlistService
from backend.app.storage.portfolio_store import PortfolioStore
from backend.app.storage.watchlist_store import WatchlistStore

# ---------------------------------------------------------------------------
# Singletons (created once, reused for all requests)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_cache_service() -> CacheService:
    return CacheService()


@lru_cache(maxsize=1)
def _get_portfolio_store() -> PortfolioStore:
    return PortfolioStore()


@lru_cache(maxsize=1)
def _get_watchlist_store() -> WatchlistStore:
    return WatchlistStore()


@lru_cache(maxsize=1)
def _get_data_fetcher() -> DataFetcher:
    return DataFetcher(cache=_get_cache_service())


@lru_cache(maxsize=1)
def _get_scoring_service() -> ScoringService:
    return ScoringService()


@lru_cache(maxsize=1)
def _get_screener_service() -> ScreenerService:
    return ScreenerService()


@lru_cache(maxsize=1)
def _get_portfolio_service() -> PortfolioService:
    return PortfolioService(
        store=_get_portfolio_store(),
        fetcher=_get_data_fetcher(),
        scorer=_get_scoring_service(),
    )


@lru_cache(maxsize=1)
def _get_watchlist_service() -> WatchlistService:
    return WatchlistService(
        store=_get_watchlist_store(),
        fetcher=_get_data_fetcher(),
        scorer=_get_scoring_service(),
    )


@lru_cache(maxsize=1)
def _get_company_service() -> CompanyService:
    return CompanyService(
        fetcher=_get_data_fetcher(),
        scorer=_get_scoring_service(),
    )


# ---------------------------------------------------------------------------
# Depends() callables for FastAPI router functions
# ---------------------------------------------------------------------------


def get_cache_service() -> CacheService:
    return _get_cache_service()


def get_data_fetcher() -> DataFetcher:
    return _get_data_fetcher()


def get_scoring_service() -> ScoringService:
    return _get_scoring_service()


def get_screener_service() -> ScreenerService:
    return _get_screener_service()


def get_portfolio_service() -> PortfolioService:
    return _get_portfolio_service()


def get_watchlist_service() -> WatchlistService:
    return _get_watchlist_service()


def get_company_service() -> CompanyService:
    return _get_company_service()
