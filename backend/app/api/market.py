"""
Invest Solo -- Market & Configuration API Router
Provides health check, universe listings, and scoring config.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_scoring_service
from backend.app.services.scoring_service import ScoringService

router = APIRouter(tags=["market"])


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.3.0"}


@router.get("/universe/pea")
async def get_pea_universe() -> List[Dict[str, Any]]:
    """Return PEA-eligible tickers from the sample universe."""
    from src.data.sample_universe import SAMPLE_UNIVERSE

    pea_stocks = [
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
    return pea_stocks


@router.get("/universe/global")
async def get_global_universe() -> List[Dict[str, Any]]:
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
) -> Dict[str, Any]:
    """Return scoring weights and signal thresholds."""
    return {
        "scoring_weights": scorer.get_weights(),
        "signal_thresholds": scorer.get_thresholds(),
    }
