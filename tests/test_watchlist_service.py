"""
Tests for WatchlistService -- cache-respecting GET + defensive guards (T1).

Verifies:
- get_watchlist() calls fetch_single with cache_only=True (no live network calls).
- get_watchlist() returns 200 with degraded rows when cache is empty.
- get_watchlist() per-ticker try/except: one bad ticker yields a degraded row, not a crash.
- add_item() triggers exactly one fetch_single(ticker, cache_only=False).
- refresh() calls fetch_single with cache_only=False for all stored tickers.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from backend.app.models.watchlist import AddWatchlistRequest
from backend.app.services.scoring_service import ScoringService
from backend.app.services.watchlist_service import WatchlistService
from backend.app.storage.watchlist_store import WatchlistStore


# ---------------------------------------------------------------------------
# Helpers / minimal fakes
# ---------------------------------------------------------------------------

def _make_item(ticker: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "added_date": "2026-01-01",
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


def _make_store(items: List[Dict[str, Any]]) -> WatchlistStore:
    store = MagicMock(spec=WatchlistStore)
    store.get_items.return_value = items
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
            "long_term": {"score": 55.0, "signal": "Hold"},
            "medium_term": {"score": 48.0, "signal": "Hold"},
            "short_term": {"score": 42.0, "signal": "Hold"},
        },
        "piotroski_f": 5,
        "altman_z": 3.1,
        "graham_number": 120.0,
        "graham_mos": 0.05,
        "dcf": {"mos_mid": 0.10},
    }
    return scorer


# ---------------------------------------------------------------------------
# Tests: get_watchlist (cache-only)
# ---------------------------------------------------------------------------


class TestGetWatchlistCacheOnly:
    """get_watchlist() must never call fetch_single with cache_only=False."""

    def test_empty_watchlist_returns_no_items(self) -> None:
        store = _make_store([])
        fetcher = _make_fetcher()
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_watchlist()

        assert result["items"] == []
        fetcher.fetch_single.assert_not_called()

    def test_fetch_single_called_with_cache_only_true(self) -> None:
        items = [_make_item("AAPL"), _make_item("MC.PA")]
        store = _make_store(items)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        svc.get_watchlist()

        # Every call must have cache_only=True
        for c in fetcher.fetch_single.call_args_list:
            _, kwargs = c
            assert kwargs.get("cache_only") is True, (
                f"Expected cache_only=True, got {kwargs}"
            )

    def test_returns_degraded_rows_on_cache_miss(self) -> None:
        """When fetch_single returns a NaN row (cache miss), scores should be null."""
        items = [_make_item("AAPL")]
        store = _make_store(items)
        # Return the NaN row so scorer gets an all-NaN series
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))

        scorer = MagicMock(spec=ScoringService)
        # Scoring an all-NaN row typically returns zeros/None; simulate that
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

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_watchlist()

        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["ticker"] == "AAPL"
        assert item["score_lt"] is None
        assert item["current_price"] is None

    def test_analyst_ratings_not_fetched_in_cache_only_mode(self) -> None:
        """fetch_analyst_ratings must NOT be called from get_watchlist (cache-only)."""
        items = [_make_item("AAPL")]
        store = _make_store(items)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        svc.get_watchlist()

        fetcher.fetch_analyst_ratings.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: get_watchlist defensive guards
# ---------------------------------------------------------------------------


class TestGetWatchlistDefensiveGuards:
    """One bad ticker must never 500 the whole list."""

    def test_bad_ticker_yields_degraded_row_not_exception(self) -> None:
        items = [_make_item("GOOD"), _make_item("BAD")]
        store = _make_store(items)

        good_row = _nan_row("GOOD")
        good_row["Price"] = 100.0
        good_row["Name"] = "Good Corp"

        def side_effect(ticker, cache_only=True):
            if ticker == "BAD":
                raise RuntimeError("Simulated fetch failure")
            return good_row

        fetcher = _make_fetcher(side_effect=side_effect)
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        # Must not raise
        result = svc.get_watchlist()

        tickers_in_result = [item["ticker"] for item in result["items"]]
        assert "GOOD" in tickers_in_result
        assert "BAD" in tickers_in_result

        bad_item = next(i for i in result["items"] if i["ticker"] == "BAD")
        assert bad_item["current_price"] is None
        assert bad_item["score_lt"] is None

    def test_scoring_failure_yields_null_scores_not_exception(self) -> None:
        items = [_make_item("AAPL")]
        store = _make_store(items)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))

        scorer = MagicMock(spec=ScoringService)
        scorer.score_single.side_effect = ValueError("Simulated scoring failure")

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        result = svc.get_watchlist()

        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["score_lt"] is None


# ---------------------------------------------------------------------------
# Tests: add_item (live fetch for new ticker)
# ---------------------------------------------------------------------------


class TestAddItem:
    """add_item() must trigger exactly one fetch_single with cache_only=False."""

    def test_add_item_triggers_live_fetch(self) -> None:
        store = MagicMock(spec=WatchlistStore)
        stored_item = _make_item("NVDA")
        store.add_item.return_value = stored_item

        fetcher = _make_fetcher(return_value=_nan_row("NVDA"))
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        req = AddWatchlistRequest(ticker="NVDA")
        result = svc.add_item(req)

        # Must call fetch_single exactly once for NVDA with cache_only=False
        fetcher.fetch_single.assert_called_once_with("NVDA", cache_only=False)
        assert result == stored_item

    def test_add_item_returns_stored_row_even_if_fetch_fails(self) -> None:
        store = MagicMock(spec=WatchlistStore)
        stored_item = _make_item("GHOST")
        store.add_item.return_value = stored_item

        fetcher = _make_fetcher(side_effect=RuntimeError("FMP + yf both down"))
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        req = AddWatchlistRequest(ticker="GHOST")
        # Must not raise despite fetch failure
        result = svc.add_item(req)

        assert result == stored_item


# ---------------------------------------------------------------------------
# Tests: refresh (force-live)
# ---------------------------------------------------------------------------


class TestRefresh:
    """refresh() must invalidate cache and call fetch_single with cache_only=False."""

    def test_refresh_calls_cache_invalidate_for_each_ticker(self) -> None:
        items = [_make_item("AAPL"), _make_item("MC.PA")]
        store = _make_store(items)

        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        svc.refresh()

        # invalidate must have been called for each ticker's hybrid key
        invalidated = [str(c.args[0]) for c in fetcher._cache.invalidate.call_args_list]
        assert "hybrid:AAPL" in invalidated
        assert "hybrid:MC.PA" in invalidated

    def test_refresh_calls_fetch_single_with_cache_only_false(self) -> None:
        items = [_make_item("AAPL")]
        store = _make_store(items)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        svc.refresh()

        # All fetch_single calls must be cache_only=False
        for c in fetcher.fetch_single.call_args_list:
            _, kwargs = c
            assert kwargs.get("cache_only") is False, (
                f"Expected cache_only=False in refresh, got {kwargs}"
            )

    def test_refresh_fetches_analyst_ratings(self) -> None:
        items = [_make_item("AAPL")]
        store = _make_store(items)
        fetcher = _make_fetcher(return_value=_nan_row("AAPL"))
        scorer = _make_scorer()

        svc = WatchlistService(store=store, fetcher=fetcher, scorer=scorer)
        svc.refresh()

        fetcher.fetch_analyst_ratings.assert_called_once_with("AAPL")
