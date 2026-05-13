"""
Invest Solo -- Portfolio Pydantic models (M10 schema).

Breaking change: composite_score / signal removed.
Replaced by score_lt / signal_lt (LT default). Use ?horizon= query param
on the endpoint to select a different view (served via enriched dict, not
model field rename — the model always exposes the full trio).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# CRUD request models (unchanged from M9)
# ---------------------------------------------------------------------------


class AddPositionRequest(BaseModel):
    """Request body for adding a new portfolio position."""

    ticker: str = Field(..., min_length=1, description="Stock ticker symbol (e.g. TTE.PA)")
    quantity: float = Field(..., gt=0, description="Number of shares")
    buy_price: float = Field(..., gt=0, description="Average purchase price per share")
    buy_date: str | None = Field(None, description="Date of purchase (YYYY-MM-DD)")
    account_type: str = Field(
        "pea",
        pattern=r"^(pea|pea_pme|cto)$",
        description="Account type: pea, pea_pme, or cto",
    )
    notes: str | None = Field(None, description="Free-text notes")


class UpdatePositionRequest(BaseModel):
    """Request body for updating an existing portfolio position."""

    quantity: float | None = Field(None, gt=0, description="Updated number of shares")
    buy_price: float | None = Field(None, gt=0, description="Updated average purchase price")
    buy_date: str | None = Field(None, description="Updated purchase date (YYYY-MM-DD)")
    notes: str | None = Field(None, description="Updated notes")


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class PortfolioPosition(BaseModel):
    """A single enriched portfolio position with live data and three-horizon scoring."""

    id: str
    ticker: str
    name: str | None = None
    sector: str | None = None
    country: str | None = None
    account_type: str
    quantity: float
    buy_price: float
    buy_date: str | None = None
    current_price: float | None = None
    market_value: float | None = None
    cost_basis: float | None = None
    gain_loss: float | None = None
    gain_loss_pct: float | None = None
    weight_pct: float | None = None

    # Key valuation ratios
    pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    revenue_growth: float | None = None
    div_yield: float | None = None

    # Three-horizon scoring (LT is the default portfolio view)
    score_lt: float | None = Field(None, description="Long-term composite score 0-100")
    score_mt: float | None = Field(None, description="Medium-term composite score 0-100")
    score_st: float | None = Field(None, description="Short-term composite score 0-100")
    signal_lt: str | None = Field(None, description="Long-term investment signal")
    signal_mt: str | None = Field(None, description="Medium-term investment signal")
    signal_st: str | None = Field(None, description="Short-term investment signal")

    # Quality indicators
    piotroski_f: int | None = None
    altman_z: float | None = None
    graham_number: float | None = None
    graham_mos: float | None = None
    dcf_mos_mid: float | None = None

    # PEA
    pea_eligible: bool | None = None
    pea_pme_eligible: bool | None = None

    # Analyst
    analyst_rating: str | None = None
    analyst_target_price: float | None = None

    # Extra
    notes: str | None = None
    forward_pe: float | None = None
    peg: float | None = None
    fifty_two_week_high_pct: float | None = None


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
    avg_score_lt: float | None = Field(None, description="Portfolio average long-term score")
    sector_allocation: dict[str, float] = Field(default_factory=dict)
    country_allocation: dict[str, float] = Field(default_factory=dict)
    signal_distribution: dict[str, int] = Field(
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

    positions: list[PortfolioPosition]
    summary: PortfolioSummary
    last_refreshed: str
    horizon: str = Field("long_term", description="Horizon used for signal_distribution")
