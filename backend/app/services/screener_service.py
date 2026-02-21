"""
Invest Solo -- Screener Service
Thin wrapper around the existing src/strategy/screener.py module.
"""
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from src.strategy.screener import (
    apply_filters,
    get_top_picks,
    generate_screening_summary,
    DEFAULT_FILTERS,
    PEA_STRICT_FILTERS,
    VALUE_FILTERS,
    QUALITY_GROWTH_FILTERS,
    DIVIDEND_INCOME_FILTERS,
)

# Map preset names to their filter dicts
PRESET_MAP: Dict[str, Dict[str, Any]] = {
    "default": DEFAULT_FILTERS,
    "pea_strict": PEA_STRICT_FILTERS,
    "value": VALUE_FILTERS,
    "pea_value": VALUE_FILTERS,
    "quality_growth": QUALITY_GROWTH_FILTERS,
    "pea_quality": QUALITY_GROWTH_FILTERS,
    "dividend_income": DIVIDEND_INCOME_FILTERS,
    "dividend": DIVIDEND_INCOME_FILTERS,
    "global": DEFAULT_FILTERS,
    "global_best": DEFAULT_FILTERS,
}


class ScreenerService:
    """High-level screener operations wrapping the existing module."""

    def run_screen(
        self,
        df: pd.DataFrame,
        filters: Dict[str, Any],
        pea_only: bool = False,
        sort_by: str = "Composite_Score",
        sort_desc: bool = True,
        limit: int = 50,
    ) -> pd.DataFrame:
        """
        Run a custom screening pass.

        Args:
            df: Scored DataFrame (must already contain Composite_Score etc.)
            filters: Dict of filter key-value pairs (as expected by apply_filters)
            pea_only: If True, restrict to PEA-eligible stocks
            sort_by: Column to sort results by
            sort_desc: If True, sort descending
            limit: Max rows to return

        Returns:
            Filtered and sorted DataFrame.
        """
        if df.empty:
            return df
        result = apply_filters(df, filters, pea_only=pea_only)
        if sort_by in result.columns:
            result = result.sort_values(sort_by, ascending=not sort_desc)
        return result.head(limit)

    def run_preset(
        self,
        df: pd.DataFrame,
        preset_name: str,
        pea_only: bool = False,
        limit: int = 50,
    ) -> pd.DataFrame:
        """
        Run a named preset screen.

        Args:
            df: Scored DataFrame
            preset_name: Key into PRESET_MAP
            pea_only: Override PEA-only filter
            limit: Max results
        """
        filters = PRESET_MAP.get(preset_name, DEFAULT_FILTERS)
        # Some presets are inherently pea-only
        force_pea = pea_only
        if preset_name in ("pea_strict",):
            force_pea = True
        return self.run_screen(df, filters, pea_only=force_pea, limit=limit)

    @staticmethod
    def get_presets() -> List[Dict[str, Any]]:
        """Return a list of available preset definitions."""
        result = []
        for name, filters in PRESET_MAP.items():
            result.append({
                "name": name,
                "description": _preset_description(name),
                "filters": filters,
            })
        return result

    @staticmethod
    def get_summary(df: pd.DataFrame) -> Dict[str, Any]:
        """Generate summary statistics for a screened DataFrame."""
        return generate_screening_summary(df)


def _preset_description(name: str) -> str:
    """Human-readable description for a preset name."""
    descriptions = {
        "default": "Balanced default filters with relaxed thresholds",
        "pea_strict": "Strict PEA-eligible quality filters (higher minimums)",
        "value": "Deep value screen: low PE, solid financials",
        "pea_value": "PEA value screen: low PE, solid financials, EU-eligible",
        "quality_growth": "Quality growth: high ROE, expanding margins, revenue growth",
        "pea_quality": "PEA quality growth: high ROE, margins, EU-eligible",
        "dividend_income": "Dividend income: sustainable high-yield payers",
        "dividend": "Dividend income: sustainable high-yield payers",
        "global": "Global best picks across all markets",
        "global_best": "Global best picks across all markets",
    }
    return descriptions.get(name, name)
