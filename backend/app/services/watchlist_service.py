"""
Invest Solo -- Watchlist Service (M10)
Enriches stored watchlist items with live data and three-horizon scoring.

Key changes vs M9:
- composite_score / signal replaced by score_lt/mt/st + signal_lt/mt/st
- dcf_mos_mid exposed on each item

Cache strategy (T1):
- get_watchlist(): cache-only -- no live FMP/yfinance calls.
- refresh(): force-live -- invalidates cache, then fetches live data.
- add_item(): live fetch for the single new ticker only.
- Per-ticker try/except prevents one bad ticker from 500-ing the whole list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.models.watchlist import AddWatchlistRequest
from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.scoring_service import ScoringService
from backend.app.storage.watchlist_store import WatchlistStore


class WatchlistService:
    """Combines storage, live data, and scoring for watchlist management."""

    def __init__(
        self,
        store: WatchlistStore,
        fetcher: DataFetcher,
        scorer: ScoringService,
    ) -> None:
        self._store = store
        self._fetcher = fetcher
        self._scorer = scorer

    def get_watchlist(self, source: str = "hybrid") -> dict[str, Any]:
        """Cache-only enriched watchlist read; honors per-source cache keys."""
        return self._build_enriched_response(cache_only=True, source=source)

    def refresh(self, source: str = "hybrid") -> dict[str, Any]:
        """Force-refresh: invalidate all source caches for stored tickers."""
        items = self._store.get_items()
        for item in items:
            ticker = item["ticker"]
            for prefix in ("hybrid", "yfinance", "fmp"):
                self._fetcher._cache.invalidate(f"{prefix}:{ticker}")
            self._fetcher._cache.invalidate(f"ticker_{ticker}")
        return self._build_enriched_response(cache_only=False, source=source)

    def add_item(
        self,
        req: AddWatchlistRequest,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        """Add a ticker with a live fetch via ``source``."""
        stored = self._store.add_item(ticker=req.ticker, notes=req.notes)

        try:
            self._fetcher.fetch_single(req.ticker, cache_only=False, source=source)
        except Exception as exc:
            logger.warning(
                f"Live fetch failed for newly added ticker {req.ticker}: {exc}. "
                "Row will have degraded scoring fields until next Refresh."
            )

        return stored

    def remove_item(self, item_id: str) -> bool:
        """Remove a watchlist item by id."""
        return self._store.remove_item(item_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_enriched_response(
        self,
        cache_only: bool,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        """Build the full enriched watchlist response."""
        raw_items = self._store.get_items()
        if not raw_items:
            return {
                "items": [],
                "last_refreshed": datetime.now(UTC).isoformat(),
            }

        tickers = list({item["ticker"] for item in raw_items})
        mode = "cache-only" if cache_only else "force-live"
        logger.info(f"Enriching {len(raw_items)} watchlist items ({len(tickers)} unique) [{mode}]")

        # Fetch data per ticker (cache_only flag governs whether live calls fire)
        live_data: dict[str, dict[str, Any]] = {}
        for ticker in tickers:
            try:
                live_data[ticker] = self._fetcher.fetch_single(
                    ticker,
                    cache_only=cache_only,
                    source=source,
                )
            except Exception as exc:
                logger.warning(f"fetch_single failed for watchlist ticker {ticker}: {exc}. Using empty row.")
                live_data[ticker] = {}

        # Score each ticker
        scored: dict[str, dict[str, Any]] = {}
        for ticker, data in live_data.items():
            if not data:
                scored[ticker] = {}
                continue
            try:
                series = pd.Series(data)
                scored[ticker] = self._scorer.score_single(series)
            except Exception as exc:
                logger.warning(f"score_single failed for {ticker}: {exc}")
                scored[ticker] = {}

        # Fetch analyst ratings -- only in force-live mode (they involve FMP calls)
        analyst_data: dict[str, dict[str, Any] | None] = {}
        if not cache_only:
            for ticker in tickers:
                try:
                    analyst_data[ticker] = self._fetcher.fetch_analyst_ratings(
                        ticker,
                        source=source,
                    )
                except Exception as exc:
                    logger.warning(f"fetch_analyst_ratings failed for {ticker}: {exc}")
                    analyst_data[ticker] = None
        else:
            # In cache-only mode analyst data is decorative; skip FMP calls.
            analyst_data = {ticker: None for ticker in tickers}

        enriched: list[dict[str, Any]] = []
        for item in raw_items:
            ticker = item["ticker"]
            try:
                ld = live_data.get(ticker, {})
                sc = scored.get(ticker, {})
                an = analyst_data.get(ticker)

                current_price = self._num(ld.get("Price"))

                high_52 = self._num(ld.get("FiftyTwoWeekHigh"))
                fifty_two_pct: float | None = None
                if current_price and high_52 and high_52 > 0:
                    fifty_two_pct = round((current_price / high_52 - 1) * 100, 1)

                analyst_rating: str | None = None
                analyst_target: float | None = None
                if an:
                    total = (
                        an.get("buy", 0)
                        + an.get("hold", 0)
                        + an.get("sell", 0)
                        + an.get("strong_buy", 0)
                        + an.get("strong_sell", 0)
                    )
                    if total > 0:
                        buys = an.get("strong_buy", 0) + an.get("buy", 0)
                        sells = an.get("sell", 0) + an.get("strong_sell", 0)
                        if buys > sells:
                            analyst_rating = "Buy"
                        elif sells > buys:
                            analyst_rating = "Sell"
                        else:
                            analyst_rating = "Hold"
                    analyst_target = an.get("target_mean")

                # Extract horizon scores
                h = sc.get("horizons", {})
                lt = h.get("long_term", {})
                mt = h.get("medium_term", {})
                st = h.get("short_term", {})

                enriched.append(
                    {
                        "id": item["id"],
                        "ticker": ticker,
                        "name": self._str(ld.get("Name")) or ticker,
                        "sector": self._str(ld.get("Sector")),
                        "country": self._str(ld.get("Country")),
                        "added_date": item.get("added_date"),
                        "notes": item.get("notes"),
                        "current_price": current_price,
                        "pe": self._num(ld.get("PE")),
                        "pb": self._num(ld.get("PB")),
                        "roe": self._num(ld.get("ROE")),
                        # Three-horizon scoring
                        "score_lt": lt.get("score"),
                        "score_mt": mt.get("score"),
                        "score_st": st.get("score"),
                        "signal_lt": lt.get("signal"),
                        "signal_mt": mt.get("signal"),
                        "signal_st": st.get("signal"),
                        # Quality
                        "piotroski_f": sc.get("piotroski_f"),
                        "altman_z": sc.get("altman_z"),
                        "graham_number": sc.get("graham_number"),
                        "graham_mos": sc.get("graham_mos"),
                        "dcf_mos_mid": sc.get("dcf", {}).get("mos_mid"),
                        # PEA
                        "pea_eligible": bool(ld.get("PEA", False)),
                        "pea_pme_eligible": bool(ld.get("PEA_PME", False)),
                        # Analyst
                        "analyst_rating": analyst_rating,
                        "analyst_target_price": analyst_target,
                        "forward_pe": self._num(ld.get("ForwardPE")),
                        "peg": self._num(ld.get("PEG")),
                        "fifty_two_week_high_pct": fifty_two_pct,
                    }
                )
            except Exception as exc:
                logger.warning(f"Enrichment failed for watchlist ticker {ticker}: {exc}. Inserting degraded row.")
                enriched.append(
                    {
                        "id": item["id"],
                        "ticker": ticker,
                        "name": ticker,
                        "sector": None,
                        "country": None,
                        "added_date": item.get("added_date"),
                        "notes": item.get("notes"),
                        "current_price": None,
                        "pe": None,
                        "pb": None,
                        "roe": None,
                        "score_lt": None,
                        "score_mt": None,
                        "score_st": None,
                        "signal_lt": None,
                        "signal_mt": None,
                        "signal_st": None,
                        "piotroski_f": None,
                        "altman_z": None,
                        "graham_number": None,
                        "graham_mos": None,
                        "dcf_mos_mid": None,
                        "pea_eligible": False,
                        "pea_pme_eligible": False,
                        "analyst_rating": None,
                        "analyst_target_price": None,
                        "forward_pe": None,
                        "peg": None,
                        "fifty_two_week_high_pct": None,
                    }
                )

        return {
            "items": enriched,
            "last_refreshed": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _num(value: Any) -> float | None:
        """Convert a value to float, returning None for NaN/None/invalid."""
        if value is None:
            return None
        try:
            f = float(value)
            if np.isnan(f) or np.isinf(f):
                return None
            return round(f, 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _str(value: Any) -> str | None:
        """Coerce a value to str, returning None for NaN/None/empty.

        pandas NaN is a truthy float, so plain ``or`` fallbacks let it through
        and break Pydantic str validation downstream. ``pd.isna`` catches
        NaN/NaT/None uniformly.
        """
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        s = str(value).strip()
        return s or None
