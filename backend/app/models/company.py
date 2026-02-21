"""
Invest Solo -- Company detail Pydantic models.
"""
from typing import Optional

from pydantic import BaseModel, Field

from backend.app.models.common import ScoringBreakdown


class AnalystRatings(BaseModel):
    """Analyst consensus data."""

    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_buy: int = 0
    strong_sell: int = 0
    target_low: Optional[float] = None
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_median: Optional[float] = None


class CompanyMetrics(BaseModel):
    """Comprehensive financial metrics for a single company."""

    ticker: str
    name: str = ""
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    exchange: Optional[str] = None

    # Price & size
    price: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None

    # Valuation ratios
    pe: Optional[float] = None
    forward_pe: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    pfcf: Optional[float] = None
    ev_ebitda: Optional[float] = None
    ev_sales: Optional[float] = None
    peg: Optional[float] = None

    # Margins
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    fcf_margin: Optional[float] = None

    # Returns
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None

    # Growth
    revenue_growth: Optional[float] = None

    # Balance sheet
    current_ratio: Optional[float] = None
    debt_equity: Optional[float] = None
    interest_coverage: Optional[float] = None

    # Shareholder
    div_yield: Optional[float] = None
    payout_ratio: Optional[float] = None

    # Risk & ownership
    beta: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    fifty_two_week_high_pct: Optional[float] = None
    insider_pct: Optional[float] = None
    institutional_pct: Optional[float] = None
    short_pct_float: Optional[float] = None
    earnings_surprise_pct: Optional[float] = None


class CompanyDetail(BaseModel):
    """Full company detail response."""

    metrics: CompanyMetrics
    scoring: ScoringBreakdown
    analyst: Optional[AnalystRatings] = None
    pea_eligible: bool = False
    pea_pme_eligible: bool = False
    data_source: str = "yfinance"
    last_updated: str = ""
