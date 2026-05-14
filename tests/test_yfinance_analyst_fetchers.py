"""Tests for the new yfinance.analysis fetcher methods + SCORING_COLUMNS additions."""
from __future__ import annotations

from backend.app.services.data_fetcher import EXTRA_FIELDS, SCORING_COLUMNS


def test_new_analyst_scoring_columns_declared() -> None:
    """The columns the scoring engine already reads must exist in SCORING_COLUMNS."""
    required = {
        "EpsRevision30d", "EpsRevision90d", "SUE", "EarningsSurprise",
        "GrowthEstimateFY", "EpsRevisionsUp30d", "EpsRevisionsDown30d",
    }
    missing = required - set(SCORING_COLUMNS)
    assert not missing, f"Missing scoring columns: {missing}"


def test_new_recommendation_fields_in_extra() -> None:
    required = {
        "RecommendationsBuy", "RecommendationsHold", "RecommendationsSell",
        "RecommendationsStrongBuy", "RecommendationsStrongSell",
    }
    missing = required - set(EXTRA_FIELDS)
    assert not missing


# ---------------------------------------------------------------------------
# yfinance.analysis fetcher methods (Task 2)
# ---------------------------------------------------------------------------

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher


@pytest.fixture
def fetcher(tmp_path: Path) -> YFinanceDataFetcher:
    return YFinanceDataFetcher(cache=CacheService(cache_dir=tmp_path / "cache"))


