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


class AnalystChange(BaseModel):
    """One row of upgrades_downgrades history."""

    date: str
    firm: str = ""
    from_grade: str = ""
    to_grade: str = ""
    action: str = ""


class EpsRevisionRow(BaseModel):
    """One row of revision counts for a time window."""

    period: str  # "7d" | "30d" | "60d" | "90d"
    up: int = 0
    down: int = 0


class EarningsHistoryRow(BaseModel):
    """One quarterly earnings actual vs estimate row."""

    date: str
    eps_actual: float | None = None
    eps_estimate: float | None = None
    eps_difference: float | None = None
    surprise_pct: float | None = None


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

    # Sub-project 2 (yfinance.analysis enrichment) — all optional, backward-compatible
    num_analysts: int | None = None
    recent_changes: list[AnalystChange] | None = None
    revisions_history: list[EpsRevisionRow] | None = None
    growth_estimate_fy: float | None = None
    growth_estimate_5y: float | None = None
    earnings_history: list[EarningsHistoryRow] | None = None


# ---------------------------------------------------------------------------
# Company calendar (sub-project 3 — yfinance.calendars enrichment)
# ---------------------------------------------------------------------------


class DividendInfo(BaseModel):
    """One historical dividend payment."""

    ex_date: str
    amount: float


class CompanyCalendar(BaseModel):
    """Forward-looking earnings + dividend events and recent dividend history.

    All fields optional — non-US tickers may have partial coverage and recent
    IPOs may have no dividend history at all.
    """

    # Next earnings event
    next_earnings_date: str | None = None
    next_earnings_eps_estimate: float | None = None
    next_earnings_eps_low: float | None = None
    next_earnings_eps_high: float | None = None
    next_earnings_revenue_estimate: float | None = None

    # Next dividend event
    dividend_date: str | None = None
    ex_dividend_date: str | None = None
    dividend_amount: float | None = None
    dividend_yield: float | None = None
    dividend_rate: float | None = None
    trailing_annual_dividend_rate: float | None = None
    trailing_annual_dividend_yield: float | None = None

    # Dividend history (last ~5y, by ex-date asc)
    dividends_5y: list[DividendInfo] = Field(default_factory=list)


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

    data_source: str = "hybrid"
    effective_source: str = Field(
        "hybrid",
        description=(
            "Source that actually supplied the data. Equals data_source unless "
            "a fallback fired (e.g. user picked 'fmp' but quota was exhausted)."
        ),
    )
    source_fallback_message: str | None = Field(
        None,
        description=(
            "Set when the user-requested source was unavailable and the backend "
            "fell back to another one. Frontend should surface this to the user."
        ),
    )
    last_updated: str = ""

    score_source: Literal["universe", "single_row_fallback"] = Field(
        "single_row_fallback",
        description=(
            "'universe' when the score came from the screener's scored cache "
            "(peer-relative percentiles); 'single_row_fallback' when it was "
            "computed in isolation (peer percentiles approximate)"
        ),
    )
