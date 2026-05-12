"""Regression tests for screener API string-field NaN handling.

Companion to f838f4e (which fixed watchlist/portfolio/company services). The
screener path went through ``backend.app.api.screener._val`` which only
handled ``float`` NaN. With pandas StringDtype variants whose ``na_value`` is
``pd.NA`` (or NaT for datetime nullable types), the old helper let the
missing sentinel through and Pydantic rejected the response::

    {'type': 'string_type',
     'loc': ('response', 'results', N, 'name'),
     'msg': 'Input should be a valid string',
     'input': nan}
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.app.api.screener import _df_to_results, _str_val, _val
from backend.app.models.screener import ScreenerResponse


def _row(ticker: str, **overrides) -> dict:
    base = {
        "Name": "Foo Inc.",
        "Sector": "Industrials",
        "PEA": True,
        "Composite_Score": 60.0,
        "Signal": "Hold",
        "score_lt": 60.0, "score_mt": 60.0, "score_st": 60.0,
        "signal_lt": "Hold", "signal_mt": "Hold", "signal_st": "Hold",
        "passes_gates_lt": True, "passes_gates_mt": True, "passes_gates_st": True,
        "PE": 12.0, "PB": 1.5, "ROE": 0.15,
        "DivYield": 2.0, "RevenueGrowth": 0.05, "MarketCap": 1e10,
        "Altman_Z": 3.0, "Piotroski_F": 6, "DCF_MoS_Mid": 0.1,
        "recommended_account": "",
        "blockers_lt": [], "blockers_mt": [], "blockers_st": [],
    }
    base.update(overrides)
    return base


def test_val_handles_float_nan() -> None:
    s = pd.Series({"x": np.nan})
    assert _val(s, "x") is None


def test_val_handles_pd_na() -> None:
    s = pd.Series({"x": pd.NA})
    assert _val(s, "x") is None


def test_val_handles_none() -> None:
    s = pd.Series({"x": None})
    assert _val(s, "x") is None


def test_val_passes_real_string() -> None:
    s = pd.Series({"x": "hello"})
    assert _val(s, "x") == "hello"


def test_str_val_strips_and_nones_empty() -> None:
    s = pd.Series({"x": "  ", "y": "Foo "})
    assert _str_val(s, "x") is None
    assert _str_val(s, "y") == "Foo"


def test_df_to_results_with_pd_na_name_validates() -> None:
    """A row where Name/Sector are pd.NA (the pandas-3 StringDtype miss) must
    produce ``name=None`` and validate against the response schema."""
    rows = [
        _row("AAA"),
        _row("BBB", Name=pd.NA, Sector=pd.NA),
        _row("CCC", Name=np.nan, Sector=np.nan),
    ]
    df = pd.DataFrame(rows, index=["AAA", "BBB", "CCC"])

    results = _df_to_results(df, horizon="long_term")

    # No string field carries a NaN sentinel of any kind
    for r in results:
        for fld in ("name", "sector", "signal_lt", "signal_mt", "signal_st"):
            v = r[fld]
            assert v is None or isinstance(v, str), f"{fld}={v!r}"
            if isinstance(v, float):
                assert not np.isnan(v)

    payload = {"results": results, "summary": {
        "total_passed": len(results), "total_universe": len(results),
        "avg_score": 60.0, "signal_distribution": {"Hold": 3},
        "horizon": "long_term",
    }, "last_refreshed": None}

    ScreenerResponse.model_validate(payload)


def test_df_to_results_string_dtype_nan() -> None:
    """Reproduce the on-disk parquet shape: StringDtype with float NaN sentinel."""
    df = pd.DataFrame(
        [_row("AAA"), _row("BBB", Name=None, Sector=None)],
        index=["AAA", "BBB"],
    )
    df["Name"] = df["Name"].astype("string")
    df["Sector"] = df["Sector"].astype("string")

    results = _df_to_results(df, horizon="long_term")
    assert results[1]["name"] is None
    assert results[1]["sector"] is None
    ScreenerResponse.model_validate({
        "results": results,
        "summary": {"total_passed": 2, "total_universe": 2, "avg_score": 60.0,
                    "signal_distribution": {"Hold": 2}, "horizon": "long_term"},
        "last_refreshed": None,
    })
