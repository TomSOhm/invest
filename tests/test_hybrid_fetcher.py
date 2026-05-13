"""
Tests for HybridDataFetcher -- FMP-first per-field fallback.

All FMP HTTP calls are mocked; no live API calls are made.
yfinance calls are also mocked except for @pytest.mark.live tests.

Coverage:
  - test_fmp_supplies_field_when_available
  - test_falls_through_to_yfinance_on_fmp_404
  - test_falls_through_to_nan_when_both_missing
  - test_quota_counter_increments
  - test_quota_exhausted_skips_fmp
  - test_ticker_symbol_mapping
  - test_field_sources_populated
  - test_data_completeness_computed
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.fmp_fetcher import (
    FMPDataFetcher,
    FMPQuotaExceeded,
    _QuotaTracker,
    _to_fmp_symbol,
)
from backend.app.services.market_data.hybrid_fetcher import HybridDataFetcher
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_cache(tmp_path: Path) -> CacheService:
    """CacheService backed by a temporary directory (isolated per test)."""
    return CacheService(cache_dir=tmp_path / "cache")


@pytest.fixture
def quota_tracker(tmp_path: Path) -> _QuotaTracker:
    """QuotaTracker backed by a temp file."""
    return _QuotaTracker(path=tmp_path / "fmp_quota.json")


@pytest.fixture
def fmp_fetcher(tmp_cache: CacheService, quota_tracker: _QuotaTracker) -> FMPDataFetcher:
    """FMPDataFetcher with a real token (not used -- all HTTP mocked) and temp quota."""
    fetcher = FMPDataFetcher(token="FAKE_TOKEN", cache=tmp_cache, daily_limit=240, enabled=True)
    fetcher._quota = quota_tracker
    return fetcher


@pytest.fixture
def yf_fetcher(tmp_cache: CacheService) -> YFinanceDataFetcher:
    return YFinanceDataFetcher(cache=tmp_cache)


@pytest.fixture
def hybrid(
    fmp_fetcher: FMPDataFetcher,
    yf_fetcher: YFinanceDataFetcher,
    tmp_cache: CacheService,
) -> HybridDataFetcher:
    return HybridDataFetcher(fmp=fmp_fetcher, yf=yf_fetcher, cache=tmp_cache)


# Minimal yfinance full_row that provides enough fields to not crash
_MINIMAL_YF_ROW: dict[str, Any] = {
    "Name": "Test Corp",
    "Sector": "Technology",
    "Industry": "Software",
    "Country": "US",
    "Exchange": "NMS",
    "Price": 150.0,
    "MarketCap": 1_000_000_000.0,
    "EV": 950_000_000.0,
    "Shares": 6_666_667.0,
    "Beta": 1.1,
    "AvgVolume": 1_000_000.0,
    "FiftyTwoWeekHigh": 200.0,
    "FiftyTwoWeekLow": 100.0,
    "ForwardPE": 20.0,
    "PEG": 1.5,
    "PE": 22.0,
    "PB": 3.0,
    "PS": 2.5,
    "PFCF": 18.0,
    "EV_EBITDA": 12.0,
    "EV_Sales": 2.2,
    "Revenue": 400_000_000.0,
    "EBITDA": 80_000_000.0,
    "EBIT": 70_000_000.0,
    "NetIncome": 50_000_000.0,
    "FCF": 40_000_000.0,
    "OperatingCashflow": 60_000_000.0,
    "CapEx": 20_000_000.0,
    "TotalAssets": 500_000_000.0,
    "TotalEquity": 200_000_000.0,
    "TotalDebt": 100_000_000.0,
    "Cash": 50_000_000.0,
    "CurrentAssets": 120_000_000.0,
    "CurrentLiabilities": 80_000_000.0,
    "RetainedEarnings": 90_000_000.0,
    "GrossMargin": 0.60,
    "OperatingMargin": 0.175,
    "NetMargin": 0.125,
    "FCFMargin": 0.10,
    "ROE": 0.25,
    "ROA": 0.10,
    "ROIC": 0.18,
    "RevenueGrowth": 0.12,
    "CurrentRatio": 1.5,
    "DebtEquity": 0.5,
    "InterestCoverage": 8.0,
    "DivYield": 0.015,
    "PayoutRatio": 0.25,
    "InsiderPct": 0.05,
    "InstitutionalPct": 0.70,
    "ShortPctFloat": 0.02,
    "YearsListed": 10.0,
    "Shares_PriorYear": 6_500_000.0,
    "PEA": False,
    "PEA_PME": False,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFMPSuppliesField:
    """FMP returns a valid EBIT; hybrid should use it with source='fmp'."""

    def test_fmp_supplies_ebit_when_available(self, hybrid: HybridDataFetcher) -> None:
        fmp_ebit_value = 85_000_000.0

        fmp_fields = {
            **{
                k: np.nan
                for k in [
                    "Revenue",
                    "EBITDA",
                    "NetIncome",
                    "OperatingCashflow",
                    "FCF",
                    "CapEx",
                    "TotalAssets",
                    "TotalEquity",
                    "TotalDebt",
                    "Cash",
                    "CurrentAssets",
                    "CurrentLiabilities",
                    "RetainedEarnings",
                    "GrossMargin",
                    "OperatingMargin",
                    "NetMargin",
                    "RevenueGrowth",
                    "ROE",
                    "ROA",
                ]
            },
            "EBIT": fmp_ebit_value,
        }

        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value=fmp_fields):
            with patch.object(hybrid._fmp, "fetch_quote", return_value={}):
                with patch.object(hybrid._yf, "fetch_full_row", return_value=_MINIMAL_YF_ROW):
                    result = hybrid.fetch_single("AAPL")

        assert abs(result["EBIT"] - fmp_ebit_value) < 1, f"Expected EBIT={fmp_ebit_value}, got {result['EBIT']}"
        assert result["field_sources"]["EBIT"] == "fmp", (
            f"Expected source='fmp', got '{result['field_sources']['EBIT']}'"
        )


class TestFallThroughOnFMP404:
    """FMP raises FMPHTTPError(404); hybrid should use yfinance value."""

    def test_yfinance_used_when_fmp_returns_empty(self, hybrid: HybridDataFetcher) -> None:
        # FMP extract_scoring_fields returns an empty dict (simulating 404)
        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value={}):
            with patch.object(hybrid._fmp, "fetch_quote", return_value={}):
                with patch.object(hybrid._yf, "fetch_full_row", return_value=_MINIMAL_YF_ROW):
                    result = hybrid.fetch_single("MC.PA")

        # yfinance EBIT should be used
        assert abs(result["EBIT"] - _MINIMAL_YF_ROW["EBIT"]) < 1, f"Expected yfinance EBIT, got {result['EBIT']}"
        assert result["field_sources"]["EBIT"] == "yfinance", (
            f"Expected source='yfinance', got '{result['field_sources']['EBIT']}'"
        )


class TestFallThroughToNaNWhenBothMissing:
    """Both FMP and yfinance fail for a field; value must be NaN, source='missing'."""

    def test_nan_when_both_sources_missing(self, hybrid: HybridDataFetcher) -> None:
        yf_row_no_ebit = {**_MINIMAL_YF_ROW, "EBIT": np.nan}

        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value={}):
            with patch.object(hybrid._fmp, "fetch_quote", return_value={}):
                with patch.object(hybrid._yf, "fetch_full_row", return_value=yf_row_no_ebit):
                    result = hybrid.fetch_single("UNKNOWN.PA")

        assert math.isnan(result["EBIT"]), f"Expected NaN for EBIT, got {result['EBIT']}"
        assert result["field_sources"]["EBIT"] == "missing", (
            f"Expected source='missing', got '{result['field_sources']['EBIT']}'"
        )


class TestQuotaCounter:
    """Quota counter increments and trips correctly."""

    def test_quota_counter_increments(
        self,
        fmp_fetcher: FMPDataFetcher,
        quota_tracker: _QuotaTracker,
    ) -> None:
        initial = quota_tracker.get_count()

        with patch("backend.app.services.market_data.fmp_fetcher._http_get") as mock_http:
            mock_http.return_value = [
                {
                    "price": 100,
                    "marketCap": 1e9,
                    "sharesOutstanding": 1e7,
                    "avgVolume": 5e5,
                    "beta": 1.0,
                    "yearHigh": 120,
                    "yearLow": 80,
                    "pe": 20,
                    "enterpriseValue": 9e8,
                }
            ]
            fmp_fetcher.fetch_quote("AAPL")

        # Post /stable/ migration, fetch_quote pulls from three endpoints:
        # /quote (base) + /profile (beta, avg volume) + /ratios-ttm (PE).
        # Each successful call increments the quota tracker by 1.
        assert quota_tracker.get_count() == initial + 3, (
            f"Expected count {initial + 3}, got {quota_tracker.get_count()}"
        )

    def test_quota_exhausted_skips_fmp(
        self,
        fmp_fetcher: FMPDataFetcher,
        quota_tracker: _QuotaTracker,
    ) -> None:
        # Force quota to the limit
        data = {"date": quota_tracker._today(), "count": 240}
        quota_tracker._save(data)

        with pytest.raises(FMPQuotaExceeded):
            fmp_fetcher.fetch_quote("AAPL")

    def test_quota_counter_resets_on_new_day(
        self,
        quota_tracker: _QuotaTracker,
    ) -> None:
        # Simulate yesterday's data
        old_data = {"date": "2020-01-01", "count": 239}
        quota_tracker._save(old_data)

        # Today's read should reset
        count = quota_tracker.get_count()
        assert count == 0, f"Expected 0 after day rollover, got {count}"

    def test_hybrid_falls_through_when_quota_exhausted(
        self, hybrid: HybridDataFetcher, quota_tracker: _QuotaTracker
    ) -> None:
        # Exhaust FMP quota
        quota_tracker._save({"date": quota_tracker._today(), "count": 240})

        with patch.object(hybrid._yf, "fetch_full_row", return_value=_MINIMAL_YF_ROW):
            result = hybrid.fetch_single("MSFT")

        # Should still return a row (from yfinance)
        assert result is not None
        assert abs(result["Price"] - _MINIMAL_YF_ROW["Price"]) < 0.01
        # All fundamental fields should be "yfinance" or "missing" (not "fmp")
        for col, src in result["field_sources"].items():
            assert src != "fmp", f"Field {col} should not come from FMP when quota is exhausted, but got source='{src}'"


class TestTickerSymbolMapping:
    """_to_fmp_symbol() maps yfinance tickers to FMP equivalents."""

    def test_pa_suffix_unchanged(self) -> None:
        assert _to_fmp_symbol("MC.PA") == "MC.PA"

    def test_as_suffix_mapped_to_ams(self) -> None:
        assert _to_fmp_symbol("ASML.AS") == "ASML.AMS"

    def test_de_suffix_mapped_to_f(self) -> None:
        assert _to_fmp_symbol("SAP.DE") == "SAP.F"

    def test_sw_suffix_unchanged(self) -> None:
        assert _to_fmp_symbol("NESN.SW") == "NESN.SW"

    def test_l_suffix_unchanged(self) -> None:
        assert _to_fmp_symbol("ULVR.L") == "ULVR.L"

    def test_us_ticker_unchanged(self) -> None:
        assert _to_fmp_symbol("AAPL") == "AAPL"
        assert _to_fmp_symbol("BRK-B") == "BRK-B"

    def test_case_insensitive(self) -> None:
        assert _to_fmp_symbol("asml.as") == "asml.AMS"


class TestFieldSourcesPopulated:
    """field_sources dict is populated for all SCORING_COLUMNS."""

    def test_all_scoring_columns_have_source(self, hybrid: HybridDataFetcher) -> None:
        from backend.app.services.data_fetcher import SCORING_COLUMNS

        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value={}):
            with patch.object(hybrid._fmp, "fetch_quote", return_value={}):
                with patch.object(hybrid._yf, "fetch_full_row", return_value=_MINIMAL_YF_ROW):
                    result = hybrid.fetch_single("AAPL")

        sources = result["field_sources"]
        for col in SCORING_COLUMNS:
            assert col in sources, f"field_sources missing entry for SCORING_COLUMN '{col}'"
            assert sources[col] in ("fmp", "yfinance", "missing"), f"Invalid source '{sources[col]}' for column '{col}'"


class TestDataCompleteness:
    """data_completeness is a float in [0,1] based on finite SCORING_COLUMNS."""

    def test_completeness_between_zero_and_one(self, hybrid: HybridDataFetcher) -> None:
        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value={}):
            with patch.object(hybrid._fmp, "fetch_quote", return_value={}):
                with patch.object(hybrid._yf, "fetch_full_row", return_value=_MINIMAL_YF_ROW):
                    result = hybrid.fetch_single("AAPL")

        dc = result["data_completeness"]
        assert isinstance(dc, float), f"Expected float, got {type(dc)}"
        assert 0.0 <= dc <= 1.0, f"data_completeness out of range: {dc}"

    def test_completeness_zero_when_all_nan(self, hybrid: HybridDataFetcher) -> None:
        # Return empty row from yfinance (all NaN)
        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value={}):
            with patch.object(hybrid._fmp, "fetch_quote", return_value={}):
                with patch.object(hybrid._yf, "fetch_full_row", return_value={}):
                    result = hybrid.fetch_single("GHOST.PA")

        assert result["data_completeness"] == 0.0, (
            f"Expected 0.0 completeness for empty row, got {result['data_completeness']}"
        )

    def test_completeness_higher_with_fmp_overlay(self, hybrid: HybridDataFetcher) -> None:
        # yfinance-only row: all NaN except identification
        yf_row_sparse = {
            "Name": "Sparse Corp",
            "Sector": "",
            "Industry": "",
            "Country": "US",
            "Exchange": "NMS",
            "PEA": False,
            "PEA_PME": False,
        }
        # FMP provides fundamentals
        fmp_fields = {
            "Revenue": 500e6,
            "EBIT": 80e6,
            "NetIncome": 55e6,
            "TotalAssets": 800e6,
            "TotalEquity": 300e6,
            "TotalDebt": 150e6,
            "Cash": 80e6,
            "CurrentAssets": 200e6,
            "CurrentLiabilities": 100e6,
            "RetainedEarnings": 120e6,
            "GrossMargin": 0.55,
            "OperatingMargin": 0.16,
            "NetMargin": 0.11,
            "RevenueGrowth": 0.08,
            "ROE": 0.18,
            "ROA": 0.07,
            "FCF": 45e6,
            "OperatingCashflow": 70e6,
            "CapEx": 25e6,
            "EBITDA": 95e6,
        }
        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value=fmp_fields):
            with patch.object(
                hybrid._fmp,
                "fetch_quote",
                return_value={
                    "Price": 120.0,
                    "MarketCap": 2e9,
                    "EV": 2.1e9,
                    "Shares": 1.6e7,
                    "Beta": 1.2,
                    "AvgVolume": 8e5,
                },
            ):
                with patch.object(hybrid._yf, "fetch_full_row", return_value=yf_row_sparse):
                    result_with_fmp = hybrid.fetch_single("SPARSE")

        # Bust cache to get clean yfinance-only result
        hybrid._cache.invalidate("hybrid:SPARSE")

        with patch.object(hybrid._fmp, "extract_scoring_fields", return_value={}):
            with patch.object(hybrid._fmp, "fetch_quote", return_value={}):
                with patch.object(hybrid._yf, "fetch_full_row", return_value=yf_row_sparse):
                    result_no_fmp = hybrid.fetch_single("SPARSE")

        assert result_with_fmp["data_completeness"] > result_no_fmp["data_completeness"], (
            "FMP overlay should improve data_completeness"
        )
