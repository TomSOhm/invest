"""Tests for source-routing in HybridDataFetcher."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.fmp_fetcher import (
    FMPDataFetcher,
    FMPHTTPError,
    FMPQuotaExceeded,
    _QuotaTracker,
)
from backend.app.services.market_data.hybrid_fetcher import HybridDataFetcher
from backend.app.services.market_data.types import (
    SOURCES,
    is_valid_source,
)
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher


def test_sources_constant_contains_three_values():
    assert SOURCES == ("hybrid", "yfinance", "fmp")


def test_is_valid_source_accepts_known():
    for s in SOURCES:
        assert is_valid_source(s)


def test_is_valid_source_rejects_unknown():
    assert not is_valid_source("alpha_vantage")
    assert not is_valid_source("")
    assert not is_valid_source(None)


# ---------------------------------------------------------------------------
# Fixtures shared across source-routing tests
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_cache(tmp_path: Path) -> CacheService:
    return CacheService(cache_dir=tmp_path / "cache")


@pytest.fixture
def hybrid(tmp_cache: CacheService, tmp_path: Path) -> HybridDataFetcher:
    fmp = FMPDataFetcher(token="FAKE", cache=tmp_cache, daily_limit=240, enabled=True)
    fmp._quota = _QuotaTracker(path=tmp_path / "fmp_quota.json")
    yf = YFinanceDataFetcher(cache=tmp_cache)
    return HybridDataFetcher(fmp=fmp, yf=yf, cache=tmp_cache)


# Minimal yfinance row that satisfies the routing tests without crashing the
# downstream PEA/completeness calculations.
_YF_ROW: dict[str, Any] = {
    "Name": "Test Corp",
    "Sector": "Technology",
    "Industry": "Software",
    "Country": "US",
    "Exchange": "NMS",
    "Price": 100.0,
    "MarketCap": 1_000_000_000.0,
    "Shares": 10_000_000.0,
    "Revenue": 4e8,
    "NetIncome": 5e7,
    "FCF": 4e7,
    "TotalAssets": 5e8,
    "TotalEquity": 2e8,
    "TotalDebt": 1e8,
    "Cash": 5e7,
    "EBIT": 7e7,
    "EBITDA": 8e7,
    "PE": 22.0,
    "ROE": 0.25,
    "PEA": False,
    "PEA_PME": False,
}


# ---------------------------------------------------------------------------
# Task 2: yfinance-only branch
# ---------------------------------------------------------------------------


def test_yfinance_only_source_skips_fmp(hybrid: HybridDataFetcher) -> None:
    with (
        patch.object(hybrid._yf, "fetch_full_row", return_value=_YF_ROW.copy()) as yf_mock,
        patch.object(hybrid._fmp, "extract_scoring_fields") as fmp_mock,
        patch.object(hybrid._fmp, "fetch_quote") as fmp_quote_mock,
    ):
        result = hybrid.fetch_single("AAPL", source="yfinance")

    yf_mock.assert_called_once()
    fmp_mock.assert_not_called()
    fmp_quote_mock.assert_not_called()
    assert result["effective_source"] == "yfinance"
    assert result["source_fallback_message"] is None
    assert all(v in ("yfinance", "missing", "computed") for v in result["field_sources"].values())


def test_yfinance_only_uses_separate_cache_key(
    hybrid: HybridDataFetcher,
    tmp_cache: CacheService,
) -> None:
    with patch.object(hybrid._yf, "fetch_full_row", return_value=_YF_ROW.copy()):
        hybrid.fetch_single("AAPL", source="yfinance")
    assert tmp_cache.get("yfinance:AAPL") is not None
    assert tmp_cache.get("hybrid:AAPL") is None


def test_unknown_source_raises(hybrid: HybridDataFetcher) -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        hybrid.fetch_single("AAPL", source="bloomberg")


# ---------------------------------------------------------------------------
# Task 3: fmp-only branch + explicit fallback
# ---------------------------------------------------------------------------


def _fmp_scoring_row() -> dict[str, Any]:
    return {
        "Revenue": 4.5e8,
        "NetIncome": 6e7,
        "FCF": 5e7,
        "TotalAssets": 5e8,
        "TotalEquity": 2e8,
        "TotalDebt": 1e8,
        "Cash": 5e7,
        "EBIT": 7e7,
        "EBITDA": 8e7,
        "OperatingMargin": 0.2,
        "ROE": 0.30,
        "ROA": 0.12,
    }


def test_fmp_only_source_skips_yfinance(hybrid: HybridDataFetcher) -> None:
    with (
        patch.object(hybrid._fmp, "extract_scoring_fields", return_value=_fmp_scoring_row()),
        patch.object(hybrid._fmp, "fetch_quote", return_value={"Price": 100.0, "MarketCap": 1e9, "Shares": 1e7}),
        patch.object(hybrid._yf, "fetch_full_row") as yf_mock,
    ):
        result = hybrid.fetch_single("AAPL", source="fmp")

    yf_mock.assert_not_called()
    assert result["effective_source"] == "fmp"
    assert result["source_fallback_message"] is None
    # yfinance.analysis injection (sub-project 2) supplies analyst fields even
    # in the fmp-only branch — accept "yfinance" as a valid source for those.
    assert all(v in ("fmp", "missing", "computed", "yfinance") for v in result["field_sources"].values())


def test_fmp_only_falls_back_to_yfinance_on_quota_exceeded(
    hybrid: HybridDataFetcher,
) -> None:
    with (
        patch.object(
            hybrid._fmp,
            "extract_scoring_fields",
            side_effect=FMPQuotaExceeded("daily cap"),
        ),
        patch.object(hybrid._yf, "fetch_full_row", return_value=_YF_ROW.copy()) as yf_mock,
    ):
        result = hybrid.fetch_single("AAPL", source="fmp")

    yf_mock.assert_called_once()
    assert result["effective_source"] == "yfinance"
    assert result["source_fallback_message"] is not None
    assert "FMP" in result["source_fallback_message"]
    assert "yfinance" in result["source_fallback_message"]


def test_fmp_only_falls_back_on_http_error(hybrid: HybridDataFetcher) -> None:
    with (
        patch.object(
            hybrid._fmp,
            "extract_scoring_fields",
            side_effect=FMPHTTPError(403, "forbidden"),
        ),
        patch.object(hybrid._yf, "fetch_full_row", return_value=_YF_ROW.copy()) as yf_mock,
    ):
        result = hybrid.fetch_single("AAPL", source="fmp")

    yf_mock.assert_called_once()
    assert result["effective_source"] == "yfinance"
    assert "error" in (result["source_fallback_message"] or "").lower()


def test_fmp_only_falls_back_when_fmp_disabled(
    tmp_cache: CacheService,
    tmp_path: Path,
) -> None:
    fmp = FMPDataFetcher(token="FAKE", cache=tmp_cache, daily_limit=240, enabled=False)
    fmp._quota = _QuotaTracker(path=tmp_path / "fmp_quota.json")
    yf = YFinanceDataFetcher(cache=tmp_cache)
    h = HybridDataFetcher(fmp=fmp, yf=yf, cache=tmp_cache)

    with patch.object(yf, "fetch_full_row", return_value=_YF_ROW.copy()):
        result = h.fetch_single("AAPL", source="fmp")

    assert result["effective_source"] == "yfinance"
    assert "disabled" in (result["source_fallback_message"] or "").lower()


def test_fmp_only_uses_fmp_cache_key(
    hybrid: HybridDataFetcher,
    tmp_cache: CacheService,
) -> None:
    with (
        patch.object(hybrid._fmp, "extract_scoring_fields", return_value=_fmp_scoring_row()),
        patch.object(hybrid._fmp, "fetch_quote", return_value={"Price": 100.0}),
    ):
        hybrid.fetch_single("AAPL", source="fmp")
    assert tmp_cache.get("fmp:AAPL") is not None
    assert tmp_cache.get("hybrid:AAPL") is None
    assert tmp_cache.get("yfinance:AAPL") is None


# ---------------------------------------------------------------------------
# Task 4: fetch_batch + fetch_analyst_ratings source kwarg
# ---------------------------------------------------------------------------


def test_fetch_batch_passes_source_through(hybrid: HybridDataFetcher) -> None:
    with patch.object(hybrid, "fetch_single") as single:
        single.return_value = {"Ticker": "X", "effective_source": "yfinance"}
        hybrid.fetch_batch(["A", "B"], source="yfinance")
    assert single.call_count == 2
    for call in single.call_args_list:
        assert call.kwargs.get("source") == "yfinance"


def test_fetch_analyst_ratings_yfinance_only_skips_fmp(
    hybrid: HybridDataFetcher,
) -> None:
    with (
        patch.object(hybrid._fmp, "fetch_analyst_targets") as fmp_mock,
        patch.object(
            hybrid._yf,
            "fetch_analyst_targets",
            return_value={"target_mean": 150.0},
        ) as yf_mock,
    ):
        result = hybrid.fetch_analyst_ratings("AAPL", source="yfinance")
    fmp_mock.assert_not_called()
    yf_mock.assert_called_once()
    assert result["target_mean"] == 150.0


def test_fetch_analyst_ratings_fmp_falls_back_on_quota(
    hybrid: HybridDataFetcher,
) -> None:
    with (
        patch.object(
            hybrid._fmp,
            "fetch_analyst_targets",
            side_effect=FMPQuotaExceeded("cap"),
        ),
        patch.object(
            hybrid._yf,
            "fetch_analyst_targets",
            return_value={"target_mean": 120.0},
        ) as yf_mock,
    ):
        result = hybrid.fetch_analyst_ratings("AAPL", source="fmp")
    yf_mock.assert_called_once()
    assert result["target_mean"] == 120.0
