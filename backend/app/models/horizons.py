"""
Invest Solo -- Horizon-aware Pydantic models (M10).

Defines the shared sub-models used by company detail, screener, portfolio,
and watchlist responses once the three-horizon scoring surface is exposed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Horizon scoring block
# ---------------------------------------------------------------------------


class HorizonScoring(BaseModel):
    """Score + signal + gate state for a single scoring horizon."""

    score: float = Field(..., description="Composite score 0-100 for this horizon")
    signal: Literal[
        "Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"
    ] = Field(..., description="Investment signal")
    passes_gates: bool = Field(..., description="All investability gates satisfied")
    blockers: List[str] = Field(
        default_factory=list,
        description="Names of failing gates when passes_gates is False",
    )
    recommended_account: Optional[Literal["PEA", "CTO"]] = Field(
        None, description="Recommended account type (CTO for ST presets)"
    )


# ---------------------------------------------------------------------------
# DCF valuation block
# ---------------------------------------------------------------------------


class DCFValuation(BaseModel):
    """Three-scenario DCF output (M6)."""

    fair_value_low: Optional[float] = Field(None, description="Pessimistic DCF intrinsic value")
    fair_value_mid: Optional[float] = Field(None, description="Base-case DCF intrinsic value")
    fair_value_high: Optional[float] = Field(None, description="Optimistic DCF intrinsic value")
    mos_low: Optional[float] = Field(
        None, description="Margin of safety vs low case: (FV - price) / price"
    )
    mos_mid: Optional[float] = Field(
        None, description="Margin of safety vs base case: (FV - price) / price"
    )
    mos_high: Optional[float] = Field(
        None, description="Margin of safety vs optimistic case: (FV - price) / price"
    )
    wacc_used: Optional[float] = Field(None, description="WACC used in the base-case DCF")
    warnings: List[str] = Field(
        default_factory=list, description="DCF computation warnings (e.g. missing FCF)"
    )


# ---------------------------------------------------------------------------
# Quality signals block
# ---------------------------------------------------------------------------


class QualitySignals(BaseModel):
    """Quality and earnings-integrity signals (M4/M5)."""

    piotroski_f: Optional[int] = Field(None, description="Piotroski F-Score 0-9", ge=0, le=9)
    altman_z: Optional[float] = Field(None, description="Altman Z-Score (classic or Z'')")
    altman_zone: Optional[Literal["Safe", "Grey", "Distress"]] = Field(
        None, description="Altman Z zone interpretation"
    )
    graham_number: Optional[float] = Field(None, description="Graham Number intrinsic value")
    graham_mos: Optional[float] = Field(
        None, description="Graham margin of safety: (Graham_Number / price - 1) * 100"
    )
    earnings_quality_score: Optional[float] = Field(
        None, description="Sector-relative earnings quality score 0-100 (M5)"
    )
    moat_score: Optional[float] = Field(
        None, description="Sector-relative economic moat score 0-100 (M5)"
    )
    m_score: Optional[float] = Field(None, description="Beneish M-Score (< -1.78 = low risk)")
    sloan_accruals: Optional[float] = Field(None, description="Sloan accruals ratio")
    cash_conversion_ratio_5y: Optional[float] = Field(
        None, description="5-year average FCF / Net Income"
    )


# ---------------------------------------------------------------------------
# Risk signals block
# ---------------------------------------------------------------------------


class RiskSignals(BaseModel):
    """Quantitative risk metrics (M5 Risk_Score_v2 + balance-sheet levers)."""

    risk_score: Optional[float] = Field(
        None, description="Sector-relative risk score 0-100 (higher = safer) (M5)"
    )
    realized_vol_1y: Optional[float] = Field(
        None, description="1-year annualised realised volatility"
    )
    max_drawdown_3y: Optional[float] = Field(
        None, description="3-year maximum drawdown (negative fraction)"
    )
    net_debt_ebitda: Optional[float] = Field(None, description="Net Debt / EBITDA")
    interest_coverage: Optional[float] = Field(None, description="EBIT / Interest Expense")
    beta: Optional[float] = Field(None, description="Market beta (52-week)")


# ---------------------------------------------------------------------------
# Momentum signals block
# ---------------------------------------------------------------------------


class MomentumSignals(BaseModel):
    """Price momentum and analyst revision signals (M9)."""

    momentum_12_1: Optional[float] = Field(
        None, description="12-minus-1 month price momentum (fraction)"
    )
    rs_3m: Optional[float] = Field(
        None, description="3-month relative strength vs market index"
    )
    above_50dma: Optional[bool] = Field(None, description="Price above 50-day MA")
    above_200dma: Optional[bool] = Field(None, description="Price above 200-day MA")
    golden_cross: Optional[bool] = Field(None, description="50dma above 200dma")
    volume_surge: Optional[float] = Field(
        None, description="5-day average volume / 90-day average volume"
    )
    eps_revision_30d: Optional[float] = Field(
        None, description="EPS consensus revision over the last 30 days (fraction)"
    )
    eps_revision_90d: Optional[float] = Field(
        None, description="EPS consensus revision over the last 90 days (fraction)"
    )
    sue_z_score: Optional[float] = Field(
        None, description="Standardised Unexpected Earnings z-score"
    )
    sentiment_30d: Optional[float] = Field(
        None, description="News sentiment score over 30 days (-1..+1)"
    )
    sentiment_trend: Optional[float] = Field(
        None, description="Trend in sentiment (positive = improving)"
    )


# ---------------------------------------------------------------------------
# Sub-scores block
# ---------------------------------------------------------------------------


class SubScores(BaseModel):
    """Six legacy sub-scores produced by the M3 scoring engine."""

    valuation: float = Field(..., description="Valuation sub-score 0-100")
    health: float = Field(..., description="Financial health sub-score 0-100")
    profitability: float = Field(..., description="Profitability sub-score 0-100")
    growth: float = Field(..., description="Growth sub-score 0-100")
    shareholder: float = Field(
        ..., description="Shareholder return sub-score 0-100 (legacy Shareholder_Score)"
    )
    risk_legacy: float = Field(
        ..., description="Legacy risk sub-score 0-100 (Risk_Score from M3, not Risk_Score_v2)"
    )
