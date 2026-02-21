"""
Invest Solo -- Watchlist API Router
Add, remove, and view watchlist items with live enrichment.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_watchlist_service
from backend.app.models.watchlist import AddWatchlistRequest, WatchlistResponse
from backend.app.services.watchlist_service import WatchlistService

router = APIRouter(tags=["watchlist"])


@router.get("/", response_model=WatchlistResponse)
async def get_watchlist(
    svc: WatchlistService = Depends(get_watchlist_service),
) -> Dict[str, Any]:
    """Return the full watchlist with live data and scoring."""
    return svc.get_watchlist()


@router.post("/")
async def add_to_watchlist(
    req: AddWatchlistRequest,
    svc: WatchlistService = Depends(get_watchlist_service),
) -> Dict[str, Any]:
    """Add a ticker to the watchlist."""
    item = svc.add_item(req)
    return {"success": True, "item": item}


@router.delete("/{item_id}")
async def remove_from_watchlist(
    item_id: str,
    svc: WatchlistService = Depends(get_watchlist_service),
) -> Dict[str, Any]:
    """Remove an item from the watchlist."""
    removed = svc.remove_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Watchlist item {item_id} not found")
    return {"success": True, "message": f"Item {item_id} removed"}


@router.post("/refresh", response_model=WatchlistResponse)
async def refresh_watchlist(
    svc: WatchlistService = Depends(get_watchlist_service),
) -> Dict[str, Any]:
    """Force-refresh all live data for watchlist items."""
    # Invalidate caches for all watchlist tickers
    items = svc._store.get_items()
    for item in items:
        svc._fetcher._cache.invalidate(f"ticker_{item['ticker']}")
    return svc.get_watchlist()
