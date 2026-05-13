"""
Invest Solo -- Scoring Service (M10)
Thin wrapper around the existing src/analysis/scoring_engine.py module.

score_single now returns the three-horizon block in addition to the legacy
sub-scores. score_dataframe continues to delegate to score_universe unchanged
(the engine already emits score_lt/mt/st columns when settings.yaml has a
horizons: block).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.analysis.scoring_engine import (
    SCORING_WEIGHTS,
    SIGNAL_THRESHOLDS,
    altman_z_score,
    compute_composite_score,
    generate_signal,
    graham_number,
    piotroski_f_score,
    score_universe,
)


def _safe_float(value: Any) -> float | None:
    """Convert to float; return None for NaN / Inf / non-numeric."""
    if value is None:
        return None
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _altman_zone(z: float | None) -> str | None:
    """Map Altman Z-score to zone label (classic thresholds)."""
    if z is None:
        return None
    if z >= 2.99:
        return "Safe"
    if z >= 1.81:
        return "Grey"
    return "Distress"


class ScoringService:
    """Delegates scoring to the existing scoring_engine module."""

    def score_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Score an entire DataFrame of stocks.

        Expects a DataFrame indexed by Ticker with the standard column schema.
        Returns the same DataFrame with all scoring columns appended, including
        the M7 three-horizon columns (score_lt/mt/st, signal_lt/mt/st,
        passes_gates_lt/mt/st, blockers_lt/mt/st) when settings.yaml has a
        horizons: block — the engine handles this transparently.
        """
        if df.empty:
            logger.warning("score_dataframe called with empty DataFrame")
            return df
        logger.info(f"Scoring {len(df)} stocks")
        return score_universe(df)

    def score_single(self, row: pd.Series) -> dict[str, Any]:
        """
        Score a single stock (represented as a pandas Series).

        Returns a dict containing:
          - Sub-scores: valuation_score, health_score, profitability_score,
            growth_score, shareholder_score, risk_score
          - Quality: piotroski_f, altman_z, altman_zone, graham_number,
            graham_mos
          - DCF: dcf_mos_low/mid/high, dcf_fair_value_low/mid/high,
            wacc_used, dcf_warnings (best-effort; all may be None)
          - Horizons: score_lt, score_mt, score_st, signal_lt, signal_mt,
            signal_st, passes_gates_lt/mt/st, blockers_lt/mt/st
            (populated when score_three_horizons has been run on a universe
            that includes this row; for single-ticker flow they fall back to
            the legacy composite signal)

        For single-ticker scoring we build a tiny 1-row DataFrame so the
        vectorised scoring path (sector-relative percentiles, DCF, M7 horizon
        gates) operates correctly.
        """
        # Build a 1-row DataFrame to reuse the vectorised engine path.
        single_df = pd.DataFrame([row])
        if single_df.index[0] != row.get("Ticker", "UNKNOWN"):
            ticker_val = row.get("Ticker", "UNKNOWN")
            single_df.index = [ticker_val]

        scored_df = score_universe(single_df)
        if scored_df.empty:
            return self._fallback_single(row)

        return self.extract_scoring_from_row(scored_df.iloc[0])

    def extract_scoring_from_row(self, scored_row: pd.Series) -> dict[str, Any]:
        """
        Build the scoring dict from a row that has ALREADY been scored.

        Same output shape as ``score_single``. Used by the company-detail
        endpoint when a row comes from the screener cache: the row already
        carries every Valuation_Score / score_lt / DCF_* / Risk_* column,
        so we skip the engine call and just project to the API shape.
        """
        # --- Sub-scores ---
        sub = {
            "valuation_score": _safe_float(scored_row.get("Valuation_Score", 50.0)),
            "health_score": _safe_float(scored_row.get("Health_Score", 50.0)),
            "profitability_score": _safe_float(scored_row.get("Profitability_Score", 50.0)),
            "growth_score": _safe_float(scored_row.get("Growth_Score", 50.0)),
            "shareholder_score": _safe_float(scored_row.get("Shareholder_Score", 50.0)),
            "risk_score": _safe_float(scored_row.get("Risk_Score", 50.0)),
        }

        # --- Quality signals ---
        az = _safe_float(scored_row.get("Altman_Z"))
        gn = _safe_float(scored_row.get("Graham_Number"))
        price = _safe_float(scored_row.get("Price"))
        graham_mos_val: float | None = None
        if gn is not None and price and price > 0:
            graham_mos_val = round((gn / price - 1) * 100, 1)

        quality = {
            "piotroski_f": int(scored_row.get("Piotroski_F", 0)) if pd.notna(scored_row.get("Piotroski_F")) else None,
            "altman_z": az,
            "altman_zone": _altman_zone(az),
            "graham_number": gn,
            "graham_mos": _safe_float(scored_row.get("Graham_MoS")) or graham_mos_val,
            "earnings_quality_score": _safe_float(scored_row.get("EarningsQuality_Score")),
            "moat_score": _safe_float(scored_row.get("Moat_Score")),
            "m_score": _safe_float(scored_row.get("M_Score")),
            "sloan_accruals": _safe_float(scored_row.get("Sloan_Accruals")),
            "cash_conversion_ratio_5y": _safe_float(scored_row.get("CashConversionRatio_5y")),
        }

        # --- DCF ---
        dcf_warnings: list[str] = []
        raw_warnings = scored_row.get("DCF_Warnings")
        if isinstance(raw_warnings, list):
            dcf_warnings = [str(w) for w in raw_warnings]

        dcf = {
            "fair_value_low": _safe_float(scored_row.get("DCF_FairValue_Low")),
            "fair_value_mid": _safe_float(scored_row.get("DCF_FairValue_Mid")),
            "fair_value_high": _safe_float(scored_row.get("DCF_FairValue_High")),
            "mos_low": _safe_float(scored_row.get("DCF_MoS_Low")),
            "mos_mid": _safe_float(scored_row.get("DCF_MoS_Mid")),
            "mos_high": _safe_float(scored_row.get("DCF_MoS_High")),
            "wacc_used": _safe_float(scored_row.get("WACC_Used")),
            "warnings": dcf_warnings,
        }

        # --- Risk signals ---
        risk = {
            "risk_score": _safe_float(scored_row.get("Risk_Score_v2")),
            "realized_vol_1y": _safe_float(scored_row.get("Realized_Vol_1y")),
            "max_drawdown_3y": _safe_float(scored_row.get("MaxDrawdown_3y")),
            "net_debt_ebitda": _safe_float(scored_row.get("NetDebt_EBITDA")),
            "interest_coverage": _safe_float(scored_row.get("InterestCoverage")),
            "beta": _safe_float(scored_row.get("Beta")),
        }

        # --- Momentum signals ---
        def _bool_or_none(val: Any) -> bool | None:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return None
            return bool(val)

        momentum = {
            "momentum_12_1": _safe_float(scored_row.get("Momentum_12_1")),
            "rs_3m": _safe_float(scored_row.get("RS_3m")),
            "above_50dma": _bool_or_none(scored_row.get("Above_50DMA")),
            "above_200dma": _bool_or_none(scored_row.get("Above_200DMA")),
            "golden_cross": _bool_or_none(scored_row.get("Golden_Cross")),
            "volume_surge": _safe_float(scored_row.get("Volume_Surge")),
            "eps_revision_30d": _safe_float(scored_row.get("EPS_Rev_30d")),
            "eps_revision_90d": _safe_float(scored_row.get("EPS_Rev_90d")),
            "sue_z_score": _safe_float(scored_row.get("SUE")),
            "sentiment_30d": _safe_float(scored_row.get("Sentiment_30d")),
            "sentiment_trend": _safe_float(scored_row.get("Sentiment_Trend")),
        }

        # --- Three-horizon scoring ---
        # The engine emits score_lt/mt/st when M7 is active. Fall back to the
        # legacy Composite_Score for single-ticker calls on sparse universes.
        composite_fallback = _safe_float(scored_row.get("Composite_Score", 50.0)) or 50.0
        signal_fallback = str(scored_row.get("Signal") or generate_signal(composite_fallback))

        def _blockers(col: str) -> list[str]:
            raw = scored_row.get(col)
            if isinstance(raw, list):
                return raw
            return []

        horizons = {
            "long_term": {
                "score": _safe_float(scored_row.get("score_lt")) or composite_fallback,
                "signal": str(scored_row.get("signal_lt") or signal_fallback),
                "passes_gates": bool(scored_row.get("passes_gates_lt", True)),
                "blockers": _blockers("blockers_lt"),
                "recommended_account": None,
            },
            "medium_term": {
                "score": _safe_float(scored_row.get("score_mt")) or composite_fallback,
                "signal": str(scored_row.get("signal_mt") or signal_fallback),
                "passes_gates": bool(scored_row.get("passes_gates_mt", True)),
                "blockers": _blockers("blockers_mt"),
                "recommended_account": None,
            },
            "short_term": {
                "score": _safe_float(scored_row.get("score_st")) or composite_fallback,
                "signal": str(scored_row.get("signal_st") or signal_fallback),
                "passes_gates": bool(scored_row.get("passes_gates_st", True)),
                "blockers": _blockers("blockers_st"),
                "recommended_account": "CTO",
            },
        }

        return {
            **sub,
            **quality,
            "dcf": dcf,
            "risk": risk,
            "momentum": momentum,
            "horizons": horizons,
            "data_completeness": _safe_float(scored_row.get("data_completeness", 0.0)) or 0.0,
        }

    def _fallback_single(self, row: pd.Series) -> dict[str, Any]:
        """Minimal fallback when the vectorised path produces an empty result."""
        scores = compute_composite_score(row)
        composite = scores.get("composite", 50.0)
        signal = generate_signal(composite)

        az = _safe_float(altman_z_score(row))
        gn = _safe_float(graham_number(row))
        price = _safe_float(row.get("Price"))
        graham_mos_val = round((gn / price - 1) * 100, 1) if gn and price and price > 0 else None
        piotroski = piotroski_f_score(row)

        horizon_block = {
            "score": composite,
            "signal": signal,
            "passes_gates": True,
            "blockers": [],
            "recommended_account": None,
        }
        return {
            "valuation_score": round(scores.get("valuation", 50.0), 1),
            "health_score": round(scores.get("financial_health", 50.0), 1),
            "profitability_score": round(scores.get("profitability", 50.0), 1),
            "growth_score": round(scores.get("growth", 50.0), 1),
            "shareholder_score": round(scores.get("shareholder_return", 50.0), 1),
            "risk_score": round(scores.get("risk", 50.0), 1),
            "piotroski_f": piotroski,
            "altman_z": az,
            "altman_zone": _altman_zone(az),
            "graham_number": gn,
            "graham_mos": graham_mos_val,
            "earnings_quality_score": None,
            "moat_score": None,
            "m_score": None,
            "sloan_accruals": None,
            "cash_conversion_ratio_5y": None,
            "dcf": {
                "fair_value_low": None,
                "fair_value_mid": None,
                "fair_value_high": None,
                "mos_low": None,
                "mos_mid": None,
                "mos_high": None,
                "wacc_used": None,
                "warnings": [],
            },
            "risk": {
                "risk_score": None,
                "realized_vol_1y": None,
                "max_drawdown_3y": None,
                "net_debt_ebitda": None,
                "interest_coverage": _safe_float(row.get("InterestCoverage")),
                "beta": _safe_float(row.get("Beta")),
            },
            "momentum": {
                "momentum_12_1": None,
                "rs_3m": None,
                "above_50dma": None,
                "above_200dma": None,
                "golden_cross": None,
                "volume_surge": None,
                "eps_revision_30d": None,
                "eps_revision_90d": None,
                "sue_z_score": None,
                "sentiment_30d": None,
                "sentiment_trend": None,
            },
            "horizons": {
                "long_term": {**horizon_block},
                "medium_term": {**horizon_block},
                "short_term": {**horizon_block, "recommended_account": "CTO"},
            },
            "data_completeness": 0.0,
        }

    @staticmethod
    def get_weights() -> dict[str, float]:
        """Return the scoring category weights."""
        return dict(SCORING_WEIGHTS)

    @staticmethod
    def get_thresholds() -> dict[str, Any]:
        """Return the signal threshold configuration."""
        return dict(SIGNAL_THRESHOLDS)
