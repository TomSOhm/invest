"""
Invest Solo -- Screener Pydantic models (M10 schema).

Breaking change: composite_score / signal replaced by score_lt/mt/st and
signal_lt/mt/st. The horizon param drives which score drives sort order.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ScreenerRequest(BaseModel):
    """Request body for running a custom horizon-aware screen."""

    horizon: Literal["long_term", "medium_term", "short_term"] = Field(
        "long_term",
        description="Scoring horizon that drives sort order and gate filtering",
    )
    preset: Optional[str] = Field(
        None,
        description="Named preset from PRESET_REGISTRY (overrides custom_filters when set)",
    )
    custom_filters: Optional[Dict[str, Any]] = Field(
        None,
        description="Ad-hoc filter key-value pairs passed directly to apply_filters",
    )
    pea_only: bool = Field(False, description="Restrict to PEA-eligible stocks only")
    sort_by: str = Field(
        "score",
        description=(
            "Column to sort by. 'score' maps to score_<horizon>. "
            "Other accepted values: 'pe', 'roe', 'market_cap', 'div_yield', "
            "'revenue_growth', 'altman_z', 'piotroski_f'."
        ),
    )
    sort_desc: bool = Field(True, description="Sort descending")
    limit: int = Field(50, ge=1, le=500, description="Max results to return")


# ---------------------------------------------------------------------------
# Result item
# ---------------------------------------------------------------------------


class ScreenerResultItem(BaseModel):
    """A single row returned by the screener."""

    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    pea_eligible: bool = False

    # Three-horizon scores
    score_lt: float = Field(..., description="Long-term composite score 0-100")
    score_mt: float = Field(..., description="Medium-term composite score 0-100")
    score_st: float = Field(..., description="Short-term composite score 0-100")

    # Signals
    signal_lt: str = Field(..., description="Long-term investment signal")
    signal_mt: str = Field(..., description="Medium-term investment signal")
    signal_st: str = Field(..., description="Short-term investment signal")

    # Gate pass/fail per horizon
    passes_gates_lt: bool = Field(..., description="All LT investability gates satisfied")
    passes_gates_mt: bool = Field(..., description="All MT investability gates satisfied")
    passes_gates_st: bool = Field(..., description="All ST investability gates satisfied")

    # Key raw metrics
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    div_yield: Optional[float] = None
    revenue_growth: Optional[float] = None
    market_cap: Optional[float] = None
    altman_z: Optional[float] = None
    piotroski_f: Optional[int] = None
    dcf_mos_mid: Optional[float] = Field(None, description="DCF mid-case margin of safety")

    # Preset / account metadata
    recommended_account: Optional[str] = Field(
        None, description="'CTO' for short-term presets; 'PEA' when preset is PEA-strict"
    )
    blockers: List[str] = Field(
        default_factory=list,
        description="Failing gate keys for the requested horizon",
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class ScreenerSummary(BaseModel):
    """Aggregate statistics for the screener run."""

    total_passed: int = Field(0, description="Rows that passed all filters")
    total_universe: int = Field(0, description="Rows in the input universe")
    avg_score: Optional[float] = Field(
        None, description="Mean score for the requested horizon"
    )
    signal_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of each signal value for the requested horizon",
    )
    horizon: str = Field("long_term", description="Horizon used for this run")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class ScreenerResponse(BaseModel):
    """Full screener API response."""

    results: List[ScreenerResultItem]
    summary: ScreenerSummary
    last_refreshed: Optional[str] = Field(
        None,
        description="ISO timestamp of the last screener-cache refresh, or None when never refreshed",
    )


# ---------------------------------------------------------------------------
# Refresh endpoint response
# ---------------------------------------------------------------------------


class ScreenerRefreshResponse(BaseModel):
    """Summary returned by POST /api/screener/refresh."""

    tickers_fetched: int = Field(..., description="Number of tickers with usable data after fetch")
    tickers_failed: List[str] = Field(
        default_factory=list,
        description="Tickers that returned no usable data (failed live fetch)",
    )
    last_refreshed: str = Field(..., description="ISO timestamp of completion")
    duration_seconds: float = Field(..., description="Elapsed wall-clock seconds for the refresh")
    universe_size: int = Field(..., description="Total rows in the resulting scored cache")
