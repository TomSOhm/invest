"""
Invest Solo -- Screener Service (M10)
Wraps the M8 horizon_presets and the existing screener.apply_filters.

Key changes vs M9:
- PRESET_REGISTRY is now sourced from src.strategy.horizon_presets (9 presets)
- run_preset delegates to screen_horizon_preset which gates on passes_gates_<h>
- run_screen accepts horizon to determine the sort column
- get_presets returns the 9 M8 preset metadata dicts
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.strategy.horizon_presets import (
    PRESET_REGISTRY,
    list_presets,
    screen_horizon_preset,
)
from src.strategy.screener import apply_filters

# Horizon -> score column mapping (these columns are emitted by score_dataframe
# when M7 is active; fall back to Composite_Score for legacy DataFrames).
_HORIZON_SCORE_COL: dict[str, str] = {
    "long_term": "score_lt",
    "medium_term": "score_mt",
    "short_term": "score_st",
}


class ScreenerService:
    """High-level screener operations wrapping the existing module."""

    def run_screen(
        self,
        df: pd.DataFrame,
        filters: dict[str, Any],
        horizon: str = "long_term",
        pea_only: bool = False,
        sort_by: str = "score",
        sort_desc: bool = True,
        limit: int = 50,
    ) -> pd.DataFrame:
        """
        Run a custom screening pass.

        Parameters
        ----------
        df : pd.DataFrame
            Scored DataFrame (must already contain score_lt/mt/st etc.)
        filters : dict
            Filter key-value pairs (as expected by apply_filters)
        horizon : str
            "long_term" | "medium_term" | "short_term". Determines gate column
            and default sort column when sort_by == "score".
        pea_only : bool
            If True, restrict to PEA-eligible stocks
        sort_by : str
            "score" maps to score_<horizon>. Also accepts: pe, roe,
            market_cap, div_yield, revenue_growth, altman_z, piotroski_f.
        sort_desc : bool
        limit : int

        Returns
        -------
        pd.DataFrame
            Filtered and sorted DataFrame.
        """
        if df.empty:
            return df

        result = apply_filters(df, filters, pea_only=pea_only)

        # Map sort key to DataFrame column
        sort_map: dict[str, str] = {
            "score": _HORIZON_SCORE_COL.get(horizon, "score_lt"),
            "pe": "PE",
            "roe": "ROE",
            "market_cap": "MarketCap",
            "div_yield": "DivYield",
            "revenue_growth": "RevenueGrowth",
            "altman_z": "Altman_Z",
            "piotroski_f": "Piotroski_F",
        }
        score_col = sort_map.get(sort_by, _HORIZON_SCORE_COL.get(horizon, "Composite_Score"))

        # Fall back to Composite_Score if the horizon column doesn't exist yet
        if score_col not in result.columns:
            score_col = "Composite_Score"

        if score_col in result.columns:
            result = result.sort_values(score_col, ascending=not sort_desc)

        return result.head(limit)

    def run_preset(
        self,
        df: pd.DataFrame,
        preset_name: str,
        pea_only: bool = False,
        limit: int = 50,
    ) -> pd.DataFrame:
        """
        Run a named M8 horizon preset screen.

        Parameters
        ----------
        df : pd.DataFrame
            Scored DataFrame with M7 horizon columns present.
        preset_name : str
            Key into PRESET_REGISTRY (case-sensitive, upper-snake: LT_QUALITY_COMPOUNDER, ...)
        pea_only : bool
            Override PEA-only filter (preset may already embed pea_only: True)
        limit : int
            Max results
        """
        if preset_name not in PRESET_REGISTRY:
            raise KeyError(f"Unknown preset '{preset_name}'. Valid names: {sorted(PRESET_REGISTRY.keys())}")

        result = screen_horizon_preset(df, preset_name)

        # Apply override pea_only after preset filtering
        if pea_only and "PEA" in result.columns:
            result = result[result["PEA"].fillna(False).astype(bool)]

        return result.head(limit)

    @staticmethod
    def get_presets() -> list[dict[str, Any]]:
        """Return the 9 M8 preset metadata dicts (name, horizon, description, ...)."""
        return list_presets()

    @staticmethod
    def get_summary(df: pd.DataFrame) -> dict[str, Any]:
        """Generate summary statistics for a screened DataFrame."""
        from src.strategy.screener import generate_screening_summary

        return generate_screening_summary(df)
