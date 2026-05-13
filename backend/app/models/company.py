"""
Invest Solo -- Company detail Pydantic models (M10 schema).

Breaking change: legacy composite_score / signal / ScoringBreakdown fields
are removed. Replaced by the three-horizon block + quality/risk/momentum
sub-models from horizons.py.
"""

from __future__ import annotations

from typing import Literal

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
    target_low: float | None = None
    target_mean: float | None = None
    target_high: float | None = None
    target_median: float | None = None


# ---------------------------------------------------------------------------
# Raw financial metrics
# ---------------------------------------------------------------------------


class CompanyMetrics(BaseModel):
    """Raw financial metrics for a single company (no scoring)."""

    ticker: str
    name: str = ""
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    exchange: str | None = None

    # Price & size
    price: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None

    # Valuation ratios
    pe: float | None = None
    forward_pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    pfcf: float | None = None
    ev_ebitda: float | None = None
    ev_sales: float | None = None
    peg: float | None = None

    # Margins
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    fcf_margin: float | None = None

    # Returns
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None

    # Growth
    revenue_growth: float | None = None

    # Balance sheet
    current_ratio: float | None = None
    debt_equity: float | None = None
    interest_coverage: float | None = None

    # Shareholder
    div_yield: float | None = None
    payout_ratio: float | None = None

    # Risk & ownership
    beta: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    fifty_two_week_high_pct: float | None = None
    insider_pct: float | None = None
    institutional_pct: float | None = None
    short_pct_float: float | None = None
    earnings_surprise_pct: float | None = None


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
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    exchange: str | None = None
    pea_eligible: bool = False
    pea_pme_eligible: bool = False

    price: float | None = None
    market_cap: float | None = None

    # Three-horizon scoring (long_term / medium_term / short_term)
    horizons: dict[
        Literal["long_term", "medium_term", "short_term"],
        HorizonScoring,
    ] = Field(..., description="Horizon-specific scores, signals, and gate states")

    sub_scores: SubScores = Field(..., description="Six legacy M3 sub-scores")
    valuation: DCFValuation = Field(..., description="M6 three-scenario DCF block")
    quality: QualitySignals = Field(..., description="Piotroski / Altman / Graham / M5 quality")
    risk: RiskSignals = Field(..., description="M5 risk signals + balance-sheet levers")
    momentum: MomentumSignals = Field(..., description="M9 price momentum and revision signals")

    metrics: CompanyMetrics = Field(..., description="Raw financial metrics (ratios, margins)")
    analyst_ratings: AnalystRatings | None = None
    data_completeness: float = Field(0.0, description="Fraction of scoring inputs present 0-1")

    data_source: str = "yfinance"
    last_updated: str = ""

    score_source: Literal["universe", "single_row_fallback"] = Field(
        "single_row_fallback",
        description=(
            "'universe' when the score came from the screener's scored cache "
            "(peer-relative percentiles); 'single_row_fallback' when it was "
            "computed in isolation (peer percentiles approximate)"
        ),
    )
