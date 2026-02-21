"""
Invest Solo -- Common Pydantic models shared across the API.
"""
from typing import Dict, Optional

from pydantic import BaseModel, Field


class ScoringBreakdown(BaseModel):
    """Full scoring breakdown for a single stock."""

    composite_score: Optional[float] = Field(None, description="Overall 0-100 composite score")
    signal: Optional[str] = Field(None, description="Investment signal (Strong Buy -> Strong Sell)")
    valuation_score: Optional[float] = Field(None, description="Valuation sub-score 0-100")
    health_score: Optional[float] = Field(None, description="Financial health sub-score 0-100")
    profitability_score: Optional[float] = Field(None, description="Profitability sub-score 0-100")
    growth_score: Optional[float] = Field(None, description="Growth sub-score 0-100")
    shareholder_score: Optional[float] = Field(None, description="Shareholder return sub-score 0-100")
    risk_score: Optional[float] = Field(None, description="Risk sub-score 0-100 (higher = safer)")
    piotroski_f: Optional[int] = Field(None, description="Piotroski F-Score 0-9")
    altman_z: Optional[float] = Field(None, description="Altman Z-Score")
    graham_number: Optional[float] = Field(None, description="Graham Number intrinsic value")
    graham_mos: Optional[float] = Field(None, description="Graham margin of safety (%)")
    scoring_weights: Optional[Dict[str, float]] = Field(
        None, description="Weights used for composite score"
    )
