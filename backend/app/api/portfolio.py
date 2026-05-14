"""
Invest Solo -- Portfolio API Router (M10)
CRUD operations and live-data refresh for portfolio positions.

?horizon= query param selects which scoring horizon drives signal_distribution
in the summary (default: long_term). All three horizon scores are always
present on every PortfolioPosition regardless of the horizon param.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.dependencies import get_portfolio_service
from backend.app.models.portfolio import (
    AddPositionRequest,
    PortfolioResponse,
    UpdatePositionRequest,
)
from backend.app.services.market_data.types import SOURCES
from backend.app.services.portfolio_service import PortfolioService

router = APIRouter(tags=["portfolio"])

_VALID_HORIZONS = {"long_term", "medium_term", "short_term"}


def _validate_source(source: str) -> None:
    if source not in SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{source}'. Must be one of: {list(SOURCES)}",
        )


def _validate_horizon(horizon: str) -> None:
    if horizon not in _VALID_HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid horizon '{horizon}'. Must be one of: {sorted(_VALID_HORIZONS)}",
        )


@router.get("/", response_model=PortfolioResponse)
async def get_portfolio(
    horizon: str = Query("long_term"),
    source: str = Query("hybrid"),
    svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Cache-only portfolio read with three-horizon scoring and P&L."""
    _validate_horizon(horizon)
    _validate_source(source)
    return svc.get_portfolio(horizon=horizon, source=source)


@router.post("/positions")
async def add_position(
    req: AddPositionRequest,
    source: str = Query("hybrid"),
    svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Add a position; triggers a live fetch for the new ticker via ``source``."""
    _validate_source(source)
    position = svc.add_position(req, source=source)
    return {"success": True, "position": position}


@router.put("/positions/{position_id}")
async def update_position(
    position_id: str,
    req: UpdatePositionRequest,
    source: str = Query("hybrid"),
    svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Update an existing position; refresh live data for that ticker via source."""
    _validate_source(source)
    result = svc.update_position(position_id, req, source=source)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    return {"success": True, "position": result}


@router.delete("/positions/{position_id}")
async def remove_position(
    position_id: str,
    svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Remove a position from the portfolio."""
    removed = svc.remove_position(position_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    return {"success": True, "message": f"Position {position_id} removed"}


@router.post("/refresh", response_model=PortfolioResponse)
async def refresh_portfolio(
    horizon: str = Query("long_term"),
    source: str = Query("hybrid"),
    svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Force-refresh all live data for the portfolio."""
    _validate_horizon(horizon)
    _validate_source(source)
    return svc.refresh(horizon=horizon, source=source)
