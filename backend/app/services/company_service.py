"""
Invest Solo -- Company Service (M10)
Fetches, scores, and assembles the CompanyDetail response.

Key changes vs M9:
- Returns three-horizon block + DCF + quality + risk + momentum sub-models
- Legacy composite_score / signal removed from response
- Uses 1-row DataFrame through score_universe to get M7 horizon columns
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import screener_cache
from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.scoring_service import ScoringService


class CompanyService:
    """Provides detailed company analysis by combining fetcher and scorer."""

    def __init__(self, fetcher: DataFetcher, scorer: ScoringService) -> None:
        self._fetcher = fetcher
        self._scorer = scorer

    def get_detail(self, ticker: str, source: str = "hybrid") -> dict[str, Any]:
        """
        Full company detail: metrics + three-horizon scoring + DCF + quality
        + risk + momentum blocks + analyst ratings + PEA status.

        ``source`` selects which backend feeds the live fetch. When ``source``
        is anything other than ``"hybrid"`` the screener-universe cache is
        bypassed so the user-chosen backend actually drives the data.
        """
        cached_row = screener_cache.lookup(ticker) if source == "hybrid" else None
        if cached_row is not None:
            data = cached_row
            scoring = self._scorer.extract_scoring_from_row(pd.Series(cached_row))
            score_source = "universe"
        else:
            data = self._fetcher.fetch_single(ticker, source=source)
            series = pd.Series(data)
            scoring = self._scorer.score_single(series)
            score_source = "single_row_fallback"

        analyst = self._fetcher.fetch_analyst_ratings(ticker, source=source)

        current_price = self._num(data.get("Price"))
        high_52 = self._num(data.get("FiftyTwoWeekHigh"))
        fifty_two_pct: float | None = None
        if current_price and high_52 and high_52 > 0:
            fifty_two_pct = round((current_price / high_52 - 1) * 100, 1)

        # --- Raw metrics ---
        metrics = {
            "ticker": ticker,
            "name": self._str(data.get("Name")) or ticker,
            "sector": self._str(data.get("Sector")),
            "industry": self._str(data.get("Industry")),
            "country": self._str(data.get("Country")),
            "exchange": self._str(data.get("Exchange")),
            "price": current_price,
            "market_cap": self._num(data.get("MarketCap")),
            "enterprise_value": self._num(data.get("EV")),
            "pe": self._num(data.get("PE")),
            "forward_pe": self._num(data.get("ForwardPE")),
            "pb": self._num(data.get("PB")),
            "ps": self._num(data.get("PS")),
            "pfcf": self._num(data.get("PFCF")),
            "ev_ebitda": self._num(data.get("EV_EBITDA")),
            "ev_sales": self._num(data.get("EV_Sales")),
            "peg": self._num(data.get("PEG")),
            "gross_margin": self._num(data.get("GrossMargin")),
            "operating_margin": self._num(data.get("OperatingMargin")),
            "net_margin": self._num(data.get("NetMargin")),
            "fcf_margin": self._num(data.get("FCFMargin")),
            "roe": self._num(data.get("ROE")),
            "roa": self._num(data.get("ROA")),
            "roic": self._num(data.get("ROIC")),
            "revenue_growth": self._num(data.get("RevenueGrowth")),
            "current_ratio": self._num(data.get("CurrentRatio")),
            "debt_equity": self._num(data.get("DebtEquity")),
            "interest_coverage": self._num(data.get("InterestCoverage")),
            "div_yield": self._num(data.get("DivYield")),
            "payout_ratio": self._num(data.get("PayoutRatio")),
            "beta": self._num(data.get("Beta")),
            "fifty_two_week_high": self._num(data.get("FiftyTwoWeekHigh")),
            "fifty_two_week_low": self._num(data.get("FiftyTwoWeekLow")),
            "fifty_two_week_high_pct": fifty_two_pct,
            "insider_pct": self._num(data.get("InsiderPct")),
            "institutional_pct": self._num(data.get("InstitutionalPct")),
            "short_pct_float": self._num(data.get("ShortPctFloat")),
            "earnings_surprise_pct": None,
        }

        # --- Sub-scores ---
        sub_scores = {
            "valuation": scoring.get("valuation_score") or 50.0,
            "health": scoring.get("health_score") or 50.0,
            "profitability": scoring.get("profitability_score") or 50.0,
            "growth": scoring.get("growth_score") or 50.0,
            "shareholder": scoring.get("shareholder_score") or 50.0,
            "risk_legacy": scoring.get("risk_score") or 50.0,
        }

        # --- Quality signals ---
        quality = {
            "piotroski_f": scoring.get("piotroski_f"),
            "piotroski_satisfied": scoring.get("piotroski_satisfied"),
            "piotroski_violated": scoring.get("piotroski_violated"),
            "piotroski_unknown": scoring.get("piotroski_unknown"),
            "altman_z": scoring.get("altman_z"),
            "altman_zone": scoring.get("altman_zone"),
            "graham_number": scoring.get("graham_number"),
            "graham_mos": scoring.get("graham_mos"),
            "earnings_quality_score": scoring.get("earnings_quality_score"),
            "moat_score": scoring.get("moat_score"),
            "m_score": scoring.get("m_score"),
            "sloan_accruals": scoring.get("sloan_accruals"),
            "cash_conversion_ratio_5y": scoring.get("cash_conversion_ratio_5y"),
        }

        return {
            "ticker": ticker,
            "name": self._str(data.get("Name")) or ticker,
            "sector": self._str(data.get("Sector")),
            "industry": self._str(data.get("Industry")),
            "country": self._str(data.get("Country")),
            "exchange": self._str(data.get("Exchange")),
            "pea_eligible": bool(data.get("PEA", False)),
            "pea_pme_eligible": bool(data.get("PEA_PME", False)),
            "price": current_price,
            "market_cap": self._num(data.get("MarketCap")),
            "horizons": scoring.get("horizons", {}),
            "sub_scores": sub_scores,
            "valuation": scoring.get("dcf", {}),
            "quality": quality,
            "risk": scoring.get("risk", {}),
            "momentum": scoring.get("momentum", {}),
            "metrics": metrics,
            "analyst_ratings": analyst,
            "data_completeness": scoring.get("data_completeness", 0.0),
            "data_source": source,
            "effective_source": data.get("effective_source", source),
            "source_fallback_message": data.get("source_fallback_message"),
            "last_updated": datetime.now(UTC).isoformat(),
            "score_source": score_source,
        }

    def get_metrics(self, ticker: str, source: str = "hybrid") -> dict[str, Any]:
        """Return only the raw metrics portion of company detail."""
        detail = self.get_detail(ticker, source=source)
        return detail["metrics"]

    def get_horizon(
        self,
        ticker: str,
        horizon: str,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        """
        Return the selected horizon's scoring block plus DCF valuation.

        Parameters
        ----------
        ticker : str
        horizon : str
            "long_term" | "medium_term" | "short_term"
        source : str
            "hybrid" | "yfinance" | "fmp"
        """
        detail = self.get_detail(ticker, source=source)
        horizons_block = detail.get("horizons", {})
        horizon_data = horizons_block.get(horizon, {})
        return {
            "ticker": ticker,
            "horizon": horizon,
            "scoring": horizon_data,
            "valuation": detail.get("valuation", {}),
            "quality": detail.get("quality", {}),
            "risk": detail.get("risk", {}),
            "momentum": detail.get("momentum", {}),
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
