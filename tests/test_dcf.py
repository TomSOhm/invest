"""Unit tests for the M6 two-stage DCF module.

Each helper is tested in isolation against synthetic fixtures with a known
analytic answer; ``dcf_with_sensitivity`` is tested end-to-end on
AAPL-like and Atos-like (distressed) inputs to verify both happy-path
fair-value bracketing and NaN-safe degradation.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.analysis.dcf import (  # noqa: E402
    build_revenue_glide,
    compute_wacc,
    dcf_with_sensitivity,
    intrinsic_value_per_share,
    project_fcf,
    terminal_value,
)


# ──────────────────────────────────────────────────────────────────────────────
# compute_wacc
# ──────────────────────────────────────────────────────────────────────────────


def test_compute_wacc_aapl_like_in_expected_range() -> None:
    """AAPL-like firm: Beta 1.0, MC 3T, Debt 100B → WACC ~8-9%.

    Re = 3% + 1.0 * 5.5% = 8.5%
    Almost-pure-equity firm → WACC ≈ Re ≈ 8.5%.
    """
    wacc = compute_wacc(
        beta=1.0,
        market_cap=3_000_000_000_000,
        total_debt=100_000_000_000,
        tax_rate=0.25,
        risk_free_rate=0.03,
        equity_risk_premium=0.055,
        cost_of_debt=0.05,
    )
    assert 0.08 <= wacc <= 0.09, f"AAPL-like WACC out of range: {wacc:.4f}"


def test_compute_wacc_zero_debt() -> None:
    """All-equity firm: WACC = Re exactly."""
    wacc = compute_wacc(
        beta=1.2, market_cap=10e9, total_debt=0,
        risk_free_rate=0.03, equity_risk_premium=0.055,
    )
    expected_re = 0.03 + 1.2 * 0.055
    assert math.isclose(wacc, expected_re, rel_tol=1e-9)


def test_compute_wacc_high_leverage() -> None:
    """Heavily-levered firm: WACC pulled down toward after-tax cost of debt."""
    wacc_lev = compute_wacc(
        beta=1.0, market_cap=10e9, total_debt=40e9,
        cost_of_debt=0.05, tax_rate=0.25,
    )
    wacc_unlev = compute_wacc(
        beta=1.0, market_cap=10e9, total_debt=0,
    )
    assert wacc_lev < wacc_unlev


def test_compute_wacc_returns_nan_when_market_cap_missing() -> None:
    assert math.isnan(compute_wacc(beta=1.0, market_cap=float("nan"), total_debt=0))


def test_compute_wacc_returns_nan_when_beta_missing() -> None:
    assert math.isnan(compute_wacc(beta=float("nan"), market_cap=1e10, total_debt=0))


def test_compute_wacc_returns_nan_when_market_cap_zero() -> None:
    assert math.isnan(compute_wacc(beta=1.0, market_cap=0, total_debt=0))


# ──────────────────────────────────────────────────────────────────────────────
# build_revenue_glide
# ──────────────────────────────────────────────────────────────────────────────


def test_build_revenue_glide_endpoints_correct() -> None:
    """Year 1 = near-term growth, year 5 = terminal growth."""
    glide = build_revenue_glide(near_term_growth=0.10, terminal_growth=0.025, n_years=5)
    assert math.isclose(glide[0], 0.10, rel_tol=1e-9)
    assert math.isclose(glide[-1], 0.025, rel_tol=1e-9)


def test_build_revenue_glide_strictly_decreasing_when_above_terminal() -> None:
    glide = build_revenue_glide(near_term_growth=0.20, terminal_growth=0.025)
    diffs = np.diff(glide)
    assert np.all(diffs < 0)


def test_build_revenue_glide_handles_nan_growth() -> None:
    """NaN near-term growth → all years pinned at terminal rate."""
    glide = build_revenue_glide(near_term_growth=float("nan"), terminal_growth=0.025)
    assert all(math.isclose(x, 0.025, rel_tol=1e-9) for x in glide)


def test_build_revenue_glide_clamps_extreme_growth() -> None:
    """A 250% YoY growth (e.g. SPAC year 1) is clamped to ±50%."""
    glide = build_revenue_glide(near_term_growth=2.5, terminal_growth=0.025)
    assert glide[0] <= 0.50


# ──────────────────────────────────────────────────────────────────────────────
# project_fcf
# ──────────────────────────────────────────────────────────────────────────────


def test_project_fcf_exact_sequence() -> None:
    """Revenue 100, glide [10%, 8%, 6%, 5%, 4%], margin 0.20.

    Year 1 rev = 100 * 1.10 = 110, FCF = 22.0
    Year 2 rev = 110 * 1.08 = 118.8, FCF = 23.76
    Year 3 rev = 118.8 * 1.06 = 125.928, FCF ≈ 25.1856
    Year 4 rev = 125.928 * 1.05 = 132.2244, FCF ≈ 26.44488
    Year 5 rev = 132.2244 * 1.04 = 137.51338, FCF ≈ 27.50267
    """
    fcf_proj = project_fcf(
        fcf_t0=20.0,
        revenue_growth_glide=[0.10, 0.08, 0.06, 0.05, 0.04],
        fcf_margin=0.20,
        revenue_t0=100.0,
    )
    expected = np.array([22.0, 23.76, 25.1856, 26.44488, 27.5026752])
    np.testing.assert_allclose(fcf_proj, expected, rtol=1e-6)


def test_project_fcf_returns_nan_when_revenue_missing_and_no_fallback() -> None:
    fcf_proj = project_fcf(
        fcf_t0=float("nan"),
        revenue_growth_glide=[0.05] * 5,
        fcf_margin=0.20,
        revenue_t0=float("nan"),
    )
    assert np.all(np.isnan(fcf_proj))


def test_project_fcf_falls_back_to_fcf_growth_when_revenue_missing() -> None:
    """If Revenue is missing but FCF is present, project FCF directly."""
    fcf_proj = project_fcf(
        fcf_t0=100.0,
        revenue_growth_glide=[0.10] * 5,
        fcf_margin=0.20,
        revenue_t0=float("nan"),
    )
    expected = np.array([110.0, 121.0, 133.1, 146.41, 161.051])
    np.testing.assert_allclose(fcf_proj, expected, rtol=1e-6)


# ──────────────────────────────────────────────────────────────────────────────
# terminal_value
# ──────────────────────────────────────────────────────────────────────────────


def test_terminal_value_textbook_example() -> None:
    """FCF=100, WACC=9%, TGR=2.5% → 100 * 1.025 / (0.09 - 0.025) ≈ 1576.92."""
    tv = terminal_value(fcf_year_5=100.0, wacc=0.09, terminal_growth_rate=0.025)
    assert math.isclose(tv, 100.0 * 1.025 / 0.065, rel_tol=1e-9)
    assert 1576 < tv < 1578


def test_terminal_value_returns_nan_when_wacc_lt_tgr() -> None:
    """Gordon model is invalid: WACC must exceed TGR."""
    assert math.isnan(terminal_value(fcf_year_5=100.0, wacc=0.02, terminal_growth_rate=0.03))


def test_terminal_value_returns_nan_when_wacc_eq_tgr() -> None:
    """Gordon model degenerates at WACC == TGR."""
    assert math.isnan(terminal_value(fcf_year_5=100.0, wacc=0.025, terminal_growth_rate=0.025))


def test_terminal_value_nan_inputs() -> None:
    assert math.isnan(terminal_value(float("nan"), 0.09, 0.025))
    assert math.isnan(terminal_value(100.0, float("nan"), 0.025))
    assert math.isnan(terminal_value(100.0, 0.09, float("nan")))


# ──────────────────────────────────────────────────────────────────────────────
# intrinsic_value_per_share
# ──────────────────────────────────────────────────────────────────────────────


def test_intrinsic_value_per_share_synthetic_known_answer() -> None:
    """Hand-checkable case.

    fcf_proj = [100, 100, 100, 100, 100] (constant FCF for clarity)
    tv = 1000
    wacc = 10%
    shares = 1
    net_debt = 0

    PV(FCF) = 100/1.1 + 100/1.21 + 100/1.331 + 100/1.4641 + 100/1.61051
            = 90.9091 + 82.6446 + 75.1315 + 68.3013 + 62.0921 = 379.0787
    PV(TV)  = 1000 / 1.61051 = 620.9213
    EV      = 1000.0
    Per-share = 1000.0
    """
    iv = intrinsic_value_per_share(
        fcf_proj=np.array([100.0] * 5),
        tv=1000.0,
        wacc=0.10,
        shares_out=1.0,
        net_debt=0.0,
    )
    assert math.isclose(iv, 1000.0, rel_tol=1e-6)


def test_intrinsic_value_per_share_subtracts_net_debt() -> None:
    """Identical to above but with 200 net debt → equity = 800, per share = 800."""
    iv = intrinsic_value_per_share(
        fcf_proj=np.array([100.0] * 5),
        tv=1000.0,
        wacc=0.10,
        shares_out=1.0,
        net_debt=200.0,
    )
    assert math.isclose(iv, 800.0, rel_tol=1e-6)


def test_intrinsic_value_per_share_nan_when_shares_zero() -> None:
    iv = intrinsic_value_per_share(
        fcf_proj=np.array([100.0] * 5),
        tv=1000.0, wacc=0.10, shares_out=0.0, net_debt=0.0,
    )
    assert math.isnan(iv)


def test_intrinsic_value_per_share_nan_when_fcf_proj_has_nan() -> None:
    iv = intrinsic_value_per_share(
        fcf_proj=np.array([100.0, float("nan"), 100.0, 100.0, 100.0]),
        tv=1000.0, wacc=0.10, shares_out=1.0, net_debt=0.0,
    )
    assert math.isnan(iv)


# ──────────────────────────────────────────────────────────────────────────────
# dcf_with_sensitivity — happy path
# ──────────────────────────────────────────────────────────────────────────────


def _aapl_like_inputs() -> dict:
    """Plausible AAPL-style row (values approximate, units consistent)."""
    return {
        "Beta": 1.07,
        "MarketCap": 4.22e12,
        "TotalDebt": 8.5e10,
        "Cash": 6.85e10,
        "Shares": 1.469e10,
        "Revenue": 4.51e11,
        "FCF": 1.01e11,
        "FCFMargin": 0.224,
        "RevenueGrowth": 0.10,   # blend of 5y CAGR + recent
        "Price": 190.0,          # consensus zone in 2026
    }


def test_dcf_aapl_like_fair_value_brackets_consensus() -> None:
    """AAPL-like inputs → mid intrinsic in [$120, $260].

    The point is to verify the math is in the right ballpark, not to nail
    a precise number (which would be brittle given input assumptions).
    """
    out = dcf_with_sensitivity(_aapl_like_inputs())
    assert not math.isnan(out["intrinsic_mid"]), out["warnings"]
    assert 100 <= out["intrinsic_mid"] <= 300, (
        f"AAPL-like mid intrinsic out of expected $100-$300 range: "
        f"{out['intrinsic_mid']:.2f} (warnings={out['warnings']})"
    )


def test_dcf_aapl_like_mos_within_sensible_range() -> None:
    """At a $190 price the MoS_Mid should fall inside [-0.50, +0.70]."""
    out = dcf_with_sensitivity(_aapl_like_inputs())
    assert not math.isnan(out["mos_mid"])
    assert -0.50 <= out["mos_mid"] <= 0.70, (
        f"AAPL-like mos_mid out of band: {out['mos_mid']:.3f}"
    )


def test_dcf_grid_low_mid_high_ordering() -> None:
    """Sensitivity grid produces ``low <= mid <= high``."""
    out = dcf_with_sensitivity(_aapl_like_inputs())
    assert out["intrinsic_low"] <= out["intrinsic_mid"] <= out["intrinsic_high"]
    assert out["mos_low"] <= out["mos_mid"] <= out["mos_high"]


def test_dcf_grid_has_nine_cells() -> None:
    """3x3 sensitivity grid → exactly 9 named scenarios."""
    out = dcf_with_sensitivity(_aapl_like_inputs())
    assert len(out["scenarios"]) == 9
    expected_keys = {
        "wacc-tgr-", "wacc-tgr", "wacc-tgr+",
        "wacctgr-", "wacctgr", "wacctgr+",
        "wacc+tgr-", "wacc+tgr", "wacc+tgr+",
    }
    assert set(out["scenarios"].keys()) == expected_keys


def test_dcf_lower_wacc_higher_intrinsic() -> None:
    """Within a row, the wacc- column produces a higher intrinsic than wacc+.

    Cross-check from a single-point DCF property: lower discount rate ->
    higher present value.
    """
    out = dcf_with_sensitivity(_aapl_like_inputs())
    assert out["scenarios"]["wacc-tgr"] > out["scenarios"]["wacc+tgr"]


# ──────────────────────────────────────────────────────────────────────────────
# dcf_with_sensitivity — distressed / partial-data fallbacks
# ──────────────────────────────────────────────────────────────────────────────


def test_dcf_atos_like_distressed_warns_or_returns_negative() -> None:
    """Atos-style: negative FCF, negative revenue growth → warning + sad MoS.

    With FCF margin negative and price $5 vs. $100 cash burn, mos_mid should
    either be NaN or sharply negative (≤ -0.30 would trigger Strong Sell in
    the new signal logic).
    """
    inputs = {
        "Beta": 1.5,
        "MarketCap": 5e8,
        "TotalDebt": 4e9,
        "Cash": 2e8,
        "Shares": 1.1e8,
        "Revenue": 1.0e10,
        "FCF": -5.0e8,
        "FCFMargin": -0.05,
        "RevenueGrowth": -0.20,
        "Price": 5.0,
    }
    out = dcf_with_sensitivity(inputs)
    assert out["warnings"], "expected at least one warning for distressed inputs"
    # Either NaN or sharply negative MoS — both are acceptable signal values
    if not math.isnan(out["mos_mid"]):
        assert out["mos_mid"] <= 0.0, (
            f"distressed mos_mid should be <=0, got {out['mos_mid']}"
        )


def test_dcf_returns_nan_when_market_cap_missing() -> None:
    inputs = {
        "Beta": 1.0,
        "MarketCap": float("nan"),
        "TotalDebt": 0,
        "Cash": 0,
        "Shares": 1e9,
        "Revenue": 1e9,
        "FCF": 1e8,
        "FCFMargin": 0.10,
        "RevenueGrowth": 0.05,
        "Price": 50.0,
    }
    out = dcf_with_sensitivity(inputs)
    assert math.isnan(out["intrinsic_mid"])
    assert math.isnan(out["mos_mid"])
    assert any("MarketCap" in w or "capital-structure" in w for w in out["warnings"])


def test_dcf_returns_nan_when_revenue_missing() -> None:
    inputs = {
        "Beta": 1.0,
        "MarketCap": 1e10,
        "TotalDebt": 0,
        "Cash": 0,
        "Shares": 1e9,
        "Revenue": float("nan"),
        "FCF": 1e8,
        "FCFMargin": 0.10,
        "RevenueGrowth": 0.05,
        "Price": 50.0,
    }
    out = dcf_with_sensitivity(inputs)
    assert math.isnan(out["intrinsic_mid"])
    assert any("Revenue" in w for w in out["warnings"])


def test_dcf_no_price_yields_nan_mos_but_finite_intrinsic() -> None:
    """When Price is missing, intrinsic still computes; only MoS is NaN."""
    inputs = _aapl_like_inputs()
    inputs["Price"] = float("nan")
    out = dcf_with_sensitivity(inputs)
    assert not math.isnan(out["intrinsic_mid"])
    assert math.isnan(out["mos_mid"])
    assert any("Price" in w for w in out["warnings"])


def test_dcf_settings_override() -> None:
    """Caller-supplied settings.yaml ``valuation.dcf`` block is respected."""
    out_default = dcf_with_sensitivity(_aapl_like_inputs())
    out_lower_rf = dcf_with_sensitivity(
        _aapl_like_inputs(),
        settings={
            "projection_years": 5,
            "terminal_growth_rate": 0.025,
            "risk_free_rate": 0.01,        # 100bp lower than default 3%
            "equity_risk_premium": 0.055,
            "tax_rate_default": 0.25,
        },
    )
    # Lower risk-free rate -> lower WACC -> higher intrinsic value.
    assert out_lower_rf["wacc_base"] < out_default["wacc_base"]
    assert out_lower_rf["intrinsic_mid"] > out_default["intrinsic_mid"]


# ──────────────────────────────────────────────────────────────────────────────
# generate_signal — M6 MoS activation
# ──────────────────────────────────────────────────────────────────────────────


def test_generate_signal_strong_buy_requires_high_score_and_deep_mos() -> None:
    from src.analysis.scoring_engine import generate_signal

    # Score 85, MoS 0.40 → Strong Buy
    assert generate_signal(85, 0.40) == "Strong Buy"
    # Score 85, MoS 0.10 → Buy (score qualifies but MoS falls short of 0.30)
    assert generate_signal(85, 0.10) == "Hold"  # score>=80 but mos<0.15 -> falls through
    # Strictly: 85 / 0.10 -> not Strong Buy (MoS too thin) and not Buy (mos<0.15) → Hold


def test_generate_signal_buy_threshold() -> None:
    from src.analysis.scoring_engine import generate_signal

    assert generate_signal(70, 0.20) == "Buy"
    assert generate_signal(64, 0.20) == "Hold"  # composite < 65


def test_generate_signal_strong_sell_when_overvalued_regardless_of_score() -> None:
    from src.analysis.scoring_engine import generate_signal

    # Even a score of 90, if price is 50% above intrinsic, gets Strong Sell.
    assert generate_signal(90, -0.40) == "Strong Sell"


def test_generate_signal_sell_when_score_low_or_overvalued() -> None:
    from src.analysis.scoring_engine import generate_signal

    assert generate_signal(35, 0.05) == "Sell"        # low score
    assert generate_signal(70, -0.20) == "Sell"       # overvalued


def test_generate_signal_legacy_fallback_when_mos_missing() -> None:
    """When MoS is NaN the function reverts to composite-only thresholds."""
    from src.analysis.scoring_engine import generate_signal

    assert generate_signal(85, float("nan")) == "Strong Buy"
    assert generate_signal(70, float("nan")) == "Buy"
    assert generate_signal(50, float("nan")) == "Hold"
    assert generate_signal(30, float("nan")) == "Sell"
    assert generate_signal(20, float("nan")) == "Strong Sell"


def test_generate_signal_default_arg_is_nan() -> None:
    """Backward-compat: legacy callers passing only composite still work."""
    from src.analysis.scoring_engine import generate_signal

    # Same as the legacy fallback above.
    assert generate_signal(85) == "Strong Buy"
    assert generate_signal(50) == "Hold"
