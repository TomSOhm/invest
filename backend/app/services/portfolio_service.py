"""
Invest Solo -- Portfolio Service
Enriches stored positions with live data, scoring, and P&L calculations.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

    def get_portfolio(self) -> Dict[str, Any]:
        """
        Load all positions, enrich with live data and scoring, compute P&L.
        Returns a dict matching PortfolioResponse schema.
        """
        raw_positions = self._store.get_positions()
        if not raw_positions:
            return {
                "positions": [],
                "summary": self._empty_summary(),
                "last_refreshed": datetime.now(timezone.utc).isoformat(),
            }

        tickers = list({p["ticker"] for p in raw_positions})
        logger.info(f"Enriching {len(raw_positions)} positions ({len(tickers)} unique tickers)")

        # Fetch live data for all unique tickers
        live_data: Dict[str, Dict[str, Any]] = {}
        for ticker in tickers:
            live_data[ticker] = self._fetcher.fetch_single(ticker)

        # Score each ticker
        scored: Dict[str, Dict[str, Any]] = {}
        for ticker, data in live_data.items():
            series = pd.Series(data)
            scored[ticker] = self._scorer.score_single(series)

        # Fetch analyst ratings
        analyst_data: Dict[str, Optional[Dict[str, Any]]] = {}
        for ticker in tickers:
            analyst_data[ticker] = self._fetcher.fetch_analyst_ratings(ticker)

        # Build enriched positions
        enriched: List[Dict[str, Any]] = []
        for pos in raw_positions:
            ticker = pos["ticker"]
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

            # 52-week high %
            high_52 = self._num(ld.get("FiftyTwoWeekHigh"))
            fifty_two_pct = None
            if current_price and high_52 and high_52 > 0:
                fifty_two_pct = round((current_price / high_52 - 1) * 100, 1)

            # Analyst summary
            analyst_rating = None
            analyst_target = None
            if an:
                total = an.get("buy", 0) + an.get("hold", 0) + an.get("sell", 0) + an.get("strong_buy", 0) + an.get("strong_sell", 0)
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

            enriched.append({
                "id": pos["id"],
                "ticker": ticker,
                "name": ld.get("Name") or ticker,
                "sector": ld.get("Sector") or None,
                "country": ld.get("Country") or None,
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
                "composite_score": sc.get("composite_score"),
                "signal": sc.get("signal"),
                "piotroski_f": sc.get("piotroski_f"),
                "altman_z": sc.get("altman_z"),
                "graham_number": sc.get("graham_number"),
                "graham_mos": sc.get("graham_mos"),
                "valuation_score": sc.get("valuation_score"),
                "health_score": sc.get("health_score"),
                "profitability_score": sc.get("profitability_score"),
                "growth_score": sc.get("growth_score"),
                "shareholder_score": sc.get("shareholder_score"),
                "risk_score": sc.get("risk_score"),
                "pea_eligible": bool(ld.get("PEA", False)),
                "pea_pme_eligible": bool(ld.get("PEA_PME", False)),
                "notes": pos.get("notes"),
                "forward_pe": self._num(ld.get("ForwardPE")),
                "peg": self._num(ld.get("PEG")),
                "analyst_rating": analyst_rating,
                "analyst_target_price": analyst_target,
                "fifty_two_week_high_pct": fifty_two_pct,
            })

        # Compute weight percentages
        total_value = sum(p["market_value"] for p in enriched if p["market_value"] is not None)
        if total_value > 0:
            for p in enriched:
                if p["market_value"] is not None:
                    p["weight_pct"] = round(p["market_value"] / total_value * 100, 2)

        summary = self._compute_summary(enriched)

        return {
            "positions": enriched,
            "summary": summary,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
        }

    def add_position(self, req: AddPositionRequest) -> Dict[str, Any]:
        """Add a position to the portfolio store and return it."""
        return self._store.add_position(
            ticker=req.ticker,
            quantity=req.quantity,
            buy_price=req.buy_price,
            buy_date=req.buy_date,
            account_type=req.account_type,
            notes=req.notes,
        )

    def update_position(self, position_id: str, req: UpdatePositionRequest) -> Optional[Dict[str, Any]]:
        """Update a position in the store."""
        updates = req.model_dump(exclude_none=True)
        return self._store.update_position(position_id, updates)

    def remove_position(self, position_id: str) -> bool:
        """Remove a position by id."""
        return self._store.remove_position(position_id)

    def refresh(self) -> Dict[str, Any]:
        """Force-refresh by invalidating caches and re-fetching."""
        # Invalidate cache for all tickers in the portfolio
        positions = self._store.get_positions()
        tickers = {p["ticker"] for p in positions}
        for ticker in tickers:
            self._fetcher._cache.invalidate(f"ticker_{ticker}")
        return self.get_portfolio()

    # -- private helpers --

    def _compute_summary(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate portfolio statistics."""
        if not positions:
            return self._empty_summary()

        total_value = sum(p["market_value"] or 0 for p in positions)
        total_cost = sum(p["cost_basis"] or 0 for p in positions)
        total_gl = total_value - total_cost
        total_gl_pct = (total_gl / total_cost * 100) if total_cost > 0 else 0.0

        # Scores
        scores = [p["composite_score"] for p in positions if p["composite_score"] is not None]
        avg_score = round(np.mean(scores), 1) if scores else None

        # Sector allocation
        sector_alloc: Dict[str, float] = {}
        country_alloc: Dict[str, float] = {}
        signal_dist: Dict[str, int] = {}
        pea_value = 0.0
        cto_value = 0.0

        for p in positions:
            mv = p["market_value"] or 0
            sector = p.get("sector") or "Unknown"
            country = p.get("country") or "Unknown"
            signal = p.get("signal") or "N/A"
            account = p.get("account_type", "pea")

            sector_alloc[sector] = sector_alloc.get(sector, 0) + mv
            country_alloc[country] = country_alloc.get(country, 0) + mv
            signal_dist[signal] = signal_dist.get(signal, 0) + 1

            if account in ("pea", "pea_pme"):
                pea_value += mv
            else:
                cto_value += mv

        # Convert allocations to percentages
        if total_value > 0:
            sector_alloc = {k: round(v / total_value * 100, 1) for k, v in sector_alloc.items()}
            country_alloc = {k: round(v / total_value * 100, 1) for k, v in country_alloc.items()}

        return {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_gain_loss": round(total_gl, 2),
            "total_gain_loss_pct": round(total_gl_pct, 2),
            "position_count": len(positions),
            "avg_composite_score": avg_score,
            "sector_allocation": sector_alloc,
            "country_allocation": country_alloc,
            "signal_distribution": signal_dist,
            "pea_value": round(pea_value, 2),
            "cto_value": round(cto_value, 2),
        }

    @staticmethod
    def _empty_summary() -> Dict[str, Any]:
        return {
            "total_value": 0.0,
            "total_cost": 0.0,
            "total_gain_loss": 0.0,
            "total_gain_loss_pct": 0.0,
            "position_count": 0,
            "avg_composite_score": None,
            "sector_allocation": {},
            "country_allocation": {},
            "signal_distribution": {},
            "pea_value": 0.0,
            "cto_value": 0.0,
        }

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
