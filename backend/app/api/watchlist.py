"""
Invest Solo -- Watchlist API Router (M10)
Add, remove, and view watchlist items with three-horizon scoring enrichment.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.dependencies import get_watchlist_service
from backend.app.models.watchlist import AddWatchlistRequest, WatchlistResponse
from backend.app.services.market_data.types import SOURCES
from backend.app.services.watchlist_service import WatchlistService

router = APIRouter(tags=["watchlist"])


def _validate_source(source: str) -> None:
    if source not in SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{source}'. Must be one of: {list(SOURCES)}",
        )


@router.get("/", response_model=WatchlistResponse)
async def get_watchlist(
    source: str = Query("hybrid"),
    svc: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, Any]:
    """Cache-only watchlist read with three-horizon scoring."""
    _validate_source(source)
    return svc.get_watchlist(source=source)


@router.post("/")
async def add_to_watchlist(
    req: AddWatchlistRequest,
    source: str = Query("hybrid"),
    svc: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, Any]:
    """Add a ticker; triggers a live fetch via ``source``."""
    _validate_source(source)
    item = svc.add_item(req, source=source)
    return {"success": True, "item": item}


@router.delete("/{item_id}")
async def remove_from_watchlist(
    item_id: str,
    svc: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, Any]:
    """Remove an item from the watchlist."""
    removed = svc.remove_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Watchlist item {item_id} not found")
    return {"success": True, "message": f"Item {item_id} removed"}


@router.post("/refresh", response_model=WatchlistResponse)
async def refresh_watchlist(
    source: str = Query("hybrid"),
    svc: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, Any]:
    """Force-refresh all live data for watchlist items via ``source``."""
    _validate_source(source)
    return svc.refresh(source=source)
