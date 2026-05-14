"""Tests that HybridDataFetcher injects SUE + EPS revisions + earnings surprise
into the scoring row across all 4 fetch branches."""

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


# Phase 0 SUE: 8 quarters of dollar surprises, current quarter excluded from σ.
_HISTORY = [
    {"date": "2024-12-31", "eps_actual": 2.10, "eps_estimate": 2.00, "surprise_pct": 5.0},
    {"date": "2024-09-30", "eps_actual": 1.95, "eps_estimate": 1.90, "surprise_pct": 2.6},
    {"date": "2024-06-30", "eps_actual": 1.80, "eps_estimate": 1.85, "surprise_pct": -2.7},
    {"date": "2024-03-31", "eps_actual": 1.70, "eps_estimate": 1.65, "surprise_pct": 3.0},
    {"date": "2023-12-31", "eps_actual": 1.60, "eps_estimate": 1.55, "surprise_pct": 3.2},
    {"date": "2023-09-30", "eps_actual": 1.50, "eps_estimate": 1.55, "surprise_pct": -3.2},
    {"date": "2023-06-30", "eps_actual": 1.40, "eps_estimate": 1.35, "surprise_pct": 3.7},
    {"date": "2023-03-31", "eps_actual": 1.30, "eps_estimate": 1.30, "surprise_pct": 0.0},
]

_TREND = [
    {"period": "0q", "current": 5.20, "n_minus_7d": 5.18, "n_minus_30d": 5.00, "n_minus_60d": 4.95, "n_minus_90d": 4.80}
]

_REVISIONS = {
    "up_last_7d": 1,
    "down_last_7d": 0,
    "up_last_30d": 5,
    "down_last_30d": 1,
    "up_last_60d": 6,
    "down_last_60d": 1,
    "up_last_90d": 7,
    "down_last_90d": 2,
}

_GROWTH = {"fy_growth": 0.12, "five_year_growth": 0.10}


def _yf_row() -> dict:
    return {
        "Name": "Test Corp",
        "Sector": "Tech",
        "Country": "US",
        "Exchange": "NMS",
        "Price": 100.0,
        "MarketCap": 1e9,
        "Shares": 1e7,
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


def _patch_analyst(hybrid: HybridDataFetcher):
    """Apply all 4 yfinance.analysis mocks the injector consumes."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch.object(hybrid._yf, "fetch_earnings_history", return_value=_HISTORY))
    stack.enter_context(patch.object(hybrid._yf, "fetch_eps_trend", return_value=_TREND))
    stack.enter_context(patch.object(hybrid._yf, "fetch_eps_revisions", return_value=_REVISIONS))
    stack.enter_context(patch.object(hybrid._yf, "fetch_growth_estimates", return_value=_GROWTH))
    return stack


def test_yfinance_branch_injects_all_analyst_signals(hybrid: HybridDataFetcher) -> None:
    with patch.object(hybrid._yf, "fetch_full_row", return_value=_yf_row()), _patch_analyst(hybrid):
        result = hybrid.fetch_single("AAPL", source="yfinance")

    assert result["SUE"] is not None
    assert result["EpsRevision30d"] is not None
    assert abs(result["EpsRevision30d"] - 0.04) < 1e-6
    assert result["EpsRevision90d"] is not None
    assert result["EarningsSurprise"] == 5.0
    assert result["EpsRevisionsUp30d"] == 5
    assert result["EpsRevisionsDown30d"] == 1
    assert result["GrowthEstimateFY"] == 0.12
    assert result["field_sources"]["SUE"] == "yfinance"
    assert result["field_sources"]["EpsRevision30d"] == "yfinance"


def test_hybrid_branch_also_injects(hybrid: HybridDataFetcher) -> None:
    with (
        patch.object(hybrid._yf, "fetch_full_row", return_value=_yf_row()),
        patch.object(hybrid._fmp, "extract_scoring_fields", return_value={}),
        patch.object(hybrid._fmp, "fetch_quote", return_value={}),
        _patch_analyst(hybrid),
    ):
        result = hybrid.fetch_single("AAPL", source="hybrid")
    assert result["SUE"] is not None
    assert result["EpsRevision30d"] is not None


def test_fmp_branch_also_injects(hybrid: HybridDataFetcher) -> None:
    with (
        patch.object(hybrid._fmp, "extract_scoring_fields", return_value={"Revenue": 4e8}),
        patch.object(hybrid._fmp, "fetch_quote", return_value={"Price": 100.0, "MarketCap": 1e9}),
        _patch_analyst(hybrid),
    ):
        result = hybrid.fetch_single("AAPL", source="fmp")
    assert result["SUE"] is not None
    assert result["EarningsSurprise"] == 5.0


def test_injection_swallows_failures(hybrid: HybridDataFetcher) -> None:
    """If any of the 4 analyst fetchers fail, the scoring row stays valid."""
    with (
        patch.object(hybrid._yf, "fetch_full_row", return_value=_yf_row()),
        patch.object(hybrid._yf, "fetch_earnings_history", side_effect=RuntimeError("boom")),
        patch.object(hybrid._yf, "fetch_eps_trend", side_effect=RuntimeError("boom")),
        patch.object(hybrid._yf, "fetch_eps_revisions", side_effect=RuntimeError("boom")),
        patch.object(hybrid._yf, "fetch_growth_estimates", side_effect=RuntimeError("boom")),
    ):
        result = hybrid.fetch_single("AAPL", source="yfinance")
    # SUE/EpsRevision30d remain NaN; row still valid
    assert result["field_sources"]["SUE"] == "missing"


# ---------------------------------------------------------------------------
# Task 6: fetch_analyst_ratings returns the full enriched shape
# ---------------------------------------------------------------------------


def test_fetch_analyst_ratings_returns_full_shape(hybrid: HybridDataFetcher) -> None:
    rec = {"strong_buy": 12, "buy": 20, "hold": 8, "sell": 2, "strong_sell": 0}
    upgrades = [
        {"date": "2025-04-01", "firm": "GS", "to_grade": "Buy", "from_grade": "Hold", "action": "up"},
    ]
    with (
        patch.object(hybrid._yf, "fetch_analyst_targets", return_value={"target_mean": 220.0, "num_analysts": 42}),
        patch.object(hybrid._yf, "fetch_recommendations_summary", return_value=rec),
        patch.object(hybrid._yf, "fetch_upgrades_downgrades", return_value=upgrades),
        patch.object(hybrid._yf, "fetch_growth_estimates", return_value=_GROWTH),
        patch.object(hybrid._yf, "fetch_earnings_history", return_value=_HISTORY),
        patch.object(hybrid._yf, "fetch_eps_revisions", return_value=_REVISIONS),
    ):
        out = hybrid.fetch_analyst_ratings("AAPL", source="yfinance")

    assert out is not None
    assert out["target_mean"] == 220.0
    assert out["num_analysts"] == 42
    assert out["buy"] == 20
    assert out["strong_buy"] == 12
    assert out["recent_changes"][0]["firm"] == "GS"
    assert out["growth_estimate_fy"] == 0.12
    assert len(out["earnings_history"]) == 8
    assert len(out["revisions_history"]) == 4
    assert {row["period"] for row in out["revisions_history"]} == {"7d", "30d", "60d", "90d"}
