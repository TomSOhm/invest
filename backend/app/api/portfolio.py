"""
Invest Solo -- Portfolio API Router (M10)
CRUD operations and live-data refresh for portfolio positions.

?horizon= query param selects which scoring horizon drives signal_distribution
in the summary (default: long_term). All three horizon scores are always
present on every PortfolioPosition regardless of the horizon param.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.dependencies import get_portfolio_service
from backend.app.models.portfolio import (
    AddPositionRequest,
    PortfolioResponse,
    UpdatePositionRequest,
)
from backend.app.services.portfolio_service import PortfolioService

router = APIRouter(tags=["portfolio"])

_VALID_HORIZONS = {"long_term", "medium_term", "short_term"}


@router.get("/", response_model=PortfolioResponse)
async def get_portfolio(
    horizon: str = Query(
        "long_term",
        description="Horizon for signal_distribution in summary: long_term | medium_term | short_term",
    ),
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Return the full portfolio with cached data, three-horizon scoring, and P&L.

    This endpoint is cache-only: no live FMP/yfinance calls are made.
    Positions without a cache entry return degraded rows (NaN scoring fields,
    None price/market_value).  Use POST /refresh to trigger a live re-fetch.

    All three horizon scores (score_lt, score_mt, score_st) are present on
    every position. The ``horizon`` param only affects which signal column is
    used for the summary's signal_distribution bucket.
    """
    if horizon not in _VALID_HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid horizon '{horizon}'. "
                   f"Must be one of: {sorted(_VALID_HORIZONS)}",
        )
    return svc.get_portfolio(horizon=horizon)


@router.post("/positions")
async def add_position(
    req: AddPositionRequest,
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Add a new position to the portfolio.

    Triggers a live fetch for the new ticker only. Returns 200 even if both
    FMP and yfinance fail (degraded row).
    """
    position = svc.add_position(req)
    return {"success": True, "position": position}


@router.put("/positions/{position_id}")
async def update_position(
    position_id: str,
    req: UpdatePositionRequest,
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Update an existing position.

    If the ticker is unchanged, re-fetches live data for that ticker only.
    """
    result = svc.update_position(position_id, req)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    return {"success": True, "position": result}


@router.delete("/positions/{position_id}")
async def remove_position(
    position_id: str,
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Remove a position from the portfolio."""
    removed = svc.remove_position(position_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    return {"success": True, "message": f"Position {position_id} removed"}


@router.post("/refresh", response_model=PortfolioResponse)
async def refresh_portfolio(
    horizon: str = Query("long_term", description="Horizon for summary signal_distribution"),
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Force-refresh all live data for the portfolio.

    Invalidates the cache for every stored ticker and re-fetches live data
    from FMP (with yfinance fallback). Analyst ratings are included.
    """
    if horizon not in _VALID_HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid horizon '{horizon}'. "
                   f"Must be one of: {sorted(_VALID_HORIZONS)}",
        )
    return svc.refresh(horizon=horizon)
