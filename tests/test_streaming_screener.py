"""Tests for backend.app.services.streaming_screener.refresh_stream.

All external dependencies (universe loader, fetcher.fetch_batch, scorer,
screener_cache disk paths) are mocked so the generator can be drained in
isolation. Each test asserts on the parsed SSE event sequence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.services import screener_cache, streaming_screener

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(stream: list[str]) -> list[tuple[str, dict]]:
    """Turn raw SSE lines into [(event_name, payload_dict), ...]."""
    out: list[tuple[str, dict]] = []
    for chunk in stream:
        event = None
        data = None
        for line in chunk.strip().split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data = line[len("data: ") :].strip()
        if event is None or data is None:
            continue
        out.append((event, json.loads(data)))
    return out


def _drain(generator) -> list[tuple[str, dict]]:
    return _parse_sse(list(generator))


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the disk cache paths so streaming tests do not touch real data."""
    screener_cache.reset_for_tests()
    monkeypatch.setattr(screener_cache, "_CACHE_PATH", tmp_path / "scored.parquet")
    monkeypatch.setattr(screener_cache, "_META_PATH", tmp_path / "scored.meta.json")
    yield
    screener_cache.reset_for_tests()


def _scored_df(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"Price": [100.0] * len(tickers), "score_lt": [70.0] * len(tickers)},
        index=pd.Index(tickers, name="Ticker"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_emits_start_ticker_done_sequence() -> None:
    tickers = ["AAA", "BBB", "CCC"]
    fetcher = MagicMock()
    scorer = MagicMock()

    def fake_fetch_batch(
        tks: list[str],
        source: str = "hybrid",
        *,
        max_workers: int = 1,
        on_ticker_complete=None,
    ) -> pd.DataFrame:
        for t in tks:
            on_ticker_complete(t, {"Ticker": t, "Price": 50.0})
        return _scored_df(tks)

    fetcher.fetch_batch.side_effect = fake_fetch_batch
    scorer.score_dataframe.side_effect = lambda df: df

    with patch.object(streaming_screener, "load_pea_universe", return_value=tickers):
        events = _drain(streaming_screener.refresh_stream(fetcher, scorer, max_workers=2))

    names = [name for name, _ in events]
    assert names[0] == "start"
    assert names.count("ticker") == len(tickers)
    assert names[-1] == "done"

    start_payload = events[0][1]
    assert start_payload["total"] == len(tickers)
    assert start_payload["max_workers"] == 2

    done_payload = events[-1][1]
    assert done_payload["tickers_fetched"] == len(tickers)
    assert done_payload["universe_size"] == len(tickers)
    assert done_payload["tickers_failed"] == []


def test_progress_counter_monotonic() -> None:
    tickers = [f"T{i}" for i in range(5)]
    fetcher = MagicMock()
    scorer = MagicMock()
    scorer.score_dataframe.side_effect = lambda df: df

    def fake_fetch_batch(
        tks: list[str],
        source: str = "hybrid",
        *,
        max_workers: int = 1,
        on_ticker_complete=None,
    ) -> pd.DataFrame:
        for t in tks:
            on_ticker_complete(t, {"Ticker": t, "Price": 1.0})
        return _scored_df(tks)

    fetcher.fetch_batch.side_effect = fake_fetch_batch

    with patch.object(streaming_screener, "load_pea_universe", return_value=tickers):
        events = _drain(streaming_screener.refresh_stream(fetcher, scorer))

    ticker_events = [p for n, p in events if n == "ticker"]
    done_counts = [e["progress"]["done"] for e in ticker_events]
    assert done_counts == sorted(done_counts)
    assert done_counts[-1] == len(tickers)
    assert all(e["progress"]["total"] == len(tickers) for e in ticker_events)


def test_failed_tickers_reported_in_done() -> None:
    """Tickers whose row has no Price are surfaced in tickers_failed."""
    tickers = ["GOOD", "FAIL"]
    fetcher = MagicMock()
    scorer = MagicMock()

    def fake_fetch_batch(
        tks: list[str],
        source: str = "hybrid",
        *,
        max_workers: int = 1,
        on_ticker_complete=None,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for t in tks:
            row = {"Ticker": t, "Price": 1.0 if t == "GOOD" else None}
            on_ticker_complete(t, row)
            rows.append(row)
        return pd.DataFrame(rows).set_index("Ticker")

    fetcher.fetch_batch.side_effect = fake_fetch_batch
    scorer.score_dataframe.side_effect = lambda df: df

    with patch.object(streaming_screener, "load_pea_universe", return_value=tickers):
        events = _drain(streaming_screener.refresh_stream(fetcher, scorer))

    done = events[-1][1]
    assert "FAIL" in done["tickers_failed"]
    assert done["tickers_fetched"] == 1


def test_emits_error_when_universe_empty() -> None:
    fetcher = MagicMock()
    scorer = MagicMock()

    with patch.object(streaming_screener, "load_pea_universe", return_value=[]):
        events = _drain(streaming_screener.refresh_stream(fetcher, scorer))

    assert any(name == "error" for name, _ in events)
    assert all(name != "done" for name, _ in events)


def test_emits_error_when_universe_loader_raises() -> None:
    fetcher = MagicMock()
    scorer = MagicMock()

    with patch.object(
        streaming_screener,
        "load_pea_universe",
        side_effect=RuntimeError("network down"),
    ):
        events = _drain(streaming_screener.refresh_stream(fetcher, scorer))

    assert events[-1][0] == "error"
    assert "network down" in events[-1][1]["reason"]


def test_emits_error_when_fetch_returns_empty_df() -> None:
    tickers = ["A", "B"]
    fetcher = MagicMock()
    scorer = MagicMock()
    fetcher.fetch_batch.return_value = pd.DataFrame()

    with patch.object(streaming_screener, "load_pea_universe", return_value=tickers):
        events = _drain(streaming_screener.refresh_stream(fetcher, scorer))

    names = [n for n, _ in events]
    assert "error" in names
    assert "done" not in names


def test_commits_scored_to_cache_on_success() -> None:
    """A successful stream must populate screener_cache so subsequent preset
    calls can read from get_scored() without re-running the slow fetch."""
    tickers = ["X", "Y"]
    fetcher = MagicMock()
    scorer = MagicMock()

    def fake_fetch_batch(tks, source="hybrid", *, max_workers=1, on_ticker_complete=None):
        for t in tks:
            on_ticker_complete(t, {"Ticker": t, "Price": 9.0})
        return _scored_df(tks)

    fetcher.fetch_batch.side_effect = fake_fetch_batch
    scorer.score_dataframe.side_effect = lambda df: df

    with patch.object(streaming_screener, "load_pea_universe", return_value=tickers):
        _drain(streaming_screener.refresh_stream(fetcher, scorer))

    scored = screener_cache.get_scored()
    assert list(scored.index.astype(str)) == tickers
    assert screener_cache.last_refreshed() is not None
