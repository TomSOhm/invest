"""
Invest Solo -- Screener Pydantic models.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScreenerFilters(BaseModel):
    """User-defined screening filter thresholds. All optional."""

    min_market_cap: Optional[float] = None
    max_market_cap: Optional[float] = None
    min_pe: Optional[float] = None
    max_pe: Optional[float] = None
    min_roe: Optional[float] = None
    min_current_ratio: Optional[float] = None
    max_debt_equity: Optional[float] = None
    min_interest_coverage: Optional[float] = None
    min_operating_margin: Optional[float] = None
    min_fcf: Optional[float] = None
    min_composite_score: Optional[float] = None
    min_div_yield: Optional[float] = None
    max_payout_ratio: Optional[float] = None
    min_revenue_growth: Optional[float] = None


class ScreenerRequest(BaseModel):
    """Request body for running a custom screen."""

    filters: ScreenerFilters = Field(default_factory=ScreenerFilters)
    pea_only: bool = Field(False, description="Restrict to PEA-eligible stocks only")
    sort_by: str = Field("composite_score", description="Column to sort by")
    sort_desc: bool = Field(True, description="Sort descending")
    limit: int = Field(50, ge=1, le=500, description="Max results to return")


class ScreenerResultItem(BaseModel):
    """A single result row from the screener."""

    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    price: Optional[float] = None
    market_cap: Optional[float] = None

    # Scoring
    composite_score: Optional[float] = None
    signal: Optional[str] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    div_yield: Optional[float] = None
    revenue_growth: Optional[float] = None
    piotroski_f: Optional[int] = None
    altman_z: Optional[float] = None
    graham_mos: Optional[float] = None
    pea_eligible: Optional[bool] = None

    # Sub-scores
    valuation_score: Optional[float] = None
    health_score: Optional[float] = None
    profitability_score: Optional[float] = None
    growth_score: Optional[float] = None


class ScreenerSummary(BaseModel):
    """Summary statistics for the screener run."""

    total_screened: int = 0
    total_passed: int = 0
    avg_score: Optional[float] = None
    signal_distribution: Dict[str, int] = Field(default_factory=dict)
    sector_distribution: Dict[str, int] = Field(default_factory=dict)


class ScreenerResponse(BaseModel):
    """Full screener API response."""

    results: List[ScreenerResultItem]
    summary: ScreenerSummary
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
