"""
Invest Solo -- Portfolio Service (M10)
Enriches stored positions with live data, three-horizon scoring, and P&L.

Key changes vs M9:
- composite_score / signal replaced by score_lt/mt/st + signal_lt/mt/st
- avg_composite_score in summary replaced by avg_score_lt
- signal_distribution uses LT signals by default
- horizon param passed through get_portfolio for optional view selection

Cache strategy (T1):
- get_portfolio(): cache-only -- no live FMP/yfinance calls.
- refresh(): force-live -- invalidates cache, then fetches live data.
- add_position(): live fetch for the single new ticker only.
- update_position(): live fetch for the affected ticker only.
- Per-ticker try/except prevents one bad ticker from 500-ing the whole list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.models.portfolio import (
    AddPositionRequest,
    UpdatePositionRequest,
)
from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.scoring_service import ScoringService
from backend.app.storage.portfolio_store import PortfolioStore


class PortfolioService:
    """Combines storage, live data, and scoring for portfolio management."""

    def __init__(
        self,
        store: PortfolioStore,
        fetcher: DataFetcher,
        scorer: ScoringService,
    ) -> None:
        self._store = store
        self._fetcher = fetcher
        self._scorer = scorer

    def get_portfolio(self, horizon: str = "long_term") -> dict[str, Any]:
        """
        Load all positions, enrich with cached data, scoring, and P&L.

        This method is cache-only: it never fires live FMP or yfinance calls.
        Positions without a cache entry return degraded rows (NaN scoring
        fields, None price/market_value).  Per-ticker try/except ensures one
        bad ticker never 500s the whole list.

        Parameters
        ----------
        horizon : str
            "long_term" | "medium_term" | "short_term". Determines which
            signal column drives signal_distribution in the summary.

        Returns a dict matching PortfolioResponse schema.
        """
        return self._build_enriched_response(horizon=horizon, cache_only=True)

    def refresh(self, horizon: str = "long_term") -> dict[str, Any]:
        """
        Force-refresh: invalidate cache for all stored tickers and re-fetch live.

        Parameters
        ----------
        horizon : str
            Passed through to the summary computation.

        Returns the freshly enriched portfolio.
        """
        positions = self._store.get_positions()
        tickers = {p["ticker"] for p in positions}
        for ticker in tickers:
            self._fetcher._cache.invalidate(f"hybrid:{ticker}")
            # Also invalidate the legacy key pattern used elsewhere
            self._fetcher._cache.invalidate(f"ticker_{ticker}")
        return self._build_enriched_response(horizon=horizon, cache_only=False)

    def add_position(self, req: AddPositionRequest) -> dict[str, Any]:
        """Add a position to the portfolio store and trigger a live fetch for it."""
        stored = self._store.add_position(
            ticker=req.ticker,
            quantity=req.quantity,
            buy_price=req.buy_price,
            buy_date=req.buy_date,
            account_type=req.account_type,
            notes=req.notes,
        )

        # Trigger a live fetch for the new ticker so scoring fields populate
        # immediately. Wrap in try/except -- if FMP/yf both fail the stored
        # row is returned with NaN scoring fields.
        try:
            self._fetcher.fetch_single(req.ticker, cache_only=False)
        except Exception as exc:
            logger.warning(
                f"Live fetch failed for newly added position {req.ticker}: {exc}. "
                "Row will have degraded scoring fields until next Refresh."
            )

        return stored

    def update_position(self, position_id: str, req: UpdatePositionRequest) -> dict[str, Any] | None:
        """Update a position in the store and refresh live data for that ticker."""
        updates = req.model_dump(exclude_none=True)
        updated = self._store.update_position(position_id, updates)

        if updated is not None:
            ticker = updated.get("ticker")
            if ticker:
                try:
                    # Invalidate and re-fetch for the affected ticker only
                    self._fetcher._cache.invalidate(f"hybrid:{ticker}")
                    self._fetcher._cache.invalidate(f"ticker_{ticker}")
                    self._fetcher.fetch_single(ticker, cache_only=False)
                except Exception as exc:
                    logger.warning(f"Live fetch failed for updated position {ticker}: {exc}.")

        return updated

    def remove_position(self, position_id: str) -> bool:
        """Remove a position by id."""
        return self._store.remove_position(position_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_enriched_response(self, horizon: str = "long_term", cache_only: bool = True) -> dict[str, Any]:
        """
        Build the full enriched portfolio response.

        Parameters
        ----------
        horizon:
            "long_term" | "medium_term" | "short_term".
        cache_only:
            When True, only serve cached data (no live FMP/yfinance calls).
            When False, force-live (all tickers re-fetched).
        """
        raw_positions = self._store.get_positions()
        if not raw_positions:
            return {
                "positions": [],
                "summary": self._empty_summary(),
                "last_refreshed": datetime.now(UTC).isoformat(),
                "horizon": horizon,
            }

        tickers = list({p["ticker"] for p in raw_positions})
        mode = "cache-only" if cache_only else "force-live"
        logger.info(f"Enriching {len(raw_positions)} positions ({len(tickers)} unique tickers) [{mode}]")

        # Fetch data per ticker
        live_data: dict[str, dict[str, Any]] = {}
        for ticker in tickers:
            try:
                live_data[ticker] = self._fetcher.fetch_single(ticker, cache_only=cache_only)
            except Exception as exc:
                logger.warning(f"fetch_single failed for portfolio ticker {ticker}: {exc}. Using empty row.")
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

        # Fetch analyst ratings -- only in force-live mode
        analyst_data: dict[str, dict[str, Any] | None] = {}
        if not cache_only:
            for ticker in tickers:
                try:
                    analyst_data[ticker] = self._fetcher.fetch_analyst_ratings(ticker)
                except Exception as exc:
                    logger.warning(f"fetch_analyst_ratings failed for {ticker}: {exc}")
                    analyst_data[ticker] = None
        else:
            analyst_data = {ticker: None for ticker in tickers}

        # Build enriched positions
        enriched: list[dict[str, Any]] = []
        for pos in raw_positions:
            ticker = pos["ticker"]
            try:
                ld = live_data.get(ticker, {})
                sc = scored.get(ticker, {})
                an = analyst_data.get(ticker)

                current_price = self._num(ld.get("Price"))
                quantity = pos["quantity"]
                buy_price = pos["buy_price"]
                cost_basis = quantity * buy_price
                market_value = quantity * current_price if current_price else None
                gain_loss = (market_value - cost_basis) if market_value is not None else None
                gain_loss_pct = (gain_loss / cost_basis * 100) if gain_loss is not None and cost_basis > 0 else None

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
                        "id": pos["id"],
                        "ticker": ticker,
                        "name": self._str(ld.get("Name")) or ticker,
                        "sector": self._str(ld.get("Sector")),
                        "country": self._str(ld.get("Country")),
                        "account_type": pos.get("account_type", "pea"),
                        "quantity": quantity,
                        "buy_price": buy_price,
                        "buy_date": pos.get("buy_date"),
                        "current_price": current_price,
                        "market_value": round(market_value, 2) if market_value is not None else None,
                        "cost_basis": round(cost_basis, 2),
                        "gain_loss": round(gain_loss, 2) if gain_loss is not None else None,
                        "gain_loss_pct": round(gain_loss_pct, 2) if gain_loss_pct is not None else None,
                        "weight_pct": None,  # Computed after all positions
                        "pe": self._num(ld.get("PE")),
                        "pb": self._num(ld.get("PB")),
                        "ps": self._num(ld.get("PS")),
                        "roe": self._num(ld.get("ROE")),
                        "roa": self._num(ld.get("ROA")),
                        "roic": self._num(ld.get("ROIC")),
                        "operating_margin": self._num(ld.get("OperatingMargin")),
                        "net_margin": self._num(ld.get("NetMargin")),
                        "revenue_growth": self._num(ld.get("RevenueGrowth")),
                        "div_yield": self._num(ld.get("DivYield")),
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
                        # Extra
                        "notes": pos.get("notes"),
                        "forward_pe": self._num(ld.get("ForwardPE")),
                        "peg": self._num(ld.get("PEG")),
                        "analyst_rating": analyst_rating,
                        "analyst_target_price": analyst_target,
                        "fifty_two_week_high_pct": fifty_two_pct,
                    }
                )
            except Exception as exc:
                logger.warning(f"Enrichment failed for portfolio ticker {ticker}: {exc}. Inserting degraded row.")
                quantity = pos["quantity"]
                buy_price = pos["buy_price"]
                enriched.append(
                    {
                        "id": pos["id"],
                        "ticker": ticker,
                        "name": ticker,
                        "sector": None,
                        "country": None,
                        "account_type": pos.get("account_type", "pea"),
                        "quantity": quantity,
                        "buy_price": buy_price,
                        "buy_date": pos.get("buy_date"),
                        "current_price": None,
                        "market_value": None,
                        "cost_basis": round(quantity * buy_price, 2),
                        "gain_loss": None,
                        "gain_loss_pct": None,
                        "weight_pct": None,
                        "pe": None,
                        "pb": None,
                        "ps": None,
                        "roe": None,
                        "roa": None,
                        "roic": None,
                        "operating_margin": None,
                        "net_margin": None,
                        "revenue_growth": None,
                        "div_yield": None,
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
                        "notes": pos.get("notes"),
                        "forward_pe": None,
                        "peg": None,
                        "analyst_rating": None,
                        "analyst_target_price": None,
                        "fifty_two_week_high_pct": None,
                    }
                )

        # Compute weight percentages
        total_value = sum(p["market_value"] for p in enriched if p["market_value"] is not None)
        if total_value > 0:
            for p in enriched:
                if p["market_value"] is not None:
                    p["weight_pct"] = round(p["market_value"] / total_value * 100, 2)

        summary = self._compute_summary(enriched, horizon=horizon)

        return {
            "positions": enriched,
            "summary": summary,
            "last_refreshed": datetime.now(UTC).isoformat(),
            "horizon": horizon,
        }

    def _compute_summary(self, positions: list[dict[str, Any]], horizon: str = "long_term") -> dict[str, Any]:
        """Aggregate portfolio statistics."""
        if not positions:
            return self._empty_summary()

        total_value = sum(p["market_value"] or 0 for p in positions)
        total_cost = sum(p["cost_basis"] or 0 for p in positions)
        total_gl = total_value - total_cost
        total_gl_pct = (total_gl / total_cost * 100) if total_cost > 0 else 0.0

        # LT scores for portfolio average
        scores_lt = [p["score_lt"] for p in positions if p.get("score_lt") is not None]
        avg_score_lt = round(np.mean(scores_lt), 1) if scores_lt else None

        # Signal distribution uses the selected horizon
        signal_key = {
            "long_term": "signal_lt",
            "medium_term": "signal_mt",
            "short_term": "signal_st",
        }.get(horizon, "signal_lt")

        sector_alloc: dict[str, float] = {}
        country_alloc: dict[str, float] = {}
        signal_dist: dict[str, int] = {}
        pea_value = 0.0
        cto_value = 0.0

        for p in positions:
            mv = p["market_value"] or 0
            sector = p.get("sector") or "Unknown"
            country = p.get("country") or "Unknown"
            signal = p.get(signal_key) or "N/A"
            account = p.get("account_type", "pea")

            sector_alloc[sector] = sector_alloc.get(sector, 0) + mv
            country_alloc[country] = country_alloc.get(country, 0) + mv
            signal_dist[signal] = signal_dist.get(signal, 0) + 1

            if account in ("pea", "pea_pme"):
                pea_value += mv
            else:
                cto_value += mv

        if total_value > 0:
            sector_alloc = {k: round(v / total_value * 100, 1) for k, v in sector_alloc.items()}
            country_alloc = {k: round(v / total_value * 100, 1) for k, v in country_alloc.items()}

        return {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_gain_loss": round(total_gl, 2),
            "total_gain_loss_pct": round(total_gl_pct, 2),
            "position_count": len(positions),
            "avg_score_lt": avg_score_lt,
            "sector_allocation": sector_alloc,
            "country_allocation": country_alloc,
            "signal_distribution": signal_dist,
            "pea_value": round(pea_value, 2),
            "cto_value": round(cto_value, 2),
        }

    @staticmethod
    def _empty_summary() -> dict[str, Any]:
        return {
            "total_value": 0.0,
            "total_cost": 0.0,
            "total_gain_loss": 0.0,
            "total_gain_loss_pct": 0.0,
            "position_count": 0,
            "avg_score_lt": None,
            "sector_allocation": {},
            "country_allocation": {},
            "signal_distribution": {},
            "pea_value": 0.0,
            "cto_value": 0.0,
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
        and break Pydantic str validation downstream.
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
