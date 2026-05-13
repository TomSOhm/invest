"""Tests that NaN gate columns are skipped, not blocking, in horizon presets."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.strategy.horizon_presets import screen_horizon_preset


def _minimal_universe_with_partial_gates() -> pd.DataFrame:
    """5 rows. 3 have passes_gates_lt=True, 1 has False, 1 has NaN.

    With the relaxed gate logic, NaN should be treated as "not blocking"
    so the row passes through the gate filter (subject to other preset
    filters).
    """
    return pd.DataFrame(
        {
            "Ticker": ["A", "B", "C", "D", "E"],
            "Name": ["A Corp", "B Corp", "C Corp", "D Corp", "E Corp"],
            "Sector": ["Tech"] * 5,
            "Country": ["FR"] * 5,
            "PEA": [True] * 5,
            # Bare-bones financial fields the preset's apply_filters won't kill on
            "MarketCap": [5e9] * 5,
            "PE": [15.0] * 5,
            "ROE": [0.15] * 5,
            "ROIC": [0.15] * 5,
            "Altman_Z": [3.0] * 5,
            "Piotroski_F": [7] * 5,
            "DebtEquity": [0.5] * 5,
            "InterestCoverage": [10.0] * 5,
            "CurrentRatio": [1.5] * 5,
            "OperatingMargin": [0.15] * 5,
            "FCFMargin": [0.10] * 5,
            "data_completeness": [0.85] * 5,
            # Required scoring outputs
            "Composite_Score": [75.0] * 5,
            "Signal": ["Buy"] * 5,
            "score_lt": [75.0, 80.0, 70.0, 65.0, 78.0],
            "signal_lt": ["Buy"] * 5,
            "passes_gates_lt": [True, True, True, False, np.nan],
        }
    ).set_index("Ticker")


def test_nan_gate_does_not_block() -> None:
    df = _minimal_universe_with_partial_gates()

    # LT_DEEP_VALUE has the loosest filter set; using it minimises non-gate
    # filter rejections so the test isolates the gate behaviour.
    out = screen_horizon_preset(df, "LT_DEEP_VALUE")

    survivors = list(out.index)
    # B, C, A all have passes_gates_lt=True. E has NaN. D has False.
    # NaN must pass; D must be filtered out.
    assert "E" in survivors, "Row with NaN gate should NOT be blocked"
    assert "D" not in survivors, "Row with explicit False gate must be blocked"
