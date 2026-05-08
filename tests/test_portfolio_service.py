"""
Tests for PortfolioService -- cache-respecting GET + defensive guards (T1).

Verifies:
- get_portfolio() calls fetch_single with cache_only=True (no live network calls).
- get_portfolio() returns enriched positions with degraded rows when cache is empty.
- get_portfolio() per-ticker try/except: one bad ticker yields a degraded row, not a crash.
- add_position() triggers exactly one fetch_single(ticker, cache_only=False).
- refresh() calls fetch_single with cache_only=False for all stored tickers.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from backend.app.models.portfolio import AddPositionRequest, UpdatePositionRequest
from backend.app.services.portfolio_service import PortfolioService
from backend.app.services.scoring_service import ScoringService
from backend.app.storage.portfolio_store import PortfolioStore


# ---------------------------------------------------------------------------
# Helpers / minimal fakes
# ---------------------------------------------------------------------------

def _make_position(ticker: str, quantity: float = 10.0, buy_price: float = 100.0) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "quantity": quantity,
        "buy_price": buy_price,
        "buy_date": "2026-01-01",
        "account_type": "pea",
        "notes": None,
    }


def _nan_row(ticker: str) -> Dict[str, Any]:
    """Minimal NaN row as returned by fetch_single(cache_only=True) on cache miss."""
    from backend.app.services.data_fetcher import SCORING_COLUMNS, EXTRA_FIELDS
    row: Dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
    row["Ticker"] = ticker
    row["field_sources"] = {col: "missing" for col in SCORING_COLUMNS + EXTRA_FIELDS}
    row["data_completeness"] = 0.0
    row["PEA"] = False
    row["PEA_PME"] = False
    return row


def _make_store(positions: List[Dict[str, Any]]) -> PortfolioStore:
    store = MagicMock(spec=PortfolioStore)
    store.get_positions.return_value = positions
    return store


def _make_fetcher(side_effect=None, return_value=None):
    fetcher = MagicMock()
    fetcher._cache = MagicMock()
    if side_effect is not None:
        fetcher.fetch_single.side_effect = side_effect
    else:
        fetcher.fetch_single.return_value = return_value or {}
    fetcher.fetch_analyst_ratings.return_value = None
    return fetcher


def _make_scorer() -> ScoringService:
    scorer = MagicMock(spec=ScoringService)
    scorer.score_single.return_value = {
        "horizons": {
            "long_term": {"score": 60.0, "signal": "Hold"},
            "medium_term": {"score": 55.0, "signal": "Hold"},
            "short_term": {"score": 50.0, "signal": "Hold"},
        },
        "piotroski_f": 6,
        "altman_z": 3.5,
        "graham_number": 140.0,
        "graham_mos": 0.08,
        "dcf": {"mos_mid": 0.15},
    }
    return scorer


# ---------------------------------------------------------------------------
# Tests: get_portfolio (cache-only)
# ---------------------------------------------------------------------------


class TestGetPortfolioCacheOnly:
    """get_portfolio() must never call fetch_single with cache_only=False."""

    def test_empty_portfolio_returns_no_positions(self) -> None:
        store = _make_store([])
        fetcher = _make_fetcher()
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_portfolio()

        assert result["positions"] == []
        fetcher.fetch_single.assert_not_called()

    def test_fetch_single_called_with_cache_only_true(self) -> None:
        positions = [_make_position("AAPL"), _make_position("MC.PA")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        svc.get_portfolio()

        for c in fetcher.fetch_single.call_args_list:
            _, kwargs = c
            assert kwargs.get("cache_only") is True, (
                f"Expected cache_only=True, got {kwargs}"
            )

    def test_returns_degraded_rows_on_cache_miss(self) -> None:
        """When fetch_single returns NaN row, scores and price should be null."""
        positions = [_make_position("AAPL", quantity=5.0, buy_price=150.0)]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))

        scorer = MagicMock(spec=ScoringService)
        scorer.score_single.return_value = {
            "horizons": {
                "long_term": {"score": None, "signal": None},
                "medium_term": {"score": None, "signal": None},
                "short_term": {"score": None, "signal": None},
            },
            "piotroski_f": None,
            "altman_z": None,
            "graham_number": None,
            "graham_mos": None,
            "dcf": {},
        }

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_portfolio()

        assert len(result["positions"]) == 1
        pos = result["positions"][0]
        assert pos["ticker"] == "AAPL"
        assert pos["score_lt"] is None
        assert pos["current_price"] is None
        assert pos["market_value"] is None
        # Cost basis is still computable from stored data
        assert pos["cost_basis"] == 5.0 * 150.0

    def test_analyst_ratings_not_fetched_in_cache_only_mode(self) -> None:
        positions = [_make_position("AAPL")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        svc.get_portfolio()

        fetcher.fetch_analyst_ratings.assert_not_called()

    def test_summary_includes_position_count(self) -> None:
        positions = [_make_position("AAPL"), _make_position("MSFT")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_portfolio()

        assert result["summary"]["position_count"] == 2


# ---------------------------------------------------------------------------
# Tests: get_portfolio defensive guards
# ---------------------------------------------------------------------------


class TestGetPortfolioDefensiveGuards:
    """One bad ticker must never 500 the whole list."""

    def test_bad_ticker_yields_degraded_row_not_exception(self) -> None:
        positions = [_make_position("GOOD"), _make_position("BAD")]
        store = _make_store(positions)

        good_row = _nan_row("GOOD")
        good_row["Price"] = 200.0
        good_row["Name"] = "Good Corp"

        def side_effect(ticker, cache_only=True):
            if ticker == "BAD":
                raise RuntimeError("Simulated fetch failure")
            return good_row

        fetcher = _make_fetcher(side_effect=side_effect)
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_portfolio()

        tickers_in_result = [p["ticker"] for p in result["positions"]]
        assert "GOOD" in tickers_in_result
        assert "BAD" in tickers_in_result

        bad_pos = next(p for p in result["positions"] if p["ticker"] == "BAD")
        assert bad_pos["current_price"] is None
        assert bad_pos["score_lt"] is None

    def test_scoring_failure_yields_null_scores_not_exception(self) -> None:
        positions = [_make_position("AAPL")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))

        scorer = MagicMock(spec=ScoringService)
        scorer.score_single.side_effect = ValueError("Simulated scoring failure")

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_portfolio()

        assert len(result["positions"]) == 1
        assert result["positions"][0]["score_lt"] is None


# ---------------------------------------------------------------------------
# Tests: add_position (live fetch for new ticker)
# ---------------------------------------------------------------------------


class TestAddPosition:
    """add_position() must trigger exactly one fetch_single with cache_only=False."""

    def test_add_position_triggers_live_fetch(self) -> None:
        store = MagicMock(spec=PortfolioStore)
        stored_pos = _make_position("NVDA")
        store.add_position.return_value = stored_pos

        fetcher = _make_fetcher(return_value=_nan_row("NVDA"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        req = AddPositionRequest(
            ticker="NVDA", quantity=5.0, buy_price=800.0, account_type="cto"
        )
        result = svc.add_position(req)

        fetcher.fetch_single.assert_called_once_with("NVDA", cache_only=False)
        assert result == stored_pos

    def test_add_position_returns_stored_pos_even_if_fetch_fails(self) -> None:
        store = MagicMock(spec=PortfolioStore)
        stored_pos = _make_position("GHOST")
        store.add_position.return_value = stored_pos

        fetcher = _make_fetcher(side_effect=RuntimeError("Network down"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        req = AddPositionRequest(
            ticker="GHOST", quantity=1.0, buy_price=50.0, account_type="pea"
        )
        result = svc.add_position(req)

        assert result == stored_pos


# ---------------------------------------------------------------------------
# Tests: refresh (force-live)
# ---------------------------------------------------------------------------


class TestRefresh:
    """refresh() must invalidate cache and call fetch_single with cache_only=False."""

    def test_refresh_invalidates_cache_for_each_ticker(self) -> None:
        positions = [_make_position("AAPL"), _make_position("MC.PA")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        svc.refresh()

        invalidated = [str(c.args[0]) for c in fetcher._cache.invalidate.call_args_list]
        assert "hybrid:AAPL" in invalidated
        assert "hybrid:MC.PA" in invalidated

    def test_refresh_calls_fetch_single_with_cache_only_false(self) -> None:
        positions = [_make_position("AAPL")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        svc.refresh()

        for c in fetcher.fetch_single.call_args_list:
            _, kwargs = c
            assert kwargs.get("cache_only") is False, (
                f"Expected cache_only=False in refresh, got {kwargs}"
            )

    def test_refresh_fetches_analyst_ratings(self) -> None:
        positions = [_make_position("AAPL")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        svc.refresh()

        fetcher.fetch_analyst_ratings.assert_called_once_with("AAPL")

    def test_refresh_passes_horizon_to_summary(self) -> None:
        positions = [_make_position("AAPL")]
        store = _make_store(positions)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = PortfolioService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.refresh(horizon="medium_term")

        assert result["horizon"] == "medium_term"
