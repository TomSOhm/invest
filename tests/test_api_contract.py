"""
Invest Solo -- M10 API Contract Tests
======================================
Validates that the new three-horizon Pydantic schemas accept and correctly
parse realistic fixture dicts. These are pure model-validation tests —
no HTTP server, no yfinance, no network IO.

Test coverage:
  - HorizonScoring, DCFValuation, QualitySignals, RiskSignals, MomentumSignals,
    SubScores (horizons.py)
  - CompanyDetail (company.py): three horizons always present
  - ScreenerResultItem (screener.py): score_lt always present
  - ScreenerResponse (screener.py): summary.horizon tracks horizon
  - PortfolioPosition / PortfolioResponse (portfolio.py): score_lt/signal_lt
  - WatchlistItem / WatchlistResponse (watchlist.py): score_lt/signal_lt
  - Horizon toggle: medium_term and short_term scores parse correctly
  - ST preset: recommended_account field accepted on HorizonScoring
  - PRESET_REGISTRY read-only: KeyError raised for unknown preset names
  - legacy fields ABSENT: composite_score / signal NOT present on models
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.models.company import CompanyDetail

# ── models under test ──────────────────────────────────────────────────────
from backend.app.models.horizons import (
    DCFValuation,
    HorizonScoring,
    QualitySignals,
    SubScores,
)
from backend.app.models.portfolio import (
    PortfolioPosition,
    PortfolioResponse,
    PortfolioSummary,
)
from backend.app.models.screener import (
    ScreenerRequest,
    ScreenerResponse,
    ScreenerResultItem,
    ScreenerSummary,
)
from backend.app.models.watchlist import WatchlistItem, WatchlistResponse

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixture builders
# ──────────────────────────────────────────────────────────────────────────────


def _horizon_scoring_dict(
    score: float = 72.5,
    signal: str = "Buy",
    passes_gates: bool = True,
    recommended_account: Any = None,
) -> dict[str, Any]:
    return {
        "score": score,
        "signal": signal,
        "passes_gates": passes_gates,
        "blockers": [],
        "recommended_account": recommended_account,
    }


def _three_horizons_dict() -> dict[str, Any]:
    return {
        "long_term": _horizon_scoring_dict(72.5, "Buy", True, None),
        "medium_term": _horizon_scoring_dict(65.0, "Hold", True, None),
        "short_term": _horizon_scoring_dict(55.0, "Hold", False, "CTO"),
    }


def _dcf_dict() -> dict[str, Any]:
    return {
        "fair_value_low": 120.0,
        "fair_value_mid": 145.0,
        "fair_value_high": 175.0,
        "mos_low": -0.12,
        "mos_mid": 0.05,
        "mos_high": 0.24,
        "wacc_used": 0.082,
        "warnings": [],
    }


def _quality_dict() -> dict[str, Any]:
    return {
        "piotroski_f": 7,
        "altman_z": 3.45,
        "altman_zone": "Safe",
        "graham_number": 138.5,
        "graham_mos": 12.4,
        "earnings_quality_score": 68.0,
        "moat_score": 74.0,
        "m_score": None,
        "sloan_accruals": None,
        "cash_conversion_ratio_5y": None,
    }


def _risk_dict() -> dict[str, Any]:
    return {
        "risk_score": 61.0,
        "realized_vol_1y": 0.22,
        "max_drawdown_3y": -0.35,
        "net_debt_ebitda": 1.8,
        "interest_coverage": 8.2,
        "beta": 0.95,
    }


def _momentum_dict() -> dict[str, Any]:
    return {
        "momentum_12_1": 0.18,
        "rs_3m": 0.05,
        "above_50dma": True,
        "above_200dma": True,
        "golden_cross": True,
        "volume_surge": 1.15,
        "eps_revision_30d": 0.02,
        "eps_revision_90d": 0.04,
        "sue_z_score": 1.2,
        "sentiment_30d": 0.3,
        "sentiment_trend": 0.1,
    }


def _sub_scores_dict() -> dict[str, Any]:
    return {
        "valuation": 62.0,
        "health": 78.0,
        "profitability": 71.0,
        "growth": 55.0,
        "shareholder": 48.0,
        "risk_legacy": 59.0,
    }


def _metrics_dict(ticker: str = "MC.PA") -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": "LVMH Moet Hennessy Louis Vuitton SE",
        "sector": "Consumer Discretionary",
        "industry": "Textiles, Apparel & Luxury Goods",
        "country": "France",
        "exchange": "PAR",
        "price": 730.0,
        "market_cap": 365_000_000_000.0,
        "enterprise_value": 380_000_000_000.0,
        "pe": 24.5,
        "forward_pe": 21.0,
        "pb": 5.2,
        "ps": 3.1,
        "pfcf": 22.0,
        "ev_ebitda": 14.5,
        "ev_sales": 3.4,
        "peg": 1.1,
        "gross_margin": 0.682,
        "operating_margin": 0.275,
        "net_margin": 0.178,
        "fcf_margin": 0.115,
        "roe": 0.21,
        "roa": 0.09,
        "roic": 0.14,
        "revenue_growth": 0.09,
        "current_ratio": 1.3,
        "debt_equity": 0.45,
        "interest_coverage": 14.2,
        "div_yield": 0.022,
        "payout_ratio": 0.48,
        "beta": 1.05,
        "fifty_two_week_high": 780.0,
        "fifty_two_week_low": 605.0,
        "fifty_two_week_high_pct": -6.4,
        "insider_pct": None,
        "institutional_pct": None,
        "short_pct_float": None,
        "earnings_surprise_pct": None,
    }


def _full_company_detail_dict(ticker: str = "MC.PA") -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": "LVMH Moet Hennessy Louis Vuitton SE",
        "sector": "Consumer Discretionary",
        "industry": "Textiles, Apparel & Luxury Goods",
        "country": "France",
        "exchange": "PAR",
        "pea_eligible": True,
        "pea_pme_eligible": False,
        "price": 730.0,
        "market_cap": 365_000_000_000.0,
        "horizons": _three_horizons_dict(),
        "sub_scores": _sub_scores_dict(),
        "valuation": _dcf_dict(),
        "quality": _quality_dict(),
        "risk": _risk_dict(),
        "momentum": _momentum_dict(),
        "metrics": _metrics_dict(ticker),
        "analyst_ratings": None,
        "data_completeness": 0.87,
        "data_source": "yfinance",
        "last_updated": "2026-05-08T12:00:00+00:00",
    }


def _screener_result_item_dict(ticker: str = "MC.PA") -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": "LVMH",
        "sector": "Consumer Discretionary",
        "pea_eligible": True,
        "score_lt": 72.5,
        "score_mt": 65.0,
        "score_st": 55.0,
        "signal_lt": "Buy",
        "signal_mt": "Hold",
        "signal_st": "Hold",
        "passes_gates_lt": True,
        "passes_gates_mt": True,
        "passes_gates_st": False,
        "pe": 24.5,
        "pb": 5.2,
        "roe": 0.21,
        "div_yield": 0.022,
        "revenue_growth": 0.09,
        "market_cap": 365_000_000_000.0,
        "altman_z": 3.45,
        "piotroski_f": 7,
        "dcf_mos_mid": 0.05,
        "recommended_account": None,
        "blockers": [],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tests: horizons.py sub-models
# ──────────────────────────────────────────────────────────────────────────────


class TestHorizonScoring:
    def test_valid_buy_signal(self) -> None:
        h = HorizonScoring(**_horizon_scoring_dict())
        assert h.score == 72.5
        assert h.signal == "Buy"
        assert h.passes_gates is True
        assert h.blockers == []
        assert h.recommended_account is None

    def test_st_cto_recommended_account(self) -> None:
        h = HorizonScoring(**_horizon_scoring_dict(recommended_account="CTO"))
        assert h.recommended_account == "CTO"

    def test_pea_recommended_account(self) -> None:
        h = HorizonScoring(**_horizon_scoring_dict(recommended_account="PEA"))
        assert h.recommended_account == "PEA"

    def test_invalid_signal_raises(self) -> None:
        with pytest.raises(ValidationError):
            HorizonScoring(**_horizon_scoring_dict(signal="Neutral"))

    def test_invalid_recommended_account_raises(self) -> None:
        with pytest.raises(ValidationError):
            HorizonScoring(**_horizon_scoring_dict(recommended_account="ISA"))

    def test_blockers_populated(self) -> None:
        d = _horizon_scoring_dict(passes_gates=False)
        d["blockers"] = ["min_data_completeness", "min_altman_z"]
        h = HorizonScoring(**d)
        assert h.passes_gates is False
        assert len(h.blockers) == 2

    def test_all_five_signals_accepted(self) -> None:
        for sig in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"):
            h = HorizonScoring(**_horizon_scoring_dict(signal=sig))
            assert h.signal == sig


class TestDCFValuation:
    def test_all_fields_present(self) -> None:
        dcf = DCFValuation(**_dcf_dict())
        assert dcf.fair_value_mid == 145.0
        assert dcf.mos_mid == 0.05
        assert dcf.wacc_used == 0.082
        assert dcf.warnings == []

    def test_all_fields_optional(self) -> None:
        dcf = DCFValuation()
        assert dcf.fair_value_mid is None
        assert dcf.warnings == []

    def test_warnings_list(self) -> None:
        d = _dcf_dict()
        d["warnings"] = ["missing_fcf", "negative_growth"]
        dcf = DCFValuation(**d)
        assert len(dcf.warnings) == 2


class TestQualitySignals:
    def test_valid_quality(self) -> None:
        q = QualitySignals(**_quality_dict())
        assert q.piotroski_f == 7
        assert q.altman_zone == "Safe"

    def test_all_optional(self) -> None:
        q = QualitySignals()
        assert q.piotroski_f is None
        assert q.altman_zone is None

    def test_invalid_altman_zone(self) -> None:
        d = _quality_dict()
        d["altman_zone"] = "Unknown"
        with pytest.raises(ValidationError):
            QualitySignals(**d)


class TestSubScores:
    def test_all_required(self) -> None:
        ss = SubScores(**_sub_scores_dict())
        assert ss.valuation == 62.0
        assert ss.risk_legacy == 59.0

    def test_missing_required_raises(self) -> None:
        d = _sub_scores_dict()
        del d["valuation"]
        with pytest.raises(ValidationError):
            SubScores(**d)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: company.py
# ──────────────────────────────────────────────────────────────────────────────


class TestCompanyDetail:
    def test_valid_full_detail(self) -> None:
        cd = CompanyDetail(**_full_company_detail_dict())
        assert cd.ticker == "MC.PA"
        assert "long_term" in cd.horizons
        assert "medium_term" in cd.horizons
        assert "short_term" in cd.horizons
        assert cd.horizons["long_term"].score == 72.5
        assert cd.data_completeness == 0.87

    def test_score_lt_always_present(self) -> None:
        """LT horizon is always present in the horizons dict."""
        cd = CompanyDetail(**_full_company_detail_dict())
        lt = cd.horizons["long_term"]
        assert lt.score is not None
        assert lt.signal in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")

    def test_st_preset_recommended_account(self) -> None:
        d = _full_company_detail_dict()
        d["horizons"]["short_term"]["recommended_account"] = "CTO"
        cd = CompanyDetail(**d)
        assert cd.horizons["short_term"].recommended_account == "CTO"

    def test_no_legacy_composite_score_field(self) -> None:
        """The CompanyDetail model must NOT have a composite_score field."""
        assert not hasattr(CompanyDetail, "composite_score")
        # Also check model fields
        field_names = set(CompanyDetail.model_fields.keys())
        assert "composite_score" not in field_names
        assert "signal" not in field_names

    def test_three_horizon_keys(self) -> None:
        cd = CompanyDetail(**_full_company_detail_dict())
        assert set(cd.horizons.keys()) == {"long_term", "medium_term", "short_term"}

    def test_pea_eligible_flag(self) -> None:
        cd = CompanyDetail(**_full_company_detail_dict())
        assert cd.pea_eligible is True

    def test_dcf_block_present(self) -> None:
        cd = CompanyDetail(**_full_company_detail_dict())
        assert cd.valuation.fair_value_mid == 145.0

    def test_quality_block_present(self) -> None:
        cd = CompanyDetail(**_full_company_detail_dict())
        assert cd.quality.piotroski_f == 7
        assert cd.quality.altman_zone == "Safe"

    def test_missing_horizons_raises(self) -> None:
        d = _full_company_detail_dict()
        del d["horizons"]
        with pytest.raises(ValidationError):
            CompanyDetail(**d)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: screener.py
# ──────────────────────────────────────────────────────────────────────────────


class TestScreenerResultItem:
    def test_valid_item(self) -> None:
        item = ScreenerResultItem(**_screener_result_item_dict())
        assert item.score_lt == 72.5
        assert item.signal_lt == "Buy"
        assert item.passes_gates_lt is True

    def test_score_lt_required(self) -> None:
        d = _screener_result_item_dict()
        del d["score_lt"]
        with pytest.raises(ValidationError):
            ScreenerResultItem(**d)

    def test_no_legacy_composite_score(self) -> None:
        field_names = set(ScreenerResultItem.model_fields.keys())
        assert "composite_score" not in field_names
        assert "signal" not in field_names

    def test_st_recommended_account(self) -> None:
        d = _screener_result_item_dict()
        d["recommended_account"] = "CTO"
        item = ScreenerResultItem(**d)
        assert item.recommended_account == "CTO"


class TestScreenerResponse:
    def test_valid_response(self) -> None:
        items = [_screener_result_item_dict("MC.PA"), _screener_result_item_dict("RMS.PA")]
        items[1]["score_lt"] = 68.0
        resp = ScreenerResponse(
            results=[ScreenerResultItem(**i) for i in items],
            summary=ScreenerSummary(
                total_passed=2,
                total_universe=31,
                avg_score=70.25,
                signal_distribution={"Buy": 2},
                horizon="long_term",
            ),
        )
        assert len(resp.results) == 2
        assert resp.summary.horizon == "long_term"

    def test_summary_horizon_tracks_request(self) -> None:
        """summary.horizon should reflect the horizon used in the screener run."""
        summary = ScreenerSummary(
            total_passed=5,
            total_universe=31,
            avg_score=62.0,
            signal_distribution={"Hold": 3, "Buy": 2},
            horizon="medium_term",
        )
        assert summary.horizon == "medium_term"

    def test_screener_request_defaults(self) -> None:
        req = ScreenerRequest()
        assert req.horizon == "long_term"
        assert req.limit == 50
        assert req.sort_by == "score"
        assert req.pea_only is False


# ──────────────────────────────────────────────────────────────────────────────
# Tests: portfolio.py
# ──────────────────────────────────────────────────────────────────────────────


def _portfolio_position_dict(ticker: str = "TTE.PA") -> dict[str, Any]:
    return {
        "id": "pos-001",
        "ticker": ticker,
        "name": "TotalEnergies SE",
        "sector": "Energy",
        "country": "France",
        "account_type": "pea",
        "quantity": 50.0,
        "buy_price": 55.0,
        "buy_date": "2024-01-15",
        "current_price": 60.0,
        "market_value": 3000.0,
        "cost_basis": 2750.0,
        "gain_loss": 250.0,
        "gain_loss_pct": 9.09,
        "weight_pct": 15.5,
        "pe": 8.5,
        "pb": 1.2,
        "ps": 0.5,
        "roe": 0.18,
        "roa": 0.07,
        "roic": 0.12,
        "operating_margin": 0.12,
        "net_margin": 0.08,
        "revenue_growth": 0.05,
        "div_yield": 0.045,
        # Three-horizon scoring
        "score_lt": 68.0,
        "score_mt": 61.0,
        "score_st": 52.0,
        "signal_lt": "Buy",
        "signal_mt": "Hold",
        "signal_st": "Hold",
        "piotroski_f": 6,
        "altman_z": 2.8,
        "graham_number": 62.0,
        "graham_mos": 3.3,
        "dcf_mos_mid": 0.08,
        "pea_eligible": True,
        "pea_pme_eligible": False,
        "analyst_rating": "Buy",
        "analyst_target_price": 65.0,
        "notes": None,
        "forward_pe": 7.9,
        "peg": None,
        "fifty_two_week_high_pct": -5.2,
    }


class TestPortfolioPosition:
    def test_valid_position(self) -> None:
        pos = PortfolioPosition(**_portfolio_position_dict())
        assert pos.score_lt == 68.0
        assert pos.signal_lt == "Buy"
        assert pos.score_mt == 61.0

    def test_no_legacy_composite_score(self) -> None:
        field_names = set(PortfolioPosition.model_fields.keys())
        assert "composite_score" not in field_names
        assert "signal" not in field_names

    def test_horizon_toggle(self) -> None:
        """score_lt / score_mt / score_st are independent fields."""
        pos = PortfolioPosition(**_portfolio_position_dict())
        # Simulate a medium-term view: score_mt should be different from score_lt
        assert pos.score_mt != pos.score_lt

    def test_dcf_mos_mid_present(self) -> None:
        pos = PortfolioPosition(**_portfolio_position_dict())
        assert pos.dcf_mos_mid == 0.08


class TestPortfolioResponse:
    def test_valid_response(self) -> None:
        resp = PortfolioResponse(
            positions=[PortfolioPosition(**_portfolio_position_dict())],
            summary=PortfolioSummary(
                total_value=3000.0,
                total_cost=2750.0,
                total_gain_loss=250.0,
                total_gain_loss_pct=9.09,
                position_count=1,
                avg_score_lt=68.0,
                sector_allocation={"Energy": 100.0},
                country_allocation={"France": 100.0},
                signal_distribution={"Buy": 1},
                pea_value=3000.0,
                cto_value=0.0,
            ),
            last_refreshed="2026-05-08T12:00:00+00:00",
            horizon="long_term",
        )
        assert resp.summary.avg_score_lt == 68.0
        assert resp.horizon == "long_term"

    def test_no_avg_composite_score_in_summary(self) -> None:
        field_names = set(PortfolioSummary.model_fields.keys())
        assert "avg_composite_score" not in field_names
        assert "avg_score_lt" in field_names

    def test_horizon_param_accepted(self) -> None:
        """PortfolioResponse carries the horizon used."""
        for h in ("long_term", "medium_term", "short_term"):
            resp = PortfolioResponse(
                positions=[],
                summary=PortfolioSummary(),
                last_refreshed="2026-05-08T12:00:00+00:00",
                horizon=h,
            )
            assert resp.horizon == h


# ──────────────────────────────────────────────────────────────────────────────
# Tests: watchlist.py
# ──────────────────────────────────────────────────────────────────────────────


def _watchlist_item_dict(ticker: str = "AIR.PA") -> dict[str, Any]:
    return {
        "id": "wl-001",
        "ticker": ticker,
        "name": "Airbus SE",
        "sector": "Industrials",
        "country": "France",
        "added_date": "2026-01-10",
        "notes": "Aerospace leader",
        "current_price": 165.0,
        "pe": 28.0,
        "pb": 8.5,
        "roe": 0.30,
        "score_lt": 74.0,
        "score_mt": 69.0,
        "score_st": 58.0,
        "signal_lt": "Buy",
        "signal_mt": "Buy",
        "signal_st": "Hold",
        "piotroski_f": 7,
        "altman_z": 3.1,
        "graham_number": 120.0,
        "graham_mos": -27.3,
        "dcf_mos_mid": -0.15,
        "pea_eligible": True,
        "pea_pme_eligible": False,
        "analyst_rating": "Buy",
        "analyst_target_price": 185.0,
        "forward_pe": 24.0,
        "peg": 1.4,
        "fifty_two_week_high_pct": -8.2,
    }


class TestWatchlistItem:
    def test_valid_item(self) -> None:
        item = WatchlistItem(**_watchlist_item_dict())
        assert item.score_lt == 74.0
        assert item.signal_lt == "Buy"
        assert item.dcf_mos_mid == -0.15

    def test_no_legacy_composite_score(self) -> None:
        field_names = set(WatchlistItem.model_fields.keys())
        assert "composite_score" not in field_names
        assert "signal" not in field_names

    def test_all_three_horizons_present(self) -> None:
        item = WatchlistItem(**_watchlist_item_dict())
        assert item.score_lt is not None
        assert item.score_mt is not None
        assert item.score_st is not None


class TestWatchlistResponse:
    def test_valid_response(self) -> None:
        resp = WatchlistResponse(
            items=[WatchlistItem(**_watchlist_item_dict())],
            last_refreshed="2026-05-08T12:00:00+00:00",
        )
        assert len(resp.items) == 1
        assert resp.items[0].ticker == "AIR.PA"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: PRESET_REGISTRY read-only
# ──────────────────────────────────────────────────────────────────────────────


class TestPresetRegistry:
    def test_known_preset_accessible(self) -> None:
        from src.strategy.horizon_presets import get_preset

        preset = get_preset("LT_QUALITY_COMPOUNDER")
        assert preset["horizon"] == "long_term"

    def test_unknown_preset_raises_key_error(self) -> None:
        from src.strategy.horizon_presets import get_preset

        with pytest.raises(KeyError):
            get_preset("NONEXISTENT_PRESET")

    def test_nine_presets_registered(self) -> None:
        from src.strategy.horizon_presets import PRESET_REGISTRY

        assert len(PRESET_REGISTRY) == 9

    def test_st_presets_have_recommended_account(self) -> None:
        from src.strategy.horizon_presets import PRESET_REGISTRY

        st_presets = [v for v in PRESET_REGISTRY.values() if v["horizon"] == "short_term"]
        assert len(st_presets) == 3
        for p in st_presets:
            assert p.get("recommended_account") == "CTO"

    def test_lt_presets_no_recommended_account(self) -> None:
        from src.strategy.horizon_presets import PRESET_REGISTRY

        lt_presets = [v for v in PRESET_REGISTRY.values() if v["horizon"] == "long_term"]
        for p in lt_presets:
            assert p.get("recommended_account", "") != "CTO"

    def test_list_presets_returns_9_entries(self) -> None:
        from src.strategy.horizon_presets import list_presets

        entries = list_presets()
        assert len(entries) == 9
        for e in entries:
            assert "name" in e
            assert "horizon" in e
            assert "description" in e


# ──────────────────────────────────────────────────────────────────────────────
# Tests: screener service preset routing
# ──────────────────────────────────────────────────────────────────────────────


class TestScreenerServicePreset:
    def test_unknown_preset_raises_key_error(self) -> None:
        import pandas as pd

        from backend.app.services.screener_service import ScreenerService

        svc = ScreenerService()
        with pytest.raises(KeyError):
            svc.run_preset(pd.DataFrame(), "FAKE_PRESET_DELETE_ME")

    def test_known_preset_does_not_raise_on_empty_df(self) -> None:
        """An empty DataFrame should return an empty result, not an exception."""
        import pandas as pd

        from backend.app.services.screener_service import ScreenerService

        svc = ScreenerService()
        # An empty df returns an empty filtered result without errors
        result = svc.run_preset(pd.DataFrame(), "LT_QUALITY_COMPOUNDER")
        assert result.empty


# ──────────────────────────────────────────────────────────────────────────────
# Tests: horizon query param toggle
# ──────────────────────────────────────────────────────────────────────────────


class TestHorizonToggle:
    def test_score_lt_is_default_sort_column(self) -> None:
        from backend.app.services.screener_service import _HORIZON_SCORE_COL

        assert _HORIZON_SCORE_COL["long_term"] == "score_lt"

    def test_horizon_col_mapping_complete(self) -> None:
        from backend.app.services.screener_service import _HORIZON_SCORE_COL

        assert set(_HORIZON_SCORE_COL.keys()) == {"long_term", "medium_term", "short_term"}
        assert _HORIZON_SCORE_COL["medium_term"] == "score_mt"
        assert _HORIZON_SCORE_COL["short_term"] == "score_st"

    def test_portfolio_summary_has_avg_score_lt(self) -> None:
        summary = PortfolioSummary(avg_score_lt=71.5)
        assert summary.avg_score_lt == 71.5

    def test_portfolio_summary_no_avg_composite_score(self) -> None:
        """Verify avg_composite_score (legacy) is NOT a field."""
        assert "avg_composite_score" not in PortfolioSummary.model_fields
