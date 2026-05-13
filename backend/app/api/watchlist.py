"""
Invest Solo -- Watchlist API Router (M10)
Add, remove, and view watchlist items with three-horizon scoring enrichment.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_watchlist_service
from backend.app.models.watchlist import AddWatchlistRequest, WatchlistResponse
from backend.app.services.watchlist_service import WatchlistService

router = APIRouter(tags=["watchlist"])


@router.get("/", response_model=WatchlistResponse)
async def get_watchlist(
    svc: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, Any]:
    """Return the full watchlist with cached data and three-horizon scoring.

    This endpoint is cache-only: no live FMP/yfinance calls are made.
    Tickers without a cache entry return degraded rows (NaN scoring fields).
    Use POST /refresh to trigger a live re-fetch.

    All three horizon scores (score_lt, score_mt, score_st) are present on
    every item. Use signal_lt / signal_mt / signal_st as appropriate for the
    investment timeframe.
    """
    return svc.get_watchlist()


@router.post("/")
async def add_to_watchlist(
    req: AddWatchlistRequest,
    svc: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, Any]:
    """Add a ticker to the watchlist.

    Triggers a live fetch for the new ticker only so scoring fields populate
    immediately. Returns 200 even if both FMP and yfinance fail (degraded row).
    """
    item = svc.add_item(req)
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
    svc: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, Any]:
    """Force-refresh all live data for watchlist items.

    Invalidates the cache for every stored ticker and re-fetches live data
    from FMP (with yfinance fallback). Analyst ratings are included.
    """
    return svc.refresh()
