"""
Invest Solo -- Horizon-aware Pydantic models (M10).

Defines the shared sub-models used by company detail, screener, portfolio,
and watchlist responses once the three-horizon scoring surface is exposed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Horizon scoring block
# ---------------------------------------------------------------------------


class HorizonScoring(BaseModel):
    """Score + signal + gate state for a single scoring horizon."""

    score: float = Field(..., description="Composite score 0-100 for this horizon")
    signal: Literal["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell", "Insufficient Data"] = Field(
        ..., description="Investment signal (Insufficient Data when data-quality gates fail)"
    )
    passes_gates: bool = Field(..., description="All investability gates satisfied")
    blockers: list[str] = Field(
        default_factory=list,
        description="Names of failing gates when passes_gates is False",
    )
    recommended_account: Literal["PEA", "CTO"] | None = Field(
        None, description="Recommended account type (CTO for ST presets)"
    )


# ---------------------------------------------------------------------------
# DCF valuation block
# ---------------------------------------------------------------------------


class DCFValuation(BaseModel):
    """Three-scenario DCF output (M6)."""

    fair_value_low: float | None = Field(None, description="Pessimistic DCF intrinsic value")
    fair_value_mid: float | None = Field(None, description="Base-case DCF intrinsic value")
    fair_value_high: float | None = Field(None, description="Optimistic DCF intrinsic value")
    mos_low: float | None = Field(None, description="Margin of safety vs low case: (FV - price) / price")
    mos_mid: float | None = Field(None, description="Margin of safety vs base case: (FV - price) / price")
    mos_high: float | None = Field(None, description="Margin of safety vs optimistic case: (FV - price) / price")
    wacc_used: float | None = Field(None, description="WACC used in the base-case DCF")
    warnings: list[str] = Field(default_factory=list, description="DCF computation warnings (e.g. missing FCF)")


# ---------------------------------------------------------------------------
# Quality signals block
# ---------------------------------------------------------------------------


class QualitySignals(BaseModel):
    """Quality and earnings-integrity signals (M4/M5)."""

    piotroski_f: int | None = Field(None, description="Piotroski F-Score 0-9", ge=0, le=9)
    altman_z: float | None = Field(None, description="Altman Z-Score (classic or Z'')")
    altman_zone: Literal["Safe", "Grey", "Distress"] | None = Field(None, description="Altman Z zone interpretation")
    graham_number: float | None = Field(None, description="Graham Number intrinsic value")
    graham_mos: float | None = Field(None, description="Graham margin of safety: (Graham_Number / price - 1) * 100")
    earnings_quality_score: float | None = Field(None, description="Sector-relative earnings quality score 0-100 (M5)")
    moat_score: float | None = Field(None, description="Sector-relative economic moat score 0-100 (M5)")
    m_score: float | None = Field(None, description="Beneish M-Score (< -1.78 = low risk)")
    sloan_accruals: float | None = Field(None, description="Sloan accruals ratio")
    cash_conversion_ratio_5y: float | None = Field(None, description="5-year average FCF / Net Income")


# ---------------------------------------------------------------------------
# Risk signals block
# ---------------------------------------------------------------------------


class RiskSignals(BaseModel):
    """Quantitative risk metrics (M5 Risk_Score_v2 + balance-sheet levers)."""

    risk_score: float | None = Field(None, description="Sector-relative risk score 0-100 (higher = safer) (M5)")
    realized_vol_1y: float | None = Field(None, description="1-year annualised realised volatility")
    max_drawdown_3y: float | None = Field(None, description="3-year maximum drawdown (negative fraction)")
    net_debt_ebitda: float | None = Field(None, description="Net Debt / EBITDA")
    interest_coverage: float | None = Field(None, description="EBIT / Interest Expense")
    beta: float | None = Field(None, description="Market beta (52-week)")


# ---------------------------------------------------------------------------
# Momentum signals block
# ---------------------------------------------------------------------------


class MomentumSignals(BaseModel):
    """Price momentum and analyst revision signals (M9)."""

    momentum_12_1: float | None = Field(None, description="12-minus-1 month price momentum (fraction)")
    rs_3m: float | None = Field(None, description="3-month relative strength vs market index")
    above_50dma: bool | None = Field(None, description="Price above 50-day MA")
    above_200dma: bool | None = Field(None, description="Price above 200-day MA")
    golden_cross: bool | None = Field(None, description="50dma above 200dma")
    volume_surge: float | None = Field(None, description="5-day average volume / 90-day average volume")
    eps_revision_30d: float | None = Field(None, description="EPS consensus revision over the last 30 days (fraction)")
    eps_revision_90d: float | None = Field(None, description="EPS consensus revision over the last 90 days (fraction)")
    sue_z_score: float | None = Field(None, description="Standardised Unexpected Earnings z-score")
    sentiment_30d: float | None = Field(None, description="News sentiment score over 30 days (-1..+1)")
    sentiment_trend: float | None = Field(None, description="Trend in sentiment (positive = improving)")


# ---------------------------------------------------------------------------
# Sub-scores block
# ---------------------------------------------------------------------------


class SubScores(BaseModel):
    """Six legacy sub-scores produced by the M3 scoring engine."""

    valuation: float = Field(..., description="Valuation sub-score 0-100")
    health: float = Field(..., description="Financial health sub-score 0-100")
    profitability: float = Field(..., description="Profitability sub-score 0-100")
    growth: float = Field(..., description="Growth sub-score 0-100")
    shareholder: float = Field(..., description="Shareholder return sub-score 0-100 (legacy Shareholder_Score)")
    risk_legacy: float = Field(..., description="Legacy risk sub-score 0-100 (Risk_Score from M3, not Risk_Score_v2)")
