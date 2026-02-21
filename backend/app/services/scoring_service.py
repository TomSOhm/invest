"""
Invest Solo -- Scoring Service
Thin wrapper around the existing src/analysis/scoring_engine.py module.
"""
from typing import Any, Dict

import numpy as np
import pandas as pd
from loguru import logger

from src.analysis.scoring_engine import (
    score_universe,
    compute_composite_score,
    generate_signal,
    piotroski_f_score,
    altman_z_score,
    graham_number,
    SCORING_WEIGHTS,
    SIGNAL_THRESHOLDS,
)


class ScoringService:
    """Delegates scoring to the existing scoring_engine module."""

    def score_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Score an entire DataFrame of stocks.
        Expects a DataFrame indexed by Ticker with the standard column schema.
        Returns the same DataFrame with scoring columns appended.
        """
        if df.empty:
            logger.warning("score_dataframe called with empty DataFrame")
            return df
        logger.info(f"Scoring {len(df)} stocks")
        return score_universe(df)

    def score_single(self, row: pd.Series) -> Dict[str, Any]:
        """
        Score a single stock (represented as a pandas Series).

        Returns a dict containing:
            composite_score, signal, valuation_score, health_score,
            profitability_score, growth_score, shareholder_score, risk_score,
            piotroski_f, altman_z, graham_number, graham_mos
        """
        scores = compute_composite_score(row)
        composite = scores["composite"]
        signal = generate_signal(composite)
        piotroski = piotroski_f_score(row)

        az = altman_z_score(row)
        az = round(az, 2) if pd.notna(az) and not np.isinf(az) else None

        gn = graham_number(row)
        gn = round(gn, 2) if pd.notna(gn) and not np.isinf(gn) else None

        # Graham margin of safety
        price = row.get("Price", 0)
        if gn is not None and price and price > 0:
            graham_mos = round((gn / price - 1) * 100, 1)
        else:
            graham_mos = None

        return {
            "composite_score": composite,
            "signal": signal,
            "valuation_score": round(scores["valuation"], 1),
            "health_score": round(scores["financial_health"], 1),
            "profitability_score": round(scores["profitability"], 1),
            "growth_score": round(scores["growth"], 1),
            "shareholder_score": round(scores["shareholder_return"], 1),
            "risk_score": round(scores["risk"], 1),
            "piotroski_f": piotroski,
            "altman_z": az,
            "graham_number": gn,
            "graham_mos": graham_mos,
        }

    @staticmethod
    def get_weights() -> Dict[str, float]:
        """Return the scoring category weights."""
        return dict(SCORING_WEIGHTS)

    @staticmethod
    def get_thresholds() -> Dict[str, Any]:
        """Return the signal threshold configuration."""
        return dict(SIGNAL_THRESHOLDS)
