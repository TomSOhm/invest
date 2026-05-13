"""
Invest Solo -- Company API Router (M10)
Detailed company analysis endpoints with three-horizon scoring.

Endpoint list
-------------
GET /api/company/{ticker}                       — full CompanyDetail (all horizons)
GET /api/company/{ticker}/metrics               — raw financial metrics only
GET /api/company/{ticker}/horizons/{horizon}    — single horizon + DCF + quality/risk/momentum
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_company_service
from backend.app.models.company import CompanyDetail, CompanyMetrics
from backend.app.services.company_service import CompanyService

router = APIRouter(tags=["company"])

_VALID_HORIZONS = {"long_term", "medium_term", "short_term"}


@router.get("/{ticker}", response_model=CompanyDetail)
async def get_company_detail(
    ticker: str,
    svc: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:
    """Full company detail: metrics, three-horizon scoring, DCF, quality,
    risk, momentum signals, analyst ratings, and PEA eligibility."""
    return svc.get_detail(ticker.upper())


@router.get("/{ticker}/metrics", response_model=CompanyMetrics)
async def get_company_metrics(
    ticker: str,
    svc: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:
    """Raw financial metrics only (no scoring)."""
    return svc.get_metrics(ticker.upper())


@router.get("/{ticker}/horizons/{horizon}")
async def get_company_horizon(
    ticker: str,
    horizon: str,
    svc: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:
    """Single-horizon scoring view for a company.

    Returns the selected horizon's HorizonScoring block together with
    DCFValuation, QualitySignals, RiskSignals, and MomentumSignals so the
    caller can fetch only the data relevant to a specific investment
    timeframe without the full payload.

    ``horizon`` must be one of: ``long_term``, ``medium_term``, ``short_term``.
    """
    if horizon not in _VALID_HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid horizon '{horizon}'. Must be one of: {sorted(_VALID_HORIZONS)}",
        )
    return svc.get_horizon(ticker.upper(), horizon)
