"""Tests for YFinanceDataFetcher.fetch_multi_price_history."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher


@pytest.fixture
def fetcher(tmp_path: Path) -> YFinanceDataFetcher:
    return YFinanceDataFetcher(cache=CacheService(cache_dir=tmp_path / "cache"))


def _fake_multi_download() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=5, freq="B")
    cols = pd.MultiIndex.from_tuples(
        [
            ("AAPL", "Open"), ("AAPL", "High"), ("AAPL", "Low"),
            ("AAPL", "Close"), ("AAPL", "Volume"),
            ("^GSPC", "Open"), ("^GSPC", "High"), ("^GSPC", "Low"),
            ("^GSPC", "Close"), ("^GSPC", "Volume"),
        ]
    )
    data = np.tile(np.array([100, 101, 99, 100.5, 1_000_000.0]), (5, 2))
    return pd.DataFrame(data, index=idx, columns=cols)


def test_multi_history_returns_per_ticker_frames(fetcher: YFinanceDataFetcher) -> None:
    with patch("yfinance.download", return_value=_fake_multi_download()) as dl:
        out = fetcher.fetch_multi_price_history(["AAPL", "^GSPC"], period="1y")
    dl.assert_called_once()
    assert set(out.keys()) == {"AAPL", "^GSPC"}
    for df in out.values():
        assert {"Open", "High", "Low", "Close", "Volume"} <= set(df.columns)
        assert len(df) == 5


def test_multi_history_empty_input(fetcher: YFinanceDataFetcher) -> None:
    assert fetcher.fetch_multi_price_history([], period="1y") == {}


def test_multi_history_caches_to_parquet(fetcher: YFinanceDataFetcher, tmp_path: Path) -> None:
    with patch("yfinance.download", return_value=_fake_multi_download()):
        fetcher.fetch_multi_price_history(["AAPL", "^GSPC"], period="1y")
    cache_dir = tmp_path / "cache" / "multi_history"
    parquets = list(cache_dir.glob("*.parquet"))
    assert len(parquets) == 1


def test_multi_history_cache_hit_skips_yfinance(fetcher: YFinanceDataFetcher) -> None:
    with patch("yfinance.download", return_value=_fake_multi_download()) as dl:
        fetcher.fetch_multi_price_history(["AAPL", "^GSPC"], period="1y")
        fetcher.fetch_multi_price_history(["AAPL", "^GSPC"], period="1y")  # cache hit
    assert dl.call_count == 1
