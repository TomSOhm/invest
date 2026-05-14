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

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.dependencies import get_chart_service, get_company_service
from backend.app.models.chart import PriceHistoryResponse
from backend.app.models.company import CompanyCalendar, CompanyDetail, CompanyMetrics
from backend.app.services.chart_service import ChartService
from backend.app.services.company_service import CompanyService
from backend.app.services.market_data.types import SOURCES

router = APIRouter(tags=["company"])

import re

_VALID_HORIZONS = {"long_term", "medium_term", "short_term"}
_VALID_PERIODS = {"1M", "3M", "6M", "1Y", "5Y", "MAX"}
_VALID_BENCHMARKS = {"^GSPC", "^FCHI", "^FTSE", "^GDAXI", "^STOXX", "^IXIC"}
_TICKER_RE = re.compile(r"^[A-Z0-9.\^_-]{1,12}$")


def _validate_source(source: str) -> None:
    if source not in SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{source}'. Must be one of: {list(SOURCES)}",
        )


def _validate_ticker(ticker: str) -> str:
    """Reject malformed tickers before they reach yfinance / cache layer."""
    t = ticker.upper()
    if not _TICKER_RE.match(t):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid ticker '{ticker}'. Must match [A-Z0-9.^_-]{{1,12}}.",
        )
    return t


@router.get("/{ticker}", response_model=CompanyDetail)
async def get_company_detail(
    ticker: str,
    source: str = Query("hybrid", description="Data source: hybrid|yfinance|fmp"),
    svc: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:
    """Full company detail: metrics, three-horizon scoring, DCF, quality,
    risk, momentum signals, analyst ratings, and PEA eligibility."""
    _validate_source(source)
    return svc.get_detail(_validate_ticker(ticker), source=source)


@router.get("/{ticker}/metrics", response_model=CompanyMetrics)
async def get_company_metrics(
    ticker: str,
    source: str = Query("hybrid"),
    svc: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:
    """Raw financial metrics only (no scoring)."""
    _validate_source(source)
    return svc.get_metrics(_validate_ticker(ticker), source=source)


@router.get("/{ticker}/horizons/{horizon}")
async def get_company_horizon(
    ticker: str,
    horizon: str,
    source: str = Query("hybrid"),
    svc: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:
    """Single-horizon scoring view for a company."""
    if horizon not in _VALID_HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid horizon '{horizon}'. Must be one of: {sorted(_VALID_HORIZONS)}",
        )
    _validate_source(source)
    return svc.get_horizon(_validate_ticker(ticker), horizon, source=source)


@router.get("/{ticker}/price-history", response_model=PriceHistoryResponse)
async def get_company_price_history(
    ticker: str,
    period: str = Query("1Y", description="1M | 3M | 6M | 1Y | 5Y | MAX"),
    benchmark: str | None = Query(None, description="Benchmark yfinance symbol, e.g. ^GSPC, ^FCHI"),
    svc: ChartService = Depends(get_chart_service),
) -> dict[str, Any]:
    """OHLCV candles + benchmark overlay + 6 derived metrics + 50/200d MAs.

    Source-agnostic (prices are universally identical across yfinance/FMP).
    """
    if period not in _VALID_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid period '{period}'. Must be one of: {sorted(_VALID_PERIODS)}",
        )
    if benchmark is not None and benchmark not in _VALID_BENCHMARKS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid benchmark '{benchmark}'. Allowed: {sorted(_VALID_BENCHMARKS)}",
        )
    return svc.get_price_history(
        _validate_ticker(ticker),
        period=period,
        benchmark=benchmark,
    )


@router.get("/{ticker}/calendar", response_model=CompanyCalendar)
async def get_company_calendar(
    ticker: str,
    source: str = Query("hybrid", description="Data source: hybrid|yfinance|fmp"),
    svc: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:
    """Forward-looking earnings + dividend events and recent dividend history.

    yfinance is the only backing source for sub-project 3; ``source`` is
    honored for cache-key isolation only (returns identical data regardless
    of source).
    """
    _validate_source(source)
    return svc.get_calendar(_validate_ticker(ticker), source=source)
