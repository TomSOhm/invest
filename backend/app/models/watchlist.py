"""
Invest Solo -- Watchlist Pydantic models (M10 schema).

Breaking change: composite_score / signal removed.
Replaced by score_lt / signal_lt as the default view.
All three horizon scores are exposed on each item.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# CRUD request models
# ---------------------------------------------------------------------------


class AddWatchlistRequest(BaseModel):
    """Request body for adding a stock to the watchlist."""

    ticker: str = Field(..., min_length=1, description="Stock ticker symbol")
    notes: Optional[str] = Field(None, description="Free-text notes")


# ---------------------------------------------------------------------------
# Watchlist item
# ---------------------------------------------------------------------------


class WatchlistItem(BaseModel):
    """A single enriched watchlist entry with live data and three-horizon scoring."""

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

    # Three-horizon scoring (LT is the default watchlist view)
    score_lt: Optional[float] = Field(None, description="Long-term composite score 0-100")
    score_mt: Optional[float] = Field(None, description="Medium-term composite score 0-100")
    score_st: Optional[float] = Field(None, description="Short-term composite score 0-100")
    signal_lt: Optional[str] = Field(None, description="Long-term investment signal")
    signal_mt: Optional[str] = Field(None, description="Medium-term investment signal")
    signal_st: Optional[str] = Field(None, description="Short-term investment signal")

    # Quality
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
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    fifty_two_week_high_pct: Optional[float] = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class WatchlistResponse(BaseModel):
    """Full watchlist API response."""

    items: List[WatchlistItem]
    last_refreshed: str
