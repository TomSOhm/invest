"""Module-level scored-universe cache for the screener.

Holds the live-fetched, scored DataFrame produced by `refresh()` so that
`/api/screener/run`, `/preset/*`, and the company-detail endpoint all read
from the same scored snapshot. Persists to parquet so a backend restart
does not force the user to re-run a slow refresh.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd
from loguru import logger

from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.scoring_service import ScoringService
from src.data.universe_loader import load_pea_universe

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CACHE_PATH = _PROJECT_ROOT / "data" / "cache" / "screener_scored.parquet"
_META_PATH = _PROJECT_ROOT / "data" / "cache" / "screener_scored.meta.json"


class ScreenerNotRefreshed(RuntimeError):
    """Raised when the scored universe has never been populated."""


class _State:
    scored_df: pd.DataFrame | None = None
    last_refreshed: datetime | None = None
    tickers_failed: list[str] = []


_state = _State()
_lock = Lock()


def _disk_load_if_present() -> bool:
    """Load cached parquet + meta into memory. Returns True on success."""
    if not _CACHE_PATH.exists():
        return False
    try:
        df = pd.read_parquet(_CACHE_PATH)
        _state.scored_df = df
        if _META_PATH.exists():
            import json

            meta = json.loads(_META_PATH.read_text())
            _state.last_refreshed = (
                datetime.fromisoformat(meta["last_refreshed"]) if meta.get("last_refreshed") else None
            )
            _state.tickers_failed = list(meta.get("tickers_failed", []))
        logger.info(f"Screener cache rehydrated from disk: {len(df)} rows, last_refreshed={_state.last_refreshed}")
        return True
    except Exception as exc:
        logger.warning(f"Screener cache disk-load failed: {exc}")
        return False


def _disk_persist(df: pd.DataFrame, last_refreshed: datetime, failed: list[str]) -> None:
    """Best-effort persist of the scored DataFrame and metadata to disk."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_CACHE_PATH)
        import json

        _META_PATH.write_text(
            json.dumps(
                {
                    "last_refreshed": last_refreshed.isoformat(),
                    "tickers_failed": failed,
                }
            )
        )
    except Exception as exc:
        logger.warning(f"Screener cache disk-persist failed: {exc}")


def refresh(
    fetcher: DataFetcher,
    scorer: ScoringService,
    *,
    use_yfinance_holdings: bool = True,
    source: str = "hybrid",
) -> dict[str, Any]:
    """Load universe, fetch live data, score, cache, persist.

    ``source`` selects the data backend for ``fetcher.fetch_batch`` so the user
    can drive a universe refresh from yfinance-only or fmp-only instead of the
    default hybrid path.

    Returns a summary dict matching ``ScreenerRefreshResponse``.
    """
    with _lock:
        started = datetime.now(UTC)
        tickers = load_pea_universe(use_yfinance=use_yfinance_holdings)

        if not tickers:
            raise RuntimeError("Universe loader returned no tickers — check data/universes/universe_pea_static.csv")

        logger.info(f"Screener refresh: fetching {len(tickers)} tickers (source={source})")
        df = fetcher.fetch_batch(tickers, source=source)

        # Track tickers that came back fully empty (every scoring field NaN
        # or missing). Treat them as "failed" so the user has visibility.
        failed: list[str] = []
        if not df.empty and "Price" in df.columns:
            failed = df.index[df["Price"].isna()].astype(str).tolist()

        if df.empty:
            raise RuntimeError(
                f"fetch_batch returned an empty DataFrame for {len(tickers)} tickers — data source may be down"
            )

        scored = scorer.score_dataframe(df)
        finished = datetime.now(UTC)

        _state.scored_df = scored
        _state.last_refreshed = finished
        _state.tickers_failed = failed
        _disk_persist(scored, finished, failed)

        return {
            "tickers_fetched": len(tickers) - len(failed),
            "tickers_failed": failed,
            "last_refreshed": finished.isoformat(),
            "duration_seconds": round((finished - started).total_seconds(), 2),
            "universe_size": len(scored),
        }


def get_scored() -> pd.DataFrame:
    """Return the cached scored DataFrame.

    Loads from disk on first access. Raises ``ScreenerNotRefreshed`` if no
    cache exists in memory or on disk.
    """
    if _state.scored_df is None:
        if not _disk_load_if_present():
            raise ScreenerNotRefreshed("Screener universe has not been refreshed. POST /api/screener/refresh first.")
    assert _state.scored_df is not None
    return _state.scored_df


def lookup(ticker: str) -> dict[str, Any] | None:
    """Return the scored row for ``ticker`` as a dict, or None.

    Returns ``None`` (not raise) when the cache is empty so the caller can
    fall back to single-row scoring without a try/except dance.
    """
    try:
        df = get_scored()
    except ScreenerNotRefreshed:
        return None
    if ticker not in df.index:
        return None
    row = df.loc[ticker]
    return row.to_dict()


def last_refreshed() -> str | None:
    """ISO timestamp of the last refresh, or None."""
    if _state.last_refreshed is None:
        # Try a disk peek without forcing a full df load
        try:
            if _META_PATH.exists():
                import json

                meta = json.loads(_META_PATH.read_text())
                return meta.get("last_refreshed")
        except Exception:
            return None
        return None
    return _state.last_refreshed.isoformat()


def tickers_failed() -> list[str]:
    """Tickers that returned no usable data on the last refresh."""
    return list(_state.tickers_failed)


def reset_for_tests() -> None:
    """Clear in-memory state. Tests only — does not touch disk."""
    _state.scored_df = None
    _state.last_refreshed = None
    _state.tickers_failed = []
