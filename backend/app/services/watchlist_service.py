"""
Invest Solo -- Watchlist Service (M10)
Enriches stored watchlist items with live data and three-horizon scoring.

Key changes vs M9:
- composite_score / signal replaced by score_lt/mt/st + signal_lt/mt/st
- dcf_mos_mid exposed on each item
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

    def get_watchlist(self) -> Dict[str, Any]:
        """
        Load watchlist, enrich with live data and three-horizon scoring.
        Returns a dict matching WatchlistResponse schema.
        """
        raw_items = self._store.get_items()
        if not raw_items:
            return {
                "items": [],
                "last_refreshed": datetime.now(timezone.utc).isoformat(),
            }

        tickers = list({item["ticker"] for item in raw_items})
        logger.info(f"Enriching {len(raw_items)} watchlist items ({len(tickers)} unique)")

        # Fetch live data
        live_data: Dict[str, Dict[str, Any]] = {}
        for ticker in tickers:
            live_data[ticker] = self._fetcher.fetch_single(ticker)

        # Score each
        scored: Dict[str, Dict[str, Any]] = {}
        for ticker, data in live_data.items():
            series = pd.Series(data)
            scored[ticker] = self._scorer.score_single(series)

        # Fetch analyst ratings
        analyst_data: Dict[str, Optional[Dict[str, Any]]] = {}
        for ticker in tickers:
            analyst_data[ticker] = self._fetcher.fetch_analyst_ratings(ticker)

        enriched: List[Dict[str, Any]] = []
        for item in raw_items:
            ticker = item["ticker"]
            ld = live_data.get(ticker, {})
            sc = scored.get(ticker, {})
            an = analyst_data.get(ticker)

            current_price = self._num(ld.get("Price"))

            high_52 = self._num(ld.get("FiftyTwoWeekHigh"))
            fifty_two_pct: Optional[float] = None
            if current_price and high_52 and high_52 > 0:
                fifty_two_pct = round((current_price / high_52 - 1) * 100, 1)

            analyst_rating: Optional[str] = None
            analyst_target: Optional[float] = None
            if an:
                total = (
                    an.get("buy", 0) + an.get("hold", 0) + an.get("sell", 0)
                    + an.get("strong_buy", 0) + an.get("strong_sell", 0)
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

            enriched.append({
                "id": item["id"],
                "ticker": ticker,
                "name": ld.get("Name") or ticker,
                "sector": ld.get("Sector") or None,
                "country": ld.get("Country") or None,
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
            })

        return {
            "items": enriched,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
        }

    def add_item(self, req: AddWatchlistRequest) -> Dict[str, Any]:
        """Add a ticker to the watchlist."""
        return self._store.add_item(ticker=req.ticker, notes=req.notes)

    def remove_item(self, item_id: str) -> bool:
        """Remove a watchlist item by id."""
        return self._store.remove_item(item_id)

    @staticmethod
    def _num(value: Any) -> Optional[float]:
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
