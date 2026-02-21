"""
Invest Solo -- Company Service
Fetches, scores, and enriches data for individual companies.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.scoring_service import ScoringService


class CompanyService:
    """Provides detailed company analysis by combining fetcher and scorer."""

    def __init__(self, fetcher: DataFetcher, scorer: ScoringService) -> None:
        self._fetcher = fetcher
        self._scorer = scorer

    def get_detail(self, ticker: str) -> Dict[str, Any]:
        """
        Full company detail: metrics + scoring + analyst ratings + PEA status.
        Returns a dict matching CompanyDetail schema.
        """
        data = self._fetcher.fetch_single(ticker)
        series = pd.Series(data)
        scoring = self._scorer.score_single(series)
        analyst = self._fetcher.fetch_analyst_ratings(ticker)

        current_price = self._num(data.get("Price"))
        high_52 = self._num(data.get("FiftyTwoWeekHigh"))
        fifty_two_pct = None
        if current_price and high_52 and high_52 > 0:
            fifty_two_pct = round((current_price / high_52 - 1) * 100, 1)

        metrics = {
            "ticker": ticker,
            "name": data.get("Name") or ticker,
            "sector": data.get("Sector") or None,
            "industry": data.get("Industry") or None,
            "country": data.get("Country") or None,
            "exchange": data.get("Exchange") or None,
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
            "earnings_surprise_pct": None,  # Not directly available from yfinance .info
        }

        scoring_breakdown = {
            "composite_score": scoring.get("composite_score"),
            "signal": scoring.get("signal"),
            "valuation_score": scoring.get("valuation_score"),
            "health_score": scoring.get("health_score"),
            "profitability_score": scoring.get("profitability_score"),
            "growth_score": scoring.get("growth_score"),
            "shareholder_score": scoring.get("shareholder_score"),
            "risk_score": scoring.get("risk_score"),
            "piotroski_f": scoring.get("piotroski_f"),
            "altman_z": scoring.get("altman_z"),
            "graham_number": scoring.get("graham_number"),
            "graham_mos": scoring.get("graham_mos"),
            "scoring_weights": self._scorer.get_weights(),
        }

        return {
            "metrics": metrics,
            "scoring": scoring_breakdown,
            "analyst": analyst,
            "pea_eligible": bool(data.get("PEA", False)),
            "pea_pme_eligible": bool(data.get("PEA_PME", False)),
            "data_source": "yfinance",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def get_metrics(self, ticker: str) -> Dict[str, Any]:
        """Return only the metrics portion of company detail."""
        detail = self.get_detail(ticker)
        return detail["metrics"]

    def get_scoring(self, ticker: str) -> Dict[str, Any]:
        """Return only the scoring breakdown for a ticker."""
        detail = self.get_detail(ticker)
        return detail["scoring"]

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
