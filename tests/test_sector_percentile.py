"""Unit tests for ``src.analysis.sector_percentile.score_sector_relative``."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.analysis.sector_percentile import score_sector_relative  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Sector group with >= min_n peers
# ──────────────────────────────────────────────────────────────────────────────


def test_within_sector_inverse_pe_six_software_stocks() -> None:
    """Six software stocks at P/E [15, 20, 25, 30, 35, 50] inverse=True.

    pandas.Series.rank(method='average', pct=True) on the sorted values
    [15, 20, 25, 30, 35, 50] gives [1/6, 2/6, 3/6, 4/6, 5/6, 6/6]
    = [16.67, 33.33, 50, 66.67, 83.33, 100]. Inverse=True flips
    around 100 -> [83.33, 66.67, 50, 33.33, 16.67, 0].
    """
    df = pd.DataFrame(
        {
            "PE": [15, 20, 25, 30, 35, 50],
            "Sector": ["Technology"] * 6,
        },
        index=["S1", "S2", "S3", "S4", "S5", "S6"],
    )
    result = score_sector_relative(df, "PE", inverse=True, min_n=5)
    expected = [83.333_333, 66.666_667, 50.0, 33.333_333, 16.666_667, 0.0]
    np.testing.assert_allclose(result.values, expected, atol=1e-4)


def test_within_sector_no_inverse_roe() -> None:
    """ROE: higher-is-better, inverse=False. Six values rank 16.67..100."""
    df = pd.DataFrame(
        {
            "ROE": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
            "Sector": ["Healthcare"] * 6,
        }
    )
    result = score_sector_relative(df, "ROE", inverse=False, min_n=5)
    expected = [16.666_667, 33.333_333, 50.0, 66.666_667, 83.333_333, 100.0]
    np.testing.assert_allclose(result.values, expected, atol=1e-4)


# ──────────────────────────────────────────────────────────────────────────────
# Fallback to global rank when sector below min_n
# ──────────────────────────────────────────────────────────────────────────────


def test_small_sector_falls_back_to_global() -> None:
    """Four utilities (below min_n=5) plus six software peers.

    The four utility rows MUST be ranked against the 10-row global
    universe, not against each other. The six software stocks DO have
    enough peers and rank within sector.
    """
    df = pd.DataFrame(
        {
            "PE": [15, 18, 20, 22, 25, 30, 35, 40, 45, 50],
            # 4 utilities (small) + 6 software (qualifies for sector rank).
            "Sector": (
                ["Utilities"] * 4
                + ["Technology"] * 6
            ),
        },
        index=[f"S{i}" for i in range(10)],
    )
    result = score_sector_relative(df, "PE", inverse=True, min_n=5)

    # Utilities (rows 0..3): rank globally by PE [15, 18, 20, 22, 25, 30,
    # 35, 40, 45, 50] -> percentiles [10, 20, 30, 40, 50, 60, 70, 80,
    # 90, 100]. Inverse: [90, 80, 70, 60, ...]. Utilities are rows 0..3
    # (PE 15, 18, 20, 22) -> inverse global ranks [90, 80, 70, 60].
    np.testing.assert_allclose(
        result.iloc[:4].values, [90.0, 80.0, 70.0, 60.0], atol=1e-4
    )

    # Tech (rows 4..9): rank within sector PE [25, 30, 35, 40, 45, 50]
    # -> [16.67, 33.33, 50, 66.67, 83.33, 100]; inverse -> [83.33,
    # 66.67, 50, 33.33, 16.67, 0].
    np.testing.assert_allclose(
        result.iloc[4:].values,
        [83.333_333, 66.666_667, 50.0, 33.333_333, 16.666_667, 0.0],
        atol=1e-4,
    )


# ──────────────────────────────────────────────────────────────────────────────
# NaN handling
# ──────────────────────────────────────────────────────────────────────────────


def test_all_nan_metric_returns_all_nan() -> None:
    """A metric column of all NaN must produce all-NaN output, not 50.0."""
    df = pd.DataFrame(
        {
            "PE": [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
            "Sector": ["Technology"] * 6,
        }
    )
    result = score_sector_relative(df, "PE", inverse=True)
    assert result.isna().all()


def test_partial_nan_preserved() -> None:
    """NaN inputs in a metric column produce NaN in the output, no imputation."""
    df = pd.DataFrame(
        {
            "PE": [10, 20, np.nan, 30, 40, 50],
            "Sector": ["Technology"] * 6,
        }
    )
    result = score_sector_relative(df, "PE", inverse=True)
    assert math.isnan(result.iloc[2])
    # The other 5 should be ranked against the 5 non-NaN values within sector.
    # Non-NaN PE values [10, 20, 30, 40, 50] -> percentiles [20, 40, 60,
    # 80, 100]; inverse [80, 60, 40, 20, 0].
    non_nan = result.dropna().sort_index()
    expected = [80.0, 60.0, 40.0, 20.0, 0.0]
    np.testing.assert_allclose(non_nan.values, expected, atol=1e-4)


# ──────────────────────────────────────────────────────────────────────────────
# Ties
# ──────────────────────────────────────────────────────────────────────────────


def test_identical_values_get_equal_rank() -> None:
    """Ties under method='average' get the mean of the tied positions."""
    df = pd.DataFrame(
        {
            "PE": [20, 20, 20, 30, 40, 50],
            "Sector": ["Technology"] * 6,
        }
    )
    result = score_sector_relative(df, "PE", inverse=True)
    # The three 20s share positions 1,2,3 -> avg rank 2 -> pct = 2/6
    # = 33.33. Inverse: 100 - 33.33 = 66.67. They must all match.
    assert result.iloc[0] == result.iloc[1] == result.iloc[2]
    assert pytest.approx(result.iloc[0], abs=1e-4) == 100 - (2 / 6) * 100


# ──────────────────────────────────────────────────────────────────────────────
# Index preservation
# ──────────────────────────────────────────────────────────────────────────────


def test_index_preserved_with_ticker_index() -> None:
    """Output index must equal input index (DataFrame indexed by ticker)."""
    df = pd.DataFrame(
        {
            "PE": [15, 25, 35, 45, 55, 65],
            "Sector": ["Technology"] * 6,
        },
        index=["AAPL", "MSFT", "GOOGL", "META", "NVDA", "ASML.AS"],
    )
    result = score_sector_relative(df, "PE", inverse=True)
    assert list(result.index) == ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "ASML.AS"]


# ──────────────────────────────────────────────────────────────────────────────
# Missing column / missing sector column
# ──────────────────────────────────────────────────────────────────────────────


def test_missing_metric_column_returns_nan() -> None:
    df = pd.DataFrame({"Sector": ["Technology"] * 5})
    result = score_sector_relative(df, "PE", inverse=True)
    assert len(result) == 5 and result.isna().all()


def test_missing_sector_column_uses_global_rank() -> None:
    """If `Sector` column is absent, fall through entirely to global rank."""
    df = pd.DataFrame({"PE": [10, 20, 30, 40, 50]})
    result = score_sector_relative(df, "PE", inverse=True, min_n=5)
    # 5 rows globally -> percentiles [20, 40, 60, 80, 100]; inverse
    # [80, 60, 40, 20, 0].
    np.testing.assert_allclose(
        result.values, [80.0, 60.0, 40.0, 20.0, 0.0], atol=1e-4
    )


def test_empty_sector_label_falls_through_to_global() -> None:
    """Rows whose sector is "" or NaN never form a qualifying group."""
    df = pd.DataFrame(
        {
            "PE": [10, 20, 30, 40, 50, 60, 70],
            "Sector": ["", None, "", None, "Technology", "Technology", "Technology"],
        }
    )
    result = score_sector_relative(df, "PE", inverse=True, min_n=5)
    # Tech has only 3 -> falls back to global. 7 rows global ranks
    # = [1..7]/7 * 100 = [14.29, 28.57, ..., 100]; inverse = [85.71,
    # 71.43, 57.14, 42.86, 28.57, 14.29, 0].
    np.testing.assert_allclose(
        result.values,
        [85.714_286, 71.428_571, 57.142_857, 42.857_143, 28.571_429, 14.285_714, 0.0],
        atol=1e-4,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Rejection of unknown fallback_universe
# ──────────────────────────────────────────────────────────────────────────────


def test_unknown_fallback_universe_raises() -> None:
    df = pd.DataFrame({"PE": [10, 20], "Sector": ["X", "X"]})
    with pytest.raises(ValueError, match="fallback_universe"):
        score_sector_relative(df, "PE", fallback_universe="regional")  # type: ignore[arg-type]
