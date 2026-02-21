"""
Invest Solo -- Portfolio API Router
CRUD operations and live-data refresh for portfolio positions.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_portfolio_service
from backend.app.models.portfolio import (
    AddPositionRequest,
    PortfolioResponse,
    UpdatePositionRequest,
)
from backend.app.services.portfolio_service import PortfolioService

router = APIRouter(tags=["portfolio"])


@router.get("/", response_model=PortfolioResponse)
async def get_portfolio(
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Return the full portfolio with live data and scoring."""
    return svc.get_portfolio()


@router.post("/positions")
async def add_position(
    req: AddPositionRequest,
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Add a new position to the portfolio."""
    position = svc.add_position(req)
    return {"success": True, "position": position}


@router.put("/positions/{position_id}")
async def update_position(
    position_id: str,
    req: UpdatePositionRequest,
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Update an existing position."""
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
    svc: PortfolioService = Depends(get_portfolio_service),
) -> Dict[str, Any]:
    """Force-refresh all live data for the portfolio."""
    return svc.refresh()
