"""
Invest Solo -- Company detail Pydantic models (M10 schema).

Breaking change: legacy composite_score / signal / ScoringBreakdown fields
are removed. Replaced by the three-horizon block + quality/risk/momentum
sub-models from horizons.py.
"""
from __future__ import annotations

from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field

from backend.app.models.horizons import (
    DCFValuation,
    HorizonScoring,
    MomentumSignals,
    QualitySignals,
    RiskSignals,
    SubScores,
)


# ---------------------------------------------------------------------------
# Analyst ratings
# ---------------------------------------------------------------------------


class AnalystRatings(BaseModel):
    """Analyst consensus ratings and price targets."""

    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_buy: int = 0
    strong_sell: int = 0
    target_low: Optional[float] = None
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_median: Optional[float] = None


# ---------------------------------------------------------------------------
# Raw financial metrics
# ---------------------------------------------------------------------------


class CompanyMetrics(BaseModel):
    """Raw financial metrics for a single company (no scoring)."""

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


# ---------------------------------------------------------------------------
# Full company detail
# ---------------------------------------------------------------------------


class CompanyDetail(BaseModel):
    """Full company detail response (M10 schema).

    All scoring is exposed through the three-horizon block; legacy
    composite_score / signal fields have been removed.
    """

    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    exchange: Optional[str] = None
    pea_eligible: bool = False
    pea_pme_eligible: bool = False

    price: Optional[float] = None
    market_cap: Optional[float] = None

    # Three-horizon scoring (long_term / medium_term / short_term)
    horizons: Dict[
        Literal["long_term", "medium_term", "short_term"],
        HorizonScoring,
    ] = Field(..., description="Horizon-specific scores, signals, and gate states")

    sub_scores: SubScores = Field(..., description="Six legacy M3 sub-scores")
    valuation: DCFValuation = Field(..., description="M6 three-scenario DCF block")
    quality: QualitySignals = Field(..., description="Piotroski / Altman / Graham / M5 quality")
    risk: RiskSignals = Field(..., description="M5 risk signals + balance-sheet levers")
    momentum: MomentumSignals = Field(..., description="M9 price momentum and revision signals")

    metrics: CompanyMetrics = Field(..., description="Raw financial metrics (ratios, margins)")
    analyst_ratings: Optional[AnalystRatings] = None
    data_completeness: float = Field(0.0, description="Fraction of scoring inputs present 0-1")

    data_source: str = "yfinance"
    last_updated: str = ""
