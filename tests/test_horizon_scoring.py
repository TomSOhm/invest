"""Synthetic-fixture tests for the M7 three-horizon scoring orchestrator.

These tests exercise ``src.analysis.horizon_scoring`` against four
hand-crafted rows that cover the failure / pass quadrants:

    1. "Hermès-like" — high quality compounder; should score top on LT,
       middle on MT, low on ST (the momentum weight on ST sinks it).
    2. "Momentum stock" — F-Score 5, fresh earnings beat, middling moat;
       should top ST and lag LT.
    3. "Distressed" — Altman Z 0.8; fails distress gate on every horizon.
    4. "Sparse-data" — 0.4 data_completeness; fails LT/MT gates, may pass
       ST (its threshold is 0.5 — borderline; in this fixture it fails).

All scores stay deterministic because we feed the sub-score columns
directly rather than running them through ``score_dataframe``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "backend", PROJECT_ROOT / "src"):
    sys.path.insert(0, str(p))

from src.analysis.horizon_scoring import (  # noqa: E402
    DEFAULT_SUB_SCORE_COLUMNS,
    score_long_term,
    score_medium_term,
    score_short_term,
    score_three_horizons,
)


# ---------------------------------------------------------------------------
# Horizon weight / gate fixtures (mirror settings.yaml so tests stay aligned)
# ---------------------------------------------------------------------------

LT_WEIGHTS = {
    "valuation": 0.20,
    "profitability": 0.25,
    "health": 0.15,
    "earnings_quality": 0.10,
    "growth": 0.10,
    "capital_allocation": 0.10,
    "risk": 0.10,
}
LT_GATES = {
    "min_data_completeness": 0.70,
    "max_distress": 1.1,
    "min_market_cap": 100_000_000,
    "min_years_listed": 3,
}

MT_WEIGHTS = {
    "valuation": 0.20,
    "profitability": 0.15,
    "health": 0.15,
    "earnings_quality": 0.10,
    "growth": 0.15,
    "capital_allocation": 0.05,
    "risk": 0.10,
    "momentum": 0.10,
}
MT_GATES = {
    "min_data_completeness": 0.60,
    "max_distress": 1.1,
    "min_market_cap": 100_000_000,
}

ST_WEIGHTS = {
    "valuation": 0.05,
    "profitability": 0.05,
    "health": 0.10,
    "earnings_quality": 0.05,
    "growth": 0.05,
    "capital_allocation": 0.05,
    "risk": 0.10,
    "momentum": 0.55,
}
ST_GATES = {
    "min_data_completeness": 0.50,
    "max_distress": 1.5,
    "min_market_cap": 500_000_000,
    "min_avg_volume": 2_000_000,
    "max_realized_vol_1y": 0.5,
    "pea_warning": True,
    "recommended_account": "CTO",
}

ALL_HORIZONS_BLOCK = {
    "long_term": {"weights": LT_WEIGHTS, "gates": LT_GATES},
    "medium_term": {"weights": MT_WEIGHTS, "gates": MT_GATES},
    "short_term": {"weights": ST_WEIGHTS, "gates": ST_GATES},
}


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _row(
    ticker: str,
    *,
    valuation: float = 50.0,
    profitability: float = 50.0,
    health: float = 50.0,
    growth: float = 50.0,
    capital_allocation: float = 50.0,
    risk_v2: float = 50.0,
    earnings_quality: float = 50.0,
    momentum: float = float("nan"),
    data_completeness: float = 0.95,
    altman_z: float = 4.0,
    market_cap: float = 5e9,
    years_listed: float = 10.0,
    avg_volume: float = 5_000_000.0,
    realized_vol_1y: float = 0.25,
    dcf_mos_mid: float = float("nan"),
) -> Dict[str, Any]:
    """Build a synthetic universe row keyed by ticker."""
    return {
        "Ticker": ticker,
        "Valuation_Score": valuation,
        "Profitability_Score": profitability,
        "Health_Score": health,
        "Growth_Score": growth,
        "Shareholder_Score": capital_allocation,
        "Risk_Score_v2": risk_v2,
        "EarningsQuality_Score": earnings_quality,
        "Momentum_Score": momentum,
        "data_completeness": data_completeness,
        "Altman_Z": altman_z,
        "MarketCap": market_cap,
        "YearsListed": years_listed,
        "AvgVolume": avg_volume,
        "Realized_Vol_1y": realized_vol_1y,
        "DCF_MoS_Mid": dcf_mos_mid,
    }


@pytest.fixture()
def universe() -> pd.DataFrame:
    """Four-row synthetic universe covering the LT/MT/ST quadrants."""
    rows = [
        # 1. Hermès-like: high quality, modest momentum
        # Momentum=30 is "below median" — by design, this name doesn't
        # screen well on a momentum-led horizon (ST has 55% momentum).
        _row(
            "HRMS",
            valuation=55.0,
            profitability=85.0,
            health=80.0,
            growth=60.0,
            capital_allocation=70.0,
            risk_v2=70.0,
            earnings_quality=80.0,
            momentum=30.0,
            altman_z=6.5,
            market_cap=200e9,
            years_listed=30.0,
        ),
        # 2. Momentum stock: middling fundamentals, hot price action
        _row(
            "MOMO",
            valuation=45.0,
            profitability=55.0,
            health=55.0,
            growth=70.0,
            capital_allocation=50.0,
            risk_v2=50.0,
            earnings_quality=55.0,
            momentum=90.0,
            altman_z=2.5,
            market_cap=10e9,
            years_listed=8.0,
        ),
        # 3. Distressed: Altman 0.8 — every horizon should fail
        _row(
            "DSTR",
            valuation=35.0,
            profitability=25.0,
            health=20.0,
            growth=30.0,
            capital_allocation=20.0,
            risk_v2=15.0,
            earnings_quality=25.0,
            momentum=35.0,
            altman_z=0.8,
            market_cap=2e9,
            years_listed=15.0,
        ),
        # 4. Sparse data: completeness 0.4 — fails LT/MT and ST
        _row(
            "SPRS",
            valuation=50.0,
            profitability=50.0,
            health=50.0,
            growth=50.0,
            capital_allocation=50.0,
            risk_v2=50.0,
            earnings_quality=50.0,
            momentum=55.0,
            data_completeness=0.40,
            altman_z=2.0,
            market_cap=800e6,
            years_listed=5.0,
        ),
    ]
    return pd.DataFrame(rows).set_index("Ticker")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_long_term_columns_present(universe: pd.DataFrame) -> None:
    out = score_long_term(universe, LT_WEIGHTS, LT_GATES)
    assert set(out.columns) == {"score_lt", "signal_lt", "passes_gates_lt", "blockers_lt"}
    assert list(out.index) == list(universe.index)


def test_hermes_like_long_vs_short(universe: pd.DataFrame) -> None:
    """Quality compounder: LT >= 70, ST <= 50, MT in between."""
    lt = score_long_term(universe, LT_WEIGHTS, LT_GATES)
    mt = score_medium_term(universe, MT_WEIGHTS, MT_GATES)
    st = score_short_term(universe, ST_WEIGHTS, ST_GATES)

    s_lt = lt.loc["HRMS", "score_lt"]
    s_mt = mt.loc["HRMS", "score_mt"]
    s_st = st.loc["HRMS", "score_st"]

    assert s_lt >= 70.0, f"LT score for HRMS-like should be >= 70, got {s_lt}"
    assert s_st <= 50.0, f"ST score for HRMS-like should be <= 50, got {s_st}"
    # MT sits between (momentum 40 drags it below LT).
    assert s_st < s_mt < s_lt
    # All gates pass for HRMS.
    assert lt.loc["HRMS", "passes_gates_lt"] is True or lt.loc["HRMS", "passes_gates_lt"]  # bool/numpy
    assert mt.loc["HRMS", "passes_gates_mt"]
    assert st.loc["HRMS", "passes_gates_st"]


def test_momentum_stock_short_vs_long(universe: pd.DataFrame) -> None:
    """Momentum-led name: ST >= 70, LT <= 60."""
    lt = score_long_term(universe, LT_WEIGHTS, LT_GATES)
    st = score_short_term(universe, ST_WEIGHTS, ST_GATES)

    s_lt = lt.loc["MOMO", "score_lt"]
    s_st = st.loc["MOMO", "score_st"]

    assert s_st >= 70.0, f"ST score for momentum stock should be >= 70, got {s_st}"
    assert s_lt <= 60.0, f"LT score for momentum stock should be <= 60, got {s_lt}"
    # ST must explicitly upgrade beyond LT for momentum names.
    assert s_st > s_lt


def test_distressed_fails_all_gates(universe: pd.DataFrame) -> None:
    """Altman Z < 1.1 trips the distress gate on every horizon.

    The distress threshold is 1.1 for LT/MT and 1.5 for ST; an Altman of
    0.8 is below both, so all three horizons must list ``max_distress``
    among their blockers.
    """
    out = score_three_horizons(universe, ALL_HORIZONS_BLOCK)
    row = out.loc["DSTR"]

    assert row["passes_gates_lt"] is False or not row["passes_gates_lt"]
    assert row["passes_gates_mt"] is False or not row["passes_gates_mt"]
    assert row["passes_gates_st"] is False or not row["passes_gates_st"]

    assert "max_distress" in row["blockers_lt"]
    assert "max_distress" in row["blockers_mt"]
    assert "max_distress" in row["blockers_st"]


def test_sparse_data_blocks_lt_and_mt(universe: pd.DataFrame) -> None:
    """data_completeness 0.4 < LT(0.70) and < MT(0.60); ST threshold 0.5 also fails."""
    out = score_three_horizons(universe, ALL_HORIZONS_BLOCK)
    row = out.loc["SPRS"]

    assert "min_data_completeness" in row["blockers_lt"]
    assert "min_data_completeness" in row["blockers_mt"]
    # ST: 0.4 < 0.5 → also blocks. min_market_cap also fails (800M < 500M? no, 800M > 500M ok).
    # Actually 800e6 > 500e6 = passes market cap; only completeness fails on ST.
    # But LT also fails min_market_cap: 800M ≥ 100M ok. So only completeness blocks LT/MT.
    assert "min_data_completeness" in row["blockers_st"]


def test_short_term_recommended_account_only_when_passing(universe: pd.DataFrame) -> None:
    """``recommended_account`` is "CTO" for ST-passing rows, empty otherwise."""
    out = score_three_horizons(universe, ALL_HORIZONS_BLOCK)
    assert "recommended_account" in out.columns

    # HRMS and MOMO pass ST; DSTR (distressed) and SPRS (sparse) fail.
    assert out.loc["HRMS", "recommended_account"] == "CTO"
    assert out.loc["MOMO", "recommended_account"] == "CTO"
    assert out.loc["DSTR", "recommended_account"] == ""
    assert out.loc["SPRS", "recommended_account"] == ""


def test_missing_momentum_blocks_short_term() -> None:
    """ST is momentum-led; NaN ``Momentum_Score`` adds ``missing_momentum`` to blockers.

    LT and MT shouldn't care — momentum either drops out (LT, no weight)
    or contributes a small slice (MT, 10%).
    """
    row = _row(
        "NOMO",
        valuation=70.0,
        profitability=70.0,
        health=70.0,
        growth=60.0,
        capital_allocation=60.0,
        risk_v2=60.0,
        earnings_quality=70.0,
        momentum=float("nan"),  # explicitly missing
    )
    df = pd.DataFrame([row]).set_index("Ticker")
    out = score_three_horizons(df, ALL_HORIZONS_BLOCK)
    assert "missing_momentum" in out.loc["NOMO", "blockers_st"]
    # LT / MT don't gate on momentum, so they should pass cleanly.
    assert out.loc["NOMO", "passes_gates_lt"]
    assert out.loc["NOMO", "passes_gates_mt"]


def test_renormalisation_when_categories_missing() -> None:
    """When a sub-score column is NaN the weight drops out and the
    composite stays on 0..100. Verify a row with momentum=NaN gets the
    same LT score as one with momentum present (LT has no momentum weight)
    and a slightly different MT score (MT loses its 10% momentum slice).
    """
    base = _row("BASE", profitability=80.0, valuation=60.0, momentum=40.0)
    no_mom = _row("NOMO", profitability=80.0, valuation=60.0, momentum=float("nan"))
    df = pd.DataFrame([base, no_mom]).set_index("Ticker")

    lt = score_long_term(df, LT_WEIGHTS, LT_GATES)
    mt = score_medium_term(df, MT_WEIGHTS, MT_GATES)

    # LT has no momentum weight → identical scores.
    assert lt.loc["BASE", "score_lt"] == lt.loc["NOMO", "score_lt"]
    # MT renormalises after dropping momentum → scores diverge.
    assert mt.loc["BASE", "score_mt"] != mt.loc["NOMO", "score_mt"]


def test_signal_uses_dcf_mos_when_available() -> None:
    """``DCF_MoS_Mid`` feeds ``generate_signal``; positive MoS + high
    composite should produce a "Strong Buy" / "Buy" downstream of the
    M6 two-criterion path.
    """
    deep_value = _row(
        "DEEP",
        valuation=90.0, profitability=90.0, health=85.0,
        growth=85.0, capital_allocation=80.0, risk_v2=80.0,
        earnings_quality=85.0, momentum=70.0,
        dcf_mos_mid=0.40,  # 40% margin of safety → Strong Buy gate
    )
    df = pd.DataFrame([deep_value]).set_index("Ticker")
    out = score_long_term(df, LT_WEIGHTS, LT_GATES)
    assert out.loc["DEEP", "signal_lt"] == "Strong Buy"


def test_empty_dataframe_returns_empty() -> None:
    """Edge case: empty ``df`` shouldn't crash the orchestrator."""
    df = pd.DataFrame()
    out = score_three_horizons(df, ALL_HORIZONS_BLOCK)
    assert out.empty


def test_default_sub_score_columns_used_when_omitted(universe: pd.DataFrame) -> None:
    """Calling without the mapping should fall back to the canonical names."""
    out = score_long_term(universe, LT_WEIGHTS, LT_GATES, sub_score_columns=None)
    assert "score_lt" in out.columns
    assert out["score_lt"].notna().all()
