"""
Invest Solo -- Market & Configuration API Router (M10)
Provides health check, universe listings, scoring config, and preset metadata.

Endpoint list
-------------
GET /api/market/health           — health check
GET /api/market/universe/pea     — PEA-eligible tickers
GET /api/market/universe/global  — all tickers
GET /api/market/config           — scoring weights, signal thresholds, horizons block, presets
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_scoring_service
from backend.app.services.scoring_service import ScoringService

router = APIRouter(tags=["market"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.4.0"}


@router.get("/universe/pea")
async def get_pea_universe() -> list[dict[str, Any]]:
    """Return PEA-eligible tickers from the sample universe."""
    from src.data.sample_universe import SAMPLE_UNIVERSE

    return [
        {
            "ticker": s["Ticker"],
            "name": s["Name"],
            "sector": s["Sector"],
            "country": s["Country"],
            "exchange": s["Exchange"],
            "pea_pme": s.get("PEA_PME", False),
        }
        for s in SAMPLE_UNIVERSE
        if s.get("PEA", False)
    ]


@router.get("/universe/global")
async def get_global_universe() -> list[dict[str, Any]]:
    """Return all tickers from the sample universe."""
    from src.data.sample_universe import SAMPLE_UNIVERSE

    return [
        {
            "ticker": s["Ticker"],
            "name": s["Name"],
            "sector": s["Sector"],
            "country": s["Country"],
            "exchange": s["Exchange"],
            "pea": s.get("PEA", False),
            "pea_pme": s.get("PEA_PME", False),
        }
        for s in SAMPLE_UNIVERSE
    ]


@router.get("/config")
async def get_config(
    scorer: ScoringService = Depends(get_scoring_service),
) -> dict[str, Any]:
    """Return scoring configuration: weights, signal thresholds, horizon
    definitions from settings.yaml, and the 9 M8 preset metadata dicts."""
    from src.strategy.horizon_presets import list_presets

    # Load the horizons block from settings.yaml if available
    try:
        from backend.app.config import settings as _settings

        horizons_block = getattr(_settings, "horizons", None)
    except Exception:
        horizons_block = None

    return {
        "scoring_weights": scorer.get_weights(),
        "signal_thresholds": scorer.get_thresholds(),
        "horizons": horizons_block,
        "presets": list_presets(),
    }
