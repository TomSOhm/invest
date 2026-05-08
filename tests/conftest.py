"""Pytest fixtures for the Invest Solo test suite.

Layout:
    tests/golden/tickers.txt              — list of ticker symbols
    tests/golden/inputs/{TICKER}.json     — frozen DataFetcher row (one capture)
    tests/golden/snapshots/{TICKER}.json  — frozen scoring output

Frozen inputs decouple regression tests from live-data drift: bug fixes in the
scoring engine produce a diff in the snapshot files, not a noise-laden diff
from yfinance returning slightly different numbers between runs.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd
import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"
INPUTS_DIR = GOLDEN_DIR / "inputs"
SNAPSHOTS_DIR = GOLDEN_DIR / "snapshots"
TICKERS_FILE = GOLDEN_DIR / "tickers.txt"


def load_tickers() -> List[str]:
    """Read non-empty, non-comment lines from tickers.txt."""
    if not TICKERS_FILE.exists():
        return []
    return [
        line.strip()
        for line in TICKERS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _safe_filename(ticker: str) -> str:
    """Map ticker to filesystem-safe stem (BRK-B -> BRK-B, MC.PA -> MC.PA).

    Windows DOS reserved names (CON, PRN, ...) get an underscore prefix so
    e.g. `CON.DE` -> `_CON.DE`. Git on Windows refuses to index files whose
    base name matches a reserved device name.
    """
    cleaned = ticker.replace("/", "_").replace("\\", "_").replace(":", "_")
    head = cleaned.split(".", 1)[0].upper()
    if head in _WINDOWS_RESERVED:
        return "_" + cleaned
    return cleaned


def input_path(ticker: str) -> Path:
    return INPUTS_DIR / f"{_safe_filename(ticker)}.json"


def snapshot_path(ticker: str) -> Path:
    return SNAPSHOTS_DIR / f"{_safe_filename(ticker)}.json"


def load_input_row(ticker: str) -> Dict[str, Any]:
    """Load a frozen input row, replacing JSON-NaN sentinels with float NaN."""
    return _decode_floats(json.loads(input_path(ticker).read_text(encoding="utf-8")))


def load_snapshot(ticker: str) -> Dict[str, Any]:
    return json.loads(snapshot_path(ticker).read_text(encoding="utf-8"))


def _decode_floats(obj: Any) -> Any:
    """Decode JSON-NaN/Inf sentinels (strings) back into float NaN/Inf."""
    if isinstance(obj, dict):
        return {k: _decode_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_floats(v) for v in obj]
    if isinstance(obj, str) and obj in ("NaN", "Infinity", "-Infinity"):
        return {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}[obj]
    return obj


def row_dict_to_series(row: Dict[str, Any]) -> pd.Series:
    """Convert a frozen JSON row back into a pandas Series for scoring functions."""
    return pd.Series(row)


def available_golden_tickers() -> List[str]:
    """Tickers that have BOTH a frozen input and a snapshot on disk."""
    if not INPUTS_DIR.exists() or not SNAPSHOTS_DIR.exists():
        return []
    declared = set(load_tickers())
    return sorted(
        t for t in declared
        if input_path(t).exists() and snapshot_path(t).exists()
    )


@pytest.fixture(scope="session")
def golden_tickers() -> List[str]:
    return available_golden_tickers()
