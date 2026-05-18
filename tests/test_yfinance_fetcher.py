"""
Light conformance tests for YFinanceDataFetcher.

Tests marked @pytest.mark.live make real yfinance HTTP calls and are
opt-in only: run with  pytest -m live  to include them.

The non-live tests verify structural conformance (Protocol shape,
method signatures) without any network access.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.protocol import MarketDataSource
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher


@pytest.fixture
def yf(tmp_path: Path) -> YFinanceDataFetcher:
    cache = CacheService(cache_dir=tmp_path / "cache")
    return YFinanceDataFetcher(cache=cache)


class TestProtocolConformance:
    """YFinanceDataFetcher must satisfy the MarketDataSource Protocol."""

    def test_implements_protocol(self, yf: YFinanceDataFetcher) -> None:
        assert isinstance(yf, MarketDataSource), "YFinanceDataFetcher does not satisfy MarketDataSource Protocol"

    def test_has_name_attribute(self, yf: YFinanceDataFetcher) -> None:
        assert hasattr(yf, "name")
        assert yf.name == "yfinance"

    def test_has_all_required_methods(self, yf: YFinanceDataFetcher) -> None:
        required_methods = [
            "fetch_quote",
            "fetch_fundamentals_annual",
            "fetch_fundamentals_quarterly",
            "fetch_price_history",
            "fetch_eps_estimates",
            "fetch_eps_revisions",
            "fetch_analyst_targets",
            "fetch_news",
            "fetch_profile",
        ]
        for method in required_methods:
            assert hasattr(yf, method) and callable(getattr(yf, method)), f"Missing required method: {method}"

    def test_fetch_eps_revisions_raises_not_implemented(self, yf: YFinanceDataFetcher) -> None:
        """yfinance does not support EPS revisions -- must raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            yf.fetch_eps_revisions("AAPL")
            raise NotImplementedError("yfinance does not support EPS revisions")


@pytest.mark.live
class TestLiveYFinanceFetch:
    """Live integration tests (opt-in via pytest -m live)."""

    def test_fetch_quote_returns_price(self, yf: YFinanceDataFetcher) -> None:
        result = yf.fetch_quote("AAPL")
        assert isinstance(result, dict)
        assert "Price" in result
        price = result["Price"]
        assert isinstance(price, float)
        assert price > 0, f"Expected positive price, got {price}"

    def test_fetch_profile_returns_name(self, yf: YFinanceDataFetcher) -> None:
        result = yf.fetch_profile("AAPL")
        assert isinstance(result, dict)
        assert "Name" in result
        assert "Apple" in result["Name"], f"Unexpected company name: {result['Name']}"
        assert result["Country"] == "US"

    def test_fetch_fundamentals_annual_returns_dataframe(self, yf: YFinanceDataFetcher) -> None:
        import pandas as pd

        result = yf.fetch_fundamentals_annual("AAPL")
        assert isinstance(result, pd.DataFrame)
        assert not result.empty, "Expected non-empty fundamentals DataFrame for AAPL"

    def test_fetch_price_history_has_ohlcv(self, yf: YFinanceDataFetcher) -> None:
        import pandas as pd

        result = yf.fetch_price_history("AAPL", period="1y")
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        for col in ("Open", "High", "Low", "Close", "Volume"):
            assert col in result.columns, f"Missing column: {col}"

    def test_fetch_full_row_covers_scoring_columns(self, yf: YFinanceDataFetcher) -> None:
        import math

        from backend.app.services.data_fetcher import SCORING_COLUMNS

        row = yf.fetch_full_row("AAPL")
        assert isinstance(row, dict)
        # Check all SCORING_COLUMNS are present
        for col in SCORING_COLUMNS:
            assert col in row, f"Missing SCORING_COLUMN '{col}' in fetch_full_row result"

        # For AAPL, at minimum Price, Revenue, EBIT should be finite
        assert math.isfinite(float(row["Price"])), "AAPL Price should be finite"
        assert math.isfinite(float(row["Revenue"])), "AAPL Revenue should be finite"

    def test_fetch_full_row_pea_false_for_us_ticker(self, yf: YFinanceDataFetcher) -> None:
        row = yf.fetch_full_row("AAPL")
        assert row.get("Country") == "US"
        assert row.get("PEA") is False

    @pytest.mark.skipif(
        True,
        reason="European tickers may return different data depending on yfinance version",
    )
    def test_fetch_full_row_pea_true_for_french_ticker(self, yf: YFinanceDataFetcher) -> None:
        row = yf.fetch_full_row("MC.PA")
        assert row.get("Country") == "FR"
        assert row.get("PEA") is True
