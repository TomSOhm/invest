"""
Invest Solo -- Watchlist Pydantic models (M10 schema).

Breaking change: composite_score / signal removed.
Replaced by score_lt / signal_lt as the default view.
All three horizon scores are exposed on each item.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# CRUD request models
# ---------------------------------------------------------------------------


class AddWatchlistRequest(BaseModel):
    """Request body for adding a stock to the watchlist."""

    ticker: str = Field(..., min_length=1, description="Stock ticker symbol")
    notes: str | None = Field(None, description="Free-text notes")


# ---------------------------------------------------------------------------
# Watchlist item
# ---------------------------------------------------------------------------


class WatchlistItem(BaseModel):
    """A single enriched watchlist entry with live data and three-horizon scoring."""

    id: str
    ticker: str
    name: str | None = None
    sector: str | None = None
    country: str | None = None
    added_date: str | None = None
    notes: str | None = None

    # Live data
    current_price: float | None = None
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None

    # Three-horizon scoring (LT is the default watchlist view)
    score_lt: float | None = Field(None, description="Long-term composite score 0-100")
    score_mt: float | None = Field(None, description="Medium-term composite score 0-100")
    score_st: float | None = Field(None, description="Short-term composite score 0-100")
    signal_lt: str | None = Field(None, description="Long-term investment signal")
    signal_mt: str | None = Field(None, description="Medium-term investment signal")
    signal_st: str | None = Field(None, description="Short-term investment signal")

    # Quality
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
    forward_pe: float | None = None
    peg: float | None = None
    fifty_two_week_high_pct: float | None = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class WatchlistResponse(BaseModel):
    """Full watchlist API response."""

    items: list[WatchlistItem]
    last_refreshed: str
