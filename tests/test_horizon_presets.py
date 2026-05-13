"""
Tests for src/strategy/horizon_presets.py and the M8 additions to screener.py.

Strategy
--------
Each of the 9 presets is tested against a synthetic 30-row DataFrame that
contains:
  - One "perfect-fit" row designed to pass the preset
  - Several rows deliberately engineered to fail one or more of the preset's
    active filters

Because several filters depend on columns not yet plumbed into the data layer
(e.g. RSI_2, Forward_PE, OpMarginImprovement_YoY), ``apply_filters`` silently
skips them.  Tests for those presets are structured so the perfect-fit row
still passes *all actually-applied filters*, and the failure rows fail at
least one *present* filter.

Cross-cutting assertions:
    - ST presets carry recommended_account="CTO" in the preset dict.
    - LT_PEA_DEFENSIVE enforces pea_only (non-EU rows excluded).
    - LT_DEEP_VALUE's key edge cases: F-Score ≥ 6 AND Altman Z ≥ 1.8.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from src.strategy.horizon_presets import (
    LT_DEEP_VALUE,
    LT_PEA_DEFENSIVE,
    LT_QUALITY_COMPOUNDER,
    MT_GARP,
    MT_INCOME,
    MT_TURNAROUND,
    PRESET_REGISTRY,
    ST_EARNINGS_DRIFT,
    ST_MOMENTUM_QUALITY,
    ST_OVERSOLD_BOUNCE,
    get_preset,
    list_presets,
    screen_horizon_preset,
)
from src.strategy.screener import apply_filters

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _base_row() -> dict[str, Any]:
    """A minimally-valid row that clears the universal pre-filters.

    Any field not explicitly set here defaults to NaN, which passes all
    apply_filters NaN-tolerant checks.
    """
    return {
        "Ticker": "BASE",
        "MarketCap": 500_000_000,  # €500M — above €100M floor
        "AvgVolume": 1_000_000,  # above €500k floor
        "YearsListed": 5,  # ≥ 3 years
        "Sector": "Technology",  # not in exclude list
        "Altman_Z": 3.0,  # well above 1.1 distress floor
        "data_completeness": 0.85,
        "Composite_Score": 70.0,
        "PEA": True,
        "Country": "FR",
        # Sub-score columns
        "Valuation_Score": 60.0,
        "Health_Score": 70.0,
        "Profitability_Score": 70.0,
        "Growth_Score": 65.0,
        "Shareholder_Score": 60.0,
        "Risk_Score_v2": 65.0,
        "EarningsQuality_Score": 65.0,
        "Moat_Score": 65.0,
        "Momentum_Score": 60.0,
        # Key fundamentals
        "ROIC": 0.18,
        "ROE": 0.20,
        "PB": 2.0,
        "PE": 16.0,
        "PFCF": 20.0,
        "DivYield": 0.03,
        "PayoutRatio": 0.40,
        "InterestCoverage": 8.0,
        "FCF": 100_000_000,
        "FCFMargin": 0.12,
        "OperatingMargin": 0.15,
        "RevenueGrowth": 0.08,
        "Beta": 0.85,
        "EV_EBITDA": 10.0,
        "EBITDA": 200_000_000,
        "EBIT": 160_000_000,
        "TotalDebt": 300_000_000,
        "Cash": 100_000_000,
        "Piotroski_F": 8,
        # M6 DCF
        "DCF_MoS_Mid": 0.20,
        # M9 columns
        "Above_50DMA": True,
        "Above_200DMA": True,
        "Golden_Cross": True,
        "Volume_Surge": 1.5,
        "Momentum_12_1": 0.15,
        "RS_3m": 0.05,
        "EPS_Rev_90d": 0.03,
        "EPS_Rev_180d": 0.04,
        "SUE": 1.8,
        "Sentiment_Score": 0.1,
        # Horizon scores
        "score_lt": 75.0,
        "passes_gates_lt": True,
        "signal_lt": "Buy",
        "blockers_lt": [],
        "score_mt": 70.0,
        "passes_gates_mt": True,
        "signal_mt": "Buy",
        "blockers_mt": [],
        "score_st": 65.0,
        "passes_gates_st": True,
        "signal_st": "Buy",
        "blockers_st": [],
    }


def _make_universe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame from a list of row dicts, indexed by Ticker."""
    df = pd.DataFrame(rows)
    if "Ticker" in df.columns:
        df = df.set_index("Ticker")
    # Ensure numeric columns aren't object dtype
    numeric_cols = [
        "MarketCap",
        "AvgVolume",
        "YearsListed",
        "Altman_Z",
        "data_completeness",
        "Composite_Score",
        "Valuation_Score",
        "Health_Score",
        "Profitability_Score",
        "Growth_Score",
        "Shareholder_Score",
        "Risk_Score_v2",
        "EarningsQuality_Score",
        "Moat_Score",
        "Momentum_Score",
        "ROIC",
        "ROE",
        "PB",
        "PE",
        "PFCF",
        "DivYield",
        "PayoutRatio",
        "InterestCoverage",
        "FCF",
        "FCFMargin",
        "OperatingMargin",
        "RevenueGrowth",
        "Beta",
        "EV_EBITDA",
        "EBITDA",
        "EBIT",
        "TotalDebt",
        "Cash",
        "Piotroski_F",
        "DCF_MoS_Mid",
        "Volume_Surge",
        "Momentum_12_1",
        "RS_3m",
        "EPS_Rev_90d",
        "EPS_Rev_180d",
        "SUE",
        "Sentiment_Score",
        "score_lt",
        "score_mt",
        "score_st",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _row(**overrides: Any) -> dict[str, Any]:
    """Return a base row with selective overrides."""
    r = _base_row()
    r.update(overrides)
    return r


def _build_30_rows(perfect_ticker: str, perfect_overrides: dict[str, Any]) -> pd.DataFrame:
    """30-row universe: 1 perfect + 29 filler rows with varied quality."""
    rows = [_row(Ticker=perfect_ticker, **perfect_overrides)]
    # 29 filler rows with mediocre data so the perfect row stands out
    for i in range(29):
        rows.append(
            _row(
                Ticker=f"FILL{i:02d}",
                Composite_Score=40.0 + i * 0.5,
                score_lt=40.0 + i * 0.5,
                score_mt=38.0 + i * 0.5,
                score_st=35.0 + i * 0.5,
                Piotroski_F=4,
                Altman_Z=1.5,
                ROIC=0.05,
                FCFMargin=0.02,
                data_completeness=0.65,  # Below 0.80 — will fail strict LT threshold
            )
        )
    return _make_universe(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Registry-level tests
# ──────────────────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_all_9_presets_present(self):
        expected = {
            "LT_QUALITY_COMPOUNDER",
            "LT_PEA_DEFENSIVE",
            "LT_DEEP_VALUE",
            "MT_GARP",
            "MT_TURNAROUND",
            "MT_INCOME",
            "ST_MOMENTUM_QUALITY",
            "ST_EARNINGS_DRIFT",
            "ST_OVERSOLD_BOUNCE",
        }
        assert set(PRESET_REGISTRY.keys()) == expected

    def test_get_preset_returns_dict(self):
        preset = get_preset("LT_QUALITY_COMPOUNDER")
        assert isinstance(preset, dict)
        assert "horizon" in preset
        assert "filters" in preset

    def test_get_preset_raises_on_unknown(self):
        with pytest.raises(KeyError, match="Unknown preset"):
            get_preset("DOES_NOT_EXIST")

    def test_list_presets_length(self):
        entries = list_presets()
        assert len(entries) == 9

    def test_list_presets_fields(self):
        for e in list_presets():
            assert "name" in e
            assert "horizon" in e
            assert "description" in e

    def test_list_presets_sorted_by_horizon(self):
        entries = list_presets()
        horizons = [e["horizon"] for e in entries]
        order = {"long_term": 0, "medium_term": 1, "short_term": 2}
        assert horizons == sorted(horizons, key=lambda h: order[h])

    def test_lt_presets_horizon(self):
        for name in ("LT_QUALITY_COMPOUNDER", "LT_PEA_DEFENSIVE", "LT_DEEP_VALUE"):
            assert PRESET_REGISTRY[name]["horizon"] == "long_term"

    def test_mt_presets_horizon(self):
        for name in ("MT_GARP", "MT_TURNAROUND", "MT_INCOME"):
            assert PRESET_REGISTRY[name]["horizon"] == "medium_term"

    def test_st_presets_horizon(self):
        for name in ("ST_MOMENTUM_QUALITY", "ST_EARNINGS_DRIFT", "ST_OVERSOLD_BOUNCE"):
            assert PRESET_REGISTRY[name]["horizon"] == "short_term"

    def test_st_presets_carry_cto_flag(self):
        for name in ("ST_MOMENTUM_QUALITY", "ST_EARNINGS_DRIFT", "ST_OVERSOLD_BOUNCE"):
            p = PRESET_REGISTRY[name]
            assert p.get("recommended_account") == "CTO", f"{name} must carry recommended_account='CTO'"
            assert p.get("pea_warning") is True, f"{name} must carry pea_warning=True"

    def test_every_preset_has_universal_prefilters(self):
        """Each preset must include the universal pre-filter keys."""
        required = {"min_market_cap", "min_years_listed", "not_in_distress", "min_data_completeness"}
        for name, p in PRESET_REGISTRY.items():
            for key in required:
                assert key in p["filters"], f"Preset {name} is missing universal filter '{key}'"


# ──────────────────────────────────────────────────────────────────────────────
# LT_QUALITY_COMPOUNDER
# ──────────────────────────────────────────────────────────────────────────────


class TestLTQualityCompounder:
    PRESET = LT_QUALITY_COMPOUNDER

    def test_perfect_row_passes(self):
        df = _build_30_rows(
            "PERFECT",
            {
                "ROIC": 0.18,
                "Piotroski_F": 8,
                "Altman_Z": 3.0,
                "InterestCoverage": 8.0,
                "FCFMargin": 0.12,
                "data_completeness": 0.85,
                "DCF_MoS_Mid": 0.20,
                "PFCF": 22.0,
                "score_lt": 75.0,
                "passes_gates_lt": True,
                "Composite_Score": 75.0,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "PERFECT" in result.index

    def test_low_f_score_excluded(self):
        """F-Score < 7 should be excluded."""
        df = _build_30_rows("LOW_F", {"Piotroski_F": 5, "data_completeness": 0.85})
        result = apply_filters(df, self.PRESET["filters"])
        assert "LOW_F" not in result.index

    def test_low_altman_z_excluded(self):
        """Altman Z < 2.6 should be excluded (strict LT safety zone)."""
        df = _build_30_rows("DISTRESSED", {"Altman_Z": 1.5, "data_completeness": 0.85})
        result = apply_filters(df, self.PRESET["filters"])
        assert "DISTRESSED" not in result.index

    def test_low_data_completeness_excluded(self):
        """data_completeness < 0.80 excluded (LT threshold)."""
        df = _build_30_rows("SPARSE", {"data_completeness": 0.70})
        result = apply_filters(df, self.PRESET["filters"])
        assert "SPARSE" not in result.index

    def test_tobacco_sector_excluded(self):
        """Tobacco sector must be filtered out."""
        df = _build_30_rows("TOBACCO", {"Sector": "Tobacco", "data_completeness": 0.85})
        result = apply_filters(df, self.PRESET["filters"])
        assert "TOBACCO" not in result.index

    def test_no_crash_missing_optional_columns(self):
        """Preset should not crash when optional M5/M9 columns are absent."""
        df = _build_30_rows("MIN", {"data_completeness": 0.85, "Piotroski_F": 8})
        # Drop optional columns that are referenced but might not exist
        cols_to_drop = [
            "ROIC_5y_Avg",
            "CashConversionRatio_3y",
            "Gross_Profitability",
            "RevenueCAGR_5y",
            "EPS_CAGR_5y",
            "PosRevenueYears_5y",
            "TotalShareholderYield",
        ]
        for col in cols_to_drop:
            if col in df.columns:
                df = df.drop(columns=[col])
        # Should not raise
        result = apply_filters(df, self.PRESET["filters"])
        assert isinstance(result, pd.DataFrame)


# ──────────────────────────────────────────────────────────────────────────────
# LT_PEA_DEFENSIVE
# ──────────────────────────────────────────────────────────────────────────────


class TestLTPEADefensive:
    PRESET = LT_PEA_DEFENSIVE

    def test_pea_only_enforced(self):
        """Non-EU companies (PEA=False) must be excluded."""
        rows = [
            _row(
                Ticker="EU_CO",
                PEA=True,
                data_completeness=0.85,
                Piotroski_F=8,
                Altman_Z=3.0,
                MarketCap=2_000_000_000,
                Beta=0.80,
                DivYield=0.025,
            ),
            _row(
                Ticker="US_CO",
                PEA=False,
                data_completeness=0.85,
                Piotroski_F=8,
                Altman_Z=3.0,
                MarketCap=2_000_000_000,
                Beta=0.80,
                DivYield=0.025,
            ),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, self.PRESET["filters"], pea_only=True)
        assert "EU_CO" in result.index
        assert "US_CO" not in result.index

    def test_high_beta_excluded(self):
        """Beta > 1.0 must be excluded (defensive tilt)."""
        df = _build_30_rows(
            "HIGHVOL",
            {
                "Beta": 1.3,
                "PEA": True,
                "data_completeness": 0.85,
                "Piotroski_F": 8,
                "Altman_Z": 3.0,
                "MarketCap": 2_000_000_000,
                "DivYield": 0.025,
            },
        )
        result = apply_filters(df, self.PRESET["filters"], pea_only=True)
        assert "HIGHVOL" not in result.index

    def test_no_dividend_excluded(self):
        """DivYield < 0.02 must be excluded."""
        df = _build_30_rows(
            "NODIV",
            {
                "DivYield": 0.005,
                "PEA": True,
                "data_completeness": 0.85,
                "Piotroski_F": 8,
                "Altman_Z": 3.0,
                "MarketCap": 2_000_000_000,
                "Beta": 0.80,
            },
        )
        result = apply_filters(df, self.PRESET["filters"], pea_only=True)
        assert "NODIV" not in result.index

    def test_market_cap_floor_1b(self):
        """MarketCap < €1B must be excluded (LT_PEA_DEFENSIVE raises floor to €1B)."""
        df = _build_30_rows(
            "SMALL_EU",
            {
                "PEA": True,
                "MarketCap": 400_000_000,
                "data_completeness": 0.85,
                "Piotroski_F": 8,
                "Altman_Z": 3.0,
                "Beta": 0.80,
                "DivYield": 0.025,
            },
        )
        result = apply_filters(df, self.PRESET["filters"], pea_only=True)
        assert "SMALL_EU" not in result.index

    def test_perfect_pea_defensive_passes(self):
        df = _build_30_rows(
            "PERFECT_PEA",
            {
                "PEA": True,
                "Beta": 0.70,
                "DivYield": 0.03,
                "PayoutRatio": 0.50,
                "MarketCap": 2_000_000_000,
                "data_completeness": 0.85,
                "Piotroski_F": 8,
                "Altman_Z": 3.2,
                "InterestCoverage": 9.0,
                "FCFMargin": 0.12,
                "ROIC": 0.15,
            },
        )
        result = apply_filters(df, self.PRESET["filters"], pea_only=True)
        assert "PERFECT_PEA" in result.index


# ──────────────────────────────────────────────────────────────────────────────
# LT_DEEP_VALUE
# ──────────────────────────────────────────────────────────────────────────────


class TestLTDeepValue:
    PRESET = LT_DEEP_VALUE

    def test_deep_value_edge_case_f_score_6(self):
        """F-Score = 5 must be excluded; F-Score = 6 must pass."""
        # EV_EBITDA=6 -> derived EV_EBIT = 6*(200/160) = 7.5 < 9 (max_ev_ebit gate)
        _dv_extras = {
            "Altman_Z": 2.0,
            "Valuation_Score": 20.0,
            "PB": 1.2,
            "DCF_MoS_Mid": 0.35,
            "EV_EBITDA": 6.0,  # derived EV_EBIT = 7.5 < 9
        }
        df_pass = _build_30_rows("F6", {"Piotroski_F": 6, **_dv_extras})
        df_fail = _build_30_rows("F5", {"Piotroski_F": 5, **_dv_extras})
        result_pass = apply_filters(df_pass, self.PRESET["filters"])
        result_fail = apply_filters(df_fail, self.PRESET["filters"])
        assert "F6" in result_pass.index
        assert "F5" not in result_fail.index

    def test_altman_z_floor_1_8(self):
        """Altman Z = 1.5 must be excluded; Altman Z = 2.0 must pass."""
        # EV_EBITDA=6 -> derived EV_EBIT = 7.5 < 9 (max_ev_ebit gate)
        _dv_extras = {"Piotroski_F": 6, "Valuation_Score": 20.0, "PB": 1.2, "DCF_MoS_Mid": 0.35, "EV_EBITDA": 6.0}
        df_pass = _build_30_rows("Z20", {"Altman_Z": 2.0, **_dv_extras})
        df_fail = _build_30_rows("Z15", {"Altman_Z": 1.5, **_dv_extras})
        result_pass = apply_filters(df_pass, self.PRESET["filters"])
        result_fail = apply_filters(df_fail, self.PRESET["filters"])
        assert "Z20" in result_pass.index
        assert "Z15" not in result_fail.index

    def test_expensive_on_pb_excluded(self):
        """PB > 1.5 must be excluded."""
        df = _build_30_rows(
            "EXP_PB",
            {
                "PB": 2.5,
                "Piotroski_F": 6,
                "Altman_Z": 2.0,
                "Valuation_Score": 20.0,
                "DCF_MoS_Mid": 0.35,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "EXP_PB" not in result.index

    def test_insufficient_dcf_mos_excluded(self):
        """DCF_MoS_Mid < 0.30 must be excluded (deep value requires 30% margin)."""
        df = _build_30_rows(
            "LOWMOS",
            {
                "DCF_MoS_Mid": 0.10,
                "Piotroski_F": 6,
                "Altman_Z": 2.0,
                "PB": 1.2,
                "Valuation_Score": 20.0,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "LOWMOS" not in result.index


# ──────────────────────────────────────────────────────────────────────────────
# MT_GARP
# ──────────────────────────────────────────────────────────────────────────────


class TestMTGARP:
    PRESET = MT_GARP

    def test_perfect_garp_passes(self):
        df = _build_30_rows(
            "GARP_OK",
            {
                "EPS_Rev_90d": 0.05,  # min_eps_revision_3m = 0.0
                "EPS_Rev_180d": 0.03,  # min_eps_revision_6m = 0.02
                "RS_3m": 0.06,  # min_relative_strength_3m_vs_index = 0.0
                "Above_200DMA": True,
                "ROIC": 0.12,
                "Piotroski_F": 7,
                "Altman_Z": 2.5,
                "score_mt": 70.0,
                "passes_gates_mt": True,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "GARP_OK" in result.index

    def test_negative_eps_revision_excluded(self):
        """Negative 3m EPS revision must exclude the name."""
        df = _build_30_rows(
            "NEG_REV",
            {
                "EPS_Rev_90d": -0.05,
                "Altman_Z": 2.5,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "NEG_REV" not in result.index

    def test_below_200dma_excluded(self):
        """Price below 200dma must exclude the name."""
        df = _build_30_rows("BELOW200", {"Above_200DMA": False})
        result = apply_filters(df, self.PRESET["filters"])
        assert "BELOW200" not in result.index

    def test_negative_rs_3m_excluded(self):
        """Negative 3m relative strength must exclude the name."""
        df = _build_30_rows("NEG_RS", {"RS_3m": -0.05})
        result = apply_filters(df, self.PRESET["filters"])
        assert "NEG_RS" not in result.index

    def test_distressed_altman_excluded(self):
        """Altman Z < 2.0 must be excluded (MT_GARP floor)."""
        df = _build_30_rows("LOW_Z_MT", {"Altman_Z": 1.8})
        result = apply_filters(df, self.PRESET["filters"])
        assert "LOW_Z_MT" not in result.index


# ──────────────────────────────────────────────────────────────────────────────
# MT_TURNAROUND
# ──────────────────────────────────────────────────────────────────────────────


class TestMTTurnaround:
    PRESET = MT_TURNAROUND

    def test_documented_gap_opmargin_improvement(self):
        """min_op_margin_improvement_yoy is in requires list — column absent should not crash."""
        df = _build_30_rows(
            "TURN_OK",
            {
                "Altman_Z": 1.6,
                "FCF": 50_000_000,  # positive_fcf_latest_year
                "Cash": 200_000_000,  # positive_cash_balance
                "score_mt": 60.0,
            },
        )
        # Ensure OpMarginImprovement_YoY is absent (it should be by default)
        assert "OpMarginImprovement_YoY" not in df.columns
        # Should not crash; filters that depend on missing columns are skipped
        result = apply_filters(df, self.PRESET["filters"])
        assert isinstance(result, pd.DataFrame)
        assert "TURN_OK" in result.index

    def test_negative_fcf_excluded(self):
        """positive_fcf_latest_year=True means FCF ≤ 0 is excluded."""
        df = _build_30_rows(
            "NEG_FCF_TURN",
            {
                "FCF": -10_000_000,  # burning cash
                "Altman_Z": 1.6,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "NEG_FCF_TURN" not in result.index

    def test_negative_cash_excluded(self):
        """positive_cash_balance=True means Cash ≤ 0 is excluded."""
        df = _build_30_rows(
            "NO_CASH_TURN",
            {
                "Cash": -5_000_000,
                "FCF": 30_000_000,
                "Altman_Z": 1.6,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "NO_CASH_TURN" not in result.index

    def test_distressed_excluded(self):
        """Altman Z < 1.5 must be excluded (survivability floor)."""
        df = _build_30_rows(
            "BANKRUPT_TURN",
            {
                "Altman_Z": 1.0,
                "FCF": 30_000_000,
                "Cash": 100_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "BANKRUPT_TURN" not in result.index


# ──────────────────────────────────────────────────────────────────────────────
# MT_INCOME
# ──────────────────────────────────────────────────────────────────────────────


class TestMTIncome:
    PRESET = MT_INCOME

    def test_perfect_income_passes(self):
        df = _build_30_rows(
            "INCOME_OK",
            {
                "DivYield": 0.04,
                "PayoutRatio": 0.55,
                "Piotroski_F": 7,
                "Altman_Z": 2.5,
                "score_mt": 60.0,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "INCOME_OK" in result.index

    def test_low_yield_excluded(self):
        """DivYield < 3.5% must be excluded."""
        df = _build_30_rows(
            "LOWDIV",
            {
                "DivYield": 0.02,  # below 3.5% threshold
                "PayoutRatio": 0.50,
                "Piotroski_F": 7,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "LOWDIV" not in result.index

    def test_high_payout_excluded(self):
        """PayoutRatio > 0.75 must be excluded (unsustainable dividend)."""
        df = _build_30_rows(
            "HIGH_PAYOUT",
            {
                "DivYield": 0.05,
                "PayoutRatio": 0.90,
                "Piotroski_F": 7,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "HIGH_PAYOUT" not in result.index

    def test_weak_f_score_excluded(self):
        """F-Score < 6 must be excluded."""
        df = _build_30_rows(
            "LOW_F_INC",
            {
                "DivYield": 0.04,
                "PayoutRatio": 0.50,
                "Piotroski_F": 4,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "LOW_F_INC" not in result.index

    def test_nan_optional_columns_pass(self):
        """Columns not plumbed (DivGrowth_5y_CAGR etc.) should not block the row."""
        df = _build_30_rows(
            "DIV_NAN_COLS",
            {
                "DivYield": 0.04,
                "PayoutRatio": 0.55,
                "Piotroski_F": 7,
                "Altman_Z": 2.5,
            },
        )
        for col in ("DivGrowth_5y_CAGR", "FCF_DivCoverage", "ConsecutiveDivYears"):
            assert col not in df.columns or df[col].isna().all()
        result = apply_filters(df, self.PRESET["filters"])
        assert "DIV_NAN_COLS" in result.index


# ──────────────────────────────────────────────────────────────────────────────
# ST_MOMENTUM_QUALITY
# ──────────────────────────────────────────────────────────────────────────────


class TestSTMomentumQuality:
    PRESET = ST_MOMENTUM_QUALITY

    def test_cto_flag(self):
        assert self.PRESET["recommended_account"] == "CTO"
        assert self.PRESET["pea_warning"] is True

    def test_perfect_momentum_passes(self):
        df = _build_30_rows(
            "MOM_OK",
            {
                "MarketCap": 1_000_000_000,
                "AvgVolume": 3_000_000,
                "Above_50DMA": True,
                "Above_200DMA": True,
                "Golden_Cross": True,
                "Volume_Surge": 1.5,
                "SUE": 1.2,
                "EPS_Rev_90d": 0.02,
                "Sentiment_Score": 0.1,
                "Altman_Z": 2.0,
                "Piotroski_F": 6,
                "Beta": 1.2,
                "score_st": 55.0,
                "passes_gates_st": True,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "MOM_OK" in result.index

    def test_below_50dma_excluded(self):
        """Price below 50dma must be excluded."""
        df = _build_30_rows(
            "BELOW50",
            {
                "Above_50DMA": False,
                "Above_200DMA": True,
                "MarketCap": 1_000_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "BELOW50" not in result.index

    def test_no_golden_cross_excluded(self):
        """Without golden cross (MA50 < MA200) must be excluded."""
        df = _build_30_rows(
            "NO_GX",
            {
                "Golden_Cross": False,
                "Above_50DMA": True,
                "Above_200DMA": True,
                "MarketCap": 1_000_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "NO_GX" not in result.index

    def test_high_beta_excluded(self):
        """Beta > 1.8 must be excluded."""
        df = _build_30_rows(
            "HYPERVOL",
            {
                "Beta": 2.1,
                "MarketCap": 1_000_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "HYPERVOL" not in result.index

    def test_small_cap_excluded(self):
        """MarketCap < €500M must be excluded (ST raises the floor)."""
        df = _build_30_rows(
            "TINYCO",
            {
                "MarketCap": 200_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "TINYCO" not in result.index


# ──────────────────────────────────────────────────────────────────────────────
# ST_EARNINGS_DRIFT
# ──────────────────────────────────────────────────────────────────────────────


class TestSTEarningsDrift:
    PRESET = ST_EARNINGS_DRIFT

    def test_cto_flag(self):
        assert self.PRESET["recommended_account"] == "CTO"
        assert self.PRESET["pea_warning"] is True

    def test_strong_sue_passes(self):
        df = _build_30_rows(
            "PEAD_OK",
            {
                "SUE": 2.0,
                "Volume_Surge": 2.5,
                "EPS_Rev_90d": 0.03,
                "Sentiment_Score": 0.1,
                "MarketCap": 1_000_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "PEAD_OK" in result.index

    def test_weak_sue_excluded(self):
        """SUE < 1.5 must be excluded."""
        df = _build_30_rows("WEAK_BEAT", {"SUE": 0.8})
        result = apply_filters(df, self.PRESET["filters"])
        assert "WEAK_BEAT" not in result.index

    def test_low_volume_surge_excluded(self):
        """Volume surge < 2.0 must be excluded (requires strong confirmation)."""
        df = _build_30_rows("LOW_VOL_DRIFT", {"Volume_Surge": 1.2, "SUE": 2.0})
        result = apply_filters(df, self.PRESET["filters"])
        assert "LOW_VOL_DRIFT" not in result.index

    def test_documented_gap_columns_absent(self):
        """EarningsAnnouncement_Within5d not yet plumbed — should not crash."""
        df = _build_30_rows("DRIFT_MIN", {"SUE": 2.0, "Volume_Surge": 2.5})
        assert "EarningsAnnouncement_Within5d" not in df.columns
        result = apply_filters(df, self.PRESET["filters"])
        assert isinstance(result, pd.DataFrame)


# ──────────────────────────────────────────────────────────────────────────────
# ST_OVERSOLD_BOUNCE
# ──────────────────────────────────────────────────────────────────────────────


class TestSTOversoldBounce:
    PRESET = ST_OVERSOLD_BOUNCE

    def test_cto_flag(self):
        assert self.PRESET["recommended_account"] == "CTO"
        assert self.PRESET["pea_warning"] is True

    def test_above_200dma_required(self):
        """Price below 200dma must be excluded (only trade in uptrends)."""
        df = _build_30_rows("BELOW200_MEAN_REV", {"Above_200DMA": False})
        result = apply_filters(df, self.PRESET["filters"])
        assert "BELOW200_MEAN_REV" not in result.index

    def test_perfect_oversold_passes(self):
        df = _build_30_rows(
            "OVERSOLD_OK",
            {
                "Above_200DMA": True,
                "Sentiment_Score": 0.0,
                "Altman_Z": 2.0,
                "MarketCap": 1_000_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "OVERSOLD_OK" in result.index

    def test_distressed_excluded(self):
        """Altman Z < 1.5 must be excluded."""
        df = _build_30_rows(
            "DISTRESS_OB",
            {
                "Altman_Z": 0.8,
                "Above_200DMA": True,
                "MarketCap": 1_000_000_000,
            },
        )
        result = apply_filters(df, self.PRESET["filters"])
        assert "DISTRESS_OB" not in result.index

    def test_rsi2_gap_documented(self):
        """RSI_2 < 10 is the primary entry trigger but RSI_2 column is not yet plumbed."""
        assert "requires" in self.PRESET
        assert "RSI_2" in self.PRESET["requires"]
        # Column absent -> filter skipped, no crash
        df = _build_30_rows(
            "OVERSOLD_NO_RSI",
            {
                "Above_200DMA": True,
                "Altman_Z": 2.0,
                "MarketCap": 1_000_000_000,
            },
        )
        assert "RSI_2" not in df.columns
        result = apply_filters(df, self.PRESET["filters"])
        assert isinstance(result, pd.DataFrame)


# ──────────────────────────────────────────────────────────────────────────────
# screen_horizon_preset integration tests
# ──────────────────────────────────────────────────────────────────────────────


class TestScreenHorizonPreset:
    """Integration tests for the screen_horizon_preset convenience helper."""

    def test_returns_dataframe(self):
        df = _build_30_rows(
            "COMPOUNDER",
            {
                "Piotroski_F": 8,
                "Altman_Z": 3.0,
                "data_completeness": 0.85,
            },
        )
        result = screen_horizon_preset(df, "LT_QUALITY_COMPOUNDER")
        assert isinstance(result, pd.DataFrame)

    def test_sorted_by_score_lt(self):
        """Result should be sorted descending by score_lt."""
        rows = [
            _row(
                Ticker="A_HIGH",
                score_lt=80.0,
                passes_gates_lt=True,
                Piotroski_F=8,
                Altman_Z=3.0,
                data_completeness=0.85,
            ),
            _row(
                Ticker="B_MED", score_lt=65.0, passes_gates_lt=True, Piotroski_F=8, Altman_Z=3.0, data_completeness=0.85
            ),
            _row(
                Ticker="C_LOW", score_lt=50.0, passes_gates_lt=True, Piotroski_F=8, Altman_Z=3.0, data_completeness=0.85
            ),
        ]
        df = _make_universe(rows)
        result = screen_horizon_preset(df, "LT_QUALITY_COMPOUNDER")
        if len(result) >= 2:
            scores = result["score_lt"].tolist()
            assert scores == sorted(scores, reverse=True)

    def test_passes_gates_filter_applied(self):
        """Rows with passes_gates_lt=False should be excluded."""
        rows = [
            _row(
                Ticker="GATE_PASS",
                passes_gates_lt=True,
                score_lt=75.0,
                Piotroski_F=8,
                Altman_Z=3.0,
                data_completeness=0.85,
            ),
            _row(
                Ticker="GATE_FAIL",
                passes_gates_lt=False,
                score_lt=75.0,
                Piotroski_F=8,
                Altman_Z=3.0,
                data_completeness=0.85,
            ),
        ]
        df = _make_universe(rows)
        result = screen_horizon_preset(df, "LT_QUALITY_COMPOUNDER")
        assert "GATE_FAIL" not in result.index

    def test_st_preset_sorted_by_score_st(self):
        rows = [
            _row(
                Ticker="ST_A",
                score_st=70.0,
                passes_gates_st=True,
                MarketCap=1_000_000_000,
                Above_50DMA=True,
                Above_200DMA=True,
                Golden_Cross=True,
                Volume_Surge=1.5,
                SUE=1.2,
            ),
            _row(
                Ticker="ST_B",
                score_st=55.0,
                passes_gates_st=True,
                MarketCap=1_000_000_000,
                Above_50DMA=True,
                Above_200DMA=True,
                Golden_Cross=True,
                Volume_Surge=1.5,
                SUE=1.2,
            ),
        ]
        df = _make_universe(rows)
        result = screen_horizon_preset(df, "ST_MOMENTUM_QUALITY")
        if len(result) >= 2:
            scores = result["score_st"].tolist()
            assert scores == sorted(scores, reverse=True)

    def test_unknown_preset_raises(self):
        df = _make_universe([_base_row()])
        with pytest.raises(KeyError):
            screen_horizon_preset(df, "DOES_NOT_EXIST")

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame()
        # apply_filters on an empty df; screen_horizon_preset should handle it
        result = screen_horizon_preset(df, "MT_INCOME")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_mt_preset_sorted_by_score_mt(self):
        rows = [
            _row(Ticker="MT_HIGH", score_mt=72.0, passes_gates_mt=True, DivYield=0.04, PayoutRatio=0.55, Piotroski_F=7),
            _row(Ticker="MT_LOW", score_mt=56.0, passes_gates_mt=True, DivYield=0.04, PayoutRatio=0.55, Piotroski_F=7),
        ]
        df = _make_universe(rows)
        result = screen_horizon_preset(df, "MT_INCOME")
        if len(result) >= 2:
            scores = result["score_mt"].tolist()
            assert scores == sorted(scores, reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# apply_filters backward-compatibility smoke test
# ──────────────────────────────────────────────────────────────────────────────


class TestApplyFiltersBackwardCompat:
    """Verify legacy filter sets still work after M8 changes."""

    def test_default_filters_still_work(self):
        from src.strategy.screener import DEFAULT_FILTERS

        rows = [
            _row(Ticker="OK", PE=18.0, ROE=0.10, Composite_Score=60.0),
            _row(Ticker="HIGH_PE", PE=30.0, ROE=0.10, Composite_Score=60.0),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, DEFAULT_FILTERS)
        assert "OK" in result.index
        assert "HIGH_PE" not in result.index

    def test_quality_growth_filters_still_work(self):
        from src.strategy.screener import QUALITY_GROWTH_FILTERS

        rows = [
            _row(
                Ticker="QUALITY",
                ROE=0.20,
                OperatingMargin=0.15,
                RevenueGrowth=0.10,
                Composite_Score=70.0,
                MarketCap=600_000_000,
            ),
            _row(
                Ticker="LOWROE",
                ROE=0.05,
                OperatingMargin=0.15,
                RevenueGrowth=0.10,
                Composite_Score=70.0,
                MarketCap=600_000_000,
            ),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, QUALITY_GROWTH_FILTERS)
        assert "QUALITY" in result.index
        assert "LOWROE" not in result.index

    def test_dividend_filters_still_work(self):
        from src.strategy.screener import DIVIDEND_INCOME_FILTERS

        rows = [
            _row(
                Ticker="DIV",
                DivYield=0.04,
                PayoutRatio=0.60,
                InterestCoverage=5.0,
                MarketCap=2_000_000_000,
                Composite_Score=55.0,
            ),
            _row(
                Ticker="NO_DIV",
                DivYield=0.01,
                PayoutRatio=0.60,
                InterestCoverage=5.0,
                MarketCap=2_000_000_000,
                Composite_Score=55.0,
            ),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, DIVIDEND_INCOME_FILTERS)
        assert "DIV" in result.index
        assert "NO_DIV" not in result.index

    def test_pea_only_flag(self):
        from src.strategy.screener import VALUE_FILTERS

        rows = [
            _row(Ticker="EU", PEA=True, PE=12.0, ROE=0.08, Composite_Score=55.0),
            _row(Ticker="US", PEA=False, PE=12.0, ROE=0.08, Composite_Score=55.0),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, VALUE_FILTERS, pea_only=True)
        assert "EU" in result.index
        assert "US" not in result.index


# ──────────────────────────────────────────────────────────────────────────────
# Universal pre-filter tests
# ──────────────────────────────────────────────────────────────────────────────


class TestUniversalPreFilters:
    """Verify the universal pre-filter logic added in M8."""

    def _minimal_filters(self) -> dict[str, Any]:
        return {
            "min_market_cap": 100_000_000,
            "min_years_listed": 3,
            "not_in_distress": True,
            "min_data_completeness": 0.70,
            "exclude_sectors": ["Tobacco", "Gambling"],
        }

    def test_not_in_distress_applied(self):
        rows = [
            _row(Ticker="SAFE", Altman_Z=2.0),
            _row(Ticker="DISTRESS", Altman_Z=0.5),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, self._minimal_filters())
        assert "SAFE" in result.index
        assert "DISTRESS" not in result.index

    def test_exclude_sectors_applied(self):
        rows = [
            _row(Ticker="TECH", Sector="Technology"),
            _row(Ticker="SMOKES", Sector="Tobacco"),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, self._minimal_filters())
        assert "TECH" in result.index
        assert "SMOKES" not in result.index

    def test_data_completeness_applied(self):
        rows = [
            _row(Ticker="COMPLETE", data_completeness=0.85),
            _row(Ticker="SPARSE", data_completeness=0.50),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, self._minimal_filters())
        assert "COMPLETE" in result.index
        assert "SPARSE" not in result.index

    def test_years_listed_applied(self):
        rows = [
            _row(Ticker="OLD", YearsListed=7.0),
            _row(Ticker="NEW_IPO", YearsListed=1.0),
        ]
        df = _make_universe(rows)
        result = apply_filters(df, self._minimal_filters())
        assert "OLD" in result.index
        assert "NEW_IPO" not in result.index

    def test_nan_passes_universal_filters(self):
        """NaN values in any pre-filter column must not block the row."""
        rows = [_row(Ticker="NAN_ROW", Altman_Z=float("nan"), data_completeness=float("nan"), YearsListed=float("nan"))]
        df = _make_universe(rows)
        result = apply_filters(df, self._minimal_filters())
        assert "NAN_ROW" in result.index
