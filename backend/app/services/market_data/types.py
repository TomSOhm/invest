"""Shared types for the market_data package."""
from __future__ import annotations

from typing import Literal

DataSource = Literal["hybrid", "yfinance", "fmp"]

SOURCES: tuple[DataSource, ...] = ("hybrid", "yfinance", "fmp")

DEFAULT_SOURCE: DataSource = "hybrid"


def is_valid_source(value: object) -> bool:
    """Return True iff ``value`` is one of the supported data sources."""
    return isinstance(value, str) and value in SOURCES