def test_fetch_recommendations_summary(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.recommendations_summary = pd.DataFrame(
        {
            "period": ["0m", "-1m", "-2m", "-3m"],
            "strongBuy": [12, 11, 10, 9],
            "buy": [18, 19, 20, 20],
            "hold": [8, 9, 9, 10],
            "sell": [2, 2, 3, 3],
            "strongSell": [0, 0, 1, 1],
        }
    )
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_recommendations_summary("AAPL")
    assert out["strong_buy"] == 12
    assert out["buy"] == 18
    assert out["hold"] == 8
    assert out["sell"] == 2
    assert out["strong_sell"] == 0


def test_fetch_recommendations_summary_empty(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.recommendations_summary = pd.DataFrame()
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_recommendations_summary("ZZZZZ")
    assert out == {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}


def test_fetch_eps_revisions_casing_trap(fetcher: YFinanceDataFetcher) -> None:
    """yfinance casing trap: upLast7days lowercase but downLast7Days capital D."""
    fake_tk = MagicMock()
    fake_tk.eps_revisions = pd.DataFrame(
        {
            "upLast7days": [3, 2, 1, 1],
            "downLast7Days": [1, 1, 0, 0],
            "upLast30days": [5, 4, 3, 2],
            "downLast30days": [1, 2, 1, 1],
        },
        index=["0q", "+1q", "0y", "+1y"],
    )
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_eps_revisions("AAPL")
    assert out["up_last_30d"] == 5
    assert out["down_last_30d"] == 1
    assert out["up_last_7d"] == 3
    assert out["down_last_7d"] == 1


def test_fetch_eps_trend(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.eps_trend = pd.DataFrame(
        {
            "current": [5.20, 22.50],
            "7daysAgo": [5.18, 22.45],
            "30daysAgo": [5.00, 22.20],
            "60daysAgo": [4.95, 22.00],
            "90daysAgo": [4.80, 21.80],
        },
        index=["0q", "+1q"],
    )
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_eps_trend("AAPL")
    assert len(out) == 2
    assert out[0]["current"] == 5.20
    assert out[0]["n_minus_30d"] == 5.00
    assert out[0]["n_minus_90d"] == 4.80


def test_fetch_earnings_history(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.earnings_history = pd.DataFrame(
        {
            "epsActual": [2.10, 1.95, 1.80, 1.70],
            "epsEstimate": [2.00, 1.90, 1.85, 1.65],
            "epsDifference": [0.10, 0.05, -0.05, 0.05],
            "surprisePercent": [5.0, 2.6, -2.7, 3.0],
        },
        index=pd.to_datetime(["2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31"]),
    )
    with patch("yfinance.Ticker", return_value=fake_tk):
        rows = fetcher.fetch_earnings_history("AAPL")
    assert len(rows) == 4
    assert rows[0]["eps_actual"] == 2.10
    assert rows[0]["surprise_pct"] == 5.0
    assert rows[0]["date"] == "2024-12-31"


def test_fetch_growth_estimates(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.growth_estimates = pd.DataFrame(
        {"stockTrend": [0.10, 0.12, 0.08, 0.09, 0.07], "indexTrend": [0.05] * 5},
        index=["0q", "+1q", "0y", "+1y", "LTG"],
    )
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_growth_estimates("AAPL")
    # +1y → fy_growth; LTG → five_year_growth (acceptable mapping)
    assert out["fy_growth"] is not None
    assert out["fy_growth"] == 0.09


def test_fetch_upgrades_downgrades(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.upgrades_downgrades = pd.DataFrame(
        {
            "Firm": ["GS", "MS", "JPM"],
            "ToGrade": ["Buy", "Overweight", "Buy"],
            "FromGrade": ["Hold", "Equal-Weight", "Hold"],
            "Action": ["up", "up", "up"],
        },
        index=pd.to_datetime(["2025-04-01", "2025-03-15", "2025-02-20"]),
    )
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_upgrades_downgrades("AAPL", limit=3)
    assert len(out) == 3
    assert out[0]["firm"] == "GS"
    assert out[0]["to_grade"] == "Buy"
    assert out[0]["date"] == "2025-04-01"


def test_fetch_all_methods_swallow_exceptions(fetcher: YFinanceDataFetcher) -> None:
    """Each fetcher should return its zero-value default on yfinance failure."""
    with patch("yfinance.Ticker", side_effect=RuntimeError("boom")):
        assert fetcher.fetch_recommendations_summary("X") == {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
        assert fetcher.fetch_eps_trend("X") == []
        assert fetcher.fetch_earnings_history("X") == []
        assert fetcher.fetch_growth_estimates("X") == {"fy_growth": None, "five_year_growth": None}
        assert fetcher.fetch_upgrades_downgrades("X") == []


# ---------------------------------------------------------------------------
# Task 3: Pydantic + horizon model extensions
# ---------------------------------------------------------------------------


def test_analyst_ratings_model_extension() -> None:
    from backend.app.models.company import (
        AnalystChange,
        AnalystRatings,
        EarningsHistoryRow,
        EpsRevisionRow,
    )

    ar = AnalystRatings(
        buy=20, hold=8, sell=2, strong_buy=12, strong_sell=0,
        target_low=180.0, target_mean=220.0, target_high=260.0, target_median=215.0,
        num_analysts=42,
        recent_changes=[
            AnalystChange(date="2025-04-01", firm="GS", from_grade="Hold", to_grade="Buy", action="up"),
        ],
        revisions_history=[EpsRevisionRow(period="7d", up=3, down=1)],
        growth_estimate_fy=0.12,
        earnings_history=[
            EarningsHistoryRow(date="2024-12-31", eps_actual=2.10, eps_estimate=2.00, surprise_pct=5.0),
        ],
    )
    assert ar.num_analysts == 42
    assert ar.recent_changes[0].firm == "GS"
    assert ar.growth_estimate_fy == 0.12
    assert ar.earnings_history[0].eps_actual == 2.10


def test_momentum_signals_eps_trend_extension() -> None:
    from backend.app.models.horizons import EpsEstimateTrendRow, MomentumSignals

    m = MomentumSignals(
        eps_estimate_trend=[
            EpsEstimateTrendRow(period="0q", current=5.20, n_minus_30d=5.00, n_minus_90d=4.80),
        ],
    )
    assert m.eps_estimate_trend[0].current == 5.20
    assert m.eps_estimate_trend[0].n_minus_90d == 4.80

