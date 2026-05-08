"""
Invest Solo -- Screener API Router (M10)
Horizon-aware screening with M8 preset support.

Endpoint list
-------------
POST /api/screener/run            — custom horizon-aware screen
GET  /api/screener/presets        — list all 9 M8 preset metadata dicts
POST /api/screener/preset/{name}  — run a named M8 preset
POST /api/screener/tickers        — score a custom ad-hoc ticker list
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# Dependency aliases
# ---------------------------------------------------------------------------

def _get_fetcher() -> DataFetcher:
    return get_data_fetcher()


def _get_scorer() -> ScoringService:
    return get_scoring_service()


def _get_screener() -> ScreenerService:
    return get_screener_service()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TickerListRequest(BaseModel):
    """Request body for scoring a custom list of tickers."""
    tickers: List[str] = Field(..., min_length=1, max_length=100)
    horizon: str = Field("long_term", description="Horizon for sort order")


class PresetRunRequest(BaseModel):
    """Request body for running a preset screen."""
    pea_only: bool = Field(False, description="Restrict to PEA-eligible stocks only")
    top_n: int = Field(50, ge=1, le=500, description="Max results to return")


# ---------------------------------------------------------------------------
# Helper: build the scored universe DataFrame
# ---------------------------------------------------------------------------

def _build_scored_universe() -> pd.DataFrame:
    """Load sample universe and score it."""
    from src.data.sample_universe import get_universe_dataframe
    df = get_universe_dataframe()
    scorer = get_scoring_service()
    return scorer.score_dataframe(df)


# ---------------------------------------------------------------------------
# Helper: map a scored DataFrame row to ScreenerResultItem-compatible dict
# ---------------------------------------------------------------------------

def _val(row: pd.Series, key: str) -> Any:
    v = row.get(key)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return v


def _num(row: pd.Series, key: str) -> Optional[float]:
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


def _int(row: pd.Series, key: str) -> Optional[int]:
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


def _blockers_for_horizon(row: pd.Series, horizon: str) -> List[str]:
    """Extract blockers list for the given horizon column."""
    col_map = {
        "long_term": "blockers_lt",
        "medium_term": "blockers_mt",
        "short_term": "blockers_st",
    }
    raw = row.get(col_map.get(horizon, "blockers_lt"))
    if isinstance(raw, list):
        return raw
    return []


def _df_to_results(df: pd.DataFrame, horizon: str = "long_term") -> List[Dict[str, Any]]:
    """Convert a scored DataFrame to a list of ScreenerResultItem-compatible dicts."""
    results: List[Dict[str, Any]] = []
    for ticker, row in df.iterrows():
        # Horizon score columns — fall back to Composite_Score for legacy DFs
        composite_fb = _num(row, "Composite_Score") or 0.0
        signal_fb = _val(row, "Signal") or "Hold"

        score_lt = _num(row, "score_lt") or composite_fb
        score_mt = _num(row, "score_mt") or composite_fb
        score_st = _num(row, "score_st") or composite_fb
        signal_lt = _val(row, "signal_lt") or signal_fb
        signal_mt = _val(row, "signal_mt") or signal_fb
        signal_st = _val(row, "signal_st") or signal_fb
        passes_lt = bool(row.get("passes_gates_lt", True))
        passes_mt = bool(row.get("passes_gates_mt", True))
        passes_st = bool(row.get("passes_gates_st", True))

        results.append({
            "ticker": str(ticker),
            "name": _val(row, "Name"),
            "sector": _val(row, "Sector"),
            "pea_eligible": bool(row.get("PEA", False)),
            "score_lt": score_lt,
            "score_mt": score_mt,
            "score_st": score_st,
            "signal_lt": signal_lt,
            "signal_mt": signal_mt,
            "signal_st": signal_st,
            "passes_gates_lt": passes_lt,
            "passes_gates_mt": passes_mt,
            "passes_gates_st": passes_st,
            "pe": _num(row, "PE"),
            "pb": _num(row, "PB"),
            "roe": _num(row, "ROE"),
            "div_yield": _num(row, "DivYield"),
            "revenue_growth": _num(row, "RevenueGrowth"),
            "market_cap": _num(row, "MarketCap"),
            "altman_z": _num(row, "Altman_Z"),
            "piotroski_f": _int(row, "Piotroski_F"),
            "dcf_mos_mid": _num(row, "DCF_MoS_Mid"),
            "recommended_account": _val(row, "recommended_account"),
            "blockers": _blockers_for_horizon(row, horizon),
        })
    return results


def _build_summary(
    total_universe: int,
    df: pd.DataFrame,
    horizon: str = "long_term",
) -> Dict[str, Any]:
    """Build ScreenerSummary from a result DataFrame."""
    if df.empty:
        return {
            "total_passed": 0,
            "total_universe": total_universe,
            "avg_score": None,
            "signal_distribution": {},
            "horizon": horizon,
        }

    score_col_map = {
        "long_term": "score_lt",
        "medium_term": "score_mt",
        "short_term": "score_st",
    }
    signal_col_map = {
        "long_term": "signal_lt",
        "medium_term": "signal_mt",
        "short_term": "signal_st",
    }
    score_col = score_col_map.get(horizon, "score_lt")
    signal_col = signal_col_map.get(horizon, "signal_lt")

    # Fall back to legacy columns when M7 columns are absent
    if score_col not in df.columns:
        score_col = "Composite_Score"
    if signal_col not in df.columns:
        signal_col = "Signal"

    avg_score: Optional[float] = None
    if score_col in df.columns:
        vals = pd.to_numeric(df[score_col], errors="coerce").dropna()
        if not vals.empty:
            avg_score = round(float(vals.mean()), 1)

    signal_dist: Dict[str, int] = {}
    if signal_col in df.columns:
        signal_dist = df[signal_col].value_counts().to_dict()

    return {
        "total_passed": len(df),
        "total_universe": total_universe,
        "avg_score": avg_score,
        "signal_distribution": signal_dist,
        "horizon": horizon,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=ScreenerResponse)
async def run_screen(
    req: ScreenerRequest,
    screener: ScreenerService = Depends(_get_screener),
) -> Dict[str, Any]:
    """Run a horizon-aware custom screen.

    When ``preset`` is set in the request body, it takes precedence over
    ``custom_filters``. Otherwise ``custom_filters`` (if provided) are
    passed directly to ``apply_filters``.
    """
    scored_df = _build_scored_universe()
    total_universe = len(scored_df)

    if req.preset:
        from src.strategy.horizon_presets import PRESET_REGISTRY
        if req.preset not in PRESET_REGISTRY:
            raise HTTPException(
                status_code=404,
                detail=f"Preset '{req.preset}' not found. "
                       f"Available: {sorted(PRESET_REGISTRY.keys())}",
            )
        result_df = screener.run_preset(
            scored_df, req.preset, pea_only=req.pea_only, limit=req.limit
        )
    else:
        filters: Dict[str, Any] = req.custom_filters or {}
        result_df = screener.run_screen(
            df=scored_df,
            filters=filters,
            horizon=req.horizon,
            pea_only=req.pea_only,
            sort_by=req.sort_by,
            sort_desc=req.sort_desc,
            limit=req.limit,
        )

    results = _df_to_results(result_df, horizon=req.horizon)
    summary = _build_summary(total_universe, result_df, horizon=req.horizon)

    return {"results": results, "summary": summary}


@router.get("/presets")
async def list_presets(
    screener: ScreenerService = Depends(_get_screener),
) -> List[Dict[str, Any]]:
    """List all 9 M8 preset metadata dicts (name, horizon, description, recommended_account, pea_warning)."""
    return screener.get_presets()


@router.post("/preset/{preset_name}", response_model=ScreenerResponse)
async def run_preset(
    preset_name: str,
    req: PresetRunRequest,
    screener: ScreenerService = Depends(_get_screener),
) -> Dict[str, Any]:
    """Run a named M8 preset screen.

    ``preset_name`` must be one of the 9 keys in PRESET_REGISTRY
    (e.g. ``LT_QUALITY_COMPOUNDER``, ``ST_MOMENTUM_QUALITY``).
    """
    from src.strategy.horizon_presets import PRESET_REGISTRY, get_preset

    if preset_name not in PRESET_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{preset_name}' not found. "
                   f"Available: {sorted(PRESET_REGISTRY.keys())}",
        )

    preset_meta = get_preset(preset_name)
    horizon: str = preset_meta.get("horizon", "long_term")

    scored_df = _build_scored_universe()
    total_universe = len(scored_df)

    result_df = screener.run_preset(scored_df, preset_name, pea_only=req.pea_only, limit=req.top_n)
    results = _df_to_results(result_df, horizon=horizon)
    summary = _build_summary(total_universe, result_df, horizon=horizon)

    return {"results": results, "summary": summary}


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
            "summary": _build_summary(0, df, horizon=req.horizon),
        }

    scored_df = scorer.score_dataframe(df)
    results = _df_to_results(scored_df, horizon=req.horizon)
    summary = _build_summary(len(req.tickers), scored_df, horizon=req.horizon)

    return {"results": results, "summary": summary}
