"""Streaming variant of ``screener_cache.refresh`` that yields SSE events.

The slow operation in the screener pipeline is the per-ticker fetch loop in
``HybridDataFetcher.fetch_batch``. This module wraps that loop in:

  1. A ``ThreadPoolExecutor`` (``max_workers`` configurable in settings.yaml)
     so the ~600 yfinance HTTP calls (127 tickers × ~5 endpoints) overlap.
  2. A generator yielding ``text/event-stream`` lines so the frontend can
     render a progress bar and a table that fills as tickers complete.

Event sequence
--------------
- ``start``  : {"total", "source", "max_workers"}
- ``ticker`` : {"ticker", "progress": {"done", "total"}, "ok": bool}
- ``done``   : {"tickers_fetched", "tickers_failed", "last_refreshed",
                "duration_seconds", "universe_size"}
- ``error``  : {"reason"}  (fatal — stream ends)
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Generator
from datetime import UTC, datetime

from loguru import logger

from backend.app.config import settings
from backend.app.services import screener_cache
from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.scoring_service import ScoringService
from src.data.universe_loader import load_pea_universe

_SENTINEL = object()


def _sse(event: str, payload: dict) -> str:
    """Format a single SSE event line."""
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def refresh_stream(
    fetcher: DataFetcher,
    scorer: ScoringService,
    *,
    source: str = "hybrid",
    use_yfinance_holdings: bool = True,
    max_workers: int | None = None,
) -> Generator[str, None, None]:
    """Run a universe refresh, emitting SSE events as tickers complete.

    Yields formatted SSE strings. The caller (FastAPI endpoint) wraps the
    generator in a ``StreamingResponse`` with ``media_type="text/event-stream"``.
    """
    if max_workers is None:
        max_workers = settings.screener_streaming_max_workers

    started = datetime.now(UTC)

    try:
        tickers = load_pea_universe(use_yfinance=use_yfinance_holdings)
    except Exception as exc:
        logger.exception("Universe loader failed")
        yield _sse("error", {"reason": f"universe load failed: {exc}"})
        return

    if not tickers:
        yield _sse("error", {"reason": "Universe loader returned no tickers"})
        return

    total = len(tickers)
    yield _sse("start", {"total": total, "source": source, "max_workers": max_workers})
    logger.info(f"Stream refresh: {total} tickers, source={source}, max_workers={max_workers}")

    events_q: queue.Queue = queue.Queue()
    done_counter = {"n": 0}
    counter_lock = threading.Lock()

    def on_ticker_complete(ticker: str, data: dict) -> None:
        with counter_lock:
            done_counter["n"] += 1
            done = done_counter["n"]
        ok = bool(data.get("Price"))
        events_q.put(
            (
                "ticker",
                {
                    "ticker": ticker,
                    "progress": {"done": done, "total": total},
                    "ok": ok,
                },
            )
        )

    result_holder: dict = {}

    def fetch_thread() -> None:
        try:
            df = fetcher.fetch_batch(
                tickers,
                source=source,
                max_workers=max_workers,
                on_ticker_complete=on_ticker_complete,
            )
            if df.empty:
                events_q.put(("error", {"reason": "fetch_batch returned empty DataFrame"}))
                return

            failed: list[str] = []
            if "Price" in df.columns:
                failed = df.index[df["Price"].isna()].astype(str).tolist()

            scored = scorer.score_dataframe(df)
            finished = datetime.now(UTC)
            screener_cache.set_scored(scored, finished, failed)

            result_holder["summary"] = {
                "tickers_fetched": len(tickers) - len(failed),
                "tickers_failed": failed,
                "last_refreshed": finished.isoformat(),
                "duration_seconds": round((finished - started).total_seconds(), 2),
                "universe_size": len(scored),
            }
        except Exception as exc:
            logger.exception("Stream refresh worker crashed")
            events_q.put(("error", {"reason": str(exc)}))
        finally:
            events_q.put((_SENTINEL, None))

    worker = threading.Thread(target=fetch_thread, name="screener-stream-refresh", daemon=True)
    worker.start()

    fatal_error = False
    while True:
        event, payload = events_q.get()
        if event is _SENTINEL:
            break
        if event == "error":
            fatal_error = True
        yield _sse(event, payload)

    worker.join(timeout=1.0)

    if not fatal_error and "summary" in result_holder:
        yield _sse("done", result_holder["summary"])
