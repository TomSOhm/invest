"""Tests for ChartService (price history + computed metrics)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.app.models.chart import (
    Candle,
    ChartMetrics,
    MovingAverages,
    PriceHistoryResponse,
)


def test_candle_model_round_trip() -> None:
    c = Candle(date="2025-01-02", open=100.0, high=101.0, low=99.5, close=100.5, volume=1_000_000)
    assert c.model_dump()["close"] == 100.5


def test_price_history_response_minimal() -> None:
    resp = PriceHistoryResponse(
        ticker="AAPL",
        period="1Y",
        benchmark=None,
        candles=[
            Candle(date="2025-01-02", open=100, high=101, low=99, close=100.5, volume=1e6),
        ],
        benchmark_candles=[],
        metrics=ChartMetrics(
            total_return=0.12,
            cagr=0.12,
            annualized_vol=0.18,
            max_drawdown=-0.10,
            beta=None,
            sharpe=0.5,
        ),
        moving_averages=MovingAverages(ma_50=[], ma_200=[]),
    )
    assert resp.ticker == "AAPL"
    assert resp.metrics.beta is None


# ---------------------------------------------------------------------------
# ChartService tests
# ---------------------------------------------------------------------------

from backend.app.services.cache_service import CacheService
from backend.app.services.chart_service import ChartService
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher


def _fake_history(n: int = 252, start: float = 100.0, drift: float = 0.0005) -> pd.DataFrame:
    rng = np.random.default_rng(seed=42)
    rets = rng.normal(loc=drift, scale=0.01, size=n)
    closes = start * np.cumprod(1 + rets)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes * 1.005,
            "Low": closes * 0.995,
            "Close": closes,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


@pytest.fixture
def chart_svc(tmp_path: Path) -> ChartService:
    yf_fetcher = YFinanceDataFetcher(cache=CacheService(cache_dir=tmp_path / "cache"))
    return ChartService(yf_fetcher=yf_fetcher)


def test_get_price_history_no_benchmark(chart_svc: ChartService) -> None:
    with patch.object(chart_svc._yf, "fetch_multi_price_history", return_value={"AAPL": _fake_history()}):
        resp = chart_svc.get_price_history("AAPL", period="1Y", benchmark=None)
    assert resp["ticker"] == "AAPL"
    assert resp["benchmark"] is None
    assert resp["benchmark_candles"] == []
    assert resp["metrics"]["beta"] is None
    assert resp["metrics"]["total_return"] is not None
    assert len(resp["candles"]) > 0


def test_period_slicing_1m_shorter_than_1y(chart_svc: ChartService) -> None:
    long_df = _fake_history(n=252)
    with patch.object(chart_svc._yf, "fetch_multi_price_history", return_value={"AAPL": long_df}):
        one_m = chart_svc.get_price_history("AAPL", period="1M", benchmark=None)
        one_y = chart_svc.get_price_history("AAPL", period="1Y", benchmark=None)
    assert len(one_m["candles"]) < len(one_y["candles"])


def test_beta_set_when_benchmark_present(chart_svc: ChartService) -> None:
    stock = _fake_history(n=252)
    bench = _fake_history(n=252, drift=0.0003)
    with patch.object(
        chart_svc._yf,
        "fetch_multi_price_history",
        return_value={"AAPL": stock, "^GSPC": bench},
    ):
        resp = chart_svc.get_price_history("AAPL", period="1Y", benchmark="^GSPC")
    assert resp["metrics"]["beta"] is not None
    assert len(resp["benchmark_candles"]) > 0


def test_moving_averages_alignment(chart_svc: ChartService) -> None:
    with patch.object(chart_svc._yf, "fetch_multi_price_history", return_value={"AAPL": _fake_history(n=300)}):
        resp = chart_svc.get_price_history("AAPL", period="1Y", benchmark=None)
    candles_n = len(resp["candles"])
    assert len(resp["moving_averages"]["ma_50"]) == candles_n
    assert len(resp["moving_averages"]["ma_200"]) == candles_n


def test_cagr_uses_calendar_days(chart_svc: ChartService) -> None:
    # 280 business days ≈ 392 calendar days > 365.25, so CAGR is set.
    with patch.object(chart_svc._yf, "fetch_multi_price_history", return_value={"AAPL": _fake_history(n=280, drift=0.0005)}):
        resp = chart_svc.get_price_history("AAPL", period="5Y", benchmark=None)
    assert resp["metrics"]["cagr"] is not None


def test_short_period_skips_cagr(chart_svc: ChartService) -> None:
    with patch.object(chart_svc._yf, "fetch_multi_price_history", return_value={"AAPL": _fake_history(n=252)}):
        resp = chart_svc.get_price_history("AAPL", period="1M", benchmark=None)
    # 1M slice is < 1 calendar year → cagr stays None
    assert resp["metrics"]["cagr"] is None
    assert resp["metrics"]["total_return"] is not None


def test_empty_frame_returns_empty_response(chart_svc: ChartService) -> None:
    with patch.object(chart_svc._yf, "fetch_multi_price_history", return_value={}):
        resp = chart_svc.get_price_history("ZZZ", period="1Y", benchmark=None)
    assert resp["candles"] == []
    assert resp["metrics"]["total_return"] is None


def test_beta_requires_60_obs(chart_svc: ChartService) -> None:
    # Only 30 days of overlap → beta should stay None
    stock = _fake_history(n=30)
    bench = _fake_history(n=30)
    with patch.object(
        chart_svc._yf,
        "fetch_multi_price_history",
        return_value={"AAPL": stock, "^GSPC": bench},
    ):
        resp = chart_svc.get_price_history("AAPL", period="1M", benchmark="^GSPC")
    assert resp["metrics"]["beta"] is None
