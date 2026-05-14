"""Tests for HybridDataFetcher.fetch_calendar wrapper (sub-project 3).

yfinance is the only backing source — FMP calendar endpoints are intentionally
unwired.  The ``source`` parameter is honored for cache-key isolation only;
all 3 sources route through yfinance internally.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.fmp_fetcher import FMPDataFetcher, _QuotaTracker
from backend.app.services.market_data.hybrid_fetcher import HybridDataFetcher
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher


@pytest.fixture
def tmp_cache(tmp_path: Path) -> CacheService:
    return CacheService(cache_dir=tmp_path / "cache")


@pytest.fixture
def hybrid(tmp_cache: CacheService, tmp_path: Path) -> HybridDataFetcher:
    fmp = FMPDataFetcher(token="FAKE", cache=tmp_cache, daily_limit=240, enabled=True)
    fmp._quota = _QuotaTracker(path=tmp_path / "fmp_quota.json")
    yf = YFinanceDataFetcher(cache=tmp_cache)
    return HybridDataFetcher(fmp=fmp, yf=yf, cache=tmp_cache)


_CAL_PAYLOAD = {
    "next_earnings_date": "2026-07-30",
    "next_earnings_eps_estimate": 2.10,
    "next_earnings_eps_low": 1.95,
    "next_earnings_eps_high": 2.20,
    "next_earnings_revenue_estimate": 93e9,
    "dividend_date": "2026-05-15",
    "ex_dividend_date": "2026-05-11",
}

_DIVS_PAYLOAD = [
    {"ex_date": "2025-05-07", "amount": 0.26},
    {"ex_date": "2026-05-11", "amount": 0.27},
]

_YIELDS_PAYLOAD = {
    "dividend_yield": 0.0046,
    "dividend_rate": 1.08,
    "trailing_annual_dividend_rate": 1.05,
    "trailing_annual_dividend_yield": 0.0044,
}


def test_fetch_calendar_routes_through_yfinance(hybrid: HybridDataFetcher) -> None:
    """Hybrid wrapper assembles all 3 yfinance fetch results into one payload."""
    with (
        patch.object(hybrid._yf, "fetch_calendar", return_value=_CAL_PAYLOAD) as mock_cal,
        patch.object(hybrid._yf, "fetch_dividends", return_value=_DIVS_PAYLOAD) as mock_div,
        patch.object(hybrid._yf, "fetch_info_yields", return_value=_YIELDS_PAYLOAD) as mock_yld,
    ):
        out = hybrid.fetch_calendar("AAPL", source="hybrid")
    assert out["next_earnings_date"] == "2026-07-30"
    assert out["dividend_yield"] == pytest.approx(0.0046)
    assert out["dividend_amount"] == pytest.approx(0.27)  # latest dividend
    assert out["dividends_5y"] == _DIVS_PAYLOAD
    mock_cal.assert_called_once_with("AAPL")
    mock_div.assert_called_once()
    mock_yld.assert_called_once_with("AAPL")


def test_fetch_calendar_source_param_isolates_cache(hybrid: HybridDataFetcher) -> None:
    """source param differentiates cache key but always routes to yfinance."""
    with (
        patch.object(hybrid._yf, "fetch_calendar", return_value=_CAL_PAYLOAD) as mock_cal,
        patch.object(hybrid._yf, "fetch_dividends", return_value=[]),
        patch.object(hybrid._yf, "fetch_info_yields", return_value=_YIELDS_PAYLOAD),
    ):
        hybrid.fetch_calendar("AAPL", source="fmp")
        hybrid.fetch_calendar("AAPL", source="yfinance")
        hybrid.fetch_calendar("AAPL", source="hybrid")
    # Each distinct cache key hits yfinance once
    assert mock_cal.call_count == 3


def test_fetch_calendar_uses_cache(hybrid: HybridDataFetcher) -> None:
    with (
        patch.object(hybrid._yf, "fetch_calendar", return_value=_CAL_PAYLOAD) as mock_cal,
        patch.object(hybrid._yf, "fetch_dividends", return_value=_DIVS_PAYLOAD),
        patch.object(hybrid._yf, "fetch_info_yields", return_value=_YIELDS_PAYLOAD),
    ):
        hybrid.fetch_calendar("AAPL", source="hybrid")
        hybrid.fetch_calendar("AAPL", source="hybrid")  # cache hit
    assert mock_cal.call_count == 1


def test_fetch_calendar_individual_failures_dont_block_others(hybrid: HybridDataFetcher) -> None:
    """Calendar fetch raises but dividends + yields still flow through."""
    with (
        patch.object(hybrid._yf, "fetch_calendar", side_effect=RuntimeError("boom")),
        patch.object(hybrid._yf, "fetch_dividends", return_value=_DIVS_PAYLOAD),
        patch.object(hybrid._yf, "fetch_info_yields", return_value=_YIELDS_PAYLOAD),
    ):
        out = hybrid.fetch_calendar("AAPL", source="hybrid")
    assert out["next_earnings_date"] is None  # calendar failed
    assert out["dividend_amount"] == pytest.approx(0.27)
    assert out["dividend_yield"] == pytest.approx(0.0046)
    assert out["dividends_5y"] == _DIVS_PAYLOAD


def test_fetch_calendar_empty_dividends_default_amount_none(hybrid: HybridDataFetcher) -> None:
    with (
        patch.object(hybrid._yf, "fetch_calendar", return_value=_CAL_PAYLOAD),
        patch.object(hybrid._yf, "fetch_dividends", return_value=[]),
        patch.object(hybrid._yf, "fetch_info_yields", return_value={}),
    ):
        out = hybrid.fetch_calendar("CRWD", source="hybrid")
    assert out["dividend_amount"] is None
    assert out["dividends_5y"] == []
