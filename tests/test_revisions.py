"""Tests for src/analysis/revisions.py (M9)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.analysis.revisions import (
    eps_revision_change,
    revisions_score,
    revisions_signals_df,
    sue_z_score,
)


# ---------------------------------------------------------------------------
# eps_revision_change
# ---------------------------------------------------------------------------


def test_eps_revision_change_30d_plus5pct():
    """Two estimate rows, 30 days apart, 1.00 -> 1.05 -> +5%."""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-02-01"]),
        "estimatedEpsAvg": [1.00, 1.05],
    })
    rev = eps_revision_change(df, days=30)
    assert math.isclose(rev, 0.05, rel_tol=1e-9)


def test_eps_revision_change_negative():
    """Estimates moved DOWN over the lookback window."""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-04-01"]),
        "estimatedEpsAvg": [2.00, 1.80],
    })
    rev = eps_revision_change(df, days=90)
    assert math.isclose(rev, -0.10, rel_tol=1e-9)


def test_eps_revision_change_insufficient_history_returns_nan():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01"]),
        "estimatedEpsAvg": [1.00],
    })
    assert math.isnan(eps_revision_change(df, days=30))


def test_eps_revision_change_lookback_outside_window_returns_nan():
    """If the only rows are within the lookback window the prior is missing."""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-12-25", "2025-12-31"]),
        "estimatedEpsAvg": [1.00, 1.05],
    })
    # Asking for 90d revision when both rows are within the same week
    assert math.isnan(eps_revision_change(df, days=90))


def test_eps_revision_change_empty_frame():
    assert math.isnan(eps_revision_change(pd.DataFrame(), days=30))


def test_eps_revision_change_ignores_zero_prior():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-02-01"]),
        "estimatedEpsAvg": [0.0, 1.0],
    })
    assert math.isnan(eps_revision_change(df, days=30))


# ---------------------------------------------------------------------------
# sue_z_score
# ---------------------------------------------------------------------------


def test_sue_z_score_basic():
    """SUE = (1.10 - 1.00) / 0.05 = 2.0 (strong beat)."""
    assert math.isclose(sue_z_score(1.10, 1.00, 0.05), 2.0, rel_tol=1e-9)


def test_sue_z_score_negative_miss():
    assert math.isclose(sue_z_score(0.80, 1.00, 0.10), -2.0, rel_tol=1e-9)


def test_sue_z_score_zero_std_returns_nan():
    assert math.isnan(sue_z_score(1.0, 1.0, 0.0))


def test_sue_z_score_nan_input_returns_nan():
    assert math.isnan(sue_z_score(float("nan"), 1.0, 0.05))


def test_sue_z_score_from_synthetic_priors():
    """Compute std of [0.01, 0.02, -0.01, 0.02] explicitly and verify SUE."""
    priors = np.array([0.01, 0.02, -0.01, 0.02])
    std = float(priors.std(ddof=1))  # sample stddev
    sue = sue_z_score(1.10, 1.00, std)
    assert math.isclose(sue, 0.10 / std, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# revisions_score
# ---------------------------------------------------------------------------


def test_revisions_score_strong_beat_high():
    """All revisions positive, strong SUE -> score should be high (>70)."""
    today = pd.Timestamp("2025-12-31")
    df = pd.DataFrame({
        "date": [today - pd.Timedelta(days=200), today - pd.Timedelta(days=100),
                 today - pd.Timedelta(days=40), today],
        "estimatedEpsAvg": [1.00, 1.10, 1.20, 1.30],
    })
    score = revisions_score(df, latest_surprise={
        "reported_eps": 1.30, "expected_eps": 1.20, "prior_surprises_std": 0.05,
    })
    assert score is not None and score > 70


def test_revisions_score_strong_miss_low():
    today = pd.Timestamp("2025-12-31")
    df = pd.DataFrame({
        "date": [today - pd.Timedelta(days=200), today - pd.Timedelta(days=100),
                 today - pd.Timedelta(days=40), today],
        "estimatedEpsAvg": [1.30, 1.20, 1.10, 1.00],
    })
    score = revisions_score(df, latest_surprise={
        "reported_eps": 0.80, "expected_eps": 1.00, "prior_surprises_std": 0.05,
    })
    assert score is not None and score < 30


def test_revisions_score_empty_returns_nan():
    score = revisions_score(pd.DataFrame(), latest_surprise=None)
    assert math.isnan(score)


# ---------------------------------------------------------------------------
# revisions_signals_df
# ---------------------------------------------------------------------------


def test_revisions_signals_df_columns_and_values():
    today = pd.Timestamp("2025-12-31")
    df_a = pd.DataFrame({
        "date": [today - pd.Timedelta(days=200), today],
        "estimatedEpsAvg": [1.00, 1.10],
    })
    df_b = pd.DataFrame({
        "date": [today - pd.Timedelta(days=200), today],
        "estimatedEpsAvg": [2.00, 1.80],
    })
    estimates_map = {"AAPL": df_a, "MSFT": df_b}
    surprises_map = {
        "AAPL": {"reported_eps": 1.10, "expected_eps": 1.00, "prior_surprises_std": 0.05},
        "MSFT": {"reported_eps": 1.70, "expected_eps": 1.80, "prior_surprises_std": 0.05},
    }
    out = revisions_signals_df(estimates_map, surprises_map)
    expected_cols = {"EPS_Rev_30d", "EPS_Rev_90d", "EPS_Rev_180d", "SUE", "Revisions_Score"}
    assert expected_cols.issubset(set(out.columns))
    assert list(out.index) == ["AAPL", "MSFT"]
    # AAPL: positive revision over 180d
    assert out.loc["AAPL", "EPS_Rev_180d"] > 0
    # MSFT: negative revision
    assert out.loc["MSFT", "EPS_Rev_180d"] < 0
    # AAPL SUE positive, MSFT negative
    assert out.loc["AAPL", "SUE"] > 0
    assert out.loc["MSFT", "SUE"] < 0


def test_revisions_signals_df_empty_input():
    out = revisions_signals_df({}, surprises_map={})
    assert out.empty
    assert "Revisions_Score" in out.columns
