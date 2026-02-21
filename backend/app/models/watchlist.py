"""
Invest Solo -- Watchlist Pydantic models.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class AddWatchlistRequest(BaseModel):
    """Request body for adding a stock to the watchlist."""

    ticker: str = Field(..., min_length=1, description="Stock ticker symbol")
    notes: Optional[str] = Field(None, description="Free-text notes")


class WatchlistItem(BaseModel):
    """A single enriched watchlist entry with live data and scoring."""

    id: str
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    added_date: Optional[str] = None
    notes: Optional[str] = None

    # Live data
    current_price: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None

    # Scoring
    composite_score: Optional[float] = None
    signal: Optional[str] = None
    piotroski_f: Optional[int] = None
    altman_z: Optional[float] = None
    graham_number: Optional[float] = None
    graham_mos: Optional[float] = None

    # PEA
    pea_eligible: Optional[bool] = None
    pea_pme_eligible: Optional[bool] = None

    # Extra
    analyst_rating: Optional[str] = None
    analyst_target_price: Optional[float] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    fifty_two_week_high_pct: Optional[float] = None


class WatchlistResponse(BaseModel):
    """Full watchlist API response."""

    items: List[WatchlistItem]
    last_refreshed: str
