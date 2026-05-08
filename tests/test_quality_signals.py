"""Unit tests for the M4 pure quality-signals module.

These tests are pure-function tests: no I/O, no fixtures from disk.  Each
synthetic ``row`` is a minimal dict containing exactly the inputs needed for
the signal under test.

Coverage
--------
* All 9 Piotroski signals (positive case, negative case, missing-input case)
* Aggregate ``piotroski_f_score`` (perfect-9, all-zero, partial-NaN)
* Altman Z (classic 5-factor) on a manufacturer-like fixture
* Altman Z'' on a high-quality fixture (Nestle-like, expect Safe > 2.6)
* Altman Z'' on a distressed fixture (Atos-like, expect < 1.1)
* Graham Number formula sanity check
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

from src.analysis.quality_signals import (  # noqa: E402
    altman_z_classic,
    altman_z_double_prime,
    altman_z_select,
    graham_number,
    piotroski_f_score,
    piotroski_signal_1_roa_positive,
    piotroski_signal_2_cfo_positive,
    piotroski_signal_3_delta_roa,
    piotroski_signal_4_accruals,
    piotroski_signal_5_delta_leverage,
    piotroski_signal_6_delta_liquidity,
    piotroski_signal_7_no_dilution,
    piotroski_signal_8_delta_gross_margin,
    piotroski_signal_9_delta_asset_turnover,
)


# ===========================================================================
# Piotroski -- individual signal tests
# ===========================================================================


class TestPiotroskiSignal1:
    def test_positive_roa_returns_1(self) -> None:
        assert piotroski_signal_1_roa_positive({"ROA": 0.08}) == 1

    def test_zero_roa_returns_0(self) -> None:
        assert piotroski_signal_1_roa_positive({"ROA": 0.0}) == 0

    def test_negative_roa_returns_0(self) -> None:
        assert piotroski_signal_1_roa_positive({"ROA": -0.05}) == 0

    def test_missing_roa_returns_none(self) -> None:
        assert piotroski_signal_1_roa_positive({}) is None
        assert piotroski_signal_1_roa_positive({"ROA": float("nan")}) is None


class TestPiotroskiSignal2:
    def test_positive_cfo(self) -> None:
        assert piotroski_signal_2_cfo_positive({"OperatingCashflow": 1_000_000}) == 1

    def test_negative_cfo(self) -> None:
        assert piotroski_signal_2_cfo_positive({"OperatingCashflow": -1_000}) == 0

    def test_missing_cfo(self) -> None:
        assert piotroski_signal_2_cfo_positive({}) is None


class TestPiotroskiSignal3:
    def test_roa_improved(self) -> None:
        assert (
            piotroski_signal_3_delta_roa({"ROA": 0.10, "ROA_PriorYear": 0.07}) == 1
        )

    def test_roa_declined(self) -> None:
        assert (
            piotroski_signal_3_delta_roa({"ROA": 0.05, "ROA_PriorYear": 0.07}) == 0
        )

    def test_missing_prior_year_returns_none(self) -> None:
        assert piotroski_signal_3_delta_roa({"ROA": 0.05}) is None


class TestPiotroskiSignal4:
    def test_accruals_quality_high(self) -> None:
        # CFO > NetIncome -> low accruals -> +1
        assert (
            piotroski_signal_4_accruals(
                {"OperatingCashflow": 100, "NetIncome": 50}
            )
            == 1
        )

    def test_accruals_quality_low(self) -> None:
        assert (
            piotroski_signal_4_accruals(
                {"OperatingCashflow": 50, "NetIncome": 100}
            )
            == 0
        )

    def test_missing_inputs(self) -> None:
        assert piotroski_signal_4_accruals({"NetIncome": 100}) is None


class TestPiotroskiSignal5:
    def test_leverage_decreased(self) -> None:
        assert (
            piotroski_signal_5_delta_leverage(
                {"LongTermDebt": 80, "LongTermDebt_PriorYear": 100}
            )
            == 1
        )

    def test_leverage_increased(self) -> None:
        assert (
            piotroski_signal_5_delta_leverage(
                {"LongTermDebt": 120, "LongTermDebt_PriorYear": 100}
            )
            == 0
        )

    def test_leverage_unchanged_does_not_count(self) -> None:
        # Strict less-than: a tie is treated as no improvement.
        assert (
            piotroski_signal_5_delta_leverage(
                {"LongTermDebt": 100, "LongTermDebt_PriorYear": 100}
            )
            == 0
        )

    def test_missing_returns_none(self) -> None:
        assert piotroski_signal_5_delta_leverage({"LongTermDebt": 100}) is None


class TestPiotroskiSignal6:
    def test_liquidity_improved(self) -> None:
        assert (
            piotroski_signal_6_delta_liquidity(
                {"CurrentRatio": 2.0, "CurrentRatio_PriorYear": 1.5}
            )
            == 1
        )

    def test_liquidity_declined(self) -> None:
        assert (
            piotroski_signal_6_delta_liquidity(
                {"CurrentRatio": 1.0, "CurrentRatio_PriorYear": 1.5}
            )
            == 0
        )


class TestPiotroskiSignal7:
    def test_no_dilution(self) -> None:
        # Shares decreased -> good
        assert (
            piotroski_signal_7_no_dilution(
                {"Shares": 1_000_000, "Shares_PriorYear": 1_000_000}
            )
            == 1
        )

    def test_small_buyback(self) -> None:
        # A buyback always passes
        assert (
            piotroski_signal_7_no_dilution(
                {"Shares": 950_000, "Shares_PriorYear": 1_000_000}
            )
            == 1
        )

    def test_within_tolerance(self) -> None:
        # Up to +0.5% increase counts as "no meaningful dilution"
        assert (
            piotroski_signal_7_no_dilution(
                {"Shares": 1_005_000, "Shares_PriorYear": 1_000_000}
            )
            == 1
        )

    def test_meaningful_dilution(self) -> None:
        assert (
            piotroski_signal_7_no_dilution(
                {"Shares": 1_100_000, "Shares_PriorYear": 1_000_000}
            )
            == 0
        )

    def test_missing_returns_none(self) -> None:
        assert piotroski_signal_7_no_dilution({"Shares": 1_000_000}) is None


class TestPiotroskiSignal8:
    def test_margin_improved(self) -> None:
        assert (
            piotroski_signal_8_delta_gross_margin(
                {"GrossMargin": 0.45, "GrossMargin_PriorYear": 0.40}
            )
            == 1
        )

    def test_margin_declined(self) -> None:
        assert (
            piotroski_signal_8_delta_gross_margin(
                {"GrossMargin": 0.35, "GrossMargin_PriorYear": 0.40}
            )
            == 0
        )


class TestPiotroskiSignal9:
    def test_asset_turnover_improved(self) -> None:
        # Now: 100/200 = 0.50; Prior: 80/200 = 0.40 -> improved
        row = {
            "Revenue": 100,
            "TotalAssets": 200,
            "Revenue_PriorYear": 80,
            "TotalAssets_PriorYear": 200,
        }
        assert piotroski_signal_9_delta_asset_turnover(row) == 1

    def test_asset_turnover_declined(self) -> None:
        row = {
            "Revenue": 80,
            "TotalAssets": 200,
            "Revenue_PriorYear": 100,
            "TotalAssets_PriorYear": 200,
        }
        assert piotroski_signal_9_delta_asset_turnover(row) == 0

    def test_zero_assets_skipped(self) -> None:
        row = {
            "Revenue": 80,
            "TotalAssets": 0,
            "Revenue_PriorYear": 100,
            "TotalAssets_PriorYear": 200,
        }
        assert piotroski_signal_9_delta_asset_turnover(row) is None


# ===========================================================================
# Piotroski aggregate
# ===========================================================================


def _perfect_row() -> dict:
    """Synthetic row where all 9 Piotroski signals trigger to +1."""
    return {
        # Signal 1: ROA > 0
        "ROA": 0.10,
        # Signal 2: CFO > 0
        "OperatingCashflow": 100,
        # Signal 3: ROA > prior ROA
        "ROA_PriorYear": 0.05,
        # Signal 4: CFO > NI
        "NetIncome": 50,
        # Signal 5: LTD decreased
        "LongTermDebt": 80,
        "LongTermDebt_PriorYear": 100,
        # Signal 6: Current ratio improved
        "CurrentRatio": 2.0,
        "CurrentRatio_PriorYear": 1.5,
        # Signal 7: No dilution (buyback)
        "Shares": 990_000,
        "Shares_PriorYear": 1_000_000,
        # Signal 8: Gross margin improved
        "GrossMargin": 0.45,
        "GrossMargin_PriorYear": 0.40,
        # Signal 9: Asset turnover improved
        "Revenue": 250,
        "TotalAssets": 1_000,
        "Revenue_PriorYear": 200,
        "TotalAssets_PriorYear": 1_000,
    }


def _all_zero_row() -> dict:
    """Synthetic row where every signal evaluates but none is satisfied."""
    return {
        "ROA": -0.05,
        "OperatingCashflow": -100,
        "ROA_PriorYear": 0.10,        # ROA declined
        "NetIncome": 200,             # CFO < NI
        "LongTermDebt": 120,
        "LongTermDebt_PriorYear": 100,  # LTD increased
        "CurrentRatio": 1.0,
        "CurrentRatio_PriorYear": 1.5,  # liquidity declined
        "Shares": 1_100_000,
        "Shares_PriorYear": 1_000_000,  # +10% dilution
        "GrossMargin": 0.30,
        "GrossMargin_PriorYear": 0.40,  # margin declined
        "Revenue": 80,
        "TotalAssets": 1_000,
        "Revenue_PriorYear": 100,
        "TotalAssets_PriorYear": 1_000,  # asset turnover declined
    }


class TestPiotroskiAggregate:
    def test_perfect_score_is_9(self) -> None:
        assert piotroski_f_score(_perfect_row()) == 9

    def test_all_zero_row_scores_0(self) -> None:
        assert piotroski_f_score(_all_zero_row()) == 0

    def test_partial_data_caps_at_present_signals(self) -> None:
        """A row with 3 inputs missing should score sum_of_5_remaining,
        not 5 out of 9 (the missing signals are skipped, not failed)."""
        row = _perfect_row()
        # Drop the inputs needed for signals 3, 5, 9 (4 prior-year fields cover three signals)
        for k in (
            "ROA_PriorYear",
            "LongTermDebt_PriorYear",
            "TotalAssets_PriorYear",
            "Revenue_PriorYear",
        ):
            row.pop(k, None)
        # Still 6 signals remain (1, 2, 4, 6, 7, 8).  All trigger -> 6.
        assert piotroski_f_score(row) == 6

    def test_completely_empty_row_scores_0(self) -> None:
        assert piotroski_f_score({}) == 0


# ===========================================================================
# Altman Z (classic, manufacturers)
# ===========================================================================


def _caterpillar_like_row() -> dict:
    """Manufacturer-like fixture (Caterpillar 2024 ballpark, simplified)."""
    return {
        "Sector": "Industrials",
        "TotalAssets": 87_000.0,
        "TotalEquity": 15_500.0,
        "MarketCap": 165_000.0,
        "Revenue": 67_000.0,
        "EBIT": 13_500.0,
        "CurrentAssets": 49_500.0,
        "CurrentLiabilities": 32_500.0,
        "RetainedEarnings": 47_700.0,
    }


class TestAltmanClassic:
    def test_caterpillar_like_in_safe_zone(self) -> None:
        row = _caterpillar_like_row()
        z = altman_z_classic(row)
        # Industrial blue chip -> classic Z above the safe threshold (2.99).
        assert z > 2.99, f"Expected Caterpillar-like classic Z > 2.99, got {z:.2f}"

    def test_classic_returns_nan_when_revenue_missing(self) -> None:
        row = _caterpillar_like_row()
        row["Revenue"] = float("nan")
        assert math.isnan(altman_z_classic(row))


# ===========================================================================
# Altman Z'' (4-factor, non-manufacturers)
# ===========================================================================


def _nestle_like_row() -> dict:
    """High-quality non-manufacturer-equivalent fixture.

    Values approximate Nestle 2024 (CHF millions, scaled): high RE, healthy
    EBIT/TA, deep equity buffer.  Z'' should land firmly in the Safe zone (>2.6).
    """
    return {
        "Sector": "Consumer Defensive",  # treated as manufacturer; pick non-mfr below
        "TotalAssets": 130_000.0,
        "TotalEquity": 50_000.0,
        "MarketCap": 250_000.0,
        "Revenue": 95_000.0,
        "EBIT": 17_000.0,
        "CurrentAssets": 36_000.0,
        "CurrentLiabilities": 33_000.0,
        "RetainedEarnings": 75_000.0,
    }


def _atos_like_distressed_row() -> dict:
    """Distressed non-manufacturer fixture.

    Approximates Atos pre-restructuring 2023:
      - Negative retained earnings (massive accumulated losses)
      - Negative working capital
      - Tiny EBIT relative to assets
      - Equity wiped out -> book leverage extreme
    Z'' should be deeply distressed (< 1.1).
    """
    return {
        "Sector": "Technology",  # IT services -> Z'' applies
        "TotalAssets": 9_000.0,
        "TotalEquity": 500.0,
        "MarketCap": 250.0,            # post-collapse
        "Revenue": 10_700.0,
        "EBIT": 50.0,                  # near zero
        "CurrentAssets": 3_000.0,
        "CurrentLiabilities": 5_500.0,  # working capital deficit
        "RetainedEarnings": -4_500.0,   # massive accumulated losses
    }


class TestAltmanDoublePrime:
    def test_nestle_like_safe_zone(self) -> None:
        row = _nestle_like_row()
        z = altman_z_double_prime(row)
        assert z > 2.6, f"Expected Nestle-like Z'' > 2.6, got {z:.2f}"

    def test_atos_like_distress_zone(self) -> None:
        row = _atos_like_distressed_row()
        z = altman_z_double_prime(row)
        assert z < 1.1, f"Expected Atos-like Z'' < 1.1, got {z:.2f}"

    def test_returns_nan_when_required_input_missing(self) -> None:
        row = _nestle_like_row()
        row["RetainedEarnings"] = float("nan")
        assert math.isnan(altman_z_double_prime(row))


class TestAltmanSelect:
    def test_industrial_sector_picks_classic(self) -> None:
        row = _caterpillar_like_row()
        score, variant = altman_z_select(row)
        assert variant == "classic"
        assert score == altman_z_classic(row)

    def test_tech_sector_picks_double_prime(self) -> None:
        row = _atos_like_distressed_row()
        score, variant = altman_z_select(row)
        assert variant == "double_prime"
        assert score == altman_z_double_prime(row)

    def test_blank_sector_falls_back_to_double_prime(self) -> None:
        row = _nestle_like_row()
        row["Sector"] = ""
        score, variant = altman_z_select(row)
        assert variant == "double_prime"


# ===========================================================================
# Graham Number
# ===========================================================================


class TestGrahamNumber:
    def test_basic_formula(self) -> None:
        # EPS = 2.0, BVPS = 8.0 -> Graham = sqrt(22.5 * 2 * 8) = sqrt(360) = 18.97
        row = {
            "NetIncome": 200.0,    # NI = 200, shares = 100 -> EPS = 2.0
            "Shares": 100.0,
            "TotalEquity": 800.0,  # BVPS = 800 / 100 = 8.0
        }
        gn = graham_number(row)
        assert math.isclose(gn, math.sqrt(22.5 * 2.0 * 8.0), rel_tol=1e-9)

    def test_negative_eps_returns_nan(self) -> None:
        row = {"NetIncome": -100.0, "Shares": 100.0, "TotalEquity": 800.0}
        assert math.isnan(graham_number(row))

    def test_negative_book_returns_nan(self) -> None:
        row = {"NetIncome": 100.0, "Shares": 100.0, "TotalEquity": -50.0}
        assert math.isnan(graham_number(row))

    def test_missing_inputs_returns_nan(self) -> None:
        assert math.isnan(graham_number({}))
