"""
Invest Solo -- Portfolio Pydantic models (M10 schema).

Breaking change: composite_score / signal removed.
Replaced by score_lt / signal_lt (LT default). Use ?horizon= query param
on the endpoint to select a different view (served via enriched dict, not
model field rename — the model always exposes the full trio).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# CRUD request models (unchanged from M9)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class PortfolioPosition(BaseModel):
    """A single enriched portfolio position with live data and three-horizon scoring."""

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

    # Key valuation ratios
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

    # Three-horizon scoring (LT is the default portfolio view)
    score_lt: Optional[float] = Field(None, description="Long-term composite score 0-100")
    score_mt: Optional[float] = Field(None, description="Medium-term composite score 0-100")
    score_st: Optional[float] = Field(None, description="Short-term composite score 0-100")
    signal_lt: Optional[str] = Field(None, description="Long-term investment signal")
    signal_mt: Optional[str] = Field(None, description="Medium-term investment signal")
    signal_st: Optional[str] = Field(None, description="Short-term investment signal")

    # Quality indicators
    piotroski_f: Optional[int] = None
    altman_z: Optional[float] = None
    graham_number: Optional[float] = None
    graham_mos: Optional[float] = None
    dcf_mos_mid: Optional[float] = None

    # PEA
    pea_eligible: Optional[bool] = None
    pea_pme_eligible: Optional[bool] = None

    # Analyst
    analyst_rating: Optional[str] = None
    analyst_target_price: Optional[float] = None

    # Extra
    notes: Optional[str] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    fifty_two_week_high_pct: Optional[float] = None


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class PortfolioSummary(BaseModel):
    """Aggregated summary of the entire portfolio."""

    total_value: float = 0.0
    total_cost: float = 0.0
    total_gain_loss: float = 0.0
    total_gain_loss_pct: float = 0.0
    position_count: int = 0
    avg_score_lt: Optional[float] = Field(
        None, description="Portfolio average long-term score"
    )
    sector_allocation: Dict[str, float] = Field(default_factory=dict)
    country_allocation: Dict[str, float] = Field(default_factory=dict)
    signal_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Signal counts for the long-term horizon",
    )
    pea_value: float = 0.0
    cto_value: float = 0.0


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class PortfolioResponse(BaseModel):
    """Full portfolio API response."""

    positions: List[PortfolioPosition]
    summary: PortfolioSummary
    last_refreshed: str
    horizon: str = Field("long_term", description="Horizon used for signal_distribution")
