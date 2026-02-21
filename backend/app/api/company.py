"""
Invest Solo -- Company API Router
Detailed company analysis endpoints.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_company_service
from backend.app.models.common import ScoringBreakdown
from backend.app.models.company import CompanyDetail, CompanyMetrics
from backend.app.services.company_service import CompanyService

router = APIRouter(tags=["company"])


@router.get("/{ticker}", response_model=CompanyDetail)
async def get_company_detail(
    ticker: str,
    svc: CompanyService = Depends(get_company_service),
) -> Dict[str, Any]:
    """Get full company detail: metrics, scoring, analyst ratings, PEA status."""
    return svc.get_detail(ticker.upper())


@router.get("/{ticker}/metrics", response_model=CompanyMetrics)
async def get_company_metrics(
    ticker: str,
    svc: CompanyService = Depends(get_company_service),
) -> Dict[str, Any]:
    """Get only the financial metrics for a company."""
    return svc.get_metrics(ticker.upper())


@router.get("/{ticker}/scoring", response_model=ScoringBreakdown)
async def get_company_scoring(
    ticker: str,
    svc: CompanyService = Depends(get_company_service),
) -> Dict[str, Any]:
    """Get only the scoring breakdown for a company."""
    return svc.get_scoring(ticker.upper())
