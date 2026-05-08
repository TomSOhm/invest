"""Snapshot regression tests for the scoring engine.

For each ticker that has both a frozen input row and a committed snapshot,
re-run the current scoring engine on the frozen input and assert the output
matches the snapshot exactly.

Snapshots are refreshed via:
    python -m scripts.capture_golden_snapshots --rescore-only

A deliberate methodology change should produce a snapshot diff. Review the
diff in the PR and run the rescore command to commit the new expected output.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "backend", PROJECT_ROOT / "src"):
    sys.path.insert(0, str(p))

from scripts.capture_golden_snapshots import score_row  # noqa: E402

from tests.conftest import (  # noqa: E402
    available_golden_tickers,
    load_input_row,
    load_snapshot,
)


GOLDEN_TICKERS = available_golden_tickers()


def _approx_equal(a, b, rel: float = 1e-6, abs_: float = 1e-6) -> bool:
    """NaN-aware numeric equality with tight tolerance for rounding noise."""
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        if math.isnan(a) or math.isnan(b):
            return False
        return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)
    return a == b


@pytest.mark.skipif(not GOLDEN_TICKERS, reason="no golden snapshots committed yet")
@pytest.mark.parametrize("ticker", GOLDEN_TICKERS)
def test_scoring_snapshot_matches(ticker: str) -> None:
    row = load_input_row(ticker)
    expected = load_snapshot(ticker)
    actual = score_row(row)

    mismatches = []
    for key, exp_val in expected.items():
        act_val = actual.get(key)
        if isinstance(exp_val, str) and exp_val in ("NaN", "Infinity", "-Infinity"):
            exp_val = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}[exp_val]
        if not _approx_equal(act_val, exp_val):
            mismatches.append(f"  {key}: expected={exp_val!r} actual={act_val!r}")
    assert not mismatches, f"{ticker} snapshot drift:\n" + "\n".join(mismatches)


def test_at_least_some_golden_files_exist() -> None:
    """Sanity check: a fresh checkout should have golden fixtures committed."""
    assert GOLDEN_TICKERS, (
        "No golden snapshots found in tests/golden/snapshots/. "
        "Run: python -m scripts.capture_golden_snapshots --all"
    )
