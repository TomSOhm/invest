"""Tests for company_service ↔ screener_cache integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.services import screener_cache
from backend.app.services.company_service import CompanyService


@pytest.fixture(autouse=True)
def _reset_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    screener_cache.reset_for_tests()
    monkeypatch.setattr(screener_cache, "_CACHE_PATH", tmp_path / "scored.parquet")
    monkeypatch.setattr(screener_cache, "_META_PATH", tmp_path / "scored.meta.json")
    yield
    screener_cache.reset_for_tests()


def _scored_row_dict(ticker: str = "MC.PA") -> dict:
    """Approximation of a scored row from the cache."""
    return {
        "Price": 700.0,
        "Name": "LVMH",
        "Sector": "Consumer Cyclical",
        "Industry": "Luxury Goods",
        "Country": "FR",
        "Exchange": "Euronext Paris",
        "PEA": True,
        "PEA_PME": False,
        "MarketCap": 350e9,
        "EV": 360e9,
        "PE": 24.0,
        "PB": 5.5,
        "PS": 3.6,
        "PFCF": 22.0,
        "EV_EBITDA": 14.0,
        "EV_Sales": 3.6,
        "ROE": 0.21,
        "ROA": 0.10,
        "ROIC": 0.18,
        "GrossMargin": 0.68,
        "OperatingMargin": 0.27,
        "NetMargin": 0.20,
        "FCFMargin": 0.19,
        "RevenueGrowth": 0.05,
        "CurrentRatio": 1.4,
        "DebtEquity": 0.35,
        "InterestCoverage": 14.0,
        "DivYield": 0.018,
        "PayoutRatio": 0.40,
        "Beta": 1.05,
        "FiftyTwoWeekHigh": 800.0,
        "FiftyTwoWeekLow": 600.0,
        # Already-scored output columns
        "Composite_Score": 75.0,
        "Signal": "Buy",
        "score_lt": 75.0,
        "score_mt": 70.0,
        "score_st": 65.0,
        "signal_lt": "Buy",
        "signal_mt": "Hold",
        "signal_st": "Hold",
        "passes_gates_lt": True,
        "passes_gates_mt": True,
        "passes_gates_st": True,
        "Valuation_Score": 60.0,
        "Health_Score": 80.0,
        "Profitability_Score": 90.0,
        "Growth_Score": 65.0,
        "Shareholder_Score": 60.0,
        "Risk_Score": 70.0,
        "Piotroski_F": 7,
        "Altman_Z": 4.2,
        "Graham_Number": 350.0,
        "data_completeness": 0.95,
    }


def test_cache_hit_marks_score_source_universe() -> None:
    fetcher = MagicMock()
    # Ratings call still happens — return an empty dict to keep the response
    # builder happy.
    fetcher.fetch_analyst_ratings.return_value = None
    scorer = MagicMock()
    # When the row is already scored, extract_scoring_from_row is what gets
    # called — return a minimal dict shaped like score_single's output.
    scorer.extract_scoring_from_row.return_value = {
        "valuation_score": 60.0,
        "health_score": 80.0,
        "profitability_score": 90.0,
        "growth_score": 65.0,
        "shareholder_score": 60.0,
        "risk_score": 70.0,
        "piotroski_f": 7,
        "altman_z": 4.2,
        "altman_zone": "Safe",
        "graham_number": 350.0,
        "graham_mos": -50.0,
        "earnings_quality_score": None,
        "moat_score": None,
        "m_score": None,
        "sloan_accruals": None,
        "cash_conversion_ratio_5y": None,
        "dcf": {
            "fair_value_low": None,
            "fair_value_mid": None,
            "fair_value_high": None,
            "mos_low": None,
            "mos_mid": None,
            "mos_high": None,
            "wacc_used": None,
            "warnings": [],
        },
        "risk": {
            "risk_score": None,
            "realized_vol_1y": None,
            "max_drawdown_3y": None,
            "net_debt_ebitda": None,
            "interest_coverage": 14.0,
            "beta": 1.05,
        },
        "momentum": {
            "momentum_12_1": None,
            "rs_3m": None,
            "above_50dma": None,
            "above_200dma": None,
            "golden_cross": None,
            "volume_surge": None,
            "eps_revision_30d": None,
            "eps_revision_90d": None,
            "sue_z_score": None,
            "sentiment_30d": None,
            "sentiment_trend": None,
        },
        "horizons": {
            "long_term": {
                "score": 75.0,
                "signal": "Buy",
                "passes_gates": True,
                "blockers": [],
                "recommended_account": None,
            },
            "medium_term": {
                "score": 70.0,
                "signal": "Hold",
                "passes_gates": True,
                "blockers": [],
                "recommended_account": None,
            },
            "short_term": {
                "score": 65.0,
                "signal": "Hold",
                "passes_gates": True,
                "blockers": [],
                "recommended_account": "CTO",
            },
        },
        "data_completeness": 0.95,
    }

    # Seed cache with our row
    df = pd.DataFrame([_scored_row_dict("MC.PA")], index=pd.Index(["MC.PA"], name="Ticker"))
    with patch.object(screener_cache, "_state") as state:
        state.scored_df = df
        state.last_refreshed = None
        state.tickers_failed = []
        # Re-bind the module-level _state attribute (not just the patched mock)
        screener_cache._state.scored_df = df
        svc = CompanyService(fetcher=fetcher, scorer=scorer)
        result = svc.get_detail("MC.PA")

    assert result["score_source"] == "universe"
    assert result["horizons"]["long_term"]["score"] == 75.0
    # The live fetch_single must NOT have been called when cache hits
    fetcher.fetch_single.assert_not_called()
    # extract_scoring_from_row was called (cache path), not score_single
    scorer.extract_scoring_from_row.assert_called_once()
    scorer.score_single.assert_not_called()


def test_cache_miss_falls_back_to_single_row() -> None:
    fetcher = MagicMock()
    fetcher.fetch_single.return_value = _scored_row_dict("AAPL")
    fetcher.fetch_analyst_ratings.return_value = None
    scorer = MagicMock()
    scorer.score_single.return_value = {
        "valuation_score": 50.0,
        "health_score": 50.0,
        "profitability_score": 50.0,
        "growth_score": 50.0,
        "shareholder_score": 50.0,
        "risk_score": 50.0,
        "piotroski_f": 5,
        "altman_z": 3.0,
        "altman_zone": "Safe",
        "graham_number": None,
        "graham_mos": None,
        "earnings_quality_score": None,
        "moat_score": None,
        "m_score": None,
        "sloan_accruals": None,
        "cash_conversion_ratio_5y": None,
        "dcf": {
            "fair_value_low": None,
            "fair_value_mid": None,
            "fair_value_high": None,
            "mos_low": None,
            "mos_mid": None,
            "mos_high": None,
            "wacc_used": None,
            "warnings": [],
        },
        "risk": {
            "risk_score": None,
            "realized_vol_1y": None,
            "max_drawdown_3y": None,
            "net_debt_ebitda": None,
            "interest_coverage": None,
            "beta": None,
        },
        "momentum": {
            "momentum_12_1": None,
            "rs_3m": None,
            "above_50dma": None,
            "above_200dma": None,
            "golden_cross": None,
            "volume_surge": None,
            "eps_revision_30d": None,
            "eps_revision_90d": None,
            "sue_z_score": None,
            "sentiment_30d": None,
            "sentiment_trend": None,
        },
        "horizons": {
            "long_term": {
                "score": 50.0,
                "signal": "Hold",
                "passes_gates": True,
                "blockers": [],
                "recommended_account": None,
            },
            "medium_term": {
                "score": 50.0,
                "signal": "Hold",
                "passes_gates": True,
                "blockers": [],
                "recommended_account": None,
            },
            "short_term": {
                "score": 50.0,
                "signal": "Hold",
                "passes_gates": True,
                "blockers": [],
                "recommended_account": "CTO",
            },
        },
        "data_completeness": 0.5,
    }

    # Cache is empty — falls back to live fetch + score_single
    svc = CompanyService(fetcher=fetcher, scorer=scorer)
    result = svc.get_detail("AAPL")

    assert result["score_source"] == "single_row_fallback"
    fetcher.fetch_single.assert_called_once_with("AAPL", source="hybrid")
    scorer.score_single.assert_called_once()


def test_company_service_threads_source_and_bypasses_universe_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When source != 'hybrid', skip the screener cache and force a live fetch
    so the user-chosen backend actually feeds the response."""
    fetcher = MagicMock()
    fetcher.fetch_single.return_value = {
        "Ticker": "AAPL",
        "Name": "Apple",
        "Sector": "Tech",
        "Country": "US",
        "Price": 150.0,
        "MarketCap": 3e12,
        "PEA": False,
        "PEA_PME": False,
        "effective_source": "yfinance",
        "source_fallback_message": "FMP daily quota exhausted; using yfinance for this fetch.",
    }
    fetcher.fetch_analyst_ratings.return_value = None

    scorer = MagicMock()
    scorer.score_single.return_value = {
        "horizons": {},
        "dcf": {},
        "risk": {},
        "momentum": {},
        "valuation_score": 50.0,
        "health_score": 50.0,
        "profitability_score": 50.0,
        "growth_score": 50.0,
        "shareholder_score": 50.0,
        "risk_score": 50.0,
    }

    # Even if the screener cache *would* have a row, source='fmp' must bypass it.
    monkeypatch.setattr(screener_cache, "lookup", lambda t: {"Price": 999.0})

    svc = CompanyService(fetcher=fetcher, scorer=scorer)
    result = svc.get_detail("AAPL", source="fmp")

    fetcher.fetch_single.assert_called_with("AAPL", source="fmp")
    fetcher.fetch_analyst_ratings.assert_called_with("AAPL", source="fmp")
    assert result["data_source"] == "fmp"
    assert result["effective_source"] == "yfinance"
    assert "FMP" in result["source_fallback_message"]
    assert result["score_source"] == "single_row_fallback"
