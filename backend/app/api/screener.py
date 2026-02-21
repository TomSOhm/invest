"""
Invest Solo -- Screener API Router
Run custom filter screens, presets, and score custom ticker lists.
"""
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.dependencies import (
    get_data_fetcher,
    get_scoring_service,
    get_screener_service,
)
from backend.app.models.screener import (
    ScreenerRequest,
    ScreenerResponse,
    ScreenerResultItem,
    ScreenerSummary,
)
from backend.app.services.data_fetcher import DataFetcher
from backend.app.services.scoring_service import ScoringService
from backend.app.services.screener_service import ScreenerService

router = APIRouter(tags=["screener"])


# Dependency aliases (simple callables)
def _get_fetcher() -> DataFetcher:
    from backend.app.dependencies import get_data_fetcher
    return get_data_fetcher()


def _get_scorer() -> ScoringService:
    from backend.app.dependencies import get_scoring_service
    return get_scoring_service()


def _get_screener() -> ScreenerService:
    from backend.app.dependencies import get_screener_service
    return get_screener_service()


class TickerListRequest(BaseModel):
    """Request body for scoring a custom list of tickers."""
    tickers: List[str] = Field(..., min_length=1, max_length=100)


class PresetRequest(BaseModel):
    """Request body for running a preset screen."""
    pea_only: bool = Field(False, description="Restrict to PEA-eligible stocks only")
    top_n: int = Field(50, ge=1, le=500, description="Max results to return")


def _build_scored_universe(pea_only: bool = False) -> pd.DataFrame:
    """Build and score the sample universe DataFrame."""
    from src.data.sample_universe import get_universe_dataframe
    from backend.app.dependencies import get_scoring_service

    df = get_universe_dataframe()
    scorer = get_scoring_service()
    scored = scorer.score_dataframe(df)
    return scored


def _df_to_results(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert a scored DataFrame to a list of ScreenerResultItem-compatible dicts."""
    results = []
    for ticker, row in df.iterrows():
        results.append({
            "ticker": ticker,
            "name": _val(row, "Name"),
            "sector": _val(row, "Sector"),
            "country": _val(row, "Country"),
            "price": _num(row, "Price"),
            "market_cap": _num(row, "MarketCap"),
            "composite_score": _num(row, "Composite_Score"),
            "signal": _val(row, "Signal"),
            "pe": _num(row, "PE"),
            "pb": _num(row, "PB"),
            "roe": _num(row, "ROE"),
            "div_yield": _num(row, "DivYield"),
            "revenue_growth": _num(row, "RevenueGrowth"),
            "piotroski_f": _int(row, "Piotroski_F"),
            "altman_z": _num(row, "Altman_Z"),
            "graham_mos": _num(row, "Graham_MoS"),
            "pea_eligible": bool(row.get("PEA", False)),
            "valuation_score": _num(row, "Valuation_Score"),
            "health_score": _num(row, "Health_Score"),
            "profitability_score": _num(row, "Profitability_Score"),
            "growth_score": _num(row, "Growth_Score"),
        })
    return results


def _build_summary(
    total_screened: int, df: pd.DataFrame
) -> Dict[str, Any]:
    """Build screener summary from a result DataFrame."""
    if df.empty:
        return {
            "total_screened": total_screened,
            "total_passed": 0,
            "avg_score": None,
            "signal_distribution": {},
            "sector_distribution": {},
        }
    signal_dist = {}
    sector_dist = {}
    if "Signal" in df.columns:
        signal_dist = df["Signal"].value_counts().to_dict()
    if "Sector" in df.columns:
        sector_dist = df["Sector"].value_counts().to_dict()

    avg_score = None
    if "Composite_Score" in df.columns:
        avg_score = round(float(df["Composite_Score"].mean()), 1)

    return {
        "total_screened": total_screened,
        "total_passed": len(df),
        "avg_score": avg_score,
        "signal_distribution": signal_dist,
        "sector_distribution": sector_dist,
    }


# -- Helper extractors --

def _val(row: pd.Series, key: str) -> Any:
    v = row.get(key)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return v


def _num(row: pd.Series, key: str) -> Any:
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _int(row: pd.Series, key: str) -> Any:
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", response_model=ScreenerResponse)
async def run_screen(
    req: ScreenerRequest,
    screener: ScreenerService = Depends(_get_screener),
) -> Dict[str, Any]:
    """Run a custom screening with user-defined filters."""
    scored_df = _build_scored_universe()
    total_screened = len(scored_df)

    # Convert ScreenerFilters to the dict format expected by screener module
    filters = {k: v for k, v in req.filters.model_dump().items() if v is not None}

    # Map sort_by from API naming to DataFrame column naming
    sort_map = {
        "composite_score": "Composite_Score",
        "pe": "PE",
        "roe": "ROE",
        "market_cap": "MarketCap",
        "div_yield": "DivYield",
        "revenue_growth": "RevenueGrowth",
    }
    sort_col = sort_map.get(req.sort_by, "Composite_Score")

    result_df = screener.run_screen(
        df=scored_df,
        filters=filters,
        pea_only=req.pea_only,
        sort_by=sort_col,
        sort_desc=req.sort_desc,
        limit=req.limit,
    )

    results = _df_to_results(result_df)
    summary = _build_summary(total_screened, result_df)

    return {
        "results": results,
        "summary": summary,
        "filters_applied": filters,
    }


@router.get("/presets")
async def list_presets(
    screener: ScreenerService = Depends(_get_screener),
) -> List[Dict[str, Any]]:
    """List all available screening presets."""
    return screener.get_presets()


@router.post("/preset/{preset_name}", response_model=ScreenerResponse)
async def run_preset(
    preset_name: str,
    req: PresetRequest,
    screener: ScreenerService = Depends(_get_screener),
) -> Dict[str, Any]:
    """Run a named preset screening."""
    from backend.app.services.screener_service import PRESET_MAP

    if preset_name not in PRESET_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{preset_name}' not found. Available: {list(PRESET_MAP.keys())}",
        )

    scored_df = _build_scored_universe()
    total_screened = len(scored_df)

    result_df = screener.run_preset(scored_df, preset_name, pea_only=req.pea_only, limit=req.top_n)
    results = _df_to_results(result_df)
    summary = _build_summary(total_screened, result_df)

    return {
        "results": results,
        "summary": summary,
        "filters_applied": {"preset": preset_name},
    }


@router.post("/tickers", response_model=ScreenerResponse)
async def score_ticker_list(
    req: TickerListRequest,
    fetcher: DataFetcher = Depends(_get_fetcher),
    scorer: ScoringService = Depends(_get_scorer),
) -> Dict[str, Any]:
    """Fetch and score a custom list of tickers (live data from yfinance)."""
    df = fetcher.fetch_batch(req.tickers)
    if df.empty:
        return {
            "results": [],
            "summary": _build_summary(0, df),
            "filters_applied": {"tickers": req.tickers},
        }

    scored_df = scorer.score_dataframe(df)
    results = _df_to_results(scored_df)
    summary = _build_summary(len(req.tickers), scored_df)

    return {
        "results": results,
        "summary": summary,
        "filters_applied": {"tickers": req.tickers},
    }
