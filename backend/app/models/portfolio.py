"""
Invest Solo -- Portfolio Pydantic models.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AddPositionRequest(BaseModel):
    """Request body for adding a new portfolio position."""

    ticker: str = Field(..., min_length=1, description="Stock ticker symbol (e.g. TTE.PA)")
    quantity: float = Field(..., gt=0, description="Number of shares")
    buy_price: float = Field(..., gt=0, description="Average purchase price per share")
    buy_date: Optional[str] = Field(None, description="Date of purchase (YYYY-MM-DD)")
    account_type: str = Field(
        "pea",
        pattern=r"^(pea|pea_pme|cto)$",
        description="Account type: pea, pea_pme, or cto",
    )
    notes: Optional[str] = Field(None, description="Free-text notes")


class UpdatePositionRequest(BaseModel):
    """Request body for updating an existing portfolio position."""

    quantity: Optional[float] = Field(None, gt=0, description="Updated number of shares")
    buy_price: Optional[float] = Field(None, gt=0, description="Updated average purchase price")
    buy_date: Optional[str] = Field(None, description="Updated purchase date (YYYY-MM-DD)")
    notes: Optional[str] = Field(None, description="Updated notes")


class PortfolioPosition(BaseModel):
    """A single enriched portfolio position with live data and scoring."""

    id: str
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    account_type: str
    quantity: float
    buy_price: float
    buy_date: Optional[str] = None
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_pct: Optional[float] = None
    weight_pct: Optional[float] = None

    # Valuation ratios
    pe: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    revenue_growth: Optional[float] = None
    div_yield: Optional[float] = None

    # Scoring
    composite_score: Optional[float] = None
    signal: Optional[str] = None
    piotroski_f: Optional[int] = None
    altman_z: Optional[float] = None
    graham_number: Optional[float] = None
    graham_mos: Optional[float] = None
    valuation_score: Optional[float] = None
    health_score: Optional[float] = None
    profitability_score: Optional[float] = None
    growth_score: Optional[float] = None
    shareholder_score: Optional[float] = None
    risk_score: Optional[float] = None

    # PEA
    pea_eligible: Optional[bool] = None
    pea_pme_eligible: Optional[bool] = None

    # Extra
    notes: Optional[str] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    analyst_rating: Optional[str] = None
    analyst_target_price: Optional[float] = None
    fifty_two_week_high_pct: Optional[float] = None


class PortfolioSummary(BaseModel):
    """Aggregated summary of the entire portfolio."""

    total_value: float = 0.0
    total_cost: float = 0.0
    total_gain_loss: float = 0.0
    total_gain_loss_pct: float = 0.0
    position_count: int = 0
    avg_composite_score: Optional[float] = None
    sector_allocation: Dict[str, float] = Field(default_factory=dict)
    country_allocation: Dict[str, float] = Field(default_factory=dict)
    signal_distribution: Dict[str, int] = Field(default_factory=dict)
    pea_value: float = 0.0
    cto_value: float = 0.0


class PortfolioResponse(BaseModel):
    """Full portfolio API response."""

    positions: List[PortfolioPosition]
    summary: PortfolioSummary
    last_refreshed: str
