"""Tests for the screener cache module."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.app.services import screener_cache


@pytest.fixture(autouse=True)
def _reset_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear cache state and isolate disk paths to a tmp dir for each test."""
    screener_cache.reset_for_tests()
    monkeypatch.setattr(screener_cache, "_CACHE_PATH", tmp_path / "scored.parquet")
    monkeypatch.setattr(screener_cache, "_META_PATH", tmp_path / "scored.meta.json")
    yield
    screener_cache.reset_for_tests()


def _scored_df(tickers: list[str]) -> pd.DataFrame:
    """Minimal scored DataFrame with the columns the cache cares about."""
    df = pd.DataFrame(
        {
            "Price": [100.0 + i for i, _ in enumerate(tickers)],
            "Name": [f"{t} Corp" for t in tickers],
            "score_lt": [70.0 + i for i, _ in enumerate(tickers)],
            "passes_gates_lt": [True] * len(tickers),
            "PEA": [True] * len(tickers),
        },
        index=pd.Index(tickers, name="Ticker"),
    )
    return df


class TestGetScored:
    def test_raises_when_empty(self) -> None:
        with pytest.raises(screener_cache.ScreenerNotRefreshed):
            screener_cache.get_scored()

    def test_lookup_returns_none_when_empty(self) -> None:
        # Lookup should not raise — it must return None so callers can
        # gracefully fall back to single-row scoring.
        assert screener_cache.lookup("MC.PA") is None

    def test_last_refreshed_none_when_empty(self) -> None:
        assert screener_cache.last_refreshed() is None


class TestRefresh:
    def test_populates_state_and_returns_summary(self) -> None:
        fetcher = MagicMock()
        fetcher.fetch_batch.return_value = pd.DataFrame(
            {"Price": [100.0]},
            index=pd.Index(["MC.PA"], name="Ticker"),
        )
        scorer = MagicMock()
        scorer.score_dataframe.return_value = _scored_df(["MC.PA"])

        with patch.object(
            screener_cache,
            "load_pea_universe",
            return_value=["MC.PA"],
        ):
            summary = screener_cache.refresh(fetcher, scorer, use_yfinance_holdings=False)

        assert summary["universe_size"] == 1
        assert summary["tickers_fetched"] == 1
        assert summary["last_refreshed"]
        assert summary["duration_seconds"] >= 0
        # And cache should now serve the scored df:
        df = screener_cache.get_scored()
        assert len(df) == 1
        assert df.index[0] == "MC.PA"

    def test_lookup_returns_row_after_refresh(self) -> None:
        fetcher = MagicMock()
        fetcher.fetch_batch.return_value = pd.DataFrame(
            {"Price": [100.0]},
            index=pd.Index(["MC.PA"], name="Ticker"),
        )
        scorer = MagicMock()
        scorer.score_dataframe.return_value = _scored_df(["MC.PA", "TTE.PA"])
        with patch.object(
            screener_cache, "load_pea_universe", return_value=["MC.PA", "TTE.PA"]
        ):
            screener_cache.refresh(fetcher, scorer, use_yfinance_holdings=False)

        row = screener_cache.lookup("MC.PA")
        assert row is not None
        assert row["score_lt"] == 70.0
        # Unknown ticker:
        assert screener_cache.lookup("UNKNOWN.XX") is None

    def test_persists_to_disk_and_rehydrates(self, tmp_path: Path) -> None:
        fetcher = MagicMock()
        fetcher.fetch_batch.return_value = pd.DataFrame(
            {"Price": [100.0]},
            index=pd.Index(["MC.PA"], name="Ticker"),
        )
        scorer = MagicMock()
        scorer.score_dataframe.return_value = _scored_df(["MC.PA"])
        with patch.object(
            screener_cache, "load_pea_universe", return_value=["MC.PA"]
        ):
            screener_cache.refresh(fetcher, scorer, use_yfinance_holdings=False)

        # Reset in-memory state — disk should still hold the parquet
        screener_cache.reset_for_tests()
        # First get_scored() must rehydrate from disk without raising
        df = screener_cache.get_scored()
        assert df.index[0] == "MC.PA"

    def test_empty_fetch_raises(self) -> None:
        fetcher = MagicMock()
        fetcher.fetch_batch.return_value = pd.DataFrame()
        scorer = MagicMock()
        with patch.object(
            screener_cache, "load_pea_universe", return_value=["MC.PA"]
        ):
            with pytest.raises(RuntimeError, match="empty DataFrame"):
                screener_cache.refresh(fetcher, scorer, use_yfinance_holdings=False)

    def test_empty_universe_raises(self) -> None:
        fetcher = MagicMock()
        scorer = MagicMock()
        with patch.object(
            screener_cache, "load_pea_universe", return_value=[]
        ):
            with pytest.raises(RuntimeError, match="no tickers"):
                screener_cache.refresh(fetcher, scorer, use_yfinance_holdings=False)
